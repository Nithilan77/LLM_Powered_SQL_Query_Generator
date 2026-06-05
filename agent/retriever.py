"""
retriever.py  --  Phase 3: RAG schema linking.

Instead of dumping ALL table descriptions into every prompt, we:
  1. (once) embed each table's semantic description into a vector.
  2. (per question) embed the question, find the top-k most similar tables
     by cosine similarity, and return only those table names.

Why no ChromaDB / FAISS here?
  We have SIX vectors. A vector database is infrastructure for searching
  millions. At this scale, cosine similarity in numpy is simpler, has zero
  extra dependencies, and is identically correct. The retrieve() interface
  below is the contract -- swapping in FAISS later (for a 200-table schema)
  is a drop-in change behind this same function.

The embedding model is injected, so we can use a real SentenceTransformer in
production and a fake one in tests (keeps tests fast and offline).
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from semantic_layer import SEMANTIC_LAYER, render_table  # noqa: E402


def _default_embedder():
    """Lazily load the local sentence-transformer (downloaded once, ~90MB)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    return lambda texts: np.asarray(model.encode(list(texts)), dtype=np.float32)


def _cosine_top_k(query_vec: np.ndarray, matrix: np.ndarray, k: int):
    """
    Return indices of the k rows in `matrix` most similar to `query_vec`.
    Cosine similarity = normalized dot product.
    """
    # normalize to unit length so dot product == cosine similarity
    q = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    sims = m @ q  # (n_tables,) similarity score per table
    top = np.argsort(-sims)[:k]  # highest similarity first
    return top, sims


class SchemaRetriever:
    """
    Embeds table descriptions once at construction, then answers
    retrieve(question, k) -> list of table names.
    """

    # In a star schema the fact table is needed by nearly every query, so we
    # pin it rather than relying on retrieval to surface it. RAG picks the dims.
    ALWAYS_INCLUDE = ("fact_orders",)

    def __init__(self, embedder=None):
        self.embedder = embedder or _default_embedder()
        self.table_names = list(SEMANTIC_LAYER.keys())
        # Embed the human-readable description of each table.
        descriptions = [self._table_text(t) for t in self.table_names]
        self.matrix = self.embedder(descriptions)  # (n_tables, dim)

    def _table_text(self, table_name: str) -> str:
        """
        The text we embed for a table. We include the purpose AND a
        natural-language line about each column (not just column names),
        so the description is richer and separates better in vector space.
        Terse 'col1, col2, col3' lists embed too similarly across tables.
        """
        entry = SEMANTIC_LAYER[table_name]
        col_lines = "; ".join(
            f"{col} ({desc.split('.')[0]})" for col, desc in entry["columns"].items()
        )
        return f"{table_name}. {entry['description']} Relevant fields: {col_lines}"

    def retrieve(self, question: str, k: int = 3):
        """
        Return the table names most relevant to the question.

        STAR-SCHEMA DESIGN CHOICE: fact_orders is the central fact table that
        almost every analytical query needs (all revenue, orders, status, and
        the FKs live there). Rather than gamble on retrieval surfacing it, we
        ALWAYS include it and use RAG to pick the relevant DIMENSIONS around it.
        This is why a star schema is RAG-friendly: pin the fact, retrieve dims.
        """
        q_vec = self.embedder([question])[0]
        idx, sims = _cosine_top_k(q_vec, self.matrix, len(self.table_names))
        ranked = [self.table_names[i] for i in idx]

        result = list(self.ALWAYS_INCLUDE)
        for t in ranked:
            if t not in result:
                result.append(t)
            if len(result) >= k:
                break
        return result[:k]

    def retrieve_with_scores(self, question: str, k: int = 3):
        """Same, but also return the similarity score (useful for debugging)."""
        q_vec = self.embedder([question])[0]
        idx, sims = _cosine_top_k(q_vec, self.matrix, len(self.table_names))
        score_map = {self.table_names[i]: float(sims[i]) for i in idx}
        tables = self.retrieve(question, k)
        return [(t, score_map[t]) for t in tables]

    def render_retrieved(self, question: str, k: int = 3) -> str:
        """Render the FULL semantic descriptions of just the retrieved tables."""
        tables = self.retrieve(question, k)
        return "\n\n".join(render_table(t) for t in tables)


if __name__ == "__main__":
    # Uses the real local model. First run downloads it.
    r = SchemaRetriever()
    for q in [
        "What are the top categories by revenue?",
        "How many repeat customers do we have?",
        "Which sellers have the best reviews?",
        "Where are most customers located?",
    ]:
        print(f"\nQ: {q}")
        for name, score in r.retrieve_with_scores(q, k=3):
            print(f"   {score:.3f}  {name}")
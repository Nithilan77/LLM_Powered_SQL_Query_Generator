import { useState, useEffect } from "react";

// Point this at your FastAPI server.
const API = "http://localhost:8000";

const SAMPLE_QUESTIONS = [
  "What are the top 5 product categories by total revenue?",
  "Which 5 states have the most canceled orders?",
  "How many customers are repeat buyers?",
  "What is the monthly revenue trend in 2018?",
];

export default function App() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [schema, setSchema] = useState([]);

  useEffect(() => {
    fetch(`${API}/schema`)
      .then((r) => r.json())
      .then((d) => setSchema(d.tables || []))
      .catch(() => {});
  }, []);

  async function ask(q) {
    const query = (q ?? question).trim();
    if (!query) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await fetch(`${API}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: query }),
      });
      const data = await r.json();
      if (!data.success) {
        setError(data.error || "Query failed.");
        setResult(data.sql ? data : null);
      } else {
        setResult(data);
      }
    } catch (e) {
      setError("Could not reach the API. Is the server running on :8000?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={S.page}>
      <div style={S.container}>
        <header style={S.header}>
          <h1 style={S.title}>Ask the Database</h1>
          <p style={S.subtitle}>
            Plain English in. Real SQL and results out. No SQL required.
          </p>
        </header>

        <div style={S.inputRow}>
          <input
            style={S.input}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder="e.g. Which sellers have the best reviews?"
          />
          <button style={S.button} onClick={() => ask()} disabled={loading}>
            {loading ? "Thinking…" : "Ask"}
          </button>
        </div>

        <div style={S.chips}>
          {SAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              style={S.chip}
              onClick={() => {
                setQuestion(q);
                ask(q);
              }}
            >
              {q}
            </button>
          ))}
        </div>

        {error && <div style={S.error}>{error}</div>}

        {result && (
          <div style={S.results}>
            {/* diagnostics */}
            <div style={S.badges}>
              {result.tables_used?.map((t) => (
                <span key={t} style={S.badge}>{t}</span>
              ))}
              {result.repaired && (
                <span style={{ ...S.badge, ...S.badgeWarn }}>
                  self-corrected ({result.attempts} tries)
                </span>
              )}
              {typeof result.latency_ms === "number" && (
                <span style={{ ...S.badge, ...S.badgeMuted }}>
                  {result.latency_ms} ms
                </span>
              )}
            </div>

            {result.sql && (
              <pre style={S.sql}><code>{result.sql}</code></pre>
            )}

            {result.columns && result.rows && (
              <div style={S.tableWrap}>
                <table style={S.table}>
                  <thead>
                    <tr>
                      {result.columns.map((c) => (
                        <th key={c} style={S.th}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.slice(0, 100).map((row, i) => (
                      <tr key={i}>
                        {row.map((v, j) => (
                          <td key={j} style={S.td}>{String(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {result.rows.length > 100 && (
                  <p style={S.more}>
                    Showing first 100 of {result.rows.length} rows
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {schema.length > 0 && (
          <details style={S.schemaBox}>
            <summary style={S.schemaSummary}>
              Database schema ({schema.length} tables)
            </summary>
            {schema.map((t) => (
              <div key={t.table} style={S.schemaTable}>
                <strong>{t.table}</strong>
                <span style={S.schemaCols}>{t.columns.join(", ")}</span>
              </div>
            ))}
          </details>
        )}
      </div>
    </div>
  );
}

const S = {
  page: {
    minHeight: "100vh",
    background: "#0f1117",
    color: "#e6e8ee",
    fontFamily: "system-ui, -apple-system, sans-serif",
    padding: "48px 16px",
  },
  container: { maxWidth: 820, margin: "0 auto" },
  header: { marginBottom: 28 },
  title: { fontSize: 34, fontWeight: 700, margin: 0, letterSpacing: "-0.02em" },
  subtitle: { color: "#9aa3b2", marginTop: 8, fontSize: 15 },
  inputRow: { display: "flex", gap: 10 },
  input: {
    flex: 1,
    padding: "14px 16px",
    fontSize: 15,
    borderRadius: 10,
    border: "1px solid #2a2f3a",
    background: "#171a22",
    color: "#e6e8ee",
    outline: "none",
  },
  button: {
    padding: "14px 24px",
    fontSize: 15,
    fontWeight: 600,
    borderRadius: 10,
    border: "none",
    background: "#4f7cff",
    color: "white",
    cursor: "pointer",
  },
  chips: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 },
  chip: {
    padding: "7px 12px",
    fontSize: 13,
    borderRadius: 999,
    border: "1px solid #2a2f3a",
    background: "#171a22",
    color: "#b8c0cf",
    cursor: "pointer",
  },
  error: {
    marginTop: 20,
    padding: "12px 16px",
    borderRadius: 10,
    background: "#2a1a1d",
    border: "1px solid #5c2a30",
    color: "#ffb4ba",
  },
  results: { marginTop: 28 },
  badges: { display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 },
  badge: {
    padding: "4px 10px",
    fontSize: 12,
    borderRadius: 6,
    background: "#1c2330",
    border: "1px solid #2a3344",
    color: "#8fb0ff",
  },
  badgeWarn: { color: "#ffd27a", borderColor: "#4a3a1a", background: "#2a2316" },
  badgeMuted: { color: "#9aa3b2" },
  sql: {
    margin: 0,
    padding: 18,
    borderRadius: 12,
    background: "#0b0d13",
    border: "1px solid #222733",
    color: "#9ad1a8",
    fontSize: 13.5,
    lineHeight: 1.5,
    overflowX: "auto",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  },
  tableWrap: {
    marginTop: 16,
    borderRadius: 12,
    border: "1px solid #222733",
    overflow: "auto",
    maxHeight: 460,
  },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 13.5 },
  th: {
    position: "sticky",
    top: 0,
    textAlign: "left",
    padding: "10px 14px",
    background: "#161a22",
    color: "#c8cedb",
    borderBottom: "1px solid #222733",
    fontWeight: 600,
  },
  td: {
    padding: "9px 14px",
    borderBottom: "1px solid #1a1e27",
    color: "#d4d9e2",
  },
  more: { color: "#9aa3b2", fontSize: 12, padding: "10px 14px", margin: 0 },
  schemaBox: {
    marginTop: 32,
    padding: 16,
    borderRadius: 12,
    background: "#12141b",
    border: "1px solid #222733",
  },
  schemaSummary: { cursor: "pointer", color: "#b8c0cf", fontSize: 14 },
  schemaTable: { marginTop: 12, fontSize: 13 },
  schemaCols: { color: "#8b94a5", marginLeft: 10 },
};
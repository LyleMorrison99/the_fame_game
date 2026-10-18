import { useState } from "react";
import { api, ErrorNote, money, Monogram, Toast, until, useApp, useNow, usePoll, useToast, when } from "../lib.jsx";

export default function Ipo() {
  const { state } = useApp();
  const now = useNow();
  const [d, setD] = useState(null);
  const [f, setF] = useState({ name: "", category: "", pitch: "" });
  const [error, setError] = useState("");
  const [toast, showToast] = useToast();
  usePoll(async () => { try { setD(await api("/api/petitions")); } catch { /* keep */ } }, 10000);
  if (!d) return <div className="empty">Loading…</div>;
  const cats = state?.categories || [];
  const top = Math.max(1, ...d.open.map((p) => p.votes));

  const vote = async (id) => {
    setError("");
    try {
      setD(id === d.my_vote ? await api("/api/petitions/vote", { method: "DELETE" }) : await api(`/api/petitions/${id}/vote`, { method: "POST" }));
    } catch (e) { setError(e.message); }
  };
  const nominate = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setD(await api("/api/petitions", { method: "POST", body: { ...f, category: f.category || cats[0] } }));
      setF({ name: "", category: "", pitch: "" });
      showToast("Petition posted. Your vote moved to it.");
    } catch (err) { setError(err.message); }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <span className="label">One new listing a week</span>
          <h1>IPOs &amp; Petitions</h1>
          <p className="muted">Vote for who should list next. Admins pick the weekly IPO from the top of the board.</p>
        </div>
      </div>

      {d.ipos.length > 0 && (
        <div className="stats" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
          {d.ipos.map((p) => (
            <a key={p.id} href={`#/p/${p.id}`} className="card card-pad stack ipo-card" style={{ textDecoration: "none" }}>
              <div className="row"><Monogram name={p.name} size={40} /><div><span className="label" style={{ color: "var(--gold)" }}>{p.status === "ipo" ? "Window open" : "Coming up"}</span><h2>{p.name}</h2></div></div>
              {p.status === "ipo" ? (
                <>
                  <div className="spread small"><span className="muted">Est. IPO price</span><span className="num">{money(p.ipo.est_price)}</span></div>
                  <div className="spread small"><span className="muted">Committed by {p.ipo.backers}</span><span className="num">{money(p.ipo.committed, 0)}</span></div>
                  <div className="spread small"><span className="muted">Closes in</span><span className="num">{until(p.ipo_closes_at, now)}</span></div>
                  <span className="btn btn-primary">Commit up to {money(state?.ipo_cap || 1000, 0)}</span>
                </>
              ) : (
                <>
                  <div className="spread small"><span className="muted">Opens</span><span>{when(p.ipo_opens_at)}</span></div>
                  <div className="spread small"><span className="muted">Countdown</span><span className="num">{until(p.ipo_opens_at, now)}</span></div>
                </>
              )}
            </a>
          ))}
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-head"><h3>Petition board</h3><span className="tiny faint">You get one vote. Tap again to take it back.</span></div>
          {d.open.map((p, i) => (
            <div key={p.id} className={"petition" + (i === 0 && p.votes ? " lead" : "")}>
              <span className="rank">{i + 1}</span>
              <div style={{ minWidth: 0 }}>
                <strong>{p.name}</strong> <span className="tiny faint">{p.category} · by {p.by}</span>
                {p.pitch && <div className="small muted">{p.pitch}</div>}
                <div className="vote-bar"><div style={{ width: `${(p.votes / top) * 100}%` }} /></div>
              </div>
              <button className={"btn btn-sm" + (d.my_vote === p.id ? " btn-primary" : "")} onClick={() => vote(p.id)} aria-pressed={d.my_vote === p.id}>
                <span className="num">{p.votes}</span> {d.my_vote === p.id ? "Voted" : "Vote"}
              </button>
            </div>
          ))}
          {!d.open.length && <div className="empty">No petitions yet. Nominate someone.</div>}
        </div>

        <div className="stack">
          <form className="card card-pad stack" onSubmit={nominate}>
            <h3>Nominate someone</h3>
            <label className="field"><span>Name</span><input id="nominee" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required maxLength={80} /></label>
            <label className="field"><span>Category</span>
              <select id="nominee-cat" className="input" value={f.category || cats[0] || ""} onChange={(e) => setF({ ...f, category: e.target.value })}>
                {cats.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label className="field"><span>Why now?</span><textarea id="pitch" className="input" value={f.pitch} onChange={(e) => setF({ ...f, pitch: e.target.value })} maxLength={280} placeholder="New album drops Friday. Trust me." /></label>
            <ErrorNote error={error} />
            <button className="btn btn-primary">Post petition</button>
          </form>
          {d.recent_ipos.length > 0 && (
            <div className="card">
              <div className="card-head"><h3>Recent IPOs</h3></div>
              <ul className="feed">
                {d.recent_ipos.map((p) => (
                  <li key={p.id}><a href={`#/p/${p.id}`}>{p.name}</a><span className="num">{money(p.price)}</span></li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      <Toast msg={toast} />
    </>
  );
}

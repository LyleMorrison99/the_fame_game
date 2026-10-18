import { useState } from "react";
import { api, ago, Avatar, int, money, pct, usePoll, useApp, when } from "../lib.jsx";

export default function Player({ username }) {
  const { state } = useApp();
  const [d, setD] = useState(null);
  const [missing, setMissing] = useState(false);
  usePoll(async () => {
    try { setD(await api(`/api/players/${encodeURIComponent(username)}`)); }
    catch (e) { if (e.status === 404) setMissing(true); }
  }, 20000, [username]);
  if (missing) return <div className="empty">No player called {username}.</div>;
  if (!d) return <div className="empty">Loading…</div>;
  const seed = state?.seed || 10000;
  const total = d.holdings.reduce((s, h) => s + h.value, 0) || 1;
  return (
    <>
      <div className="row" style={{ gap: 16, alignItems: "center" }}>
        <Avatar user={d.user} size={72} />
        <div className="stack" style={{ gap: 4 }}>
          <h1>{d.user.username}</h1>
          {d.user.bio && <p className="muted">{d.user.bio}</p>}
          <p className="tiny faint">Joined {when(d.user.joined)}{d.finishes.length ? ` · Best finish: #${Math.min(...d.finishes.map((f) => f.rank))}` : ""}</p>
        </div>
      </div>
      <div className="stats">
        <div className="stat"><span className="label">Net worth</span><span className="num">{money(d.net_worth, 0)}</span></div>
        <div className="stat"><span className="label">Season return</span><span className={"num " + (d.net_worth >= seed ? "up" : "down")}>{pct(d.net_worth / seed - 1)}</span></div>
        <div className="stat"><span className="label">Positions</span><span className="num">{d.holdings.length}</span></div>
      </div>
      <div className="grid-2">
        <div className="card">
          <div className="card-head"><h3>Holdings</h3></div>
          <ul className="feed">
            {d.holdings.map((h) => (
              <li key={h.personality.id}>
                <span style={{ minWidth: 0 }}><a href={`#/p/${h.personality.id}`}>{h.personality.name}</a> <span className="tiny faint">{int(h.shares)} sh</span></span>
                <span className="num">{money(h.value, 0)} <span className="faint">· {((h.value / total) * 100).toFixed(0)}%</span></span>
              </li>
            ))}
            {!d.holdings.length && <li className="faint">All cash right now.</li>}
          </ul>
        </div>
        <div className="card">
          <div className="card-head"><h3>Recent trades</h3></div>
          <ul className="feed">
            {d.recent.map((f, i) => (
              <li key={i}>
                <span><span className={f.side === "sell" ? "down" : "up"}>{f.side === "sell" ? "Sold" : f.side === "ipo" ? "IPO" : "Bought"}</span> {int(f.shares)} <a href={`#/p/${f.pid}`}>{f.personality}</a></span>
                <span className="num faint">{money(f.price)} · {ago(f.ts)}</span>
              </li>
            ))}
            {!d.recent.length && <li className="faint">No trades yet.</li>}
          </ul>
        </div>
      </div>
    </>
  );
}

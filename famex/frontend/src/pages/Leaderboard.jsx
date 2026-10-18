import { useState } from "react";
import { api, Avatar, go, int, money, pct, usePoll, useApp, when } from "../lib.jsx";

export default function Leaderboard() {
  const { me, state } = useApp();
  const [d, setD] = useState(null);
  const [hof, setHof] = useState([]);
  usePoll(async () => {
    try {
      const [l, h] = await Promise.all([api("/api/leaderboard"), api("/api/hall-of-fame")]);
      setD(l); setHof(h.seasons);
    } catch { /* keep last */ }
  }, 20000);
  if (!d) return <div className="empty">Loading…</div>;
  const seed = d.seed;
  return (
    <>
      <div className="page-head">
        <div>
          <span className="label">Season {state?.season?.number}</span>
          <h1>Leaderboard</h1>
          {state?.season && <p className="muted">Season ends {when(state.season.ends_at)}. Highest net worth wins.</p>}
        </div>
      </div>
      <div className="card table-wrap">
        <table className="t">
          <thead><tr><th style={{ width: 50 }}>#</th><th>Player</th><th className="r">Net worth</th><th className="r">Return</th><th className="r hide-sm">Cash</th><th className="r hide-sm">Positions</th></tr></thead>
          <tbody>
            {d.players.map((r) => (
              <tr key={r.user.id} className="clickable" onClick={() => go(`u/${encodeURIComponent(r.user.username)}`)}
                style={r.user.id === me.id ? { background: "var(--flash-soft)" } : undefined}>
                <td className="num" style={{ fontWeight: 700, color: r.rank <= 3 ? "var(--flash)" : "var(--ink-3)" }}>{r.rank}</td>
                <td>
                  <div className="name-cell">
                    <Avatar user={r.user} size={34} />
                    <div style={{ minWidth: 0 }}>
                      <strong>{r.user.username}</strong>{r.user.id === me.id && <span className="tiny faint"> (you)</span>}
                      {r.user.bio && <div className="tiny faint" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 260 }}>{r.user.bio}</div>}
                    </div>
                  </div>
                </td>
                <td className="r num">{money(r.net_worth, 0)}</td>
                <td className={"r num " + (r.net_worth >= seed ? "up" : "down")}>{pct(r.net_worth / seed - 1)}</td>
                <td className="r num hide-sm">{money(r.cash, 0)}</td>
                <td className="r num hide-sm">{int(r.positions)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hof.length > 0 && (
        <div className="stack">
          <h2>Hall of Fame</h2>
          <div className="stats">
            {hof.map((s) => (
              <div key={s.season} className="card card-pad stack" style={{ gap: 8 }}>
                <span className="label">Season {s.season}</span>
                {s.standings.slice(0, 3).map((r) => (
                  <div key={r.rank} className="spread small">
                    <span><strong className="num" style={{ color: "var(--flash)" }}>{r.rank}</strong> {r.username}</span>
                    <span className="num">{money(r.net_worth, 0)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

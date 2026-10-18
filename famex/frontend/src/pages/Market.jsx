import { useMemo, useState } from "react";
import { api, ago, Change, compact, go, int, money, Monogram, Sparkline, StatusChips, usePoll, useApp } from "../lib.jsx";

const SORTS = {
  movers: ["Biggest movers", (a, b) => Math.abs(b.change_24h) - Math.abs(a.change_24h)],
  gainers: ["Top gainers", (a, b) => b.change_24h - a.change_24h],
  losers: ["Top losers", (a, b) => a.change_24h - b.change_24h],
  cap: ["Market cap", (a, b) => b.market_cap - a.market_cap],
  price: ["Price", (a, b) => b.price - a.price],
  volume: ["24h volume", (a, b) => b.volume_24h - a.volume_24h],
  name: ["A–Z", (a, b) => a.name.localeCompare(b.name)],
};

export default function Market() {
  const { state } = useApp();
  const [data, setData] = useState(null);
  const [feed, setFeed] = useState([]);
  const [cat, setCat] = useState("All");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("cap");

  usePoll(async () => {
    try {
      const [m, f] = await Promise.all([api("/api/market"), api("/api/feed")]);
      setData(m.personalities);
      setFeed(f.items);
    } catch { /* keep last */ }
  }, 15000);

  const rows = useMemo(() => {
    if (!data) return [];
    const ql = q.trim().toLowerCase();
    return data
      .filter((p) => p.status === "live")
      .filter((p) => cat === "All" || p.category === cat)
      .filter((p) => !ql || p.name.toLowerCase().includes(ql))
      .sort(SORTS[sort][1]);
  }, [data, cat, q, sort]);

  const ipos = (data || []).filter((p) => p.status === "ipo");
  const totalCap = (data || []).reduce((s, p) => s + p.market_cap, 0);
  const cats = ["All", ...(state?.categories || [])];

  return (
    <>
      <div className="page-head">
        <div>
          <span className="label">Season {state?.season?.number ?? "—"}</span>
          <h1>The Market</h1>
          <p className="muted">{data ? `${rows.length} Personalities · ${compact(totalCap)} total market cap` : "Loading prices…"}</p>
        </div>
        <input className="input" style={{ maxWidth: 260 }} placeholder="Search Personalities" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
      </div>

      {ipos.map((p) => (
        <a key={p.id} href={`#/p/${p.id}`} className="card card-pad ipo-card spread" style={{ textDecoration: "none" }}>
          <div className="row">
            <Monogram name={p.name} size={40} />
            <div>
              <span className="label" style={{ color: "var(--gold)" }}>IPO window open</span>
              <h2>{p.name}</h2>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="num" style={{ fontSize: "1.2rem", fontWeight: 600 }}>{money(p.ipo?.est_price)}</div>
            <div className="small muted">est. IPO price · {p.ipo?.backers ?? 0} in</div>
          </div>
        </a>
      ))}

      <div className="spread" style={{ flexWrap: "wrap" }}>
        <div className="chips">
          {cats.map((c) => <button key={c} className={"chip" + (c === cat ? " on" : "")} onClick={() => setCat(c)}>{c}</button>)}
        </div>
        <select className="input" style={{ width: "auto" }} value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          {Object.entries(SORTS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </div>

      <div className="grid-2">
        <div className="card table-wrap">
          <table className="t">
            <thead>
              <tr>
                <th>Personality</th>
                <th className="hide-sm">24h</th>
                <th className="r">Price</th>
                <th className="r">24h</th>
                <th className="r hide-sm">Holders</th>
                <th className="r hide-sm">Owned</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="clickable" onClick={() => go(`p/${p.id}`)}>
                  <td>
                    <div className="name-cell">
                      <Monogram name={p.name} />
                      <div style={{ minWidth: 0 }}>
                        <a href={`#/p/${p.id}`} style={{ textDecoration: "none" }}><strong>{p.name}</strong></a>
                        <div className="tiny faint row" style={{ gap: 6 }}>{p.category} <StatusChips p={p} /></div>
                      </div>
                    </div>
                  </td>
                  <td className="hide-sm"><Sparkline points={p.spark} /></td>
                  <td className="r num">{money(p.price)}</td>
                  <td className="r"><Change v={p.change_24h} /></td>
                  <td className="r num hide-sm">{int(p.holders)}</td>
                  <td className="r num hide-sm faint">{((p.sold / p.supply) * 100).toFixed(1)}%</td>
                </tr>
              ))}
              {data && !rows.length && <tr><td colSpan="6" className="empty">No Personalities match that search.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="card-head"><h3>Latest fills</h3><span className="tiny faint">clears every 30s</span></div>
          <ul className="feed">
            {feed.slice(0, 18).map((f, i) => (
              <li key={i}>
                <span style={{ minWidth: 0 }}>
                  <a href={`#/u/${encodeURIComponent(f.user)}`}>{f.user}</a>{" "}
                  <span className={f.side === "sell" ? "down" : "up"}>{f.side === "sell" ? "sold" : f.side === "ipo" ? "got IPO" : "bought"}</span>{" "}
                  {int(f.shares)} <a href={`#/p/${f.pid}`}>{f.personality}</a>
                </span>
                <span className="num faint" style={{ whiteSpace: "nowrap" }}>{money(f.price)} · {ago(f.ts)}</span>
              </li>
            ))}
            {!feed.length && <li className="faint">No trades yet. Be the first.</li>}
          </ul>
        </div>
      </div>
    </>
  );
}

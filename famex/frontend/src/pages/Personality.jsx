import { useEffect, useMemo, useRef, useState } from "react";
import {
  api, ago, Avatar, Change, ErrorNote, int, money, Monogram, quote, sharesForDollars, StatusChips,
  Toast, until, useApp, useNow, usePoll, useToast, when,
} from "../lib.jsx";

const RANGES = { "1D": 1, "1W": 7, Season: 400 };

function PriceChart({ history, days }) {
  const pts = useMemo(() => {
    const cutoff = Date.now() - days * 86400e3;
    const all = (history || []).map((h) => ({ t: new Date(h.t).getTime(), p: h.p }));
    let sel = all.filter((h) => h.t >= cutoff);
    const before = all.filter((h) => h.t < cutoff).pop();
    if (before) sel = [{ t: cutoff, p: before.p }, ...sel];
    if (sel.length) sel.push({ t: Date.now(), p: sel[sel.length - 1].p });
    return sel;
  }, [history, days]);
  const box = useRef(null);
  const [W, setW] = useState(640);
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, [pts.length < 2]);
  const H = W < 480 ? 180 : 220, padR = 52, padB = 22, padT = 10;
  if (pts.length < 2) return <div className="empty" ref={box}>Price history appears after the first trades.</div>;
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
  let lo = Math.min(...pts.map((p) => p.p)), hi = Math.max(...pts.map((p) => p.p));
  if (hi - lo < 0.5) { hi += 0.25; lo -= 0.25; }
  const x = (t) => ((t - t0) / (t1 - t0 || 1)) * (W - padR);
  const y = (p) => padT + (1 - (p - lo) / (hi - lo)) * (H - padT - padB);
  // step line: price holds until the next clearing
  let d = `M${x(pts[0].t)} ${y(pts[0].p)}`;
  for (let i = 1; i < pts.length; i++) d += ` H${x(pts[i].t).toFixed(1)} V${y(pts[i].p).toFixed(1)}`;
  const up = pts[pts.length - 1].p >= pts[0].p;
  const color = up ? "var(--up)" : "var(--down)";
  const area = d + ` V${H - padB} H0 Z`;
  const ticks = [hi, (hi + lo) / 2, lo];
  const fmtT = (t) => new Date(t).toLocaleString("en-US", days <= 1 ? { hour: "numeric", minute: "2-digit" } : { month: "short", day: "numeric" });
  const last = pts[pts.length - 1];
  return (
    <div className="chart-box" ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Price history">
        <defs>
          <linearGradient id="fade" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={up ? "#0f8a57" : "#cc3340"} stopOpacity="0.22" />
            <stop offset="100%" stopColor={up ? "#0f8a57" : "#cc3340"} stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((v, i) => (
          <g key={i}>
            <line x1="0" x2={W - padR} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeDasharray={i === 1 ? "3 4" : ""} />
            <text x={W - padR + 6} y={y(v) + 4} fontSize="11" fill="var(--ink-3)" fontFamily="var(--mono)">${v.toFixed(2)}</text>
          </g>
        ))}
        <path d={area} fill="url(#fade)" />
        <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
        <circle cx={x(last.t)} cy={y(last.p)} r="4" fill={color} stroke="var(--surface)" strokeWidth="2" />
        <text x="0" y={H - 4} fontSize="11" fill="var(--ink-3)">{fmtT(t0)}</text>
        <text x={W - padR} y={H - 4} fontSize="11" fill="var(--ink-3)" textAnchor="end">now</text>
      </svg>
    </div>
  );
}

function TradePanel({ p, mine, orders, reload }) {
  const { me, refreshMe } = useApp();
  const [side, setSide] = useState("buy");
  const [shares, setShares] = useState("");
  const [limit, setLimit] = useState("");
  const [showLimit, setShowLimit] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, showToast] = useToast();
  const n = parseInt(shares, 10) || 0;
  const qt = quote(p, side, n);
  const available = (mine?.shares || 0) - (mine?.locked || 0);
  const defaultLimit = qt ? (side === "buy" ? qt.avg * 1.1 : qt.avg * 0.9) : null;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/api/orders", { method: "POST", body: { personality_id: p.id, side, shares: n, limit_price: limit ? parseFloat(limit) : null } });
      setShares(""); setLimit("");
      showToast(`Order placed. It clears at the next tick.`);
      reload(); refreshMe();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  const cancel = async (id) => {
    try { await api(`/api/orders/${id}`, { method: "DELETE" }); reload(); refreshMe(); showToast("Order cancelled."); }
    catch (err) { setError(err.message); }
  };

  return (
    <form className="card card-pad stack" onSubmit={submit}>
      <div className="spread">
        <h3>Trade</h3>
        <div className="seg" role="tablist">
          <button type="button" className={"buy" + (side === "buy" ? " on" : "")} onClick={() => setSide("buy")}>Buy</button>
          <button type="button" className={"sell" + (side === "sell" ? " on" : "")} onClick={() => setSide("sell")}>Sell</button>
        </div>
      </div>
      <label className="field">
        <span>Shares</span>
        <input id="shares" className="input num" inputMode="numeric" value={shares} onChange={(e) => setShares(e.target.value.replace(/\D/g, ""))} placeholder="0" />
      </label>
      <div className="row" style={{ gap: 6 }}>
        {side === "buy"
          ? [100, 250, 500, 1000].map((d) => (
            <button type="button" key={d} className="btn btn-sm" onClick={() => setShares(String(sharesForDollars(p, d) || 1))}>${d}</button>))
          : [0.25, 0.5, 1].map((f) => (
            <button type="button" key={f} className="btn btn-sm" disabled={!available} onClick={() => setShares(String(Math.max(1, Math.floor(available * f))))}>{f === 1 ? "All" : `${f * 100}%`}</button>))}
        <span className="tiny faint" style={{ marginLeft: "auto" }}>
          {side === "buy" ? `${money(me.cash)} cash` : `${int(available)} available`}
        </span>
      </div>
      {qt && (
        <dl className="kv">
          <dt>Est. price per share</dt><dd>{money(qt.avg)}</dd>
          <dt>Est. {side === "buy" ? "cost" : "proceeds"}</dt><dd>{money(qt.total)}</dd>
          <dt>Price after</dt><dd>{money(qt.after)}</dd>
          {side === "buy" && qt.shares < n && <><dt className="down">Shares left to buy</dt><dd className="down">{int(qt.shares)}</dd></>}
        </dl>
      )}
      {showLimit ? (
        <label className="field">
          <span>{side === "buy" ? "Max price per share" : "Min price per share"}</span>
          <input id="limit" className="input num" inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder={defaultLimit ? defaultLimit.toFixed(2) : ""} />
          <span className="hint">If the batch clears outside this price, your order waits for a later batch (up to 24 hours).</span>
        </label>
      ) : (
        <button type="button" className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start", padding: 0 }} onClick={() => setShowLimit(true)}>
          Set a price limit {defaultLimit ? `(default ${money(defaultLimit)})` : ""}
        </button>
      )}
      <ErrorNote error={error} />
      <button className={"btn btn-block " + (side === "buy" ? "btn-buy" : "btn-sell")} disabled={busy || !n || (side === "buy" && p.sold_out)}>
        {p.sold_out && side === "buy" ? "Sold out" : `${side === "buy" ? "Buy" : "Sell"} ${n ? int(n) + " " : ""}shares`}
      </button>
      <div className="batch-banner">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
        Everyone in the same 30-second batch gets the same price.
      </div>
      {orders.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <span className="label">Your open orders</span>
          {orders.map((o) => (
            <div key={o.id} className="spread small">
              <span><span className={o.side === "buy" ? "up" : "down"}>{o.side === "buy" ? "Buy" : "Sell"}</span> {int(o.shares)} · limit {money(o.limit_price)}</span>
              <button type="button" className="btn btn-sm" onClick={() => cancel(o.id)}>Cancel</button>
            </div>
          ))}
        </div>
      )}
      <Toast msg={toast} />
    </form>
  );
}

function IpoPanel({ p, mine, orders, reload }) {
  const { me, state, refreshMe } = useApp();
  const now = useNow();
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [toast, showToast] = useToast();
  const cap = state?.ipo_cap ?? 1000;
  const committed = mine?.ipo_committed || 0;
  const room = Math.max(0, cap - committed);

  if (p.status === "queued") {
    return (
      <div className="card card-pad stack ipo-card">
        <span className="label" style={{ color: "var(--gold)" }}>IPO scheduled</span>
        <h3>Opens in {until(p.ipo_opens_at, now)}</h3>
        <p className="small muted">{when(p.ipo_opens_at)} – {when(p.ipo_closes_at)}. Commit up to {money(cap, 0)} during the window. Everyone gets the same IPO price.</p>
      </div>
    );
  }
  const commit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/ipo/commit", { method: "POST", body: { personality_id: p.id, dollars: parseFloat(amount) } });
      setAmount(""); showToast("You're in. Shares are allocated when the window closes."); reload(); refreshMe();
    } catch (err) { setError(err.message); }
  };
  const cancel = async (id) => {
    try { await api(`/api/orders/${id}`, { method: "DELETE" }); reload(); refreshMe(); } catch (err) { setError(err.message); }
  };
  return (
    <form className="card card-pad stack ipo-card" onSubmit={commit}>
      <div className="spread">
        <span className="label" style={{ color: "var(--gold)" }}>IPO window open</span>
        <span className="small num">closes in {until(p.ipo_closes_at, now)}</span>
      </div>
      <dl className="kv">
        <dt>Committed so far</dt><dd>{money(p.ipo?.committed)}</dd>
        <dt>Players in</dt><dd>{p.ipo?.backers}</dd>
        <dt>Est. IPO price</dt><dd>{money(p.ipo?.est_price)}</dd>
        <dt>Est. opening price</dt><dd className="up">{money(p.ipo?.est_open)}</dd>
      </dl>
      <p className="small muted">Commit dollars now. When the window closes everyone pays one IPO price, and trading opens higher, at the curve price.</p>
      <label className="field">
        <span>Amount to commit</span>
        <input id="ipo-amount" className="input num" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={`up to ${money(Math.min(room, me.cash), 0)}`} />
      </label>
      <div className="row" style={{ gap: 6 }}>
        {[250, 500, cap].map((d) => <button type="button" key={d} className="btn btn-sm" disabled={d > room} onClick={() => setAmount(String(Math.min(d, room)))}>{d === cap ? "Max" : `$${d}`}</button>)}
        <span className="tiny faint" style={{ marginLeft: "auto" }}>{money(room, 0)} of {money(cap, 0)} cap left</span>
      </div>
      <ErrorNote error={error} />
      <button className="btn btn-primary btn-block" disabled={!parseFloat(amount)}>Commit to IPO</button>
      {orders.map((o) => (
        <div key={o.id} className="spread small">
          <span>Committed {money(o.amount)}</span>
          <button type="button" className="btn btn-sm" onClick={() => cancel(o.id)}>Withdraw</button>
        </div>
      ))}
      <Toast msg={toast} />
    </form>
  );
}

export default function Personality({ id }) {
  const [p, setP] = useState(null);
  const [orders, setOrders] = useState([]);
  const [range, setRange] = useState("1D");
  const [missing, setMissing] = useState(false);
  const load = async () => {
    try {
      const [d, port] = await Promise.all([api(`/api/personalities/${id}`), api("/api/portfolio").catch(() => null)]);
      setP(d);
      setOrders((port?.orders || []).filter((o) => o.personality.id === d.id && o.status === "open"));
    } catch (e) { if (e.status === 404) setMissing(true); }
  };
  usePoll(load, 15000, [id]);
  if (missing) return <div className="empty">That Personality isn't on the exchange.</div>;
  if (!p) return <div className="empty">Loading…</div>;

  const mine = p.mine;
  const pnl = mine && mine.shares ? mine.value - mine.cost : null;
  const tradeOrders = orders.filter((o) => o.side !== "ipo");
  const ipoOrders = orders.filter((o) => o.side === "ipo");

  return (
    <>
      <div className="hero">
        <div className="row" style={{ gap: 14, alignItems: "center" }}>
          <Monogram name={p.name} size={56} />
          <div>
            <div className="row" style={{ gap: 8 }}><span className="label">{p.category}</span><StatusChips p={p} /></div>
            <h1>{p.name}</h1>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="price-big">{money(p.price)}</div>
          {p.status === "live" && <div className="small" style={{ marginTop: 6 }}><Change v={p.change_24h} /> <span className="faint">today</span> · <Change v={p.change_7d} /> <span className="faint">7d</span></div>}
          {p.status !== "live" && <div className="small faint">IPO base price</div>}
        </div>
      </div>

      <div className="grid-2">
        <div className="stack">
          {p.status === "live" && (
            <div className="card card-pad stack">
              <div className="spread">
                <h3>Price</h3>
                <div className="seg">{Object.keys(RANGES).map((r) => <button key={r} className={r === range ? "on" : ""} onClick={() => setRange(r)}>{r}</button>)}</div>
              </div>
              <PriceChart history={p.history} days={RANGES[range]} />
            </div>
          )}

          <div className="stats stats-3">
            <div className="stat"><span className="label">Market cap</span><span className="num">{money(p.market_cap, 0)}</span></div>
            <div className="stat"><span className="label">Shares held</span><span className="num">{int(p.sold)}</span></div>
            <div className="stat"><span className="label">Holders</span><span className="num">{int(p.holders)}</span></div>
          </div>

          <div className="card card-pad stack">
            <div className="spread"><h3>Supply</h3><span className="small num faint">{int(p.sold)} / {int(p.supply)} shares</span></div>
            <div className="curve-meter"><div style={{ width: `${Math.min(100, (p.sold / p.supply) * 100)}%` }} /></div>
            <p className="small muted">
              Every share bought pushes the price up {money(p.k, 4)}; every share sold pulls it down the same.
              {p.sold_out ? " This Personality is sold out. New buys wait until someone sells." : ` Sells out at ${money(p.p0 + p.k * p.supply)}.`}
            </p>
          </div>

          <div className="card">
            <div className="card-head"><h3>Top holders</h3></div>
            <ul className="feed">
              {p.top_holders.map((h) => (
                <li key={h.user.id}>
                  <a href={`#/u/${encodeURIComponent(h.user.username)}`} className="row" style={{ gap: 8, textDecoration: "none" }}>
                    <Avatar user={h.user} size={24} /> {h.user.username}
                  </a>
                  <span className="num">{int(h.shares)} <span className="faint">· {(h.pct * 100).toFixed(1)}%</span></span>
                </li>
              ))}
              {!p.top_holders.length && <li className="faint">Nobody owns {p.name} yet.</li>}
            </ul>
          </div>
        </div>

        <div className="stack trade-col">
          {p.status === "live" ? <TradePanel p={p} mine={mine} orders={tradeOrders} reload={load} /> : <IpoPanel p={p} mine={mine} orders={ipoOrders} reload={load} />}
          {mine && mine.shares > 0 && (
            <div className="card card-pad stack">
              <h3>Your position</h3>
              <dl className="kv">
                <dt>Shares</dt><dd>{int(mine.shares)}</dd>
                <dt>Cost basis</dt><dd>{money(mine.cost)}</dd>
                <dt>Cash-out value</dt><dd>{money(mine.value)}</dd>
                <dt>Profit / loss</dt><dd className={pnl >= 0 ? "up" : "down"}>{money(pnl)}</dd>
              </dl>
              <p className="tiny faint">Cash-out value is what selling all of it at once would bring in, after your own sale moves the price.</p>
            </div>
          )}
          <div className="card">
            <div className="card-head"><h3>Recent trades</h3></div>
            <ul className="feed">
              {p.recent.map((f, i) => (
                <li key={i}>
                  <span><a href={`#/u/${encodeURIComponent(f.user)}`}>{f.user}</a> <span className={f.side === "sell" ? "down" : "up"}>{f.side === "sell" ? "sold" : f.side === "ipo" ? "IPO" : "bought"}</span> {int(f.shares)}</span>
                  <span className="num faint">{money(f.price)} · {ago(f.ts)}</span>
                </li>
              ))}
              {!p.recent.length && <li className="faint">No trades yet.</li>}
            </ul>
          </div>
        </div>
      </div>
    </>
  );
}

import { useState } from "react";
import { api, ago, ErrorNote, go, int, money, Monogram, pct, usePoll, useApp } from "../lib.jsx";

const STATUS = {
  open: ["Waiting for next batch", "chip-flash"], filled: ["Filled", "chip-up"], partial: ["Partly filled", "chip-gold"],
  soldout: ["Sold out", "chip"], cancelled: ["Cancelled", "chip"], expired: ["Expired", "chip"],
};

export default function Portfolio() {
  const { refreshMe, state } = useApp();
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const load = async () => { try { setD(await api("/api/portfolio")); } catch (e) { setError(e.message); } };
  usePoll(load, 15000);
  if (!d) return <div className="empty">{error || "Loading…"}</div>;
  const { me, holdings, orders } = d;
  const seed = state?.seed || 10000;
  const totalCost = holdings.reduce((s, h) => s + h.cost, 0);
  const totalValue = holdings.reduce((s, h) => s + h.value, 0);
  const open = orders.filter((o) => o.status === "open");
  const closed = orders.filter((o) => o.status !== "open").slice(0, 25);

  const cancel = async (id) => {
    try { await api(`/api/orders/${id}`, { method: "DELETE" }); load(); refreshMe(); } catch (e) { setError(e.message); }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <span className="label">Your portfolio</span>
          <h1 className="num" style={{ fontFamily: "var(--mono)" }}>{money(me.net_worth)}</h1>
          <p className={me.net_worth >= seed ? "up" : "down"}>{pct(me.net_worth / seed - 1)} since the season started with {money(seed, 0)}</p>
        </div>
      </div>
      <div className="stats">
        <div className="stat"><span className="label">Cash</span><span className="num">{money(me.cash)}</span></div>
        <div className="stat"><span className="label">Set aside in orders</span><span className="num">{money(me.reserved)}</span></div>
        <div className="stat"><span className="label">Holdings value</span><span className="num">{money(totalValue)}</span></div>
        <div className="stat"><span className="label">Unrealized P/L</span><span className={"num " + (totalValue - totalCost >= 0 ? "up" : "down")}>{money(totalValue - totalCost)}</span></div>
      </div>
      <ErrorNote error={error} />

      {open.length > 0 && (
        <div className="card table-wrap">
          <div className="card-head"><h3>Open orders</h3><span className="tiny faint">Clear at the next tick</span></div>
          <table className="t">
            <thead><tr><th>Personality</th><th>Order</th><th className="r">Limit / amount</th><th className="r hide-sm">Placed</th><th></th></tr></thead>
            <tbody>
              {open.map((o) => (
                <tr key={o.id}>
                  <td><a href={`#/p/${o.personality.id}`}>{o.personality.name}</a></td>
                  <td><span className={o.side === "sell" ? "down" : "up"}>{o.side === "ipo" ? "IPO" : o.side === "buy" ? "Buy" : "Sell"}</span> {o.side !== "ipo" && int(o.shares)}</td>
                  <td className="r num">{o.side === "ipo" ? money(o.amount) : money(o.limit_price)}</td>
                  <td className="r hide-sm faint">{ago(o.created_at)}</td>
                  <td className="r"><button className="btn btn-sm" onClick={() => cancel(o.id)}>{o.side === "ipo" ? "Withdraw" : "Cancel"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card table-wrap">
        <div className="card-head"><h3>Holdings</h3><span className="tiny faint">Valued at what selling each position would bring in</span></div>
        <table className="t">
          <thead><tr><th>Personality</th><th className="r">Shares</th><th className="r hide-sm">Price</th><th className="r">Value</th><th className="r">P/L</th></tr></thead>
          <tbody>
            {holdings.map((h) => {
              const pl = h.value - h.cost;
              return (
                <tr key={h.personality.id} className="clickable" onClick={() => go(`p/${h.personality.id}`)}>
                  <td><div className="name-cell"><Monogram name={h.personality.name} size={30} /><strong>{h.personality.name}</strong></div></td>
                  <td className="r num">{int(h.shares)}{h.locked ? <div className="tiny faint">{int(h.locked)} in orders</div> : null}</td>
                  <td className="r num hide-sm">{money(h.personality.price)}</td>
                  <td className="r num">{money(h.value)}</td>
                  <td className={"r num " + (pl >= 0 ? "up" : "down")}>{money(pl)}<div className="tiny">{h.cost ? pct(pl / h.cost) : ""}</div></td>
                </tr>
              );
            })}
            {!holdings.length && <tr><td colSpan="5" className="empty">No positions yet. <a href="#/market">Browse the market</a> to buy your first shares.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="card table-wrap">
        <div className="card-head"><h3>Order history</h3></div>
        <table className="t">
          <thead><tr><th>Personality</th><th>Order</th><th className="r">Filled</th><th className="r hide-sm">When</th><th className="r">Status</th></tr></thead>
          <tbody>
            {closed.map((o) => (
              <tr key={o.id}>
                <td><a href={`#/p/${o.personality.id}`}>{o.personality.name}</a></td>
                <td><span className={o.side === "sell" ? "down" : "up"}>{o.side === "ipo" ? "IPO" : o.side === "buy" ? "Buy" : "Sell"}</span> {o.side !== "ipo" && int(o.shares)}</td>
                <td className="r num">{o.filled_shares ? `${int(o.filled_shares)} @ ${money(o.fill_price)}` : "—"}</td>
                <td className="r hide-sm faint">{o.closed_at ? ago(o.closed_at) : ""}</td>
                <td className="r"><span className={"chip " + (STATUS[o.status]?.[1] || "")}>{STATUS[o.status]?.[0] || o.status}</span></td>
              </tr>
            ))}
            {!closed.length && <tr><td colSpan="5" className="empty">Filled orders show up here.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

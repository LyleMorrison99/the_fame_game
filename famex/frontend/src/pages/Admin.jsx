import { useState } from "react";
import { api, ago, Avatar, ErrorNote, money, Toast, until, useNow, usePoll, useToast, useApp, when, pct } from "../lib.jsx";

const TABS = [["requests", "Join requests"], ["passphrases", "Passphrases"], ["ipos", "IPO queue"],
  ["players", "Players"], ["house", "House players"], ["season", "Season"]];

const toLocalInput = (iso) => {
  const d = new Date(iso);
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
};
const fromLocalInput = (v) => (v ? new Date(v).toISOString() : null);

async function copy(text, show) {
  try { await navigator.clipboard.writeText(text); show("Copied."); } catch { show("Select the text to copy it."); }
}

function Requests({ o, reload, show }) {
  const [warn, setWarn] = useState(null);
  const [error, setError] = useState("");
  const act = async (u, action, force = false) => {
    setError("");
    try {
      if (action === "approve") await api(`/api/admin/users/${u.id}/approve`, { method: "POST", body: { force } });
      else await api(`/api/admin/users/${u.id}/${action}`, { method: "POST" });
      setWarn(null); show(action === "approve" ? `${u.username} approved.` : action === "defer" ? `${u.username} starts next season.` : `${u.username} declined.`);
      reload();
    } catch (e) {
      if (e.status === 409) setWarn({ user: u, msg: e.message }); else setError(e.message);
    }
  };
  const g = o.growth;
  return (
    <div className="stack">
      <div className="stats">
        <div className="stat"><span className="label">Traders now</span><span className="num">{g.traders}</span></div>
        <div className="stat"><span className="label">Season baseline</span><span className="num">{g.baseline}</span></div>
        <div className="stat"><span className="label">Growth</span><span className={"num " + (g.growth > g.limit ? "down" : "")}>{pct(g.growth)}</span></div>
      </div>
      <p className="small muted">Mid-season joins add money and push prices up. Past {Math.round(g.limit * 100)}% growth you'll be asked to confirm or defer the player to next season.</p>
      {warn && (
        <div className="notice notice-warn stack" style={{ gap: 10 }}>
          <span>{warn.msg}</span>
          <div className="row">
            <button className="btn btn-sm" onClick={() => act(warn.user, "approve", true)}>Approve anyway</button>
            <button className="btn btn-sm" onClick={() => act(warn.user, "defer")}>Defer to next season</button>
            <button className="btn btn-sm btn-ghost" onClick={() => setWarn(null)}>Never mind</button>
          </div>
        </div>
      )}
      <ErrorNote error={error} />
      <div className="card">
        {o.pending.map((u) => (
          <div key={u.id} className="petition" style={{ gridTemplateColumns: "40px minmax(0,1fr) auto" }}>
            <Avatar user={u} size={36} />
            <div style={{ minWidth: 0 }}>
              <strong>{u.username}</strong> {u.status === "deferred" && <span className="chip chip-gold">Next season</span>}
              <div className="tiny faint">{u.email} · signed up {ago(u.created_at)}</div>
              {u.bio && <div className="small muted">{u.bio}</div>}
            </div>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn btn-sm btn-buy" onClick={() => act(u, "approve")}>Approve</button>
              {u.status !== "deferred" && <button className="btn btn-sm" onClick={() => act(u, "defer")}>Defer</button>}
              <button className="btn btn-sm" onClick={() => act(u, "deny")}>Decline</button>
            </div>
          </div>
        ))}
        {!o.pending.length && <div className="empty">No one is waiting.</div>}
      </div>
    </div>
  );
}

function Passphrases({ o, reload, show }) {
  const [count, setCount] = useState(1);
  const [note, setNote] = useState("");
  const [fresh, setFresh] = useState([]);
  const [error, setError] = useState("");
  const make = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const r = await api("/api/admin/invites", { method: "POST", body: { count: Number(count), note } });
      setFresh(r.codes); setNote(""); reload();
    } catch (err) { setError(err.message); }
  };
  const del = async (id) => { await api(`/api/admin/invites/${id}`, { method: "DELETE" }); reload(); };
  const link = window.location.origin + "/#/signup";
  return (
    <div className="stack">
      <form className="card card-pad stack" onSubmit={make}>
        <h3>Make passphrases</h3>
        <p className="small muted">Each passphrase works once. Send one to each friend along with the signup link: <span className="code">{link}</span></p>
        <div className="row">
          <label className="field" style={{ width: 90 }}><span>How many</span><input id="inv-count" className="input num" type="number" min="1" max="50" value={count} onChange={(e) => setCount(e.target.value)} /></label>
          <label className="field" style={{ flex: 1, minWidth: 180 }}><span>Note (who it's for)</span><input id="inv-note" className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Mike from work" /></label>
        </div>
        <ErrorNote error={error} />
        <button className="btn btn-primary" style={{ alignSelf: "flex-start" }}>Generate</button>
        {fresh.length > 0 && (
          <div className="notice notice-ok stack" style={{ gap: 6 }}>
            {fresh.map((c) => <div key={c} className="spread"><span className="code">{c}</span><button type="button" className="btn btn-sm" onClick={() => copy(`Join me on FameX: ${link}\nYour passphrase: ${c}`, show)}>Copy invite</button></div>)}
          </div>
        )}
      </form>
      <div className="card table-wrap">
        <table className="t">
          <thead><tr><th>Passphrase</th><th>Note</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {o.invites.map((i) => (
              <tr key={i.id}>
                <td><span className="code">{i.code}</span></td>
                <td className="small">{i.note || <span className="faint">—</span>}</td>
                <td className="small">{i.used_by ? <>Used by <strong>{i.used_by}</strong></> : <span className="chip chip-flash">Unused</span>}</td>
                <td className="r">{!i.used_by && <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                  <button className="btn btn-sm" onClick={() => copy(`Join me on FameX: ${link}\nYour passphrase: ${i.code}`, show)}>Copy</button>
                  <button className="btn btn-sm" onClick={() => del(i.id)}>Delete</button></div>}</td>
              </tr>
            ))}
            {!o.invites.length && <tr><td colSpan="4" className="empty">No passphrases yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IpoQueue({ o, show }) {
  const { state } = useApp();
  const now = useNow();
  const [d, setD] = useState(null);
  const [opens, setOpens] = useState(toLocalInput(o.default_ipo_window[0]));
  const [closes, setCloses] = useState(toLocalInput(o.default_ipo_window[1]));
  const [direct, setDirect] = useState({ name: "", category: "" });
  const [error, setError] = useState("");
  usePoll(async () => { try { setD(await api("/api/petitions")); } catch { /* keep */ } }, 15000);
  if (!d) return <div className="empty">Loading…</div>;
  const windowBody = { opens_at: fromLocalInput(opens), closes_at: fromLocalInput(closes) };
  const run = async (fn, msg) => { setError(""); try { setD(await fn()); show(msg); } catch (e) { setError(e.message); } };
  const cats = state?.categories || [];
  return (
    <div className="stack">
      <div className="card card-pad stack">
        <h3>IPO window</h3>
        <p className="small muted">New IPOs use this window. The default is next Monday at 2pm for 24 hours, skipping weeks that already have one.</p>
        <div className="row">
          <label className="field"><span>Opens</span><input id="ipo-open" className="input" type="datetime-local" value={opens} onChange={(e) => setOpens(e.target.value)} /></label>
          <label className="field"><span>Closes</span><input id="ipo-close" className="input" type="datetime-local" value={closes} onChange={(e) => setCloses(e.target.value)} /></label>
        </div>
      </div>
      <ErrorNote error={error} />
      {d.ipos.length > 0 && (
        <div className="card">
          <div className="card-head"><h3>Scheduled</h3></div>
          {d.ipos.map((p) => (
            <div key={p.id} className="petition" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
              <div><strong>{p.name}</strong> <span className={"chip " + (p.status === "ipo" ? "chip-gold" : "")}>{p.status === "ipo" ? "Window open" : `Opens in ${until(p.ipo_opens_at, now)}`}</span>
                <div className="tiny faint">{when(p.ipo_opens_at)} – {when(p.ipo_closes_at)}{p.ipo ? ` · ${money(p.ipo.committed, 0)} committed` : ""}</div></div>
              {p.status === "queued" && <button className="btn btn-sm" onClick={() => run(() => api(`/api/admin/ipos/${p.id}`, { method: "DELETE" }), "IPO cancelled.")}>Cancel</button>}
            </div>
          ))}
        </div>
      )}
      <div className="card">
        <div className="card-head"><h3>Petition board</h3><span className="tiny faint">Highest votes first</span></div>
        {d.open.map((p, i) => (
          <div key={p.id} className="petition">
            <span className="rank">{i + 1}</span>
            <div style={{ minWidth: 0 }}><strong>{p.name}</strong> <span className="tiny faint">{p.category} · {p.votes} votes · by {p.by}</span>
              {p.pitch && <div className="small muted">{p.pitch}</div>}</div>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn btn-sm btn-primary" onClick={() => run(() => api(`/api/admin/petitions/${p.id}/schedule`, { method: "POST", body: windowBody }), `${p.name} IPO scheduled.`)}>Schedule IPO</button>
              <button className="btn btn-sm" onClick={() => run(() => api(`/api/admin/petitions/${p.id}/reject`, { method: "POST" }), "Petition rejected.")}>Reject</button>
            </div>
          </div>
        ))}
        {!d.open.length && <div className="empty">No open petitions.</div>}
      </div>
      <form className="card card-pad stack" onSubmit={(e) => { e.preventDefault(); run(() => api("/api/admin/ipos", { method: "POST", body: { ...direct, category: direct.category || cats[0], ...windowBody } }), "IPO scheduled."); setDirect({ name: "", category: "" }); }}>
        <h3>Schedule an IPO directly</h3>
        <div className="row">
          <label className="field" style={{ flex: 1, minWidth: 180 }}><span>Name</span><input id="direct-name" className="input" value={direct.name} onChange={(e) => setDirect({ ...direct, name: e.target.value })} required /></label>
          <label className="field"><span>Category</span><select id="direct-cat" className="input" value={direct.category || cats[0] || ""} onChange={(e) => setDirect({ ...direct, category: e.target.value })}>{cats.map((c) => <option key={c}>{c}</option>)}</select></label>
        </div>
        <button className="btn" style={{ alignSelf: "flex-start" }}>Schedule</button>
      </form>
    </div>
  );
}

function Players({ o, reload, show }) {
  const { me } = useApp();
  const act = async (u, action) => { await api(`/api/admin/users/${u.id}/${action}`, { method: "POST" }); show("Updated."); reload(); };
  return (
    <div className="card table-wrap">
      <table className="t">
        <thead><tr><th>Player</th><th className="hide-sm">Email</th><th>Role</th><th></th></tr></thead>
        <tbody>
          {o.players.map((u) => (
            <tr key={u.id}>
              <td><div className="name-cell"><Avatar user={u} size={28} /><strong>{u.username}</strong></div></td>
              <td className="small hide-sm">{u.email}</td>
              <td>{u.is_admin ? <span className="chip chip-flash">Admin</span> : <span className="chip">Player</span>}</td>
              <td className="r">{u.id !== me.id && (u.is_admin
                ? <button className="btn btn-sm" onClick={() => act(u, "remove-admin")}>Remove admin</button>
                : <button className="btn btn-sm" onClick={() => act(u, "make-admin")}>Make admin</button>)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STYLE = { momentum: "Chases whatever is rising", contrarian: "Buys dips, sells rebounds", ipo_flipper: "Piles into IPOs, flips the pop",
  index: "Holds a diversified basket", superfan: "Mostly buys one category" };

function House({ o }) {
  return (
    <div className="stack">
      <div className="notice notice-info">Only admins can see this list. To everyone else these five are ordinary players. They trade on prices a few minutes old, keep human hours, and follow the same rules and caps.</div>
      <div className="card table-wrap">
        <table className="t">
          <thead><tr><th>Username</th><th>Style</th><th className="r">Rank</th><th className="r">Net worth</th></tr></thead>
          <tbody>
            {o.bots.map((b) => (
              <tr key={b.username}><td><a href={`#/u/${encodeURIComponent(b.username)}`}>{b.username}</a></td><td className="small">{STYLE[b.strategy] || b.strategy}</td>
                <td className="r num">#{b.rank}</td><td className="r num">{money(b.net_worth, 0)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Season({ o, reload, show }) {
  const [expected, setExpected] = useState(o.season?.expected_traders || 30);
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const end = async (e) => {
    e.preventDefault();
    setError("");
    try { const r = await api("/api/admin/season/end", { method: "POST", body: { expected_traders: Number(expected), confirm } }); show(`Season ${r.season} has started.`); setConfirm(""); reload(); }
    catch (err) { setError(err.message); }
  };
  const s = o.season;
  return (
    <div className="stack">
      {s && (
        <div className="stats">
          <div className="stat"><span className="label">Season</span><span className="num">{s.number}</span></div>
          <div className="stat"><span className="label">Started</span><span className="small">{when(s.starts_at)}</span></div>
          <div className="stat"><span className="label">Scheduled end</span><span className="small">{when(s.ends_at)}</span></div>
          <div className="stat"><span className="label">Market clock</span><span className="small">{o.clock.running ? `Running · last clear ${o.clock.last_tick ? ago(o.clock.last_tick) : "pending"}` : "Stopped"}</span></div>
        </div>
      )}
      <form className="card card-pad stack" onSubmit={end} style={{ maxWidth: 620 }}>
        <h3>End season and start the next</h3>
        <p className="small muted">This records the top 10 in the Hall of Fame, cancels open orders, wipes holdings and price history, resets everyone to the starting bankroll, admits deferred players, and recalibrates every price curve for the expected number of traders.</p>
        <label className="field" style={{ maxWidth: 220 }}><span>Expected traders next season</span><input id="expected" className="input num" type="number" min="5" value={expected} onChange={(e) => setExpected(e.target.value)} />
          <span className="hint">Include the 5 house players.</span></label>
        <label className="field" style={{ maxWidth: 300 }}><span>Type END SEASON to confirm</span><input id="confirm" className="input mono" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label>
        <ErrorNote error={error} />
        <button className="btn btn-sell" style={{ alignSelf: "flex-start" }} disabled={confirm.trim().toUpperCase() !== "END SEASON"}>End season</button>
      </form>
    </div>
  );
}

export default function Admin() {
  const [tab, setTab] = useState("requests");
  const [o, setO] = useState(null);
  const [toast, show] = useToast();
  const load = async () => { try { setO(await api("/api/admin/overview")); } catch { /* keep */ } };
  usePoll(load, 15000);
  if (!o) return <div className="empty">Loading…</div>;
  const props = { o, reload: load, show };
  return (
    <>
      <div className="page-head"><div><span className="label">Commissioner's office</span><h1>Admin</h1></div></div>
      <div className="chips">
        {TABS.map(([k, label]) => (
          <button key={k} className={"chip" + (tab === k ? " on" : "")} onClick={() => setTab(k)}>
            {label}{k === "requests" && o.pending.filter((u) => u.status === "pending").length ? ` (${o.pending.filter((u) => u.status === "pending").length})` : ""}
          </button>
        ))}
      </div>
      {tab === "requests" && <Requests {...props} />}
      {tab === "passphrases" && <Passphrases {...props} />}
      {tab === "ipos" && <IpoQueue {...props} />}
      {tab === "players" && <Players {...props} />}
      {tab === "house" && <House {...props} />}
      {tab === "season" && <Season {...props} />}
      <Toast msg={toast} />
    </>
  );
}

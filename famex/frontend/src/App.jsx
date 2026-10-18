import { useEffect, useRef, useState } from "react";
import { api, AppCtx, Avatar, go, money, pct, dir, useRoute, usePoll } from "./lib.jsx";
import Auth from "./pages/Auth.jsx";
import Market from "./pages/Market.jsx";
import Personality from "./pages/Personality.jsx";
import Portfolio from "./pages/Portfolio.jsx";
import Leaderboard from "./pages/Leaderboard.jsx";
import Ipo from "./pages/Ipo.jsx";
import Player from "./pages/Player.jsx";
import Settings from "./pages/Settings.jsx";
import Admin from "./pages/Admin.jsx";

const ICONS = {
  market: <path d="M4 18l5-6 4 3 7-9" />,
  ipo: <path d="M12 3v12m0-12l-4 4m4-4l4 4M5 21h14" />,
  leaders: <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 01-10 0V4zM7 6H4a3 3 0 003 3M17 6h3a3 3 0 01-3 3" />,
  portfolio: <path d="M4 7h16v12H4zM9 7V5h6v2M4 12h16" />,
  admin: <path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" />,
};
const Icon = ({ name }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
);

function ClearingClock({ offset, tickSeconds }) {
  const [left, setLeft] = useState(tickSeconds);
  const last = useRef(null);
  useEffect(() => {
    const step = () => {
      const now = Date.now() + offset;
      const secs = (now / 1000) % tickSeconds;
      const remain = tickSeconds - secs;
      const tickId = Math.floor(now / 1000 / tickSeconds);
      if (last.current !== null && tickId !== last.current) window.dispatchEvent(new Event("famex:tick"));
      last.current = tickId;
      setLeft(remain);
    };
    step();
    const id = setInterval(step, 250);
    return () => clearInterval(id);
  }, [offset, tickSeconds]);
  const r = 9, c = 2 * Math.PI * r;
  const frac = left / tickSeconds;
  return (
    <div className={"clock" + (left < 5 ? " flash" : "")} title="Every order placed before the clock hits zero clears together at one price.">
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r={r} fill="none" stroke="rgba(255,255,255,.18)" strokeWidth="3" />
        <circle cx="12" cy="12" r={r} fill="none" stroke="#ff5cae" strokeWidth="3" strokeDasharray={c}
          strokeDashoffset={c * (1 - frac)} transform="rotate(-90 12 12)" strokeLinecap="round" />
      </svg>
      <span><span className="clock-text">Clears in </span><span className="num">0:{String(Math.ceil(left) % 60).padStart(2, "0")}</span></span>
    </div>
  );
}

function Ticker({ items }) {
  if (!items.length) return null;
  const row = items.map((p) => (
    <a key={p.id} href={`#/p/${p.id}`}>
      {p.name.toUpperCase()} <span className="num">{money(p.price)}</span>{" "}
      <span className={dir(p.change_24h)}>{pct(p.change_24h)}</span>
    </a>
  ));
  return (
    <div className="ticker" aria-label="Biggest movers">
      <div className="ticker-track">{row}{row}</div>
    </div>
  );
}

export default function App() {
  const route = useRoute();
  const [me, setMe] = useState(undefined);
  const [state, setState] = useState(null);
  const [offset, setOffset] = useState(0);
  const [movers, setMovers] = useState([]);

  const refreshMe = async () => {
    try { const r = await api("/api/me"); setMe(r.user); } catch { setMe(null); }
  };
  useEffect(() => {
    refreshMe();
    api("/api/state").then((s) => {
      setState(s);
      setOffset(new Date(s.server_time).getTime() - Date.now());
      document.title = s.app_name;
    }).catch(() => {});
  }, []);
  usePoll(() => { if (me && me.status === "approved") refreshMe(); }, 20000, [me?.status]);
  usePoll(async () => {
    if (!me) return;
    try {
      const m = await api("/api/market");
      const live = m.personalities.filter((p) => p.status === "live");
      live.sort((a, b) => Math.abs(b.change_24h) - Math.abs(a.change_24h));
      setMovers(live.slice(0, 16));
    } catch { /* ignore */ }
  }, 30000, [!!me]);

  if (me === undefined) return null;
  const [page, arg] = route;

  if (!me || page === "login" || page === "signup") {
    if (me && (page === "login" || page === "signup")) { go("market"); return null; }
    return <Auth mode={page === "signup" ? "signup" : "login"} onAuthed={(u) => { setMe(u); go("market"); }} appName={state?.app_name || "FameX"} />;
  }

  const ctx = { me, refreshMe, state, setMe };
  const pending = me.status !== "approved";
  const tabs = [["market", "Market"], ["ipo", "IPO"], ["leaders", "Leaders"], ["portfolio", "Portfolio"]];
  if (me.is_admin) tabs.push(["admin", "Admin"]);

  let body;
  if (pending && !["settings", "u", "admin"].includes(page)) {
    body = <Pending me={me} />;
  } else if (page === "p") body = <Personality id={arg} />;
  else if (page === "portfolio") body = <Portfolio />;
  else if (page === "leaders") body = <Leaderboard />;
  else if (page === "ipo") body = <Ipo />;
  else if (page === "u") body = <Player username={decodeURIComponent(arg || "")} />;
  else if (page === "settings") body = <Settings />;
  else if (page === "admin" && me.is_admin) body = <Admin />;
  else body = <Market />;

  return (
    <AppCtx.Provider value={ctx}>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/market">
            <span className="brand-mark"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M4 18l5-6 4 3 7-9" /></svg></span>
            {state?.app_name || "FameX"}
          </a>
          <nav className="nav">
            {tabs.map(([k, label]) => <a key={k} href={`#/${k}`} className={page === k ? "active" : ""}>{label}</a>)}
          </nav>
          <div className="top-right">
            <ClearingClock offset={offset} tickSeconds={state?.tick_seconds || 30} />
            {me.status === "approved" && (
              <a className="wallet" href="#/portfolio">
                <div className="num">{money(me.net_worth, 0)}</div>
                <div className="tiny">{money(me.cash, 0)} cash</div>
              </a>
            )}
            <a href="#/settings" aria-label="Your profile"><Avatar user={me} size={32} /></a>
          </div>
        </div>
        <Ticker items={movers} />
      </header>
      <main className="page">{body}</main>
      <nav className="tabbar" style={{ "--tabs": tabs.length }}>
        {tabs.map(([k, label]) => (
          <a key={k} href={`#/${k}`} className={page === k ? "active" : ""}><Icon name={k} />{label}</a>
        ))}
      </nav>
    </AppCtx.Provider>
  );
}

function Pending({ me }) {
  return (
    <div className="card card-pad stack" style={{ maxWidth: 560 }}>
      <span className="label">{me.status === "deferred" ? "Starts next season" : "Waiting for approval"}</span>
      <h1>You're on the list, {me.username}.</h1>
      <p className="muted">
        {me.status === "deferred"
          ? "An admin has you starting at the beginning of next season, with a fresh bankroll alongside everyone else."
          : "An admin will approve your account shortly. Once they do, you'll get your starting cash and can start trading."}
      </p>
      <p className="muted">In the meantime you can <a href="#/settings">set up your profile</a>.</p>
    </div>
  );
}

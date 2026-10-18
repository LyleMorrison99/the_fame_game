import { useEffect, useRef, useState, createContext, useContext } from "react";

// ------------------------------------------------------------------ api
export async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const err = new Error((data && data.detail && (typeof data.detail === "string" ? data.detail : "Check the form and try again.")) || `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// ------------------------------------------------------------------ app context
export const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);

// ------------------------------------------------------------------ routing
export function useRoute() {
  const read = () => (window.location.hash.replace(/^#\/?/, "") || "market").split("/");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
export const go = (path) => { window.location.hash = "#/" + path; };

// ------------------------------------------------------------------ formatting
export const money = (v, digits = 2) =>
  v == null ? "—" : (v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const compact = (v) =>
  v >= 1e6 ? "$" + (v / 1e6).toFixed(2) + "M" : v >= 1e4 ? "$" + (v / 1e3).toFixed(1) + "K" : money(v, 0);
export const pct = (v, digits = 1) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(digits) + "%");
export const int = (v) => (v ?? 0).toLocaleString("en-US");
export const dir = (v) => (v > 0.00005 ? "up" : v < -0.00005 ? "down" : "");

export function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 45) return "just now";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
export function when(iso) {
  return new Date(iso).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
export function until(iso, now = Date.now()) {
  let s = Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000));
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

// ------------------------------------------------------------------ curve math (mirrors the server)
export const curvePrice = (p, sold = p.sold) => p.p0 + p.k * sold;
export function quote(p, side, shares) {
  if (!shares || shares < 1) return null;
  const n = side === "buy" ? Math.min(shares, Math.max(0, p.supply - p.sold)) : Math.min(shares, p.sold);
  const d = side === "buy" ? n : -n;
  const avg = p.p0 + p.k * (p.sold + d / 2);
  return { shares: n, avg, total: avg * n, after: curvePrice(p, p.sold + d) };
}
export function sharesForDollars(p, dollars) {
  // solve n * (price + k n / 2) = dollars
  const a = p.k / 2, b = curvePrice(p);
  if (a === 0) return Math.floor(dollars / b);
  return Math.max(0, Math.floor((-b + Math.sqrt(b * b + 4 * a * dollars)) / (2 * a)));
}

// ------------------------------------------------------------------ hooks
export function usePoll(fn, ms, deps = []) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    let alive = true;
    const run = () => alive && saved.current();
    run();
    const id = setInterval(run, ms);
    const onTick = () => setTimeout(run, 1500);
    window.addEventListener("famex:tick", onTick);
    return () => { alive = false; clearInterval(id); window.removeEventListener("famex:tick", onTick); };
  }, deps);
}

export function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(id); }, [ms]);
  return now;
}

// ------------------------------------------------------------------ small components
const HUES = [330, 262, 200, 160, 24, 290, 12, 220, 180, 45];
function hueFor(s) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0; return HUES[h % HUES.length]; }

export function Avatar({ user, size = 32 }) {
  if (user?.avatar_url) return <img className="avatar" src={user.avatar_url} width={size} height={size} alt="" style={{ width: size, height: size }} />;
  const name = user?.username || "?";
  const hue = hueFor(name);
  return (
    <span className="avatar" aria-hidden="true"
      style={{ width: size, height: size, fontSize: size * 0.42, background: `hsl(${hue} 62% 46%)` }}>
      {name.replace(/[^A-Za-z0-9]/g, "").slice(0, 1).toUpperCase()}
    </span>
  );
}

export function Monogram({ name, size = 34 }) {
  const parts = name.replace(/[^A-Za-z0-9 ]/g, "").split(" ").filter(Boolean);
  const text = (parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : parts[0]?.[1] || "");
  const hue = hueFor(name);
  return (
    <span className="monogram" aria-hidden="true"
      style={{ width: size, height: size, background: `hsl(${hue} 70% 50% / 0.15)`, color: `hsl(${hue} 65% 45%)` }}>
      {text.toUpperCase()}
    </span>
  );
}

export function Change({ v, digits = 1 }) {
  return <span className={"num " + dir(v)}>{pct(v || 0, digits)}</span>;
}

export function Sparkline({ points, width = 84, height = 26 }) {
  if (!points || points.length < 2) return <svg width={width} height={height} aria-hidden="true"><line x1="0" x2={width} y1={height / 2} y2={height / 2} stroke="var(--line)" /></svg>;
  const min = Math.min(...points), max = Math.max(...points);
  const span = max - min || 1;
  const xy = points.map((p, i) => [(i / (points.length - 1)) * (width - 2) + 1, height - 2 - ((p - min) / span) * (height - 4)]);
  const d = xy.map(([x, y], i) => (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1)).join(" ");
  const color = points[points.length - 1] >= points[0] ? "var(--up)" : "var(--down)";
  return (
    <svg width={width} height={height} aria-hidden="true">
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={xy[xy.length - 1][0]} cy={xy[xy.length - 1][1]} r="2" fill={color} />
    </svg>
  );
}

export function StatusChips({ p }) {
  return (
    <span className="chips">
      {p.sold_out && <span className="chip chip-soldout">SOLD OUT</span>}
      {p.status === "ipo" && <span className="chip chip-gold">IPO OPEN</span>}
      {p.status === "queued" && <span className="chip chip-gold">IPO SOON</span>}
    </span>
  );
}

export function Toast({ msg }) {
  if (!msg) return null;
  return <div className="toast" role="status">{msg}</div>;
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return <div className="notice notice-error" role="alert">{error}</div>;
}

export function useToast() {
  const [msg, setMsg] = useState("");
  const t = useRef();
  const show = (m) => { setMsg(m); clearTimeout(t.current); t.current = setTimeout(() => setMsg(""), 3200); };
  return [msg, show];
}

export async function resizeImage(file, size = 256) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
    const s = Math.min(img.width, img.height);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    canvas.getContext("2d").drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size);
    return await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.86));
  } finally {
    URL.revokeObjectURL(url);
  }
}

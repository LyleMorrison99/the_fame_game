import { useState } from "react";
import { api, Avatar, ErrorNote, resizeImage } from "../lib.jsx";

export default function Auth({ mode, onAuthed, appName }) {
  const signup = mode === "signup";
  const [f, setF] = useState({ passphrase: "", username: "", password: "", email: "", bio: "" });
  const [avatar, setAvatar] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const pick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const blob = await resizeImage(file);
      setAvatar(blob);
      setPreview(URL.createObjectURL(blob));
    } catch {
      setError("That image couldn't be read. Try a JPEG or PNG.");
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      let user;
      if (signup) {
        user = await api("/api/auth/signup", { method: "POST", body: f });
        if (avatar) {
          const form = new FormData();
          form.append("file", avatar, "avatar.jpg");
          user = await api("/api/me/avatar", { method: "POST", form });
        }
      } else {
        user = await api("/api/auth/login", { method: "POST", body: { username: f.username, password: f.password } });
      }
      onAuthed(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="auth">
        <div className="auth-hero stack">
          <span className="brand">
            <span className="brand-mark"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M4 18l5-6 4 3 7-9" /></svg></span>
            {appName}
          </span>
          <p className="muted">The stock market for famous people. Buy low on who's about to blow up.</p>
        </div>
        <form className="card card-pad stack" onSubmit={submit}>
          <h2>{signup ? "Create your account" : "Log in"}</h2>
          {signup && (
            <label className="field">
              <span>Passphrase</span>
              <input id="passphrase" className="input mono" value={f.passphrase} onChange={set("passphrase")} placeholder="e.g. velvet-comet-42" required autoComplete="off" />
              <span className="hint">Your admin gives each player their own passphrase. It works once.</span>
            </label>
          )}
          <label className="field">
            <span>Username</span>
            <input id="username" className="input" value={f.username} onChange={set("username")} required autoComplete="username" />
          </label>
          <label className="field">
            <span>Password</span>
            <input id="password" className="input" type="password" value={f.password} onChange={set("password")} required minLength={signup ? 8 : undefined} autoComplete={signup ? "new-password" : "current-password"} />
            {signup && <span className="hint">At least 8 characters.</span>}
          </label>
          {signup && (
            <>
              <label className="field">
                <span>Email</span>
                <input id="email" className="input" type="email" value={f.email} onChange={set("email")} required autoComplete="email" />
                <span className="hint">Only admins see this.</span>
              </label>
              <label className="field">
                <span>Short bio</span>
                <textarea id="bio" className="input" value={f.bio} onChange={set("bio")} maxLength={160} placeholder="Your trading philosophy, in one line." />
                <span className="hint">{160 - f.bio.length} characters left</span>
              </label>
              <div className="field">
                <span>Avatar (optional)</span>
                <div className="avatar-pick">
                  {preview ? <img className="avatar" src={preview} width="56" height="56" alt="" /> : <Avatar user={{ username: f.username || "?" }} size={56} />}
                  <label className="btn btn-sm">
                    {preview ? "Choose another" : "Upload image"}
                    <input id="avatar" type="file" accept="image/*" onChange={pick} hidden />
                  </label>
                </div>
              </div>
            </>
          )}
          <ErrorNote error={error} />
          <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "One sec…" : signup ? "Create account" : "Log in"}</button>
          <p className="small muted" style={{ textAlign: "center" }}>
            {signup ? <>Already playing? <a href="#/login">Log in</a></> : <>Got a passphrase? <a href="#/signup">Create your account</a></>}
          </p>
        </form>
      </div>
    </div>
  );
}

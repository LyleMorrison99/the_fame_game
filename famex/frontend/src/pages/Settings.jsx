import { useState } from "react";
import { api, Avatar, ErrorNote, go, resizeImage, Toast, useApp, useToast } from "../lib.jsx";

export default function Settings() {
  const { me, setMe } = useApp();
  const [bio, setBio] = useState(me.bio || "");
  const [email, setEmail] = useState(me.email || "");
  const [error, setError] = useState("");
  const [toast, showToast] = useToast();

  const save = async (e) => {
    e.preventDefault();
    setError("");
    try { setMe(await api("/api/me", { method: "PUT", body: { bio, email } })); showToast("Profile saved."); }
    catch (err) { setError(err.message); }
  };
  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    try {
      const blob = await resizeImage(file);
      const form = new FormData();
      form.append("file", blob, "avatar.jpg");
      setMe(await api("/api/me/avatar", { method: "POST", form }));
      showToast("Avatar updated.");
    } catch (err) { setError(err.message || "That image couldn't be read."); }
  };
  const logout = async () => { await api("/api/auth/logout", { method: "POST" }); setMe(null); go("login"); };

  return (
    <>
      <div className="page-head"><div><span className="label">Profile</span><h1>{me.username}</h1></div>
        <a className="btn" href={`#/u/${encodeURIComponent(me.username)}`}>View public profile</a></div>
      <form className="card card-pad stack" style={{ maxWidth: 560 }} onSubmit={save}>
        <div className="avatar-pick">
          <Avatar user={me} size={72} />
          <label className="btn btn-sm">Change avatar<input id="avatar-upload" type="file" accept="image/*" onChange={upload} hidden /></label>
        </div>
        <label className="field"><span>Short bio</span>
          <textarea id="bio" className="input" value={bio} onChange={(e) => setBio(e.target.value)} maxLength={160} />
          <span className="hint">{160 - bio.length} characters left. Everyone sees this on the leaderboard.</span>
        </label>
        <label className="field"><span>Email</span>
          <input id="email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <span className="hint">Only admins see your email.</span>
        </label>
        <ErrorNote error={error} />
        <div className="spread">
          <button className="btn btn-primary">Save profile</button>
          <button type="button" className="btn" onClick={logout}>Log out</button>
        </div>
      </form>
      <Toast msg={toast} />
    </>
  );
}

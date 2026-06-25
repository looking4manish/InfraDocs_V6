import { useState } from "react";
import { endpoints, setToken } from "../api/client";

const wrap =
  "min-h-screen flex items-center justify-center bg-[#0a0e14] text-zinc-100 p-6";
const panel =
  "neon-panel w-full max-w-sm rounded-2xl p-7 flex flex-col gap-4";
const field =
  "w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm outline-none focus:border-[var(--neon)] transition-colors";
const btn =
  "w-full rounded-lg py-2 text-sm font-medium neon-glow border border-[var(--neon)] bg-[var(--neon)]/10 hover:bg-[var(--neon)]/20 disabled:opacity-50 transition-colors";

export function Login({ onLoggedIn }) {
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const { data } = await endpoints.login(u.trim(), p);
      setToken(data.token);
      onLoggedIn(data);
    } catch (e2) {
      setErr(e2?.response?.data?.detail || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={wrap}>
      <form onSubmit={submit} className={panel}>
        <div className="text-center">
          <div className="text-xl font-semibold tracking-tight">InfraDocs</div>
          <div className="text-xs text-zinc-400 mt-1">Sign in to continue</div>
        </div>
        <input
          className={field}
          placeholder="Username"
          autoFocus
          value={u}
          onChange={(e) => setU(e.target.value)}
        />
        <input
          className={field}
          type="password"
          placeholder="Password"
          value={p}
          onChange={(e) => setP(e.target.value)}
        />
        {err && <div className="text-rose-400 text-xs">{err}</div>}
        <button className={btn} disabled={busy || !u || !p}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

export function ChangePassword({ onDone }) {
  const [p1, setP1] = useState("");
  const [p2, setP2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    if (p1.length < 8) return setErr("Use at least 8 characters");
    if (p1 !== p2) return setErr("Passwords don't match");
    setBusy(true);
    try {
      await endpoints.changePassword(p1);
      onDone();
    } catch (e2) {
      setErr(e2?.response?.data?.detail || "Could not change password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={wrap}>
      <form onSubmit={submit} className={panel}>
        <div className="text-center">
          <div className="text-xl font-semibold tracking-tight">
            Set a new password
          </div>
          <div className="text-xs text-zinc-400 mt-1">
            You're using the default password — please change it.
          </div>
        </div>
        <input
          className={field}
          type="password"
          placeholder="New password (min 8 chars)"
          autoFocus
          value={p1}
          onChange={(e) => setP1(e.target.value)}
        />
        <input
          className={field}
          type="password"
          placeholder="Confirm new password"
          value={p2}
          onChange={(e) => setP2(e.target.value)}
        />
        {err && <div className="text-rose-400 text-xs">{err}</div>}
        <button className={btn} disabled={busy || !p1 || !p2}>
          {busy ? "Saving…" : "Save & continue"}
        </button>
      </form>
    </div>
  );
}

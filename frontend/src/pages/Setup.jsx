import { useState } from "react";
import { endpoints } from "../api/client";

const field =
  "w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm outline-none focus:border-[var(--neon)] transition-colors";
const choice = (active) =>
  `flex-1 rounded-lg border px-3 py-2 text-sm text-center cursor-pointer transition-colors ${
    active
      ? "border-[var(--neon)] bg-[var(--neon)]/10 neon-glow"
      : "border-white/10 hover:border-white/25"
  }`;
const btn =
  "rounded-lg px-4 py-2 text-sm font-medium neon-glow border border-[var(--neon)] bg-[var(--neon)]/10 hover:bg-[var(--neon)]/20 disabled:opacity-50 transition-colors";

function Section({ n, title, children }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
        {n}. {title}
      </div>
      {children}
    </div>
  );
}

export default function Setup({ onDone }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("standalone");
  const [primaryUrl, setPrimaryUrl] = useState("");
  const [joinToken, setJoinToken] = useState("");
  const [exposure, setExposure] = useState("domain");
  const [domain, setDomain] = useState("");
  const [token, setToken] = useState("");
  const [ip, setIp] = useState(null);
  const [detecting, setDetecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function detect() {
    setDetecting(true);
    setErr("");
    try {
      const { data } = await endpoints.detectIp();
      setIp(data);
    } catch {
      setErr("Could not detect IP");
    } finally {
      setDetecting(false);
    }
  }

  async function finish() {
    setBusy(true);
    setErr("");
    try {
      await endpoints.completeSetup({
        server_name: name || null,
        role,
        exposure,
        domain: domain || null,
        primary_url: role === "secondary" ? primaryUrl || null : null,
        join_token: role === "secondary" ? joinToken || null : null,
      });
      onDone();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Could not save setup");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0e14] text-zinc-100 p-6">
      <div className="neon-panel w-full max-w-lg rounded-2xl p-7 flex flex-col gap-6">
        <div>
          <div className="text-xl font-semibold tracking-tight">Welcome to InfraDocs</div>
          <div className="text-xs text-zinc-400 mt-1">A few details to get this server online.</div>
        </div>

        <Section n="1" title="This server">
          <input
            className={field}
            placeholder="Display name (e.g. OCI, N150)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Section>

        <Section n="2" title="Role">
          <div className="flex gap-2">
            {["standalone", "primary", "secondary"].map((r) => (
              <div key={r} className={choice(role === r)} onClick={() => setRole(r)}>
                {r}
              </div>
            ))}
          </div>
          {role === "secondary" && (
            <div className="flex flex-col gap-2 mt-1">
              <input className={field} placeholder="Primary URL (e.g. https://infra.you.com)"
                value={primaryUrl} onChange={(e) => setPrimaryUrl(e.target.value)} />
              <input className={field} placeholder="Join token (from the primary)"
                value={joinToken} onChange={(e) => setJoinToken(e.target.value)} />
            </div>
          )}
        </Section>

        <Section n="3" title="How will you reach the UI?">
          <div className="flex gap-2">
            {[
              ["domain", "I have a domain"],
              ["tailscale", "No domain (Tailscale)"],
              ["cloudflare", "Cloudflare Tunnel"],
            ].map(([k, label]) => (
              <div key={k} className={choice(exposure === k)} onClick={() => setExposure(k)}>
                {label}
              </div>
            ))}
          </div>

          {exposure === "domain" && (
            <div className="flex flex-col gap-2 mt-1">
              <input className={field} placeholder="Domain (e.g. infra.you.com)"
                value={domain} onChange={(e) => setDomain(e.target.value)} />
              <button type="button" className={`${btn} self-start`} onClick={detect} disabled={detecting}>
                {detecting ? "Detecting…" : "Detect my public IP"}
              </button>
              {ip && (
                <div className="rounded-lg border border-white/10 bg-black/30 p-3 text-sm flex flex-col gap-2">
                  {ip.public_ip ? (
                    <div>
                      Point your DNS <span className="font-mono text-zinc-300">A</span>-record at:{" "}
                      <span className="font-mono text-[var(--neon)] text-base">{ip.public_ip}</span>
                    </div>
                  ) : (
                    <div className="text-amber-400">No public IP found — this host is likely behind NAT.</div>
                  )}
                  {ip.warnings?.length > 0 && (
                    <ul className="text-[12px] text-amber-400/90 list-disc pl-4 space-y-0.5">
                      {ip.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  )}
                  <div className="text-[11px] text-zinc-500">
                    On a cloud VM, also open ports 80/443 in the firewall/security-list.
                  </div>
                </div>
              )}
            </div>
          )}
          {exposure === "tailscale" && (
            <div className="text-[12.5px] text-zinc-400 mt-1">
              No domain needed — InfraDocs will be reachable on your tailnet via Tailscale Funnel.
              You'll click a one-time login link to join the device.
            </div>
          )}
          {exposure === "cloudflare" && (
            <input className={field} placeholder="Cloudflare tunnel token"
              value={token} onChange={(e) => setToken(e.target.value)} />
          )}
        </Section>

        {err && <div className="text-rose-400 text-xs">{err}</div>}
        <button className={`${btn} self-end`} onClick={finish} disabled={busy}>
          {busy ? "Saving…" : "Finish setup"}
        </button>
      </div>
    </div>
  );
}

# InfraDocs federation timers — install guide

Two scheduled cycles for the federation control plane. Both wrap CLIs that already
exist (`app/federation_agent.py`); these units just run them on a timer.

| Unit pair | Runs where | What it does | Cadence |
|---|---|---|---|
| `infradocs-fed-reap.{service,timer}` | **PRIMARY only** | expires commands a secondary claimed but never reported (`> 900s`) | every 5 min |
| `infradocs-fed-poll.{service,timer}` | **each SECONDARY only** | claims queued commands, runs them via the guarded dispatcher, reports back (outbound → NAT-friendly) | every 5 min |

> **Install is role-detected — never guess.** On each host, read its configured role
> (`settings._id="app"` → `role`, written by the setup wizard) and install ONLY the
> matching timer:
>
> ```bash
> # what role is THIS host? (run from the repo dir, venv active)
> python - <<'PY'
> from app.core.config_loader import load_config
> from app.core.db_manager import DBManager
> cfg = load_config("config.yml")
> db = DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)
> print("role =", (db.db.settings.find_one({"_id": "app"}) or {}).get("role"))
> db.close()
> PY
> ```
>
> - `role == primary`   → install **reap** only.
> - `role == secondary` → install **poll** only.
> - `role` unset/None    → install **nothing**; run the setup wizard first.
>
> Both cycles also **self-guard** at runtime: `poll` is a no-op unless `role==secondary`,
> `reap` is a no-op unless `role==primary`. So a cross-install can't corrupt anything —
> it just logs a refusal — but don't rely on that; install by detected role.

## Paths — adjust before installing

The `.service` files are written for the reference deploy:

- user/group: `msinha`
- repo (`WorkingDirectory`): `/home/msinha/projects/InfraDocs_V6`
- interpreter (`ExecStart`): `…/venv/bin/python`
- env (`EnvironmentFile`): `…/.env` (supplies `INFRADOCS_MONGO_URI`, etc.)

If a host differs, edit those four lines in the relevant `.service` before copying.
A secondary must have the InfraDocs repo + venv installed **and** be configured as a
secondary (setup wizard → role `secondary`, primary URL, join token) or `poll` exits 1.

## Install — PRIMARY (reap)

```bash
REPO=/home/msinha/projects/InfraDocs_V6
sudo cp "$REPO"/deploy/systemd/infradocs-fed-reap.service /etc/systemd/system/
sudo cp "$REPO"/deploy/systemd/infradocs-fed-reap.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now infradocs-fed-reap.timer
```

## Install — SECONDARY (poll)

```bash
REPO=/home/msinha/projects/InfraDocs_V6   # path on THAT secondary
sudo cp "$REPO"/deploy/systemd/infradocs-fed-poll.service /etc/systemd/system/
sudo cp "$REPO"/deploy/systemd/infradocs-fed-poll.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now infradocs-fed-poll.timer
```

## Verify (either host)

```bash
systemctl list-timers --all | grep infradocs-fed     # timer registered, next run shown
systemctl status  infradocs-fed-reap.timer           # (or -poll)
journalctl -u infradocs-fed-reap.service -n 20 --no-pager   # last run output, no errors
# force one run now:
sudo systemctl start infradocs-fed-reap.service       # (or -poll)
```

A healthy reap run logs `reaped N stale command(s)` (N is 0 when the queue is clean).
A healthy poll run logs `executed N command(s): [...]`.

## Uninstall

```bash
sudo systemctl disable --now infradocs-fed-reap.timer    # (or -poll)
sudo rm /etc/systemd/system/infradocs-fed-reap.service /etc/systemd/system/infradocs-fed-reap.timer
sudo systemctl daemon-reload
```

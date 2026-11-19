# /// script
# requires-python = ">=3.10"
# dependencies = ["tzdata"]
# ///
"""Email Autopilot guard: safety limits, kill switch, lead database, activity log.

Every command prints JSON so an AI agent can read it. Run with:  uv run tools/guard.py <command>
The mailer (tools/mailer.py) calls the same functions, so the limits hold even if an agent forgets them.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config.yaml"
LEADS = DATA / "leads.csv"
LOG = DATA / "activity_log.csv"
BLOCK = DATA / "blocklist.txt"
STOP = DATA / "STOP"
REPORTS = DATA / "reports"

LEAD_FIELDS = ["email", "name", "company", "website", "category", "location", "source", "fit_score", "hook",
               "status", "added", "last_contact", "followups", "notes"]
LOG_FIELDS = ["timestamp", "action", "target", "mode", "detail"]
STATUSES = ["new", "emailed", "followed_up", "replied", "interested", "not_interested", "bounced", "skipped"]
SEND_ACTIONS = ("email", "followup", "reply")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FREEMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.gr", "yahoo.co.uk", "hotmail.com", "hotmail.gr",
            "outlook.com", "live.com", "msn.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "aol.com",
            "gmx.com", "gmx.net", "gmx.de", "mail.com", "otenet.gr", "windowslive.com", "yandex.com", "zoho.com"}

DEFAULTS = {
    "outreach": {"enabled": True, "mode": "dry_run", "followups": 1, "followup_after_days": 5},
    "email": {"provider": "smtp", "from_name": "", "from_email": "", "reply_to": "", "smtp_host": "smtp.gmail.com",
              "smtp_port": 587, "smtp_user": "", "imap_host": "", "footer": "", "allow_freemail": True},
    "limits": {"emails_per_day": 30, "warmup_days": 14, "min_delay_seconds": 45, "max_delay_seconds": 120,
               "work_hours": "09:00-18:00", "work_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
               "timezone": "Europe/Athens"},
    "schedule": {"outreach_runs": ["09:30", "11:30", "14:30", "16:30"], "inbox_run": "17:30"},
}
HARD_CAPS = {"emails_per_day": 100}


# ---------------------------------------------------------------- config (tiny YAML subset)
def _strip_comment(s: str) -> str:
    in_q = False
    for i, ch in enumerate(s):
        if ch == '"':
            in_q = not in_q
        elif ch == "#" and not in_q and (i == 0 or s[i - 1] in " \t"):
            return s[:i]
    return s


def _value(raw: str):
    raw = raw.strip()
    if raw == "":
        return ""
    if raw[0] in '["':
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip('"')
    low = raw.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return int(raw)
    except ValueError:
        return raw


def load_config() -> dict:
    cfg: dict = {k: dict(v) for k, v in DEFAULTS.items()}
    if not CONFIG.exists():
        return cfg
    section = None
    for line in CONFIG.read_text(encoding="utf-8-sig").splitlines():
        line = _strip_comment(line).rstrip()
        if not line.strip() or ":" not in line:
            continue
        indented = line[0] in " \t"
        key, _, val = line.strip().partition(":")
        if not indented:
            if val.strip() == "":
                section = key
                cfg.setdefault(section, {})
            else:
                cfg[key] = _value(val)
                section = None
        elif section:
            cfg[section][key] = _value(val)
    for k, cap in HARD_CAPS.items():
        try:
            cfg["limits"][k] = min(int(cfg["limits"][k]), cap)
        except (KeyError, ValueError, TypeError):
            cfg["limits"][k] = DEFAULTS["limits"].get(k, 0)
    return cfg


def now(cfg) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(cfg["limits"].get("timezone", "Europe/Athens"))).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def mode(cfg) -> str:
    return "live" if str(cfg["outreach"].get("mode", "dry_run")).lower() == "live" else "dry_run"


# ---------------------------------------------------------------- keys (an email address or a business domain)
def domain_of(x: str) -> str:
    x = (x or "").strip().lower()
    if "@" in x:
        return x.rsplit("@", 1)[1].strip("> ")
    x = re.sub(r"^[a-z]+://", "", x).split("/")[0].split("?")[0].split("#")[0]
    return x[4:] if x.startswith("www.") else x


def norm_email(x: str) -> str:
    return (x or "").strip().strip("<>").lower()


def same_business(a: str, b: str) -> bool:
    """Same address, or two different addresses at the same company domain (never for free mail providers)."""
    if not a or not b:
        return False
    if "@" in a and "@" in b and norm_email(a) == norm_email(b):
        return True
    da, db = domain_of(a), domain_of(b)
    return bool(da) and da == db and da not in FREEMAIL


def is_freemail(x: str) -> bool:
    return domain_of(x) in FREEMAIL


# ---------------------------------------------------------------- csv helpers
def read_csv(path: Path, fields: list[str]) -> list[dict]:
    for attempt in range(5):
        try:
            if not path.exists():
                return []
            with path.open(encoding="utf-8-sig", newline="") as f:
                return [{k: (r.get(k) or "") for k in fields} for r in csv.DictReader(f)]
        except (PermissionError, OSError):
            time.sleep(0.1 * (attempt + 1))
    return []


def _replace_retry(tmp: Path, path: Path) -> None:
    for i in range(40):
        try:
            tmp.replace(path)
            return
        except PermissionError:  # Windows: another process is reading the file for a moment
            time.sleep(0.05 * (i + 1) if i < 10 else 0.5)
    tmp.replace(path)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    _replace_retry(tmp, path)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    _replace_retry(tmp, path)


def append_log(action: str, target: str, md: str, detail: str, cfg) -> None:
    rows = read_csv(LOG, LOG_FIELDS)
    rows.append({"timestamp": now(cfg).strftime("%Y-%m-%d %H:%M:%S"), "action": action,
                 "target": target, "mode": md, "detail": detail.replace("\n", " ")[:1500]})
    write_csv(LOG, LOG_FIELDS, rows)


def blocked() -> set[str]:
    if not BLOCK.exists():
        return set()
    return {l.strip().lower() for l in BLOCK.read_text(encoding="utf-8").splitlines() if l.strip()}


def is_blocked(x: str, bl: set[str] | None = None) -> bool:
    bl = blocked() if bl is None else bl
    e = norm_email(x) if "@" in x else ""
    d = domain_of(x)
    return (bool(e) and e in bl) or (bool(d) and d not in FREEMAIL and d in bl)


def out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- limits
def counts(cfg, md: str, since: datetime, actions: tuple[str, ...]) -> int:
    n = 0
    for r in read_csv(LOG, LOG_FIELDS):
        if r["mode"] != md or r["action"] not in actions:
            continue
        try:
            if datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S") >= since:
                n += 1
        except ValueError:
            pass
    return n


def in_warmup(cfg) -> bool:
    live = [r for r in read_csv(LOG, LOG_FIELDS) if r["mode"] == "live" and r["action"] in SEND_ACTIONS]
    if not live:
        return True
    first = datetime.strptime(live[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
    return (now(cfg) - first).days < int(cfg["limits"].get("warmup_days", 14))


def remaining(cfg) -> tuple[int, str]:
    daily = int(cfg["limits"]["emails_per_day"])
    if in_warmup(cfg):
        daily = max(1, daily // 2)
    day_start = now(cfg).replace(hour=0, minute=0, second=0, microsecond=0)
    left = daily - counts(cfg, mode(cfg), day_start, SEND_ACTIONS)
    return max(0, left), ("daily emails_per_day reached" if left <= 0 else "")


def working_time(cfg) -> tuple[bool, str]:
    if os.environ.get("EA_FORCE") == "1":
        return True, ""
    lim = cfg["limits"]
    t = now(cfg)
    if DAYS[t.weekday()] not in lim.get("work_days", DAYS[:5]):
        return False, f"{DAYS[t.weekday()]} is not a work day"
    try:
        a, b = str(lim.get("work_hours", "09:00-18:00")).split("-")
        start = datetime.strptime(a.strip(), "%H:%M").time()
        end = datetime.strptime(b.strip(), "%H:%M").time()
        if not (start <= t.time() <= end):
            return False, f"outside work hours {a}-{b}"
    except ValueError:
        pass
    return True, ""


def check_send(cfg) -> dict:
    """Single source of truth for 'may I send an email right now?' (used by `check` and by the mailer)."""
    if STOP.exists():
        return {"ok": False, "reason": "KILL SWITCH: " + STOP.read_text(encoding="utf-8-sig").strip()
                + " (delete data/STOP to resume)"}
    if not cfg["outreach"].get("enabled", True):
        return {"ok": False, "reason": "outreach disabled in config"}
    ok, why = working_time(cfg)
    if not ok:
        return {"ok": False, "reason": why}
    left, why = remaining(cfg)
    return {"ok": left > 0, "remaining": left, "mode": mode(cfg), "warmup": in_warmup(cfg), "reason": why}


def cmd_check(a, cfg):
    out(check_send(cfg))


def cmd_batch(a, cfg):
    left, _ = remaining(cfg)
    t = now(cfg).strftime("%H:%M")
    later = [r for r in cfg["schedule"].get("outreach_runs", []) if str(r) > t]
    runs_left = 1 + len(later)
    n = math.ceil(left / runs_left) if left > 0 else 0
    out({"this_run": n, "remaining_today": left, "runs_left_today": runs_left})


def cmd_log(a, cfg):
    append_log(a.action, a.target, mode(cfg), a.detail or "", cfg)
    left = remaining(cfg)[0] if a.action in SEND_ACTIONS else None
    out({"logged": True, "mode": mode(cfg), "remaining": left})


def cmd_delay(a, cfg):
    lim = cfg["limits"]
    lo, hi = int(lim.get("min_delay_seconds", 45)), int(lim.get("max_delay_seconds", 120))
    s = random.randint(min(lo, hi), max(lo, hi))
    if a.seconds is not None:
        s = a.seconds
    time.sleep(s)
    out({"slept_seconds": s})


def cmd_stop(a, cfg):
    _atomic_write(STOP, f"{now(cfg):%Y-%m-%d %H:%M} {a.reason}\n")
    append_log("stop", "-", mode(cfg), a.reason, cfg)
    out({"stopped": True, "reason": a.reason})


def cmd_resume(a, cfg):
    existed = STOP.exists()
    STOP.unlink(missing_ok=True)
    out({"resumed": True, "was_stopped": existed})


# ---------------------------------------------------------------- leads
def contacted_live(x: str) -> bool:
    return any(r["mode"] == "live" and r["action"] in SEND_ACTIONS and same_business(r["target"], x)
               for r in read_csv(LOG, LOG_FIELDS))  # dry_run drafts do not count as contact


def cmd_seen(a, cfg):
    x = a.key.strip().lower()
    lead = next((r for r in read_csv(LEADS, LEAD_FIELDS) if same_business(r["email"], x) or
                 (domain_of(r["website"]) == domain_of(x) and domain_of(x) not in FREEMAIL and domain_of(x))), None)
    out({"key": x, "blocked": is_blocked(x), "contacted": contacted_live(x),
         "in_leads": bool(lead), "status": lead["status"] if lead else None})


EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)+$")


def cmd_lead_add(a, cfg):
    e = norm_email(a.email)
    if not EMAIL_RE.match(e) or e.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js"):
        return out({"added": False, "reason": "not a valid email address"})
    if is_blocked(e):
        return out({"added": False, "reason": "blocked"})
    if is_freemail(e) and not cfg["email"].get("allow_freemail", True):
        return out({"added": False, "reason": "free-mail address and allow_freemail is false"})
    rows = read_csv(LEADS, LEAD_FIELDS)
    if any(same_business(r["email"], e) for r in rows):
        return out({"added": False, "reason": "duplicate (same address or same company domain)"})
    rows.append({"email": e, "name": a.name or "", "company": a.company or "", "website": a.website or "",
                 "category": a.category or "", "location": a.location or "", "source": a.source or "",
                 "fit_score": str(a.score or ""), "hook": a.hook or "", "status": "new",
                 "added": now(cfg).strftime("%Y-%m-%d"), "last_contact": "", "followups": "0", "notes": ""})
    write_csv(LEADS, LEAD_FIELDS, rows)
    out({"added": True, "email": e, "total_leads": len(rows)})


def cmd_lead_list(a, cfg):
    rows = read_csv(LEADS, LEAD_FIELDS)
    bl = blocked()
    rows = [r for r in rows if not is_blocked(r["email"], bl)]
    if a.due_followup:
        max_f = int(cfg["outreach"].get("followups", 1))
        after = int(cfg["outreach"].get("followup_after_days", 5))
        cutoff = now(cfg) - timedelta(days=after)
        due = []
        for r in rows:
            if r["status"] not in ("emailed", "followed_up"):
                continue
            if int(r["followups"] or 0) >= max_f:
                continue
            try:
                if datetime.strptime(r["last_contact"], "%Y-%m-%d %H:%M") <= cutoff:
                    due.append(r)
            except ValueError:
                pass
        rows = due
    elif a.status:
        rows = [r for r in rows if r["status"] == a.status]
    rows.sort(key=lambda r: -int(r["fit_score"] or 0))
    if a.limit is not None:
        rows = rows[: a.limit]
    out({"count": len(rows), "leads": rows})


def lead_update(email: str, cfg, status=None, note=None, contacted=False, force=False):
    """Used by the CLI and by the mailer. In dry_run a 'sent' status is NOT applied, so the live run still contacts the lead."""
    rows = read_csv(LEADS, LEAD_FIELDS)
    hit = next((r for r in rows if norm_email(r["email"]) == norm_email(email)), None)
    if not hit:
        return {"updated": False, "reason": "lead not found; add it with lead-add first"}
    if status and not force and mode(cfg) == "dry_run" and status in ("emailed", "followed_up"):
        hit["notes"] = (hit["notes"] + " | " if hit["notes"] else "") + f"[dry_run: would be {status}]"
        write_csv(LEADS, LEAD_FIELDS, rows)
        return {"updated": False, "dry_run": True, "reason": "dry_run: status kept so the live run still contacts this lead"}
    if status:
        if status not in STATUSES:
            return {"updated": False, "reason": f"status must be one of {STATUSES}"}
        if status == "followed_up":
            hit["followups"] = str(int(hit["followups"] or 0) + 1)
        hit["status"] = status
    if note:
        hit["notes"] = (hit["notes"] + " | " if hit["notes"] else "") + note.replace("\n", " ")
    if contacted:
        hit["last_contact"] = now(cfg).strftime("%Y-%m-%d %H:%M")
    write_csv(LEADS, LEAD_FIELDS, rows)
    return {"updated": True, "lead": hit}


def cmd_lead_set(a, cfg):
    out(lead_update(a.email, cfg, a.status, a.note, a.contacted))


# ---------------------------------------------------------------- orders (the user's own instructions to the agent)
ORDERS = DATA / "orders.json"


def load_orders() -> list[dict]:
    try:
        d = json.loads(ORDERS.read_text(encoding="utf-8-sig"))
        return [o for o in d if isinstance(o, dict) and "id" in o] if isinstance(d, list) else []
    except Exception:
        return []


def save_orders(items: list[dict]) -> None:
    _atomic_write(ORDERS, json.dumps(items[-200:], ensure_ascii=False, indent=1))


def add_order(text: str) -> dict:
    items = load_orders()
    o = {"id": max([int(x.get("id", 0)) for x in items] + [0]) + 1, "text": text.strip()[:2000], "status": "pending",
         "created": time.strftime("%Y-%m-%d %H:%M"), "result": ""}
    items.append(o)
    save_orders(items)
    return o


def cmd_order_add(a, cfg):
    out(add_order(a.text))


def cmd_order_list(a, cfg):
    items = load_orders()
    out({"orders": items if a.all else [o for o in items if o.get("status") == "pending"]})


def cmd_order_done(a, cfg):
    items = load_orders()
    hit = next((o for o in items if int(o.get("id", -1)) == a.id), None)
    if not hit:
        out({"ok": False, "error": "no such order"})
        return
    hit["status"] = a.status
    hit["result"] = (a.result or "")[:1500]
    save_orders(items)
    out({"ok": True, "order": hit})


def block_key(x: str, cfg, reason: str = "") -> str:
    """Block an address (free mail) or the whole company domain (everything else). Idempotent."""
    k = norm_email(x) if ("@" in x and is_freemail(x)) else domain_of(x)
    if k and k not in blocked():
        with BLOCK.open("a", encoding="utf-8") as f:
            f.write(k + "\n")
    rows = read_csv(LEADS, LEAD_FIELDS)
    for r in rows:
        if same_business(r["email"], x):
            r["status"] = "not_interested"
    write_csv(LEADS, LEAD_FIELDS, rows)
    append_log("block", k, mode(cfg), reason, cfg)
    return k


def cmd_block(a, cfg):
    out({"blocked": True, "key": block_key(a.key, cfg, a.reason or "")})


def cmd_bounce(a, cfg):
    """A message to this address bounced: never write there again; stop everything if bounces pile up (protects the sender reputation)."""
    e = norm_email(a.email)
    rows = read_csv(LEADS, LEAD_FIELDS)
    for r in rows:
        if norm_email(r["email"]) == e:
            r["status"] = "bounced"
    write_csv(LEADS, LEAD_FIELDS, rows)
    with BLOCK.open("a", encoding="utf-8") as f:
        f.write(e + "\n")
    append_log("bounce", e, mode(cfg), a.reason or "", cfg)
    log = [r for r in read_csv(LOG, LOG_FIELDS) if r["mode"] == "live"]
    sent = [r for r in log if r["action"] in SEND_ACTIONS][-40:]
    bounced = len([r for r in log if r["action"] == "bounce"])
    rate = bounced / max(1, len(sent))
    stopped = False
    if len(sent) >= 10 and bounced >= 3 and rate > 0.08:
        cmd_stop(argparse.Namespace(reason=f"Bounce rate {rate:.0%}: too many invalid addresses. Fix the lead sources, then delete data/STOP."), cfg)
        stopped = True
    out({"bounced": e, "recent_bounce_rate": f"{rate:.0%}", "stopped": stopped})


# ---------------------------------------------------------------- report / schedule
def build_report(cfg, write: bool = True) -> dict:
    """Today's numbers as a dict. write=False for read-only callers (the dashboard polls this)."""
    t = now(cfg)
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    md = mode(cfg)
    today = {k: counts(cfg, md, day, (k,)) for k in ("email", "followup", "reply", "bounce")}
    leads = read_csv(LEADS, LEAD_FIELDS)
    pipeline = {s: sum(1 for r in leads if r["status"] == s) for s in STATUSES}
    log = [r for r in read_csv(LOG, LOG_FIELDS) if r["mode"] == md]
    first = {r["target"].lower() for r in log if r["action"] == "email"}
    by_email = {norm_email(r["email"]): r for r in leads}
    replied = sum(1 for e in first if by_email.get(e, {}).get("status") in ("replied", "interested", "not_interested"))
    bounced = sum(1 for e in first if by_email.get(e, {}).get("status") == "bounced")
    n = len(first)
    rep = {
        "date": t.strftime("%Y-%m-%d"), "mode": md, "warmup": in_warmup(cfg),
        "kill_switch": STOP.read_text(encoding="utf-8-sig").strip() if STOP.exists() else None,
        "today": today, "pipeline": pipeline,
        "reply_rate": f"{(replied / n * 100):.0f}%" if n else "n/a",
        "bounce_rate": f"{(bounced / n * 100):.0f}%" if n else "n/a",
        "remaining_today": {"email": remaining(cfg)[0]},
    }
    warn = []
    if n >= 40 and replied / n < 0.02:
        warn.append("Reply rate under 2% after 40+ emails: change the subject line, the offer or the targeting.")
    if n >= 20 and bounced / n > 0.05:
        warn.append("Bounce rate above 5%: bad addresses hurt your sender reputation. Tighten where the addresses come from.")
    rep["warnings"] = warn
    if not write:
        return rep
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [f"# Email Autopilot report {rep['date']} ({md}{', warm-up' if rep['warmup'] else ''})", ""]
    if rep["kill_switch"]:
        lines += [f"**STOPPED:** {rep['kill_switch']}. Delete `data/STOP` to resume.", ""]
    lines += ["## Today"] + [f"- {k}: {v}" for k, v in today.items()]
    lines += ["", "## Pipeline"] + [f"- {k}: {v}" for k, v in pipeline.items() if v]
    lines += ["", f"Reply rate: {rep['reply_rate']} | Bounce rate: {rep['bounce_rate']}"]
    if warn:
        lines += ["", "## Warnings"] + [f"- {w}" for w in warn]
    _atomic_write(REPORTS / f"{rep['date']}.md", "\n".join(lines) + "\n")
    return rep


def cmd_report(a, cfg):
    out(build_report(cfg, write=True))


def cmd_schedule(a, cfg):
    s, lim = cfg["schedule"], cfg["limits"]
    out({"outreach_runs": s.get("outreach_runs", []), "inbox_run": s.get("inbox_run", "17:30"),
         "work_days": lim.get("work_days", DAYS[:5])})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("batch")
    s = sub.add_parser("log"); s.add_argument("action", choices=list(SEND_ACTIONS) + ["find", "note"])
    s.add_argument("target"); s.add_argument("--detail", default="")
    s = sub.add_parser("delay"); s.add_argument("--seconds", type=int)
    s = sub.add_parser("stop"); s.add_argument("reason")
    sub.add_parser("resume")
    s = sub.add_parser("seen"); s.add_argument("key")
    s = sub.add_parser("lead-add")
    for f in ("email", "name", "company", "website", "category", "location", "source", "hook"):
        s.add_argument("--" + f, required=(f == "email"))
    s.add_argument("--score", type=int)
    s = sub.add_parser("lead-list"); s.add_argument("--status", choices=STATUSES)
    s.add_argument("--limit", type=int); s.add_argument("--due-followup", action="store_true")
    s = sub.add_parser("lead-set"); s.add_argument("email"); s.add_argument("--status")
    s.add_argument("--note"); s.add_argument("--contacted", action="store_true")
    s = sub.add_parser("block"); s.add_argument("key"); s.add_argument("--reason", default="")
    s = sub.add_parser("bounce"); s.add_argument("email"); s.add_argument("--reason", default="")
    sub.add_parser("report")
    sub.add_parser("schedule")
    s = sub.add_parser("order-add"); s.add_argument("text")
    s = sub.add_parser("order-list"); s.add_argument("--all", action="store_true")
    s = sub.add_parser("order-done"); s.add_argument("id", type=int)
    s.add_argument("--status", choices=["done", "drafted", "failed", "skipped"], default="done"); s.add_argument("--result", default="")
    a = ap.parse_args()
    cfg = load_config()
    {"check": cmd_check, "batch": cmd_batch, "log": cmd_log, "delay": cmd_delay, "stop": cmd_stop,
     "resume": cmd_resume, "seen": cmd_seen, "lead-add": cmd_lead_add, "lead-list": cmd_lead_list,
     "lead-set": cmd_lead_set, "block": cmd_block, "bounce": cmd_bounce, "report": cmd_report,
     "schedule": cmd_schedule, "order-add": cmd_order_add, "order-list": cmd_order_list,
     "order-done": cmd_order_done}[a.cmd](a, cfg)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

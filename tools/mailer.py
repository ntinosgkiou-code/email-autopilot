# /// script
# requires-python = ">=3.10"
# dependencies = ["tzdata"]
# ///
"""Email Autopilot mailer: the ONLY way emails leave this program.

The guard rules are enforced HERE in code (kill switch, daily limit, work hours, blocklist, no repeat contact,
dry_run), so they hold even if an AI agent forgets them.

  uv run tools/mailer.py send --to a@b.com --subject "..." --body "..." [--kind email|followup|reply]
  uv run tools/mailer.py inbox [--days 14]        # replies + bounces from the mailbox (IMAP)
  uv run tools/mailer.py test --to me@example.com # sends a test message to YOURSELF (not counted, not a lead)
  uv run tools/mailer.py status                   # is sending configured?

Passwords live ONLY in data/.secrets/email.json (written by the dashboard form). Never in config.yaml.
"""
from __future__ import annotations

import argparse
import imaplib
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402

SECRETS = guard.DATA / ".secrets" / "email.json"
OUTBOX = guard.DATA / "outbox"
UNSUB_DEFAULT = "If this is not relevant to you, just reply \"stop\" and I will not write again."


def secrets() -> dict:
    try:
        d = json.loads(SECRETS.read_text(encoding="utf-8-sig"))
        d = d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        d = {}
    if os.environ.get("EA_SMTP_PASSWORD"):
        d["password"] = os.environ["EA_SMTP_PASSWORD"]
    if os.environ.get("EA_RESEND_KEY"):
        d["resend_key"] = os.environ["EA_RESEND_KEY"]
    return d


def save_secrets(update: dict) -> None:
    cur = secrets()
    cur.update({k: v for k, v in update.items() if v not in (None, "")})
    guard._atomic_write(SECRETS, json.dumps(cur, ensure_ascii=False))


def configured(cfg) -> tuple[bool, str]:
    e, s = cfg["email"], secrets()
    if not guard.EMAIL_RE.match(guard.norm_email(e.get("from_email", ""))):
        return False, "Λείπει το email αποστολής (from_email)."
    if e.get("provider") == "resend":
        return (bool(s.get("resend_key")), "Λείπει το Resend API key.") if not s.get("resend_key") else (True, "")
    if not e.get("smtp_host") or not (e.get("smtp_user") or e.get("from_email")) or not s.get("password"):
        return False, "Λείπει ο κωδικός εφαρμογής (app password) του email."
    return True, ""


def compose(cfg, to: str, subject: str, body: str, kind: str, with_footer: bool = True) -> EmailMessage:
    e = cfg["email"]
    frm_email = guard.norm_email(e.get("from_email", ""))
    name = (e.get("from_name") or "").replace('"', "").strip()
    m = EmailMessage()
    m["From"] = f'"{name}" <{frm_email}>' if name else frm_email
    m["To"] = to
    m["Subject"] = subject.strip()
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=guard.domain_of(frm_email) or None)
    if e.get("reply_to"):
        m["Reply-To"] = e["reply_to"]
    if with_footer:
        m["List-Unsubscribe"] = f"<mailto:{e.get('reply_to') or frm_email}?subject=unsubscribe>"
    text = body.strip()
    if with_footer:
        unsub = (e.get("unsubscribe_text") or UNSUB_DEFAULT).strip()
        foot = (e.get("footer") or "").strip()
        text += "\n\n-- \n" + (foot + "\n" if foot else "") + unsub
    m.set_content(text)
    return m


def transmit(cfg, m: EmailMessage) -> None:
    e, s = cfg["email"], secrets()
    if e.get("provider") == "resend":
        payload = {"from": m["From"], "to": [m["To"]], "subject": m["Subject"], "text": m.get_content()}
        if m["Reply-To"]:
            payload["reply_to"] = m["Reply-To"]
        if m["List-Unsubscribe"]:
            payload["headers"] = {"List-Unsubscribe": m["List-Unsubscribe"]}
        req = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {s['resend_key']}", "Content-Type": "application/json",
                                              "User-Agent": "email-autopilot/1.0"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
        except urllib.error.HTTPError as ex:
            raise RuntimeError(f"Resend {ex.code}: {ex.read().decode('utf-8', 'replace')[:300]}") from ex
        return
    host, port = e.get("smtp_host"), int(e.get("smtp_port") or 587)
    user = e.get("smtp_user") or e.get("from_email")
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as srv:
            srv.login(user, s["password"].replace(" ", ""))
            srv.send_message(m)
    else:
        with smtplib.SMTP(host, port, timeout=30) as srv:
            srv.starttls(context=ctx)
            srv.login(user, s["password"].replace(" ", ""))
            srv.send_message(m)


def domain_resolves(addr: str) -> bool:
    try:
        socket.getaddrinfo(guard.domain_of(addr), None)
        return True
    except OSError:
        return False


def refuse(reason: str, **extra) -> dict:
    return {"sent": False, "refused": True, "reason": reason, **extra}


def send(cfg, to: str, subject: str, body: str, kind: str = "email") -> dict:
    to = guard.norm_email(to)
    if kind not in guard.SEND_ACTIONS:
        return refuse("kind must be email, followup or reply")
    if not guard.EMAIL_RE.match(to):
        return refuse("invalid recipient address")
    if len(subject.strip()) < 3 or len(body.strip()) < 20:
        return refuse("subject or body too short")
    if guard.is_blocked(to):
        return refuse("recipient is on the blocklist (said no, bounced, or blocked)")
    chk = guard.check_send(cfg)
    if not chk["ok"]:
        return refuse(chk["reason"])
    if guard.is_freemail(to) and not cfg["email"].get("allow_freemail", True):
        return refuse("free-mail address and allow_freemail is false")
    if kind == "email":
        if "http://" in body.lower() or "https://" in body.lower() or "www." in body.lower():
            return refuse("no links in a first email (links belong in replies to interested people)")
        if guard.contacted_live(to):
            return refuse("this person or company was already contacted; use kind=followup")
    elif kind == "followup":
        lead = next((r for r in guard.read_csv(guard.LEADS, guard.LEAD_FIELDS) if guard.norm_email(r["email"]) == to), None)
        if lead and lead["status"] in ("replied", "interested", "not_interested", "bounced"):
            return refuse(f"lead status is {lead['status']}: no follow-ups")
    md = guard.mode(cfg)
    same = [r for r in guard.read_csv(guard.LOG, guard.LOG_FIELDS)
            if r["mode"] == md and r["action"] in guard.SEND_ACTIONS and body.strip()[:80] in r["detail"]]
    if same:
        return refuse("an identical message was already written; every email must be unique")
    detail = f"SUBJECT: {subject.strip()} | {body.strip()}"
    if md == "dry_run":
        OUTBOX.mkdir(parents=True, exist_ok=True)
        fn = OUTBOX / f"{datetime.now():%Y%m%d_%H%M%S}_{re.sub(r'[^a-z0-9]+', '_', to)}.txt"
        m = compose(cfg, to, subject, body, kind)
        fn.write_text(f"To: {to}\nSubject: {m['Subject']}\n\n{m.get_content()}", encoding="utf-8")
        guard.append_log(kind, to, md, detail, cfg)
        guard.lead_update(to, cfg, "followed_up" if kind == "followup" else "emailed", contacted=True)
        return {"sent": False, "dry_run": True, "saved": str(fn.relative_to(guard.ROOT)), "remaining": guard.remaining(cfg)[0]}
    ok, why = configured(cfg)
    if not ok:
        return refuse(why)
    if len((cfg["email"].get("footer") or "").strip()) < 10:
        return refuse("email.footer is empty: put your name, company and postal address there before going live (required by EU/UK/US law)")
    if not domain_resolves(to):
        guard.append_log("note", to, md, "domain does not exist, skipped", cfg)
        guard.cmd_bounce(argparse.Namespace(email=to, reason="domain does not resolve"), cfg)
        return refuse("the domain of this address does not exist (blocked)")
    try:
        transmit(cfg, compose(cfg, to, subject, body, kind))
    except smtplib.SMTPRecipientsRefused:
        guard.cmd_bounce(argparse.Namespace(email=to, reason="refused by server"), cfg)
        return refuse("the mail server refused this recipient (marked as bounced)")
    except smtplib.SMTPAuthenticationError:
        guard.cmd_stop(argparse.Namespace(reason="Email login failed. Check the app password in the dashboard, then delete data/STOP."), cfg)
        return refuse("login to the mail account failed (kill switch set)")
    except Exception as ex:  # noqa: BLE001
        return refuse(f"send failed: {type(ex).__name__}: {ex}")
    guard.append_log(kind, to, md, detail, cfg)
    if kind != "reply":
        guard.lead_update(to, cfg, "followed_up" if kind == "followup" else "emailed", contacted=True)
    return {"sent": True, "to": to, "remaining": guard.remaining(cfg)[0]}


def send_test(cfg, to: str) -> dict:
    ok, why = configured(cfg)
    if not ok:
        return {"ok": False, "message": why}
    try:
        transmit(cfg, compose(cfg, to, "Email Autopilot: test", "This is a test message. If you can read it, sending works.", "email", False))
        return {"ok": True, "message": f"Στάλθηκε δοκιμαστικό email στο {to}. Έλεγξε το inbox (και το spam)."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "message": "Λάθος κωδικός ή όνομα χρήστη. Για Gmail χρειάζεται «κωδικός εφαρμογής» (app password), όχι ο κανονικός κωδικός."}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "message": f"Αποτυχία: {type(ex).__name__}: {ex}"}


# ---------------------------------------------------------------- inbox (replies + bounces)
def _h(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:  # noqa: BLE001
        return v or ""


def imap_host(cfg) -> str:
    e = cfg["email"]
    if e.get("imap_host"):
        return e["imap_host"]
    return (e.get("smtp_host") or "").replace("smtp.", "imap.", 1)


def read_inbox(cfg, days: int = 14, limit: int = 80) -> dict:
    s, e = secrets(), cfg["email"]
    if e.get("provider") == "resend" or not imap_host(cfg) or not s.get("password"):
        return {"ok": False, "reason": "IMAP not available (needs SMTP/IMAP mailbox with app password). Read replies in your mail app.", "messages": []}
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    user = e.get("smtp_user") or e.get("from_email")
    msgs = []
    try:
        box = imaplib.IMAP4_SSL(imap_host(cfg), timeout=30)
        box.login(user, s["password"].replace(" ", ""))
        box.select("INBOX", readonly=True)
        _, ids = box.search(None, "SINCE", since)
        for i in (ids[0].split() or [])[-limit:]:
            _, d = box.fetch(i, "(BODY.PEEK[])")
            if not d or not d[0]:
                continue
            m = message_from_bytes(d[0][1])
            text = ""
            for part in (m.walk() if m.is_multipart() else [m]):
                if part.get_content_type() == "text/plain":
                    text = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
                    break
            frm = parseaddr(_h(m.get("From")))[1].lower()
            subj = _h(m.get("Subject"))
            bounce = bool(re.search(r"mailer-daemon|postmaster", frm) or re.search(r"undeliver|delivery status|failure notice|returned mail", subj, re.I))
            bad = sorted(set(re.findall(r"[a-z0-9._%+\-]+@[a-z0-9\-]+(?:\.[a-z0-9\-]+)+", text.lower()))) if bounce else []
            msgs.append({"from": frm, "subject": subj[:160], "date": m.get("Date"), "in_reply_to": m.get("In-Reply-To"),
                         "is_bounce": bounce, "addresses_in_bounce": [a for a in bad if a != guard.norm_email(user)][:5],
                         "snippet": re.sub(r"\s+", " ", text)[:500]})
        box.logout()
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(ex).__name__}: {ex}", "messages": []}
    return {"ok": True, "count": len(msgs), "messages": list(reversed(msgs))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send"); s.add_argument("--to", required=True); s.add_argument("--subject", required=True)
    s.add_argument("--body"); s.add_argument("--body-file"); s.add_argument("--kind", default="email")
    s = sub.add_parser("inbox"); s.add_argument("--days", type=int, default=14)
    s = sub.add_parser("test"); s.add_argument("--to", required=True)
    sub.add_parser("status")
    a = ap.parse_args()
    cfg = guard.load_config()
    if a.cmd == "send":
        body = a.body if a.body is not None else (open(a.body_file, encoding="utf-8-sig").read() if a.body_file else "")
        guard.out(send(cfg, a.to, a.subject, body, a.kind))
    elif a.cmd == "inbox":
        guard.out(read_inbox(cfg, a.days))
    elif a.cmd == "test":
        guard.out(send_test(cfg, a.to))
    else:
        ok, why = configured(cfg)
        guard.out({"configured": ok, "problem": why, "mode": guard.mode(cfg), "provider": cfg["email"].get("provider")})


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

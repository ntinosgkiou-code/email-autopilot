# /// script
# requires-python = ">=3.10"
# dependencies = ["tzdata"]
# ///
"""Email deliverability check for your sending domain: SPF, DKIM, DMARC, mail servers, domain age, your sending volume.

  uv run tools/deliverability.py [--domain mycompany.gr] [--save]

Without --domain it uses the domain of email.from_email in config.yaml. Prints JSON. Nothing is sent.
Cold email from a domain without SPF/DKIM/DMARC goes to spam. This tells you what to fix, in plain words (Greek).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dnsutil  # noqa: E402
import guard  # noqa: E402

DKIM_SELECTORS = ["google", "selector1", "selector2", "default", "k1", "k2", "k3", "s1", "s2", "mail", "dkim", "smtp",
                  "zoho", "zmail", "resend", "mandrill", "mxvault", "everlytickey1", "protonmail", "pm", "cm", "fm1", "fm2", "fm3", "mailo"]
OUT = guard.DATA / "deliverability.json"


def item(id_: str, status: str, title: str, detail: str, fix: str = "") -> dict:
    return {"id": id_, "status": status, "title": title, "detail": detail, "fix": fix}


def spf_lookups(record: str, depth: int = 0) -> int:
    n = 0
    for m in re.finditer(r"\b(include:|a\b|mx\b|ptr\b|exists:|redirect=)([^\s]*)", record):
        n += 1
        if m.group(1) == "include:" and depth < 3:
            ans, _ = dnsutil.lookup(m.group(2), "TXT")
            for r in ans or []:
                if r.lower().startswith("v=spf1"):
                    n += spf_lookups(r, depth + 1)
    return n


def domain_age_days(domain: str) -> int | None:
    try:
        req = urllib.request.Request(f"https://rdap.org/domain/{domain}", headers={"User-Agent": "email-autopilot/1.0", "Accept": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace"))
        for e in d.get("events", []):
            if e.get("eventAction") == "registration":
                t = datetime.fromisoformat(e["eventDate"].replace("Z", "+00:00"))
                return (datetime.now(timezone.utc) - t).days
    except Exception:  # noqa: BLE001
        return None
    return None


def run(cfg, domain: str = "") -> dict:
    dom = (domain or guard.domain_of(cfg["email"].get("from_email", ""))).lower()
    if not dom:
        return {"ok": False, "error": "Βάλε πρώτα το Email αποστολής στις Ρυθμίσεις (ενότητα 5) και πάτα Αποθήκευση.", "items": []}
    items: list[dict] = []
    if dom in guard.FREEMAIL:
        items.append(item("freemail", "warn", "Στέλνεις από δωρεάν email (" + dom + ")",
                          "Το SPF/DKIM ανήκει στον πάροχο, άρα τεχνικά δουλεύει, αλλά ο πάροχος κόβει τα cold emails γρήγορα.",
                          "Για περισσότερα από ~20 emails τη μέρα πάρε ΞΕΧΩΡΙΣΤΟ domain για αποστολή (π.χ. etairia-mail.gr) με Google Workspace ή Zoho (~€5/μήνα). Μην στέλνεις cold από το κύριο domain της εταιρείας σου."))
    hosts, st = dnsutil.mx_hosts(dom)
    if hosts is None:
        return {"ok": False, "error": f"Δεν έγινε έλεγχος DNS (δίκτυο): {st}", "items": items}
    items.append(item("mx", "pass" if hosts else "fail", "Διακομιστές email (MX)", ", ".join(hosts[:3]) or "Δεν βρέθηκαν",
                      "" if hosts else "Το domain δεν έχει MX: δεν μπορεί να λάβει απαντήσεις. Ρύθμισε το email στον πάροχο του domain."))
    if dom not in guard.FREEMAIL:
        txt, _ = dnsutil.lookup(dom, "TXT")
        spf = [r for r in (txt or []) if r.lower().startswith("v=spf1")]
        if not spf:
            items.append(item("spf", "fail", "SPF", "Δεν βρέθηκε", "Πρόσθεσε εγγραφή TXT SPF στο DNS (ο πάροχος email δίνει την ακριβή τιμή, π.χ. «v=spf1 include:_spf.google.com ~all»)."))
        elif len(spf) > 1:
            items.append(item("spf", "fail", "SPF", "Βρέθηκαν " + str(len(spf)) + " εγγραφές SPF", "Πρέπει να υπάρχει ΜΙΑ. Ένωσέ τες σε μία."))
        else:
            r = spf[0]
            n = spf_lookups(r)
            if r.rstrip().endswith("+all") or r.rstrip().endswith("?all"):
                items.append(item("spf", "fail", "SPF", r, "Τελείωσε το SPF με ~all ή -all, όχι +all/?all."))
            elif n > 10:
                items.append(item("spf", "warn", "SPF", f"{r} ({n} lookups)", "Πάνω από 10 lookups: ο SPF αποτυγχάνει. Αφαίρεσε περιττά include."))
            else:
                items.append(item("spf", "pass", "SPF", r))
        found = None
        for sel in DKIM_SELECTORS:
            for t in ("TXT", "CNAME"):
                ans, _ = dnsutil.lookup(f"{sel}._domainkey.{dom}", t)
                if ans and any(("v=dkim1" in a.lower()) or ("p=" in a.lower()) or t == "CNAME" for a in ans):
                    found = sel
                    break
            if found:
                break
        items.append(item("dkim", "pass" if found else "warn", "DKIM", f"Βρέθηκε (selector «{found}»)" if found else "Δεν βρέθηκε στους συνηθισμένους selectors",
                          "" if found else "Ενεργοποίησε το DKIM στον πάροχο email (Google Workspace: Admin → Gmail → Authenticate email). Αν το έχεις ήδη, ο selector μπορεί απλώς να έχει άλλο όνομα."))
        dm, _ = dnsutil.lookup(f"_dmarc.{dom}", "TXT")
        dmarc = next((r for r in (dm or []) if r.lower().startswith("v=dmarc1")), None)
        if not dmarc:
            items.append(item("dmarc", "fail", "DMARC", "Δεν βρέθηκε", "Πρόσθεσε TXT στο _dmarc." + dom + ": «v=DMARC1; p=none; rua=mailto:" + (cfg["email"].get("from_email") or "you@" + dom) + "». Είναι απαραίτητο για Gmail/Yahoo."))
        else:
            pol = re.search(r"\bp=(\w+)", dmarc)
            p = pol.group(1).lower() if pol else "?"
            items.append(item("dmarc", "pass" if p in ("quarantine", "reject") else "warn", "DMARC", dmarc,
                              "" if p in ("quarantine", "reject") else "Το p=none είναι εντάξει για αρχή. Μετά από 2–4 εβδομάδες χωρίς προβλήματα πέρασε σε p=quarantine."))
        age = domain_age_days(dom)
        if age is not None:
            if age < 30:
                items.append(item("age", "fail", "Ηλικία domain", f"{age} μέρες", "Πολύ νέο domain: ξεκίνα με 5–10 emails τη μέρα και ανέβαινε αργά για 4 εβδομάδες. Τα νέα domains που στέλνουν cold email μπλοκάρονται."))
            elif age < 90:
                items.append(item("age", "warn", "Ηλικία domain", f"{age} μέρες", "Νέο domain: κράτα το όριο κάτω από 20 τη μέρα τον πρώτο μήνα."))
            else:
                items.append(item("age", "pass", "Ηλικία domain", f"{age} μέρες"))
        main = guard.domain_of(cfg["email"].get("from_email", ""))
        site = guard.domain_of(cfg["offer"].get("link", "")) if cfg.get("offer") else ""
        if site and site == main:
            items.append(item("separate", "warn", "Ίδιο domain με το site σου", site, "Αν τα cold emails πάρουν παράπονα, πέφτει η φήμη ΟΛΟΥ του domain (και των κανονικών σου emails). Ξεχωριστό domain για αποστολή."))
    rep = guard.build_report(cfg, write=False)
    live = [r for r in guard.read_csv(guard.LOG, guard.LOG_FIELDS) if r["mode"] == "live" and r["action"] in guard.SEND_ACTIONS]
    per_day = int(cfg["limits"].get("emails_per_day", 30))
    msg = f"όριο {per_day}/μέρα, προθέρμανση {'ενεργή' if rep['warmup'] else 'τελείωσε'}, bounce rate {rep['bounce_rate']}, απαντήσεις {rep['reply_rate']}, πραγματικά emails ως τώρα: {len(live)}"
    st = "pass"
    fix = ""
    if per_day > 50 and dom in guard.FREEMAIL:
        st, fix = "fail", "Με δωρεάν email κράτα το όριο ≤ 30 τη μέρα."
    elif per_day > 40:
        st, fix = "warn", "Πάνω από 40 τη μέρα ανέβα σταδιακά (+10 την εβδομάδα) και μόνο αν το bounce rate είναι < 3%."
    items.append(item("volume", st, "Όγκος αποστολής", msg, fix))
    fails = sum(1 for i in items if i["status"] == "fail")
    warns = sum(1 for i in items if i["status"] == "warn")
    verdict = "ΕΤΟΙΜΟ" if not fails and not warns else ("ΜΕ ΠΡΟΣΟΧΗ" if not fails else "ΔΙΟΡΘΩΣΕ ΠΡΩΤΑ")
    res = {"ok": True, "domain": dom, "verdict": verdict, "fails": fails, "warns": warns, "checked": datetime.now().strftime("%Y-%m-%d %H:%M"), "items": items}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", default="")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    res = run(guard.load_config(), a.domain)
    if a.save:
        guard._atomic_write(OUT, json.dumps(res, ensure_ascii=False, indent=1))
    guard.out(res)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

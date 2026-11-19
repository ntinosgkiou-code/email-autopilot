# Email Autopilot

> **Not technical?** Double-click **`START.bat`** (Mac: `START.command`). A dashboard opens in your browser with a checklist, settings forms, a test button, a go-live button, replies and a pause button. No commands needed. The step-by-step guide is `START-HERE-GUIDE.html` (Greek).

An AI agent (Claude Code or Codex) that does cold email outreach for you, every work day, from your own mailbox:

- **Finds leads.** Local businesses from maps (Google Places with your key, or the free OpenStreetMap data) and from their own websites. Creators who run their own brand, found through web search and their brand sites.
- **Reads their public website** and takes the business contact email that is published there. It never guesses addresses.
- **Scores each lead 1–10** against your ideal customer and writes one **personalized email** per lead, based on a real detail from their site.
- **Sends** within safe limits, **reads replies and bounces**, sends one polite follow-up, blocks anyone who says no.
- **Safety in code, not just in prompts.** The mailer enforces the daily limit, work hours, a warm-up period, a blocklist, no repeat contact, no links in first emails, a footer with your identity and an unsubscribe line, and a kill switch that also trips on login failures or a bounce spike.

## Install (pick one)

**A. From the unzipped folder, in PowerShell or cmd (Windows):**
```
powershell -ExecutionPolicy Bypass -File install.ps1
```
Mac/Linux: `bash install.sh`. It copies the program to `~/email-autopilot`, installs `uv`, registers the skill for Claude Code / Codex, adds a desktop icon and opens the dashboard. Run it again any time to update: your settings and data are kept.

**B. One line from the internet (Windows, PowerShell or cmd):**
```
powershell -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create(((irm https://raw.githubusercontent.com/ntinosgkiou-code/email-autopilot/main/install.ps1).TrimStart([char]0xFEFF)))) -Url https://github.com/ntinosgkiou-code/email-autopilot/archive/refs/heads/main.zip"
```

**C. Let your AI agent install it.** Open any agent (Claude Code, Codex, Cursor, ...) and say:
> Install Email Autopilot: read `AGENT-INSTALL.md` in this folder and follow it. Stop where it says the user must act.

**D. Just double-click `START.bat`.** The dashboard guides you through the rest.

## Setup in 5 steps (the dashboard does all of this with buttons)
1. Install an AI agent and sign in: [Claude Code](https://claude.com/claude-code) (paid Claude plan) or [Codex](https://developers.openai.com/codex).
2. Open the dashboard, tab **Ρυθμίσεις**: who you are, what you sell, which businesses or creators you want (kinds, cities, niches).
3. Section **5**: your sending email. For Gmail create an **app password** (Google Account → Security → 2-Step Verification → App passwords). It is saved only on your computer in `data/.secrets/`. Fill the **footer** (your name, company, postal address): it is mandatory for live sending.
4. Press **Δοκιμή τώρα**. It finds real leads and writes real emails but **sends nothing**. Read them in the tabs «Επαφές» and «Emails» (drafts are also in `data/outbox/`).
5. Press **Στείλε δοκιμαστικό email στον εαυτό μου**, then **Ενεργοποίηση κανονικής αποστολής**. Press **Καθημερινό πρόγραμμα** so it runs by itself.

## Controls
- **Tell it what to do, in your own words:** dashboard tab «Εντολές» (or say it in a Claude Code / Codex chat in this folder). For example "write to info@someshop.gr about our new service" or "find 15 physiotherapists in Athens with a website and add them to my leads" or "find 10 creators with their own skincare brand and write to them about a collaboration". Same limits apply.
- **Pause everything:** create an empty file `data/STOP` (or press «Παύση»). To resume, delete it.
- **Run something now:** `scripts\run.ps1 -Task outreach|inbox|orders` (or `scripts/run.sh <task>`).
- **Uninstall:** `scripts\uninstall.ps1` (Windows).

## Limits (default)
| | Default | Hard cap (cannot be raised) |
|---|---|---|
| Emails per day (first emails + follow-ups + replies) | 30 | 100 |
| First 14 days | half of the above | |
| Delay between real sends | 45–120 s, random | |

A new mailbox that suddenly sends 100 cold emails a day goes to spam. Stay at 30 or lower for a fresh address. The report warns you when the reply rate drops below 2% or the bounce rate rises above 5%: fix the targeting or the message before you send more.

## ⚠️ Read this first
- **Laws.** Unsolicited commercial email is regulated. In the EU (ePrivacy + GDPR) and in Greece (Law 3471/2006) consent rules may apply even to business addresses; in the US the CAN-SPAM Act requires a postal address and an opt-out. The tool adds your footer and an opt-out line and blocks anyone who says no, but **you are responsible** for the outreach. Prefer company addresses (info@, hello@) over personal ones. If unsure, ask a lawyer.
- **Deliverability.** Use a mailbox on your own domain if you can, with SPF/DKIM set up. Do not use your main personal address for a first test of cold outreach.
- **Maps data.** The free OpenStreetMap data has fewer small businesses than Google Maps. With a Google Places API key (official, pay-as-you-go, there is a free monthly credit) you get far more results.
- **AI.** Emails are written by AI from public information. If a recipient asks, the agent does not deny it.

## Where to look
| File | What's in it |
|---|---|
| `data/hot_leads.md` | **People who replied.** Check it daily. |
| `data/reports/<date>.md` | Daily numbers, reply rate, bounce rate, warnings |
| `data/leads.csv` | Every lead with fit score, hook and status |
| `data/activity_log.csv` | Every email with the exact text |
| `data/outbox/` | Draft emails written in test mode |
| `data/runs/` | Full agent log of each run |

## Troubleshooting
- **"Λάθος κωδικός"** on the test email → use an app password, not your normal password; for Outlook/Microsoft 365 SMTP auth may be disabled by the admin.
- **Nothing happens at the scheduled time** → Windows: open Task Scheduler → `EmailAutopilot` and check *Last Run Result*. Mac: `crontab -l`.
- **The map search returns few results** → try a broader business type, another city spelling, or add a Google Places key.
- **Codex runs can't reach the web** → in `scripts/run.ps1` / `run.sh`, replace `--full-auto` with `--dangerously-bypass-approvals-and-sandbox`. Only do this in this folder.

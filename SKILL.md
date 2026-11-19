---
name: email-autopilot
description: Runs outreach by email, locally: finds businesses (maps and websites) and creators with brands that match the user's filters, writes personalized emails, sends them within safe limits, reads replies and reports. Use when the user wants to automate cold email outreach or lead generation, or to install, configure, run, pause or check Email Autopilot.
---

# Email Autopilot (agent skill)

A local, agent-driven email outreach workflow. The folder this file sits in is the whole product: rules, routines, a safety guard, a lead finder, a mailer and a dashboard.
It works with any agent that can read files and run shell commands (Claude Code, Codex, and others). The rules live in `AGENTS.md` (Claude reads `CLAUDE.md`, which includes it).

## Decide what the user wants

| The user says | You do |
|---|---|
| "install / set up Email Autopilot" | Follow `AGENT-INSTALL.md` exactly. |
| `setup`, "configure it", "change my target customers" | Run the routine in `prompts/setup.md` (interview the user, fill `config.yaml`). |
| `outreach` / `inbox` | Run the routine in `prompts/<name>.md`, following `AGENTS.md`. |
| "write to <email/site/business>…", "find me N <kind of businesses or creators>…" | The user's own orders. Run `uv run tools/guard.py order-add "<their exact words>"`, then follow `prompts/orders.md`. Dry-run rules and limits still apply. They can also type orders in the dashboard tab "Εντολές". |
| `status`, "how is it going" | `uv run tools/guard.py report` and summarize; also read `data/hot_leads.md`. |
| "pause" / "resume" | Create / delete `data/STOP`. |
| "open the dashboard" | Run `START.bat` (Windows) or `./START.command` (Mac/Linux). |

## Non-negotiable rules (full list in `AGENTS.md`)
1. **Never ask for, type or read the user's email password or API keys.** The user saves them in the dashboard (they go to `data/.secrets/`, which you must not read).
2. **Never switch `outreach.mode` to `live` on your own.** Only when the user clearly asks, after they saw dry-run results.
3. Emails leave only through `tools/mailer.py`, which enforces the limits. Obey every refusal and `data/STOP`.
4. Use only business contact emails that are published publicly. Never guess addresses. Stop on any login failure or bounce spike.
5. Be honest with the user: cold email can hurt their sender reputation, unsolicited-email laws differ by country (consent rules may apply even to businesses in Greece/EU), and they are responsible for what is sent.

## Layout
`config.yaml` the user's settings · `AGENTS.md` operating manual · `prompts/` the routines · `tools/guard.py` limits, kill switch, lead database · `tools/finder.py` maps, web and website contact finder · `tools/mailer.py` sending, inbox · `ui/` local dashboard · `scripts/` scheduler and runners · `data/` everything produced (leads, log, reports, outbox drafts).

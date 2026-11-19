# Routine: inbox (unattended, once a day)

Goal: react to replies, record bounces, send due follow-ups, and write the daily report.

## 1. Pre-flight
Read `config.yaml`. If `data/STOP` exists, the guard reports it: only write the report and end the run.

## 2. Read the mailbox
`uv run tools/mailer.py inbox --days 14`.
If `ok` is false (no mailbox access, or the sender is Resend), say so in the summary, skip steps 3–4 and **skip follow-ups** (you cannot tell who already replied). Do only step 5.

## 3. Bounces and replies
For every message:
- **Bounce** (`is_bounce:true`): for each address in `addresses_in_bounce` that is a lead (`guard.py seen`), run `guard.py bounce <address>`.
- **Automatic reply** (out of office, "this mailbox is not monitored", auto-responder): ignore.
- **Reply from a lead** (match `from` with `guard.py seen <from>` / `lead-list`; a reply from another address at the same company domain counts):
  Classify the last message:
  - **interested** (asks for details, price, a call, says yes): `lead-set <email> --status interested --note "<one-line summary>"`. Append to `data/hot_leads.md` a dated entry with name, email, what they said and a suggested next reply.
    If they asked a direct question you can answer from `config.yaml` (`offer.price`, `offer.faq`, `offer.what`) and the mode is live: answer once with
    `mailer.py send --kind reply --to <email> --subject "Re: <their subject>" --body "<answer, then offer.cta>"` (you may include `offer.link`). Never invent prices or terms.
  - **question / neutral**: `lead-set <email> --status replied`. Add it to `data/hot_leads.md` for the human. Do not auto-reply.
  - **not interested / stop / unsubscribe / hostile**: `guard.py block <email> --reason "<why>"`. Do not reply.
  Every reply stops the follow-up sequence for that lead.

## 4. Follow-ups
If `outreach.followups` > 0: `guard.py lead-list --due-followup`. For each lead:
- `guard.py check`. Stop this step if `ok:false`.
- Read the first email's subject in `data/activity_log.csv`. Write a 1–2 line follow-up that adds new value (no links).
- `mailer.py send --kind followup --to <email> --subject "Re: <first subject>" --body "<text>"`. Obey the result as in outreach step 2. Real send → `guard.py delay`.

## 5. Report
`uv run tools/guard.py report` writes `data/reports/<date>.md`. Then follow "End of every run" in AGENTS.md.

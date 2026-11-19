# Routine: orders (the user's own instructions)

The user types instructions in their own words (in the dashboard tab "Εντολές", or by telling you in chat).
Each is an "order". Orders have priority over automatic prospecting, but they obey **every** hard rule in AGENTS.md and the same daily limit.

## 0. Pre-flight
1. Read `config.yaml`. Run `uv run tools/guard.py order-list`. If there are no pending orders, end the run.
2. `uv run tools/guard.py check`. If `ok:false` you can still do orders of kind B and C (finding leads costs no sends); skip sending.

## 1. For each pending order, oldest first
Read the text and decide which kind it is. It can be in Greek or English.

**A. Specific recipients** (an email address, a website, or a business/person name), with or without a note about what to say.
For each recipient:
1. Resolve the email: if the user gave one, use it. If you have a website, run `finder.py site <url>` and take the best published address. If you only have a name, find the official website with a web search, then `finder.py site`. Ambiguous or nothing published → `order-done ID --status skipped --result "which one? <candidates>" / "no public email found"`. Never guess an address.
2. `guard.py seen <email>`. Blocked → skip with "blocked: said no before". Contacted before → do not send a first email again, skip with the reason.
3. Add to the lead list if missing (`lead-add`, `--source order`, score what you see, `hook` = the user's reason or a real detail from their site).
4. Write the email following the user's note (angle, topic, tone, offer) and the writing style in AGENTS.md.
   If the note and the rules conflict (a fake claim, a link in the first email, sensitive targeting), follow the rules and say so in the result.
5. `mailer.py send --to .. --subject .. --body ..` and obey the result. Real send → `guard.py delay`.

**B. Find leads** ("find 10 dentists in Thessaloniki with a website", "find 10 creators with their own skincare brand").
Use the user's words as the search instead of `targeting` for this order. Follow step 1a (businesses) or 1b (creators) of `prompts/outreach.md`.
Add as many as asked (default 10), at most. Do not email them unless the order says to ("and write to them"). If it does, treat each as kind A.

**C. Anything else** (a question, a status, "pause", "stop writing to X").
Do what is safe and possible within the rules. For "stop writing to X" use `guard.py block <email or domain>`. If you cannot, say why in the result.

## 2. Close each order
- Sent / added: `guard.py order-done ID --status done --result "<what you did, one or two lines, with the exact subject and text>"`.
- dry_run (nothing sent): `--status drafted --result "<the exact subject and text you would send>"`.
- Could not do it: `--status failed --result "<why>"`.
Never leave an order pending after you handled it. If you ran out of today's limit, leave it pending and say so in the run summary.

## 3. Finish
Follow "End of every run" in AGENTS.md.

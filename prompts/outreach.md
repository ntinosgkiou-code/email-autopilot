# Routine: outreach (unattended)

Goal: keep a pipeline of well-fitting leads with a public business email, and send this run's share of emails within the limits.

## 0. Pre-flight
1. Read `config.yaml`. If `outreach.enabled` is false, end the run.
2. `uv run tools/guard.py check`. If `ok:false`, report the reason and end the run.
3. `uv run tools/mailer.py status`. In dry_run a missing email setup is fine. In live mode, if `configured` is false: `guard.py stop "Email is not configured: <problem>"` and end the run.
4. `uv run tools/guard.py batch`. `this_run` is this run's maximum. Call it `N`.

## 0b. The user's own orders come first
Run `uv run tools/guard.py order-list`. If any are pending, follow `prompts/orders.md` for them now (they spend from the same limit). Then run `batch` again and continue with what is left.

## 1. Make sure the pipeline has leads (do this FIRST)
Count `guard.py lead-list --status new`. If fewer than `2 × N`, prospect. Rotate the combinations between runs so they are not identical every time.

### 1a. Local businesses (`targeting.kinds` contains "businesses")
For each `targeting.businesses` × `targeting.locations` combination:
1. `finder.py maps "<type>" --location "<location>" --limit 30`.
2. For each place: skip it if its name or category matches `exclude_keywords`, or `guard.py seen <website or email>` says contacted or blocked, or it has no website and no email.
3. Get the email: use the map's `email` if present; otherwise run `finder.py site <website>` and take the first email with `same_domain: true` (best ranked). No email found → skip (never guess one).
4. Read `description` and `excerpt` from `finder.py site` (run it even if the map gave an email, you need it for the hook). Score the fit 1 to 10 against `targeting.ideal_customer`.
   Write a `hook`: one concrete, verifiable detail from their site that you will mention (a service, a specialty, a recent announcement, their neighborhood).
5. If the score is at least `targeting.min_fit_score`: `guard.py lead-add --email .. --name .. --company .. --website .. --category .. --location .. --source maps --score N --hook ".."`.

### 1b. Creators with their own brand (`targeting.kinds` contains "creators")
For each `targeting.creators` niche:
1. Use your web search (or `finder.py search`) with queries like `"<niche>" founder own brand website contact`, `"<niche>" creator shop collaborations email`. Look for people who clearly run their own brand or shop (they sell something, have a brand site), not just an account.
2. Open the brand's website with `finder.py site <url>`. Accept only an email published on that site for business, collaboration or press enquiries. No email found → skip (never guess, never DM-scrape).
3. Score, write the hook (a product, a recent launch, their brand story), `guard.py lead-add ... --source creator`.

Stop prospecting once you have added `2 × N` leads, or after reading about 40 websites in this run.

## 2. Send the emails (spend N)
1. `guard.py lead-list --status new --limit N` (highest fit first).
2. For each lead:
   - `guard.py check`. Stop this step if `ok:false`.
   - `guard.py seen <email>`: if contacted or blocked, `lead-set <email> --status skipped` and move on.
   - Re-open `finder.py site <website>` if you need fresh details. Write the subject and body following AGENTS.md and `outreach.message_style`, using the lead's `hook`, `offer` and the lead's language.
   - `mailer.py send --to <email> --subject "<subject>" --body "<body>"`. Read the JSON result:
     - `dry_run:true` or `sent:true`: done. (The mailer already logged it and updated the lead.)
     - `refused:true`: obey the `reason`. A limit, kill switch or work-hours reason → end this step. A lead-specific reason (blocked, bad address, already contacted) → `lead-set <email> --status skipped --note "<reason>"` and continue.
   - If `sent:true` (a real send): run `guard.py delay` before the next email. In dry_run skip the delay.

## 3. Finish
Follow "End of every run" in AGENTS.md.

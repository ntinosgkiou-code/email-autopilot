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

### 1c. Review pain (only if `targeting.review_pain` is true and a Google Places key is saved)
Businesses with MANY bad reviews are the warmest leads when your offer fixes what customers complain about.
1. For each `targeting.businesses` × `targeting.locations`: `finder.py reviews "<type>" --location "<location>" --min-reviews <review_min_reviews> --max-rating <review_max_rating> --min-negative <review_min_negative>`.
   If it returns `ok:false`, skip this step (do not retry more than once, never scrape Google Maps pages).
2. Take only places with `qualifies:true`, highest `pain_score` first. For each: skip if `seen`, excluded, or no website; get the email as in 1a.
3. Read `bad_sample_reviews` and decide what customers actually ask for or say is missing. Write `--pain "<one sentence, paraphrased>"` (e.g. "several reviews mention phone calls going unanswered and long waits for an appointment").
   Only write what the sample supports (`evidence: strong` = 2+ bad reviews with text). With `weak` or `none`, write `--pain ""` and use an ordinary hook: the low rating alone is not something you may claim a reason for.
4. Only keep the lead if the pain is something the user's `offer` genuinely helps with (score the fit against `ideal_customer` AND the pain). Otherwise skip it.
5. `guard.py lead-add ... --source reviews --pain "<sentence>" --hook "<site detail>"`. In the email, mention the pattern gently and honestly ("a few customers mention …"), after the site-specific detail. Never quote or name a reviewer, never say "your customers hate you", never make fun of the rating, never claim you read "all" reviews.

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

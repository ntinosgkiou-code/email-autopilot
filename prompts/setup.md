# Routine: setup (interactive, a human is present)

Interview the user and fill `config.yaml`. Speak their language. Ask in **4 short rounds**, a few questions per round, and propose a good default for anything they skip.

1. **You and your offer.** Name, company name, language for emails (or "auto"), a short bio with one proof point, what they sell,
   who it is for, the outcome (push for a number), the call to action they want, the price (or whether it may be discussed), and answers to the 3 questions prospects ask most (into `offer.faq`).
2. **Targets.** Local businesses (which kinds, which cities) and/or creators with their own brand (which niches). Who to exclude, and a plain-words description of the perfect lead (`targeting.ideal_customer`).
   Set `targeting.kinds` accordingly (`["businesses"]`, `["creators"]` or both).
3. **The emails.** Show a 3-line sample in the tone they describe and ask "like this?". Set `outreach.message_style` and follow-ups (0–2).
4. **Sending.** Which email address sends (Gmail, Outlook, a company mailbox, or Resend). Fill `email.from_name`, `email.from_email`, `email.smtp_host`, `email.smtp_user`.
   Ask for their **postal address and company name** and put them in `email.footer` (EU/UK/US law requires them in every commercial email).
   **Never ask for the email password or API key in chat and never write them anywhere.** Tell the user to open the dashboard (START.bat), tab «Ρυθμίσεις», section 5, and paste the app password there. Explain a Gmail app password (Google Account → Security → 2-Step Verification → App passwords).
   Explain the limits: a new mailbox should stay at 30 emails a day or fewer, the first 14 days run at half. Never set `limits.emails_per_day` above 100.
   Also tell them honestly: cold email can land in spam, laws on unsolicited email differ by country (in Greece and much of the EU, consent rules may apply even to businesses), and they are responsible for their outreach.

Then:
- Write `config.yaml`. Keep its exact structure and comments, keep every list on one line, and keep `outreach.mode: "dry_run"`.
- Write 2 sample emails for imaginary leads that match their ideal customer, so they can approve the voice. Adjust until they are happy.
- Tell them the next step: in the dashboard press «Δοκιμή τώρα», check the «Επαφές» and «Emails» tabs, then switch to live.

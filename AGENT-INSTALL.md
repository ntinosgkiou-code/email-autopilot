# Installing Email Autopilot (instructions for an AI agent)

You are an AI agent (Claude Code, Codex, or similar) asked to install this package for a user. Follow these steps in order. Run commands yourself; only the items marked **USER** must be done by the human.
Package folder = the folder containing this file. Call it `$PKG`.

## 0. Tell the user, before anything else
Say this in one short message and continue unless they object:
> Cold email can land in spam and hurt your sender reputation, and laws on unsolicited email differ by country (in Greece and much of the EU, consent rules may apply even to business addresses). You are responsible for what is sent. The tool starts in test mode and sends nothing until you explicitly turn it on.

## 1. Check the machine
- Windows 10/11 (PowerShell 5.1+), macOS, or Linux. Internet access is required.
- Check `uv --version`. If missing: Windows `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"`; Mac/Linux `curl -LsSf https://astral.sh/uv/install.sh | sh`. Then add `~/.local/bin` to PATH for this session.
- Check that one agent CLI exists: `claude --version` or `codex --version`. If none: Claude Code is `irm https://claude.ai/install.ps1 | iex` (Windows) or `curl -fsSL https://claude.ai/install.sh | bash`. It needs the user's own paid Claude plan. **USER** signs in (`claude`, then `/login`).

## 2. Put the package in its permanent place
Preferred: run the installer, which copies the package to `~/email-autopilot` (keeps `config.yaml` and `data/` on updates), registers the skill for the agents found and creates a desktop shortcut:
- Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "$PKG\install.ps1" -Yes -NoLaunch`
- Mac/Linux: `bash "$PKG/install.sh" --yes --no-launch`

Add `-Agent claude|codex|both` (`--agent`) to choose which agent to register (default: every agent CLI found).
Other agents: nothing to register. Point them at `SKILL.md` / `AGENTS.md` in the install folder. No MCP server is needed: the tools are plain Python run with `uv run`.

## 3. Configure
Either open the dashboard (`START.bat` / `./START.command`) and let the user fill the **Settings** forms, or run the `setup` routine in `prompts/setup.md` yourself (interview, then edit `config.yaml`). Keep `outreach.mode: "dry_run"`.
**USER** pastes their email app password (and optional Google Maps key) into the dashboard, tab Ρυθμίσεις. **Never ask for, type or read passwords or API keys.**

## 4. Schedule
Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -ScheduleOnly`. Mac/Linux: `bash scripts/setup.sh` (installs cron entries). This creates the daily runs. They do nothing in dry-run mode.

## 5. Verify (do all, report results honestly)
1. `uv run tools/guard.py check` returns JSON with `"mode": "dry_run"`.
2. `uv run tools/finder.py maps "dentist" --location "Thessaloniki, Greece" --limit 3` returns places.
3. Dry-run: `powershell -File scripts\run.ps1 -Task outreach -Force` (or `EA_FORCE=1 bash scripts/run.sh outreach`). When it finishes, `data/leads.csv` has leads, `data/activity_log.csv` has drafts with `mode=dry_run` and `data/outbox/` has the draft emails. Nothing was sent.
4. Show the user 2–3 of the drafted emails and ask if the tone is right. Adjust `outreach.message_style` if not.

## 6. Going live. **USER decides**
Only if the user clearly says to start sending: first check `email.footer` has their name, company and postal address, then set `outreach.mode: "live"` (or use the dashboard button). Remind them that the first 14 days run at half the daily limit. Test sending first with the dashboard button «Στείλε δοκιμαστικό email στον εαυτό μου».

## Daily operation
Runs happen by themselves. The user checks `data/hot_leads.md` (people who replied) and answers those personally. `data/STOP` pauses everything. Problems show up in `data/ALERT.txt` and on the dashboard.

## If something fails
`data/ui.log` (dashboard), `data/runs/*.log` (each run), `data/ALERT.txt` (last problem). Never retry past a login failure or a bounce spike: stop and tell the user.

#!/usr/bin/env bash
# Email Autopilot: macOS/Linux setup.  Run:  bash scripts/setup.sh [claude|codex]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
ask() { read -r -p "$1 [Y/n] " a; [[ ! "$a" =~ ^[Nn] ]]; }

echo "[1/4] uv"
if ! command -v uv >/dev/null; then
  ask "uv is not installed. Install it from astral.sh (~20 MB)?" || { echo "uv is required"; exit 1; }
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[2/4] Agent"
AGENT="${1:-}"
if [ -z "$AGENT" ]; then
  if command -v claude >/dev/null && command -v codex >/dev/null; then
    read -r -p "Use (1) Claude Code or (2) Codex? [1/2] " c; [ "$c" = "2" ] && AGENT=codex || AGENT=claude
  elif command -v claude >/dev/null; then AGENT=claude
  elif command -v codex >/dev/null; then AGENT=codex
  else echo "Install Claude Code or Codex first, sign in, then re-run."; exit 1; fi
fi
mkdir -p data && echo "$AGENT" > data/.agent

echo "[3/4] Scheduling (cron)"
SCHED="$(uv run --quiet tools/guard.py schedule)"
j() { printf '%s' "$SCHED" | uv run --quiet python -c "import json,sys;d=json.load(sys.stdin);v=d['$1'];print(' '.join(v) if isinstance(v,list) else v)"; }
dnum() { case "$1" in Sun) echo 0;; Mon) echo 1;; Tue) echo 2;; Wed) echo 3;; Thu) echo 4;; Fri) echo 5;; Sat) echo 6;; esac; }
days() { local out=""; for d in $1; do out="$out,$(dnum "$d")"; done; echo "${out#,}"; }
WD="$(days "$(j work_days)")"
LINES=""
for t in $(j outreach_runs); do LINES="$LINES${t#*:} ${t%%:*} * * $WD bash \"$ROOT/scripts/run.sh\" outreach\n"; done
t="$(j inbox_run)"; LINES="$LINES${t#*:} ${t%%:*} * * $WD bash \"$ROOT/scripts/run.sh\" inbox\n"
TZLINE="CRON_TZ=$(grep -E '^\s*timezone:' config.yaml | sed -E 's/.*"(.*)".*/\1/')"
( crontab -l 2>/dev/null | sed '/# >>> email-autopilot/,/# <<< email-autopilot/d'
  printf '# >>> email-autopilot\n%s\n%b# <<< email-autopilot\n' "$TZLINE" "$LINES" ) | crontab -
crontab -l | sed -n '/# >>> email-autopilot/,/# <<< email-autopilot/p'

echo "[4/4] Done"
uv run --quiet tools/guard.py report >/dev/null
cat <<EOF

Scheduled. Computer must be on.  Mode = config.yaml (default dry_run: nothing is sent).
  Test now:   bash scripts/run.sh outreach
  Results:    data/reports/  data/leads.csv  data/hot_leads.md  data/runs/
  Go live:    mode: "live"  in config.yaml (and fill the email section)
  Pause:      touch data/STOP
  Uninstall:  crontab -l | sed '/# >>> email-autopilot/,/# <<< email-autopilot/d' | crontab -
EOF

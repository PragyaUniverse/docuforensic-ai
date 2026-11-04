#!/usr/bin/env bash
# Scan the working tree and the whole git history for secrets. Run before every public push.
# Findings are redacted, so running this can't itself print a key.
set -u
cd "$(dirname "$0")/.."

status=0

if command -v gitleaks >/dev/null 2>&1; then
  echo "== gitleaks: full git history =="
  gitleaks git . --redact --no-banner || status=1
  echo "== gitleaks: working tree (ignored files excluded) =="
  tmp="$(mktemp -d)"
  git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' f; do
    [ -f "$f" ] && mkdir -p "$tmp/$(dirname "$f")" && cp "$f" "$tmp/$f"
  done
  gitleaks dir "$tmp" --redact --no-banner || status=1
  rm -rf "$tmp"
else
  echo "gitleaks is not installed; running the fallback grep only" >&2
  status=1
fi

echo "== pattern check: tracked files and history =="
pattern='AIza[0-9A-Za-z_-]{30,}|gsk_[0-9A-Za-z]{20,}|sk-or-[0-9A-Za-z-]{20,}|sk-ant-[0-9A-Za-z-]{20,}|hf_[0-9A-Za-z]{30,}'
if git grep -lE "$pattern" -- ':!tests' >/dev/null 2>&1; then
  echo "POSSIBLE KEY in tracked files:"
  git grep -lE "$pattern" -- ':!tests'
  status=1
fi
if [ -n "$(git log --all -G"$pattern" --oneline -- ':!tests' 2>/dev/null | head -1)" ]; then
  echo "POSSIBLE KEY in history:"
  git log --all -G"$pattern" --oneline -- ':!tests' | head -20
  status=1
fi

echo "== .env must never be tracked =="
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo ".env IS TRACKED"
  status=1
fi
if [ -n "$(git log --all --oneline -- .env 2>/dev/null | head -1)" ]; then
  echo ".env appears in history: revoke any key it held"
  status=1
fi

if [ "$status" -eq 0 ]; then echo "RESULT: clean"; else echo "RESULT: review the output above"; fi
exit "$status"

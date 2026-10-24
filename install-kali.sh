#!/bin/bash
# ============================================================
#  sgpt + adapter — Kali Linux one-click install
#  Run:  chmod +x install-kali.sh && ./install-kali.sh [MODEL]
#  NO default model (v4.3.3): pass one as the argument, or install
#  without one and set it afterwards with:
#        nano ~/.config/shell_gpt/.sgptrc
#  Any provider/model that OpenCode supports can be passed, e.g.
#        ./install-kali.sh opencode/big-pickle
#        ./install-kali.sh openai/gpt-5-mini   (provider connected)
#  Safe to re-run (idempotent). The existing .sgptrc is backed up
#  before it is rewritten. The adapter listens on 127.0.0.1 only.
#  OpenRouter models need OpenRouter connected in OpenCode once
#  (opencode -> /connect); OpenCode's built-in free models need
#  no account at all.
# ============================================================
set -u
DIR="$HOME/.local/share/sgpt-opencode"
BIN="$HOME/.local/bin"
SRC="$(cd "$(dirname "$0")" && pwd)"
MODEL="${1:-}"
# A model argument may be a bare OpenCode free-model id (big-pickle) or a
# full provider/model id (openrouter/recursive/flint-v1.0:free). Only bare
# ids get the opencode/ prefix in opencode commands. No argument means
# NO model: the config gets the placeholder and the user sets it after
# install (the sanity check and live test are skipped, not faked).
if [ -z "$MODEL" ]; then
  FULL_MODEL=""
else
  case "$MODEL" in
    */*) FULL_MODEL="$MODEL" ;;
    *)   FULL_MODEL="opencode/$MODEL" ;;
  esac
fi

echo "==> [1/6] System packages (pipx, curl, python3)"
if ! command -v pipx >/dev/null 2>&1; then
  sudo apt update && sudo apt install -y pipx curl python3
fi
pipx ensurepath >/dev/null 2>&1 || true
export PATH="$BIN:$HOME/.opencode/bin:$PATH"

echo "==> [2/6] OpenCode CLI"
if ! command -v opencode >/dev/null 2>&1 && [ ! -x "$HOME/.opencode/bin/opencode" ]; then
  curl -fsSL https://opencode.ai/install | bash
fi
OC="$(command -v opencode || echo "$HOME/.opencode/bin/opencode")"
echo "    opencode: $("$OC" --version 2>/dev/null | head -1) at $OC"

echo "==> [3/6] SANITY CHECK — selected model (everything else depends on this)"
if [ -z "$FULL_MODEL" ]; then
  echo "    No model given — skipping the sanity check (nothing to test yet)."
  echo "    After install, set your model, then test it with:"
  echo "      opencode run -m <provider/model-id> \"Reply with exactly one word: hello\""
else
  echo "    Model: $FULL_MODEL — waiting up to 3 minutes..."
  case "$FULL_MODEL" in
    openrouter/*) echo "    Note: OpenRouter must be connected in OpenCode (opencode -> /connect -> OpenRouter)." ;;
  esac
  mkdir -p /tmp/sgpt-sanity && cd /tmp/sgpt-sanity || exit 1
  if timeout 180 "$OC" run -m "$FULL_MODEL" "Reply with exactly one word: hello" 2>&1 | tee /tmp/sgpt-sanity-out.txt | grep -qi .; then
    if grep -qi "hello" /tmp/sgpt-sanity-out.txt; then
      echo "    [OK] The free model answered."
    else
      echo "    [WARN] Got output but 'hello' is not clearly in it — see: /tmp/sgpt-sanity-out.txt"
      echo "           Continuing anyway; test it yourself after install (step 6)."
    fi
  else
    echo "    [FAIL] The model did not answer within 3 minutes."
    echo "           Check your internet, or try another model:"
    echo "             ./install-kali.sh opencode/big-pickle"
    echo "           For a provider model (e.g. openrouter/...), connect that"
    echo "           provider in OpenCode first (run: opencode, then /connect)."
    echo "           If it still stays silent, that provider/model is slow or"
    echo "           down right now. This is NOT an adapter problem — the"
    echo "           adapter is not involved yet."
    exit 1
  fi
  cd "$SRC" || exit 1
fi

echo "==> [4/6] ShellGPT — the ORIGINAL package, via pipx (Kali blocks system pip)"
if ! command -v sgpt >/dev/null 2>&1; then
  pipx install shell-gpt
fi
export PATH="$BIN:$PATH"

echo "==> [5/6] Adapter + config"
mkdir -p "$DIR" "$BIN" "$HOME/.config/shell_gpt"
cp "$SRC/adapter.py" "$DIR/adapter.py"
cp "$SRC/sgpt-free" "$BIN/sgpt-free"
# Test/audit helpers live next to the adapter for later re-runs.
# sgpt-audit.sh is MANUAL ONLY — it is copied here so the user can
# run it after choosing a model; it is never executed by this script.
[ -f "$SRC/test_adapter.py" ] && cp "$SRC/test_adapter.py" "$DIR/test_adapter.py"
[ -f "$SRC/sgpt-audit.sh" ] && cp "$SRC/sgpt-audit.sh" "$DIR/sgpt-audit.sh" && chmod +x "$DIR/sgpt-audit.sh"
chmod +x "$DIR/adapter.py" "$BIN/sgpt-free"
if [ -f "$HOME/.config/shell_gpt/.sgptrc" ]; then
  cp "$HOME/.config/shell_gpt/.sgptrc" "$HOME/.config/shell_gpt/.sgptrc.before-install.bak"
  echo "    Backed up existing .sgptrc to .sgptrc.before-install.bak"
fi
# v4.3.4 rule (user's no-default order, enforced): a no-argument
# install NEVER reuses a model from an existing config. The placeholder
# is always written, so a model appears only when the user sets it
# himself in this install (nano ~/.config/shell_gpt/.sgptrc) or passes
# it as an argument. The old file is already backed up above, so
# nothing is lost — the user can copy their previous model from
# .sgptrc.before-install.bak if they want it back.
cat > "$HOME/.config/shell_gpt/.sgptrc" <<EOF
OPENAI_API_KEY=dummy-local
API_BASE_URL=http://127.0.0.1:8642/v1
DEFAULT_MODEL=${FULL_MODEL:-SET_YOUR_MODEL_HERE}
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
REQUEST_TIMEOUT=600
DISABLE_STREAMING=false
EOF
if [ -z "$FULL_MODEL" ]; then
  echo "    No model set: DEFAULT_MODEL=SET_YOUR_MODEL_HERE (placeholder)."
  echo "    Set your own model after install: nano ~/.config/shell_gpt/.sgptrc"
fi
if [ ! -x "$HOME/.opencode/bin/opencode" ] && [ "$OC" != "$HOME/.opencode/bin/opencode" ]; then
  echo "    NOTE: opencode lives at: $OC — export this before starting the adapter: SGPT_OC_BIN=$OC"
fi

echo "==> [6/6] Test your model YOURSELF with sgpt-audit.sh (manual step, not run here)"
echo "    The audit is deliberately NOT run by this installer."
echo "    After you choose a model, run it yourself:"
if [ -z "$FULL_MODEL" ]; then
  echo "      nano ~/.config/shell_gpt/.sgptrc   (set DEFAULT_MODEL first)"
  echo "      bash $DIR/sgpt-audit.sh"
else
  echo "      bash $DIR/sgpt-audit.sh $FULL_MODEL"
  echo "    (or: bash $DIR/sgpt-audit.sh  to test the DEFAULT_MODEL above)"
fi
echo "    It tests every sgpt feature for real with that model and"
echo "    reports PASS/FAIL/SKIP per check. Nothing is executed"
echo "    (the -s interactive probe answers A = Abort)."

cat <<EOF

[DONE] Setup complete. Daily use is a single command:
    sgpt-free "your question"
    sgpt-free -s "show all listening ports"
    sgpt-free -s "show failed SSH logins from the last hour"
    sgpt-free -c "write a simple port scanner in python"
    sgpt-free --repl temp

Notes: openrouter/* models are answered through OpenRouter's API
directly (fast, native). Every other provider/model runs through
'opencode run', which boots per request, so answers are slower
(often 20-60s). The adapter listens on 127.0.0.1 only.
Log: $DIR/adapter.log
ANY provider/model that OpenCode supports can be used: set it in
~/.config/shell_gpt/.sgptrc (DEFAULT_MODEL=provider/model-id, exact
id from 'opencode models') or per command: sgpt-free --model
provider/model-id "...". Full docs: README.md
Test your chosen model any time with:  bash $DIR/sgpt-audit.sh [model]
EOF

#!/usr/bin/env bash
# v4.3.3: NO default model is shipped or forced any more. This script
# installs the new adapter, backs up the current adapter + config, and
# NEVER touches an existing DEFAULT_MODEL line. If .sgptrc is missing
# it is created from the template with the placeholder
# DEFAULT_MODEL=SET_YOUR_MODEL_HERE, which the user then replaces
# with their own model (nano ~/.config/shell_gpt/.sgptrc).
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.local/share/sgpt-opencode"
TARGET="$TARGET_DIR/adapter.py"
CFG="$HOME/.config/shell_gpt/.sgptrc"

if [[ ! -f "$SOURCE_DIR/adapter.py" ]]; then
  echo "ERROR: adapter.py missing beside this script." >&2; exit 1
fi
if ! command -v sgpt >/dev/null 2>&1; then
  echo "ERROR: original ShellGPT 'sgpt' executable was not found." >&2; exit 1
fi
mkdir -p "$TARGET_DIR" "$(dirname "$CFG")"

if [[ -f "$TARGET" && ! -f "$TARGET.before-openrouter-flint-fix.bak" ]]; then
  cp -p "$TARGET" "$TARGET.before-openrouter-flint-fix.bak"
fi
if [[ -f "$CFG" && ! -f "$CFG.before-openrouter-flint-fix.bak" ]]; then
  cp -p "$CFG" "$CFG.before-openrouter-flint-fix.bak"
fi
install -m 0644 "$SOURCE_DIR/adapter.py" "$TARGET"
# The audit travels with the upgrade (copied, never executed here —
# the user runs it after choosing a model).
if [[ -f "$SOURCE_DIR/sgpt-audit.sh" ]]; then
  install -m 0755 "$SOURCE_DIR/sgpt-audit.sh" "$TARGET_DIR/sgpt-audit.sh"
fi

python3 - "$CFG" <<'PY'
from pathlib import Path
import re, sys
path = Path(sys.argv[1])
text = path.read_text() if path.exists() else ""
# Non-model settings only. DEFAULT_MODEL is NEVER overwritten: if the
# line already exists it stays exactly as the user set it; only a
# missing line gets the placeholder the user must replace.
settings = {
    "OPENAI_API_KEY": "dummy-local",
    "API_BASE_URL": "http://127.0.0.1:8642/v1",
    "USE_LITELLM": "false",
    "REQUEST_TIMEOUT": "600",
    "DISABLE_STREAMING": "false",
}
for name, value in settings.items():
    pattern = rf"(?m)^{re.escape(name)}=.*$"
    if re.search(pattern, text):
        text = re.sub(pattern, lambda _: f"{name}={value}", text)
    else:
        text = text.rstrip() + f"\n{name}={value}\n"
if not re.search(r"(?m)^DEFAULT_MODEL=", text):
    text = text.rstrip() + "\nDEFAULT_MODEL=SET_YOUR_MODEL_HERE\n"
path.write_text(text.rstrip() + "\n")
PY

python3 -m py_compile "$TARGET"
# Validate key access without displaying it.
python3 - "$TARGET" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sgpt_adapter_check", sys.argv[1])
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
spec.loader.exec_module(module)
key, source = module._find_openrouter_key()
if key:
    if len(key) < 8:
        raise SystemExit("OpenRouter credential exists but looks too short")
    print(f"[PASS] OpenRouter credential found via {source} (secret not displayed)")
else:
    print("[WARN] No readable OpenRouter credential found in env / OpenCode auth.json /")
    print("       OpenCode config / credential database. This is NOT fatal: the adapter")
    print("       will serve openrouter/* models through the OpenCode CLI route (the")
    print("       way the working v2 setup ran) until a readable API key exists.")
    print("       For the fast direct route: opencode -> /connect -> OpenRouter (API key),")
    print("       or start the adapter with OPENROUTER_API_KEY set.")
PY

pkill -f '[a]dapter.py' >/dev/null 2>&1 || true
sleep 1
nohup python3 "$TARGET" >"$TARGET_DIR/adapter.log" 2>&1 </dev/null &
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8642/health > /tmp/sgpt-openrouter-health.json 2>/dev/null; then break; fi
  sleep 1
done
python3 - /tmp/sgpt-openrouter-health.json <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"ERROR: adapter health check failed: {exc}")
if data.get("status") != "ok":
    raise SystemExit(f"ERROR: wrong adapter process/config: {data}")
print("[PASS] Adapter online")
PY

# Report the user's own model status (never set or changed here).
CURRENT_MODEL="$(grep -E '^DEFAULT_MODEL=' "$CFG" 2>/dev/null | head -1 | cut -d= -f2-)"
if [[ -n "${CURRENT_MODEL:-}" && "$CURRENT_MODEL" != "SET_YOUR_MODEL_HERE" ]]; then
  printf '[PASS] Your configured model is unchanged: %s\n' "$CURRENT_MODEL"
else
  cat <<'EOF'
[INFO] No model configured yet. Set your own model first:
         nano ~/.config/shell_gpt/.sgptrc
       then set DEFAULT_MODEL to an exact id from 'opencode models',
       e.g. DEFAULT_MODEL=opencode/beam-free
       See README.md section 8 for every provider: where the free
       model names come from and how to write them.
EOF
fi

cat <<'EOF'

Adapter updated and ready.
Now run the full test script:
EOF
printf 'Test your chosen model yourself (manual, after setting it): bash "%s/sgpt-audit.sh" [model]\n' "$TARGET_DIR"
printf 'Backups: %s/adapter.py.before-openrouter-flint-fix.bak and %s.before-openrouter-flint-fix.bak\n' "$TARGET_DIR" "$CFG"

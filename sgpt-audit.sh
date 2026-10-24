#!/usr/bin/env bash
# sgpt-audit.sh — verify the CURRENT sgpt + adapter setup end to end.
#
# Unlike the earlier Flint audit, this script does NOT reconfigure
# anything: it tests the model already set as DEFAULT_MODEL in
# ~/.config/shell_gpt/.sgptrc (override with: ./sgpt-audit.sh MODEL_ID).
# Interactive features are tested through a real PTY (pseudo-terminal),
# because sgpt reads its E/M/D/A prompt and REPL input from /dev/tty —
# piping an answer into stdin does NOT work (piped stdin becomes part
# of the prompt instead). The shell test ABORTS the generated command;
# nothing is executed except the harmless --no-interaction print check
# (that mode only prints the command, it never runs it).
set +e

CFG="$HOME/.config/shell_gpt/.sgptrc"
ADAPTER="$HOME/.local/share/sgpt-opencode/adapter.py"
ADAPTER_DIR="$HOME/.local/share/sgpt-opencode"
LOG="$ADAPTER_DIR/adapter.log"
AUDIT_DIR="$(mktemp -d /tmp/sgpt-audit.XXXXXX)"
TS="$(date +%s)"
PASS=0; FAIL=0; SKIP=0

pass() { printf '[PASS] %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '[FAIL] %s\n' "$1"; FAIL=$((FAIL+1)); }
skip() { printf '[SKIP] %s\n' "$1"; SKIP=$((SKIP+1)); }
note() { printf '[NOTE] %s\n' "$1"; }

# Self-heal: if one live probe times out, a stuck backend request can be
# holding the adapter's single request gate. Restart the adapter so the
# remaining tests still run against a clean state.
restart_adapter() {
  fuser -k 8642/tcp >/dev/null 2>&1
  sleep 1
  sgpt-free --version >/dev/null 2>&1
  local i
  for i in $(seq 1 20); do
    if curl -s --max-time 3 http://127.0.0.1:8642/health >/dev/null 2>&1; then
      note "adapter restarted OK"
      return 0
    fi
    sleep 1
  done
  note "adapter did not come back after restart - later live tests may fail"
}

MODEL="${1:-}"
if [ -z "$MODEL" ] && [ -f "$CFG" ]; then
  MODEL="$(grep -E '^DEFAULT_MODEL=' "$CFG" | head -1 | cut -d= -f2-)"
fi

printf '%s\n' '========================================' ' SGPT + adapter audit (current setup)' '========================================'
printf 'Model under test: %s\n' "${MODEL:-<none found in .sgptrc>}"
printf 'Audit logs: %s\n\n' "$AUDIT_DIR"

if ! command -v sgpt-free >/dev/null 2>&1 || ! command -v sgpt >/dev/null 2>&1; then
  fail 'sgpt-free / sgpt executable'; echo 'Install the package first (see README).'; exit 1
fi
if [ ! -f "$ADAPTER" ]; then fail "Adapter not found: $ADAPTER"; exit 1; fi
if [ -z "$MODEL" ]; then fail 'DEFAULT_MODEL not set in .sgptrc'; exit 1; fi
if [ "$MODEL" = "SET_YOUR_MODEL_HERE" ]; then
  fail 'DEFAULT_MODEL is still the placeholder SET_YOUR_MODEL_HERE'
  echo 'This package ships NO default model. Set your own first:'
  echo '  nano ~/.config/shell_gpt/.sgptrc   (DEFAULT_MODEL=provider/model-id)'
  echo 'Use an exact id from: opencode models  (see README.md section 8)'
  exit 1
fi

python3 -m py_compile "$ADAPTER" >"$AUDIT_DIR/syntax.log" 2>&1
if [ $? -eq 0 ]; then pass 'Adapter Python syntax'; else fail 'Adapter Python syntax'; cat "$AUDIT_DIR/syntax.log"; exit 1; fi

# Offline unit tests (mocked backends): routing, role/parameter/tool
# forwarding, sanitizers, SSE shape. No API quota is spent on these.
TEST_FILE=""
for cand in "$(dirname "$0")/test_adapter.py" "$ADAPTER_DIR/test_adapter.py" "./test_adapter.py"; do
  if [ -f "$cand" ]; then TEST_FILE="$cand"; break; fi
done
if [ -n "$TEST_FILE" ]; then
  if (cd "$(dirname "$TEST_FILE")" && python3 -m unittest test_adapter) >"$AUDIT_DIR/unit.log" 2>&1; then
    pass "Adapter unit tests ($(basename "$TEST_FILE"); routing/forwarding/sanitizers/SSE)"
  else
    fail "Adapter unit tests (log=$AUDIT_DIR/unit.log)"; tail -n 15 "$AUDIT_DIR/unit.log"
  fi
else
  skip 'Adapter unit tests (test_adapter.py not found next to the audit, in the install dir, or in the current folder)'
fi

# Restart the adapter so the audit tests the adapter.py currently
# installed on disk (not an older copy still running from before).
fuser -k 8642/tcp >/dev/null 2>&1 || true
sleep 1

# Make sure the adapter is up (sgpt-free starts it if needed).
sgpt-free --version >"$AUDIT_DIR/version.log" 2>&1
if [ $? -eq 0 ]; then pass 'CLI --version'; else fail 'CLI --version'; fi
for _ in $(seq 1 15); do
  if curl -fsS --max-time 2 http://127.0.0.1:8642/health >/dev/null 2>&1; then break; fi
  sleep 1
done
if curl -fsS --max-time 3 http://127.0.0.1:8642/health >/dev/null 2>&1; then
  pass 'Adapter health endpoint'
else
  fail 'Adapter health endpoint'; tail -n 20 "$LOG"; exit 1
fi
if curl -fsS --max-time 3 http://127.0.0.1:8642/v1/models >"$AUDIT_DIR/models.json" 2>/dev/null; then
  if grep -Fq "$MODEL" "$AUDIT_DIR/models.json"; then
    pass '/v1/models advertises the configured model'
  else
    pass '/v1/models endpoint OK (configured model is passed through; static list does not contain it)'
  fi
else
  fail '/v1/models endpoint'
fi

sgpt-free --help >"$AUDIT_DIR/help.log" 2>&1
if [ $? -eq 0 ]; then pass 'CLI --help'; else fail 'CLI --help'; fi
for flag in --shell --code --describe-shell --chat --repl --editor --model --temperature --top-p --cache --no-cache --md --no-md --interaction --no-interaction --functions --no-functions --role --create-role --show-role --list-roles --show-chat --list-chats; do
  if grep -Fq -- "$flag" "$AUDIT_DIR/help.log"; then pass "Option recognized in help: $flag"; else fail "Option listed in help: $flag"; fi
done

# PTY driver: ptyrun.py TIMEOUT "WAIT=>SEND" ... -- command...
cat > "$AUDIT_DIR/ptyrun.py" <<'PY'
import os, pty, select, sys, time
timeout = int(sys.argv[1]); steps = []
i = 2
while sys.argv[i] != "--":
    w, _, s = sys.argv[i].partition("=>")
    steps.append((w, s.encode().decode("unicode_escape")))
    i += 1
cmd = sys.argv[i + 1:]
pid, fd = pty.fork()
if pid == 0:
    os.execvp(cmd[0], cmd)
out = b""; deadline = time.time() + timeout; idx = 0; rc = None
while time.time() < deadline:
    r, _, _ = select.select([fd], [], [], 0.5)
    if fd in r:
        try: data = os.read(fd, 4096)
        except OSError: data = b""
        if data: out += data
    if idx < len(steps) and steps[idx][0].encode() in out:
        if steps[idx][1]: os.write(fd, steps[idx][1].encode())
        idx += 1
    w, status = os.waitpid(pid, os.WNOHANG)
    if w == pid:
        rc = os.waitstatus_to_exitcode(status); break
if rc is None:
    try: os.kill(pid, 9)
    except ProcessLookupError: pass
    os.waitpid(pid, 0)
sys.stdout.buffer.write(out)
sys.exit(0 if rc == 0 else 1)
PY

probe() {
  local name="$1" expected="$2" logfile="$3"; shift 3
  local tmo="${PROBE_TIMEOUT:-150}"
  timeout "$tmo" "$@" >"$logfile" 2>&1
  local rc=$?
  if [ "$rc" -eq 0 ] && grep -Fq -- "$expected" "$logfile"; then
    pass "$name"
  else
    fail "$name (exit=$rc; log=$logfile)"
    tail -n 8 "$logfile" | sed 's/[[:cntrl:]]//g'
    if [ "$rc" -eq 124 ]; then
      note "probe timed out - restarting the adapter to clear any stuck request, then continuing"
      restart_adapter
    fi
  fi
}

# Same as probe(), but the expected string is an extended regex (grep -E).
# Used where several output forms are equally correct - e.g. a generated
# echo command is right with double quotes, single quotes, or no quotes
# around the text; all three forms must pass.
probe_re() {
  local name="$1" expected="$2" logfile="$3"; shift 3
  local tmo="${PROBE_TIMEOUT:-150}"
  timeout "$tmo" "$@" >"$logfile" 2>&1
  local rc=$?
  if [ "$rc" -eq 0 ] && grep -Eq -- "$expected" "$logfile"; then
    pass "$name"
  else
    fail "$name (exit=$rc; log=$logfile)"
    tail -n 8 "$logfile" | sed 's/[[:cntrl:]]//g'
    if [ "$rc" -eq 124 ]; then
      note "probe timed out - restarting the adapter to clear any stuck request, then continuing"
      restart_adapter
    fi
  fi
}

printf '\n%s\n' '--- Live model-backed modes (may take time; free-tier limits apply) ---'
probe 'Normal chat response' 'SGPT_CHAT_OK' "$AUDIT_DIR/chat.log" \
  sgpt-free --no-cache --model "$MODEL" 'Reply with exactly this token and nothing else: SGPT_CHAT_OK'
probe 'Code generation (-c)' 'SGPT_CODE_OK' "$AUDIT_DIR/code.log" \
  sgpt-free --no-cache --model "$MODEL" -c 'Return only Python code that prints exactly SGPT_CODE_OK'
probe 'Describe shell (-d)' 'SGPT_DESCRIBE_OK' "$AUDIT_DIR/describe.log" \
  sgpt-free --no-cache --model "$MODEL" -d "echo SGPT_DESCRIBE_OK"

CHAT_ID="audit$TS"
PROBE_TIMEOUT=240
probe "Chat session (--chat $CHAT_ID)" 'SGPT_CHATMODE_OK' "$AUDIT_DIR/chat-mode.log" \
  sgpt-free --no-cache --model "$MODEL" --chat "$CHAT_ID" 'Reply with exactly this token and nothing else: SGPT_CHATMODE_OK'
unset PROBE_TIMEOUT
sgpt-free --show-chat "$CHAT_ID" >"$AUDIT_DIR/show-chat.log" 2>&1
if [ $? -eq 0 ] && grep -Fq 'SGPT_CHATMODE_OK' "$AUDIT_DIR/show-chat.log"; then
  pass '--show-chat shows the session'
else
  fail '--show-chat shows the session'
fi
rm -f "${TMPDIR:-/tmp}/chat_cache/$CHAT_ID" 2>/dev/null

# Shell mode, print-only check (never executes: --no-interaction only prints).
# The generated command may quote the text or not - all forms are correct.
PROBE_TIMEOUT=240
probe_re 'Shell generation (-s --no-interaction, print only)' "echo[[:space:]]+[\"']?SGPT_SHELL_OK[\"']?" "$AUDIT_DIR/shell-print.log" \
  sgpt-free --no-cache --model "$MODEL" -s --no-interaction \
  'Return exactly one harmless shell command that prints SGPT_SHELL_OK using echo. No explanation.'
unset PROBE_TIMEOUT

# Shell mode, interactive prompt through a PTY; answer 'a' = Abort (no execution).
timeout 260 python3 "$AUDIT_DIR/ptyrun.py" 240 \
  "[A]bort=>a\n" -- \
  sgpt-free --no-cache --model "$MODEL" -s \
  'Return exactly one harmless shell command that prints SGPT_SHELL_OK using echo. No explanation.' \
  >"$AUDIT_DIR/shell-pty.log" 2>&1
if [ $? -eq 0 ] && grep -Eq "echo[[:space:]]+[\"']?SGPT_SHELL_OK[\"']?" "$AUDIT_DIR/shell-pty.log"; then
  pass 'Shell interactive E/M/D/A prompt (PTY, aborted)'
else
  fail "Shell interactive E/M/D/A prompt (PTY; log=$AUDIT_DIR/shell-pty.log)"
  tail -n 8 "$AUDIT_DIR/shell-pty.log" | sed 's/[[:cntrl:]]//g'
fi

# REPL through a PTY: ask a question, expect the token, then Ctrl+C.
timeout 260 python3 "$AUDIT_DIR/ptyrun.py" 240 \
  ">>>=>Reply with exactly this token and nothing else: SGPT_REPL_OK\n" \
  "SGPT_REPL_OK=>\x03" -- \
  sgpt-free --model "$MODEL" --repl "auditrepl$TS" \
  >"$AUDIT_DIR/repl-pty.log" 2>&1
if grep -Fq 'SGPT_REPL_OK' "$AUDIT_DIR/repl-pty.log"; then
  pass 'REPL interactive session (PTY)'
else
  fail "REPL interactive session (PTY; log=$AUDIT_DIR/repl-pty.log)"
  tail -n 8 "$AUDIT_DIR/repl-pty.log" | sed 's/[[:cntrl:]]//g'
fi
rm -f "${TMPDIR:-/tmp}/chat_cache/auditrepl$TS" 2>/dev/null

probe 'CLI parses --temperature/--top-p/--no-md' 'SGPT_FLAGS_OK' "$AUDIT_DIR/flags.log" \
  sgpt-free --no-cache --no-md --temperature 0 --top-p 1 --model "$MODEL" \
  'Reply with exactly this token and nothing else: SGPT_FLAGS_OK'
case "$MODEL" in
  openrouter/*)
    note '--temperature/--top-p are forwarded natively to OpenRouter on this route (verified in the adapter unit tests).' ;;
  *)
    note '--temperature/--top-p are accepted by sgpt; on the OpenCode route the adapter cannot forward sampling values (opencode run exposes no sampling flags). Behaviour, not a failure.' ;;
esac

CACHE_TOKEN="SGPT_CACHE_$TS"
probe 'Cache-enabled request (--cache)' "$CACHE_TOKEN" "$AUDIT_DIR/cache.log" \
  sgpt-free --cache --model "$MODEL" "Reply with exactly this token and nothing else: $CACHE_TOKEN"

# --editor through a PTY with a scripted $EDITOR that writes the prompt.
printf '#!/bin/sh\nprintf "Reply with exactly this token and nothing else: SGPT_EDITOR_OK" > "$1"\n' > "$AUDIT_DIR/fake-editor.sh"
chmod +x "$AUDIT_DIR/fake-editor.sh"
EDITOR="$AUDIT_DIR/fake-editor.sh" timeout 260 python3 "$AUDIT_DIR/ptyrun.py" 240 \
  -- sgpt-free --no-cache --model "$MODEL" --editor \
  >"$AUDIT_DIR/editor-pty.log" 2>&1
if grep -Fq 'SGPT_EDITOR_OK' "$AUDIT_DIR/editor-pty.log"; then
  pass '--editor (PTY, scripted editor)'
else
  fail "--editor (PTY; log=$AUDIT_DIR/editor-pty.log)"
  tail -n 8 "$AUDIT_DIR/editor-pty.log" | sed 's/[[:cntrl:]]//g'
fi

# Roles: list/show are read-only; create+show+cleanup uses a throwaway role.
sgpt-free --list-roles >"$AUDIT_DIR/roles.log" 2>&1
if [ $? -eq 0 ]; then pass 'Local --list-roles command'; else fail 'Local --list-roles command'; fi
sgpt-free --list-chats >"$AUDIT_DIR/chats.log" 2>&1
if [ $? -eq 0 ]; then pass 'Local --list-chats command'; else fail 'Local --list-chats command'; fi
ROLE_NAME="AuditRole$TS"
timeout 60 python3 "$AUDIT_DIR/ptyrun.py" 50 \
  "Enter role description=>You answer with very short replies.\n" -- \
  sgpt-free --create-role "$ROLE_NAME" >"$AUDIT_DIR/create-role.log" 2>&1
sgpt-free --show-role "$ROLE_NAME" >"$AUDIT_DIR/show-role.log" 2>&1
if [ $? -eq 0 ] && grep -Fq 'very short replies' "$AUDIT_DIR/show-role.log"; then
  pass '--create-role + --show-role (PTY)'
else
  fail "--create-role + --show-role (PTY; log=$AUDIT_DIR/create-role.log)"
fi
rm -f "$HOME/.config/shell_gpt/roles/$ROLE_NAME.json" 2>/dev/null
probe '--role (built-in ShellGPT role)' 'SGPT_ROLE_OK' "$AUDIT_DIR/role.log" \
  sgpt-free --no-cache --model "$MODEL" --role ShellGPT \
  'Reply with exactly this token and nothing else: SGPT_ROLE_OK'

# Functions: only meaningful when enabled AND at least one function file exists.
FUNC_DIR="$HOME/.config/shell_gpt/functions"
if grep -Eq '^OPENAI_USE_FUNCTIONS=true' "$CFG" 2>/dev/null && ls "$FUNC_DIR"/*.py >/dev/null 2>&1; then
  timeout 150 sgpt-free --no-cache --model "$MODEL" --functions \
    'Reply with exactly this token and nothing else: SGPT_FUNC_OK' \
    >"$AUDIT_DIR/functions.log" 2>&1
  if [ $? -eq 0 ] && ! grep -Fq 'Traceback' "$AUDIT_DIR/functions.log"; then
    pass '--functions request (enabled; no crash, text or tool-call answer)'
  else
    fail "--functions request (log=$AUDIT_DIR/functions.log)"
    tail -n 8 "$AUDIT_DIR/functions.log" | sed 's/[[:cntrl:]]//g'
  fi
else
  skip '--functions: not enabled (set OPENAI_USE_FUNCTIONS=true in .sgptrc and install a function first — see README)'
fi

printf '\n%s\n' '========================================'
printf 'RESULT: %d PASS | %d FAIL | %d SKIP\n' "$PASS" "$FAIL" "$SKIP"
printf 'Logs: %s\n' "$AUDIT_DIR"
printf 'Adapter log: %s\n' "$LOG"
printf '%s\n' '========================================'

#!/usr/bin/env bash
# ============================================================
#  sgpt-free / sgpt-f — Universal Linux Installer
#  Works on ANY Linux (Ubuntu, Debian, Kali, Arch, Fedora,
#  RHEL/Rocky/Alma, openSUSE, Alpine, WSL, etc.)
#
#  Usage:
#    chmod +x install.sh
#    ./install.sh                              # Install (configure later via sgpt-free --setup)
#    ./install.sh --colab <NGROK_URL> [MODEL]  # Install + connect to Colab immediately
#    ./install.sh --colab-only                 # Install without OpenCode CLI
#    ./install.sh --opencode <MODEL>           # Install + set OpenCode/OpenRouter model
#    ./install.sh <MODEL>                      # Shorthand for --opencode <MODEL>
# ============================================================
set -u

DIR="$HOME/.local/share/sgpt-opencode"
BIN="$HOME/.local/bin"
CFG_DIR="$HOME/.config/shell_gpt"
CFG="$CFG_DIR/.sgptrc"
SRC="$(cd "$(dirname "$0")" && pwd)"

MODE=""
COLAB_URL=""
MODEL=""
SKIP_OPENCODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --colab)
      MODE="colab"
      COLAB_URL="${2:-}"
      MODEL="${3:-}"
      shift
      [ -n "$COLAB_URL" ] && shift
      [ -n "$MODEL" ] && shift
      ;;
    --colab-only)
      SKIP_OPENCODE=1
      shift
      ;;
    --opencode)
      MODE="opencode"
      MODEL="${2:-}"
      shift
      [ -n "$MODEL" ] && shift
      ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      if [ -z "$MODE" ] && [ -z "$MODEL" ]; then
        MODE="opencode"
        MODEL="$1"
      fi
      shift
      ;;
  esac
done

run_sudo() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    "$@"
  fi
}

echo "==> [1/5] Checking system packages (python3, curl, pipx)"
install_sys_pkgs() {
  if command -v apt-get >/dev/null 2>&1; then
    run_sudo apt-get update -qq && run_sudo apt-get install -y python3 python3-venv curl pipx || true
  elif command -v dnf >/dev/null 2>&1; then
    run_sudo dnf install -y python3 curl pipx || run_sudo dnf install -y python3 python3-pip curl || true
  elif command -v yum >/dev/null 2>&1; then
    run_sudo yum install -y python3 python3-pip curl || true
  elif command -v pacman >/dev/null 2>&1; then
    run_sudo pacman -Sy --noconfirm python python-pipx curl || true
  elif command -v zypper >/dev/null 2>&1; then
    run_sudo zypper --non-interactive install python3 python3-pipx curl || run_sudo zypper --non-interactive install python3 python3-pip curl || true
  elif command -v apk >/dev/null 2>&1; then
    run_sudo apk add --no-cache python3 py3-pip curl bash || true
  else
    echo "    [WARN] Unknown package manager — make sure python3, curl, and pipx/pip are installed."
  fi
}

if ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1 || ! command -v pipx >/dev/null 2>&1; then
  install_sys_pkgs
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required. Please install python3 and re-run." >&2
  exit 1
fi

if command -v pipx >/dev/null 2>&1; then
  pipx ensurepath >/dev/null 2>&1 || true
fi
export PATH="$BIN:$HOME/.opencode/bin:$PATH"

echo "==> [2/5] Installing original ShellGPT (sgpt)"
if ! command -v sgpt >/dev/null 2>&1; then
  if command -v pipx >/dev/null 2>&1; then
    pipx install shell-gpt
  elif python3 -m pip --version >/dev/null 2>&1; then
    python3 -m pip install --user shell-gpt || python3 -m pip install --user --break-system-packages shell-gpt
  else
    echo "ERROR: neither pipx nor pip is available to install shell-gpt." >&2
    exit 1
  fi
fi
if command -v sgpt >/dev/null 2>&1; then
  echo "    [OK] sgpt ready: $(command -v sgpt)"
else
  echo "    [WARN] sgpt was installed, make sure $BIN is in your PATH."
fi

echo "==> [3/5] OpenCode CLI (optional — used for OpenCode / OpenRouter backend)"
if [ "$SKIP_OPENCODE" -eq 1 ]; then
  echo "    Skipped (--colab-only)."
elif command -v opencode >/dev/null 2>&1 || [ -x "$HOME/.opencode/bin/opencode" ]; then
  OC="$(command -v opencode || echo "$HOME/.opencode/bin/opencode")"
  echo "    [OK] opencode already installed: $OC"
else
  if curl -fsSL https://opencode.ai/install | bash; then
    echo "    [OK] opencode installed."
  else
    echo "    [WARN] OpenCode install failed or skipped — Colab backend still works 100%."
  fi
fi

echo "==> [4/5] Installing adapter, sgpt-free, and sgpt-f alias"
mkdir -p "$DIR" "$BIN" "$CFG_DIR"
cp "$SRC/adapter.py" "$DIR/adapter.py"
cp "$SRC/sgpt-free" "$BIN/sgpt-free"
chmod +x "$DIR/adapter.py" "$BIN/sgpt-free"
ln -sf "$BIN/sgpt-free" "$BIN/sgpt-f"

[ -f "$SRC/test_adapter.py" ] && cp "$SRC/test_adapter.py" "$DIR/test_adapter.py"
[ -f "$SRC/sgpt-audit.sh" ] && cp "$SRC/sgpt-audit.sh" "$DIR/sgpt-audit.sh" && chmod +x "$DIR/sgpt-audit.sh"

# Ensure ~/.local/bin is in shell PATH for future terminals
for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [ -f "$rcfile" ] && ! grep -Fq '.local/bin' "$rcfile"; then
    printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rcfile"
    echo "    Added ~/.local/bin to $rcfile"
  fi
done

# Backup existing .sgptrc and point it at the local adapter
if [ -f "$CFG" ]; then
  cp "$CFG" "$CFG.before-install.bak"
  echo "    Backed up existing .sgptrc to $CFG.before-install.bak"
fi

if [ ! -f "$CFG" ]; then
  cat > "$CFG" <<EOF
OPENAI_API_KEY=dummy-local
API_BASE_URL=http://127.0.0.1:8642/v1
DEFAULT_MODEL=SET_YOUR_MODEL_HERE
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
REQUEST_TIMEOUT=600
DISABLE_STREAMING=false
EOF
else
  python3 - "$CFG" <<'PY'
from pathlib import Path
import re, sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace")
settings = {
    "OPENAI_API_KEY": "dummy-local",
    "API_BASE_URL": "http://127.0.0.1:8642/v1",
    "USE_LITELLM": "false",
    "REQUEST_TIMEOUT": "600",
    "DISABLE_STREAMING": "false",
}
for k, v in settings.items():
    pat = rf"(?m)^{re.escape(k)}=.*$"
    if re.search(pat, text):
        text = re.sub(pat, lambda _m, k=k, v=v: f"{k}={v}", text)
    else:
        text = text.rstrip() + f"\n{k}={v}\n"
if not re.search(r"(?m)^DEFAULT_MODEL=", text):
    text = text.rstrip() + "\nDEFAULT_MODEL=SET_YOUR_MODEL_HERE\n"
path.write_text(text.rstrip() + "\n", encoding="utf-8")
PY
fi

echo "==> [5/5] Finalizing backend & restarting local adapter"
"$BIN/sgpt-free" --restart >/dev/null 2>&1 || true

if [ "$MODE" = "colab" ] && [ -n "$COLAB_URL" ]; then
  if [ -n "$MODEL" ]; then
    "$BIN/sgpt-free" --colab "$COLAB_URL" "$MODEL"
  else
    "$BIN/sgpt-free" --colab "$COLAB_URL"
  fi
elif [ "$MODE" = "opencode" ] && [ -n "$MODEL" ]; then
  "$BIN/sgpt-free" --opencode "$MODEL"
fi

cat <<'EOF'

========================================================================
  [DONE] sgpt-free & sgpt-f installed!
========================================================================
  If this is a new terminal, run:   export PATH="$HOME/.local/bin:$PATH"

  NEXT STEPS:
    1) Interactive setup (Colab or OpenCode):
         sgpt-free --setup

    2) Or connect Google Colab in ONE command:
         sgpt-free --colab <NGROK_URL> <MODEL>

    3) Or use OpenCode / OpenRouter:
         sgpt-free --opencode opencode/beam-free

    4) REQUIRED — Run the pre-flight test to verify all features before use:
         sgpt-f --test

    5) See ALL local commands + original sgpt commands:
         sgpt-free --help    (or: sgpt-f --h)

  Short alias: `sgpt-f` works everywhere identically to `sgpt-free`!
========================================================================
EOF

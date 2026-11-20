# sgpt-free (`sgpt-f`) — Free ShellGPT on Any Linux

by UNIT-61398

Run the **original, unmodified** [ShellGPT (`sgpt`)](https://github.com/TheR1D/shell_gpt) for free on **any Linux distribution** (Ubuntu, Debian, Kali, Arch, Fedora, RHEL/Rocky/Alma, openSUSE, Alpine, WSL) using either of two free backends:

1. **Google Colab + Ollama (Free T4 GPU)** — Run **any** Ollama model you want via `colab_sgpt_server.py`, with optional Google Drive model caching so models download only once.
2. **OpenCode / OpenRouter** — Use OpenCode's built-in free models, OpenRouter's direct API, or any provider connected in OpenCode.

Every original ShellGPT feature works on both backends: normal chat, shell command generation (`-s`) with interactive `[E]xecute / [M]odify / [D]escribe / [A]bort`, shell command description (`-d`), code generation (`-c`), persistent chats (`--chat`), interactive REPL (`--repl`), custom roles (`--role`, `--create-role`), function calling (`--functions`), markdown rendering, caching, and `stdin` piping.

Both **`sgpt-free`** and its short alias **`sgpt-f`** work identically.

---

## Does Original ShellGPT (`sgpt`) Need Any Changes?

**No. Zero changes to ShellGPT's source code are required.**

- `install.sh` installs the official upstream `shell-gpt` package directly (via `pipx` or `pip`).
- The `Original SGPT/` folder in this repository is kept **completely untouched** as an upstream reference only — it is not modified or required at runtime.
- The **only** thing changed for original `sgpt` is its standard configuration file (`~/.config/shell_gpt/.sgptrc`), which points ShellGPT at the local adapter (`http://127.0.0.1:8642/v1`) instead of OpenAI's paid API.
- `install.sh` and `sgpt-free` manage `~/.config/shell_gpt/.sgptrc` automatically (and back up any existing `.sgptrc` first). You never need to edit it manually.

For reference, these are the settings written to `~/.config/shell_gpt/.sgptrc`:

```ini
OPENAI_API_KEY=dummy-local
API_BASE_URL=http://127.0.0.1:8642/v1
DEFAULT_MODEL=<your-selected-model>
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
REQUEST_TIMEOUT=600
DISABLE_STREAMING=false
```

---

## Required vs. Optional Files

### Required Files (to install and run on Linux)

| File | Required For | Description |
| :--- | :--- | :--- |
| `install.sh` | Linux install | Universal Linux installer. Installs `sgpt`, copies `adapter.py`, installs `sgpt-free` and the `sgpt-f` symlink, and configures `.sgptrc`. |
| `adapter.py` | Runtime (Linux) | Local OpenAI-compatible HTTP server (`127.0.0.1:8642/v1`). Routes requests to Colab/Ollama or OpenCode/OpenRouter, strips `<think>` / scaffolding tags, sanitizes `-s` and `-c` output, and handles tool calls. |
| `sgpt-free` | Runtime (Linux) | CLI launcher and local configuration manager (also symlinked as `sgpt-f`). Starts `adapter.py` automatically and forwards normal queries to original `sgpt`. |

### Required Only for Google Colab Backend

| File | Required For | Description |
| :--- | :--- | :--- |
| `colab_sgpt_server.py` | Google Colab | Python script you paste into a Google Colab cell (T4 GPU). Installs Ollama, pulls your chosen model, exposes `/v1` over ngrok, optionally caches models in Google Drive, and keeps the server alive. |

### Optional / Testing / Reference Files (not required for daily use)

| File / Folder | Purpose |
| :--- | :--- |
| `sgpt-audit.sh` | End-to-end live feature verification script (`sgpt-free --audit`). |
| `test_adapter.py` | Offline unit test suite (`python3 -m unittest test_adapter -v`). |
| `sgptrc.example` | Example `~/.config/shell_gpt/.sgptrc` template for reference. |
| `Original SGPT/` | Unmodified upstream ShellGPT source archive for reference only (can be omitted when copying to a Linux machine). |
| `LICENSE.txt` | License file. |

---

## How It Works

```text
  sgpt-free / sgpt-f (CLI)
          │
          ├── Local commands (--setup, --colab, --opencode, --set-model, --models, --status, --help)
          │       └── Updates ~/.config/shell_gpt/sgpt-free.json & ~/.config/shell_gpt/.sgptrc
          │
          └── Normal ShellGPT prompts (-s, -c, -d, --chat, --repl, --role, --functions, ...)
                  └── Original `sgpt`
                          └── Local Adapter (http://127.0.0.1:8642/v1)
                                  ├── [colab]    -> Colab Ollama /v1 via ngrok (native tools + JSON shim fallback)
                                  └── [opencode] -> OpenRouter direct API or OpenCode CLI
```

- **Instant config reload:** `adapter.py` reads `~/.config/shell_gpt/sgpt-free.json` dynamically on every request, so switching between Colab and OpenCode or changing the URL takes effect immediately.
- **Loopback only:** `adapter.py` binds exclusively to `127.0.0.1:8642`.
- **Full feature compatibility:**
  - Reasoning tags (`<think>...</think>`) and agent scaffolding tags are stripped before reaching ShellGPT.
  - `-s` (shell) and `-c` (code) outputs are sanitized so markdown fences or commentary never break shell execution.
  - `--functions` uses native OpenAI tool calling on Colab/Ollama and OpenRouter, and automatically falls back to a JSON tool-call shim if an Ollama model (or OpenCode CLI route) does not support native tools.

---

## 1. Installation (Any Linux)

Copy at least `install.sh`, `adapter.py`, and `sgpt-free` (plus `sgpt-audit.sh` and `test_adapter.py` if you want testing) to your Linux machine, then run:

```bash
chmod +x install.sh
./install.sh
```

### Installer Options

| Command | Behavior |
| :--- | :--- |
| `./install.sh` | Full install (original `sgpt` + adapter + `sgpt-free` / `sgpt-f` + OpenCode CLI). |
| `./install.sh --colab-only` | Same as above, but skips installing OpenCode CLI (use if you only want Google Colab). |
| `./install.sh --colab <NGROK_URL> [MODEL]` | Installs everything and connects to your running Colab server immediately. |
| `./install.sh --opencode <MODEL>` | Installs everything and sets an OpenCode/OpenRouter model immediately. |

If `~/.local/bin` is not yet in your current terminal's `PATH`, run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Mandatory Post-Install Check

Right after installing and connecting your backend (Colab or OpenCode below), **always run the pre-flight test** before daily use:

```bash
sgpt-f --test
```

This verifies all 48+ checks (unit tests, adapter health, chat, `-s`, `-s` interactive `[E/M/D/A]`, `-c`, `-d`, `stdin` piping, `--chat`, `--repl`, `--editor`, `--role`, `--cache`, and `--temperature`/`--top-p`). Do not skip this step — it catches offline tunnels, missing PATH entries, or misconfigured models immediately.

---

## 2. Backend A: Google Colab + Ollama (Any Model, Free T4 GPU)

1. Open [Google Colab](https://colab.research.google.com/) and enable a GPU:
   **Runtime → Change runtime type → T4 GPU**.
2. Create a code cell and paste the full contents of [`colab_sgpt_server.py`](colab_sgpt_server.py).
3. Edit only the **CONFIGURATION** section at the top of the script:
   - `MODEL` — Any Ollama model name (tested on T4 15 GB GPU: `"qwen2.5-coder:7b"`, `"qwen3:8b"`, `"llama3.1:8b"`, `"mistral:7b"`, `"gemma3:12b"`, `"gemma3:4b"`, or any other Ollama model).
   - `USE_MODELFILE` / `CUSTOM_MODEL_NAME` / `NUM_CTX` — Set `USE_MODELFILE = True` to build a custom model with your chosen context length (`32768` is safe for 7B–8B models on T4; use `16384` for 12B+ models).
   - `NGROK_TOKEN` — Paste your free authtoken from [dashboard.ngrok.com/authtokens](https://dashboard.ngrok.com/authtokens).
   - `NGROK_DOMAIN` *(optional)* — Paste a free static domain from [dashboard.ngrok.com/domains](https://dashboard.ngrok.com/domains) so your URL never changes between Colab sessions.
   - `USE_GOOGLE_DRIVE` — Set `True` to save downloaded models in Google Drive (`DRIVE_MODELS_DIR`) so you only download them once; set `False` if you don't want to use Drive storage.
   - `UNCENSORED_MODE` / `UNCENSORED_SYSTEM_PROMPT` — Optional custom system prompt (requires `USE_MODELFILE = True`).
   - `KEEP_ALIVE_LOOP = True` — Keeps the Colab cell alive and automatically restarts Ollama or reconnects ngrok if either drops.
4. Run the cell. When ready, it prints a single copy-paste command for your Linux terminal:

```bash
sgpt-free --colab https://xxxx.ngrok-free.app sgpt-ai
```

*(If you omit the model name, `sgpt-free --colab <URL>` automatically fetches `/v1/models` from Colab and selects the active model.)*

---

## 3. Backend B: OpenCode / OpenRouter

Switch to OpenCode or OpenRouter at any time:

```bash
# Built-in OpenCode free model (no account required):
sgpt-free --opencode opencode/beam-free

# Or interactive wizard:
sgpt-free --setup

# List all available OpenCode models:
sgpt-free --models
```

- **OpenCode built-in free models** (e.g., `opencode/beam-free`, `opencode/big-pickle`, `opencode/deepseek-v4.1-flash-free`) work with no API key.
- **OpenRouter models** (e.g., `openrouter/recursive/flint-v1.0:free`) use OpenRouter's fast direct API when `OPENROUTER_API_KEY` is set or OpenRouter is connected in OpenCode (`opencode` → `/connect` → OpenRouter); otherwise they fall back transparently to `opencode run`.

---

## 4. Complete Command Reference

Run **`sgpt-free --help`** (or `sgpt-free --h`, `sgpt-f --h`, `sgpt-f -h`) at any time to display **both** the local management commands and all original `sgpt` options.

### Local Management Commands (`sgpt-free` / `sgpt-f`)

| Command | Description |
| :--- | :--- |
| `sgpt-free --setup` | Interactive setup wizard (choose Colab or OpenCode and select a model). |
| `sgpt-free --colab <URL> [MODEL]` | Switch to Google Colab / Ollama backend and update `.sgptrc`. |
| `sgpt-free --opencode [MODEL]` | Switch to OpenCode / OpenRouter backend. |
| `sgpt-free --set-model <MODEL>` | Change the default model for the active backend. |
| `sgpt-free --models` | List live models from Colab (or `opencode models` + free list). |
| `sgpt-free --status` | Show active backend, default model, Colab URL, functions toggle, and adapter health. |
| `sgpt-free --functions-on` | Enable ShellGPT function calling (`OPENAI_USE_FUNCTIONS=true`). |
| `sgpt-free --functions-off` | Disable ShellGPT function calling (`OPENAI_USE_FUNCTIONS=false`). |
| `sgpt-free --restart` | Restart the local background adapter. |
| `sgpt-free --stop` | Stop the local background adapter. |
| `sgpt-free --logs` | Show the last 60 lines of `~/.local/share/sgpt-opencode/adapter.log`. |
| `sgpt-free --test` / `--audit [MODEL]` | Run the full pre-flight test of all local + original `sgpt` features (`sgpt-audit.sh`). |
| `sgpt-free --help` / `--h` / `-h` | Show all local commands + original `sgpt --help`. |

### Original ShellGPT Features (identical with `sgpt-free` or `sgpt-f`)

```bash
# Normal chat
sgpt-f "explain Linux inodes in 3 lines"

# Generate and interactively run a shell command ([E]xecute, [M]odify, [D]escribe, [A]bort)
sgpt-f -s "show all listening TCP ports with process names"

# Print a shell command without interactive prompt
sgpt-f -s --no-interaction "find files larger than 100MB in /var"

# Describe a shell command
sgpt-f -d "tar -xzvf archive.tar.gz -C /opt"

# Generate code only (no markdown fences)
sgpt-f -c "write a python TCP port scanner"

# Persistent multi-turn chat
sgpt-f --chat dev "I am building a Flask API"
sgpt-f --chat dev "add JWT authentication to it"
sgpt-f --list-chats
sgpt-f --show-chat dev

# Interactive REPL (chat, shell, or code)
sgpt-f --repl temp
sgpt-f -s --repl temp
sgpt-f -c --repl temp

# Custom roles
sgpt-f --create-role pentest
sgpt-f --role pentest "check this nmap output"
sgpt-f --list-roles

# Function calling (enable once, install default functions once)
sgpt-f --functions-on
sgpt-f --install-functions
sgpt-f "what is my current working directory?"

# Pipe stdin into any prompt
cat /var/log/syslog | tail -n 30 | sgpt-f "summarize any errors"

# Override model for a single command (explicit prefixes work across backends)
sgpt-f --model colab/qwen2.5-coder:7b "write a systemd service"
sgpt-f --model opencode/beam-free "explain DNSSEC"
```

---

## 5. Testing & Verification

### Offline Unit Tests (no internet or Colab required)

```bash
python3 -m unittest test_adapter -v
```

### End-to-End Pre-Flight Test (tests every original `sgpt` feature)

Run this right after setup to verify all 48+ checks (unit tests, chat, `-s`, `-s` interactive `[E/M/D/A]`, `-c`, `-d`, `stdin` piping, `--chat`, `--repl`, `--editor`, `--role`, `--cache`, `--temperature`/`--top-p`, and `--functions` if enabled):

```bash
sgpt-f --test
# or test a specific model:
sgpt-f --test qwen2.5-coder:7b
```

---

## 6. Troubleshooting

- **`Colab/Ollama connection failed` or `HTTP 404` (`ERR_NGROK_3200`)**:
  - Check that your Google Colab cell is still running.
  - If you are not using a static `NGROK_DOMAIN`, Colab generates a new URL each session — update it with `sgpt-f --colab <NEW_URL> <MODEL>`.
- **`sgpt: command not found` or `sgpt-free: command not found`**:
  - Add `~/.local/bin` to your `PATH`: `export PATH="$HOME/.local/bin:$PATH"`.
- **OpenCode backend takes 15–45s per reply**:
  - Expected behavior on the `opencode run` route (OpenCode boots per request). For fast streaming replies, use the Google Colab backend or an OpenRouter model with a connected API key.
- **Thinking models (`qwen3.5`, `gemma4`, `qwen3`) on Colab**:
  - By default, the adapter sends `"reasoning_effort": "none"` and streams chat live so replies stay fast. To re-enable full chain-of-thought thinking, start the adapter with `SGPT_COLAB_THINK=true`.
- **Adapter seems stuck or unresponsive**:
  - Run `sgpt-f --restart` and inspect `sgpt-f --logs`.
- **Colab GPU out of memory (HTTP 500)**:
  - Lower `NUM_CTX` in `colab_sgpt_server.py` (e.g. `16384`) or choose a smaller model (e.g. `qwen2.5-coder:7b` or `gemma3:4b`).

---

## 7. Uninstall / Clean Removal

### Remove `sgpt-free`, `sgpt-f`, local adapter, and config (keeps `sgpt` and `opencode`)

```bash
# 1. Stop the local adapter
pkill -f '[a]dapter.py' 2>/dev/null || true
fuser -k 8642/tcp 2>/dev/null || true

# 2. Remove adapter files, logs, and launchers
rm -rf ~/.local/share/sgpt-opencode
rm -f ~/.local/bin/sgpt-free ~/.local/bin/sgpt-f
rm -rf /tmp/sgpt-oc-sandbox /tmp/sgpt-sanity /tmp/sgpt-audit.*

# 3. Remove sgpt-free config and .sgptrc (or restore your backup if you had one)
rm -f ~/.config/shell_gpt/sgpt-free.json ~/.config/shell_gpt/.sgptrc ~/.config/shell_gpt/.sgptrc*.bak
```

### Optional: Also remove original ShellGPT (`sgpt`) and OpenCode CLI

```bash
pipx uninstall shell-gpt 2>/dev/null || python3 -m pip uninstall -y shell-gpt
rm -rf ~/.config/shell_gpt ~/.opencode
```

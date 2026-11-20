# sgpt-free (`sgpt-f`) — Complete Guide to Free ShellGPT on Any Linux

by UNIT-61398

Run the **original, unmodified** [ShellGPT (`sgpt`)](https://github.com/TheR1D/shell_gpt) for free on **any Linux distribution** (Ubuntu, Debian, Kali, Arch, Fedora, RHEL/Rocky/Alma, openSUSE, Alpine, WSL) using either of two free backends:

1. **Google Colab + Ollama (Free T4 GPU)** — Host **any** Ollama model you want via `colab_sgpt_server.py` (with optional Google Drive model caching so models download only once).
2. **OpenCode / OpenRouter** — Use OpenCode's built-in free models, OpenRouter's direct API, or any provider connected in OpenCode.

Every single original ShellGPT feature works on both backends. Both **`sgpt-free`** and its short alias **`sgpt-f`** work identically everywhere.

---

## Table of Contents

1. [Does Original ShellGPT (`sgpt`) Need Any Changes?](#1-does-original-shellgpt-sgpt-need-any-changes)
2. [Required vs. Optional Files](#2-required-vs-optional-files)
3. [How It Works (Architecture)](#3-how-it-works-architecture)
4. [Installation (Any Linux) & Mandatory Post-Install Test](#4-installation-any-linux--mandatory-post-install-test)
5. [Backend A: Google Colab + Ollama (Any Model, Free T4 GPU)](#5-backend-a-google-colab--ollama-any-model-free-t4-gpu)
6. [Backend B: OpenCode / OpenRouter](#6-backend-b-opencode--openrouter)
7. [Quick Cheat Sheet ("What I Want to Do → Command")](#7-quick-cheat-sheet-what-i-want-to-do--command)
8. [Complete Command Reference (Every Local & Original `sgpt` Command)](#8-complete-command-reference-every-local--original-sgpt-command)
9. [Testing & Verification](#9-testing--verification)
10. [Troubleshooting](#10-troubleshooting)
11. [Uninstall / Clean Removal](#11-uninstall--clean-removal)

---

## 1. Does Original ShellGPT (`sgpt`) Need Any Changes?

**No. Zero changes to ShellGPT's source code are required.**

- `install.sh` installs the official upstream `shell-gpt` package directly (via `pipx` or `pip`).
- The `Original SGPT/` folder in this repository is kept **completely untouched** as an upstream reference only — it is not modified and is not required at runtime.
- The **only** thing configured for original `sgpt` is its standard config file (`~/.config/shell_gpt/.sgptrc`), which points ShellGPT at the local adapter (`http://127.0.0.1:8642/v1`) instead of OpenAI's paid API.
- `install.sh` and `sgpt-free` manage `~/.config/shell_gpt/.sgptrc` automatically (and back up any existing `.sgptrc` first). You never need to edit it manually.

For reference, these are the settings managed in `~/.config/shell_gpt/.sgptrc`:

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

## 2. Required vs. Optional Files

### Required Files (to install and run on Linux)

| File | Required For | Description |
| :--- | :--- | :--- |
| `install.sh` | Linux install | Universal Linux installer. Installs `sgpt`, copies `adapter.py`, installs `sgpt-free` and the `sgpt-f` symlink, and configures `.sgptrc`. |
| `adapter.py` | Runtime (Linux) | Local OpenAI-compatible HTTP server (`127.0.0.1:8642/v1`). Routes requests to Colab/Ollama or OpenCode/OpenRouter, streams chat live, strips `<think>` / scaffolding tags, sanitizes `-s` and `-c` output, and handles tool calls. |
| `sgpt-free` | Runtime (Linux) | CLI launcher and local configuration manager (also symlinked as `sgpt-f`). Starts `adapter.py` automatically and passes normal queries to original `sgpt`. |

### Required Only for Google Colab Backend

| File | Required For | Description |
| :--- | :--- | :--- |
| `colab_sgpt_server.py` | Google Colab | Python script you paste into a Google Colab cell (T4 GPU). Installs Ollama, pulls your chosen model, exposes `/v1` over ngrok, optionally caches models in Google Drive, and keeps the server alive. |

### Optional / Testing / Reference Files (not required for daily use)

| File / Folder | Purpose |
| :--- | :--- |
| `sgpt-audit.sh` | End-to-end live feature test script (run via `sgpt-f --test` or `sgpt-f --audit`). |
| `test_adapter.py` | Offline unit test suite (`python3 -m unittest test_adapter -v`). |
| `sgptrc.example` | Example `~/.config/shell_gpt/.sgptrc` template for reference. |
| `Original SGPT/` | Unmodified upstream ShellGPT source archive for reference only (not needed when copying to Linux). |
| `LICENSE.txt` | License file. |

---

## 3. How It Works (Architecture)

```text
  sgpt-free / sgpt-f (CLI)
          │
          ├── Local commands (--setup, --colab, --opencode, --set-model, --models, --status, --test, --help)
          │       └── Updates ~/.config/shell_gpt/sgpt-free.json & ~/.config/shell_gpt/.sgptrc
          │
          └── Normal ShellGPT prompts (-s, -c, -d, --chat, --repl, --role, --functions, ...)
                  └── Original `sgpt`
                          └── Local Adapter (http://127.0.0.1:8642/v1)
                                  ├── [colab]    -> Colab Ollama /v1 via ngrok (live stream + native tools + JSON shim fallback)
                                  └── [opencode] -> OpenRouter direct API or OpenCode CLI
```

- **Loopback only:** `adapter.py` binds exclusively to `127.0.0.1:8642`.
- **Dynamic config:** `adapter.py` reads `~/.config/shell_gpt/sgpt-free.json` on every request, so switching backends or models takes effect immediately.
- **Clean output on every mode:** `<think>...</think>` reasoning blocks and leaked agent tags are stripped, `-s` and `-c` outputs are sanitized so markdown fences never break shell execution or code files, and `--functions` works with native tools plus automatic JSON shim fallback.

---

## 4. Installation (Any Linux) & Mandatory Post-Install Test

Copy the project folder (or at minimum `install.sh`, `adapter.py`, `sgpt-free`, `sgpt-audit.sh`, and `test_adapter.py`) to your Linux machine, then run:

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

Right after installing and connecting your backend (Section 5 or 6 below), **always run the pre-flight test** before daily use:

```bash
sgpt-f --test
```

This verifies all 48+ checks (unit tests, adapter health, chat, `-s`, `-s` interactive `[E/M/D/A]`, `-c`, `-d`, `stdin` piping, `--chat`, `--repl`, `--editor`, `--role`, `--cache`, and `--temperature`/`--top-p`). Do not skip this step — it catches offline tunnels, missing `PATH` entries, or misconfigured models immediately.

---

## 5. Backend A: Google Colab + Ollama (Any Model, Free T4 GPU)

1. Open [Google Colab](https://colab.research.google.com/) and enable a GPU:
   **Runtime → Change runtime type → T4 GPU**.
2. Create a code cell and paste the full contents of [`colab_sgpt_server.py`](colab_sgpt_server.py).
3. Edit only the **CONFIGURATION** section at the top of the script:
   - `MODEL` — Any Ollama model name (tested on T4 15 GB GPU: `"qwen2.5-coder:7b"`, `"qwen3:8b"`, `"llama3.1:8b"`, `"mistral:7b"`, `"gemma3:12b"`, `"gemma3:4b"`, or any other Ollama / HuggingFace model).
   - `USE_MODELFILE` / `CUSTOM_MODEL_NAME` / `NUM_CTX` — Set `USE_MODELFILE = True` to build a custom model with your chosen context length (`32768` is safe for 7B–8B models on T4; use `16384` for 12B+ models).
   - `NGROK_TOKEN` — Paste your free authtoken from [dashboard.ngrok.com/authtokens](https://dashboard.ngrok.com/authtokens).
   - `NGROK_DOMAIN` *(optional)* — Paste a free static domain from [dashboard.ngrok.com/domains](https://dashboard.ngrok.com/domains) so your URL never changes between Colab sessions.
   - `USE_GOOGLE_DRIVE` — Set `True` to save downloaded models in Google Drive (`DRIVE_MODELS_DIR`) so you only download them once; set `False` if you don't want to use Drive storage.
   - `UNCENSORED_MODE` / `UNCENSORED_SYSTEM_PROMPT` — Optional custom system prompt (requires `USE_MODELFILE = True`).
   - `KEEP_ALIVE_LOOP = True` — Keeps the Colab cell alive and automatically restarts Ollama or reconnects ngrok if either drops.
4. Run the cell. When ready, copy-paste the single command it prints into your Linux terminal:

```bash
sgpt-f --colab https://xxxx.ngrok-free.app sgpt-ai
```

*(If you omit the model name, `sgpt-f --colab <URL>` automatically fetches `/v1/models` from Colab and selects the active model.)*

---

## 6. Backend B: OpenCode / OpenRouter

Switch to OpenCode or OpenRouter at any time:

```bash
# List available models in OpenCode:
sgpt-f --opencode
sgpt-f --models

# Select a built-in free model (no API key needed):
sgpt-f --opencode opencode/big-pickle
# or:
sgpt-f --opencode opencode/beam-free

# Or use the interactive setup wizard:
sgpt-f --setup
```

- **OpenCode built-in free models** work with no account or API key.
- **OpenRouter models** (e.g., `openrouter/recursive/flint-v1.0:free`) use OpenRouter's fast direct API when `OPENROUTER_API_KEY` is set or OpenRouter is connected in OpenCode (`opencode` → `/connect` → OpenRouter); otherwise they transparently fall back to `opencode run`.

---

## 7. Quick Cheat Sheet ("What I Want to Do → Command")

| What you want to do | Command |
| :--- | :--- |
| Ask a normal question (no flag needed!) | `sgpt-f "what is DNS?"` |
| Have a multi-turn conversation (remembers context) | `sgpt-f --chat work "hello"` |
| Open an interactive live chat loop (like ChatGPT) | `sgpt-f --repl temp` |
| Generate a Linux shell command and run it (`[E/M/D/A]`) | `sgpt-f -s "show open ports"` |
| Print a shell command only (no confirmation prompt) | `sgpt-f -s --no-interaction "show open ports"` |
| Explain what a Linux command does | `sgpt-f -d "chmod -R 755 /var/www"` |
| Generate pure code only (no markdown / explanation) | `sgpt-f -c "python port scanner"` |
| Save generated code directly to a file | `sgpt-f -c "python port scanner" > scan.py` |
| Analyze a file or command output via pipe | `cat error.log \| sgpt-f "why did this fail?"` |
| Write a long multi-line prompt in your text editor | `sgpt-f --editor` |
| Switch to Google Colab server | `sgpt-f --colab <NGROK_URL> [MODEL]` |
| Switch to OpenCode / OpenRouter | `sgpt-f --opencode [MODEL]` |
| Change default model | `sgpt-f --set-model <MODEL>` |
| List available models | `sgpt-f --models` |
| Check current backend, model, URL, and adapter status | `sgpt-f --status` |
| Run full pre-flight test of all features | `sgpt-f --test` |
| Show all local + original `sgpt` commands | `sgpt-f --h` (or `sgpt-free --help`) |

---

## 8. Complete Command Reference (Every Local & Original `sgpt` Command)

Run **`sgpt-f --h`** (or `sgpt-free --help` / `sgpt-f -h`) anytime to see both local commands and original `sgpt --help` right in your terminal.

### 8.1 Local Setup & Backend Management Commands (`sgpt-free` / `sgpt-f`)

| Command | What it does | Example |
| :--- | :--- | :--- |
| `--setup` | Interactive setup wizard to pick Colab or OpenCode and select a model. | `sgpt-f --setup` |
| `--colab <URL> [MODEL]` | Switch to Google Colab / Ollama backend, verify URL, update `.sgptrc`, and restart adapter. Auto-selects model if omitted. | `sgpt-f --colab https://xxxx.ngrok-free.app sgpt-ai` |
| `--opencode [MODEL]` | Switch to OpenCode / OpenRouter backend and optionally set default model. | `sgpt-f --opencode opencode/big-pickle` |
| `--set-model <MODEL>` | Change `DEFAULT_MODEL` for the active backend without editing `.sgptrc`. | `sgpt-f --set-model qwen2.5-coder:7b` |
| `--models` / `--list-models` | List live models from Colab (when on Colab) or `opencode models` + known free models. | `sgpt-f --models` |
| `--status` | Show active backend, default model, Colab URL, functions status, and adapter health. | `sgpt-f --status` |
| `--functions-on` | Enable ShellGPT function calling (`OPENAI_USE_FUNCTIONS=true`). | `sgpt-f --functions-on` |
| `--functions-off` | Disable ShellGPT function calling (`OPENAI_USE_FUNCTIONS=false`). | `sgpt-f --functions-off` |
| `--restart` | Restart the local background `adapter.py` process. | `sgpt-f --restart` |
| `--stop` | Stop the local background `adapter.py` process. | `sgpt-f --stop` |
| `--logs` | Print the last 60 lines of `~/.local/share/sgpt-opencode/adapter.log`. | `sgpt-f --logs` |
| `--test` / `--audit [MODEL]` | Run the full 48+ check pre-flight test suite (`sgpt-audit.sh`). | `sgpt-f --test` |
| `--help` / `--h` / `-h` | Show all local commands + original `sgpt --help`. | `sgpt-f --h` |

---

### 8.2 Normal Chat & Multi-Turn Conversations (Original `sgpt`)

| Option | What it does | Example |
| :--- | :--- | :--- |
| *(no flag)* `"PROMPT"` | **Default chat mode.** Ask any question and get a direct answer. | `sgpt-f "explain TCP vs UDP in 3 lines"` |
| `--chat <ID>` | Continue a named conversation (saves history in temp cache; use `"temp"` for a quick session). | `sgpt-f --chat api "design a REST API"`<br>`sgpt-f --chat api "now add JWT auth"` |
| `--repl <ID>` | Start an interactive back-and-forth REPL chat loop in your terminal (press `Ctrl+C` to exit; supports multi-line input with `"""`). | `sgpt-f --repl temp` |
| `--show-chat <ID>` | Print all saved messages from a previous `--chat` or `--repl` session. | `sgpt-f --show-chat api` |
| `-lc`, `--list-chats` | List all existing saved chat IDs. | `sgpt-f -lc` |

---

### 8.3 Shell Commands & System Administration (Original `sgpt`)

| Option | What it does | Example |
| :--- | :--- | :--- |
| `-s`, `--shell` | Generate a valid shell command for your Linux/shell, then prompt `[E]xecute, [M]odify, [D]escribe, [A]bort`. | `sgpt-f -s "find all files larger than 100MB"` |
| `--interaction` / `--no-interaction` | Control whether `-s` asks `[E/M/D/A]` (`--interaction`, default) or just prints the command without running it (`--no-interaction`). | `sgpt-f -s --no-interaction "restart nginx"` |
| `-d`, `--describe-shell` | Explain what a shell command and each of its flags do. | `sgpt-f -d "tar -xzvf backup.tar.gz -C /opt"` |
| `-s --repl <ID>` | Interactive shell-command REPL (type requests, execute or modify commands continuously). | `sgpt-f -s --repl temp` |
| `--install-integration` | Install Bash/ZSH hotkey integration (`Ctrl+L` turns your current terminal line into a generated shell command). | `sgpt-f --install-integration` |

---

### 8.4 Code Generation (Original `sgpt`)

| Option | What it does | Example |
| :--- | :--- | :--- |
| `-c`, `--code` | Output **pure code only** (no markdown backticks or explanations), ready to redirect to a file. | `sgpt-f -c "python script to check open ports"`<br>`sgpt-f -c "fizzbuzz in python" > fizz.py` |
| `-c --repl <ID>` | Interactive code-generation REPL. | `sgpt-f -c --repl codechat` |
| `-c --chat <ID>` | Multi-turn code generation session. | `sgpt-f -c --chat script1 "write a bash backup script"` |

---

### 8.5 Piping `stdin` & Using Your Text Editor (Original `sgpt`)

| Feature / Option | What it does | Example |
| :--- | :--- | :--- |
| `stdin` piping | Pipe logs, files, diffs, or command output directly into `sgpt-f`. | `cat /var/log/syslog \| tail -n 30 \| sgpt-f "summarize errors"`<br>`git diff \| sgpt-f "write a commit message"` |
| `--editor` | Opens your `$EDITOR` (`nano`/`vim`) so you can type a long multi-line prompt cleanly, then sends it on save & exit. | `sgpt-f --editor` |

---

### 8.6 Custom Roles / Personas (Original `sgpt`)

| Option | What it does | Example |
| :--- | :--- | :--- |
| `--create-role <NAME>` | Create and save a custom system role/persona (prompts you for the role instructions). | `sgpt-f --create-role pentest` |
| `--role <NAME>` | Run a prompt using a saved custom role (or built-in `ShellGPT` role). | `sgpt-f --role pentest "analyze this nmap scan"` |
| `--show-role <NAME>` | Display the saved prompt/instructions of a role. | `sgpt-f --show-role pentest` |
| `-lr`, `--list-roles` | List all available roles in `~/.config/shell_gpt/roles/`. | `sgpt-f -lr` |

---

### 8.7 Function Calling / Tool Execution (Original `sgpt`)

| Option | What it does | Example |
| :--- | :--- | :--- |
| `--install-functions` | Install ShellGPT's default local functions (e.g., `execute_shell_command`) into `~/.config/shell_gpt/functions/`. | `sgpt-f --install-functions` |
| `--functions` / `--no-functions` | Enable or disable function calling for a single command (use `sgpt-f --functions-on` / `--functions-off` to change the default). | `sgpt-f --functions "check my disk usage"`<br>`sgpt-f --no-functions "just explain df -h"` |

*Note: On Colab/Ollama and OpenRouter, `--functions` uses native OpenAI tool calling. If your chosen Ollama model (or OpenCode CLI route) does not support native tools, `adapter.py` automatically falls back to a JSON tool-call shim.*

---

### 8.8 Model, Sampling, Formatting, Cache & Version Flags (Original `sgpt`)

| Option | What it does | Example |
| :--- | :--- | :--- |
| `--model <MODEL>` | Override the default model for a single command. Supports explicit cross-backend prefixes: `colab/<model>`, `ollama/<model>`, `opencode/<model>`, `openrouter/<model>`. | `sgpt-f --model colab/qwen2.5-coder:7b "write a systemd unit"`<br>`sgpt-f --model opencode/big-pickle "explain DNSSEC"` |
| `--temperature <0.0–2.0>` | Controls randomness (`0.0` = deterministic/focused, `1.0+` = more creative). | `sgpt-f --temperature 0.7 "brainstorm 5 project names"` |
| `--top-p <0.0–1.0>` | Nucleus sampling probability cutoff (`1.0` = default). | `sgpt-f --top-p 0.9 "write a short story"` |
| `--md` / `--no-md` | Enable (`--md`, default) or disable (`--no-md`) rich terminal Markdown formatting. | `sgpt-f --no-md "explain chmod"` |
| `--cache` / `--no-cache` | Use (`--cache`, default) or bypass (`--no-cache`) ShellGPT's local response cache for identical prompts. | `sgpt-f --no-cache "give me a fresh example"` |
| `--version` | Show the installed ShellGPT version. | `sgpt-f --version` |

---

## 9. Testing & Verification

### Offline Unit Tests (no internet or Colab required)

```bash
python3 -m unittest test_adapter -v
```

### End-to-End Pre-Flight Test (mandatory after install)

```bash
sgpt-f --test
# or test a specific model:
sgpt-f --test qwen2.5-coder:7b
```

---

## 10. Troubleshooting

- **`Colab/Ollama connection failed` or `HTTP 404` (`ERR_NGROK_3200`)**:
  - Check that your Google Colab cell is still running.
  - If you are not using a static `NGROK_DOMAIN`, Colab generates a new URL each session — update it with `sgpt-f --colab <NEW_URL> <MODEL>`.
- **`sgpt: command not found` or `sgpt-free: command not found`**:
  - Add `~/.local/bin` to your `PATH`: `export PATH="$HOME/.local/bin:$PATH"`.
- **OpenCode backend takes 15–45s per reply**:
  - Expected behavior on the `opencode run` route (OpenCode boots per request). For fast live-streaming replies, use the Google Colab backend or an OpenRouter model with a connected API key.
- **Thinking models (`qwen3.5`, `gemma4`, `qwen3`) on Colab**:
  - By default, the adapter sends `"reasoning_effort": "none"` and streams chat live so replies stay fast. To re-enable full chain-of-thought thinking, start the adapter with `SGPT_COLAB_THINK=true`.
- **Adapter seems stuck or unresponsive**:
  - Run `sgpt-f --restart` and inspect `sgpt-f --logs`.
- **Colab GPU out of memory (HTTP 500)**:
  - Lower `NUM_CTX` in `colab_sgpt_server.py` (e.g. `16384`) or choose a smaller model (e.g. `qwen2.5-coder:7b` or `gemma3:4b`).

---

## 11. Uninstall / Clean Removal

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

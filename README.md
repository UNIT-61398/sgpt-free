# ShellGPT + OpenCode Free Models

> Run the **original, unmodified ShellGPT** (`sgpt`) in your terminal with **any model OpenCode supports** — including OpenCode's built-in free models and OpenRouter's free models — through a small local adapter. **No video needed:** everything is explained and commanded on this page.

**Current version: v4.3.4 (2026-10-24).**
Package: `sgpt-opencode-adapter-fixed-v4.3.4.zip`
SHA-256: `7f8e5df6df5305c394b1fee1bbfec23d8ebb70113e29ac846ea3a841294ee560`

**The one rule you must know first:** this package ships **no default model**. Nobody chooses a model for you. You set it yourself (Section 7), and until you do, every request fails with a clear message telling you exactly what to run. That is deliberate, not a bug.

---

## Table of Contents

- [1. What this is (and what it is not)](#1-what-this-is-and-what-it-is-not)
- [2. How it works](#2-how-it-works)
- [3. Quick start](#3-quick-start)
- [4. Requirements](#4-requirements)
- [5. Installation — Method A: one-click](#5-installation--method-a-one-click)
- [6. Installation — Method B: manual, step by step](#6-installation--method-b-manual-step-by-step)
- [7. First run: set YOUR model](#7-first-run-set-your-model)
- [8. Find a model: every provider](#8-find-a-model-every-provider)
- [9. Daily use: every command](#9-daily-use-every-command)
- [10. Which route answers you](#10-which-route-answers-you)
- [11. Test your model: sgpt-audit.sh](#11-test-your-model-sgpt-auditsh)
- [12. Manage the adapter](#12-manage-the-adapter)
- [13. Troubleshooting](#13-troubleshooting)
- [14. FAQ](#14-faq)
- [15. Uninstall and rollback](#15-uninstall-and-rollback)
- [16. Files in this repo](#16-files-in-this-repo)
- [17. Version history](#17-version-history)

---

## 1. What this is (and what it is not)

**What it is:**

- The **original ShellGPT** from PyPI (`pipx install shell-gpt`, the official `TheR1D/shell_gpt` package). Its code is never touched, patched, restricted, or replaced.
- A **local adapter** (`adapter.py`, one Python file, standard library only) that runs on your own machine at `http://127.0.0.1:8642` and nothing else. It translates sgpt's OpenAI-shaped requests into answers from OpenCode's models.
- A **launcher** (`sgpt-free`) that starts the adapter if it is not running, then runs the original `sgpt` with your arguments. Daily use is one command.
- A **full test script** (`sgpt-audit.sh`) that verifies every sgpt feature for real with your chosen model.

**What it is not:**

- Not a modified sgpt. Not a new AI tool. Not a cloud service. Nothing leaves your machine except the prompt itself, sent to the model provider you chose.
- Not a model picker. It never silently selects a model for you (see Section 7).
- Not a crack, key generator, or bypass. It uses OpenCode's own official CLI and your own provider credentials. Free models are free because the provider offers them, not because anything is circumvented.

**Who this is for:** anyone who wants `sgpt` in the terminal but wants to answer through OpenCode's free models (or any other OpenCode provider) instead of paying OpenAI.

---

## 2. How it works

### The chain

```text
you type:  sgpt-free "your question"
     |
     v
sgpt (ORIGINAL, unmodified) --[ API_BASE_URL = http://127.0.0.1:8642/v1 ]--> adapter.py (127.0.0.1:8642, your machine only)
     |
     +--[ model id starts with openrouter/ ]--> OpenRouter official API (fast, native roles/sampling/tool calls)
     |      key read from OpenCode's own stored credentials; if no readable key exists,
     |      the SAME model is served through the OpenCode CLI route instead (slower, nothing breaks)
     |
     +--[ every other provider/model ]--> `opencode run` (OpenCode's official CLI)
            includes OpenCode's built-in free models (opencode/*) and every provider
            you connected in OpenCode: OpenAI, Anthropic, Google, Groq, Ollama, ...
```

### Why an adapter is needed at all

OpenCode's built-in free models (the "Zen" free tier) **reject direct API calls** with `403 FreeTierError` — the free tier is only allowed from inside OpenCode itself. That is OpenCode's own rule, not a bug in this setup. So sgpt cannot call those models directly. The adapter solves it by going through the official `opencode run` CLI for those models, which is allowed. For `openrouter/*` models the adapter uses OpenRouter's official API directly, because that is what makes sgpt work properly there (real message roles, native sampling, native tool calls — see Section 10).

### Why there are two routes, and why one is slow

- **OpenRouter route:** one HTTPS API call. Answers in seconds.
- **OpenCode route:** every request boots a fresh `opencode run` process. Answers commonly take 20–60 seconds. That is the price of that route, not an adapter fault. If a request feels slow, check which route your model uses: `openrouter/*` is fast, everything else is the CLI route.

### Why sgpt's config points at localhost

sgpt has a built-in setting, `API_BASE_URL`, in `~/.config/shell_gpt/.sgptrc`. This setup points it at the local adapter (`http://127.0.0.1:8642/v1`). sgpt thinks it is talking to an OpenAI-compatible API. The adapter does the rest. The `OPENAI_API_KEY=dummy-local` value in that file is a placeholder sgpt requires to be non-empty; it is only ever sent to your local adapter, never to the internet.

---

## 3. Quick start

If you already have Kali Linux (or any Linux/macOS) with internet, this is the whole flow. Each step is explained in full below; this is just the map.

```bash
# 1. Unpack the package
unzip -o sgpt-opencode-adapter-fixed-v4.3.4.zip -d sgpt-v4.3.4
cd sgpt-v4.3.4

# 2. Install (fresh machine). With a model argument, that model is set for you.
#    Without an argument, NO model is set — you set it yourself in step 3.
./install-kali.sh opencode/beam-free

# 3. If you installed without a model argument, set your own model now:
nano ~/.config/shell_gpt/.sgptrc
#    Change the DEFAULT_MODEL= line to an exact id from `opencode models`
#    (Section 8), save, exit.

# 4. Test your model yourself (the audit NEVER runs automatically):
bash ~/.local/share/sgpt-opencode/sgpt-audit.sh

# 5. Daily use from now on — one command:
sgpt-free "what does the nmap -sV flag do?"
```

Already have an older version installed? Do **not** run the fresh installer. Use the upgrade script instead (it preserves your model and restarts the adapter):

```bash
bash apply-flint-fix.sh
```

---

## 4. Requirements

| # | Software | Why you need it | Install (Kali) | Verify |
|---|----------|-----------------|----------------|--------|
| 1 | Linux or macOS (Windows: use WSL) | base system | — | `cat /etc/os-release` |
| 2 | Internet | the models are online | — | `curl -sI https://opencode.ai \| head -1` |
| 3 | `curl` | downloads + adapter health checks | `sudo apt install -y curl` | `curl --version` |
| 4 | `python3` | runs `adapter.py` (standard library only, no extra packages) | preinstalled on Kali | `python3 --version` |
| 5 | `unzip` | unpacks this package | `sudo apt install -y unzip` | `unzip -v` |
| 6 | `pipx` | installs ShellGPT isolated (Kali blocks system-wide `pip`) | `sudo apt install -y pipx` then `pipx ensurepath` | `pipx --version` |
| 7 | OpenCode CLI (`opencode`) | runs non-OpenRouter models; stores provider credentials | official script, see Section 6 step 3 | `opencode --version` |
| 8 | ShellGPT (`sgpt`) | your terminal assistant — original, unmodified | `pipx install shell-gpt` | `sgpt --version` |
| 9 | This package | adapter + launcher + tests + docs | Method A or B below | `sgpt-free --version` |

No Node.js, no Docker, no database. If `pip` gives you an `externally-managed-environment` error on Kali, you used `pip` — always use `pipx` here.

---

## 5. Installation — Method A: one-click

### Fresh install

```bash
unzip -o sgpt-opencode-adapter-fixed-v4.3.4.zip -d sgpt-v4.3.4
cd sgpt-v4.3.4
chmod +x install-kali.sh

# Option 1: install WITH a model you chose (that model becomes your DEFAULT_MODEL)
./install-kali.sh opencode/beam-free
./install-kali.sh openrouter/recursive/flint-v1.0:free
./install-kali.sh groq/llama-3.1-8b-instant

# Option 2: install WITHOUT a model (recommended if you want to choose carefully)
./install-kali.sh
# Then set your model yourself (Section 7):
nano ~/.config/shell_gpt/.sgptrc
```

### What the installer does, in order

```text
[1/6] System packages — installs pipx, curl, python3 via apt (if missing).
[2/6] OpenCode CLI — installs opencode if missing (official installer).
[3/6] Sanity check — ONLY when you passed a model. Runs:
        opencode run -m <your-model> "Reply with exactly one word: hello"
      (up to 3 minutes). If the model stays silent, the installer STOPS
      and tells you why. Nothing half-installed. The adapter is not
      involved yet at this step — this proves the MODEL itself answers.
      With no model argument, this step is skipped (nothing to test yet).
[4/6] ShellGPT — installs the ORIGINAL package via pipx (skipped if present).
[5/6] Adapter + config — copies adapter.py, sgpt-free, test_adapter.py and
      sgpt-audit.sh to ~/.local/share/sgpt-opencode/ and ~/.local/bin/.
      Backs up any existing .sgptrc to .sgptrc.before-install.bak, then
      writes the config: with a model argument, DEFAULT_MODEL=<that model>;
      without one, DEFAULT_MODEL=SET_YOUR_MODEL_HERE (placeholder — see
      Section 7). A no-argument install NEVER reuses a model from an old
      config: a model appears only if you pass it or set it yourself.
[6/6] Manual test step — the installer deliberately does NOT run any
      test itself. It tells you to test your model yourself with:
        bash ~/.local/share/sgpt-opencode/sgpt-audit.sh [model]
      (Section 11). Nothing is executed by the test's shell probe.
```

### Upgrade an existing install (do NOT run the fresh installer)

```bash
cd sgpt-v4.3.4
bash apply-flint-fix.sh
```

The name is historical (it was first written to fix the Flint setup); in v4.3.4 it sets **no** model. What it does, in order:

```text
1. Checks that adapter.py sits beside it and that original sgpt exists.
2. Backs up your current adapter and .sgptrc (*.before-openrouter-flint-fix.bak).
3. Installs the new adapter.py and copies sgpt-audit.sh to the install dir.
4. Updates the non-model settings in .sgptrc (API address, timeouts, ...).
   It NEVER touches your DEFAULT_MODEL line. Your model survives the upgrade.
   Only if the DEFAULT_MODEL line is missing entirely does it add the placeholder.
5. Checks the OpenRouter key search WITHOUT printing any key:
   key found  -> [PASS] ... (secret never displayed)
   key missing -> [WARN] ... (NOT fatal: openrouter/* models are then served
                   through the OpenCode CLI route, as the earlier working setup ran)
6. Stops the old running adapter and starts the new one, then verifies
   health (status "ok"). This restart is what makes a new adapter file
   actually take effect — replacing files alone never restarts a running process.
7. Reports your configured model (unchanged), or, if the placeholder is
   still there, tells you to set a model with nano (Section 7).
```

It never runs the audit (it only copies it), never touches your roles, chats, functions, or credentials, and never reinstalls sgpt or OpenCode.

### Verify the installation

```bash
python3 --version
pipx --version
opencode --version
sgpt --version
sgpt-free --version

curl -s http://127.0.0.1:8642/health
#   {"status": "ok", "default_model": "opencode/beam-free"}   <- your model, when set
#   {"status": "ok", "default_model": null}               <- nothing configured yet

curl -s http://127.0.0.1:8642/v1/models   # known free ids (discovery list, NOT a default)

cat ~/.config/shell_gpt/.sgptrc           # API_BASE_URL must be http://127.0.0.1:8642/v1
```

---

## 6. Installation — Method B: manual, step by step

Do this only if you want to understand or control every step. Method A does exactly this, automatically.

```bash
# Step 1 — system packages
sudo apt update && sudo apt install -y curl python3 unzip pipx

# Step 2 — pipx bin folder on PATH (then open a NEW terminal)
pipx ensurepath

# Step 3 — OpenCode CLI (official installer)
curl -fsSL https://opencode.ai/install | bash
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$PATH"

# Step 4 — verify OpenCode
opencode --version

# Step 5 — connect a provider once (only needed for that provider's models;
# OpenCode's built-in free models need no account at all)
opencode            # inside: type  /connect  -> pick a provider
                    # then Ctrl+C to exit

# Step 6 — THE sanity check (do not skip: this must answer first).
# Use YOUR chosen model id (Section 8), not somebody else's default.
cd /tmp && opencode run -m opencode/beam-free "Reply with exactly one word: hello"
# Expected: it prints "hello".

# Step 7 — original ShellGPT (unmodified, from PyPI)
pipx install shell-gpt

# Step 8 — verify sgpt
sgpt --version

# Step 9 — adapter + helpers + config (run from the unzipped package folder)
mkdir -p ~/.local/share/sgpt-opencode ~/.local/bin ~/.config/shell_gpt
cp adapter.py test_adapter.py sgpt-audit.sh ~/.local/share/sgpt-opencode/
cp sgpt-free ~/.local/bin/ && chmod +x ~/.local/bin/sgpt-free ~/.local/share/sgpt-opencode/sgpt-audit.sh
cp sgptrc.example ~/.config/shell_gpt/.sgptrc

# Step 9b — SET YOUR OWN MODEL (no default is shipped):
nano ~/.config/shell_gpt/.sgptrc   # replace SET_YOUR_MODEL_HERE with
                                   # an exact id from 'opencode models'

# Step 10 — final live test (only works after step 9b)
sgpt-free --no-cache "Reply in one short line: say hi"
```

## 7. First run: set YOUR model

### The no-default rule, stated plainly

This package ships **no default model** — not Flint, not Beam, not anything. A model appears in your config only in two ways, both of them your action:

1. You pass it to the installer: `./install-kali.sh opencode/beam-free`
2. You write it yourself: `nano ~/.config/shell_gpt/.sgptrc`

A fresh install without a model argument writes this line:

```text
DEFAULT_MODEL=SET_YOUR_MODEL_HERE
```

That is a placeholder, not a model. With it (or with no model at all), sgpt refuses with this exact message instead of silently answering with a model you never chose:

```text
No model configured: set DEFAULT_MODEL in ~/.config/shell_gpt/.sgptrc
(run: nano ~/.config/shell_gpt/.sgptrc) to a real model id, e.g.
opencode/beam-free or openrouter/recursive/flint-v1.0:free,
or pass --model <provider/model-id> for one command.
```

That refusal is the intended behavior. Fix it by setting a model (below). The audit script refuses the same way (Section 11).

### Set it (the only edit you need)

```bash
nano ~/.config/shell_gpt/.sgptrc
```

Change the `DEFAULT_MODEL=` line to an exact model id (Section 8), save, exit. Examples of what that line looks like when set:

```bash
DEFAULT_MODEL=opencode/beam-free
DEFAULT_MODEL=openrouter/recursive/flint-v1.0:free
DEFAULT_MODEL=groq/llama-3.1-8b-instant
DEFAULT_MODEL=google/gemini-3.8-flash
```

No adapter restart is needed after editing `.sgptrc`: sgpt reads the file on every invocation, and always sends its own `DEFAULT_MODEL` with the request. (The adapter's own default only matters for its `/health` display and its `/v1/models` discovery list.)

### Use a different model for one command only

```bash
sgpt-free --model groq/llama-3.1-8b-instant "your question"
sgpt-free --model openrouter/recursive/flint-v1.0:free "your question"
```

This does not change your default.

### The 7 lines the installer writes — and why the file is short

A fresh install writes only these 7 settings:

```text
OPENAI_API_KEY=dummy-local
API_BASE_URL=http://127.0.0.1:8642/v1
DEFAULT_MODEL=<your model, or SET_YOUR_MODEL_HERE>
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
REQUEST_TIMEOUT=600
DISABLE_STREAMING=false
```

If you have seen a much longer `.sgptrc` before (with `CHAT_CACHE_PATH`, `CACHE_LENGTH`, `CODE_THEME`, `ROLE_STORAGE_PATH`, and so on), that long file was written by **sgpt itself** on its first run — those are sgpt's own built-in defaults. They still apply when they are not written in the file, so the short file loses nothing. Your previous file is always backed up first (`.sgptrc.before-install.bak`), so nothing is ever silently destroyed.

---

## 8. Find a model: every provider

### The format rule

Every model id has exactly two parts, joined by one slash:

```text
provider/model-id
```

- `provider` = the OpenCode provider name, exactly as OpenCode spells it: `opencode`, `openrouter`, `groq`, `google`, `openai`, `anthropic`, `ollama`, and so on.
- `model-id` = the model's exact id from that provider's catalogue: same spelling, same case, same dashes, same suffixes. Copy it, never guess it.

### Where the names come from (the source of truth)

Free-model lists change constantly — a name that worked last month can disappear or lose its free tier. These commands are the truth; any table (including the one below) is a snapshot to start from:

```bash
opencode models                 # every provider/model id available to you
opencode models <provider>      # one provider only, e.g. opencode models groq
opencode                        # inside the TUI: type  /models
```

For OpenRouter specifically, also: `openrouter.ai/models`, search "free" — every free model there ends in `:free`.

### Test a model BEFORE making it your default

```bash
opencode run -m <provider/model-id> "Reply with exactly one word: hello"
```

If that answers, the id is right and the provider works. (For `openrouter/*` ids the adapter's direct path may still work even if `opencode run` is slow — the real end-to-end test is `sgpt-free` or the audit in Section 11.)

### Two adapter spelling rules

- A **bare id with no slash** (e.g. `big-pickle`) is treated as an OpenCode built-in free model: `opencode/big-pickle`. Writing the full id is recommended; the shorthand exists only for convenience.
- A **bare id ending in `:free`** (e.g. `recursive/flint-v1.0:free`) is treated as an OpenRouter model: `openrouter/recursive/flint-v1.0:free`.

### Every provider: connect, list, free or paid, how to write it

Snapshot from **2026-10-24**. If an id fails, re-run the list command for that provider and copy the id it shows today.

| Provider | Connect first? | List its models | Free? | How to write it (snapshot examples) |
|---|---|---|---|---|
| `opencode` (OpenCode Zen, built in) | No — no account at all | `opencode models opencode` | Yes, built-in free | `opencode/beam-free`, `opencode/big-pickle`, `opencode/mimo-v2.6-flash-free`, `opencode/deepseek-v4.1-flash-free`, `opencode/glm-5.3-flash-free`, `opencode/minimax-m3.1-flash-free`, `opencode/longcat-2.5-preview-free`, `opencode/nemotron-3.5-lightning-free`, `opencode/nemotron-3.5-super-vl-free`, `opencode/nemotron-3-ultra-free` |
| `openrouter` (gateway to hundreds of models) | Yes: `opencode` → `/connect` → OpenRouter | `opencode models openrouter`, or openrouter.ai/models filtered "free" | The `:free` models only | `openrouter/recursive/flint-v1.0:free`, `openrouter/nvidia/nemotron-3.5-lightning:free`, `openrouter/cohere/north-mini-code:free`, `openrouter/poolside/laguna-s-2.1:free`, `openrouter/poolside/laguna-xs-2.1:free`, `openrouter/openai/gpt-oss-20b:free`, `openrouter/google/gemma-4-26b-a4b-it:free`, `openrouter/google/gemma-4-31b-it:free`, `openrouter/nvidia/nemotron-3-super-120b-a12b:free`, `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`, `openrouter/liquid/lfm-2.5-2.6b:free`, `openrouter/dots-studio/dots-3-note-preview:free` — plus `openrouter/free`, the auto-router that picks a free model for you |
| `groq` (fast LPU inference) | Yes: `/connect` → Groq (free developer tier, no card) | `opencode models groq` | Yes, free tier with per-model daily limits | `groq/llama-3.1-8b-instant`, `groq/llama-3.3-70b-versatile`, `groq/openai/gpt-oss-120b`, `groq/openai/gpt-oss-20b`, `groq/openai/gpt-oss-safeguard-20b`, `groq/qwen/qwen3.8-27b`, `groq/moonshotai/kimi-k2-instruct`, `groq/allam-2-7b` |
| `google` (Gemini via AI Studio) | Yes: `/connect` → Google (free tier, no card) | `opencode models google` | Yes, Flash/Flash-Lite free tier (per-project limits; Pro models are paid) | `google/gemini-3.8-flash`, `google/gemini-3.6-flash`, `google/gemini-3.5-flash-lite`, `google/gemini-3.1-flash-lite`, `google/gemma-4` |
| `ollama` (runs on your own machine) | No key — install Ollama, then `ollama pull <tag>` | `ollama list`, or `opencode models ollama` | Yes, except your own hardware/electricity | `ollama/llama3.1`, `ollama/qwen3`, `ollama/<whatever tag you pulled>` |
| Every other provider (`anthropic`, `openai`, `xai`, `deepseek`, `cerebras`, `mistral`, `zai`, `moonshot`, ...) | Yes: `/connect` → that provider | `opencode models <provider>` | Depends on the provider — most are paid; a few run free tiers or promos. **Free vs paid is the provider's business, not the adapter's.** Check that provider's pricing page before heavy use | Exactly the same format: `anthropic/claude-sonnet-4-5`, `openai/gpt-5-mini`, `xai/grok-4-1`, `deepseek/deepseek-chat`, `cerebras/<id-from-the-list>` — whatever `opencode models <provider>` prints, copied exactly |

### Three patterns worth memorizing

- **OpenCode built-in free:** `opencode/<name>` — the word `free` is already inside the name (`beam-free`); there is NO colon suffix. `opencode/beam:free` is wrong.
- **OpenRouter free:** `openrouter/<owner>/<name>:free` — the `:free` suffix IS part of the id. Dropping it picks a different (paid) route or fails outright.
- **Ordinary provider free tiers:** `groq/...`, `google/...` — no `:free` suffix; "free" comes from the provider's free tier, and the id is just the plain model id under that provider.

### Mistakes that look like adapter bugs

- **Invented id** (`opencode/gpt-5`, `groq/llama-99b`): the backend says model not found. Copy the id from the list command — never guess one.
- **Wrong case or a dropped suffix** (`Beam-Free`, `flint-v1.0` without `:free` on OpenRouter): ids are exact strings.
- **Provider not connected**: `opencode` → `/connect` → that provider, then re-test with `opencode run -m <id>`.
- **Free limit hit** (`FREE LIMIT HIT`): the model is right, its quota is spent — wait, or switch model (Section 13).

---

## 9. Daily use: every command

Daily use is ONE command: **`sgpt-free`** (it auto-starts the adapter if needed). Plain `sgpt` works identically once the adapter is running — same program, same config.

### Normal questions

```bash
sgpt-free "what does the nmap -sV flag do?"
sgpt-free --no-cache "Reply with exactly SGPT_OK"
sgpt-free --no-md "your question"     # plain output, no markdown rendering
sgpt-free --cache "your question"     # sgpt's local cache (on by default)
```

### `-s` / `--shell`: get a shell command (read it before you run it)

```bash
sgpt-free -s "show all listening ports"
sgpt-free -s "create a Python hello-world file named free-sgpt.py in my Downloads folder"
```

sgpt prints ONE shell command, then asks:

```text
[E]xecute  [M]odify  [D]escribe  [A]bort
```

- **E** runs it. **M** lets you edit it first. **D** explains it. **A** aborts (nothing runs).
- **Read the command before pressing E**, especially anything with `sudo`, `rm`, or pipes into a shell. This is the same rule as any AI shell tool.
- The adapter strips model commentary and markdown fences, and strips leaked agent scaffolding lines, so only the command reaches sgpt. Compound commands, pipes, quotes, and redirections pass through untouched.

Print the command ONLY, without executing it (execution happens only via the E prompt):

```bash
sgpt-free -s "show disk usage" --no-interaction
```

> Why you cannot pipe an answer into the E/M/D/A prompt: sgpt reads piped stdin as **prompt context**, and reads its E/M/D/A answers from `/dev/tty` (your real terminal) by design. Piping `echo E | sgpt-free -s ...` does not work — the `E` becomes part of the question. The same applies to REPL input. The audit (Section 11) tests these through a real pseudo-terminal for exactly this reason.

### `-c` / `--code`: code only

```bash
sgpt-free -c "write a simple TCP port scanner in python"
```

Markdown fences are stripped for you, so you get raw code.

### `-d` / `--describe-shell`: understand a command

```bash
sgpt-free -d "find / -perm -4000 2>/dev/null"
```

### `--chat`: a named session that remembers context

```bash
sgpt-free --chat learn "explain the TCP three-way handshake simply"
sgpt-free --chat learn "now quiz me on that"
sgpt-free --show-chat learn
sgpt-free --list-chats        # or -lc
```

Chat history lives in `${TMPDIR:-/tmp}/chat_cache/<id>`. A reused id (like `temp`) keeps ALL its old context — if answers look polluted, use a fresh id or delete that file.

### `--repl`: interactive session

```bash
sgpt-free --repl temp
```

Remembers context across turns. Ctrl+C to exit. (Same `/dev/tty` rule as above: REPL input cannot be piped.)

### Roles

```bash
sgpt-free --list-roles        # or -lr
sgpt-free --show-role ShellGPT
sgpt-free --role ShellGPT "your question"
sgpt-free --create-role MyRole     # asks for the role description
```

### `--editor`: compose the prompt in your editor first

```bash
sgpt-free --editor
```

### Pipe command output INTO sgpt for analysis

```bash
cat /var/log/auth.log | tail -50 | sgpt-free "any suspicious activity in these logs?"
```

Piped text becomes prompt context (sgpt's own feature). The `__sgpt__eof__` line separates piped context from interactive input, per sgpt's design.

### One-off model, sampling, and formatting

```bash
sgpt-free --model opencode/big-pickle "your question"
sgpt-free --model openai/gpt-5-mini "your question"

# Sampling / formatting (see Section 10 for what each route supports)
sgpt-free --temperature 0.7 --top-p 0.9 "your question"
```

`--temperature` / `--top-p` are accepted by sgpt on both routes, but only forwarded natively on the OpenRouter route. On the OpenCode route `opencode run` exposes no sampling flags, so the model's own defaults apply.

### Functions (`--functions`)

Function calling works when **all three** hold: (a) `OPENAI_USE_FUNCTIONS=true` is set in `~/.config/shell_gpt/.sgptrc`, (b) at least one function file exists in `~/.config/shell_gpt/functions/` (install sgpt's defaults with `sgpt --install-functions`), and (c) you pass `--functions`.

```bash
sgpt --install-functions
# then in .sgptrc set: OPENAI_USE_FUNCTIONS=true
sgpt-free --functions "what is the weather in Lahore?"
```

- **OpenRouter route:** tool calls are **native** — requests, tool results, and follow-up answers round-trip exactly as sgpt designed.
- **OpenCode route:** text models cannot emit native tool calls, so the adapter uses a JSON shim: functions are listed in the prompt, a JSON call reply is converted into a real tool-call response, sgpt executes your local function and sends the result back. Simple single calls work; exotic multi-call flows are model-dependent.

> ⚠️ A **broken function file breaks EVERY sgpt command** (sgpt loads all function files at startup and crashes on a bad one). If sgpt suddenly dies with a traceback mentioning `functions`, fix or remove the newest file in `~/.config/shell_gpt/functions/`. The package ships with functions OFF for exactly this reason.

## 10. Which route answers you

| Feature | OpenRouter route (`openrouter/*`) | OpenCode route (all other providers) |
|---|---|---|
| Message roles preserved | ✅ native | flattened into one prompt (neutral framing) |
| `--temperature` / `--top-p` | ✅ forwarded to the API | accepted by sgpt; **not forwarded** — `opencode run` exposes no sampling flags; the model's own defaults apply |
| `--functions` tool calls | ✅ native | ✅ via JSON shim (best effort) |
| Streaming to sgpt | buffered, then valid SSE chunks + `[DONE]` (same visible result) | same |
| `-s` shell sanitize / `-c` de-fencing | ✅ adapter-side, both routes | ✅ |
| Scaffolding-strip (Section 13, parse-error fix) | ✅ every reply, every mode | ✅ |
| Speed | seconds | 20–60s per request (fresh `opencode run`) |
| Account needed | OpenRouter key (already in OpenCode) | none for built-in free models; provider's own for others |

Everything else — `-s` E/M/D/A flow, `--chat`, `--repl`, roles, `--editor`, `--cache`, `--md` — is **sgpt's own code** and behaves identically on both routes.

**Free-tier data note:** free models (OpenCode's and OpenRouter's `:free`) may use collected data to improve their models. Do not paste secrets or private logs.

**API keys stay private:** the adapter reads the OpenRouter key from OpenCode's auth store at request time; it is never written to the adapter log, the sgpt config, or this package. If no readable key exists, the adapter serves `openrouter/*` models through the OpenCode CLI route instead of failing — one log line says so.

---

## 11. Test your model: sgpt-audit.sh

`sgpt-audit.sh` is the package's test file. Understand its one rule first: **it is manual only**. Neither the installer nor the upgrade script ever runs it. The flow is: **choose your model first (Section 7/8), then run the audit yourself** to test that model. It ships inside the package and is copied to `~/.local/share/sgpt-opencode/` by the installer, so it is there whenever you need it again — for example, after switching models.

### Commands

```bash
# Test the model in your .sgptrc:
bash ~/.local/share/sgpt-opencode/sgpt-audit.sh

# Or test one model without changing your default:
bash ~/.local/share/sgpt-opencode/sgpt-audit.sh opencode/beam-free
bash ~/.local/share/sgpt-opencode/sgpt-audit.sh groq/llama-3.1-8b-instant

# From the unzipped package folder:
bash sgpt-audit.sh opencode/beam-free
```

### What it tests (actual behavior, not help text)

- Adapter Python syntax + offline unit tests (routing, parameter/tool forwarding, sanitizers, SSE shape) — no API quota spent.
- Adapter health + `/v1/models`.
- Token probes: normal chat, `-c`, `-d`, `--chat` (unique id) + `--show-chat`, sampling/formatting flags, `--cache`.
- `-s` two ways: `--no-interaction` (print-only, never executes) and the real interactive E/M/D/A prompt driven through a pseudo-terminal, answered with **A (Abort)** — nothing executes.
- `--repl` through a pseudo-terminal (real terminal behavior).
- `--editor` through a pseudo-terminal with a scripted editor.
- Roles: `--list-roles`, `--create-role` + `--show-role` (throwaway role, cleaned up), `--role`.
- `--functions`: real probe when enabled and functions installed, otherwise a SKIP that says exactly why.

### How to read the results

Each check prints `PASS`, `FAIL`, or `SKIP` with its name. A `SKIP` is not a failure — it says why that check did not apply (for example, `--functions` is skipped when functions ship disabled, which is the package default). A `FAIL` prints the relevant log tail so you can see what happened. If the config still has the `SET_YOUR_MODEL_HERE` placeholder, the audit stops immediately and tells you to set a model first (Section 7) — it refuses to "test" a placeholder.

### Why a pseudo-terminal (PTY)?

sgpt reads its E/M/D/A answers and REPL input from `/dev/tty` by design — piping an answer into stdin does NOT work (piped stdin becomes part of the prompt instead). An earlier audit's `-s` "timeout" was exactly this test-harness problem, not an adapter failure; a `--chat temp` failure was a stale shared chat cache plus a strict token match. This audit avoids both traps.

---

## 12. Manage the adapter

```bash
curl -s http://127.0.0.1:8642/health
#   {"status": "ok", "default_model": "opencode/beam-free"}   <- your model, when set
#   {"status": "ok", "default_model": null}               <- nothing configured yet

curl -s http://127.0.0.1:8642/v1/models   # known free ids (discovery list, NOT a default)

tail -30 ~/.local/share/sgpt-opencode/adapter.log   # its log

fuser -k 8642/tcp                              # stop it (next sgpt-free call starts it again)

python3 ~/.local/share/sgpt-opencode/adapter.py     # run in foreground (debug)
```

The adapter binds `127.0.0.1` only. Client disconnects (Ctrl+C in sgpt) are handled quietly — no BrokenPipe tracebacks. Remember: **replacing the adapter file never restarts the running process**. After upgrading the adapter file, restart it (`fuser -k 8642/tcp`, then run `sgpt-free` again) so the new code is what actually runs. This is the single most common cause of "I installed the fix but the old error is still there."

---

## 13. Troubleshooting

| Problem | What is happening | Fix |
|---|---|---|
| `No model configured` / `SET_YOUR_MODEL_HERE` | Intended (v4.3.4): no default is shipped | Set your own: `nano ~/.config/shell_gpt/.sgptrc`, `DEFAULT_MODEL=<exact id from opencode models>` (Sections 7–8) |
| `sgpt-free: command not found` | `~/.local/bin` is not on PATH in this terminal | New terminal, or `export PATH="$HOME/.local/bin:$PATH"` |
| `sgpt: command not found` | ShellGPT is not installed | `pipx list`; if empty, `pipx install shell-gpt` |
| `externally-managed-environment` | You used `pip` | On Kali always use **pipx** |
| Sanity check silent for 3 minutes | The model did not answer | Check internet + that the provider is connected (`opencode` → `/connect`). Retry later if the provider is down — NOT an adapter problem (the adapter is not involved yet at that step) |
| `OpenRouter API key not found` (old apply script) / adapter log says no readable credential | OpenCode holds the credential in a form the direct route cannot read (e.g. OAuth-only or a newer credential store) | Fixed in v4.1+: the adapter searches env, `auth.json` (incl. OAuth), OpenCode config apiKey, and the credential database — and if none is readable it automatically serves the model through the OpenCode CLI route instead of failing. For the fast direct route, connect OpenRouter with an API key (`opencode` → `/connect`) or export `OPENROUTER_API_KEY` before starting the adapter |
| `403 FreeTierError` | Something is calling Zen directly | Check `.sgptrc`: `API_BASE_URL` must be `http://127.0.0.1:8642/v1`, never an `opencode.ai` URL |
| zsh says `parse error near '>'` after executing an `-s` command | The agent backend leaked an XML-style fragment (e.g. `</rfl:parameter>`) into the generated command | Fixed in v4.3.2 and present in v4.3.4: the adapter strips scaffolding lines from every reply before sgpt sees it. If you still see it, your RUNNING adapter is old: restart it (`fuser -k 8642/tcp`, then run `sgpt-free` again) or upgrade from the new package folder — do not re-run the upgrade from the old folder. The command itself was correct; only the stray line broke it |
| sgpt shows `FREE LIMIT HIT` | That IS the result, not a crash: the free model's quota/rate limit is exhausted | Wait a few minutes or switch model (`sgpt-free --model <provider/model> "..."`). Paid models instead show `LIMIT HIT (paid model)` when their rate limit, quota, or credit runs out — check the provider plan/balance. Both routes report limits this clearly since v4.2 |
| Model refuses sgpt-style requests | On the OpenRouter route this should not happen (roles are native). On the OpenCode route a few safety-tuned models dislike persona text | Switch model |
| sgpt crashes at startup mentioning `functions` | A broken file in `~/.config/shell_gpt/functions/` | Fix/remove it (Section 9, functions) |
| Answer hangs | A slow backend request can hold the adapter's single-request gate | Log (Section 12), then restart: `fuser -k 8642/tcp`, run `sgpt-free` again |
| Port 8642 already in use | An adapter is already running | Fine, `sgpt-free` reuses it. After upgrading the adapter file, restart it so the new code is what runs |
| Model works in `opencode run` but not through sgpt | Config or routing issue | Check `API_BASE_URL` in `.sgptrc`, check the adapter log (Section 12), re-run the audit (Section 11) |

---

## 14. FAQ

**Is this the original sgpt?**
Yes. Installed as-is from PyPI via pipx. Its code is never modified. The adapter is only a backend bridge.

**Do I need an account?**
For OpenCode's built-in free models (`opencode/...`): no account at all — verified with zero stored credentials. For OpenRouter models: connect OpenRouter once in OpenCode (`opencode` → `/connect`). For any other provider: that provider's own account/key, connected the same way.

**Why is there no default model?**
Because a default would answer you with a model you never chose. This package refuses to guess. You set one line (Section 7) and that is what runs.

**Which free model is "the best"?**
There is no single answer — free lists change, limits differ, and models behave differently per task. Pick 2–3 candidates from Section 8, test each with the audit (Section 11), and keep the one that answers your work best.

**Will my model survive an upgrade?**
Yes for upgrades: `apply-flint-fix.sh` never touches your `DEFAULT_MODEL` line. No for fresh installs without a model argument: the installer writes the placeholder, and you set the model yourself (your old file is backed up first as `.sgptrc.before-install.bak`).

**Is my OpenRouter key safe?**
The adapter reads it from OpenCode's own credential store at request time and never prints it, never writes it to any log, config, or file in this package.

**Can I use paid models too?**
Yes. Anything OpenCode supports works the same way (`--model provider/model-id` or `DEFAULT_MODEL`). Paid models bill per their provider's own rules; free vs paid is the provider's business.

**Does it work outside Kali?**
Linux and macOS yes. Windows: run the adapter + sgpt inside WSL.

**What if a model disappears from the free list?**
That happens regularly. Re-run `opencode models <provider>`, pick a current id, update `DEFAULT_MODEL`, re-run the audit.

---

## 15. Uninstall and rollback

### Remove only the adapter (keeps sgpt, OpenCode, and your config)

```bash
fuser -k 8642/tcp 2>/dev/null; rm -rf ~/.local/share/sgpt-opencode ~/.local/bin/sgpt-free
```

After this, `sgpt-free` is gone and plain `sgpt` will fail to reach the (now missing) adapter until you reinstall. Your `.sgptrc`, roles, chats, and OpenCode setup stay intact.

### Roll back an upgrade or install (backups are kept next to the originals)

```bash
# Adapter rollback (after apply-flint-fix.sh)
cp ~/.local/share/sgpt-opencode/adapter.py.before-openrouter-flint-fix.bak \
   ~/.local/share/sgpt-opencode/adapter.py
cp ~/.config/shell_gpt/.sgptrc.before-openrouter-flint-fix.bak \
   ~/.config/shell_gpt/.sgptrc
fuser -k 8642/tcp    # next sgpt-free call starts the restored adapter

# Config rollback (after install-kali.sh)
cp ~/.config/shell_gpt/.sgptrc.before-install.bak ~/.config/shell_gpt/.sgptrc
```

Your roles, chats, functions, and credentials are never touched by either script.

### Remove everything

```bash
fuser -k 8642/tcp 2>/dev/null            # stop the adapter
pipx uninstall shell-gpt                  # remove original sgpt
rm -rf ~/.local/share/sgpt-opencode       # adapter + tests + audit
rm -f  ~/.local/bin/sgpt-free             # launcher
rm -rf ~/.config/shell_gpt                # sgpt config + cache + roles
rm -rf ~/.opencode                        # OpenCode (optional)
```

---

## 16. Files in this repo

| File | Purpose |
|------|---------|
| `README.md` | main documentation (the in-package guide) |
| `README-GitHub.md` | this file — the GitHub-facing guide (same version, written for a first-time reader) |
| `MASTER-README-SGPT-OpenCode.md` | the long master guide (providers, direct-OpenAI mode, uninstall detail) |
| `CHANGELOG.md` | what changed in each version |
| `install-kali.sh` | one-click installer (Method A) |
| `apply-flint-fix.sh` | safe upgrade for existing installs (backups + health verify; never touches your `DEFAULT_MODEL`) |
| `adapter.py` | the local adapter (Python standard library only) |
| `test_adapter.py` | offline adapter unit tests |
| `sgpt-audit.sh` | full live feature audit (Section 11) |
| `sgpt-free` | launcher that auto-starts the adapter, then runs original `sgpt` |
| `sgptrc.example` | sgpt config template → `~/.config/shell_gpt/.sgptrc` (placeholder model — you set it) |
| `start-adapter.sh` | manual adapter start (foreground) |
| `setup-guide.md` | background notes: why Zen free models need OpenCode, alternative routes |

---

## 17. Version history

- **v4.3.4 (2026-10-24, current):** no-argument install always writes the placeholder — a model appears only when you pass it or set it yourself. Upgrade behavior unchanged (never touches `DEFAULT_MODEL`).
- **v4.3.3 (2026-10-24):** no shipped default model at all; every-provider model-id guide (README section 8); `sgpt-audit.sh` documented as the manual post-model-choice test.
- **v4.3.2 (2026-10-24):** strips leaked agent scaffolding lines (e.g. `</rfl:parameter>`) from every reply — fixes the `zsh:2: parse error near '>'` failure on Execute.
- **v4.3.1 and earlier:** OpenRouter direct route with layered credential search and CLI fallback; free/paid limit messages; stuck-request protection; code-fence stripping; JSON function-call shim on the CLI route.

Full detail lives in `CHANGELOG.md`. Facts verified live during development: Zen free models reject direct API calls (`403 FreeTierError`); OpenCode's built-in free models run with zero stored credentials; the bundled audit passes 44 checks with 1 expected SKIP (`--functions` off) on the author's machine — run it on yours (Section 11) for your own confirmation.

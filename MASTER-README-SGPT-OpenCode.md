# Master Guide: OpenCode + ShellGPT (sgpt) + OpenRouter / OpenAI
## Kali Linux — installation, provider setup, testing, daily use, switching, and uninstall

> **Status — package v4.3.3 (2026-10-24).** Changes since v4.3.1: **no shipped default model** — the user sets `DEFAULT_MODEL` in `.sgptrc` themselves (a placeholder is refused with a clear message, never silently replaced); a full every-provider model-id guide in README section 8 (where each provider's free model names come from and exactly how to write them); and `sgpt-audit.sh` documented as the **manual** test the user runs **after** choosing a model (never auto-run by install/upgrade). The v4.3.1 setup was verified end to end on the target Kali machine: the bundled audit finished **44 PASS | 0 FAIL | 1 SKIP** (the SKIP is `--functions`, which ships disabled — see Section 5.6). v4.3.3 behavior is verified on the build machine (unit tests + mocked-backend end-to-end + audit dry-run); the same live audit on Kali is the pending confirmation. This guide otherwise describes the v4.3.1 behavior throughout, including the layered OpenRouter credential search with automatic OpenCode-CLI fallback (Section 4.6), the explicit free/paid limit messages (Section 8), and the stuck-request protection in the adapter and the audit.

This guide combines the setup steps and the issues encountered while installing the ShellGPT-to-OpenCode adapter. Commands are written for the normal Linux account `kali`, not the `root` account.

> **Important:** OpenCode, ShellGPT, and the adapter are separate components. OpenCode is the model client; ShellGPT is the terminal assistant; `sgpt-free` is a launcher; `adapter.py` bridges ShellGPT's OpenAI-compatible request to the model backend. Routing is by model ID: `openrouter/*` models are called through OpenRouter's official API (native roles, sampling parameters, and tool/function calling) when a readable OpenRouter API key exists, and automatically fall back to the OpenCode CLI route when none does; every other provider/model runs through the OpenCode CLI, where function calling is provided by a JSON shim in the adapter. See README.md section 7 for the exact per-route support table.

---

# Section 1 — Required software and installation

## 1.1 What is required?

| Component | Purpose | Required? |
|---|---|---|
| Kali Linux | Operating system | Yes |
| Internet connection | Download software and call hosted models | Yes |
| `curl` | Download OpenCode installer and test local adapter | Yes |
| `python3` | Runs the adapter | Yes |
| `unzip` | Extracts the package | Yes |
| `pipx` | Installs ShellGPT in an isolated Python environment | Yes |
| OpenCode CLI | Runs provider models from the terminal | Yes for this adapter |
| OpenCode Desktop | Graphical app for OpenCode | Optional; can be installed alongside CLI |
| ShellGPT (`shell-gpt`, command `sgpt`) | Original terminal assistant | Yes for the adapter workflow |
| `click` Python package | Required dependency of the ShellGPT version encountered during this setup | Install/inject if the `No module named click` error occurs |
| `sgpt-opencode-adapter-fixed-v4.3.3.zip` | Contains adapter, launcher, installer, and guides | Yes |

## 1.2 Use the normal user

Open a terminal and run:

```bash
whoami
```

Expected output:

```text
kali
```

If it says `root`, type:

```bash
exit
```

Do not use `sudo su` for user-level OpenCode/ShellGPT setup. Installing OpenCode as root caused it to be configured under `/root`, where the normal user could not access it.

## 1.3 Install and verify system packages

```bash
sudo apt update
sudo apt install -y curl python3 unzip pipx
pipx ensurepath
```

Close and reopen the terminal if needed, or refresh the current shell:

```bash
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
```

Verify:

```bash
python3 --version
curl --version
unzip -v
pipx --version
```

**Expected:** Each command prints a version or help output. `pipx ensurepath` may say `~/.local/bin` is already in PATH; that is informational and not a failure.

## 1.4 Extract the adapter ZIP

Download `sgpt-opencode-adapter-fixed-v4.3.3.zip` to `~/Downloads`, then run:

```bash
cd ~/Downloads
unzip -o sgpt-opencode-adapter-fixed-v4.3.3.zip -d sgpt-v4.3.3
cd sgpt-v4.3.3
ls -l
```

Then install in one of two ways:

- **Fresh machine:** `bash install-kali.sh` installs everything end to end (or follow the manual steps in the rest of this guide).
- **Existing install (upgrade):** `bash apply-flint-fix.sh` backs up the current adapter and `.sgptrc` first, installs the new adapter, restarts it, and runs a health check. It never touches your `DEFAULT_MODEL` line and never hard-fails over a missing OpenRouter key — it prints a WARN and the adapter uses the automatic CLI fallback described in Section 4.6. After upgrading, test your chosen model yourself with `sgpt-audit.sh` (manual, never auto-run).

Expected package files:

```text
README.md
MASTER-README-SGPT-OpenCode.md
CHANGELOG.md
adapter.py
test_adapter.py
sgpt-audit.sh
apply-flint-fix.sh
start-adapter.sh
sgptrc.example
setup-guide.md
install-kali.sh
sgpt-free
```

If the ZIP has a different filename, use the exact filename shown by `ls`.

## 1.5 Install OpenCode CLI

Official install page: https://opencode.ai/download

For the CLI, as user `kali`:

```bash
curl -fsSL https://opencode.ai/install | bash
```

Then configure PATH for the current shell:

```bash
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$PATH"
hash -r
```

For Zsh (Kali's usual default), persist PATH:

```bash
grep -qxF 'export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"' ~/.zshrc || \
printf '\nexport PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"\n' >> ~/.zshrc
source ~/.zshrc
hash -r
```

Verify:

```bash
command -v opencode
opencode --version
```

Expected path for this user's install:

```text
/home/kali/.opencode/bin/opencode
```

The version number may differ from `1.19.4` or `2.1.4` because OpenCode releases change.

### If `opencode: command not found`

Run one command at a time:

```bash
ls -l "$HOME/.opencode/bin/opencode"
printf '%s\n' "$PATH"
source ~/.zshrc
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$PATH"
hash -r
command -v opencode
opencode --version
```

If the binary is missing, rerun the official installer as `kali` (not root). Do not keep reinstalling if the binary exists; fix PATH first.

### Do not paste multiple commands into one malformed line

A Zsh `parse error` happened when several commands were accidentally pasted together. Paste each command on its own line, or paste a complete block while preserving the line breaks.

## 1.6 Optional: Install OpenCode Desktop on Linux

OpenCode Desktop is separate from the CLI. Download the Linux build from the official page:

https://opencode.ai/download

Choose the Linux package that matches your system, such as `.deb` for Debian/Kali-based systems or AppImage if offered. If you download a `.deb` to `~/Downloads`, install it with:

```bash
cd ~/Downloads
sudo apt install ./NAME-OF-DOWNLOADED-FILE.deb
```

Replace the filename with the exact downloaded `.deb` name. Do not type the placeholder literally.

Verify the Desktop app by opening it from the applications menu. Install the CLI as well if you want to use `opencode run` and the ShellGPT adapter. The desktop app does not replace the adapter's need for a working CLI binary.

Official download page: https://opencode.ai/download

## 1.7 Install original ShellGPT with pipx

First check:

```bash
command -v sgpt
pipx list
```

If ShellGPT is not installed:

```bash
pipx install shell-gpt
```

Then verify:

```bash
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
command -v sgpt
sgpt --version
```

### If `ModuleNotFoundError: No module named 'click'`

This error occurred during the setup documented here. Fix the isolated pipx environment with:

```bash
pipx inject shell-gpt click
```

Then retry:

```bash
sgpt --version
```

If a later ShellGPT release installs correctly without this error, do not inject packages unnecessarily.

### If ShellGPT asks for an OpenAI API key

That usually means ShellGPT's config has not yet been written, or it is being run before the adapter configuration is in place. For the adapter workflow, the configuration in Section 4 supplies a local placeholder key and a local adapter URL. Do not put your real OpenRouter key in the ShellGPT config for the adapter mode.

---

# Section 2 — Configure OpenCode providers and API keys

OpenCode supports many hosted providers and local model runtimes; its catalogue changes over time. Check the official provider directory:
https://opencode.ai/docs/providers/

### First understand the three separate things

| Thing | What it means | Example |
|---|---|---|
| OpenCode CLI | The program/command that sends a prompt to a model | `opencode run ...` |
| Provider | The service that actually hosts or routes the model | OpenRouter, OpenCode, OpenAI, Google, Anthropic |
| Model ID | The specific model, including the provider prefix OpenCode expects | `openrouter/recursive/flint-v1.0:free` |

**You normally do not need a completely different terminal command for every provider.** The command remains `opencode run --model "PROVIDER/MODEL_ID" "your prompt"`; the provider/model ID and that provider's saved credentials change. OpenRouter is a provider inside OpenCode, not a separate Linux command.

**Credentials are provider-specific.** An OpenRouter key does not authenticate OpenCode/Zen, OpenAI, Anthropic, or any other provider. Connect each provider you plan to use.

## 2.1 OpenCode interface: connect a provider

Start the CLI interface:

```bash
opencode
```

Inside OpenCode, type:

```text
/connect
```

Choose the provider and follow its prompts. Then type:

```text
/models
```

Choose a model from that provider. To leave the interface, use its exit command or press `Ctrl+C`.

OpenCode stores provider credentials in its local auth configuration. Treat those files as secrets and do not publish them.

Official provider documentation:
https://opencode.ai/docs/providers/

## 2.2 OpenCode Zen

Zen is an optional OpenCode-curated provider. It is not required to use OpenCode or OpenRouter. Zen usage may require account setup and billing/credits; check the current Zen page before using it.

Official guide: https://opencode.ai/docs/zen/

Steps:

1. Open https://opencode.ai/zen/ (or follow the current Zen link from OpenCode's provider guide).
2. Sign in and create an API key in the Zen dashboard.
3. In the OpenCode terminal interface, run `/connect`.
4. Select **OpenCode Zen** and paste the Zen key into the prompt.
5. Run `/models` and choose a Zen model.
6. Test it using a simple prompt in the interface, or copy the exact model ID and test with `opencode run` as in Section 3.

Do not assume Zen is free. Review its pricing and account requirements first.

## 2.3 OpenRouter

OpenRouter offers a gateway to models from multiple providers, including some free models. A model marked `:free` is subject to availability, limits, and the provider's current policies; it is not a promise of unlimited service.

Official dashboard/docs:
- https://openrouter.ai/
- https://openrouter.ai/docs/quickstart
- API keys: open the OpenRouter dashboard and use **Keys / Create API Key** (the exact UI label may change).

Steps:

1. Sign in to OpenRouter.
2. Open the API Keys page and create a key.
3. Copy it once and store it securely.
4. In OpenCode, run `/connect`, choose **OpenRouter**, and paste the key.
5. Run `/models`, find the desired OpenRouter model, and select it.
6. Test the model as in Section 3.

The model used in the setup described in this guide was:

```text
recursive/flint-v1.0:free
```

Its OpenCode model ID was tested successfully as:

```text
openrouter/recursive/flint-v1.0:free
```

Test result previously observed: `hello`.

Do not share the API key in chat, screenshots, source code, or README files. If it leaks, revoke it in the provider dashboard and create a new one.

## 2.4 Other common providers: where to get keys

OpenCode's catalog contains many providers; not every provider is free and not every provider offers an API free tier. Check each provider's current pricing, supported models, regional availability, and API terms.

| Provider / route | Where to get credentials | Notes |
|---|---|---|
| OpenAI API | https://platform.openai.com/api-keys | API billing is separate from a ChatGPT subscription. Do not assume ChatGPT Free/Plus/Pro includes API credits. |
| OpenRouter | https://openrouter.ai/ | One key can route to many listed models; costs and free limits depend on the selected model. |
| OpenCode Zen | https://opencode.ai/zen/ | Optional curated gateway; check current billing/credit requirements. |
| Anthropic API | https://console.anthropic.com/ | API account/key and billing may be required. |
| Google Gemini API | https://aistudio.google.com/apikey | Free quotas and eligibility vary; review current terms. |
| xAI API | https://console.x.ai/ | API key and billing/availability depend on the account. |
| DeepSeek API | https://platform.deepseek.com/ | Use the official platform to create a key and check pricing/limits. |
| GroqCloud | https://console.groq.com/keys | Check current model availability and free-tier rate limits. |
| Cerebras | https://cloud.cerebras.ai/ | Check access, supported models, and limits. |
| Mistral AI | https://console.mistral.ai/ | Check API plan and model availability. |
| Together AI | https://api.together.ai/ | Check pricing and supported models. |
| Fireworks AI | https://fireworks.ai/ | Check pricing and model availability. |
| GitHub Models / Copilot routes | https://github.com/marketplace/models and https://github.com/features/copilot | Authentication method and model access depend on the specific integration/plan. |
| Ollama (local) | https://ollama.com/ | Runs supported models locally; a provider API key may not be needed, but local hardware and model downloads are required. |
| LM Studio (local) | https://lmstudio.ai/ | Can expose a local OpenAI-compatible endpoint; configuration differs from hosted providers. |

For other providers, use the official provider catalog and the provider's own console. Avoid third-party key sellers.

### Is every provider free?

No. OpenCode is the client and is free/open source, but hosted inference can be paid. Some providers/models have free quotas or promotional `:free` models, while others require credits, a subscription, or pay-as-you-go billing. Always verify pricing with the provider.

---

# Section 3 — Find, check, select, and test a model

This section answers four different questions:

1. **What models does OpenCode know about?** List the provider's catalogue.
2. **Which are advertised as free?** Check current provider/model pricing and the `:free` label where applicable.
3. **Which works for my account right now?** Send a real test prompt.
4. **How do I make ShellGPT use it?** Put the exact tested OpenCode model ID into ShellGPT's `DEFAULT_MODEL` setting (Section 4).

These are separate checks. A model appearing in a catalogue does not guarantee that your key has access to it or that the model endpoint is online at this exact moment.

## 3.1 Refresh and list models by provider

First see the commands your installed release supports:

```bash
opencode models --help
```

Refresh the available model catalogue and list models:

```bash
opencode models --refresh
```

List models for one provider only:

```bash
opencode models openrouter --refresh
opencode models opencode --refresh
opencode models openai --refresh
```

If a provider's ID is different in your installed release, use the provider name/ID shown by `/connect` and the output of `opencode models`. To view additional model metadata, including price information where available, use:

```bash
opencode models openrouter --verbose
```

You can also open the interactive interface:

```bash
opencode
```

Then enter:

```text
/connect
/models
```

Connect the provider first; `/models` is the easiest way to see models enabled for the current project and credentials. Select an entry shown there instead of guessing the spelling.

## 3.2 Find current free OpenRouter models

OpenRouter's list of zero-price models changes. Visit its live catalogue and apply the free/zero-pricing filter:

https://openrouter.ai/models?max_price=0

Some OpenRouter model IDs end with `:free`. This is a pricing/availability label, not a promise of unlimited requests. Rate limits, temporary endpoint failures, access rules, and model availability can change.

Now compare the website's model slug with OpenCode's output from:

```bash
opencode models openrouter --refresh
```

Use the **full OpenCode model ID** from OpenCode's output. It generally starts with `openrouter/`, followed by the OpenRouter model slug. Do not paste only the model's marketing name. If the website says the model is free but it does not appear in OpenCode's list, refresh the catalogue and verify the current provider/model ID before trying it.

OpenRouter also has a `openrouter/free` router that chooses a free model automatically at the OpenRouter API layer. Do not assume that its raw API slug is the same as the OpenCode `provider/model` ID. Use only the exact model ID that your installed OpenCode lists; otherwise select one specific model ending in `:free`.

## 3.3 Test one chosen model before using it in ShellGPT

Copy the exact ID shown by `opencode models` or `/models`, and replace `PASTE_EXACT_MODEL_ID_HERE` below:

```bash
opencode run --model "PASTE_EXACT_MODEL_ID_HERE" "Reply with exactly one word: hello"
```

For the OpenRouter model that worked during the earlier setup, the test was:

```bash
opencode run --model "openrouter/recursive/flint-v1.0:free" "Reply with exactly one word: hello"
```

The earlier test returned `hello`, but that does **not** guarantee that the same model remains free or available today. Refresh and re-test it before relying on it.

A successful response confirms that this model was reachable with the current configuration at the time of the test. If it fails, use the error to decide what to fix:

- `model not found` / unavailable: wrong, stale, or unsupported model ID; refresh and copy the exact one.
- `401` / unauthorized: provider key missing, invalid, revoked, or connected to a different provider.
- `402` / payment / insufficient credits: the chosen route may require credits or the account may not meet its billing requirements.
- `429` / rate limit: try later or check current account/model limits.
- timeout / provider error: retry; the provider may be busy or the endpoint temporarily unavailable.

## 3.4 Provider examples: same command, different model ID

These are examples of the **pattern**, not a guarantee that every sample model is currently enabled or free:

```bash
# OpenRouter: use the exact ID listed by `opencode models openrouter`
opencode run --model "openrouter/EXACT_MODEL_ID" "Reply with exactly one word: hello"

# OpenCode provider: use the exact ID listed by `opencode models opencode`
opencode run --model "opencode/EXACT_MODEL_ID" "Reply with exactly one word: hello"

# OpenAI provider in OpenCode: use the exact ID listed by `opencode models openai`
opencode run --model "openai/EXACT_MODEL_ID" "Reply with exactly one word: hello"

# Another connected provider: substitute its provider ID and model ID
opencode run --model "PROVIDER_ID/EXACT_MODEL_ID" "Reply with exactly one word: hello"
```

The actual IDs will not contain the words `EXACT_MODEL_ID` or `PROVIDER_ID`; these are placeholders. Do not run the sample placeholders literally.

**Key point:** the command syntax does not change per provider. The model ID chooses the provider/model route. `/connect` (or another supported authentication method) supplies credentials. A real prompt test tells you whether the route works now.

---

# Section 4 — Install and configure the ShellGPT adapter

This package runs **the original ShellGPT CLI** and uses `adapter.py` to forward its API-shaped request to the model backend — OpenRouter's API directly when a readable key exists, otherwise the OpenCode CLI (Section 4.6). The local adapter is intended to bind only to `127.0.0.1:8642`.

## 4.1 Copy adapter files into the user's home

Run as `kali`:

```bash
cd ~/Downloads/sgpt-v4.3.1
mkdir -p ~/.local/share/sgpt-opencode
mkdir -p ~/.local/bin
mkdir -p ~/.config/shell_gpt

cp adapter.py ~/.local/share/sgpt-opencode/adapter.py
cp sgpt-free ~/.local/bin/sgpt-free
chmod +x ~/.local/share/sgpt-opencode/adapter.py
chmod +x ~/.local/bin/sgpt-free
```

If your extracted folder has a different name, use that path instead of `~/Downloads/sgpt-v4.3.1`.

## 4.2 Set the adapter configuration and understand each line

The adapter uses the model ID that ShellGPT sends. ShellGPT's normal default comes from `DEFAULT_MODEL` in `~/.config/shell_gpt/.sgptrc`. The model must be a valid full OpenCode ID for the provider you connected.

Back up any existing config first, then open it:

```bash
mkdir -p ~/.config/shell_gpt
if [ -f ~/.config/shell_gpt/.sgptrc ]; then
  cp ~/.config/shell_gpt/.sgptrc ~/.config/shell_gpt/.sgptrc.before-adapter.bak
fi
nano ~/.config/shell_gpt/.sgptrc
```

For the adapter mode, the file should contain (v4.3.3 ships NO
default model — replace the placeholder with your own tested id,
see README section 8 for every provider):

```text
OPENAI_API_KEY=dummy-local
API_BASE_URL=http://127.0.0.1:8642/v1
DEFAULT_MODEL=SET_YOUR_MODEL_HERE
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
REQUEST_TIMEOUT=600
DISABLE_STREAMING=false
```

The Flint example from earlier testing was
`DEFAULT_MODEL=openrouter/recursive/flint-v1.0:free` — usable as
your own choice, but no longer a shipped default.

What each important line means:

- `OPENAI_API_KEY=dummy-local` — a non-empty placeholder used by ShellGPT's OpenAI-compatible client. It is **not** the real OpenRouter/OpenAI key.
- `API_BASE_URL=http://127.0.0.1:8642/v1` — send ShellGPT's API-shaped request to the local adapter, not directly to OpenAI.
- `DEFAULT_MODEL=openrouter/recursive/flint-v1.0:free` — the model ShellGPT requests through the adapter. Change this to the exact ID you tested in Section 3.
- `OPENAI_USE_FUNCTIONS=false` — function calling ships OFF in this package (the audit therefore skips its functions test). Set it to `true` and add function files under `~/.config/shell_gpt/functions/` to enable it — native tool calls on the OpenRouter route, JSON-shim calls on the OpenCode route (see Section 5.6).
- `USE_LITELLM=false` — keeps this setup on the direct OpenAI-compatible endpoint path.
- `REQUEST_TIMEOUT=600` — allows time for the relatively slow OpenCode run.
- `DISABLE_STREAMING=false` — ShellGPT may request streaming, but this adapter waits for the OpenCode response and then emits buffered chunks; it is not true token-by-token streaming.

For a different tested provider/model, edit **only** the `DEFAULT_MODEL` line first. Do not paste your actual OpenRouter key into this file: OpenCode stores the provider credential when you connect it using `/connect`.

## 4.3 Ensure PATH persists in new terminals

```bash
grep -qxF 'export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"' ~/.zshrc || \
printf '\nexport PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"\n' >> ~/.zshrc

source ~/.zshrc
hash -r
```

Verify:

```bash
opencode --version
sgpt --version
command -v sgpt-free
```

Expected:
- OpenCode prints its version.
- ShellGPT prints its version without asking for an OpenAI API key.
- `command -v sgpt-free` prints `/home/kali/.local/bin/sgpt-free`.

## 4.4 Run the live adapter test

```bash
sgpt-free --no-cache "Reply in one short line: say hi from Kali"
```

Expected: an AI response in the terminal, for example `Hi from Kali!`.

The first run may display:

```text
[sgpt-free] starting adapter...
```

This is a status message from the launcher. It means the local adapter was not responding to its health check, so the launcher tried to start it in the background. It is not an AI response and is not itself an error. Later calls usually do not print it if the adapter is still running.

Check health:

```bash
curl -s http://127.0.0.1:8642/health
```

Expected:

```json
{"status": "ok"}
```

If the live test fails, inspect:

```bash
tail -n 50 ~/.local/share/sgpt-opencode/adapter.log
```

## 4.5 Change or test a different model in ShellGPT

Do **not** expect `sgpt-free` to search for a free model on its own. Its job is to check/start the local adapter and then run the original `sgpt` command. The model is supplied by ShellGPT's config or by an explicit `--model` option.

Use this safe process whenever changing models:

1. Find a current model ID using Section 3.
2. Test it with `opencode run --model "EXACT_ID" "Reply with exactly one word: hello"`.
3. If the test succeeds, back up and edit the ShellGPT configuration:

```bash
cp ~/.config/shell_gpt/.sgptrc ~/.config/shell_gpt/.sgptrc.before-model-change.bak
nano ~/.config/shell_gpt/.sgptrc
```

Change this line:

```text
DEFAULT_MODEL=openrouter/recursive/flint-v1.0:free
```

to the exact ID that passed your test, for example:

```text
DEFAULT_MODEL=openrouter/EXACT_MODEL_SLUG:free
```

That sample is illustrative only; replace `EXACT_MODEL_SLUG` with a real model ID listed by OpenCode. Save nano with `Ctrl+O`, Enter, then exit with `Ctrl+X`.

Test through ShellGPT:

```bash
sgpt-free --no-cache "Reply with exactly one word: hello"
```

The response should come from the model selected in `DEFAULT_MODEL`. If it works in `opencode run` but not through ShellGPT, inspect the adapter log:

```bash
tail -n 80 ~/.local/share/sgpt-opencode/adapter.log
```

You can also request a one-off model if your installed ShellGPT accepts its `--model` option:

```bash
sgpt-free --model "EXACT_OPENCODE_MODEL_ID" --no-cache "Say hello"
```

Test this one-off option with `sgpt --help` first. For predictable everyday use, changing `DEFAULT_MODEL` is easier to verify.

### Does ShellGPT know automatically which models are online and free?

No. This adapter's `FREE_MODELS` list in `adapter.py` is a **static list**, not a live OpenRouter/OpenCode catalogue query. It can become stale. The adapter does not query pricing or automatically select the best free model. You must discover the current model, check its price/free label, test the live request, then set `DEFAULT_MODEL` as described above. A model appearing in any list still does not guarantee that its endpoint is responding right now.

## 4.6 How the request works

```text
sgpt-free
   -> original ShellGPT (sgpt)
   -> local adapter at 127.0.0.1:8642
   -> if the model ID starts with openrouter/ AND a readable
      OpenRouter API key was found:
        OpenRouter official Chat Completions API
        (roles, temperature/top_p and tool calls are native)
   -> if the model ID starts with openrouter/ but NO readable
      key was found:
        served through the OpenCode CLI route below instead
        (automatic fallback; the adapter logs one clear line)
   -> otherwise (opencode/*, openai/*, anthropic/*, any provider
      connected in OpenCode):
        opencode run -m <selected-model>
   -> model response returns to the terminal
```

**Where the adapter looks for the OpenRouter key** (the value is never printed or logged): the `OPENROUTER_API_KEY` environment variable; OpenCode's `~/.local/share/opencode/auth.json` (API-key entries, plus OAuth entries whose access token has not expired); an `apiKey` set for the OpenRouter provider in `~/.config/opencode/opencode.json` / `opencode.jsonc` (including `{env:...}` and `{file:...}` references); and OpenCode's credential database (`opencode.db`, read-only). OpenCode can hold a credential in a form none of these expose (for example an OAuth-only connect) — then the fallback above applies and everything still works, just through the slower CLI route. For the fast direct route, connect OpenRouter with an API key (`opencode` → `/connect`) or start the adapter with `OPENROUTER_API_KEY` set.

The OpenCode route launches a fresh `opencode run` for each request, so responses can be slow; the OpenRouter route answers at API speed. Both routes buffer the model response before returning it to ShellGPT (ShellGPT then streams it locally as SSE chunks). Shell-mode output is sanitized and code-mode output is de-fenced by the adapter on both routes. Function/tool calling is native on the OpenRouter route and provided by a JSON shim on the OpenCode route (see README.md section 7).

---

# Section 5 — Use ShellGPT day to day

## 5.1 Normal question

```bash
sgpt-free "Explain Linux file permissions in simple English"
```

Roman Urdu prompt example:

```bash
sgpt-free --no-cache "Roman Urdu mein batao Kali Linux kya hai"
```

The model's response language usually follows the prompt. The launcher status message language is independent of the model's answer.

## 5.2 Generate a shell command

```bash
sgpt-free -s "Show listening ports"
```

Read the generated command before accepting execution. Do not approve commands you do not understand, especially commands using `sudo`, `rm`, redirection, pipes, or scripts downloaded from the internet.

At the prompt you can choose **[E]xecute, [M]odify, [D]escribe, [A]bort**. Note what `--no-interaction` really does (verified against ShellGPT 1.5.1 source): it skips the prompt and **only prints** the generated command — it does **not** execute it. Execution happens only through the interactive **E** choice (or your own copy/paste).

## 5.3 Generate code

```bash
sgpt-free -c "Write a simple Python calculator"
```

## 5.4 Interactive REPL

```bash
sgpt-free --repl temp
```

Exit with `Ctrl+C`.

## 5.5 Use the original `sgpt` command

Once the adapter is running and the `.sgptrc` config points at the local endpoint, the original command also uses that configured endpoint:

```bash
sgpt "Explain the grep command"
```

If you want to be certain you are using the adapter path, use `sgpt-free`.

## 5.6 Complete switch reference (ShellGPT 1.5.1, as tested)

Every option from `sgpt --help`, with its real behavior in this setup. All of these are ShellGPT's own code; the adapter only affects the model request behind them.

| Option | Behavior here |
|---|---|
| *(no option)* prompt | Normal answer from the configured model |
| `--model <id>` | Any provider/model ID from `opencode models` (exact ID); routes per Section 4.6 |
| `--temperature`, `--top-p` | **OpenRouter route:** forwarded to the API. **OpenCode route:** accepted by sgpt but not forwarded (`opencode run` has no sampling flags) — the model's defaults apply |
| `--md` / `--no-md` | sgpt's own markdown rendering on/off — unchanged |
| `--editor` / `--no-editor` | Compose the prompt in `$EDITOR` (needs a real terminal) |
| `--cache` / `--no-cache` | sgpt's own local response cache — unchanged |
| `--version`, `--help` | Local, no model involved |
| `-s` / `--shell` | Generate a command, then the interactive **[E]xecute, [M]odify, [D]escribe, [A]bort** prompt; the adapter strips commentary/fences so only the command reaches sgpt |
| `--interaction` / `--no-interaction` | With `--no-interaction`, `-s` **prints the command only** — it never executes it |
| `-d` / `--describe-shell` | Plain-language description of the given command |
| `-c` / `--code` | Code only; adapter strips markdown fences if the model adds them |
| `--functions` / `--no-functions` | Needs `OPENAI_USE_FUNCTIONS=true` in `.sgptrc` + function files in `~/.config/shell_gpt/functions/`. Native tool calls on the OpenRouter route; JSON-shim tool calls on the OpenCode route |
| `--chat <id>` | Named session; history kept in `${TMPDIR:-/tmp}/chat_cache/<id>` — a reused ID keeps ALL old context |
| `--show-chat <id>` | Print a session's history (local) |
| `--list-chats` / `-lc` | List session IDs (local) |
| `--repl <id>` | Interactive session on a real terminal; `Ctrl+C` exits. Input comes from the terminal — piping answers into stdin does not work (piped stdin becomes prompt context; the `__sgpt__eof__` line separates piped context from interactive input) |
| `--role <name>` | Apply a saved role to the request |
| `--create-role <name>` | Interactively create a role (asks for its description) |
| `--show-role <name>` | Print a role (local) |
| `--list-roles` / `-lr` | List roles (local) |

The bundled `sgpt-audit.sh` tests these behaviors end to end (see README.md section 10).

---

# Section 6 — Configure original ShellGPT to use the OpenAI API directly

This uses the original `sgpt` CLI, but skips the OpenCode adapter and sends the request to OpenAI directly. You need a real OpenAI API key and API access/billing for the selected model. A ChatGPT subscription and API billing are separate products.

Official links:
- API keys: https://platform.openai.com/api-keys
- Model directory: https://developers.openai.com/api/docs/models
- List API models: https://developers.openai.com/api/reference/resources/models/methods/list

## 6.1 What is configured right now in adapter mode?

The earlier adapter configuration is expected to look like this:

```text
OPENAI_API_KEY=dummy-local
API_BASE_URL=http://127.0.0.1:8642/v1
DEFAULT_MODEL=openrouter/recursive/flint-v1.0:free
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
REQUEST_TIMEOUT=600
DISABLE_STREAMING=false
```

The three most important lines for deciding where requests go are:

| Current line | Current meaning | Direct OpenAI needs |
|---|---|---|
| `OPENAI_API_KEY=dummy-local` | Placeholder for the local adapter; not a real provider key | Replace with your real API key if editing the config for direct mode |
| `API_BASE_URL=http://127.0.0.1:8642/v1` | Sends `sgpt` to your local adapter | Remove it or set `API_BASE_URL=default` so the default OpenAI API URL is used |
| `DEFAULT_MODEL=openrouter/recursive/flint-v1.0:free` | Routes the adapter request through OpenCode to OpenRouter | Change it to a model ID available to your OpenAI API account |

The other lines can normally stay, although `REQUEST_TIMEOUT` can be reduced for direct API calls. `OPENAI_USE_FUNCTIONS=false` means you should not expect ShellGPT's function calling to be enabled by this setting.

## 6.2 Get a real API key and pick a model

1. Sign in at https://platform.openai.com/api-keys and create a key.
2. Check that API access/billing is enabled for your account.
3. Select a model from the current API model directory. For example, `gpt-6-luna` appears in the current model documentation, but use it **only if it is available to your API account**; never assume a model name is universally enabled.
4. Keep the key private. Do not paste it into this README, a screenshot, a public repository, or chat.

You can inspect model IDs exposed to your API key with the following command. This lists models; it does not guarantee every listed model is available on every endpoint or that you have quota for it:

```bash
printf 'OpenAI API key: '
read -rs OPENAI_API_KEY
printf '\n'
curl -sS https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | python3 -m json.tool | less
unset OPENAI_API_KEY
```

Press `q` to leave `less`. For ShellGPT, choose an API model compatible with the chat-completion endpoint used by your installed ShellGPT version. The actual test request below is the final check.

## 6.3 Option A — Switch the shared `.sgptrc` to direct OpenAI mode

**This is the simple mode-switching method, but it changes what `sgpt-free` uses too**, because both launchers call the same original `sgpt` and read the same ShellGPT config.

Back up the working adapter config:

```bash
cp ~/.config/shell_gpt/.sgptrc ~/.config/shell_gpt/.sgptrc.adapter.bak
nano ~/.config/shell_gpt/.sgptrc
```

Replace the existing adapter lines with the following. Replace both placeholders with your real secret/model ID:

```text
OPENAI_API_KEY=PASTE_YOUR_REAL_OPENAI_API_KEY_HERE
API_BASE_URL=default
DEFAULT_MODEL=PASTE_MODEL_ID_AVAILABLE_TO_YOUR_API_ACCOUNT
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
REQUEST_TIMEOUT=60
DISABLE_STREAMING=false
```

What you changed:

- Replaced `dummy-local` with your real OpenAI API key.
- Changed the local adapter URL to `API_BASE_URL=default` so the request goes directly to OpenAI.
- Changed the model from `openrouter/...` to an OpenAI API model ID such as `gpt-6-luna` **only if that model is available on your account**.
- Reduced the timeout from `600` to `60` seconds as a sensible starting point for direct API calls; it can be increased if required.

Save nano with `Ctrl+O`, Enter, then `Ctrl+X`. Test using the original CLI, not `sgpt-free`:

```bash
sgpt --no-cache "Reply with exactly one word: hello"
```

**Important:** when `.sgptrc` is in direct OpenAI mode, `sgpt-free` can still check/start the adapter in the background, but the subsequent `sgpt` call will use the direct OpenAI URL from `.sgptrc`. In other words, it will not really use OpenCode/OpenRouter for that request. Restore the adapter config in Section 6.5 to return to adapter mode.

## 6.4 Option B — Use direct OpenAI for a test without changing the adapter config (recommended if you want both)

This is often the safer option. It uses environment-variable overrides for just one command, while leaving the adapter `.sgptrc` untouched. ShellGPT gives environment variables priority over the config-file values.

Run this block; paste your key at the hidden prompt, and the key will not be echoed as you type:

```bash
printf 'OpenAI API key: '
read -rs OPENAI_API_KEY
printf '\n'
API_BASE_URL=default DEFAULT_MODEL="gpt-6-luna" OPENAI_API_KEY="$OPENAI_API_KEY" \
  sgpt --no-cache "Reply with exactly one word: hello"
unset OPENAI_API_KEY
```

Use another model ID in place of `gpt-6-luna` if it is not available to your API account. This command changes `API_BASE_URL`, `DEFAULT_MODEL`, and `OPENAI_API_KEY` for that invocation only; it does **not** rewrite `.sgptrc`. Do not replace `sgpt` with `sgpt-free` in this test, because `sgpt-free` is specifically the adapter launcher.

If you plan to use direct OpenAI frequently, Option A or a separate dedicated launcher is more convenient. If you mainly want the free-model adapter and only occasionally test OpenAI, Option B keeps the existing configuration intact.

## 6.5 Switch back to the OpenCode/OpenRouter adapter

If you used Option A and changed the shared config, restore the backup:

```bash
cp ~/.config/shell_gpt/.sgptrc.adapter.bak ~/.config/shell_gpt/.sgptrc
```

Check that these lines are back in the file:

```text
OPENAI_API_KEY=dummy-local
API_BASE_URL=http://127.0.0.1:8642/v1
DEFAULT_MODEL=openrouter/recursive/flint-v1.0:free
```

The `DEFAULT_MODEL` value should be the current model you successfully tested, not necessarily the historical Flint example. Then verify adapter mode:

```bash
sgpt-free --no-cache "Reply with exactly one word: hello"
```

If you used Option B, no restore is needed because `.sgptrc` was not changed.

# Section 7 — Provider/model switching summary

| Goal | Exact action |
|---|---|
| Connect an OpenCode provider | Run `opencode`, enter `/connect`, select that provider and authenticate |
| See available model IDs | Run `opencode models --refresh`; filter with `opencode models openrouter --refresh`, `opencode models openai --refresh`, etc. |
| Check model prices/free label | Inspect `opencode models openrouter --verbose` and the provider's current pricing page; for OpenRouter, use https://openrouter.ai/models?max_price=0 |
| Test one model now | `opencode run --model "EXACT_PROVIDER/MODEL_ID" "Reply with exactly one word: hello"` |
| Use that model in the adapter | Set `DEFAULT_MODEL=EXACT_PROVIDER/MODEL_ID` in `~/.config/shell_gpt/.sgptrc`, then run `sgpt-free --no-cache "..."` |
| Use direct OpenAI temporarily | Supply `OPENAI_API_KEY`, `API_BASE_URL=default`, and `DEFAULT_MODEL=...` as environment overrides to `sgpt` (Section 6.4) |
| Switch the whole ShellGPT config to direct OpenAI | Back up `.sgptrc`, replace placeholder key/local URL/model as in Section 6.3; note that `sgpt-free` then also uses the direct config |
| Switch back from direct mode | Restore `~/.config/shell_gpt/.sgptrc.adapter.bak` and confirm the local adapter URL is present |

**Mental model:** provider credentials decide which services you can access; the OpenCode model ID chooses the model/provider route; an `opencode run` test checks current availability; ShellGPT's `DEFAULT_MODEL` chooses the model sent by ShellGPT; `API_BASE_URL` decides whether ShellGPT talks to the local adapter or directly to OpenAI.

---

# Section 8 — Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `opencode: command not found` | PATH is not loaded or CLI installed for another user | Check `~/.opencode/bin/opencode`, source `~/.zshrc`, and ensure you are `kali`, not root |
| Access denied under `/root` | Normal user cannot access root's home | Do not change permissions; install/use OpenCode under `kali` |
| `sgpt: command not found` | ShellGPT not installed or `~/.local/bin` not in PATH | `pipx install shell-gpt`, then add `~/.local/bin` to PATH |
| `No module named 'click'` | Missing dependency in ShellGPT pipx environment | `pipx inject shell-gpt click` |
| ShellGPT asks for an OpenAI API key in adapter mode | `.sgptrc` is missing/wrong or ShellGPT reads another config | Verify `~/.config/shell_gpt/.sgptrc` contains a non-empty placeholder key and local `API_BASE_URL` |
| `sgpt-free: command not found` | Launcher has not been copied or PATH missing | Copy launcher to `~/.local/bin/sgpt-free`, `chmod +x`, refresh PATH |
| `[sgpt-free] starting adapter...` | Launcher did not find a healthy adapter and tried to start it | Usually normal on first use; check health endpoint if it repeats |
| Health check returns nothing | Adapter not running or startup failed | `tail -n 50 ~/.local/share/sgpt-opencode/adapter.log` |
| `opencode run` says model not found | Wrong/outdated model ID | Check `/models` or `opencode models` and use the exact ID |
| The model is listed but the test fails | The catalogue is not a live uptime guarantee; credentials, quota, or endpoint may fail | Check the specific error and retry; verify provider auth/pricing and test again |
| `sgpt-free` uses the wrong provider after editing `.sgptrc` | `sgpt-free` calls original `sgpt`, which reads the same config | Restore the adapter config or use Section 6.4 for one-off direct OpenAI tests |
| No free models show up / a previous free model fails | The catalogue and free endpoints change; adapter `FREE_MODELS` is static | Refresh `opencode models`, inspect the live provider free catalogue, test the exact model, then update `DEFAULT_MODEL` |
| 401 / unauthorized | Wrong, missing, revoked, or provider-mismatched key | Reconnect the correct provider using `/connect` |
| 402 / credits / billing error | Provider account has no available balance or access | Check the provider dashboard and pricing |
| 429 / rate limit | Provider rate limit or free-tier quota reached | Wait, reduce request frequency, or choose another available model |
| 403 / free-tier access error | The selected provider/model may restrict access or have changed its free policy | Test the model inside OpenCode, verify account/provider settings, and select another supported model if needed |
| Timeout or slow answer | Model/provider latency; adapter launches a fresh OpenCode run for each request | Wait for completion, inspect adapter log, try another available model |
| Zsh parse error after pasting commands | Multiple commands pasted as a malformed single line | Run each command on a separate line |
| OpenCode works in one terminal but not a new one | PATH export applied only to one shell session | Persist PATH in `~/.zshrc` as shown in Section 1.5 |
| Installer prints `[WARN] No readable OpenRouter credential found`, or the adapter log says `openrouter/*` is served via the OpenCode CLI route | OpenCode holds the credential in a form the adapter cannot read (e.g. OAuth-only connect) | Not a failure — the model works through the OpenCode CLI route, just slower. For the fast direct route: `/connect` OpenRouter with an API key, or start the adapter with `OPENROUTER_API_KEY` set. Never paste the key into `.sgptrc` for adapter mode |
| sgpt shows `FREE LIMIT HIT` | The free model's quota / rate limit is exhausted (the adapter turns the provider's 429/quota error into this explicit message) | Wait a few minutes and retry, or switch `DEFAULT_MODEL` / `--model` to another model |
| sgpt shows `LIMIT HIT (paid model)` | The paid model's rate limit, quota, or account credit is exhausted | Check the provider plan/balance, wait and retry, or switch model |
| Model answers with a refusal about "persona" or "injected instructions" | On the OpenCode route, a few safety-tuned models dislike sgpt's role text when it is flattened into one prompt | Use the OpenRouter route for that model if available (roles stay native there), or switch to another model |
| The E/M/D/A prompt or REPL ignores piped answers | By ShellGPT's design, piped stdin becomes prompt context and interactive answers are read from `/dev/tty` | Answer at the real terminal, or use `-s --no-interaction` when you only need the printed command |
| `--chat temp` answers seem to use old context | The `temp` chat ID reuses its saved history file | Use a fresh chat ID, or delete `${TMPDIR:-/tmp}/chat_cache/temp` |
| ShellGPT crashes at startup with a traceback mentioning `functions` | A broken file in `~/.config/shell_gpt/functions/` — ShellGPT loads all function files at startup | Fix or remove the newest function file; run `sgpt --list-roles` (a local command) to confirm sgpt starts again |

## Useful verification commands

```bash
whoami
python3 --version
curl --version
pipx --version
command -v opencode
opencode --version
command -v sgpt
sgpt --version
command -v sgpt-free
curl -s http://127.0.0.1:8642/health
tail -n 50 ~/.local/share/sgpt-opencode/adapter.log
```

Do not post API keys or other secrets with diagnostic output.

---

# Section 9 — Uninstall the adapter, ShellGPT, and OpenCode

Run these commands as the normal `kali` user. Review each section before running it. Uninstalling the adapter is separate from uninstalling OpenCode Desktop.

## 9.1 Stop the local adapter

```bash
fuser -k 8642/tcp 2>/dev/null || true
```

This stops the process listening on the adapter's local port, if one is running.

## 9.2 Remove adapter and launcher files

```bash
rm -rf ~/.local/share/sgpt-opencode
rm -f ~/.local/bin/sgpt-free
```

## 9.3 Remove ShellGPT

```bash
pipx uninstall shell-gpt
```

This removes the pipx-managed ShellGPT environment. It does not uninstall Python or pipx.

## 9.4 Remove ShellGPT config

If you want to remove the adapter config and ShellGPT settings/cache:

```bash
rm -rf ~/.config/shell_gpt
```

This deletes the whole ShellGPT configuration directory, including any saved chats/cache and any backup configs stored there. Back up anything you want to keep first.

## 9.5 Remove OpenCode CLI (optional)

Only if you want to remove the user-level CLI installation:

```bash
rm -rf ~/.opencode
```

This deletes the CLI installation stored in that directory. OpenCode credentials may be stored elsewhere, so check the current OpenCode documentation before assuming all credentials were removed.

OpenCode provider auth may be stored at:

```text
~/.local/share/opencode/auth.json
```

If you specifically want to remove locally saved OpenCode credentials, inspect the file first and then remove it only if you are sure:

```bash
ls -l ~/.local/share/opencode/auth.json
```

To remove it:

```bash
rm -f ~/.local/share/opencode/auth.json
```

This logs out/removes saved provider credentials for the user. It does **not** revoke API keys at the provider; revoke keys separately in each provider dashboard.

## 9.6 Remove the PATH line (optional)

If you added the PATH line from this guide and want to remove it:

```bash
nano ~/.zshrc
```

Delete only this line if present:

```bash
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
```

Save and reload:

```bash
source ~/.zshrc
```

`~/.local/bin` is often useful for other apps too, so only remove the PATH line if you no longer want it.

## 9.7 Uninstall OpenCode Desktop (optional)

Desktop removal depends on how it was installed:

- If installed from a `.deb`, use the package name shown by `dpkg -l | grep -i opencode`, then remove that package with `sudo apt remove PACKAGE_NAME`.
- If installed as an AppImage, close it and delete the downloaded AppImage file.
- Review the package name before removing anything. Do not remove unrelated packages.

## 9.8 Root-level installation from the earlier attempt

An earlier OpenCode install was performed as `root`. It can be left unused; it is not required for the `kali` setup. Do not change `/root` permissions to access it. If you later want to remove the root-level installation, inspect it from a root shell and remove only the confirmed OpenCode files/configs; do not delete unrelated root files.

---

# Section 10 — Known limitations and final checklist

## Known limitations

- Hosted models require internet access.
- Free model availability, quotas, names, and terms can change.
- OpenCode Desktop and OpenCode CLI are distinct installs; the adapter specifically runs the CLI.
- The adapter starts a new `opencode run` for each request, so latency can be high.
- The adapter buffers the model response before returning it (no true token-by-token streaming from the backend). Function/tool calling is native on the OpenRouter route and provided by a JSON shim on the OpenCode route (best effort, model-dependent).
- `--temperature` / `--top-p` are forwarded on the OpenRouter route. On the OpenCode route they are accepted by ShellGPT but cannot be forwarded, because `opencode run` exposes no sampling parameters.
- If no readable OpenRouter API key exists, `openrouter/*` models are served through the OpenCode CLI route automatically: fully working, but slower, and the direct-route behaviors above (native sampling, native tool calls) do not apply there.
- One stuck request cannot block later ones: on timeout the adapter kills the backend's whole process group, and the bundled audit restarts the adapter and continues if a test probe times out.
- When a provider limit is hit, the answer says so explicitly — `FREE LIMIT HIT` for free models, `LIMIT HIT (paid model)` for paid ones — instead of a raw provider error.
- `sgpt-free -s` generates shell commands. Read them carefully before execution.
- OpenAI API billing is separate from ChatGPT subscription access.
- Zen and OpenRouter are separate providers and require their own credentials.
- The adapter's `FREE_MODELS` list is static: it does not discover today's free models or guarantee that a model is online.
- `sgpt-free` does not choose a free model automatically; `DEFAULT_MODEL` in `.sgptrc` (or a one-off `--model`) determines the requested model.
- Direct OpenAI settings and adapter settings share the same ShellGPT config unless environment overrides are used. Editing `.sgptrc` for direct mode also changes what `sgpt-free` will use.
- The placeholder `OPENAI_API_KEY=dummy-local` is only for ShellGPT's local-adapter configuration; it is not a real OpenAI/OpenRouter key.

## Final checklist

- [ ] `whoami` returns `kali`.
- [ ] `python3`, `curl`, `unzip`, and `pipx` versions display.
- [ ] `opencode --version` works in a new terminal.
- [ ] OpenCode opens with `opencode`.
- [ ] Provider is connected using `/connect`.
- [ ] `/models` lists the intended model.
- [ ] Direct `opencode run -m "PROVIDER/MODEL_ID" "Reply with exactly one word: hello"` returns `hello`.
- [ ] `sgpt --version` works without missing-dependency or missing-key errors.
- [ ] `command -v sgpt-free` points to `~/.local/bin/sgpt-free`.
- [ ] `.sgptrc` points to `http://127.0.0.1:8642/v1` and uses the intended, previously tested `DEFAULT_MODEL` when adapter mode is selected.
- [ ] `sgpt-free --no-cache "Reply in one short line: say hi from Kali"` returns a response through the adapter.
- [ ] `curl -s http://127.0.0.1:8642/health` returns `{"status":"ok"}` while the adapter is running.
- [ ] If testing direct OpenAI, the command uses `sgpt` with `API_BASE_URL=default` and a real key; `.sgptrc` is either deliberately switched or left intact using Section 6.4.
- [ ] After switching from direct OpenAI back to adapter mode, `.sgptrc` again contains the local URL and a tested OpenCode model ID.

## Official references

- OpenCode download (CLI/Desktop): https://opencode.ai/download
- OpenCode providers: https://opencode.ai/docs/providers/
- OpenCode Zen: https://opencode.ai/docs/zen/
- OpenRouter: https://openrouter.ai/
- OpenRouter quickstart: https://openrouter.ai/docs/quickstart
- OpenAI API keys: https://platform.openai.com/api-keys
- OpenAI API docs: https://platform.openai.com/docs/
- ShellGPT project: https://github.com/TheR1D/shell_gpt

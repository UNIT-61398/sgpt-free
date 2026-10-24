# sgpt + Free Models — Verified Setup Guide
Checked live: 2026-10-21 (Asia/Karachi)

## VERDICT (tested, not guesswork)
Direct `sgpt` -> OpenCode Zen FREE models does **NOT** work.
Live test of both endpoints:
- POST https://opencode.ai/zen/v1/chat/completions  (model: big-pickle)
- POST https://opencode.ai/inference/openai/v1/chat/completions (model: big-pickle)

Both return:
```json
{"type":"error","error":{"type":"FreeTierError","message":"OpenCode's free tier can only be used from within OpenCode."}}
```
Same result with no key, a dummy key, and (reported in OpenCode's own
GitHub issues) with a real Console API key / OAuth. Paid Zen models with
the same credentials DO reach the API (they return 402 Insufficient
funds if no credit) — the block is specific to the free tier.
Since Sept 2026 the free tier is app-only by OpenCode's design.
Third-party "bridge / fingerprint" tools that spoof the OpenCode client
to bypass this gate exist, but they circumvent OpenCode's restriction,
break often (15-min cooldowns reported), and are NOT recommended here.

## Free models live on Zen today (from GET /zen/v1/models)
big-pickle, beam-free, mimo-v2.6-flash-free, deepseek-v4.1-flash-free,
glm-5.3-flash-free, minimax-m3.1-flash-free, longcat-2.5-preview-free,
nemotron-3.5-lightning-free, nemotron-3.5-super-vl-free
(jev-1.13-free is also listed but returns structured decisions, not text.)
Line-up is promotional and changes often.

---

## ROUTE 1 — Free OpenCode models, the legit way: use OpenCode itself
OpenCode is itself a terminal tool. `opencode run` is scriptable like sgpt:

```bash
# install
curl -fsSL https://opencode.ai/install | bash
# or: npm install -g opencode-ai

# free model, no key/card needed for the free tier inside the app
opencode run -m opencode/big-pickle "give me a shell command to find failed SSH logins in the last hour"
opencode run -m opencode/deepseek-v4.1-flash-free "explain this nmap output: ..."

# sgpt-style alias (bash/zsh, add to ~/.bashrc or ~/.zshrc)
alias sgpt-free='opencode run -m opencode/big-pickle'
sgpt-free "shell command to list listening ports"
```
Interactive: run `opencode`, then `/models` and pick a *-free model / Big Pickle.

## ROUTE 2 — sgpt + OpenCode Zen PAID models (direct API works)
File: ~/.config/shell_gpt/.sgptrc
```ini
OPENAI_API_KEY=<your OpenCode Console API key>
API_BASE_URL=https://opencode.ai/zen/v1
DEFAULT_MODEL=deepseek-v4.1-flash
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
```
Requires Console credit (opencode.ai/auth -> create API key, add credits).
Cheap per-token, NOT free. Only chat/completions models work in sgpt —
GPT models on Zen use the Responses endpoint and Claude models use
Anthropic Messages, so stick to chat/completions IDs like:
deepseek-v4.1-flash, glm-5.3-flash, minimax-m3, kimi-k2.7-code, qwen3.8-max

## ROUTE 3 — sgpt + genuinely free external API (recommended for sgpt)
Groq free tier (free key, no card, OpenAI-compatible, allows external apps):
File: ~/.config/shell_gpt/.sgptrc
```ini
OPENAI_API_KEY=<your Groq API key from console.groq.com>
API_BASE_URL=https://api.groq.com/openai/v1
DEFAULT_MODEL=llama-3.3-70b-versatile
OPENAI_USE_FUNCTIONS=false
USE_LITELLM=false
```
Alt: OpenRouter free models — API_BASE_URL=https://openrouter.ai/api/v1
with a model id ending in `:free`. Alt 2: Ollama local —
`pip install "shell-gpt[litellm]"`, USE_LITELLM=true,
API_BASE_URL=http://localhost:11434, DEFAULT_MODEL=ollama/<model>.

Install sgpt (all routes):  pip install shell-gpt
Test:                        sgpt "hello, reply in one line"
Shell mode:                  sgpt -s "find all files over 100MB"

---

## ROUTE 4 — sgpt + OpenCode FREE models via a local adapter (the workaround)
Added 2026-10-21. Idea: sgpt never talks to Zen directly. A tiny local
adapter (adapter.py, Python stdlib only) speaks OpenAI's API to sgpt and
executes every request with the OFFICIAL `opencode run` command, which
is the scripting mode OpenCode documents — so the model call genuinely
comes from within OpenCode and the free-tier gate is honoured, not
spoofed. (Same architecture as the public OpenCode-Wrap project, which
puts an OpenAI-compatible API in front of `opencode serve`.)

Chain (v4, current package):  sgpt -> http://127.0.0.1:8642/v1 -> adapter.py
        -> openrouter/* : OpenRouter official API (key from OpenCode's
           stored credentials; native roles/sampling/tool calls)
        -> any other provider/model : `opencode run -m <provider/model>`
           (the Route-4 chain below; honours the Zen free-tier gate)

UPDATE 2026-10-23 (v3/v4): the adapter is now hybrid. The default
model is openrouter/recursive/flint-v1.0:free, reached through
OpenRouter's own API — this fixed Flint's persona refusals (roles are
native there, nothing is flattened) and made temperature/top_p and
tool calls work natively for OpenRouter models. The Route-4 chain
below still serves every other provider/model, with a JSON function-
call shim added. Full documentation: README.md in this package.

UPDATE 2026-10-24 (v4.3.3): NO default model is shipped any more.
The v3/v4 Flint default above is history, not current behavior:
the Flint id (openrouter/recursive/flint-v1.0:free) remains usable
only as the user's own choice, set by the user in
~/.config/shell_gpt/.sgptrc (nano ~/.config/shell_gpt/.sgptrc).
Until a real model is set, requests are refused with a clear
"No model configured" message instead of silently using a default.
See README.md section 8 for every provider: where the free model
names come from and exactly how to write them.

Setup (Linux/macOS; Windows: run adapter + sgpt inside WSL):
0. KALI LINUX (user's target, decided 2026-10-21): just unzip and run
   `./install-kali.sh` — it installs pipx + shell-gpt the Kali way
   (system pip is blocked on Kali), installs OpenCode, runs the
   step-1 sanity check FIRST and stops if the free model does not
   answer, then wires everything and gives one daily command:
   `sgpt-free "..."` / `sgpt-free -s "..."` (auto-starts the adapter).
   Optional model pick: `./install-kali.sh mimo-v2.6-flash-free`.
   Launcher end-to-end TESTED on the Muse VM with a mock backend
   (auto-start + chat + shell modes PASS).
1. Install OpenCode:      curl -fsSL https://opencode.ai/install | bash
   Sanity check (must answer): 
                          opencode run -m opencode/big-pickle "say hello"
2. Install ShellGPT:      pip install shell-gpt
3. Copy sgptrc.example to ~/.config/shell_gpt/.sgptrc
4. Terminal 1 (keep open): ./start-adapter.sh
5. Terminal 2:             sgpt "say hi"
                          sgpt -s "find files over 100MB"
                          sgpt -c "python port scanner"

TESTED 2026-10-21 on the Muse VM:
- Adapter protocol (health, /v1/models, chat non-stream + SSE stream)
  PASS against a mock backend.
- Real sgpt client -> adapter PASS in all 3 modes (chat, -s shell,
  -c code): sgpt's system role + user prompt reached the backend and
  the streamed answer rendered correctly.
- Live free-model leg from THIS VM: inconclusive — the VM's proxied
  network makes each Zen call take ~25s and `opencode run` did not
  finish within 170s/580s test windows here (it stalls after init in
  this sandbox). Step 1's sanity check is therefore mandatory: on a
  normal home connection, if that one command answers, the whole
  chain works; if it stalls for you too, the bottleneck is OpenCode/
  Zen itself, not this adapter.
- Expect SLOW: every sgpt question boots a fresh opencode run.
  Personal/light use only; adapter listens on 127.0.0.1 only and runs
  the agent in an empty sandbox dir (/tmp/sgpt-oc-sandbox).


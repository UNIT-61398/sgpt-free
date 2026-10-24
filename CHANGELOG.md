# Changelog

## v4.3.4 — no-argument install always writes the placeholder (2026-10-24)

Correction to a v4.3.3 behavior that broke the user's no-default
rule. v4.3.3's installer reused a real DEFAULT_MODEL from an existing
config on a no-argument reinstall ("Keeping your existing model").
On the user's machine this made a model appear that he had not set
in that install — exactly the "khud ho raha ha" he objected to,
even though the model was his own earlier choice carried forward,
not a package default. Reverted: a no-argument install now ALWAYS
writes DEFAULT_MODEL=SET_YOUR_MODEL_HERE, so a model appears only
when the user sets it himself (nano ~/.config/shell_gpt/.sgptrc)
or passes it as an install argument. The previous config is still
backed up to .sgptrc.before-install.bak first, so the old model is
recoverable. apply-flint-fix.sh is unchanged: an upgrade still never
touches an existing DEFAULT_MODEL line (that is an upgrade of a
working setup, not a fresh install).

## v4.3.3 — no default model + every-provider guide + audit as manual test (2026-10-24)

The package ships NO default model any more, and the user sets their
own model. Nothing is silently chosen for the user.

(a) Adapter: `DEFAULT_MODEL` is empty by default (overridable only by
an explicit `SGPT_OC_MODEL` env value for advanced setups). A request
with no model, or with the placeholder `SET_YOUR_MODEL_HERE`, is
refused with a clear message: "No model configured: set DEFAULT_MODEL
in ~/.config/shell_gpt/.sgptrc (run: nano ~/.config/shell_gpt/.sgptrc)
to a real model id ... or pass --model <provider/model-id>".
`backend_model` is now called inside the `do_POST` try block, so that
refusal surfaces to sgpt as a 502 with the message instead of a
dropped connection. `/health` reports `default_model: null` when
nothing is configured; `/v1/models` is a discovery list of known
free ids, not a default.

(b) Scripts never force a model: `apply-flint-fix.sh` and
`install-kali.sh` NEVER overwrite an existing `DEFAULT_MODEL` line
(apply leaves the line untouched; install reuses an existing real
model on a no-argument reinstall and only writes the placeholder
when truly no model exists). `sgptrc.example` uses
`DEFAULT_MODEL=SET_YOUR_MODEL_HERE` with nano instructions.
`sgpt-audit.sh` refuses the placeholder with the same nano
instruction instead of "testing" it.

(c) Docs: README section 8 rewritten — the universal
`provider/model-id` format rule, where every provider's model names
come from (`opencode models`, `opencode models <provider>`, the
`/models` TUI command, openrouter.ai/models for `:free` ids), how to
test an id before adopting it, and the section 8.2 provider table
(opencode Zen built-ins, openrouter `:free` + the `openrouter/free`
router, groq free tier, google AI Studio free tier, ollama local,
and every other provider by the same method) as a snapshot dated
2026-10-24, with the list commands as the source of truth. README
section 10 documents `sgpt-audit.sh` as the MANUAL test the user
runs AFTER choosing a model — it is shipped in the package, copied
to `~/.local/share/sgpt-opencode/` by the installer, and never
auto-run by install or upgrade. Install step 6 no longer auto-runs
a live test; it points at the audit instead.

(d) The v4.3.2 scaffolding fix (`strip_scaffolding`, which removes
leaked agent tag lines such as `</rfl:parameter>` from every reply
before sgpt sees it) is carried over unchanged.

(e) `setup-guide.md` stale claim fixed (the v3/v4 "default model is
Flint" paragraph is kept as history with a v4.3.3 update after it:
no default shipped; Flint usable only as the user's own choice),
and install preserves an existing model on no-argument reinstall.

Verification on the build machine: adapter unit tests (including 2
new no-model tests), OpenRouter-route end-to-end 8/8, audit dry-run
against mocked backends, a live scaffolding proof (junk backend
emitting a command plus a `</rfl:parameter>` line returns only the
clean command), and a live no-model proof (empty default + request
without a model returns 502 containing "nano" and "DEFAULT_MODEL").
The live audit on the target Kali is the pending confirmation.

## v4.3.2 — strip leaked agent scaffolding (2026-10-24)

Live report on v4.3.1: `sgpt-free -s` generated a correct command,
the user pressed E, and zsh failed with `zsh:2: parse error near '>'`.
The same signature had already appeared once before (an nmap test),
without the fragment being visible. This time the paste showed it:
the generated text contained a second line, `</rfl:parameter>`.

Root cause: on the OpenCode CLI route the answer comes from an agent,
and agents sometimes leak XML-style fragments of their internal
tool-call serialization into the final answer. The adapter's
sanitizers handled markdown fences and English commentary, but not a
standalone tag line — so the fragment reached sgpt, was executed, and
zsh choked on the `<` (a redirect operator) in it. The leak sits in
the backend reply, not in any sgpt switch, so it could surface in
-s, -c, -d, or chat alike.

Fix (adapter only): every reply is now passed through
`strip_scaffolding` before the mode sanitizers, on both routes and in
every mode — a line that is exactly one harness tag (rfl, parameter,
tool_call, function, invocation, tool, response, namespaced or not)
is removed everywhere; any other standalone tag line is removed in
shell mode, where it can never be a valid command (code mode keeps
real HTML/XML, chat mode keeps everything except harness tags); a
closing tag glued to the end of a shell command is cut off.
Legitimate redirections (`> out.txt`, `< in.txt`) are untouched.
Verification: unit tests 27/27 (7 new), junk-mock backend through the
live adapter returns the clean command in shell and chat modes, full
audit dry-run 44 PASS | 0 FAIL | 1 SKIP.

## v4.3.1 — audit check accepts quoted echo (2026-10-23)

Audit-only release; `adapter.py` is byte-identical to v4.3 (no reinstall
needed — replace `sgpt-audit.sh` and re-run the audit).

Live v4.3 audit: Flint generated `echo "SGPT_SHELL_OK"` — a correct
command, produced quickly (no timeout this time; the v4.3 framing
worked) — but both `-s` checks still failed because they matched the
exact string `echo SGPT_SHELL_OK` without quotes. A generated command
is equally correct as `echo X`, `echo "X"`, or `echo 'X'`. The two
shell checks now match any of those forms (regex), while still
rejecting a wrong command (e.g. `print X`) or a wrong token.
Dry-run after the change: 44 PASS | 0 FAIL | 1 SKIP.

## v4.3 — FINAL: shell-generation reliability (2026-10-23)

Live v4.2 audit on the user's Kali: 42 PASS | 2 FAIL | 1 SKIP — both
FAILs in `-s` shell generation on the CLI fallback route, both traced
to the model end, and both now fixed at the root:

- **Adapter: shell framing.** Asked for "a command that prints X",
  Flint answered `print X` (it copied the request's verb). The CLI
  route's prompt now states, for shell-generation requests only: the
  request describes what the command must do (it is not the command
  itself); output exactly one valid bash/zsh command; when the command
  must display text, use `echo` with the text in quotes. This improves
  real daily `-s` use, not just the audit.
- **Audit: unambiguous `-s` probes.** Both shell probes now ask for a
  command "that prints SGPT_SHELL_OK using echo", removing the
  echo-vs-print ambiguity from the test itself.
- **Audit: realistic time budgets.** The `-s` print probe and all PTY
  probes (shell / REPL / editor) now allow 240 s — free models behind
  the `opencode run` agent route can be slow, and a probe timeout was
  measuring speed, not correctness.
- Verification: unit tests 20/20 (2 new framing tests), OpenRouter
  end-to-end 8/8, full audit dry-run 44 PASS | 0 FAIL | 1 SKIP.

## v4.2 — limit messages + stuck-request-proofing (2026-10-23)

Field report from the user's Kali (v4.1): install OK (credential WARN →
CLI fallback engaged, as designed), audit passed everything up to
`--chat`, which timed out at 150 s — and the audit then appeared stuck,
because one slow backend request holds the adapter's single request
gate and every later test queues behind it.

- **Clear limit reporting (user request).** When a provider limit is
  hit, sgpt now shows an explicit message instead of a raw error:
  `FREE LIMIT HIT: ...` for free models (quota/rate exhausted — wait or
  switch model) and `LIMIT HIT (paid model): ...` for paid models
  (rate/quota/credit exhausted — check plan/balance). Detection:
  OpenRouter HTTP 402/429 and error bodies on the direct route, plus
  limit-pattern scanning of `opencode run` output on the CLI route.
- **Timeout kills the whole process group.** `run_opencode` now uses
  `Popen(start_new_session=True)`; on timeout it SIGKILLs the process
  group, so no orphaned OpenCode child can keep the gate hostage.
- **Audit self-heals.** After any probe timeout the audit restarts the
  adapter (clearing any stuck request) and continues with the remaining
  tests. The `--chat` probe gets a 240 s budget.
- `apply-flint-fix.sh` closing line pointed at the old audit filename
  (`audit-flint-v2.sh`); fixed to `sgpt-audit.sh`.
- Tests: 18 unit tests (5 new limit-mapping tests). OpenRouter e2e 8/8;
  full mock audit re-run.

## v4.1 — credential discovery + no-hard-fail routing (2026-10-23)

Found on the user's Kali: v4's `apply-flint-fix.sh` stopped with
"OpenRouter API key not found" even though OpenCode itself could run
Flint fine. Cross-checked against every earlier version: the v2 setup
that provably worked live never read a raw key at all — it routed
everything through `opencode run`, so OpenCode's own credential
handling did the work. The v3/v4 direct route only looked for an
API key in `auth.json` under standard field names, which misses
real-world storage variants.

Fixes:

- **Layered credential discovery** (`_find_openrouter_key`): tries, in
  order — `OPENROUTER_API_KEY` env; OpenCode `auth.json` (API-key
  entries, any `sk-or-…` value, and unexpired OAuth `access` tokens);
  OpenCode config files (`provider.openrouter.options.apiKey`,
  including `{env:VAR}` / `{file:path}` references, JSONC-tolerant);
  and newer OpenCode builds' SQLite credential database
  (`credential` / `account` tables, read-only). The source is reported
  ("found via …"), the key itself is never printed or logged.
- **No more hard failure:** if no readable credential exists, the
  adapter now serves `openrouter/*` through the OpenCode CLI route
  (the proven v2 behavior) and logs one clear line explaining this,
  instead of returning an error for every request. When a readable
  key exists, the fast native direct route is used.
- **`apply-flint-fix.sh`:** the credential check is now warn-and-
  continue (it reports the discovery source, or explains the CLI
  fallback). The adapter health check remains the hard gate.
- **Tests:** 13 unit tests (new: OAuth entry, config `{env:}` key,
  credential-database lookup, handler-level fallback when no key).
  OpenRouter end-to-end suite re-verified 8/8; full audit dry-run
  re-run against the updated package.

## v4 — merged final (2026-10-23)

Base: the v3 Flint adapter (OpenRouter direct route), reviewed line by
line and merged with the independently built/verified fixes from the
OpenCode-route package. Every change below was regression-tested
(see README section 10 for the test summary).

Added on top of v3:

- **Code-mode cleanup on both routes:** `-c` replies wrapped in
  markdown fences now have the fences stripped before reaching sgpt
  (previously only shell output was sanitized).
- **Function calling on the OpenCode route:** v3 silently dropped
  tool specs for non-OpenRouter models. The fallback now uses a JSON
  shim — functions are listed in the prompt, a JSON call reply is
  converted into a real OpenAI `tool_calls` response, sgpt executes
  the local function, and its result is rendered back into the
  conversation (assistant call turns included). Native on OpenRouter,
  best-effort shim on the OpenCode route; neither route drops the
  request silently anymore.
- **Every provider/model, explicitly:** routing is by model id —
  `openrouter/*` goes direct; ANY other provider/model id that
  OpenCode supports (`opencode/*`, `openai/*`, `anthropic/*`,
  `google/*`, ...) runs through the official OpenCode CLI. Switching
  is just `--model` or `DEFAULT_MODEL` with the exact id from
  `opencode models`. Installer accepts any of these as its argument.
- **Installer:** English throughout; default model is Flint;
  backs up an existing `.sgptrc` (`.sgptrc.before-install.bak`)
  before rewriting; installs `test_adapter.py` + `sgpt-audit.sh`
  next to the adapter for later re-runs.
- **Audit (`sgpt-audit.sh`, replaces the Flint-only audit):**
  model-agnostic (tests whatever `DEFAULT_MODEL` is configured),
  runs the offline unit tests, uses a unique chat id (no stale
  `--chat temp` cache), tests `-s` both print-only and through a
  real PTY (E/M/D/A answered with Abort — nothing executes), and
  covers `--repl`, `--editor`, roles and `--functions` for real
  instead of skipping them.
- **Docs:** README rewritten for the hybrid routing, with an honest
  per-route support table (temperature/top_p forwarded on OpenRouter;
  accepted-but-not-forwarded on the OpenCode route because
  `opencode run` exposes no sampling flags). MASTER guide corrected
  (`--no-interaction` prints only, never executes; full switch
  reference added).

## v3 — Flint adapter fix

- Switched `openrouter/*` requests from `opencode run` to the official
  OpenRouter Chat Completions endpoint. The key is read from
  `OPENROUTER_API_KEY` or OpenCode's `auth.json`; never copied to
  `.sgptrc` or printed.
- Kept original message roles intact for OpenRouter models, fixing
  chat-session context and the persona/refusal-style replies caused
  by the old single-prompt wrapper.
- Forwarded `temperature`, `top_p`, token limits, stop settings,
  JSON response format, `tools`/`tool_choice`, and legacy
  `functions`/`function_call` fields.
- Preserved OpenAI-style JSON completion structure, including
  tool/function calls; SSE streaming shape with tool-call chunks
  and `[DONE]`.
- Shell mode sanitizes model commentary before returning command
  text; the interactive confirmation workflow stays sgpt's own.
- OpenRouter HTTP/rate-limit/provider errors surfaced without
  exposing credentials; client disconnects logged without noisy
  tracebacks.
- Mocked regression tests for credential lookup, route/model
  mapping, parameter/tool forwarding, shell sanitization, JSON
  and SSE responses.

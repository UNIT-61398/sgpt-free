#!/usr/bin/env python3
"""ShellGPT-compatible local adapter: every provider, every model.

Routing:
- ``openrouter/*`` model IDs are called through OpenRouter's official
  Chat Completions API (native roles, sampling parameters and tool
  calls) when a credential can be read — from OPENROUTER_API_KEY,
  OpenCode's auth.json (API-key or OAuth entry), OpenCode's config
  (provider.openrouter apiKey), or OpenCode's credential database.
  Secrets are never printed. If NO readable credential exists,
  ``openrouter/*`` transparently uses the OpenCode CLI route below
  instead of failing (that is how the v2 setup ran successfully).
- Every other model ID (``opencode/*`` Zen free models, or any provider
  connected in OpenCode — OpenAI, Anthropic, Google, ...) runs through
  the official OpenCode CLI, so any model OpenCode can run works here.

Shell output is sanitized and code output is de-fenced before reaching
ShellGPT on both routes. On the OpenCode fallback route, function
calling uses a JSON shim (see _fallback_response); on OpenRouter it is
native. The adapter only listens on loopback. ShellGPT remains
responsible for its interactive [E/M/D/A] confirmation and execution.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Semaphore
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PORT = int(os.getenv("SGPT_OC_PORT", "8642"))
# No shipped default model (v4.3.3): the user sets DEFAULT_MODEL in
# ~/.config/shell_gpt/.sgptrc (or passes --model per command).
# SGPT_OC_MODEL may still set an adapter-side default for advanced
# setups, but the package itself ships with none: an unset or
# placeholder model is refused with a clear message, never silently
# replaced by a default.
DEFAULT_MODEL = os.getenv("SGPT_OC_MODEL", "")
MODEL_PLACEHOLDER = "SET_YOUR_MODEL_HERE"
NO_MODEL_MESSAGE = (
    "No model configured: set DEFAULT_MODEL in ~/.config/shell_gpt/.sgptrc "
    "(run: nano ~/.config/shell_gpt/.sgptrc) to a real model id, e.g. "
    "opencode/beam-free or openrouter/recursive/flint-v1.0:free, "
    "or pass --model <provider/model-id> for one command."
)
OPENCODE_BIN = os.getenv("SGPT_OC_BIN", os.path.expanduser("~/.opencode/bin/opencode"))
TIMEOUT = int(os.getenv("SGPT_OC_TIMEOUT", "600"))
SANDBOX = os.getenv("SGPT_OC_SANDBOX", "/tmp/sgpt-oc-sandbox")
OPENROUTER_URL = os.getenv("SGPT_OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
os.makedirs(SANDBOX, exist_ok=True)

# Avoid stampeding a free model with concurrent requests.
gate = Semaphore(1)

FREE_MODELS = [
    "openrouter/recursive/flint-v1.0:free",
    "opencode/big-pickle",
    "opencode/beam-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/glm-5.3-flash-free",
    "opencode/minimax-m3.1-flash-free",
    "opencode/longcat-2.5-preview-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/nemotron-3.5-super-vl-free",
    "opencode/nemotron-3-ultra-free",
]


def backend_model(requested: str | None) -> str:
    m = (requested or DEFAULT_MODEL).strip()
    if not m or m == MODEL_PLACEHOLDER:
        raise RuntimeError(NO_MODEL_MESSAGE)
    if m.startswith(("openrouter/", "opencode/")):
        return m
    # A bare OpenRouter model id ending in :free is likely intentional.
    if m.endswith(":free"):
        return f"openrouter/{m}"
    if "/" in m:
        return m
    return f"opencode/{m}"


def flatten_messages(messages: list[dict]) -> str:
    """Serialize messages for the CLI fallback without persona/jailbreak text."""
    parts: list[str] = []
    for msg in messages:
        role = str(msg.get("role", "user")).upper()
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = "".join(
                str(p.get("text", "")) for p in content if isinstance(p, dict)
            )
        if not content and msg.get("tool_calls"):
            # Assistant function-call turns carry no text; render the call
            # so the model can see what already ran (fallback shim flow).
            rendered = []
            for call in msg.get("tool_calls") or []:
                fn = (call or {}).get("function") or {}
                rendered.append(
                    f"[called function {fn.get('name', '?')} "
                    f"with arguments {fn.get('arguments', '{}')}]"
                )
            content = "\n".join(rendered)
        parts.append(f"{role}:\n{content}")
    transcript = "\n\n".join(parts)
    shell_note = ""
    if output_mode(messages) == "shell":
        # Observed live (Flint, CLI route): asked for "a command that prints
        # X", the model answered "print X" - it copied the request's verb
        # instead of producing the standard shell command. Clarify once,
        # here, so real -s use benefits too, not just the audit.
        shell_note = (
            " The request describes what the command must do - it is not "
            "the command itself. Output exactly one valid bash/zsh command; "
            "when the command must display text, use echo with the text "
            "in quotes."
        )
    return (
        "Respond to the conversation below, following its requested output format. "
        "Do not execute commands or use tools; return text only. For shell-command "
        "generation, return the command only because the calling CLI handles its "
        f"own review and execution.{shell_note}\n\n"
        + transcript
    )


def _message_text(message: dict) -> str:
    content = message.get("content") or ""
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    return str(content)


def output_mode(messages: list[dict]) -> str:
    system_text = "\n".join(
        _message_text(m) for m in messages if m.get("role") == "system"
    ).lower()
    if (
        "shell command generator" in system_text
        or "ensure the output is a valid shell command" in system_text
        or (
            "provide only" in system_text
            and "commands" in system_text
            and "without any description" in system_text
        )
    ):
        return "shell"
    if "code generator" in system_text or "provide only code as output" in system_text:
        return "code"
    return "chat"


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_FENCED_BLOCK_RE = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?[ \t]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE_LINE_RE = re.compile(r"^[ \t]*`([^`\n]+)`[ \t]*$", re.MULTILINE)
_META_LINE_RE = re.compile(
    r"^\s*(?:wait\s*[—-]|so the final answer\b|the final answer\b|"
    r"explanation\s*:|reasoning\s*:|analysis\s*:|note\s*:)", re.IGNORECASE
)


# Agent-harness scaffolding: agent backends (e.g. the OpenCode agent on
# the CLI route) sometimes leak XML-style fragments of their internal
# tool-call serialization into the final answer, e.g. a stray
# </rfl:parameter> line after the real command. In shell mode that line
# is EXECUTED, and the shell dies with "parse error near '>'" (zsh
# reports it at line 2 of the executed text). The leak sits in the
# backend reply, not in any sgpt switch, so it can surface in -s, -c,
# -d, or chat alike - the strip below therefore runs for every mode.
_TAG_NAME = r"[A-Za-z][A-Za-z0-9_:\-\.]*"
_STANDALONE_TAG_RE = re.compile(rf"^\s*</?{_TAG_NAME}(\s+[^<>]*)?>\s*$")
# Tag names that are harness vocabulary, never document content. A bare
# line with one of these (optionally namespaced, e.g. </rfl:parameter>)
# is scaffolding in every mode. Generic element names (div, result,
# content, ...) are NOT in this list, so real HTML/XML keeps working.
_HARNESS_TAG_NAMES = (
    "rfl", "parameter", "tool_call", "toolcall", "function_call",
    "function", "invocation", "tool", "response",
)
_HARNESS_TAG_RE = re.compile(
    rf"^\s*</?(?:[A-Za-z][A-Za-z0-9_-]*:)?(?:{'|'.join(_HARNESS_TAG_NAMES)})(\s+[^<>]*)?>\s*$",
    re.IGNORECASE,
)
_TRAILING_CLOSING_TAG_RE = re.compile(r"\s*</[A-Za-z][A-Za-z0-9_:\-\.]*>\s*$")


def strip_scaffolding(text: str, mode: str = "chat") -> str:
    """Remove leaked agent-harness scaffolding lines from a model reply.

    Rules, deliberately conservative:
    - A line that is exactly one harness tag is removed in every mode.
    - Any other standalone tag line is removed only in shell mode, where
      such a line can never be a valid command (code mode keeps real
      HTML/XML, chat mode keeps everything except harness tags).
    - A closing tag glued to the end of a shell command is cut off.
    Legitimate shell redirections (echo hi > out.txt, cat < in.txt)
    are untouched: they are not standalone tag lines.
    """
    lines = []
    for line in (text or "").splitlines():
        if _HARNESS_TAG_RE.match(line):
            continue
        if mode == "shell" and _STANDALONE_TAG_RE.match(line):
            continue
        lines.append(line)
    out = "\n".join(lines).strip()
    if mode == "shell":
        out = _TRAILING_CLOSING_TAG_RE.sub("", out).strip()
    return out


def sanitize_shell_output(raw: str) -> str:
    """Strip common model commentary before handing a command to ShellGPT."""
    text = _ANSI_RE.sub("", (raw or "")).replace("\r\n", "\n").strip()
    if not text:
        raise ValueError("Model returned an empty shell command; nothing was executed.")
    inline_lines = _INLINE_CODE_LINE_RE.findall(text)
    if inline_lines:
        return inline_lines[-1].strip()
    fenced_blocks = _FENCED_BLOCK_RE.findall(text)
    if fenced_blocks:
        candidate = fenced_blocks[-1].strip()
        candidate = re.sub(r"^(?:bash|sh|zsh|shell)\s*\n", "", candidate, flags=re.I)
        if candidate:
            return candidate
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        if _META_LINE_RE.match(line):
            break
        kept.append(line)
    candidate = "\n".join(kept).strip().split("\n\n", 1)[0].strip()
    candidate_lines = [line.strip() for line in candidate.splitlines() if line.strip()]
    if not candidate_lines:
        raise ValueError("Model returned commentary instead of a shell command; nothing was executed.")
    prose_start = re.compile(
        r"^(?:sure\b|here(?:'s| is)\b|the command\b|you can\b|to \w+\b|"
        r"first[, :]\b|this command\b|i (?:would|will|can)\b|the final answer\b)",
        re.I,
    )
    if prose_start.match(candidate_lines[0]):
        command_line = next((line for line in candidate_lines[1:] if not prose_start.match(line)), None)
        if command_line is None:
            raise ValueError("Model returned commentary instead of a shell command; nothing was executed.")
        return command_line
    return candidate


def sanitize_code_output(raw: str) -> str:
    """Return only code for ShellGPT's -c role.

    The role asks for plain code without markdown fences, but models often
    wrap code in ``` fences anyway (which would end up inside the user's
    file/terminal). If the reply contains a fenced block, return the first
    block's content; otherwise return the reply trimmed, unchanged.
    """
    text = _ANSI_RE.sub("", (raw or "")).replace("\r\n", "\n").strip()
    if not text:
        raise ValueError("Model returned empty code output.")
    blocks = _FENCED_BLOCK_RE.findall(text)
    if blocks:
        candidate = blocks[0].strip()
        if candidate:
            return candidate
    return text


def extract_tools(req: dict) -> list[dict]:
    """Normalize OpenAI-style tool/function specs from a request body."""
    tools: list[dict] = []
    for item in req.get("tools") or []:
        fn = (item or {}).get("function") or {}
        if fn.get("name"):
            tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
    for item in req.get("functions") or []:  # legacy field
        if (item or {}).get("name"):
            tools.append({
                "name": item["name"],
                "description": item.get("description", ""),
                "parameters": item.get("parameters", {}),
            })
    return tools


def parse_tool_call(text: str, allowed: set) -> tuple | None:
    """Find a function-call reply of the form
    {"tool_call": {"name": ..., "arguments": {...}}} (or the bare
    {"name": ..., "arguments": {...}}) anywhere in the model output."""
    if not text:
        return None
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        cand = obj.get("tool_call") if isinstance(obj.get("tool_call"), dict) else obj
        name = cand.get("name")
        if name in allowed:
            args = cand.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            return name, args
    return None


def _data_dirs() -> list[Path]:
    dirs = [Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))),
            Path.home() / ".local" / "share",
            Path.home() / ".config"]
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def _config_dirs() -> list[Path]:
    dirs = [Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))),
            Path.home() / ".config"]
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def _load_json_tolerant(path: Path):
    """Parse JSON or JSONC (// and /* */ comments, trailing commas)."""
    try:
        text = path.read_text()
    except OSError:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # String-aware comment stripper (does not touch // inside strings).
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    esc = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def _key_from_auth_entry(entry) -> str | None:
    """Extract a usable credential from one provider's auth.json entry.

    OpenCode auth entries are {"type": "api", "key": ...} or
    {"type": "oauth", "access": ..., "refresh": ..., "expires": <ms>}.
    """
    if not isinstance(entry, dict):
        return None
    for field in ("key", "apiKey", "api_key"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Any OpenRouter-shaped key stored under an unexpected field name.
    for value in entry.values():
        if isinstance(value, str) and value.strip().startswith("sk-or-"):
            return value.strip()
    if entry.get("type") == "oauth":
        access = entry.get("access") or entry.get("accessToken") or entry.get("token")
        expires = entry.get("expires") or entry.get("expiry") or 0
        try:
            expires = float(expires)
        except (TypeError, ValueError):
            expires = 0
        # expires is milliseconds since epoch in OpenCode's schema.
        if isinstance(access, str) and access.strip() and (
            not expires or expires > time.time() * 1000
        ):
            return access.strip()
    return None


def _key_from_auth_files() -> str | None:
    candidates: list[Path] = []
    explicit = os.getenv("SGPT_OPENROUTER_AUTH_FILE")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    for d in _data_dirs():
        candidates.append(d / "opencode" / "auth.json")
    seen: set[str] = set()
    for path in candidates:
        if str(path) in seen:
            continue
        seen.add(str(path))
        data = _load_json_tolerant(path)
        if isinstance(data, dict):
            key = _key_from_auth_entry(data.get("openrouter"))
            if key:
                return key
    return None


def _resolve_config_value(value):
    """Resolve OpenCode config substitutions like {env:VAR} / {file:path}."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    m = re.fullmatch(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", value)
    if m:
        return os.getenv(m.group(1), "").strip() or None
    m = re.fullmatch(r"\{file:([^}]+)\}", value)
    if m:
        try:
            return Path(m.group(1)).expanduser().read_text().strip() or None
        except OSError:
            return None
    return value or None


def _key_from_opencode_config() -> str | None:
    for d in _config_dirs():
        for name in ("opencode.json", "opencode.jsonc", "config.json"):
            data = _load_json_tolerant(d / "opencode" / name)
            if not isinstance(data, dict):
                continue
            provider = data.get("provider")
            if isinstance(provider, dict):
                orc = provider.get("openrouter")
                if isinstance(orc, dict):
                    options = orc.get("options") if isinstance(orc.get("options"), dict) else {}
                    for holder in (options, orc):
                        key = _resolve_config_value(holder.get("apiKey") or holder.get("api_key"))
                        if key:
                            return key
    return None


def _key_from_opencode_db() -> str | None:
    """Newer OpenCode builds keep credentials in opencode.db (SQLite).

    Read-only and fully guarded: any schema mismatch just means
    "not found here". Only OpenRouter-labelled rows are considered,
    and the value itself is never logged.
    """
    try:
        import sqlite3
    except Exception:
        return None
    for d in _data_dirs():
        path = d / "opencode" / "opencode.db"
        if not path.exists():
            continue
        try:
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
            try:
                tables = {r[0] for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if "credential" in tables:
                    cols = {r[1] for r in db.execute("PRAGMA table_info(credential)")}
                    if {"value", "integration_id", "label"} & cols and "value" in cols:
                        rows = db.execute("SELECT * FROM credential").fetchall()
                        names = [r[1] for r in db.execute("PRAGMA table_info(credential)")]
                        for row in rows:
                            rec = dict(zip(names, row))
                            label_text = " ".join(
                                str(rec.get(c, "")) for c in
                                ("integration_id", "label", "connector_id", "method_id")
                            ).lower()
                            value = rec.get("value")
                            if "openrouter" in label_text and isinstance(value, str) \
                                    and value.strip().startswith("sk-or-"):
                                return value.strip()
                if "account" in tables:
                    rows = db.execute(
                        "SELECT url, access_token, token_expiry FROM account").fetchall()
                    now_ms = time.time() * 1000
                    for url, token, expiry in rows:
                        if url and "openrouter" in str(url).lower() \
                                and isinstance(token, str) and token.strip():
                            try:
                                exp = float(expiry or 0)
                            except (TypeError, ValueError):
                                exp = 0
                            # expiry may be seconds or ms; accept if not
                            # clearly past under either scale.
                            if not exp or exp > now_ms or exp > time.time():
                                return token.strip()
            finally:
                db.close()
        except Exception:
            continue
    return None


_KEY_CACHE: dict = {"key": None}
_OR_FALLBACK_NOTED = False


def _find_openrouter_key() -> tuple:
    """Return (key, source-label) or (None, None). Never logs the key."""
    if _KEY_CACHE["key"]:
        return _KEY_CACHE["key"], "cache"
    env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env_key:
        _KEY_CACHE["key"] = env_key
        return env_key, "OPENROUTER_API_KEY env"
    for finder, label in (
        (_key_from_auth_files, "OpenCode auth.json"),
        (_key_from_opencode_config, "OpenCode config (provider.openrouter apiKey)"),
        (_key_from_opencode_db, "OpenCode credential database"),
    ):
        try:
            key = finder()
        except Exception:
            key = None
        if key:
            _KEY_CACHE["key"] = key
            return key, label
    return None, None


def _openrouter_api_key() -> str:
    key, _source = _find_openrouter_key()
    if key:
        return key
    raise RuntimeError(
        "OpenRouter API key not found. Set OPENROUTER_API_KEY or connect OpenRouter "
        "in OpenCode (opencode /connect). The key value is never printed by this adapter."
    )


# Fields supported by OpenRouter's OpenAI-compatible chat completions endpoint.
_OPENROUTER_PARAMETERS = (
    "temperature", "top_p", "max_tokens", "max_completion_tokens", "stop",
    "presence_penalty", "frequency_penalty", "repetition_penalty", "top_k",
    "min_p", "seed", "n", "logit_bias", "response_format", "tools",
    "tool_choice", "parallel_tool_calls", "functions", "function_call", "user",
)


# ---------------------------------------------------------------------------
# Provider limit reporting
#
# When a free model's quota/rate limit is exhausted - or a paid model's
# limit/credit runs out - the user should SEE that clearly instead of a raw
# provider error or a hang. Both routes map those failures onto one of two
# explicit messages.
# ---------------------------------------------------------------------------

LIMIT_MARKERS = (
    "rate limit", "rate_limit", "ratelimit", "too many requests",
    "quota", "insufficient credits", "insufficient balance",
    "insufficient funds", "credit balance", "usage limit",
    "limit exceeded", "overloaded", "429",
)


def _is_free_model(model: str) -> bool:
    m = (model or "").lower()
    return (
        m.endswith(":free")
        or m.endswith("-free")
        or "/free" in m
        or m in ("opencode/big-pickle", "big-pickle")
    )


def _looks_like_limit(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in LIMIT_MARKERS)


def limit_message(model: str, detail: str = "") -> str:
    """Clear user-facing message when a provider limit is hit."""
    detail = (detail or "").strip()
    suffix = f" Provider said: {detail[:300]}" if detail else ""
    if _is_free_model(model):
        return (
            f"FREE LIMIT HIT: the free quota / rate limit for model '{model}' "
            "is exhausted. Wait a few minutes and try again, or switch to "
            "another model, e.g. sgpt --model <provider/model> \"...\"."
            f"{suffix}"
        )
    return (
        f"LIMIT HIT (paid model): model '{model}' refused the request - its "
        "rate limit, quota or account credit is exhausted. Check the "
        "provider plan/balance, wait and retry, or switch to another model."
        f"{suffix}"
    )


def run_openrouter(model: str, req: dict) -> dict:
    """Call OpenRouter directly using the OpenCode-stored credential."""
    model_id = model[len("openrouter/"):] if model.startswith("openrouter/") else model
    payload: dict = {
        "model": model_id,
        "messages": req.get("messages", []),
        # Get the full response first so shell-mode text can be sanitized safely.
        "stream": False,
    }
    for key in _OPENROUTER_PARAMETERS:
        if key in req and req[key] is not None:
            payload[key] = req[key]
    # OpenRouter prefers tool calling through tools/tool_choice; retain legacy
    # function calling only when that is what the client supplied.

    headers = {
        "Authorization": f"Bearer {_openrouter_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Title": "ShellGPT OpenRouter adapter",
    }
    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    if referer:
        headers["HTTP-Referer"] = referer
    data = json.dumps(payload).encode("utf-8")
    request = Request(OPENROUTER_URL, data=data, headers=headers, method="POST")
    with gate:
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                details = json.loads(exc.read().decode("utf-8", errors="replace"))
                error = details.get("error", {})
                if isinstance(error, dict):
                    message = str(error.get("message") or error.get("code") or "request rejected")
                else:
                    message = str(error or details.get("message") or "request rejected")
            except Exception:
                message = "request rejected"
            if exc.code in (402, 429) or _looks_like_limit(message):
                raise RuntimeError(limit_message(model, message)) from None
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {message[:600]}") from None
        except URLError as exc:
            raise RuntimeError(f"OpenRouter connection failed: {exc.reason}") from None
        except TimeoutError:
            raise RuntimeError(f"OpenRouter request timed out after {TIMEOUT} seconds") from None
        except json.JSONDecodeError:
            raise RuntimeError("OpenRouter returned invalid JSON") from None
    if not isinstance(result, dict) or not isinstance(result.get("choices"), list) or not result["choices"]:
        # OpenRouter sometimes answers HTTP 200 with an error object instead
        # of choices (for example a provider-side rate limit mid-request).
        err = result.get("error") if isinstance(result, dict) else None
        if isinstance(err, dict):
            msg = str(err.get("message") or err.get("code") or "")
            code = err.get("code")
            if code in (402, 429, "402", "429") or _looks_like_limit(msg):
                raise RuntimeError(limit_message(model, msg))
            if msg:
                raise RuntimeError(f"OpenRouter error: {msg[:600]}")
        raise RuntimeError("OpenRouter response contained no choices")
    return result


def run_opencode(model: str, prompt: str) -> str:
    with gate:
        try:
            proc = subprocess.Popen(
                [OPENCODE_BIN, "run", "-m", model, prompt],
                cwd=SANDBOX,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as exc:
            raise RuntimeError(f"Could not start OpenCode CLI: {exc}") from None
        try:
            stdout, stderr = proc.communicate(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            # Kill the WHOLE process group: a plain child kill can leave
            # OpenCode's children alive, holding the request gate (and the
            # provider session) hostage for every later request.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except Exception:
                stdout, stderr = "", ""
            partial = f"{stdout or ''} {stderr or ''}"
            if _looks_like_limit(partial):
                raise RuntimeError(limit_message(model, partial.strip()[-300:])) from None
            raise RuntimeError(f"opencode run timed out after {TIMEOUT} seconds") from None
    out = (stdout or "").strip()
    if proc.returncode != 0 or not out:
        combined = f"{stdout or ''}\n{stderr or ''}"
        if _looks_like_limit(combined):
            raise RuntimeError(limit_message(model, combined.strip()[-300:]))
        err = (stderr or "").strip()[-600:]
        raise RuntimeError(f"opencode run failed (rc={proc.returncode}): {err or 'empty response'}")
    return out


def _fallback_response(model: str, messages: list[dict], req: dict | None = None) -> dict:
    """OpenCode CLI fallback for non-OpenRouter models.

    Text models behind `opencode run` cannot emit native tool calls, so
    when the client sent tool specs this uses a JSON shim: the functions
    are listed in the prompt, a JSON function-call reply is translated
    into a real OpenAI tool_calls response, and ShellGPT executes the
    local function and sends the result back for a final answer.
    OpenRouter models don't need this — they get native tool calling.
    """
    tools = extract_tools(req or {})
    prompt = flatten_messages(messages)
    if tools:
        brief = "\n".join(
            f"- {t['name']}: {t['description']} "
            f"Parameters (JSON schema): {json.dumps(t['parameters'])}"
            for t in tools
        )
        prompt += (
            "\n\nFunctions you may call (at most one per reply), provided "
            "by the person's own terminal program:\n" + brief + "\n"
            "To call one, reply with ONLY this JSON object and nothing "
            "else:\n"
            '{"tool_call": {"name": "<function name>", '
            '"arguments": {<arguments>}}}\n'
            "If no function is needed, answer in plain text as usual."
        )
    text = run_opencode(model, prompt)
    if tools:
        parsed = parse_tool_call(text, {t["name"] for t in tools})
        if parsed is not None:
            name, args = parsed
            return {
                "id": "chatcmpl-" + uuid.uuid4().hex[:24],
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_" + uuid.uuid4().hex[:24],
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args),
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:24],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def chunk(cid: str, model: str, delta: dict, finish=None) -> dict:
    return {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[adapter] {fmt % args}", flush=True)

    def _send_json(self, code: int, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            print("[adapter] client disconnected before JSON response finished", flush=True)

    def do_GET(self):
        if self.path in ("/health", "/v1/health"):
            return self._send_json(200, {"status": "ok", "default_model": DEFAULT_MODEL or None})
        if self.path == "/v1/models":
            # Known free ids, for discovery only — NOT a default. When no
            # adapter default is set, the list is just FREE_MODELS and
            # /health reports default_model: null.
            models = list(dict.fromkeys([m for m in [DEFAULT_MODEL, *FREE_MODELS] if m]))
            data = [
                {"id": m, "object": "model", "created": int(time.time()), "owned_by": "openrouter" if m.startswith("openrouter/") else "opencode"}
                for m in models
            ]
            return self._send_json(200, {"object": "list", "data": data})
        return self._send_json(404, {"error": {"message": "not found"}})

    def _stream_response(self, response: dict, model: str):
        choice = response["choices"][0]
        message = choice.get("message") or {}
        cid = response.get("id") or ("chatcmpl-" + uuid.uuid4().hex[:24])
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def sse(payload: dict):
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            sse(chunk(cid, model, {"role": "assistant"}))
            content = message.get("content")
            if isinstance(content, str) and content:
                for i in range(0, len(content), 400):
                    sse(chunk(cid, model, {"content": content[i:i + 400]}))
            # Preserve modern tool calls (single complete delta per call) and
            # deprecated function_call responses for ShellGPT's OpenAI client.
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list):
                for index, tool in enumerate(tool_calls):
                    delta_tool = dict(tool)
                    delta_tool["index"] = index
                    sse(chunk(cid, model, {"tool_calls": [delta_tool]}))
            if isinstance(message.get("function_call"), dict):
                sse(chunk(cid, model, {"function_call": message["function_call"]}))
            sse(chunk(cid, model, {}, finish=choice.get("finish_reason") or "stop"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            print("[adapter] streaming client disconnected; response stopped", flush=True)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._send_json(404, {"error": {"message": "not found"}})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(req, dict):
                raise ValueError("request body must be a JSON object")
        except Exception as exc:
            return self._send_json(400, {"error": {"message": str(exc)}})

        messages = req.get("messages", [])
        if not isinstance(messages, list):
            return self._send_json(400, {"error": {"message": "messages must be an array"}})
        mode = output_mode(messages)
        try:
            # Inside the try so an unset/placeholder model reaches sgpt
            # as a clear 502 message instead of a dropped connection.
            model = backend_model(req.get("model"))
            if model.startswith("openrouter/"):
                _key, _src = _find_openrouter_key()
                if _key:
                    response = run_openrouter(model, req)
                else:
                    # No readable OpenRouter credential (e.g. the key is
                    # held in a store this adapter cannot read). Do NOT
                    # hard-fail: the OpenCode CLI route provably works on
                    # machines where OpenCode itself can reach the model
                    # (that is how the v2 setup ran). Log it once, plainly.
                    global _OR_FALLBACK_NOTED
                    if not _OR_FALLBACK_NOTED:
                        _OR_FALLBACK_NOTED = True
                        print(
                            "[adapter] No readable OpenRouter credential found "
                            "(checked env, OpenCode auth.json, OpenCode config, "
                            "credential database). Serving openrouter/* via the "
                            "OpenCode CLI route instead — same model, slower, "
                            "and sampling/tool calls use the fallback behavior. "
                            "To use the direct route, connect OpenRouter with "
                            "an API key in OpenCode (/connect) or set "
                            "OPENROUTER_API_KEY for the adapter.",
                            flush=True,
                        )
                    response = _fallback_response(model, messages, req)
            else:
                response = _fallback_response(model, messages, req)
            choices = response.get("choices") or []
            if not choices:
                raise RuntimeError("Model response contained no choices")
            choice = choices[0]
            message = choice.get("message") or {}
            if isinstance(message.get("content"), str) and message["content"].strip():
                # Strip leaked agent scaffolding FIRST (every mode, both
                # routes): a stray tag line must never reach sgpt, let
                # alone be executed as a shell command.
                message["content"] = strip_scaffolding(message["content"], mode)
                if mode == "shell":
                    message["content"] = sanitize_shell_output(message["content"])
                elif mode == "code":
                    message["content"] = sanitize_code_output(message["content"])
                choice["message"] = message
        except Exception as exc:
            return self._send_json(502, {"error": {"message": str(exc), "type": "backend_error"}})

        if bool(req.get("stream")):
            return self._stream_response(response, model)
        # OpenRouter's response already matches the OpenAI response structure;
        # fallback response is normalized to the same shape.
        return self._send_json(200, response)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(
        f"sgpt adapter on http://127.0.0.1:{PORT}/v1 "
        f"(default model: {DEFAULT_MODEL or 'none configured - set DEFAULT_MODEL in .sgptrc or pass --model'}; OpenRouter direct for openrouter/*; "
        f"OpenCode CLI fallback for other models; sandbox: {SANDBOX})",
        flush=True,
    )
    server.serve_forever()

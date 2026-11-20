#!/usr/bin/env python3
"""ShellGPT-compatible local adapter: Colab/Ollama + OpenCode/OpenRouter.

Supports two backends switchable at any time via `sgpt-free` / `sgpt-f`:
1. ``colab`` (Google Colab + Ollama + ngrok, or any OpenAI-compatible /v1 URL):
   - Sends requests directly to ``<colab_url>/v1/chat/completions`` with
     ``ngrok-skip-browser-warning: true`` header.
   - Supports native tool calling (``--functions``), and automatically falls
     back to the JSON tool-call shim if the chosen Ollama model does not
     support native tools.
   - Strips ``<think>...</think>`` reasoning blocks and leaked scaffolding
     before handing shell/code output to ShellGPT.
2. ``opencode`` (OpenCode CLI + OpenRouter direct):
   - ``openrouter/*`` model IDs call OpenRouter's Chat Completions API directly
     when a readable credential is found (OPENROUTER_API_KEY, OpenCode
     auth.json, config, or credential DB); otherwise transparently falls back
     to ``opencode run``.
   - Every other provider/model (``opencode/*`` Zen free models, etc.) runs
     through ``opencode run``.

Explicit prefixes always work regardless of active backend:
- ``colab/<model>`` or ``ollama/<model>`` -> routes to configured Colab URL.
- ``openrouter/<model>`` -> routes to OpenRouter / OpenCode.
- ``opencode/<model>`` -> routes to OpenCode CLI.

The adapter listens on 127.0.0.1 only. ShellGPT remains responsible for its
interactive [E/M/D/A] confirmation, execution, chats, REPL, roles, and cache.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Semaphore
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PORT = int(os.getenv("SGPT_OC_PORT", "8642"))
DEFAULT_MODEL = os.getenv("SGPT_OC_MODEL", "")
MODEL_PLACEHOLDER = "SET_YOUR_MODEL_HERE"
NO_MODEL_MESSAGE = (
    "No model configured: run 'sgpt-free --setup' (or 'sgpt-free --colab <URL> <MODEL>' "
    "or 'sgpt-free --set-model <MODEL>'), or set DEFAULT_MODEL in ~/.config/shell_gpt/.sgptrc "
    "(run: nano ~/.config/shell_gpt/.sgptrc), or pass --model <model> for one command."
)
OPENCODE_BIN = os.getenv("SGPT_OC_BIN", os.path.expanduser("~/.opencode/bin/opencode"))
TIMEOUT = int(os.getenv("SGPT_OC_TIMEOUT", "600"))
SANDBOX = os.getenv("SGPT_OC_SANDBOX", os.path.join(tempfile.gettempdir(), "sgpt-oc-sandbox"))
OPENROUTER_URL = os.getenv("SGPT_OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
CONFIG_PATH = Path(
    os.getenv(
        "SGPT_FREE_CONFIG",
        os.path.join(os.path.expanduser("~/.config"), "shell_gpt", "sgpt-free.json"),
    )
)
os.makedirs(SANDBOX, exist_ok=True)

# Avoid stampeding a free model or single-GPU T4 server with concurrent requests.
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


# ---------------------------------------------------------------------------
# Dynamic local configuration (~/.config/shell_gpt/sgpt-free.json)
# ---------------------------------------------------------------------------

def load_runtime_config() -> dict:
    """Load backend config dynamically so changes take effect without restart."""
    cfg = {
        "backend": "opencode",
        "colab_url": "",
        "colab_model": "",
        "colab_api_key": "",
        "opencode_model": "",
    }
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if v is not None})
    except Exception:
        pass
    # Environment overrides (useful for scripting/testing)
    if os.getenv("SGPT_BACKEND"):
        cfg["backend"] = os.getenv("SGPT_BACKEND", "").strip().lower()
    if os.getenv("SGPT_COLAB_URL"):
        cfg["colab_url"] = os.getenv("SGPT_COLAB_URL", "").strip()
    if os.getenv("SGPT_COLAB_MODEL"):
        cfg["colab_model"] = os.getenv("SGPT_COLAB_MODEL", "").strip()
    if os.getenv("SGPT_COLAB_API_KEY"):
        cfg["colab_api_key"] = os.getenv("SGPT_COLAB_API_KEY", "").strip()
    if cfg.get("backend") not in ("colab", "opencode"):
        cfg["backend"] = "opencode"
    return cfg


def normalize_base_url(url: str) -> str:
    """Normalize a Colab / Ollama / OpenAI-compatible base URL (without /v1)."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    for suffix in ("/v1/chat/completions", "/v1/models", "/api/chat", "/api/tags", "/v1"):
        if u.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
    return u


def resolve_route(requested: str | None, cfg: dict | None = None) -> tuple[str, str]:
    """Return (route, model_id) where route is 'colab' or 'opencode'.

    Explicit prefixes ('colab/', 'ollama/', 'openrouter/', 'opencode/') always
    override the active backend; bare model names follow cfg['backend'].
    """
    cfg = cfg if cfg is not None else load_runtime_config()
    active_backend = cfg.get("backend", "opencode")
    raw = (requested or "").strip()

    if raw.startswith(("colab/", "ollama/")):
        model_name = raw.split("/", 1)[1].strip()
        if not model_name:
            raise RuntimeError(NO_MODEL_MESSAGE)
        return "colab", model_name

    if raw.startswith(("openrouter/", "opencode/")):
        return "opencode", raw

    if active_backend == "colab":
        m = raw or cfg.get("colab_model", "").strip() or DEFAULT_MODEL.strip()
        if not m or m == MODEL_PLACEHOLDER:
            raise RuntimeError(NO_MODEL_MESSAGE)
        return "colab", m

    return "opencode", backend_model(requested)


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


# ---------------------------------------------------------------------------
# Message & output formatting / sanitization
# ---------------------------------------------------------------------------

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
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)
_FENCED_BLOCK_RE = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?[ \t]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE_LINE_RE = re.compile(r"^[ \t]*`([^`\n]+)`[ \t]*$", re.MULTILINE)
_META_LINE_RE = re.compile(
    r"^\s*(?:wait\s*[—-]|so the final answer\b|the final answer\b|"
    r"explanation\s*:|reasoning\s*:|analysis\s*:|note\s*:)",
    re.IGNORECASE,
)

_TAG_NAME = r"[A-Za-z][A-Za-z0-9_:\-\.]*"
_STANDALONE_TAG_RE = re.compile(rf"^\s*</?{_TAG_NAME}(\s+[^<>]*)?>\s*$")
_HARNESS_TAG_NAMES = (
    "rfl", "parameter", "tool_call", "toolcall", "function_call",
    "function", "invocation", "tool", "response",
)
_HARNESS_TAG_RE = re.compile(
    rf"^\s*</?(?:[A-Za-z][A-Za-z0-9_-]*:)?(?:{'|'.join(_HARNESS_TAG_NAMES)})(\s+[^<>]*)?>\s*$",
    re.IGNORECASE,
)
_TRAILING_CLOSING_TAG_RE = re.compile(r"\s*</[A-Za-z][A-Za-z0-9_:\-\.]*>\s*$")


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> reasoning blocks emitted by reasoning models."""
    if not text or "<think>" not in text.lower():
        return text or ""
    cleaned = _THINK_BLOCK_RE.sub("", text).strip()
    if not cleaned:
        # Model put everything inside <think>; keep inner text rather than empty
        return re.sub(r"</?think>", "", text, flags=re.IGNORECASE).strip()
    # Handle truncated unclosed <think> if there is text before it
    if "<think>" in cleaned.lower():
        without_tail = _UNCLOSED_THINK_RE.sub("", cleaned).strip()
        if without_tail:
            return without_tail
    return cleaned


def strip_scaffolding(text: str, mode: str = "chat") -> str:
    """Remove leaked agent-harness scaffolding lines from a model reply."""
    text = strip_thinking(text or "")
    lines = []
    for line in text.splitlines():
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
    """Return only code for ShellGPT's -c role."""
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


def _tool_shim_instruction(tools: list[dict]) -> str:
    brief = "\n".join(
        f"- {t['name']}: {t['description']} "
        f"Parameters (JSON schema): {json.dumps(t['parameters'])}"
        for t in tools
    )
    return (
        "\n\nFunctions you may call (at most one per reply), provided "
        "by the person's own terminal program:\n" + brief + "\n"
        "To call one, reply with ONLY this JSON object and nothing "
        "else:\n"
        '{"tool_call": {"name": "<function name>", '
        '"arguments": {<arguments>}}}\n'
        "If no function is needed, answer in plain text as usual."
    )


def _make_tool_call_response(model: str, name: str, args: dict) -> dict:
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


# ---------------------------------------------------------------------------
# OpenRouter credential discovery
# ---------------------------------------------------------------------------

def _data_dirs() -> list[Path]:
    dirs = [
        Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))),
        Path.home() / ".local" / "share",
        Path.home() / ".config",
    ]
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def _config_dirs() -> list[Path]:
    dirs = [
        Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))),
        Path.home() / ".config",
    ]
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def _load_json_tolerant(path: Path):
    """Parse JSON or JSONC (// and /* */ comments, trailing commas)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
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
    if not isinstance(entry, dict):
        return None
    for field in ("key", "apiKey", "api_key"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
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
    if not isinstance(value, str):
        return None
    value = value.strip()
    m = re.fullmatch(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", value)
    if m:
        return os.getenv(m.group(1), "").strip() or None
    m = re.fullmatch(r"\{file:([^}]+)\}", value)
    if m:
        try:
            return Path(m.group(1)).expanduser().read_text(encoding="utf-8").strip() or None
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


_OPENAI_PARAMETERS = (
    "temperature", "top_p", "max_tokens", "max_completion_tokens", "stop",
    "presence_penalty", "frequency_penalty", "repetition_penalty", "top_k",
    "min_p", "seed", "n", "logit_bias", "response_format", "tools",
    "tool_choice", "parallel_tool_calls", "functions", "function_call", "user",
)

# ---------------------------------------------------------------------------
# Provider limit reporting
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
    detail = (detail or "").strip()
    suffix = f" Provider said: {detail[:300]}" if detail else ""
    if _is_free_model(model):
        return (
            f"FREE LIMIT HIT: the free quota / rate limit for model '{model}' "
            "is exhausted. Wait a few minutes and try again, or switch to "
            "another model (sgpt-free --set-model <model>) or switch to Colab "
            "(sgpt-free --colab <URL> <MODEL>)."
            f"{suffix}"
        )
    return (
        f"LIMIT HIT (paid model): model '{model}' refused the request - its "
        "rate limit, quota or account credit is exhausted. Check the "
        "provider plan/balance, wait and retry, or switch to another model."
        f"{suffix}"
    )


# ---------------------------------------------------------------------------
# Backend 1: Colab / Ollama (OpenAI-compatible /v1 API)
# ---------------------------------------------------------------------------

def _colab_headers(api_key: str = "") -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "sgpt-free-adapter/5.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _post_colab(endpoint: str, payload: dict, api_key: str = "") -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(endpoint, data=data, headers=_colab_headers(api_key), method="POST")
    # Do not hold the global OpenCode semaphore here: if a user Ctrl+C's a
    # slow request or had a stale ngrok URL, the next request must not hang.
    with urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def _normalize_colab_message(response: dict) -> dict:
    """If a thinking model put its reply in reasoning/reasoning_content with empty content, surface it."""
    choices = response.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if not (isinstance(content, str) and content.strip()):
            fallback = msg.get("reasoning_content") or msg.get("reasoning") or ""
            if isinstance(fallback, str) and fallback.strip() and not msg.get("tool_calls"):
                msg["content"] = fallback
                choices[0]["message"] = msg
    return response


def _extract_http_error_message(exc: HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(raw)
            err = details.get("error", {})
            if isinstance(err, dict):
                return str(err.get("message") or err.get("code") or raw[:300])
            return str(err or details.get("message") or raw[:300])
        except Exception:
            return raw[:300] or f"HTTP {exc.code}"
    except Exception:
        return f"HTTP {exc.code}"


def _prepare_messages_for_shim(messages: list[dict], tools: list[dict]) -> list[dict]:
    """Convert tool-role messages + append tool shim instructions for models without native tools."""
    converted: list[dict] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = _message_text(msg)
        if role == "tool":
            converted.append({
                "role": "user",
                "content": f"[Function result]: {content}",
            })
        elif role == "assistant" and not content and msg.get("tool_calls"):
            rendered = []
            for call in msg.get("tool_calls") or []:
                fn = (call or {}).get("function") or {}
                rendered.append(
                    f"[called function {fn.get('name', '?')} "
                    f"with arguments {fn.get('arguments', '{}')}]"
                )
            converted.append({"role": "assistant", "content": "\n".join(rendered)})
        else:
            converted.append({"role": role, "content": content})

    shim = _tool_shim_instruction(tools)
    if converted and converted[0].get("role") == "system":
        converted[0] = {
            "role": "system",
            "content": converted[0]["content"] + shim,
        }
    else:
        converted.insert(0, {"role": "system", "content": shim.strip()})
    return converted


def run_colab(model: str, req: dict, cfg: dict) -> dict:
    """Call the Google Colab / Ollama OpenAI-compatible /v1/chat/completions endpoint."""
    base_url = normalize_base_url(cfg.get("colab_url", ""))
    if not base_url:
        raise RuntimeError(
            "Colab backend is active, but no Colab URL is set. "
            "Run: sgpt-free --colab <NGROK_URL> <MODEL>"
        )
    endpoint = f"{base_url}/v1/chat/completions"
    api_key = (cfg.get("colab_api_key") or "").strip()
    messages = req.get("messages", [])
    tools = extract_tools(req)

    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    for key in _OPENAI_PARAMETERS:
        if key in req and req[key] is not None:
            payload[key] = req[key]

    # Disable slow chain-of-thought thinking for shell (-s) and code (-c)
    # on Ollama thinking models (qwen3/qwen3.5/gemma4) so commands/code return
    # in seconds instead of waiting 30-90s for hidden reasoning tokens.
    mode = output_mode(messages)
    think_env = os.getenv("SGPT_COLAB_THINK", "").strip().lower()
    if mode in ("shell", "code") and think_env != "true" and "reasoning_effort" not in payload:
        payload["reasoning_effort"] = "none"

    try:
        result = _post_colab(endpoint, payload, api_key)
    except HTTPError as exc:
        msg = _extract_http_error_message(exc)
        low = msg.lower()
        # If an OpenAI-compatible server rejects reasoning_effort, retry without it
        if exc.code == 400 and "reasoning_effort" in payload and "reasoning" in low:
            payload.pop("reasoning_effort", None)
            result = _post_colab(endpoint, payload, api_key)
            return _normalize_colab_message(result)
        # Automatic fallback: if the Ollama model doesn't support native tools,
        # retry with our JSON tool-call shim so `sgpt-free --functions` still works!
        if exc.code == 400 and tools and ("tool" in low or "function" in low):
            shim_payload = {
                "model": model,
                "messages": _prepare_messages_for_shim(messages, tools),
                "stream": False,
            }
            for key in ("temperature", "top_p", "max_tokens", "stop", "seed"):
                if key in req and req[key] is not None:
                    shim_payload[key] = req[key]
            try:
                result = _post_colab(endpoint, shim_payload, api_key)
            except HTTPError as exc2:
                msg2 = _extract_http_error_message(exc2)
                raise RuntimeError(f"Colab/Ollama HTTP {exc2.code}: {msg2[:500]}") from None
            except URLError as exc2:
                raise RuntimeError(
                    f"Colab/Ollama connection failed ({base_url}): {exc2.reason}. "
                    "Is your Colab cell still running?"
                ) from None
            except TimeoutError:
                raise RuntimeError(f"Colab/Ollama request timed out after {TIMEOUT}s") from None
            # Translate JSON shim reply into native OpenAI tool_calls response
            choices = result.get("choices") or []
            if choices:
                text = strip_thinking(((choices[0].get("message") or {}).get("content")) or "")
                parsed = parse_tool_call(text, {t["name"] for t in tools})
                if parsed is not None:
                    return _make_tool_call_response(model, parsed[0], parsed[1])
            return result

        if exc.code == 404:
            if "ngrok" in low or "tunnel" in low or "not found" in low:
                raise RuntimeError(
                    f"Colab/Ollama HTTP 404 ({msg[:300]}). "
                    "Either the ngrok tunnel expired (update with: sgpt-free --colab <NEW_URL> <MODEL>) "
                    f"or model '{model}' is not loaded on Colab (check: sgpt-free --models)."
                ) from None
        if exc.code in (502, 503, 504):
            raise RuntimeError(
                f"Colab/Ollama HTTP {exc.code}: Colab server or ngrok tunnel is unreachable. "
                "Make sure your Colab cell is still running."
            ) from None
        raise RuntimeError(f"Colab/Ollama HTTP {exc.code}: {msg[:500]}") from None
    except URLError as exc:
        raise RuntimeError(
            f"Colab/Ollama connection failed ({base_url}): {exc.reason}. "
            "Check that your Colab cell is running and update URL with: sgpt-free --colab <URL> <MODEL>"
        ) from None
    except TimeoutError:
        raise RuntimeError(f"Colab/Ollama request timed out after {TIMEOUT} seconds") from None
    except json.JSONDecodeError:
        raise RuntimeError(
            "Colab/Ollama returned non-JSON (possibly an ngrok warning or offline page). "
            "Verify your Colab cell is running and URL is current."
        ) from None

    if not isinstance(result, dict) or not isinstance(result.get("choices"), list) or not result["choices"]:
        err = result.get("error") if isinstance(result, dict) else None
        if isinstance(err, dict) and err.get("message"):
            raise RuntimeError(f"Colab/Ollama error: {str(err['message'])[:500]}")
        raise RuntimeError("Colab/Ollama response contained no choices")
    return _normalize_colab_message(result)


def fetch_colab_models(cfg: dict) -> list[str]:
    """Query live model IDs from the configured Colab/Ollama server."""
    base_url = normalize_base_url(cfg.get("colab_url", ""))
    if not base_url:
        return []
    api_key = (cfg.get("colab_api_key") or "").strip()
    headers = _colab_headers(api_key)
    for path in ("/v1/models", "/api/tags"):
        try:
            req = Request(f"{base_url}{path}", headers=headers, method="GET")
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(data, dict):
                if isinstance(data.get("data"), list):
                    ids = [str(m.get("id", "")).strip() for m in data["data"] if isinstance(m, dict)]
                    ids = [x for x in ids if x]
                    if ids:
                        return ids
                if isinstance(data.get("models"), list):
                    ids = [str(m.get("name", "")).strip() for m in data["models"] if isinstance(m, dict)]
                    ids = [x for x in ids if x]
                    if ids:
                        return ids
        except Exception:
            continue
    return []


# ---------------------------------------------------------------------------
# Backend 2: OpenRouter direct + OpenCode CLI
# ---------------------------------------------------------------------------

def run_openrouter(model: str, req: dict) -> dict:
    """Call OpenRouter directly using the OpenCode-stored credential."""
    model_id = model[len("openrouter/"):] if model.startswith("openrouter/") else model
    payload: dict = {
        "model": model_id,
        "messages": req.get("messages", []),
        "stream": False,
    }
    for key in _OPENAI_PARAMETERS:
        if key in req and req[key] is not None:
            payload[key] = req[key]

    headers = {
        "Authorization": f"Bearer {_openrouter_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Title": "ShellGPT Local Adapter",
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
            message = _extract_http_error_message(exc)
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
            popen_kwargs: dict = {
                "cwd": SANDBOX,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
            }
            if os.name != "nt":
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen([OPENCODE_BIN, "run", "-m", model, prompt], **popen_kwargs)
        except OSError as exc:
            raise RuntimeError(f"Could not start OpenCode CLI: {exc}") from None
        try:
            stdout, stderr = proc.communicate(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
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
    """OpenCode CLI fallback for non-OpenRouter models (with JSON tool-call shim)."""
    tools = extract_tools(req or {})
    prompt = flatten_messages(messages)
    if tools:
        prompt += _tool_shim_instruction(tools)
    text = run_opencode(model, prompt)
    if tools:
        parsed = parse_tool_call(text, {t["name"] for t in tools})
        if parsed is not None:
            return _make_tool_call_response(model, parsed[0], parsed[1])
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
        cfg = load_runtime_config()
        if self.path in ("/health", "/v1/health"):
            return self._send_json(200, {
                "status": "ok",
                "backend": cfg.get("backend", "opencode"),
                "colab_url": normalize_base_url(cfg.get("colab_url", "")) or None,
                "default_model": (
                    cfg.get("colab_model") if cfg.get("backend") == "colab" else DEFAULT_MODEL
                ) or None,
            })
        if self.path == "/v1/models":
            if cfg.get("backend") == "colab" and cfg.get("colab_url"):
                live = fetch_colab_models(cfg)
                if not live and cfg.get("colab_model"):
                    live = [cfg["colab_model"]]
                data = [
                    {"id": m, "object": "model", "created": int(time.time()), "owned_by": "colab-ollama"}
                    for m in live
                ]
                return self._send_json(200, {"object": "list", "data": data})
            models = list(dict.fromkeys([m for m in [DEFAULT_MODEL, *FREE_MODELS] if m]))
            data = [
                {
                    "id": m,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "openrouter" if m.startswith("openrouter/") else "opencode",
                }
                for m in models
            ]
            return self._send_json(200, {"object": "list", "data": data})
        return self._send_json(404, {"error": {"message": "not found"}})

    def _stream_response(self, response: dict, model: str):
        choice = response["choices"][0]
        message = choice.get("message") or {}
        cid = response.get("id") or ("chatcmpl-" + uuid.uuid4().hex[:24])
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
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

    def _proxy_colab_stream(self, model: str, req: dict, cfg: dict) -> bool:
        """Stream tokens live from Colab/Ollama for chat mode so output appears immediately."""
        base_url = normalize_base_url(cfg.get("colab_url", ""))
        if not base_url:
            raise RuntimeError(
                "Colab backend is active, but no Colab URL is set. "
                "Run: sgpt-free --colab <NGROK_URL> <MODEL>"
            )
        endpoint = f"{base_url}/v1/chat/completions"
        api_key = (cfg.get("colab_api_key") or "").strip()
        payload: dict = {
            "model": model,
            "messages": req.get("messages", []),
            "stream": True,
        }
        for key in _OPENAI_PARAMETERS:
            if key in req and req[key] is not None:
                payload[key] = req[key]
        if os.getenv("SGPT_COLAB_THINK", "").strip().lower() != "true" and "reasoning_effort" not in payload:
            payload["reasoning_effort"] = "none"

        def _open_stream(body_dict: dict):
            data = json.dumps(body_dict).encode("utf-8")
            request = Request(endpoint, data=data, headers=_colab_headers(api_key), method="POST")
            return urlopen(request, timeout=TIMEOUT)

        try:
            upstream = _open_stream(payload)
        except HTTPError as exc:
            msg = _extract_http_error_message(exc)
            if exc.code == 400 and "reasoning_effort" in payload and "reasoning" in msg.lower():
                payload.pop("reasoning_effort", None)
                try:
                    upstream = _open_stream(payload)
                except HTTPError as exc2:
                    msg2 = _extract_http_error_message(exc2)
                    raise RuntimeError(f"Colab/Ollama HTTP {exc2.code}: {msg2[:500]}") from None
            else:
                raise RuntimeError(f"Colab/Ollama HTTP {exc.code}: {msg[:500]}") from None
        except URLError as exc:
            raise RuntimeError(
                f"Colab/Ollama connection failed ({base_url}): {exc.reason}. "
                "Make sure your Colab cell is still running."
            ) from None
        except TimeoutError:
            raise RuntimeError(f"Colab/Ollama request timed out after {TIMEOUT} seconds") from None

        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        in_think = False
        sent_content = False
        reasoning_buf: list[str] = []
        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        try:
            with upstream:
                for raw_line in upstream:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        if not sent_content and reasoning_buf:
                            fallback_text = "".join(reasoning_buf).strip()
                            if fallback_text:
                                self.wfile.write(
                                    f"data: {json.dumps(chunk(cid, model, {'content': fallback_text}), ensure_ascii=False)}\n\n".encode("utf-8")
                                )
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                        break
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    try:
                        evt = json.loads(body)
                    except Exception:
                        continue
                    if evt.get("id"):
                        cid = evt["id"]
                    choices = evt.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        rtxt = delta.get("reasoning_content") or delta.get("reasoning")
                        if isinstance(rtxt, str) and rtxt:
                            reasoning_buf.append(rtxt)
                        text = delta.get("content")
                        if isinstance(text, str) and text:
                            if "<think>" in text:
                                in_think = True
                                text = text.split("<think>", 1)[0]
                            if in_think:
                                if "</think>" in text:
                                    text = text.split("</think>", 1)[1]
                                    in_think = False
                                else:
                                    text = ""
                            if text:
                                sent_content = True
                            delta["content"] = text
                            choices[0]["delta"] = delta
                    self.wfile.write(f"data: {json.dumps(evt, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            print("[adapter] streaming client disconnected; stopped Colab stream", flush=True)
        return True

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
        cfg = load_runtime_config()
        try:
            route, model = resolve_route(req.get("model"), cfg)
            if route == "colab" and bool(req.get("stream")) and mode == "chat" and not extract_tools(req):
                self._proxy_colab_stream(model, req, cfg)
                return
            if route == "colab":
                response = run_colab(model, req, cfg)
            elif model.startswith("openrouter/"):
                _key, _src = _find_openrouter_key()
                if _key:
                    response = run_openrouter(model, req)
                else:
                    global _OR_FALLBACK_NOTED
                    if not _OR_FALLBACK_NOTED:
                        _OR_FALLBACK_NOTED = True
                        print(
                            "[adapter] No readable OpenRouter credential found. "
                            "Serving openrouter/* via OpenCode CLI instead.",
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
        return self._send_json(200, response)


if __name__ == "__main__":
    cfg = load_runtime_config()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(
        f"sgpt-free adapter by UNIT-61398 on http://127.0.0.1:{PORT}/v1 "
        f"(backend: {cfg.get('backend')}; colab_url: {cfg.get('colab_url') or 'not set'}; "
        f"config: {CONFIG_PATH}; sandbox: {SANDBOX})",
        flush=True,
    )
    server.serve_forever()

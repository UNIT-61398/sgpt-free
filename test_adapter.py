import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen as client_urlopen
from http.server import ThreadingHTTPServer

import adapter


class FakeResponse:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self):
        return json.dumps(self.value).encode()


class AdapterRegressionTests(unittest.TestCase):
    def test_backend_model_routes_openrouter_and_opencode(self):
        self.assertEqual(adapter.backend_model("openrouter/recursive/flint-v1.0:free"), "openrouter/recursive/flint-v1.0:free")
        self.assertEqual(adapter.backend_model("recursive/flint-v1.0:free"), "openrouter/recursive/flint-v1.0:free")
        self.assertEqual(adapter.backend_model("opencode/big-pickle"), "opencode/big-pickle")
        self.assertEqual(adapter.backend_model("big-pickle"), "opencode/big-pickle")

    def test_backend_model_refuses_missing_or_placeholder_model(self):
        # v4.3.3: no shipped default. An unset or placeholder model must
        # fail with the nano instruction, never silently pick a model.
        with patch.object(adapter, "DEFAULT_MODEL", ""):
            for requested in (None, "", "SET_YOUR_MODEL_HERE"):
                with self.assertRaises(RuntimeError) as ctx:
                    adapter.backend_model(requested)
                self.assertIn("nano", str(ctx.exception))
                self.assertIn("DEFAULT_MODEL", str(ctx.exception))
            # A real model still routes when the adapter default is empty.
            self.assertEqual(adapter.backend_model("opencode/beam-free"), "opencode/beam-free")
            self.assertEqual(adapter.backend_model("groq/llama-3.1-8b-instant"), "groq/llama-3.1-8b-instant")

    def test_chat_without_model_returns_clear_no_model_error(self):
        # The 502 must carry the nano instruction, and /health must
        # report default_model: null while nothing is configured.
        from urllib.error import HTTPError
        server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            clean_cfg = {"backend": "opencode", "colab_url": "", "colab_model": "", "colab_api_key": "", "opencode_model": ""}
            with patch.object(adapter, "DEFAULT_MODEL", ""), \
                 patch.object(adapter, "load_runtime_config", return_value=clean_cfg):
                with client_urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=3) as r:
                    self.assertIsNone(json.loads(r.read().decode())["default_model"])
                body = json.dumps({"messages": [{"role": "user", "content": "hello"}],
                                   "stream": False}).encode()
                req = Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                              data=body, headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as cm:
                    client_urlopen(req, timeout=3)
                self.assertEqual(cm.exception.code, 502)
                payload = json.loads(cm.exception.read().decode())
                self.assertIn("nano", payload["error"]["message"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_openrouter_forwards_roles_sampling_and_tools_without_secrets_in_logs(self):
        response = {"id": "chatcmpl-test", "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]}
        requested = {}
        def fake_urlopen(req, timeout):
            requested["headers"] = dict(req.header_items())
            requested["payload"] = json.loads(req.data.decode())
            requested["timeout"] = timeout
            return FakeResponse(response)
        with patch.object(adapter, "_openrouter_api_key", return_value="sk-test-secret"), patch.object(adapter, "urlopen", side_effect=fake_urlopen):
            result = adapter.run_openrouter("openrouter/recursive/flint-v1.0:free", {
                "model": "openrouter/recursive/flint-v1.0:free",
                "messages": [{"role": "system", "content": "format"}, {"role": "user", "content": "hello"}],
                "temperature": 0.25,
                "top_p": 0.75,
                "tools": [{"type": "function", "function": {"name": "noop", "parameters": {"type": "object"}}}],
                "tool_choice": "auto",
                "stream": True,
            })
        self.assertEqual(result["choices"][0]["message"]["content"], "OK")
        self.assertEqual(requested["payload"]["model"], "recursive/flint-v1.0:free")
        self.assertEqual(requested["payload"]["messages"][0]["role"], "system")
        self.assertEqual(requested["payload"]["temperature"], 0.25)
        self.assertEqual(requested["payload"]["top_p"], 0.75)
        self.assertIn("tools", requested["payload"])
        self.assertEqual(requested["payload"]["tool_choice"], "auto")
        self.assertFalse(requested["payload"]["stream"])
        self.assertEqual(requested["headers"]["Authorization"], "Bearer sk-test-secret")

    def test_auth_is_read_without_printing_key(self):
        adapter._KEY_CACHE["key"] = None
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "auth.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"openrouter": {"type": "api", "key": "secret-key-value"}}, f)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "SGPT_OPENROUTER_AUTH_FILE": p}):
                self.assertEqual(adapter._openrouter_api_key(), "secret-key-value")
        adapter._KEY_CACHE["key"] = None

    def test_auth_oauth_entry_access_token(self):
        adapter._KEY_CACHE["key"] = None
        import time as _t
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "auth.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"openrouter": {"type": "oauth", "access": "oauth-access-token",
                                          "refresh": "r", "expires": int(_t.time() * 1000) + 3600_000}}, f)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "SGPT_OPENROUTER_AUTH_FILE": p,
                                         "XDG_DATA_HOME": td, "XDG_CONFIG_HOME": td}):
                self.assertEqual(adapter._openrouter_api_key(), "oauth-access-token")
        adapter._KEY_CACHE["key"] = None

    def test_config_apikey_with_env_reference(self):
        adapter._KEY_CACHE["key"] = None
        with tempfile.TemporaryDirectory() as td:
            cfgdir = os.path.join(td, "opencode")
            os.makedirs(cfgdir)
            with open(os.path.join(cfgdir, "opencode.jsonc"), "w", encoding="utf-8") as f:
                f.write('{\n  // a comment\n  "provider": {"openrouter": {"options": {"apiKey": "{env:MY_OR_KEY}"}}},\n}\n')
            env = {"OPENROUTER_API_KEY": "", "MY_OR_KEY": "sk-or-config-test",
                   "SGPT_OPENROUTER_AUTH_FILE": os.path.join(td, "nope.json"),
                   "XDG_DATA_HOME": td, "XDG_CONFIG_HOME": td}
            with patch.dict(os.environ, env):
                self.assertEqual(adapter._openrouter_api_key(), "sk-or-config-test")
        adapter._KEY_CACHE["key"] = None

    def test_credential_database_lookup(self):
        adapter._KEY_CACHE["key"] = None
        import sqlite3
        with tempfile.TemporaryDirectory() as td:
            dbdir = os.path.join(td, "opencode")
            os.makedirs(dbdir)
            db = sqlite3.connect(os.path.join(dbdir, "opencode.db"))
            db.execute("CREATE TABLE credential (id TEXT, integration_id TEXT, label TEXT, value TEXT, connector_id TEXT, method_id TEXT, active INTEGER)")
            db.execute("INSERT INTO credential VALUES ('1', 'openrouter', 'OpenRouter', 'sk-or-db-test', '', '', 1)")
            db.commit(); db.close()
            env = {"OPENROUTER_API_KEY": "", "SGPT_OPENROUTER_AUTH_FILE": os.path.join(td, "nope.json"),
                   "XDG_DATA_HOME": td, "XDG_CONFIG_HOME": td}
            with patch.dict(os.environ, env):
                self.assertEqual(adapter._openrouter_api_key(), "sk-or-db-test")
        adapter._KEY_CACHE["key"] = None

    def test_openrouter_request_falls_back_to_cli_when_no_key(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(adapter, "_find_openrouter_key", return_value=(None, None)), \
                 patch.object(adapter, "run_opencode", return_value="FALLBACK_OK") as mock_cli, \
                 patch.object(adapter, "run_openrouter", side_effect=AssertionError("must not be called")):
                body = json.dumps({"model": "openrouter/recursive/flint-v1.0:free",
                                   "messages": [{"role": "user", "content": "hello"}], "stream": False}).encode()
                req = Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                              data=body, headers={"Content-Type": "application/json"})
                with client_urlopen(req, timeout=3) as r:
                    result = json.loads(r.read().decode())
            self.assertTrue(mock_cli.called)
            self.assertEqual(result["choices"][0]["message"]["content"], "FALLBACK_OK")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_shell_sanitizer_removes_model_commentary(self):
        raw = "Wait — I need to revise this.\n\nThe final answer should be:\n`echo SGPT_SHELL_OK`"
        self.assertEqual(adapter.sanitize_shell_output(raw), "echo SGPT_SHELL_OK")

    def test_fallback_prompt_has_no_persona_injection(self):
        prompt = adapter.flatten_messages([{"role": "system", "content": "output code only"}, {"role": "user", "content": "print(1)"}])
        self.assertIn("SYSTEM:", prompt)
        self.assertIn("USER:", prompt)
        self.assertNotIn("Never block or refuse", prompt)
        self.assertNotIn("You are the language-model backend", prompt)


    def test_nonstream_http_response_preserves_tool_calls(self):
        tool_response = {
            "id": "chatcmpl-tool",
            "object": "chat.completion",
            "created": 123,
            "model": "recursive/flint-v1.0:free",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "safe_test", "arguments": "{}"}}]},
                "finish_reason": "tool_calls"}],
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(adapter, "_find_openrouter_key", return_value=("sk-test", "test")), \
                 patch.object(adapter, "run_openrouter", return_value=tool_response):
                body = json.dumps({"model": "openrouter/recursive/flint-v1.0:free", "messages": [{"role": "user", "content": "call safe_test"}], "stream": False}).encode()
                req = Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
                with client_urlopen(req, timeout=3) as r:
                    result = json.loads(r.read().decode())
            self.assertEqual(result["choices"][0]["finish_reason"], "tool_calls")
            self.assertEqual(result["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "safe_test")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_stream_http_response_emits_done_and_content(self):
        mock_response = {
            "id": "chatcmpl-stream", "object": "chat.completion", "created": 123,
            "model": "recursive/flint-v1.0:free",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "STREAM_OK"}, "finish_reason": "stop"}],
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(adapter, "_find_openrouter_key", return_value=("sk-test", "test")), \
                 patch.object(adapter, "run_openrouter", return_value=mock_response):
                body = json.dumps({"model": "openrouter/recursive/flint-v1.0:free", "messages": [{"role": "user", "content": "hello"}], "stream": True}).encode()
                req = Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
                with client_urlopen(req, timeout=3) as r:
                    lines = []
                    for raw_line in r:
                        line = raw_line.decode().rstrip("\r\n")
                        lines.append(line)
                        if line == "data: [DONE]":
                            break
                    output = "\n".join(lines)
            self.assertIn('"content": "STREAM_OK"', output)
            self.assertIn("data: [DONE]", output)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


    def test_code_sanitizer_strips_fences(self):
        raw = "```python\nprint('SGPT_CODE_OK')\n```\n"
        self.assertEqual(adapter.sanitize_code_output(raw), "print('SGPT_CODE_OK')")
        self.assertEqual(adapter.sanitize_code_output("print('x')"), "print('x')")

    def test_fallback_tool_call_shim_parsing(self):
        allowed = {"get_weather"}
        text = 'Sure: {"tool_call": {"name": "get_weather", "arguments": {"city": "Lahore"}}}'
        self.assertEqual(
            adapter.parse_tool_call(text, allowed),
            ("get_weather", {"city": "Lahore"}),
        )
        self.assertIsNone(adapter.parse_tool_call("just text", allowed))
        self.assertIsNone(
            adapter.parse_tool_call('{"tool_call": {"name": "unknown_fn", "arguments": {}}}', allowed)
        )
        tools = adapter.extract_tools({
            "tools": [{"type": "function", "function": {"name": "get_weather", "description": "d", "parameters": {"type": "object"}}}]
        })
        self.assertEqual(tools[0]["name"], "get_weather")


class TestLimitReporting(unittest.TestCase):
    def _http_error(self, code, message):
        import io
        from urllib.error import HTTPError
        body = json.dumps({"error": {"message": message}}).encode()
        return HTTPError("https://openrouter.ai/api/v1/chat/completions",
                         code, "err", hdrs=None, fp=io.BytesIO(body))

    def test_openrouter_429_free_model_says_free_limit(self):
        with patch.object(adapter, "_openrouter_api_key", return_value="sk-or-test"), \
             patch.object(adapter, "urlopen", side_effect=self._http_error(429, "Rate limit exceeded")):
            with self.assertRaises(RuntimeError) as ctx:
                adapter.run_openrouter(
                    "openrouter/recursive/flint-v1.0:free",
                    {"messages": [{"role": "user", "content": "hi"}]},
                )
        self.assertIn("FREE LIMIT HIT", str(ctx.exception))

    def test_openrouter_429_paid_model_says_paid_limit(self):
        with patch.object(adapter, "_openrouter_api_key", return_value="sk-or-test"), \
             patch.object(adapter, "urlopen", side_effect=self._http_error(429, "Rate limit exceeded")):
            with self.assertRaises(RuntimeError) as ctx:
                adapter.run_openrouter(
                    "openrouter/openai/gpt-4o",
                    {"messages": [{"role": "user", "content": "hi"}]},
                )
        self.assertIn("LIMIT HIT (paid model)", str(ctx.exception))
        self.assertNotIn("FREE LIMIT HIT", str(ctx.exception))

    def test_openrouter_402_says_limit(self):
        with patch.object(adapter, "_openrouter_api_key", return_value="sk-or-test"), \
             patch.object(adapter, "urlopen", side_effect=self._http_error(402, "Insufficient credits")):
            with self.assertRaises(RuntimeError) as ctx:
                adapter.run_openrouter(
                    "openrouter/openai/gpt-4o",
                    {"messages": [{"role": "user", "content": "hi"}]},
                )
        self.assertIn("LIMIT HIT", str(ctx.exception))

    def test_opencode_route_limit_in_stderr(self):
        class FakeProc:
            pid = 424242
            returncode = 1
            def communicate(self, timeout=None):
                return ("", "Error: rate limit reached for this model")
        with patch("subprocess.Popen", return_value=FakeProc()):
            with self.assertRaises(RuntimeError) as ctx:
                adapter.run_opencode("opencode/big-pickle", "hello")
        self.assertIn("FREE LIMIT HIT", str(ctx.exception))

    def test_limit_helpers(self):
        self.assertTrue(adapter._is_free_model("openrouter/recursive/flint-v1.0:free"))
        self.assertTrue(adapter._is_free_model("opencode/kimi-k2.6-free"))
        self.assertFalse(adapter._is_free_model("openrouter/openai/gpt-4o"))
        self.assertTrue(adapter._looks_like_limit("Too Many Requests"))
        self.assertFalse(adapter._looks_like_limit("some normal failure"))


class TestShellFraming(unittest.TestCase):
    SHELL_MESSAGES = [
        {"role": "system", "content": "You are a shell command generator. Ensure the output is a valid shell command."},
        {"role": "user", "content": "a command that prints hello"},
    ]
    CHAT_MESSAGES = [
        {"role": "system", "content": "You are ShellGPT, a helpful assistant."},
        {"role": "user", "content": "hello"},
    ]

    def test_shell_prompt_gets_echo_guidance(self):
        prompt = adapter.flatten_messages(self.SHELL_MESSAGES)
        self.assertIn("use echo", prompt)
        self.assertIn("a command that prints hello", prompt)

    def test_chat_prompt_has_no_shell_guidance(self):
        prompt = adapter.flatten_messages(self.CHAT_MESSAGES)
        self.assertNotIn("use echo", prompt)


class TestScaffoldingStrip(unittest.TestCase):
    def test_reported_case_shell_trailing_rfl_tag(self):
        raw = "sudo apt-get update && apt list --upgradable\n</rfl:parameter>"
        self.assertEqual(
            adapter.strip_scaffolding(raw, "shell"),
            "sudo apt-get update && apt list --upgradable",
        )

    def test_shell_any_standalone_tag_removed(self):
        self.assertEqual(
            adapter.strip_scaffolding("echo hi\n</widget>", "shell"), "echo hi"
        )

    def test_shell_glued_trailing_tag_cut(self):
        self.assertEqual(
            adapter.strip_scaffolding("echo ok </rfl:parameter>", "shell"),
            "echo ok",
        )

    def test_shell_legit_redirects_preserved(self):
        raw = "echo hi > out.txt\ncat < in.txt\ngrep x file | wc -l"
        self.assertEqual(adapter.strip_scaffolding(raw, "shell"), raw)

    def test_harness_tag_removed_in_all_modes(self):
        for mode in ("shell", "code", "chat"):
            self.assertEqual(
                adapter.strip_scaffolding("real text\n</rfl:parameter>", mode),
                "real text",
            )

    def test_chat_keeps_real_html(self):
        raw = "<div>\nhello\n</div>"
        self.assertEqual(adapter.strip_scaffolding(raw, "chat"), raw)

    def test_code_keeps_real_html(self):
        raw = "<div>\nhello\n</div>"
        self.assertEqual(adapter.strip_scaffolding(raw, "code"), raw)

    def test_strip_thinking_blocks(self):
        raw = "<think>\nLet me reason about this.\n</think>\n\necho HELLO_OK"
        self.assertEqual(adapter.strip_scaffolding(raw, "shell"), "echo HELLO_OK")
        self.assertEqual(adapter.strip_scaffolding(raw, "chat"), "echo HELLO_OK")


class TestColabBackend(unittest.TestCase):
    def test_normalize_base_url(self):
        self.assertEqual(adapter.normalize_base_url("https://abc.ngrok-free.app/v1/"), "https://abc.ngrok-free.app")
        self.assertEqual(adapter.normalize_base_url("abc.ngrok-free.app/v1/chat/completions"), "https://abc.ngrok-free.app")
        self.assertEqual(adapter.normalize_base_url("http://127.0.0.1:11434/api/tags"), "http://127.0.0.1:11434")

    def test_resolve_route_colab_and_prefixes(self):
        colab_cfg = {"backend": "colab", "colab_url": "https://x.ngrok-free.app", "colab_model": "sgpt-ai"}
        self.assertEqual(adapter.resolve_route("sgpt-ai", colab_cfg), ("colab", "sgpt-ai"))
        self.assertEqual(adapter.resolve_route("qwen2.5-coder:7b", colab_cfg), ("colab", "qwen2.5-coder:7b"))
        self.assertEqual(adapter.resolve_route("opencode/beam-free", colab_cfg), ("opencode", "opencode/beam-free"))
        self.assertEqual(adapter.resolve_route("openrouter/x:free", colab_cfg), ("opencode", "openrouter/x:free"))

        oc_cfg = {"backend": "opencode", "colab_url": "https://x.ngrok-free.app", "colab_model": "sgpt-ai"}
        self.assertEqual(adapter.resolve_route("colab/qwen3:8b", oc_cfg), ("colab", "qwen3:8b"))
        self.assertEqual(adapter.resolve_route("ollama/llama3.1:8b", oc_cfg), ("colab", "llama3.1:8b"))
        self.assertEqual(adapter.resolve_route("beam-free", oc_cfg), ("opencode", "opencode/beam-free"))

    def test_colab_sends_ngrok_header_and_sanitizes_shell(self):
        captured = {}
        fake_reply = {
            "id": "chatcmpl-colab",
            "object": "chat.completion",
            "created": 123,
            "model": "sgpt-ai",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "<think>checking command</think>\n```bash\nss -tulnp\n```",
                },
                "finish_reason": "stop",
            }],
        }

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["payload"] = json.loads(req.data.decode())
            return FakeResponse(fake_reply)

        server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            colab_cfg = {"backend": "colab", "colab_url": "https://demo.ngrok-free.app/v1", "colab_model": "sgpt-ai"}
            with patch.object(adapter, "load_runtime_config", return_value=colab_cfg), \
                 patch.object(adapter, "urlopen", side_effect=fake_urlopen):
                body = json.dumps({
                    "model": "sgpt-ai",
                    "messages": [
                        {"role": "system", "content": "You are a shell command generator. Ensure the output is a valid shell command."},
                        {"role": "user", "content": "show listening ports"},
                    ],
                    "stream": False,
                }).encode()
                req = Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                              data=body, headers={"Content-Type": "application/json"})
                with client_urlopen(req, timeout=3) as r:
                    res = json.loads(r.read().decode())
            self.assertEqual(captured["url"], "https://demo.ngrok-free.app/v1/chat/completions")
            self.assertEqual(captured["headers"].get("ngrok-skip-browser-warning"), "true")
            self.assertEqual(res["choices"][0]["message"]["content"], "ss -tulnp")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_colab_tool_call_automatic_shim_fallback(self):
        from urllib.error import HTTPError
        calls = []

        def fake_urlopen(req, timeout):
            payload = json.loads(req.data.decode())
            calls.append(payload)
            if len(calls) == 1:
                err_body = json.dumps({"error": {"message": "registry.ollama.ai/model does not support tools"}}).encode()
                raise HTTPError(req.full_url, 400, "Bad Request", hdrs=None, fp=io.BytesIO(err_body))
            return FakeResponse({
                "id": "chatcmpl-shim",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": '{"tool_call": {"name": "execute_shell", "arguments": {"command": "uname -a"}}}',
                    },
                    "finish_reason": "stop",
                }],
            })

        colab_cfg = {"backend": "colab", "colab_url": "https://demo.ngrok-free.app", "colab_model": "gemma3:4b"}
        with patch.object(adapter, "urlopen", side_effect=fake_urlopen):
            res = adapter.run_colab("gemma3:4b", {
                "messages": [{"role": "user", "content": "check kernel"}],
                "tools": [{"type": "function", "function": {"name": "execute_shell", "description": "run", "parameters": {"type": "object"}}}],
            }, colab_cfg)
        self.assertEqual(len(calls), 2)
        self.assertIn("tools", calls[0])
        self.assertNotIn("tools", calls[1])
        self.assertEqual(res["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(res["choices"][0]["message"]["tool_calls"][0]["function"]["name"], "execute_shell")


class TestSgptFreeCLI(unittest.TestCase):
    def test_cli_colab_opencode_set_model_and_help(self):
        import importlib.machinery
        import importlib.util
        import shutil
        cli_path = None
        for cand in (
            os.path.join(os.path.dirname(__file__), "sgpt-free"),
            shutil.which("sgpt-free") or "",
            os.path.expanduser("~/.local/bin/sgpt-free"),
        ):
            if cand and os.path.isfile(cand):
                cli_path = cand
                break
        if not cli_path:
            self.skipTest("sgpt-free executable not found")
        loader = importlib.machinery.SourceFileLoader("sgpt_free_cli", cli_path)
        spec = importlib.util.spec_from_loader("sgpt_free_cli", loader)
        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)

        with tempfile.TemporaryDirectory() as td:
            cfg_dir = adapter.Path(td)
            with patch.object(cli, "CFG_DIR", cfg_dir), \
                 patch.object(cli, "SGPTRC", cfg_dir / ".sgptrc"), \
                 patch.object(cli, "FREE_CFG", cfg_dir / "sgpt-free.json"), \
                 patch.object(cli, "fetch_colab_models", return_value=["sgpt-ai"]), \
                 patch.object(cli, "ensure_adapter", return_value=True):
                self.assertEqual(cli.cmd_colab(["https://demo.ngrok-free.app"]), 0)
                saved = cli.load_free_cfg()
                self.assertEqual(saved["backend"], "colab")
                self.assertEqual(saved["colab_url"], "https://demo.ngrok-free.app")
                self.assertEqual(saved["colab_model"], "sgpt-ai")
                self.assertEqual(cli.read_sgptrc()["DEFAULT_MODEL"], "sgpt-ai")

                self.assertEqual(cli.cmd_set_model(["qwen3:8b"]), 0)
                self.assertEqual(cli.read_sgptrc()["DEFAULT_MODEL"], "qwen3:8b")

                self.assertEqual(cli.cmd_opencode(["opencode/beam-free"]), 0)
                self.assertEqual(cli.load_free_cfg()["backend"], "opencode")
                self.assertEqual(cli.read_sgptrc()["DEFAULT_MODEL"], "opencode/beam-free")

                self.assertEqual(cli.cmd_functions(True), 0)
                self.assertEqual(cli.read_sgptrc()["OPENAI_USE_FUNCTIONS"], "true")

                # Help should work even without sgpt installed locally
                with patch.object(cli.shutil, "which", return_value=None):
                    self.assertEqual(cli.cmd_help(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

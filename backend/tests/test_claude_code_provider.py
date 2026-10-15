"""Proveedor Claude Code con un ejecutor de procesos SIMULADO (no se lanza la CLI real)."""

import json
import subprocess
import sys

import pytest

from app.ai.claude_code import ClaudeCodeProvider, extract_json
from app.config import Settings
from app.errors import AIUnavailable


class FakeRun:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, args, **kw):
        self.calls.append((args, kw))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        rc, envelope = r
        return subprocess.CompletedProcess(args, rc, stdout=json.dumps(envelope), stderr="")


def provider(results, **settings):
    run = FakeRun(results)
    s = Settings(claude_code_path=sys.executable, **settings)  # cualquier ejecutable existente
    return ClaudeCodeProvider(s, runner=run), run


def ok(result, model="claude-sonnet-x"):
    return (0, {"type": "result", "is_error": False, "result": result, "modelUsage": {model: {}}})


def test_isolated_invocation_and_parsing(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "clave-secreta")
    p, run = provider([ok('```json\n{"summary": "Resumen ñ"}\n```')], claude_code_model="sonnet")
    out = p.executive_summary({"name": "X"}, {"duration_working_days": 3})
    assert out.summary == "Resumen ñ"
    args, kw = run.calls[0]
    assert args[args.index("--tools") + 1] == ""          # sin herramientas
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert args[args.index("--model") + 1] == "sonnet"
    assert "<<<DATOS>>>" in kw["input"]                    # el prompt va por stdin
    assert "SECRETS_ENCRYPTION_KEY" not in kw["env"]               # sin secretos del backend
    assert p.model == "claude-sonnet-x"


def test_records_model_with_most_output():
    envelope = {"type": "result", "is_error": False, "result": '{"summary": "x"}',
                "modelUsage": {"claude-haiku": {"outputTokens": 20}, "claude-opus": {"outputTokens": 900}}}
    p, _ = provider([(0, envelope)])
    p.executive_summary({}, {})
    assert p.model == "claude-opus"


def test_retries_once_on_invalid_json():
    p, run = provider([ok("no es json"), ok('{"summary": "ok"}')])
    assert p.executive_summary({}, {}).summary == "ok"
    assert len(run.calls) == 2 and "no cumplió el esquema" in run.calls[1][1]["input"]


def test_not_logged_in_message():
    p, _ = provider([(1, {"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})])
    with pytest.raises(AIUnavailable) as exc:
        p.executive_summary({}, {})
    assert "/login" in exc.value.message and exc.value.code == "ai_not_configured"


def test_timeout_is_reported():
    p, _ = provider([subprocess.TimeoutExpired("claude", 1)])
    with pytest.raises(AIUnavailable):
        p.executive_summary({}, {})


def test_missing_cli():
    with pytest.raises(AIUnavailable):
        ClaudeCodeProvider(Settings(claude_code_path="Z:/no/existe/claude.exe"))


def test_extract_json_variants():
    assert extract_json('Acá va: {"a": 1} listo') == {"a": 1}
    assert extract_json('{"a": [1, 2]}') == {"a": [1, 2]}

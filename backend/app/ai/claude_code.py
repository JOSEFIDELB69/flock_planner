"""Proveedor de IA de Flock Planner: la CLI de Claude Code en modo headless (`claude -p`).

Requiere la CLI instalada y una sesión iniciada (`claude` → /login) en la máquina del backend.
Medidas de aislamiento:

* todas las herramientas desactivadas (`--tools ""`): el modelo no puede leer archivos, ejecutar comandos ni
  navegar, así que un texto malicioso dentro de un requisito no puede provocar acciones;
* sin servidores MCP (`--strict-mcp-config`), sin configuraciones de proyecto y sin persistir la sesión;
* se ejecuta en un directorio temporal vacío (no ve el repositorio ni su CLAUDE.md);
* el prompt va por stdin (evita el límite de longitud de la línea de comandos de Windows);
* el entorno del proceso no recibe los secretos del backend.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.ai import prompts
from app.ai.schemas import DocumentRequirements, ExecutiveSummary, GeneratedBacklog, ScenarioExplanation
from app.config import Settings
from app.errors import AIUnavailable
from app.schemas import AnalysisResult

T = TypeVar("T", bound=BaseModel)

SECRET_ENV = {"SECRETS_ENCRYPTION_KEY", "DATABASE_URL"}


def find_claude_cli(configured: str | None) -> str | None:
    if configured:
        return configured if Path(configured).exists() else None
    found = shutil.which("claude")
    if found:
        return found
    # CLI incluida en la app de escritorio de Claude (Windows / macOS)
    patterns = [
        os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code", "*", "*", "claude.exe"),
        os.path.expanduser("~/Library/Application Support/Claude/claude-code/*/*/claude"),
        os.path.expanduser("~/.local/bin/claude"),
    ]
    candidates = [p for pat in patterns for p in glob.glob(pat)]
    return max(candidates, key=os.path.getmtime) if candidates else None


def extract_json(text: str) -> object:
    """Acepta JSON puro, en bloque ```json``` o rodeado de texto."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


class ClaudeCodeProvider:
    name = "claude_code"
    is_simulated = False

    def __init__(self, settings: Settings, runner=subprocess.run):
        self.cli = find_claude_cli(settings.claude_code_path)
        if not self.cli:
            raise AIUnavailable(
                "No encontramos la CLI de Claude Code. Instalala o indicá su ruta en CLAUDE_CODE_PATH.",
                code="ai_not_configured")
        self.configured_model = settings.claude_code_model
        self.model = settings.claude_code_model or "claude-code"
        self.timeout = settings.claude_code_timeout_seconds
        self._run = runner

    def _invoke(self, system: str, user: str, files: dict[str, bytes] | None = None) -> str:
        # sin archivos: ninguna herramienta. Con archivos: solo Read (lectura), y la CLI en modo headless
        # rechaza leer fuera de la carpeta aislada (no hay forma de conceder permisos de forma interactiva).
        tools = "Read" if files else ""
        args = [self.cli, "-p", "--output-format", "json", "--tools", tools, "--no-session-persistence",
                "--strict-mcp-config", "--setting-sources", "", "--system-prompt", system]
        if self.configured_model:
            args += ["--model", self.configured_model]
        env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
        with tempfile.TemporaryDirectory(prefix="pm_agent_cc_") as tmp:
            # ruta larga real: la CLI marca como sospechosas las rutas cortas 8.3 de Windows (JOSBAR~1)
            workdir = str(Path(tmp).resolve())
            for name, data in (files or {}).items():
                (Path(workdir) / name).write_bytes(data)
            try:
                proc = self._run(args, input=user, capture_output=True, text=True, encoding="utf-8",
                                 cwd=workdir, env=env, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                raise AIUnavailable("Claude Code no respondió a tiempo. Probá de nuevo o aumentá "
                                    "CLAUDE_CODE_TIMEOUT_SECONDS.")
            except OSError:
                raise AIUnavailable("No se pudo ejecutar la CLI de Claude Code.")
        try:
            envelope = json.loads(proc.stdout)
        except (json.JSONDecodeError, TypeError):
            raise AIUnavailable("Claude Code devolvió una respuesta inesperada. Probá de nuevo.",
                                {"stderr": (proc.stderr or "")[:300]})
        result = str(envelope.get("result") or "")
        if envelope.get("is_error") or proc.returncode != 0:
            if "login" in result.lower():
                raise AIUnavailable("Claude Code no tiene una sesión iniciada. Abrí una terminal, ejecutá "
                                    "`claude` y usá /login; después probá de nuevo.", code="ai_not_configured")
            raise AIUnavailable(f"Claude Code devolvió un error: {result[:200]}")
        usage = envelope.get("modelUsage") or {}
        if usage:
            # la CLI puede usar un modelo chico para tareas internas: se registra el que más tokens generó
            self.model = max(usage, key=lambda m: (usage[m] or {}).get("outputTokens", 0))
        return result

    def _call(self, messages: list[dict[str, str]], schema: type[T], files: dict[str, bytes] | None = None) -> T:
        system = messages[0]["content"]
        user = messages[1]["content"]
        last_error, previous = "", ""
        for _attempt in range(2):
            prompt = user if not last_error else (
                user + "\n\nTu respuesta anterior no cumplió el esquema:\n" + previous[:6000]
                + "\nError: " + last_error + "\nDevolvé SOLO el JSON corregido.")
            previous = self._invoke(system, prompt, files)
            try:
                return schema.model_validate(extract_json(previous))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc)[:1500]
        raise AIUnavailable("La respuesta de Claude Code no tuvo el formato esperado. Probá de nuevo.",
                            {"validation": last_error}, code="ai_invalid_response")

    def analyze_requirements(self, project, requirements):
        return self._call(prompts.analysis_messages(project, requirements), AnalysisResult)

    def generate_backlog(self, project, requirements, analysis, answers, profiles, extra):
        return self._call(prompts.backlog_messages(project, requirements, analysis, answers, profiles, extra),
                          GeneratedBacklog)

    def executive_summary(self, project, metrics):
        return self._call(prompts.summary_messages(project, metrics), ExecutiveSummary)

    def extract_requirements_from_document(self, project, filename: str, kind: str, data: bytes):
        """El agente lee el archivo directamente (PDF y texto). Un .docx no se puede leer como archivo:
        se le entrega su texto; el original queda adjunto sin cambios."""
        if kind == "docx":
            from app.services.documents import extract_text

            name, payload, converted = "documento.txt", extract_text(filename, data).text.encode("utf-8"), True
        else:
            name, payload, converted = ("documento.pdf" if kind == "pdf" else "documento.txt"), data, False
        return self._call(prompts.document_messages(project, name, filename, converted), DocumentRequirements,
                          files={name: payload})

    def explain_scenarios(self, project, comparisons):
        return self._call(prompts.scenario_messages(project, comparisons), ScenarioExplanation)

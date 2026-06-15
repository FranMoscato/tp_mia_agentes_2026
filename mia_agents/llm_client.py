"""Cliente LLM por defecto — wrapper fino sobre Bedrock y Ollama.

Este archivo es FIJO. No lo edites. Su única responsabilidad es traducir
entre el formato de mensajes del framework y la API del proveedor.

Toda la lógica interesante del framework — bucle del agente, gestión de
memoria, reintentos ante fallos transitorios, validación y reparación de
salida estructurada, logging — debe vivir **en el agente**, no aquí. De
otro modo los tests de conformidad, que sustituyen este cliente por
`MockLLMClient`, no podrán ejercitarla y no contará para la nota.

El andamiaje incluye proveedores para AWS Bedrock y Ollama. Si necesitan
un proveedor distinto, NO modifiquen este archivo. En su lugar:

    1. Implementen su propia clase en `student_framework/` que satisfaga
       el protocolo `mia_agents.protocols.LLMClient` (un único método
       `chat(...) -> LLMResponse`).
    2. Pásenla al agente vía configuración:

        agent = build_agent({"llm_client": my_custom_client})

El propio `MockLLMClient` que usan los tests es un ejemplo de esa misma
sustitución por protocolo.
"""

from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any

import boto3
import ollama

from mia_agents._env import load_env_files
from mia_agents.types import LLMResponse, ToolCall, ToolSchema

# Cada entrada: ToolSchema (recomendado) o dict ya normalizado con to_llm_spec().
ToolSpecInput = ToolSchema | dict[str, Any]


class _BaseLLMProvider(ABC):
    """Lógica compartida entre proveedores; cada subclase adapta mensajes y tools."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpecInput] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse: ...

    @staticmethod
    def _tool_specs_as_dicts(
        tools: list[ToolSpecInput] | None,
    ) -> list[dict[str, Any]]:
        """`ToolSchema` → dict con name, description, parameters (JSON Schema)."""
        if not tools:
            return []
        specs: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, ToolSchema):
                specs.append(tool.to_llm_spec())
            else:
                specs.append(tool)
        return specs

    @staticmethod
    def _parameters_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
        return spec.get("parameters", {"type": "object", "properties": {}})

    @classmethod
    def _format_tools(cls, tools: list[ToolSpecInput]) -> list[dict[str, Any]]:
        return [
            cls._wrap_tool_spec(spec)
            for spec in cls._tool_specs_as_dicts(tools)
        ]

    @staticmethod
    @abstractmethod
    def _wrap_tool_spec(spec: dict[str, Any]) -> dict[str, Any]:
        """Un tool en el formato nativo del proveedor (Ollama vs Bedrock Converse)."""
        ...


def _pick(obj: Any, name: str, default: Any = None) -> Any:
    """Lee un campo del objeto, sea atributo (Pydantic) o clave (dict).

    Las respuestas del SDK de Ollama pueden volver como modelos Pydantic
    o como dicts en versiones distintas. Este helper aísla esa ambigüedad
    para que el resto del código se centre en QUÉ campo queremos, no en
    CÓMO está envuelto. Solo considera "ausente" si el atributo es None;
    valores falsos pero presentes (0, "", []) se devuelven tal cual.
    """
    val = getattr(obj, name, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _arguments_to_dict(raw_args: Any) -> dict[str, Any]:
    """Coacciona un campo `arguments` de tool call a dict (para Ollama saliente).

    Nuestro `ToolCall.arguments` interno es un string JSON; el formato de
    Ollama exige dict. Algunas fuentes nos lo dan ya como dict (e.g. al
    re-enviar historial recién construido). Aceptamos cualquiera de los
    dos. JSON malformado o ausente cae a {} en lugar de propagar el error.
    """
    if isinstance(raw_args, str):
        if not raw_args:
            return {}
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {}
    return raw_args or {}


def _arguments_to_json_string(raw_args: Any) -> str:
    """Serializa un campo `arguments` (Ollama entrante) a string JSON.

    Es la inversa de `_arguments_to_dict`: para `ToolCall.arguments` queremos
    siempre un string. La mayoría de modelos Ollama emiten dict; algunos
    emiten string ya serializado, que pasamos tal cual.
    """
    if isinstance(raw_args, dict):
        return json.dumps(dict(raw_args), ensure_ascii=False)
    if isinstance(raw_args, str):
        return raw_args
    return json.dumps(raw_args)


def _provider_raw_response(resp: Any) -> dict[str, Any] | None:
    """Payload crudo del proveedor (dict o Pydantic); None si no es serializable."""
    if isinstance(resp, dict):
        return resp
    model_dump = getattr(resp, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return None


class OllamaProvider(_BaseLLMProvider):
    """Cliente nativo para un servidor Ollama local (o remoto).

    Usa el SDK oficial `ollama` y soporta:
      - Mensajes multi-turno con tool calls (los models de Ollama compatibles
        emiten tool_calls; nosotros sintetizamos un `id` por llamada porque
        Ollama no lo expone).
      - Modo de salida estructurada: `response_format` recibe un JSON
        Schema y se pasa como `format` a Ollama.
      - Contexto configurable: el valor por defecto de Ollama (~2048) es
        insuficiente para nuestros escenarios; aquí usamos 16384 salvo
        que se pase otro a `num_ctx`.

    Variables de entorno:
      - `OLLAMA_HOST`: host del servidor (defecto: http://localhost:11434).
      - `OLLAMA_MODEL`: modelo (defecto: llama3.1).

    El payload crudo del SDK va en `LLMResponse.raw_response` (p. ej.
    `done_reason`); no forma parte del contrato normalizado del agente.
    """

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        num_ctx: int = 16384,
        default_format: dict[str, Any] | None = None,
    ) -> None:
        self._client = ollama.Client(
            host=host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        )
        self._model = model or os.environ.get("OLLAMA_MODEL", "llama3.1")
        self._num_ctx = num_ctx
        self._default_format = default_format

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpecInput] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        normalized = self._normalize_messages(messages, system)
        ollama_tools = self._format_tools(tools) if tools else None

        fmt: dict[str, Any] | None = (
            response_format if response_format is not None else self._default_format
        )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": normalized,
            "options": {"temperature": temperature, "num_ctx": self._num_ctx},
        }
        if ollama_tools:
            kwargs["tools"] = ollama_tools
        if fmt is not None:
            kwargs["format"] = fmt

        resp = self._client.chat(**kwargs)
        return self._to_llm_response(resp)

    # -- internos --------------------------------------------------------

    @staticmethod
    def _normalize_messages(
        messages: list[dict[str, Any]], system: str | None
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            role = m.get("role")
            if role == "system":
                # Si el agente embebe system en la lista, lo ignoramos:
                # ya lo hemos antepuesto via el parámetro `system`.
                continue
            if role == "tool":
                out.append({"role": "tool", "content": str(m.get("content", ""))})
                continue
            if role == "assistant" and m.get("tool_calls"):
                tcs = [
                    {
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": _arguments_to_dict(
                                tc.get("function", {}).get("arguments")
                            ),
                        }
                    }
                    for tc in m["tool_calls"]
                ]
                out.append(
                    {
                        "role": "assistant",
                        "content": m.get("content") or "",
                        "tool_calls": tcs,
                    }
                )
                continue
            # Caso por defecto: pasar role + content tal cual.
            out.append(
                {"role": role or "user", "content": m.get("content", "") or ""}
            )
        return out

    @staticmethod
    def _wrap_tool_spec(spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "parameters": _BaseLLMProvider._parameters_from_spec(spec),
            },
        }

    @staticmethod
    def _to_llm_response(resp: Any) -> LLMResponse:
        # `resp` puede ser un Pydantic `ChatResponse` (ollama >= 0.4) o un
        # dict en versiones futuras; `_pick` aísla esa diferencia.
        msg = _pick(resp, "message")
        if msg is None:
            return LLMResponse(
                content=None,
                tool_calls=[],
                raw_response=_provider_raw_response(resp),
            )

        tool_calls: list[ToolCall] = []
        for tc in _pick(msg, "tool_calls") or []:
            fn = _pick(tc, "function")
            if fn is None:
                continue
            tool_calls.append(
                ToolCall(
                    # Ollama no emite tool_call_id; lo sintetizamos para
                    # que el agente pueda referenciarlo en turnos siguientes.
                    id=_pick(tc, "id") or f"call_{uuid.uuid4().hex[:8]}",
                    name=_pick(fn, "name") or "",
                    arguments=_arguments_to_json_string(
                        _pick(fn, "arguments", default={})
                    ),
                )
            )

        content = _pick(msg, "content")
        return LLMResponse(
            content=content or None,  # "" -> None: vacío == sin texto
            tool_calls=tool_calls,
            input_tokens=_pick(resp, "prompt_eval_count"),
            output_tokens=_pick(resp, "eval_count"),
            raw_response=_provider_raw_response(resp),
        )


class BedrockProvider(_BaseLLMProvider):
    """Cliente nativo para AWS Bedrock vía la API Converse.

    Usa `boto3` con la cadena estándar de credenciales: lee
    `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` y, opcionalmente,
    `AWS_SESSION_TOKEN` del entorno (compatibles con setups SSO/STS).

    La API Converse normaliza el formato de mensajes de la familia Amazon
    Nova y otros modelos Bedrock compatibles con tool use.

    Variables de entorno:
      - `BEDROCK_MODEL_ID`: id completo del modelo
        (e.g. `amazon.nova-lite-v1:0`).
      - `AWS_REGION` / `AWS_DEFAULT_REGION`: región (defecto: `us-east-1`).

    `response_format` forma parte del protocolo `LLMClient` pero **no**
    lo implementa este provider: en M2 `structured_call` usa la tool
    `final_result`; Ollama sí pasa
    `response_format` al `format` nativo.

    El payload crudo de Converse va en
    `LLMResponse.raw_response` (p. ej. `stopReason`); no forma parte del
    contrato normalizado del agente.
    """

    def __init__(
        self,
        model: str | None = None,
        region: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self._model = model or os.environ.get("BEDROCK_MODEL_ID")
        if not self._model:
            raise RuntimeError(
                "Define BEDROCK_MODEL_ID o pásalo como argumento al "
                "constructor de BedrockProvider."
            )
        self._region = (
            region
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self._max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", region_name=self._region)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpecInput] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "modelId": self._model,
            "messages": self._normalize_messages(messages),
            "inferenceConfig": {
                "maxTokens": self._max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            kwargs["system"] = [{"text": system}]
        if tools:
            kwargs["toolConfig"] = {"tools": self._format_tools(tools)}

        resp = self._client.converse(**kwargs)
        return self._to_llm_response(resp)

    # -- internos --------------------------------------------------------

    @staticmethod
    def _normalize_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Traduce el historial interno al formato Converse.

        Mapeo:
          user                     -> {role: user, content: [{text: ...}]}
          assistant (texto)        -> {role: assistant, content: [{text: ...}]}
          assistant (+ tool_calls) -> bloques {text} y {toolUse}
          tool (resultado)         -> agrupa N resultados consecutivos en
                                       UN user msg con {toolResult} blocks
                                       (Converse exige que los resultados
                                       sigan inmediatamente al toolUse)
        """
        out: list[dict[str, Any]] = []
        i = 0
        while i < len(messages):
            m = messages[i]
            role = m.get("role")
            if role == "system":
                i += 1
                continue
            if role == "user":
                out.append(
                    {"role": "user", "content": [{"text": m.get("content") or ""}]}
                )
                i += 1
                continue
            if role == "assistant":
                blocks: list[dict[str, Any]] = []
                text = m.get("content") or ""
                if text:
                    blocks.append({"text": text})
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    blocks.append(
                        {
                            "toolUse": {
                                "toolUseId": tc.get("id")
                                or f"call_{uuid.uuid4().hex[:8]}",
                                "name": fn.get("name", ""),
                                "input": _arguments_to_dict(fn.get("arguments")),
                            }
                        }
                    )
                if blocks:
                    out.append({"role": "assistant", "content": blocks})
                i += 1
                # Agrupar mensajes 'tool' consecutivos en un único user msg.
                tool_blocks: list[dict[str, Any]] = []
                while i < len(messages) and messages[i].get("role") == "tool":
                    tm = messages[i]
                    tool_blocks.append(
                        {
                            "toolResult": {
                                "toolUseId": tm.get("tool_call_id", ""),
                                "content": [
                                    {"text": str(tm.get("content", ""))}
                                ],
                            }
                        }
                    )
                    i += 1
                if tool_blocks:
                    out.append({"role": "user", "content": tool_blocks})
                continue
            if role == "tool":
                # tool huérfano (sin assistant previo). Lo envolvemos como
                # user con toolResult para preservar la información.
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "toolResult": {
                                    "toolUseId": m.get("tool_call_id", ""),
                                    "content": [
                                        {"text": str(m.get("content", ""))}
                                    ],
                                }
                            }
                        ],
                    }
                )
                i += 1
                continue
            # default: tratar como user con texto plano.
            out.append(
                {"role": role or "user", "content": [{"text": m.get("content") or ""}]}
            )
            i += 1
        return out

    @staticmethod
    def _wrap_tool_spec(spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "toolSpec": {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "inputSchema": {"json": _BaseLLMProvider._parameters_from_spec(spec)},
            }
        }

    @staticmethod
    def _to_llm_response(resp: dict[str, Any]) -> LLMResponse:
        message = (resp.get("output") or {}).get("message") or {}
        blocks = message.get("content") or []

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in blocks:
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(
                    ToolCall(
                        id=tu.get("toolUseId") or f"call_{uuid.uuid4().hex[:8]}",
                        name=tu.get("name", ""),
                        arguments=json.dumps(
                            tu.get("input") or {}, ensure_ascii=False
                        ),
                    )
                )

        usage = resp.get("usage") or {}
        return LLMResponse(
            content="".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
            raw_response=_provider_raw_response(resp),
        )


class LLMClient:
    """Wrapper liviano con un constructor estático `from_env()`."""

    def __init__(self, provider: _BaseLLMProvider) -> None:
        self._provider = provider

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpecInput] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        return self._provider.chat(
            messages=messages,
            tools=tools,
            system=system,
            temperature=temperature,
            response_format=response_format,
        )

    @staticmethod
    def from_env() -> "LLMClient":
        # Levanta configuración de un `.env` (Bedrock/Ollama) si existe.
        # No pisa variables ya presentes ni inyecta refs op:// sin resolver.
        load_env_files()
        # Cada proveedor se selecciona por su env var "específica":
        # OLLAMA_HOST para local, BEDROCK_MODEL_ID para AWS Bedrock.
        # Usar BEDROCK_MODEL_ID en lugar de solo AWS_ACCESS_KEY_ID evita
        # falsos positivos cuando las credenciales AWS están en el
        # entorno por otras razones (S3, CI/CD, etc.).
        if os.environ.get("OLLAMA_HOST"):
            return LLMClient(OllamaProvider())
        if os.environ.get("BEDROCK_MODEL_ID"):
            return LLMClient(BedrockProvider())
        raise RuntimeError("Define OLLAMA_HOST o BEDROCK_MODEL_ID")

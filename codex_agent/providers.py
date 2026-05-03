from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import requests


class ProviderError(RuntimeError):
    """Raised when a provider is unavailable or fails."""


class BaseProvider(ABC):
    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self.enabled = bool(config.get("enabled", True))

    @abstractmethod
    def healthcheck(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def available_models(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        model: str,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float = 0.2,
    ) -> str:
        raise NotImplementedError


class OllamaProvider(BaseProvider):
    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name, config)
        self.base_url = str(config.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = int(config.get("timeout_seconds", 180))

    def healthcheck(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            return {"ok": True, "reason": "reachable"}
        except requests.RequestException as exc:
            return {"ok": False, "reason": str(exc)}

    def available_models(self) -> List[str]:
        status = self.healthcheck()
        if not status["ok"]:
            return []

        response = requests.get(f"{self.base_url}/api/tags", timeout=5)
        response.raise_for_status()
        data = response.json()
        return [item["name"] for item in data.get("models", [])]

    def generate(
        self,
        model: str,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float = 0.2,
    ) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        data = response.json()
        text = data.get("response", "")
        if not text:
            raise ProviderError("Ollama returned an empty response.")
        return text.strip()


class OpenInterpreterProvider(BaseProvider):
    def healthcheck(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "disabled"}
        try:
            from interpreter import OpenInterpreter  # noqa: F401
        except Exception as exc:  # pragma: no cover - import varies by install
            return {"ok": False, "reason": str(exc)}
        return {"ok": True, "reason": "importable"}

    def available_models(self) -> List[str]:
        models = self.config.get("models", [])
        return [str(item) for item in models]

    def generate(
        self,
        model: str,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float = 0.2,
    ) -> str:
        try:
            from interpreter import OpenInterpreter
        except Exception as exc:  # pragma: no cover - optional dependency
            raise ProviderError(f"OpenInterpreter import failed: {exc}") from exc

        session = OpenInterpreter()
        session.auto_run = bool(self.config.get("auto_run", False))
        session.llm.model = model
        session.llm.temperature = temperature
        raw = session.chat(f"{system_prompt}\n\n{prompt}".strip())
        return _flatten_interpreter_output(raw)


def _flatten_interpreter_output(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: List[str] = []
        for item in raw:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for inner in content:
                        if isinstance(inner, dict) and "text" in inner:
                            parts.append(str(inner["text"]))
            else:
                parts.append(str(item))
        return "\n".join(part.strip() for part in parts if str(part).strip())
    return json.dumps(raw, ensure_ascii=False)


def build_providers(settings: Dict[str, Any]) -> Dict[str, BaseProvider]:
    providers: Dict[str, BaseProvider] = {}
    for name, config in settings.get("providers", {}).items():
        provider_type = config.get("type")
        if provider_type == "ollama":
            providers[name] = OllamaProvider(name, config)
        elif provider_type == "open_interpreter":
            providers[name] = OpenInterpreterProvider(name, config)
    return providers

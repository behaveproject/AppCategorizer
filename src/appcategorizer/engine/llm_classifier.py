# Copyright (c) 2026, Sorbonne Université, CNRS, LIP6.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the
# GNU Lesser General Public License v3.0 (LGPL-3.0-only)
# which accompanies this distribution, and is available at
# https://www.gnu.org/licenses/lgpl-3.0.en.html

import os
from json import JSONDecodeError

import httpx

from .embedding_classifier import CATEGORY_DESCRIPTIONS
from .logger import logger

# Load .env file if python-dotenv is installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

CATEGORIES = list(CATEGORY_DESCRIPTIONS.keys())

SYSTEM_PROMPT = (
    "You are an application classifier. "
    "Given an application name, respond with EXACTLY one of the following "
    "categories and nothing else:\n" + "\n".join(CATEGORIES)
)

# Per-provider configuration: base URL, environment variable name for the API
# key, wire format, and the default model to use when none is specified.
PROVIDER_CONFIGS: dict[str, dict] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "format": "openai",
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "format": "anthropic",
        "default_model": "claude-haiku-4-5-20251001",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "env_key": "MISTRAL_API_KEY",
        "format": "openai",
        "default_model": "mistral-small-latest",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "env_key": "GEMINI_API_KEY",
        "format": "gemini",
        "default_model": "gemini-2.0-flash",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "env_key": None,
        "format": "openai",
        "default_model": "llama3.2",
    },
    # Generic OpenAI-compatible endpoint; user must supply base_url and model.
    "custom": {
        "base_url": None,
        "env_key": "LLM_API_KEY",
        "format": "openai",
        "default_model": None,
    },
}

KNOWN_PROVIDERS = list(PROVIDER_CONFIGS.keys())


class LLMClassifierError(Exception):
    """Base error for cloud LLM classification failures."""


class LLMConfigurationError(LLMClassifierError):
    """Raised when the LLM provider configuration is invalid or incomplete."""


class LLMRequestError(LLMClassifierError):
    """Raised when the LLM API request fails."""


def _resolve_api_key(provider: str, explicit_key: str | None) -> str | None:
    """Return the API key using: explicit arg > env var > .env file."""
    if explicit_key:
        return explicit_key

    config = PROVIDER_CONFIGS[provider]
    env_key_name = config.get("env_key")
    if env_key_name:
        value = os.environ.get(env_key_name)
        if value:
            return value

    # Gemini accepts either GEMINI_API_KEY or the older GOOGLE_API_KEY.
    if provider == "gemini":
        return os.environ.get("GOOGLE_API_KEY")

    return None


def _extract_response_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except (JSONDecodeError, ValueError):
        return response.text.strip() or None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    return response.text.strip() or None


def _build_request_error_message(provider: str, model: str, status: int | None = None) -> str:
    base = f"{provider}/{model} request failed"
    if status is None:
        return base

    if status == 429:
        return f"{base} with HTTP {status} (rate limit or quota exceeded)"

    return f"{base} with HTTP {status}"


class LLMClassifier:
    """Classifies an application name by querying a remote LLM API."""

    def __init__(
        self,
        provider: str,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        if provider not in PROVIDER_CONFIGS:
            raise LLMConfigurationError(
                f"Unknown LLM provider '{provider}'. "
                f"Supported providers: {', '.join(KNOWN_PROVIDERS)}"
            )

        config = PROVIDER_CONFIGS[provider]

        if provider == "custom" and not base_url:
            raise LLMConfigurationError(
                "Provider 'custom' requires an explicit llm_base_url."
            )

        self.provider = provider
        self.format: str = config["format"]
        self.model: str = model or config["default_model"]
        self.base_url: str = (base_url or config["base_url"]).rstrip("/")

        if self.model is None:
            raise LLMConfigurationError(
                f"Provider '{provider}' requires an explicit llm_model."
            )

        self.api_key: str | None = _resolve_api_key(provider, api_key)

        # Ollama runs locally and typically needs no authentication.
        if provider != "ollama" and not self.api_key:
            env_var = config.get("env_key") or "LLM_API_KEY"
            raise LLMConfigurationError(
                f"No API key found for provider '{provider}'. "
                f"Pass --api-key, set the {env_var} environment variable, "
                f"or add it to a .env file."
            )

    async def classify(self, app_name: str) -> str:
        """Send the sanitized app name to the LLM and return a category."""
        logger.debug(f"[LLM] Querying {self.provider}/{self.model} for '{app_name}'")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if self.format == "openai":
                    raw = await self._call_openai(client, app_name)
                elif self.format == "anthropic":
                    raw = await self._call_anthropic(client, app_name)
                elif self.format == "gemini":
                    raw = await self._call_gemini(client, app_name)
                else:
                    raise LLMConfigurationError(f"Unknown request format: {self.format}")
            except httpx.HTTPStatusError as exc:
                detail = _extract_response_error_detail(exc.response)
                status = exc.response.status_code
                message = _build_request_error_message(self.provider, self.model, status)
                if detail:
                    logger.debug(f"[LLM] Error detail: {detail}")
                raise LLMRequestError(message) from None
            except httpx.RequestError as exc:
                logger.debug(f"[LLM] Network error detail: {exc}")
                raise LLMRequestError(
                    _build_request_error_message(self.provider, self.model)
                    + ": network error"
                ) from None

        result = raw.strip()
        logger.debug(f"[LLM] Raw response: '{result}'")

        if result not in CATEGORIES:
            logger.warning(
                f"[LLM] Response '{result}' is not a recognised category, "
                f"falling back to 'Others'."
            )
            return "Others"

        return result

    # ------------------------------------------------------------------ #
    # Private per-format request helpers                                   #
    # ------------------------------------------------------------------ #

    async def _call_openai(self, client: httpx.AsyncClient, app_name: str) -> str:
        """OpenAI Chat Completions format (also used by Mistral, Ollama, custom)."""
        response = await client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key or 'ollama'}",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": app_name},
                ],
                "temperature": 0,
                "max_tokens": 20,
            },
        )
        response.raise_for_status()
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (JSONDecodeError, ValueError, KeyError, IndexError, TypeError):
            raise LLMRequestError(
                f"{self.provider}/{self.model} returned an invalid response format"
            ) from None

    async def _call_anthropic(self, client: httpx.AsyncClient, app_name: str) -> str:
        """Anthropic Messages API format."""
        response = await client.post(
            f"{self.base_url}/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": app_name}],
                "max_tokens": 20,
            },
        )
        response.raise_for_status()
        try:
            return response.json()["content"][0]["text"]
        except (JSONDecodeError, ValueError, KeyError, IndexError, TypeError):
            raise LLMRequestError(
                f"{self.provider}/{self.model} returned an invalid response format"
            ) from None

    async def _call_gemini(self, client: httpx.AsyncClient, app_name: str) -> str:
        """Google Gemini generateContent format."""
        response = await client.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            params={"key": self.api_key},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": app_name}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 20},
            },
        )
        response.raise_for_status()
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (JSONDecodeError, ValueError, KeyError, IndexError, TypeError):
            raise LLMRequestError(
                f"{self.provider}/{self.model} returned an invalid response format"
            ) from None
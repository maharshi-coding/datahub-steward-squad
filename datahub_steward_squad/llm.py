"""Zero-dependency Anthropic (Claude) client for the Steward Squad.

The steward team is genuinely agentic when an ``ANTHROPIC_API_KEY`` is present:
a Claude model reasons over the grounded DataHub findings and writes the
steward-facing narrative. When no key is available (the default offline demo),
callers fall back to the deterministic path, so the project always runs.

This module intentionally uses only the Python standard library so the project
keeps zero required dependencies. If the official ``anthropic`` SDK happens to be
installed it is preferred, otherwise a small ``urllib`` client calls the Messages
API directly.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

# Default to a current, capable Claude model. Override with STEWARD_LLM_MODEL.
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LLMUnavailable(RuntimeError):
    """Raised when an LLM engine is requested but cannot be constructed."""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    # Headroom: current Claude models think by default, and thinking shares the
    # output budget with the response, so keep this comfortably above the brief size.
    max_tokens: int = 2000
    api_url: str = DEFAULT_API_URL
    timeout: float = 60.0
    # NOTE: sampling params (temperature/top_p/top_k) are intentionally omitted.
    # The current Claude models (claude-sonnet-5 and the rest of the Claude 5
    # family) reject `temperature` with a 400 "deprecated for this model".


def resolve_config(model: str | None = None) -> LLMConfig | None:
    """Build an :class:`LLMConfig` from the environment, or ``None`` if no key."""

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    return LLMConfig(
        api_key=api_key,
        model=(model or os.environ.get("STEWARD_LLM_MODEL") or DEFAULT_MODEL).strip(),
        max_tokens=int(os.environ.get("STEWARD_LLM_MAX_TOKENS", "2000")),
    )


class LLMClient:
    """Minimal Claude Messages client with an SDK fast-path and urllib fallback."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._sdk = _try_load_sdk(config.api_key)

    def complete(self, system: str, prompt: str) -> str:
        """Return the model's text response for a single-turn request."""

        if self._sdk is not None:
            return self._complete_sdk(system, prompt)
        return self._complete_http(system, prompt)

    def _complete_sdk(self, system: str, prompt: str) -> str:
        message = self._sdk.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        ).strip()

    def _complete_http(self, system: str, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.config.api_url,
            data=payload,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self.config.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:  # pragma: no cover - network path
            detail = error.read().decode("utf-8", "replace")
            raise LLMUnavailable(f"Anthropic API error {error.code}: {detail}") from error
        except urllib.error.URLError as error:  # pragma: no cover - network path
            raise LLMUnavailable(f"Could not reach Anthropic API: {error.reason}") from error

        blocks = body.get("content", [])
        return "".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        ).strip()


def _try_load_sdk(api_key: str):
    try:
        import anthropic  # type: ignore
    except Exception:  # pragma: no cover - SDK optional
        return None
    try:
        return anthropic.Anthropic(api_key=api_key)
    except Exception:  # pragma: no cover - defensive
        return None

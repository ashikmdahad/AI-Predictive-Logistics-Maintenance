from __future__ import annotations

import json
import os
from typing import Dict

import httpx

from ..core.config import settings


class AssistantUnavailable(Exception):
    """Raised when the AI assistant cannot fulfill a request."""


def _google_credentials() -> tuple[str, str]:
    api_key = os.getenv("GOOGLE_GENAI_API_KEY", settings.GOOGLE_GENAI_API_KEY)
    model = os.getenv("GOOGLE_GENAI_MODEL", settings.GOOGLE_GENAI_MODEL)
    return api_key, model


def _timeout_seconds() -> float:
    return float(os.getenv("EXTERNAL_TIMEOUT_SECONDS", str(settings.EXTERNAL_TIMEOUT_SECONDS)))


def generate_response(system_prompt: str, payload: Dict) -> Dict[str, str]:
    """Send a structured request to Google Generative AI and return text output."""

    api_key, model = _google_credentials()
    if not api_key:
        raise AssistantUnavailable("Google Generative AI is not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "system_instruction": {
            "role": "model",
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(payload, default=str)}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "text/plain",
            "maxOutputTokens": 512,
            "temperature": 0.2,
        },
    }

    headers = {"Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=_timeout_seconds()) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network failures handled gracefully
        raise AssistantUnavailable(str(exc)) from exc

    data = response.json()
    text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    if not text.strip():
        raise AssistantUnavailable("Empty response from Google Assistant")

    return {"text": text.strip(), "model": model}


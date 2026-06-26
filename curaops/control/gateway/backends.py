"""
OpenAI-compatible Backend-Proxy fuer den Pi-Harness-native AI Gateway.

Proxyt Requests an lokale vLLM/OpenAI-compatible Backends.
Supportet Streaming (SSE) und normale Responses.
Kein LiteLLM. Keine externen Provider-Abhaengigkeiten.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional

import httpx

# Default-Timeouts
DEFAULT_TIMEOUT = 120.0
CONNECT_TIMEOUT = 10.0


class BackendProxy:
    """
    Proxy fuer OpenAI-compatible /v1/chat/completions Endpunkte.

    Nutzt httpx.AsyncClient fuer nicht-blockierende Requests.
    Streaming wird ueber SSE (Server-Sent Events) unterstuetzt.
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = httpx.Timeout(timeout, connect=CONNECT_TIMEOUT)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def proxy_chat(
        self,
        base_url: str,
        model: str,
        messages: list[Dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any] | AsyncIterator[bytes]:
        """
        Proxyt eine /v1/chat/completions Anfrage an das Backend.

        Args:
            base_url: Backend-URL (z.B. http://localhost:8001/v1).
            model: Modellname fuer das Backend.
            messages: Chat-Nachrichten im OpenAI-Format.
            stream: Ob Streaming angefordert wurde.
            **kwargs: Zusaetzliche Parameter (temperature, max_tokens, etc.).

        Returns:
            Bei stream=False: Response-Dict.
            Bei stream=True: AsyncIterator ueber SSE-Chunks.
        """
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        # Zusaetzliche Parameter uebernehmen
        for key in ("temperature", "max_tokens", "top_p", "frequency_penalty",
                     "presence_penalty", "stop", "n", "response_format"):
            if key in kwargs:
                payload[key] = kwargs[key]

        client = await self._get_client()

        if stream:
            return self._stream_response(client, url, payload)

        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def _stream_response(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: Dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """
        Streamt eine SSE-Response vom Backend.

        Yielded rohe SSE-Chunks (bytes) an den Aufrufer.
        """
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk

    async def fetch_models(self, base_url: str) -> Dict[str, Any]:
        """
        Ruft /v1/models vom Backend ab.

        Args:
            base_url: Backend-URL.

        Returns:
            Models-Response im OpenAI-Format.
        """
        url = f"{base_url.rstrip('/')}/models"
        client = await self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def health_check(self, base_url: str) -> Dict[str, Any]:
        """
        Prueft die Gesundheit eines Backends.

        Versucht /v1/models. Gibt Status zurueck.
        """
        try:
            result = await self.fetch_models(base_url)
            model_count = len(result.get("data", []))
            return {"status": "healthy", "model_count": model_count}
        except httpx.ConnectError:
            return {"status": "unreachable", "error": "Verbindung fehlgeschlagen"}
        except httpx.TimeoutException:
            return {"status": "timeout", "error": "Timeout"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

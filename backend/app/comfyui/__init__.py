import httpx

from app.schemas import ComfyuiStatus

_TIMEOUT_SECONDS = 5.0


class ComfyUIClient:
    """Async client for talking to ComfyUI.

    Phase 1 only performs connectivity/status checks. Prompt submission,
    WebSocket monitoring, and output retrieval arrive in Phase 3.
    A new client is created per base URL and cached; a failed request
    never raises - callers always get a status dict.
    """

    def __init__(self) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}

    def _client(self, base_url: str) -> httpx.AsyncClient:
        client = self._clients.get(base_url)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                base_url=base_url.rstrip("/"),
                timeout=_TIMEOUT_SECONDS,
            )
            self._clients[base_url] = client
        return client

    async def get_status(self, base_url: str) -> ComfyuiStatus:
        try:
            response = await self._client(base_url).get("/system_stats")
            response.raise_for_status()
            data = response.json()
            system = data.get("system", {}) if isinstance(data, dict) else {}
            return ComfyuiStatus(
                connected=True,
                version=system.get("comfyui_version"),
                detail=None,
            )
        except Exception as exc:  # noqa: BLE001 - report, never propagate
            return ComfyuiStatus(
                connected=False,
                version=None,
                detail=f"{type(exc).__name__}: {exc}",
            )

    async def close(self) -> None:
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()


comfyui_client = ComfyUIClient()

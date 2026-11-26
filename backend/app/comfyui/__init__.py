import time
import uuid

import httpx

from app.schemas import ComfyuiStatus

_TIMEOUT_SECONDS = 10.0
_VIEW_TIMEOUT = 60.0


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    """Async client for ComfyUI HTTP API.

    Network failures raise ComfyUIError except in get_status(), which always
    returns a status object.
    """

    def __init__(self) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._object_info_cache: dict[str, tuple[float, dict]] = {}

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

    async def _request(self, base_url: str, method: str, path: str, **kwargs):
        try:
            response = await self._client(base_url).request(method, path, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise ComfyUIError(f"ComfyUI unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise ComfyUIError(
                f"ComfyUI {path} failed ({response.status_code}): {response.text[:300]}"
            )
        return response

    async def object_info(self, base_url: str, max_age: float = 300.0) -> dict:
        now = time.monotonic()
        cached = self._object_info_cache.get(base_url)
        if cached and now - cached[0] < max_age:
            return cached[1]
        response = await self._request(base_url, "GET", "/object_info")
        info = response.json()
        self._object_info_cache[base_url] = (now, info)
        return info

    async def upload_image(
        self, base_url: str, filename: str, data: bytes, content_type: str
    ) -> str:
        response = await self._request(
            base_url,
            "POST",
            "/upload/image",
            files={"image": (filename, data, content_type)},
            data={"subfolder": "", "type": "input", "overwrite": "false"},
        )
        body = response.json()
        name = body.get("name")
        if not name:
            raise ComfyUIError(f"ComfyUI upload returned no name: {body}")
        return name

    async def submit_prompt(
        self, base_url: str, workflow: dict, client_id: str
    ) -> str:
        response = await self._request(
            base_url,
            "POST",
            "/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        body = response.json()
        prompt_id = body.get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"ComfyUI rejected prompt: {body}")
        return prompt_id

    async def get_queue(self, base_url: str) -> dict:
        response = await self._request(base_url, "GET", "/queue")
        return response.json().get("queue", {"running": [], "pending": []})

    async def get_history(self, base_url: str, prompt_id: str) -> dict | None:
        response = await self._request(base_url, "GET", f"/history/{prompt_id}")
        body = response.json()
        return body.get(prompt_id)

    async def view_image(
        self,
        base_url: str,
        filename: str,
        subfolder: str,
        image_type: str,
    ) -> bytes:
        client = self._client(base_url)
        try:
            response = await client.get(
                "/view",
                params={"filename": filename, "subfolder": subfolder, "type": image_type},
                timeout=_VIEW_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001
            raise ComfyUIError(f"ComfyUI view failed: {exc}") from exc
        if response.status_code >= 400:
            raise ComfyUIError(f"ComfyUI view failed ({response.status_code})")
        return response.content

    async def interrupt(self, base_url: str, prompt_id: str) -> None:
        await self._request(
            base_url, "POST", "/interrupt", json={"prompt_id": prompt_id}
        )

    def new_client_id(self) -> str:
        return uuid.uuid4().hex

    async def close(self) -> None:
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()


comfyui_client = ComfyUIClient()

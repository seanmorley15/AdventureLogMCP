"""Thin async client for the AdventureLog REST API (`/api/...`).

Every error AdventureLog returns has the same body, `{detail, code, fields?}`
(backend/server/API.md, "Errors"); it becomes an `AdventureLogError` here.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import httpx

from .config import Settings, get_settings


class AdventureLogError(Exception):
    """An error answered by AdventureLog (or by the proxy in front of it)."""

    def __init__(
        self,
        detail: str,
        *,
        code: str = "error",
        status: int = 0,
        fields: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        etag: str | None = None,
    ):
        super().__init__(detail)
        self.etag = etag  # on a 412, the record's current version
        self.detail = detail
        self.code = code
        self.status = status
        self.fields = fields or {}
        self.extra = extra or {}

    def for_model(self) -> str:
        """A message the model can act on: what went wrong, the code, and which fields to fix."""
        parts = [f"{self.detail} (code: {self.code}, HTTP {self.status})" if self.status else self.detail]
        if self.fields:
            parts.append(
                "Fields: "
                + "; ".join(
                    f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in self.fields.items()
                )
            )
        return " ".join(parts)


def new_id() -> str:
    """A random id, for parts of a record (checklist items) that need no repeat protection of their own."""
    return str(uuid.uuid4())


_ID_NAMESPACE = uuid.UUID("6f2c1d52-6a0e-4d52-9a54-2c1f0f6f6c10")


def stable_id(api_key: str, kind: str, payload: Any) -> str:
    """A record id derived from who is asking, what kind of record, and exactly what they asked for.

    AdventureLog lets a client choose the id of what it creates, and answers a repeat of an id it has
    already stored with that record instead of making another (API.md, "Client-chosen ids"). Deriving the
    id from the request means a model that repeats an identical call (after a timeout, or because it lost
    track) gets the original record back. The caller's key is part of the input, so two users never
    collide, and the key itself is hashed.
    """
    who = hashlib.sha256(api_key.encode()).hexdigest()
    body = json.dumps(payload, sort_keys=True, default=str)
    return str(uuid.uuid5(_ID_NAMESPACE, f"{who}|{kind}|{body}"))


class AdventureLogClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings or get_settings()
        self._http = httpx.AsyncClient(
            base_url=self.settings.api_base,
            timeout=self.settings.request_timeout,
            transport=transport,
            # The web frontend answers `/api/x/` with a 308 to `/api/x` (method and body are kept on 308).
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        with_etag: bool = False,
    ) -> Any:
        """Call `path` (e.g. ``/api/account/``) as the owner of ``api_key``. Returns parsed JSON, or None for 204.

        With ``with_etag`` it returns ``(json, etag)``: the record's version, to send back as ``If-Match``."""
        h = {"X-API-Key": api_key, "Accept": "application/json", "Origin": self.settings.origin}
        if headers:
            h.update(headers)
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = await self._http.request(method, path, params=clean or None, json=json, headers=h)
        except httpx.TimeoutException as e:
            raise AdventureLogError("AdventureLog did not answer in time.", code="upstream_timeout", status=504) from e
        except httpx.HTTPError as e:
            raise AdventureLogError(
                f"Could not reach AdventureLog at {self.settings.api_base} ({type(e).__name__}).",
                code="upstream_error",
                status=502,
            ) from e

        if resp.status_code == 204 or not resp.content:
            if resp.is_success:
                return (None, None) if with_etag else None
        try:
            body = resp.json()
        except ValueError:
            body = None

        if resp.is_success:
            return (body, resp.headers.get("etag")) if with_etag else body

        if isinstance(body, dict) and "detail" in body:
            extra = {k: v for k, v in body.items() if k not in {"detail", "code", "fields"}}
            raise AdventureLogError(
                str(body["detail"]),
                code=str(body.get("code", "error")),
                status=resp.status_code,
                fields=body.get("fields"),
                extra=extra,
                etag=resp.headers.get("etag"),
            )
        raise AdventureLogError(
            f"AdventureLog answered HTTP {resp.status_code} with an unexpected body.",
            code="upstream_error",
            status=resp.status_code,
        )

    async def get(self, path: str, *, api_key: str, **kw: Any) -> Any:
        return await self.request("GET", path, api_key=api_key, **kw)

    async def post(self, path: str, *, api_key: str, **kw: Any) -> Any:
        return await self.request("POST", path, api_key=api_key, **kw)

    async def patch(self, path: str, *, api_key: str, **kw: Any) -> Any:
        return await self.request("PATCH", path, api_key=api_key, **kw)

    async def delete(self, path: str, *, api_key: str, **kw: Any) -> Any:
        return await self.request("DELETE", path, api_key=api_key, **kw)

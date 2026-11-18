"""Tiny raw-REST helper for Lago.

Section 2 deliberately talks to Lago over plain HTTP: that is what SaaSCo's own
automation does, and it maps 1:1 onto the curl sequence we hand to the customer.
Section 3 uses the official Python SDK (lago-python-client) instead.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .config import LAGO_API_KEY, LAGO_API_URL, require


class LagoError(RuntimeError):
    def __init__(self, status: int, body: Any):
        super().__init__(f"Lago API {status}: {body}")
        self.status = status
        self.body = body


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=f"{LAGO_API_URL}/api/v1",
        headers={"Authorization": f"Bearer {require(LAGO_API_KEY, 'LAGO_API_KEY')}"},
        timeout=30,
    )


def call(method: str, path: str, json: Any = None, params: Any = None, retries: int = 4) -> Any:
    """Call Lago; retry on 429/5xx with exponential backoff; raise LagoError otherwise."""
    with _client() as c:
        for attempt in range(retries + 1):
            r = c.request(method, path, json=json, params=params)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(min(2**attempt, 10))
                continue
            if r.status_code >= 400:
                try:
                    body = r.json()
                except ValueError:
                    body = r.text
                raise LagoError(r.status_code, body)
            return r.json() if r.content else None
    return None


def get(path: str, **params: Any) -> Any:
    return call("GET", path, params=params or None)


def post(path: str, body: Any) -> Any:
    return call("POST", path, json=body)


def put(path: str, body: Any) -> Any:
    return call("PUT", path, json=body)


def delete(path: str) -> Any:
    return call("DELETE", path)


def get_or_none(path: str, **params: Any) -> Any:
    try:
        return get(path, **params)
    except LagoError as e:
        if e.status == 404:
            return None
        raise


def paginate(path: str, root: str, per_page: int = 100, **params: Any):
    """Yield every item of a paginated Lago list endpoint."""
    page = 1
    while True:
        data = get(path, page=page, per_page=per_page, **params)
        yield from data.get(root, [])
        meta = data.get("meta") or {}
        if not meta.get("next_page"):
            break
        page = meta["next_page"]

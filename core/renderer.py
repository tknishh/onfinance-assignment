from __future__ import annotations

from typing import Optional, Tuple

import httpx

from core.cache import get_svg_cache, prompt_hash, set_svg_cache
from core.config import get_settings

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15.0)
    return _client


async def _post_svg(base_url: str, code: str) -> Tuple[bool, Optional[str], Optional[str]]:
    url = f"{base_url.rstrip('/')}/plantuml/svg"
    client = _get_client()
    resp = await client.post(
        url,
        content=code.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
    )
    if resp.status_code == 200:
        return True, resp.text, None
    return False, None, resp.text or f"HTTP {resp.status_code}"


async def render_svg(code: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Returns (ok, svg_text, error_text). Caches successful SVGs."""
    key = prompt_hash(code)
    cached = get_svg_cache(key)
    if cached:
        return True, cached, None

    settings = get_settings()
    try:
        ok, svg, err = await _post_svg(settings.kroki_url, code)
        if ok and svg:
            set_svg_cache(key, svg)
            return True, svg, None
        if err is not None:
            return False, None, err
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
        pass

    # Fallback to public Kroki
    try:
        ok, svg, err = await _post_svg(settings.kroki_fallback_url, code)
        if ok and svg:
            set_svg_cache(key, svg)
            return True, svg, None
        return False, None, err
    except Exception as e:
        return False, None, str(e)

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any, Optional

from diskcache import Cache

from core.config import get_settings


@lru_cache
def _cache() -> Cache:
    settings = get_settings()
    return Cache(settings.cache_dir)


def prompt_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def get_gen_cache(key: str) -> Optional[dict[str, Any]]:
    return _cache().get(f"gen:{key}")


def set_gen_cache(key: str, value: dict[str, Any]) -> None:
    _cache().set(f"gen:{key}", value, expire=60 * 60 * 24 * 7)


def get_svg_cache(key: str) -> Optional[str]:
    return _cache().get(f"svg:{key}")


def set_svg_cache(key: str, svg: str) -> None:
    _cache().set(f"svg:{key}", svg, expire=60 * 60 * 24 * 30)

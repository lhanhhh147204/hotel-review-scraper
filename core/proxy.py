# core/proxy.py
from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    host:     str
    port:     int
    username: str
    password: str
    country:  str  # VN, US, JP, SG...

    @property
    def url(self) -> str:
        return (
            f"http://{self.username}:{self.password}"
            f"@{self.host}:{self.port}"
        )


class ProxyPool:
    """Quản lý proxy pool với rotation tự động."""

    def __init__(self, proxies: list[ProxyConfig]):
        self._pool  = itertools.cycle(proxies)
        self._lock  = asyncio.Lock()
        self._bad:   set[str]        = set()
        self._usage: dict[str, int]  = {}
        self._total = len(proxies)

    async def get(self) -> Optional[ProxyConfig]:
        async with self._lock:
            for _ in range(self._total + 10):
                proxy = next(self._pool)
                if proxy.url not in self._bad:
                    self._usage[proxy.url] = (
                        self._usage.get(proxy.url, 0) + 1
                    )
                    return proxy
        return None
    async def mark_bad(self, proxy: ProxyConfig) -> None:
        async with self._lock:
            self._bad.add(proxy.url)
            log.warning(
                f"Proxy bị block: {proxy.host}:{proxy.port}"
            )

    async def health_check(self, proxy: ProxyConfig) -> bool:
        """Kiểm tra proxy còn sống không."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        "https://httpbin.org/ip",
                        proxy=proxy.url,
                        timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    @property
    def stats(self) -> dict:
        return {
            "total":  self._total,
            "bad":    len(self._bad),
            "active": self._total - len(self._bad),
        }

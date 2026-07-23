"""SSRF protection — validate URLs against private-network ranges.

Uses shared pattern: `ssrf-protection`.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import ClassVar
from urllib.parse import urlparse

import httpx


class SSRFProtector:
    """Validate URLs to prevent server-side request forgery."""

    ALLOWED_SCHEMES: ClassVar[set[str]] = {"https"}
    BLOCKED_NETWORKS: ClassVar[list[ipaddress.IPv4Network]] = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
    ]
    BLOCKED_HOSTS: ClassVar[set[str]] = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "169.254.169.254",
    }

    def validate_url(self, url: str) -> bool:
        """Return False if URL targets a blocked range, True if safe."""
        parsed = urlparse(url)

        if parsed.scheme not in self.ALLOWED_SCHEMES:
            return False

        hostname = parsed.hostname
        if hostname is None:
            return False

        if hostname in self.BLOCKED_HOSTS:
            return False

        # Resolve hostname to IP and check against blocked ranges
        try:
            ip_str = socket.gethostbyname(hostname)
            addr = ipaddress.ip_address(ip_str)
            for network in self.BLOCKED_NETWORKS:
                if addr in network:
                    return False
        except socket.gaierror:
            # Unresolvable hostname — block it
            return False

        return True

    async def safe_fetch(self, url: str) -> bytes:
        """Fetch URL content with SSRF checks. Raises ValueError on blocked URLs."""
        if not self.validate_url(url):
            raise ValueError(f"Blocked URL: {url}")

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=30.0)
            resp.raise_for_status()
            return resp.content

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""DNS lookups over HTTPS (works everywhere, needs no extra libraries). Used by verify and deliverability checks."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

_CACHE: dict[tuple[str, str], tuple[float, list[str]]] = {}
TYPES = {"A": 1, "MX": 15, "TXT": 16, "CNAME": 5}
ENDPOINTS = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")


def lookup(name: str, rtype: str = "TXT", ttl: int = 600) -> tuple[list[str] | None, str]:
    """Returns (answers, status). answers is None when the lookup itself failed (network), [] when the name has no such record."""
    key = (name.lower(), rtype)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1], "cached"
    last = "no answer"
    for ep in ENDPOINTS:
        try:
            req = urllib.request.Request(ep + "?" + urllib.parse.urlencode({"name": name, "type": rtype}),
                                         headers={"Accept": "application/dns-json", "User-Agent": "email-autopilot/1.0"})
            d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace"))
            status = d.get("Status", 2)
            if status == 3:  # NXDOMAIN: the name does not exist
                _CACHE[key] = (time.time(), [])
                return [], "nxdomain"
            ans = [a.get("data", "") for a in d.get("Answer", []) if a.get("type") == TYPES.get(rtype)]
            if rtype == "TXT":
                ans = [re.sub(r'"\s*"', "", a).strip('"') for a in ans]
            _CACHE[key] = (time.time(), ans)
            return ans, "ok"
        except Exception as ex:  # noqa: BLE001
            last = f"{type(ex).__name__}: {ex}"
    return None, last


def mx_hosts(domain: str) -> tuple[list[str] | None, str]:
    ans, st = lookup(domain, "MX")
    if ans is None:
        return None, st
    hosts = []
    for a in ans:
        parts = a.split()
        if len(parts) == 2:
            hosts.append((int(parts[0]) if parts[0].isdigit() else 99, parts[1].rstrip(".")))
    hosts.sort()
    return [h for _, h in hosts if h and h != "."], st

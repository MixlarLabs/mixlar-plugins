#!/usr/bin/env python3
"""Report publish results + the fresh catalog back to mixlar.net.

Reads ``published.json`` (written by sign_and_publish.py) and ``plugins.json``
(the regenerated catalog) and POSTs them to registry-published.php, which marks
submissions live and refreshes the server's catalog cache. Best-effort.

Env: MIXLAR_CALLBACK_URL, REGISTRY_CALLBACK_SECRET
"""
from __future__ import annotations

import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    url = os.environ.get("MIXLAR_CALLBACK_URL", "").strip()
    secret = os.environ.get("REGISTRY_CALLBACK_SECRET", "").strip()
    if not url or not secret:
        print("callback skipped (not configured)")
        return 0

    try:
        with open(os.path.join(ROOT, "published.json"), encoding="utf-8") as fh:
            pub = json.load(fh)
    except (OSError, ValueError):
        pub = {"published": []}
    try:
        with open(os.path.join(ROOT, "plugins.json"), encoding="utf-8") as fh:
            catalog = fh.read()
    except OSError:
        catalog = "[]"

    body = json.dumps({"published": pub.get("published", []),
                       "catalog": catalog}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {secret}",
                 "Content-Type": "application/json", "User-Agent": "mixlar-ci"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("callback", r.status, r.read().decode("utf-8", "replace")[:200])
    except Exception as e:  # noqa: BLE001
        print("callback failed:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

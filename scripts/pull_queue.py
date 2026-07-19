#!/usr/bin/env python3
"""Pull approved submissions from mixlar.net into ``incoming/``.

Runs in CI (publish-queue.yml). Authenticates to the registry queue endpoint
with the shared secret, writes each approved submission's unsigned package +
metadata into ``incoming/``, where ``sign_and_publish.py`` then signs and lists
them. This is the "pull" side — the server needs no GitHub credentials.

Env:
  MIXLAR_QUEUE_URL          the registry-queue.php endpoint
  REGISTRY_CALLBACK_SECRET  bearer secret (shared with the server)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCOMING = os.path.join(ROOT, "incoming")


def main() -> int:
    url = os.environ.get("MIXLAR_QUEUE_URL", "").strip()
    secret = os.environ.get("REGISTRY_CALLBACK_SECRET", "").strip()
    if not url or not secret:
        print("MIXLAR_QUEUE_URL / REGISTRY_CALLBACK_SECRET not set", flush=True)
        return 0  # nothing to do; don't fail the workflow

    req = urllib.request.Request(url, data=b"", method="POST",
                                 headers={"Authorization": f"Bearer {secret}",
                                          "User-Agent": "mixlar-ci"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        print(f"queue fetch failed: {e}", flush=True)
        return 0

    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not items:
        print("queue empty", flush=True)
        return 0

    os.makedirs(INCOMING, exist_ok=True)
    written = 0
    for it in items:
        fn = it.get("filename")
        b64 = it.get("mixplugin_b64")
        if not fn or not b64:
            continue
        base = fn[:-len(".mixplugin")] if fn.endswith(".mixplugin") else fn
        try:
            with open(os.path.join(INCOMING, fn), "wb") as fh:
                fh.write(base64.b64decode(b64))
            with open(os.path.join(INCOMING, base + ".meta.json"), "w", encoding="utf-8") as fh:
                json.dump(it.get("meta", {}), fh)
            written += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ! {fn}: {e}", flush=True)
    print(f"pulled {written} submission(s) into incoming/", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

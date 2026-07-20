#!/usr/bin/env python3
"""Sign approved submissions and publish them into the registry.

Runs in CI (see .github/workflows/sign.yml). For every package in ``incoming/``
it:

  1. unpacks the (unsigned) ``.mixplugin``,
  2. signs it with the ``mixlar-registry-1`` key (seed from the
     ``MIXLAR_SIGNING_KEY`` secret) using the SDK's own byte-faithful packer,
  3. writes the signed ``.mixplugin`` + a catalog ``entry.json`` into
     ``plugins/<id>/``,
  4. removes the incoming files,

then regenerates the root ``plugins.json`` from every ``plugins/*/entry.json``.

The signing/packaging uses the published ``mixlar-sdk`` so the produced
signature is identical to what the desktop app and SDK verify.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile

from mixlar import packaging  # from the pip-installed mixlar-sdk
from mixlar import permissions as _perms
from mixlar import scan as _scan
from mixlar import imaging as _imaging
from mixlar.manifest import read_manifest

# Set MIXLAR_ALLOW_HIGH_RISK=1 to sign despite high-risk findings (a human
# reviewer explicitly overriding). Undeclared-capability use is always refused.
_ALLOW_HIGH = os.environ.get("MIXLAR_ALLOW_HIGH_RISK") == "1"

KEY_ID = "mixlar-registry-1"
REPO_RAW = "https://raw.githubusercontent.com/MixlarLabs/mixlar-plugins/main"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCOMING = os.path.join(ROOT, "incoming")
PLUGINS = os.path.join(ROOT, "plugins")


def _seed() -> str:
    seed = os.environ.get("MIXLAR_SIGNING_KEY", "").strip()
    if not seed:
        sys.exit("MIXLAR_SIGNING_KEY is not set (GitHub Actions secret).")
    return seed


def _download_url(pid: str, fname: str) -> str:
    return f"{REPO_RAW}/plugins/{pid}/{fname}"


def _publish_one(mixplugin_path: str, seed: str) -> str | None:
    base = os.path.basename(mixplugin_path)[: -len(".mixplugin")]
    meta_path = os.path.join(INCOMING, base + ".meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)

    submission_id = meta.get("submission_id")

    with tempfile.TemporaryDirectory() as tmp:
        folder = packaging.unpack(mixplugin_path, tmp)
        man, err = read_manifest(folder)
        if err:
            print(f"  ! {base}: invalid manifest — {err}; skipping", flush=True)
            return None
        pid = man["id"]
        version = man["version"]

        # Security gate — the last automated check before we put the registry's
        # signature on this code. Two refusals:
        #  1. Undeclared capability use — always refused (declare it in permissions).
        #  2. Genuine malware smells — obfuscation, and dynamic code execution
        #     (eval/exec). NOT a blanket "high risk": a plugin that legitimately
        #     declares `native`/`subprocess` trips high-severity capability
        #     findings by design, and that's fine — it declared them. We only
        #     hard-block the patterns you can't justify by declaring a capability.
        report = _scan.scan_package(folder)
        declared = _perms.declared_caps(man)
        undeclared, _ = _perms.diff(declared, report.capabilities)
        if undeclared:
            print(f"  ! {pid}: REFUSED — uses undeclared capabilities "
                  f"{sorted(undeclared)} (declare them in permissions)", flush=True)
            return None
        danger = [f for f in report.findings
                  if f.category == "obfuscation"
                  or (f.category == "dynamic-code" and f.level == _scan.HIGH)]
        if danger and not _ALLOW_HIGH:
            hits = "; ".join(f"{f.file}:{f.line} {f.message}" for f in danger[:5])
            print(f"  ! {pid}: REFUSED — suspicious code (eval/exec/obfuscation): "
                  f"{hits} (set MIXLAR_ALLOW_HIGH_RISK=1 to override after review)", flush=True)
            return None

        out_name = f"{pid}-{version}.mixplugin"
        dest_dir = os.path.join(PLUGINS, pid)
        os.makedirs(dest_dir, exist_ok=True)
        signed_path = os.path.join(dest_dir, out_name)

        # Sign in place, then deterministically repack to the destination.
        packaging.pack(folder, out_path=signed_path, sign_with=(KEY_ID, seed))

        with open(signed_path, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()

        entry = {
            "id": pid,
            "name": man.get("name", pid),
            "version": version,
            "author": man.get("author", ""),
            "description": man.get("description", ""),
            "category": meta.get("category", "Other"),
            "icon": man.get("icon", "fa5s.puzzle-piece"),
            "icon_color": man.get("icon_color", meta.get("image_color", "")),
            "download_url": _download_url(pid, out_name),
            "sha256": sha,
            "has_widget": bool(man.get("widgets")),
        }
        # Custom plugin icon: if the plugin ships icon.png / hero.png / .jpg,
        # normalize it to the one standard SQUARE size (512×512) and publish it
        # next to the plugin; the catalog carries its URL. Square so the app can
        # cover-crop it into the Discover hero AND scale it down to a small icon.
        # Every plugin's icon is the same dimensions, so the store stays uniform.
        src_img = None
        for cand in ("icon.png", "icon.jpg", "icon.jpeg", "hero.png", "hero.jpg"):
            cp = os.path.join(folder, cand)
            if os.path.isfile(cp):
                src_img = cp
                break
        if src_img:
            png = _imaging.normalize_icon(src_img)
            if png:
                with open(os.path.join(dest_dir, "icon.png"), "wb") as fh:
                    fh.write(png)
                entry["image"] = _download_url(pid, "icon.png")
                print(f"    · card image normalized to {_imaging.ICON_SIZE}", flush=True)

        # Optional store-only fields the app tolerates as extras.
        for k in ("long_description", "social_url", "github_url"):
            if meta.get(k):
                entry[k] = meta[k]

        with open(os.path.join(dest_dir, "entry.json"), "w", encoding="utf-8") as fh:
            json.dump(entry, fh, indent=2, sort_keys=True)
        print(f"  + {pid} {version} signed ({sha[:16]}…)", flush=True)

    # Clean up the incoming pair.
    os.remove(mixplugin_path)
    if os.path.exists(meta_path):
        os.remove(meta_path)
    return {
        "id": pid,
        "version": version,
        "sha256": sha,
        "download_url": _download_url(pid, out_name),
        "submission_id": submission_id,
    }


def _rebuild_catalog() -> int:
    entries = []
    if os.path.isdir(PLUGINS):
        for pid in sorted(os.listdir(PLUGINS)):
            ej = os.path.join(PLUGINS, pid, "entry.json")
            if os.path.exists(ej):
                with open(ej, encoding="utf-8") as fh:
                    entries.append(json.load(fh))
    with open(os.path.join(ROOT, "plugins.json"), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return len(entries)


def main() -> int:
    seed = _seed()
    published = []
    if os.path.isdir(INCOMING):
        for name in sorted(os.listdir(INCOMING)):
            if name.endswith(".mixplugin"):
                res = _publish_one(os.path.join(INCOMING, name), seed)
                if res:
                    published.append(res)
    total = _rebuild_catalog()
    # Drop a summary the workflow posts back to mixlar.net (best-effort).
    with open(os.path.join(ROOT, "published.json"), "w", encoding="utf-8") as fh:
        json.dump({"published": published}, fh)
    print(f"Published {len(published)}; catalog now lists {total} plugin(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

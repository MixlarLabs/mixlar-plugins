# mixlar-plugins

The official registry of community plugins for [Mixlar](https://mixlar.net).
The Mixlar Control desktop app reads [`plugins.json`](./plugins.json) from this
repo to populate its plugin marketplace.

> **You don't submit here directly.** Plugins are published through the
> [Mixlar SDK](https://pypi.org/project/mixlar-sdk/) (`mixlar-sdk publish`) or
> the [Studio](https://mixlar.net/studio) — both require a signed-in
> mixlar.net account. Submissions go into review; once approved (or if you're a
> trusted author) they are **signed by Mixlar** and land here automatically.

## Layout

```
plugins.json              Catalog the app reads (auto-generated — do not edit)
plugins/<id>/
    <id>-<version>.mixplugin   Signed, installable plugin package
    entry.json                 That plugin's catalog entry (source of truth)
incoming/                 Approved-but-unsigned submissions (transient).
                          The server pushes here; the signing Action picks them
                          up, signs, relocates to plugins/, and deletes them.
scripts/sign_and_publish.py    The signer (runs in CI only).
.github/workflows/sign.yml     Signs incoming/ on push and rebuilds the catalog.
```

## Trust model

Every published plugin is signed with the `mixlar-registry-1` ed25519 key
(held only as a GitHub Actions secret — never in this repo). The desktop app
and SDK pin the matching **public** key, so a plugin that installs from this
registry is cryptographically verified as reviewed-and-signed by Mixlar. The
`author` field records who wrote it; identity is bound to their mixlar.net
account at publish time (only the account that owns an author handle can
publish under it).

## Removing a plugin

Delete its `plugins/<id>/` folder and the Action rebuilds `plugins.json`
without it. To actively kill an installed bad plugin, use the app-side
quarantine list, not this repo.

# incoming/

Transient staging for approved-but-unsigned submissions.

The mixlar.net server pushes an approved submission here as a pair:

```
incoming/<id>-<version>.mixplugin     the unsigned package
incoming/<id>-<version>.meta.json     store metadata (category, colors, links)
```

On push, `.github/workflows/sign.yml` runs `scripts/sign_and_publish.py`,
which signs the package with the `mixlar-registry-1` key, writes the signed
`.mixplugin` + `entry.json` into `plugins/<id>/`, regenerates the root
`plugins.json`, and deletes these incoming files. Nothing should live here for
more than a few seconds of CI time.

# Registry security & signing-key runbook

The Mixlar registry auto-trusts a plugin when it carries a valid ed25519
signature from a **pinned publisher key**. The community key is
`mixlar-registry-1`; its **private** half exists only as the `MIXLAR_SIGNING_KEY`
secret in this repo's **`signing` GitHub environment**, which is gated behind a
**required reviewer**. Nothing else can produce a trusted signature.

## How signing is protected

- `MIXLAR_SIGNING_KEY` is an **environment secret** (environment: `signing`), not
  a repo secret. Only a job that declares `environment: signing` can read it.
- The `signing` environment has a **required reviewer**. The signing job pauses
  until a maintainer approves it in the GitHub UI, so even a compromised push (or
  a malicious workflow edit) can't release the key without a human.
- The workflow is split: `check` (ungated, peeks the queue) → `sign`
  (environment-gated). Empty schedule runs never enter the environment, so
  reviewers aren't pinged for nothing.

**Keep it that way:** never move `MIXLAR_SIGNING_KEY` back to a repo secret, never
remove the required reviewer, and require review on changes to
`.github/workflows/**` (branch protection).

## If the signing key leaks — rotation runbook

Rotating means retiring `mixlar-registry-1` and shipping `mixlar-registry-2`.
Because the app **pins** public keys, clients only trust the new key after an app
update — so plan for a transition window.

### 1. Mint the new key
```bash
python -c "from mixlar.signing import generate_keypair; p,k=generate_keypair(); \
  open('seed.txt','w').write(p); print('PUBLIC mixlar-registry-2 =', k)"
```
Put the **private** seed into the `signing` environment secret and delete the old
one:
```bash
gh secret set MIXLAR_SIGNING_KEY --env signing --repo MixlarLabs/mixlar-plugins < seed.txt
rm -f seed.txt
```

### 2. Pin the new PUBLIC key **alongside** the old one (transition)
Add `mixlar-registry-2` to **both** keysets, keeping `mixlar-registry-1` so
already-installed plugins still verify during the transition:
- app `PC Software/mixlar_mini.py` → `_PUBLISHER_KEYS`
- SDK `src/mixlar/signing.py` → `PUBLISHER_KEYS`

Update `scripts/sign_and_publish.py` `KEY_ID = "mixlar-registry-2"`.

### 3. Ship + re-sign
- Release a new **mixlar-sdk** (new pinned key) to PyPI.
- **Rebuild the app** (`Builds\build.bat`) and push the update so clients pin the
  new key.
- **Re-sign every live plugin** with the new key: trigger the publish workflow so
  CI re-signs the catalog (or bump each submission back to `approved`).

### 4. Contain the leak
- **Quarantine** anything signed by the old key that you can't vouch for (the app
  quarantine kill-list, by id/version).
- Once clients have updated and the catalog is re-signed, **remove
  `mixlar-registry-1`** from both keysets in the next release. Anything still
  signed only by the old key then stops auto-trusting.

### 5. Post-mortem
Rotate the `REGISTRY_CALLBACK_SECRET` too (it's shared with mixlar.net's `.env`),
review who had access, and check the Actions logs for unauthorized `sign` runs.

## Reviewer checklist (before approving a `sign` run)

- The submission was approved in the mixlar.net admin panel (not injected).
- The diff to `.github/workflows/**` and `scripts/**` is expected (a malicious
  workflow edit is the main way to abuse an approval).
- Nothing unusual in the `check` job's reported count.

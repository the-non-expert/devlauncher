# Releasing devlauncher

This document covers the full release process: merging, tagging, and publishing to PyPI.

---

## How publishing works

Releases are triggered by pushing a `v*` tag to `main`. The `publish.yml` workflow:

1. Runs the full test suite as a gate
2. Builds the package (`python -m build`)
3. Publishes to PyPI via Trusted Publisher (OIDC — no API token required)

Publishing only happens when **both** conditions are met:
- The tag matches `v*` (e.g. `v0.2.0`)
- The test job passes

---

## One-time setup (Trusted Publisher)

Before the first release, register devlauncher on PyPI as a Trusted Publisher:

1. Go to [pypi.org](https://pypi.org) → your `devlauncher` project → Settings → "Add a trusted publisher"
2. Fill in:
   - **Owner:** `the-non-expert`
   - **Repository:** `devlauncher`
   - **Workflow filename:** `publish.yml`
   - **Environment:** leave blank (or `pypi` if you configure a GitHub environment)
3. Save — no token, no secret needed after this

---

## Release checklist

1. Merge the release PR into `main`
2. Pull main locally:
   ```
   git checkout main && git pull
   ```
3. Update version in `pyproject.toml` and `src/devlauncher/__init__.py`
4. Update `CHANGELOG.md` — move items from `[Unreleased]` to the new version section
5. Commit:
   ```
   git add pyproject.toml src/devlauncher/__init__.py CHANGELOG.md
   git commit -m "chore: release vX.Y.Z"
   ```
6. Tag and push:
   ```
   git tag vX.Y.Z
   git push origin main --tags
   ```
7. Watch the Actions tab — `publish.yml` will run tests then publish

---

## Versioning

devlauncher follows [Semantic Versioning](https://semver.org):

| Change | Version bump |
|--------|-------------|
| Bug fixes, docs, minor improvements | Patch (`0.2.0` → `0.2.1`) |
| New features, backwards-compatible | Minor (`0.2.0` → `0.3.0`) |
| Breaking changes to `dev.toml` format or CLI | Major (`0.2.0` → `1.0.0`) |

---

## Who can publish

Only repository owners and collaborators with write access can push tags and trigger publishing. PR contributors from forks have no write access to the repository — they cannot push tags.

> ⚠️ **Before adding collaborators:** GitHub branch protection rulesets do not cover tags by default. A collaborator with write access can push a `v*` tag and trigger a release. To prevent this, create a Tag ruleset under Settings → Rules → Rulesets → New ruleset → target: Tag, and restrict tag creation to repository admins only. Do this before granting write access to anyone.

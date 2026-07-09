# Worky — Git Workflow

> **Purpose:** Define the branch strategy, commit conventions, release process, and versioning approach for the Worky backend repository.
> **Audience:** All contributors.

---

## Table of Contents

1. [Branch Strategy](#1-branch-strategy)
2. [Branch Naming](#2-branch-naming)
3. [Commit Message Convention](#3-commit-message-convention)
4. [Working on a Feature](#4-working-on-a-feature)
5. [Merge Strategy](#5-merge-strategy)
6. [Release Process](#6-release-process)
7. [Versioning](#7-versioning)
8. [Hotfix Process](#8-hotfix-process)
9. [Example: Full Feature Lifecycle](#9-example-full-feature-lifecycle)

---

## 1. Branch Strategy

Worky uses **trunk-based development** with short-lived feature branches.

```
main  (protected — production-ready at all times)
  │
  ├── feature/outlook-calendar-fetcher      (short-lived)
  ├── feature/slack-mentions-fetcher        (short-lived)
  ├── fix/token-refresh-race-condition      (short-lived)
  └── release/v0.3.0                        (release prep — short-lived)
```

### `main`
- Always deployable. Every commit on `main` is production-quality.
- Protected: no direct pushes. All changes via pull request.
- Requires at least 1 approving review before merge.
- Requires all CI checks to pass (lint, typecheck, tests).

### Feature branches
- Branch from `main`, merge back to `main`.
- Lifetime: ideally under 3 days. Anything longer should be split into smaller PRs.
- Deleted immediately after merge.

### Release branches
- Created from `main` when preparing a tagged release.
- Used for final integration testing and documentation updates.
- Deleted after the release tag is created.

---

## 2. Branch Naming

```
<type>/<scope>-<short-description>
```

| Type | Purpose |
|---|---|
| `feature/` | New functionality |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Code restructuring with no behavior change |
| `test/` | Adding or improving tests |
| `chore/` | Dependencies, CI config, tooling |
| `release/` | Release preparation |

### Examples

```bash
# New features
feature/outlook-calendar-fetcher
feature/slack-connector-base
feature/context-builder-async-gather
feature/bob-service-interface

# Bug fixes
fix/token-refresh-on-401
fix/graph-client-missing-select-param
fix/normalizer-missing-attendees-crash

# Documentation
docs/update-connector-guide-examples
docs/add-slack-adr

# Maintenance
chore/upgrade-httpx-0.28
chore/add-ruff-config
test/add-normalizer-edge-cases
```

---

## 3. Commit Message Convention

Worky follows [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

### Types

| Type | Use for |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Restructuring without behavior change |
| `test` | Test additions or changes |
| `chore` | Build, tooling, dependencies |
| `perf` | Performance improvement |

### Scopes (use the affected module)

`outlook` · `slack` · `github` · `auth` · `context-builder` · `bob` · `recommendations` · `config` · `shared` · `docs` · `ci`

### Rules

- Subject line in **imperative mood**: "add" not "added" or "adds"
- Subject line ≤ 72 characters
- No period at end of subject line
- Body wraps at 72 characters
- Body explains *why*, not *what*
- Breaking changes: add `BREAKING CHANGE:` in footer

### Good Examples

```
feat(outlook): add CalendarFetcher for today's events

Fetches calendar events for the current UTC day using the calendarView
endpoint. Runs concurrently with EmailFetcher in OutlookConnector.

Refs #14
```

```
fix(auth): prevent token refresh race condition under concurrent requests

Under high load, two concurrent requests for the same expired token
would both trigger a refresh, causing the second refresh to fail with
an invalid_grant error. Added a per-user async lock to serialize
refresh calls.

Fixes #27
```

```
feat(bob): define BobService interface and MockBobService

MockBobService returns deterministic hardcoded recommendations for
development and testing. Real IBMBobService is injected when
APP_ENV=production.
```

```
chore: upgrade pydantic to 2.8.0

Resolves deprecation warnings on computed_field usage.
No behavior changes.
```

### Bad Examples (do not use)

```
fix stuff                          ← no type, no scope, vague
WIP: working on calendar           ← WIP commits should not be pushed
updated files                      ← tells nothing
feat: added the calendar fetcher   ← wrong tense ("added" vs "add")
```

---

## 4. Working on a Feature

### Step-by-step

```bash
# 1. Start from an up-to-date main
git checkout main
git pull origin main

# 2. Create your feature branch
git checkout -b feature/outlook-calendar-fetcher

# 3. Work in small, logical commits
git add app/connectors/outlook/fetchers/calendar.py
git commit -m "feat(outlook): add CalendarFetcher skeleton"

git add tests/connectors/outlook/test_calendar_fetcher.py
git commit -m "test(outlook): add unit tests for CalendarFetcher"

git add app/connectors/outlook/fetchers/calendar.py
git commit -m "feat(outlook): implement date range filtering in CalendarFetcher"

# 4. Keep your branch up to date (rebase, not merge)
git fetch origin
git rebase origin/main

# 5. Push and open a PR
git push origin feature/outlook-calendar-fetcher
```

### Keeping your branch current

Always rebase onto `main` (not merge) to keep a linear history:

```bash
git fetch origin
git rebase origin/main

# If there are conflicts:
# 1. Resolve conflicts in the marked files
# 2. git add <resolved-file>
# 3. git rebase --continue
```

**Never use `git merge main` into a feature branch.** Merge commits on feature branches pollute the PR diff.

---

## 5. Merge Strategy

### Squash and Merge (default)
All feature and fix PRs are **squash-merged** into `main`. This keeps `main` history clean — one logical PR = one commit on `main`.

The squash commit message is:
```
feat(outlook): add CalendarFetcher (#42)
```

After squash merge:
- Delete the feature branch immediately (GitHub does this automatically if configured)
- The feature branch's individual commits are no longer in `main`'s history

### Regular Merge (milestone PRs only)
Phase completion PRs (e.g., "Phase 7: Outlook Connector complete") use a regular merge commit to preserve the full development history of the milestone in `main`.

### Never rebase `main`
`main` history is immutable. Never force-push to `main`.

---

## 6. Release Process

Releases are created after completing a full phase milestone.

```bash
# 1. Ensure main is up to date and all CI passes
git checkout main
git pull origin main

# 2. Create a release branch for final integration testing
git checkout -b release/v0.2.0

# 3. Update ROADMAP.md — mark phase as complete
# 4. Update README.md — update status table
# 5. Commit documentation updates
git commit -m "docs: update ROADMAP and README for v0.2.0 release"

# 6. Merge release branch back to main (regular merge)
git checkout main
git merge release/v0.2.0

# 7. Tag the release
git tag -a v0.2.0 -m "Phase 7: Outlook Connector complete

Delivers the complete Outlook connector including:
- GraphAPIClient with retry logic
- CalendarFetcher and EmailFetcher
- OutlookNormalizer
- OutlookConnector(BaseConnector) with partial failure handling
- Full test suite (94% coverage)"

# 8. Push tag
git push origin main
git push origin v0.2.0

# 9. Delete release branch
git branch -d release/v0.2.0
git push origin --delete release/v0.2.0
```

---

## 7. Versioning

Worky uses **Semantic Versioning** (SemVer): `MAJOR.MINOR.PATCH`

| Segment | When to increment |
|---|---|
| `MAJOR` | Breaking changes to the widget API or WorkContext schema |
| `MINOR` | New connector added or new feature without breaking changes |
| `PATCH` | Bug fixes, documentation updates |

### Version map to phases

| Version | Milestone |
|---|---|
| `v0.1.0` | Phase 1 — Project Foundation |
| `v0.2.0` | Phase 2 — Outlook Authentication |
| `v0.3.0` | Phase 3 — Graph Client |
| `v0.4.0` | Phase 4 + 5 — Fetchers |
| `v0.5.0` | Phase 6 + 7 — Normalizer + Outlook Connector |
| `v0.6.0` | Phase 8 — Slack Connector |
| `v0.7.0` | Phase 9 — Context Builder |
| `v0.8.0` | Phase 10 — IBM Bob Integration |
| `v0.9.0` | Phase 11 — Recommendation Service |
| `v1.0.0` | Phase 12 + 13 — Widget Integration + Production Hardening |

---

## 8. Hotfix Process

For urgent production bugs discovered on `main`:

```bash
# 1. Branch from main directly
git checkout main
git pull origin main
git checkout -b fix/token-refresh-null-pointer

# 2. Fix, test, commit
git commit -m "fix(auth): handle null refresh_token in TokenRepository.get()"

# 3. Open PR with [HOTFIX] prefix in the title
# Title: "fix(auth): handle null refresh_token in TokenRepository.get() [HOTFIX]"

# 4. After merge, tag with a patch version
git tag -a v0.5.1 -m "Hotfix: null refresh_token crash in AuthService"
git push origin v0.5.1
```

---

## 9. Example: Full Feature Lifecycle

This example shows the complete lifecycle of implementing the `CalendarFetcher`.

```
Day 1, 09:00 — Start work
git checkout main && git pull origin main
git checkout -b feature/outlook-calendar-fetcher

Day 1, 11:00 — First commit
git commit -m "feat(outlook): add CalendarFetcher skeleton with GraphAPIClient dependency"

Day 1, 14:00 — Tests
git commit -m "test(outlook): add fixtures/calendar_events.json from Graph API"
git commit -m "test(outlook): add unit tests for CalendarFetcher happy path"

Day 1, 16:00 — Edge cases
git commit -m "feat(outlook): handle empty calendar (zero events response)"
git commit -m "test(outlook): add test for empty calendar response"

Day 2, 09:00 — Rebase and polish
git fetch origin && git rebase origin/main
git commit -m "docs(outlook): add CalendarFetcher docstring and param descriptions"

Day 2, 10:00 — Open PR
git push origin feature/outlook-calendar-fetcher
# → Open PR on GitHub with description, checklist completed

Day 2, 14:00 — Review received, address comments
git commit -m "fix(outlook): use $select to avoid fetching full event body"

Day 2, 15:00 — Approved, squash merge
# Squash commit on main: "feat(outlook): add CalendarFetcher (#31)"
# Branch deleted

Day 2, 15:05 — Update roadmap
# Update ROADMAP.md: Phase 4 Calendar Fetcher → In Progress → Done
```

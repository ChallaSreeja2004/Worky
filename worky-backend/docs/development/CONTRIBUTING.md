# Contributing to Worky

> Thank you for contributing to Worky. This document defines the engineering standards, conventions, and processes that all contributors must follow to keep the codebase consistent, reviewable, and maintainable as the team grows.

---

## Table of Contents

1. [Repository Workflow](#1-repository-workflow)
2. [Branch Naming Convention](#2-branch-naming-convention)
3. [Commit Message Convention](#3-commit-message-convention)
4. [Pull Request Process](#4-pull-request-process)
5. [Code Review Expectations](#5-code-review-expectations)
6. [Coding Standards](#6-coding-standards)
7. [Folder and File Naming](#7-folder-and-file-naming)
8. [Documentation Requirements](#8-documentation-requirements)
9. [Testing Requirements](#9-testing-requirements)
10. [Connector Development Rules](#10-connector-development-rules)
11. [Architecture Rules](#11-architecture-rules)
12. [Merge Strategy](#12-merge-strategy)

---

## 1. Repository Workflow

Worky uses a **trunk-based development** workflow with short-lived feature branches.

```
main  (protected — no direct commits)
  └─ feature/outlook-calendar-fetcher   ← your feature branch
  └─ feature/slack-mentions-fetcher     ← teammate's feature branch
  └─ fix/token-refresh-on-401
  └─ docs/update-connector-guide
```

### Rules
- `main` is always deployable. Every commit on `main` must pass all tests and linting.
- No developer commits directly to `main`. All changes go through a pull request.
- Feature branches are short-lived — ideally less than 3 days. Large features are broken into smaller PRs.
- One developer per connector sub-package. Coordinate before touching shared contracts.

---

## 2. Branch Naming Convention

```
<type>/<scope>-<short-description>
```

| Type | Use for |
|---|---|
| `feature/` | New functionality |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `refactor/` | Code changes with no functional difference |
| `test/` | Adding or improving tests only |
| `chore/` | Dependency updates, CI changes, tooling |

### Examples

```bash
feature/outlook-calendar-fetcher
feature/slack-connector-base
feature/context-builder-implementation
fix/token-refresh-race-condition
fix/graph-client-retry-on-429
docs/update-architecture-diagrams
refactor/normalizer-extract-date-helper
test/outlook-connector-partial-failure
chore/upgrade-pydantic-v2.8
```

### Rules
- Use lowercase and hyphens only — no underscores, no spaces, no uppercase
- The scope identifies which module is affected: `outlook`, `slack`, `auth`, `context-builder`, `bob`, `recommendations`
- Keep descriptions concise — under 50 characters total after the prefix

---

## 3. Commit Message Convention

Worky follows the **Conventional Commits** specification.

```
<type>(<scope>): <short description>

[optional body — explains WHY, not what]

[optional footer — references issues, breaking changes]
```

### Types

| Type | Use for |
|---|---|
| `feat` | A new feature or capability |
| `fix` | A bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code restructuring without behavior change |
| `test` | Adding or modifying tests |
| `chore` | Build process, dependency updates, CI |
| `perf` | Performance improvements |

### Scopes

Use the affected module as the scope: `outlook`, `slack`, `auth`, `context-builder`, `bob`, `config`, `shared`.

### Examples

```
feat(outlook): add CalendarFetcher for today's events

Fetches calendar events for the current day using calendarView endpoint.
Runs concurrently with EmailFetcher in the OutlookConnector.

feat(auth): implement token refresh on 401 response

fix(outlook): handle missing attendees field in calendar events

Graph API omits the attendees field when the event has no attendees.
Added .get() with empty list default in OutlookNormalizer.

docs(shared): add import rules to BaseConnector docstring

test(slack): add unit tests for MentionsFetcher partial failure

chore: upgrade httpx to 0.27.0
```

### Rules
- Subject line is imperative mood: "add CalendarFetcher" not "added" or "adding"
- Subject line is under 72 characters
- Body explains *why*, not *what* — the diff shows what changed
- Never include "WIP", "fix stuff", or "misc changes" in a commit message

---

## 4. Pull Request Process

### Before opening a PR
- [ ] All tests pass locally: `pytest tests/`
- [ ] No linting errors: `ruff check app/`
- [ ] No type errors: `mypy app/`
- [ ] New code has corresponding tests
- [ ] New environment variables are documented in `.env.example`
- [ ] Architecture rules are not violated (see [Architecture Rules](#11-architecture-rules))

### PR title format
Follow the same convention as commit messages:
```
feat(outlook): implement CalendarFetcher with today's events
```

### PR description template

```markdown
## Summary
<!-- One paragraph explaining what this PR does and why. -->

## Changes
<!-- Bullet list of specific changes made. -->
- Added `CalendarFetcher` in `app/connectors/outlook/fetchers/calendar.py`
- Added `OutlookCalendarEvent` Pydantic model in `app/connectors/outlook/models.py`
- Added unit tests in `tests/connectors/outlook/test_calendar_fetcher.py`

## Testing
<!-- Describe how you tested these changes. -->
- Unit tests: 12 passing
- Manual test: triggered context collection with a live Graph API token

## Notes for Reviewers
<!-- Anything specific the reviewer should pay attention to. -->

## Related Issues
<!-- Closes #123 -->
```

### PR size guidelines
| PR Size | Lines changed | Expectation |
|---|---|---|
| Small | < 200 | Review within 4 hours |
| Medium | 200–500 | Review within 1 business day |
| Large | > 500 | Split into smaller PRs if possible |

---

## 5. Code Review Expectations

### Reviewer responsibilities
- Review within **1 business day** of being assigned
- Check for architecture rule violations before anything else
- Focus on correctness, clarity, and consistency — not style preferences
- Ask questions rather than give orders: "Could this be simplified to X?" not "Change this to X"
- Approve only when you are confident the code is production-ready

### Author responsibilities
- Respond to all review comments within 1 business day
- Do not merge until all required approvals are received and CI passes
- Do not resolve review threads yourself unless the reviewer requested a minor fix

### What reviewers check
1. **Architecture compliance** — no layer violations, no direct connector-to-Bob calls
2. **Error handling** — `get_context()` never raises, partial failures return `ConnectorResult.partial()`
3. **Concurrency** — fetchers use `asyncio.gather()`, not sequential awaits
4. **Test coverage** — normalizer, fetchers, and connector all have tests
5. **Documentation** — public methods have docstrings, import rules are documented
6. **Environment variables** — new vars are in `.env.example` with a comment

---

## 6. Coding Standards

### Language
Python 3.11+ only. Use modern syntax: `X | Y` union types, `match` statements where appropriate, `datetime.now(timezone.utc)` (never `datetime.utcnow()`).

### Formatting
`ruff format` is the project formatter. Run before every commit:
```bash
ruff format app/ tests/
ruff check app/ tests/ --fix
```

### Type hints
All function signatures must have complete type hints. Return types are required on all public methods.

```python
# CORRECT
async def fetch(self, access_token: str) -> list[dict]:

# WRONG
async def fetch(self, access_token):
```

### Async
All I/O must be async. Never use `requests` — use `httpx` with `async with`. Never block the event loop with synchronous I/O.

### Imports
- Standard library first
- Third-party packages second
- Internal `app.*` imports last
- Separate each group with a blank line

```python
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult
```

### Docstrings
All public classes and methods require docstrings. Use Google-style format:
```python
async def get_context(self, user_id: str, access_token: str) -> ConnectorResult:
    """
    Collect data from the Slack API for the given user.

    Args:
        user_id: The Worky-internal user identifier.
        access_token: A valid Slack OAuth bearer token.

    Returns:
        ConnectorResult with status SUCCESS, PARTIAL, or FAILED.
    """
```

---

## 7. Folder and File Naming

| Item | Convention | Example |
|---|---|---|
| Packages (directories) | `snake_case` | `context_builder/`, `outlook/` |
| Python files | `snake_case.py` | `graph_client.py`, `calendar_fetcher.py` |
| Pydantic models | `PascalCase` | `CalendarEvent`, `OutlookContext` |
| Functions / methods | `snake_case` | `get_context()`, `fetch_calendar_events()` |
| Constants | `UPPER_SNAKE_CASE` | `TOKEN_REFRESH_BUFFER_MINUTES` |
| Connector `source_name` | `lowercase-hyphenated` | `"outlook"`, `"github"` |

---

## 8. Documentation Requirements

### Every new module must have
- A module-level docstring (minimum 3 lines) explaining what the module owns and what it does NOT own
- Import rules documented at the bottom of the module docstring

### Every public class must have
- A class-level docstring explaining its purpose, responsibilities, and what it must NOT do

### Every public method must have
- A method docstring including parameters, return value, and what exceptions it raises

### Architecture-impacting changes must update
- `docs/ARCHITECTURE.md` if a new layer or module is introduced
- `docs/CONNECTOR_GUIDE.md` if the connector pattern changes
- `docs/ROADMAP.md` status updates as phases complete
- `docs/DECISIONS.md` if a new major architectural decision is made

---

## 9. Testing Requirements

### Coverage requirements
| Layer | Minimum Coverage |
|---|---|
| Normalizer | 100% — pure function, no reason for gaps |
| Fetchers | 90% — mock the API client |
| Connector | 85% — cover SUCCESS, PARTIAL, FAILED paths |
| Auth service | 85% |
| Shared contracts | 90% |

### Test file location
Mirror the source structure:
```
app/connectors/outlook/fetchers/calendar.py
→ tests/connectors/outlook/test_calendar_fetcher.py
```

### Test naming
```python
def test_<method>_<scenario>_<expected_outcome>():
    # Examples:
def test_fetch_returns_empty_list_when_no_events():
def test_normalize_handles_missing_attendees_field():
def test_get_context_returns_partial_when_email_fetch_fails():
```

### Fixtures
- Store raw API response fixtures as `.json` files in `tests/connectors/<name>/fixtures/`
- Never make real API calls in tests — use `respx` to mock `httpx`, or inject mock clients

### Running tests
```bash
# All tests
pytest tests/

# Specific connector
pytest tests/connectors/outlook/ -v

# With coverage
pytest tests/ --cov=app --cov-report=term-missing
```

---

## 10. Connector Development Rules

These rules apply to every connector without exception:

1. **One connector per enterprise application.** A single connector package may not integrate two different APIs.
2. **`get_context()` never raises.** All exceptions are caught inside the connector and returned as `ConnectorResult.failed()`.
3. **All HTTP calls live in the API client.** Fetchers, normalizer, and connector classes never call `httpx` directly.
4. **Fetchers never normalize.** They return raw API JSON dictionaries.
5. **The normalizer has no I/O.** It is a pure transformation function.
6. **Run fetchers concurrently** via `asyncio.gather()`.
7. **The `source_name` must be unique and stable.** Never rename after deployment.
8. **Connector-specific settings stay in the connector's own `settings.py`.**
9. **Never import from another connector.** `SlackConnector` must not import from `outlook/`.
10. **No connector imports from `context_builder` or `bob`.**

Detailed guide: [`CONNECTOR_GUIDE.md`](CONNECTOR_GUIDE.md)

---

## 11. Architecture Rules

These rules protect the layered architecture. Violations require a team discussion and an entry in `DECISIONS.md` before being merged.

| Rule | Violation example |
|---|---|
| Connectors must not call IBM Bob | `SlackConnector` calling `BobService.analyze()` |
| Context Builder must not import specific connectors | `ContextBuilder` importing from `outlook/` |
| IBM Bob must receive only `WorkContext` | Passing a raw `CalendarEvent` list to Bob |
| Auth layer must not import from connectors | `AuthService` importing `GraphAPIClient` |
| Domain contracts must not import from outer layers | `ConnectorResult` importing `FastAPI` |
| No new global mutable state | Module-level dict replacing `TokenRepository` |
| New settings must not be added to `AppSettings` | Adding `AZURE_CLIENT_ID` to global settings |

---

## 12. Merge Strategy

### Default: Squash and merge
All feature and fix PRs are squash-merged. This keeps `main` history clean — one logical PR = one commit on `main`.

The squash commit message follows the commit convention:
```
feat(outlook): implement CalendarFetcher (#42)
```

### Exception: preserve history for major milestones
Phase completion PRs (e.g., "Complete Outlook Connector — Phase 7") use a regular merge commit to preserve the full development history of that milestone.

### After merging
- Delete the feature branch immediately
- Update the phase status in `ROADMAP.md`
- Notify the team in the project channel

### Release tagging
```bash
git tag -a v0.1.0 -m "Phase 1: Project Foundation complete"
git tag -a v0.2.0 -m "Phase 7: Outlook Connector complete"
```

See [`GIT_WORKFLOW.md`](GIT_WORKFLOW.md) for the full release process.

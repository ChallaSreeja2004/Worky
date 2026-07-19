# Worky — Changelog

All notable changes to the Worky backend are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions correspond to Git tags on the `main` branch.

---

## [Unreleased] — Phase 5: Email Fetcher

### Added

- `app/connectors/outlook/fetchers/email.py` — `EmailFetcher` class.
  - Accepts `GraphAPIClient` via constructor injection.
  - Calls `GraphAPIClient.get_messages()` — no direct HTTP.
  - Returns `response.get("value", [])` — raw Graph message list, no transformation.
  - Returns `[]` when the inbox is empty or the `value` key is absent.
  - All `GraphError` subclasses (`GraphAuthError`, `GraphRateLimitError`, `GraphServiceError`) propagate to the caller unchanged.
  - Mirrors `CalendarFetcher` exactly — single public `fetch()` method, no filtering, no sorting, no normalization.
- `tests/connectors/outlook/test_email_fetcher.py` — 12 unit tests for `EmailFetcher`.
  - `TestEmailFetcherSuccess` — raw list returned, object identity preserved, client called once, order preserved, envelope not leaked.
  - `TestEmailFetcherEmpty` — `value=[]` returns `[]`, missing `value` key returns `[]`, no exception raised.
  - `TestEmailFetcherErrorPropagation` — `GraphAuthError`, `GraphRateLimitError`, `GraphServiceError` propagate with identity and message intact.
  - `GraphAPIClient` replaced with `AsyncMock` — no real HTTP calls.

### Tests

| Suite | Tests | Status |
|---|---|---|
| `tests/auth/test_service.py` | 31 | ✅ Passing |
| `tests/connectors/outlook/test_graph_client.py` | 46 | ✅ Passing |
| `tests/connectors/outlook/test_calendar_fetcher.py` | 12 | ✅ Passing |
| `tests/connectors/outlook/test_email_fetcher.py` | 12 | ✅ Passing |
| **Total** | **101** | **✅ All passing** |

### Engineering Review

Phase 5 passed engineering review with verdict **APPROVED — no changes required**.

---

## [v0.4.0] — Phase 4: Calendar Fetcher

### Added

- `app/connectors/outlook/fetchers/__init__.py` — Fetchers sub-package for the Outlook connector. Documents the package purpose and phase roadmap for future fetchers (`EmailFetcher` in Phase 5).
- `app/connectors/outlook/fetchers/calendar.py` — `CalendarFetcher` class.
  - Accepts `GraphAPIClient` via constructor injection.
  - Calls `GraphAPIClient.get_calendar_events()` — no direct HTTP.
  - Returns `response.get("value", [])` — raw Graph event list, no transformation.
  - Returns `[]` when the calendar is empty or the `value` key is absent.
  - All `GraphError` subclasses (`GraphAuthError`, `GraphRateLimitError`, `GraphServiceError`) propagate to the caller unchanged.
- `tests/connectors/outlook/test_calendar_fetcher.py` — 12 unit tests for `CalendarFetcher`.
  - `TestCalendarFetcherSuccess` — raw list returned, object identity preserved, client called once, order preserved, envelope not leaked.
  - `TestCalendarFetcherEmpty` — `value=[]` returns `[]`, missing `value` key returns `[]`, no exception raised.
  - `TestCalendarFetcherErrorPropagation` — `GraphAuthError`, `GraphRateLimitError`, `GraphServiceError` propagate with identity and message intact.
  - `GraphAPIClient` replaced with `AsyncMock` — no real HTTP calls.

### Documentation

- `docs/planning/ROADMAP.md` — Phases 2, 3, 4 marked ✅ Complete. Phase 5 marked 🔜 Next. Summary table and last-updated header updated.
- `docs/IMPLEMENTATION_CHECKLIST.md` — Phases 2, 3, 4 all tasks checked. Phase 5 marked as next.
- `docs/README.md` — Current development status table updated. Development roadmap table updated. Repository structure tree updated to reflect actual files.
- `docs/reference/REPOSITORY_STRUCTURE.md` — Complete tree updated: existing files marked ✅, planned files marked 📋. `dependencies.py` added. Future planned files correctly scoped per phase.
- `docs/architecture/ARCHITECTURE.md` — New section added under Connector Architecture: "Outlook Connector — Current Build State (v0.4.0)" showing the `GraphAPIClient → CalendarFetcher → Raw Graph Events` data flow diagram.
- `docs/CHANGELOG.md` — This file created.

### Tests

| Suite | Tests | Status |
|---|---|---|
| `tests/auth/test_service.py` | 31 | ✅ Passing |
| `tests/connectors/outlook/test_graph_client.py` | 46 | ✅ Passing |
| `tests/connectors/outlook/test_calendar_fetcher.py` | 12 | ✅ Passing |
| **Total** | **89** | **✅ All passing** |

### Engineering Review

Phase 4 passed engineering review with verdict **APPROVED — no changes required**.

---

## [v0.3.0] — Phase 3: Microsoft Graph Client

### Added

- `app/connectors/outlook/graph_client.py` — `GraphAPIClient` with:
  - `get_current_user()` — `GET /me?$select=id,displayName,mail,userPrincipalName`
  - `get_calendar_events()` — `GET /me/calendarView` (today UTC, `$select`, `$orderby`, `$top=20`)
  - `get_messages()` — `GET /me/messages` (`$filter` unread/high-importance, `$select`, `$orderby`, `$top=25`)
  - `ping()` — returns `True`/`False`, never raises
  - Exponential back-off retry on 429/503 (max 3 attempts: 1 s → 2 s → raise)
  - Timeout and network errors retried under same policy
  - `AsyncClient` constructed once outside retry loop (connection reuse)
  - `GraphError` exception hierarchy: `GraphAuthError`, `GraphRateLimitError`, `GraphServiceError`
  - `_extract_error_message()` module-level helper
- `tests/connectors/outlook/test_graph_client.py` — 46 unit tests (all passing)
- `pytest.ini` — `asyncio_mode = auto` (required for pytest-asyncio 0.23.7, which defaults to strict mode and skips async tests without this setting)

### Fixed (post-review)

- `AsyncClient` moved outside retry loop — previously recreated on each attempt, defeating TCP keep-alive
- Duplicate `except httpx.TimeoutException` / `except httpx.RequestError` blocks merged into single clause (`TimeoutException` is a subclass of `RequestError`)
- Retry policy docstring corrected — timeout/network exhaustion raises `GraphServiceError`, not `GraphRateLimitError`
- `_extract_error_message` docstring updated to document empty-string fallback behaviour
- Added missing tests: `get_calendar_events` 500, `get_messages` 403, `_extract_error_message` empty-string case

---

## [v0.2.0] — Phase 2: Outlook Authentication

### Added

- `app/connectors/outlook/settings.py` — `OutlookSettings` with `extra="ignore"` (shared `.env` compatibility)
- `app/auth/service.py` — `AuthService` with full PKCE flow: authorization URL generation, code exchange, silent refresh, token revocation, Fernet encryption
- `app/auth/dependencies.py` — `get_token_repository()`, `get_auth_service()` FastAPI DI helpers
- `app/auth/router.py` — `GET /api/v1/auth/login`, `GET /api/v1/auth/callback`, `POST /api/v1/auth/refresh`
- `tests/conftest.py` — shared fixtures (`token_repository`, `encryption_key`)
- `tests/auth/test_service.py` — 31 unit tests (all passing)

### Fixed

- `app/config/settings.py` — `extra="ignore"` added to `AppSettings.model_config` (pydantic-settings 2.3.4 defaults to `extra="forbid"`; connector vars in shared `.env` previously caused `ValidationError` at startup)
- `app/connectors/outlook/settings.py` — same `extra="ignore"` fix applied

---

## [v0.1.0] — Phase 1: Project Foundation

### Added

- `app/config/settings.py` — `AppSettings`
- `app/connectors/base.py` — `BaseConnector` ABC + `ConnectorError` exception hierarchy
- `app/connectors/models.py` — `ConnectorResult`, `ConnectorStatus`
- `app/context_builder/models.py` — `WorkContext`, `ConnectorSummary`
- `app/auth/models.py` — `TokenData`, `AuthorizationResponse`
- `app/auth/repository.py` — `TokenRepository` ABC + `InMemoryTokenRepository`
- `main.py` — FastAPI application with versioned `/api/v1` prefix
- `.env.example` — grouped by settings class with comments
- `.gitignore`
- `docs/` — full engineering handbook (12 documents)

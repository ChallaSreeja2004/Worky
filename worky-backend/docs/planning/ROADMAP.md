# Worky — Implementation Roadmap

> **Last updated:** Phase 1 complete
> **Format:** Each phase has an objective, deliverables, dependencies, implementation details, completion criteria, suggested commit, Git tag, and repository state after completion.
> **Daily tracker:** Use [`../IMPLEMENTATION_CHECKLIST.md`](../IMPLEMENTATION_CHECKLIST.md) to track phase progress and check off tasks.

---

## Summary

| Phase | Name | Owner | Git Tag | Status |
|---|---|---|---|---|
| [Phase 1](#phase-1--project-foundation) | Project Foundation | Team | `v0.1.0` | ✅ Complete |
| [Phase 2](#phase-2--outlook-authentication) | Outlook Authentication | Outlook Dev | `v0.2.0` | 🔄 In Progress |
| [Phase 3](#phase-3--microsoft-graph-client) | Microsoft Graph Client | Outlook Dev | `v0.3.0` | 📋 Planned |
| [Phase 4](#phase-4--calendar-fetcher) | Calendar Fetcher | Outlook Dev | (→ v0.4.0) | 📋 Planned |
| [Phase 5](#phase-5--email-fetcher) | Email Fetcher | Outlook Dev | `v0.4.0` | 📋 Planned |
| [Phase 6](#phase-6--normalizer) | Normalizer | Outlook Dev | (→ v0.5.0) | 📋 Planned |
| [Phase 7](#phase-7--outlook-connector) | Outlook Connector | Outlook Dev | `v0.5.0` | 📋 Planned |
| [Phase 8](#phase-8--slack-connector) | Slack Connector | Slack Dev | `v0.6.0` | 📋 Planned |
| [Phase 9](#phase-9--context-builder) | Context Builder | Team | `v0.7.0` | 📋 Planned |
| [Phase 10](#phase-10--ibm-bob-integration) | IBM Bob Integration | Team | `v0.8.0` | 📋 Planned |
| [Phase 11](#phase-11--recommendation-service) | Recommendation Service | Team | `v0.9.0` | 📋 Planned |
| [Phase 12](#phase-12--desktop-widget-integration) | Desktop Widget Integration | Team | `v0.10.0` | 📋 Planned |
| [Phase 13](#phase-13--production-hardening) | Production Hardening | Team | `v1.0.0` | 📋 Planned |

---

## Phase 1 — Project Foundation

**Status:** ✅ Complete | **Owner:** Team | **Git Tag:** `v0.1.0`

**Suggested Commit:** `feat(shared): establish project foundation and shared contracts`

### Objective
Establish the shared engineering foundation that all connectors and services will build upon. Define all shared contracts before any connector-specific code is written.

### Deliverables

| Deliverable | File | Status |
|---|---|---|
| Project directory structure | `worky-backend/` | ✅ |
| Global application settings | `app/config/settings.py` | ✅ |
| `BaseConnector` abstract interface | `app/connectors/base.py` | ✅ |
| Connector exception hierarchy | `app/connectors/base.py` | ✅ |
| `ConnectorResult` model | `app/connectors/models.py` | ✅ |
| `ConnectorStatus` enum | `app/connectors/models.py` | ✅ |
| `WorkContext` model | `app/context_builder/models.py` | ✅ |
| `ConnectorSummary` model | `app/context_builder/models.py` | ✅ |
| `TokenData` model | `app/auth/models.py` | ✅ |
| `TokenRepository` interface | `app/auth/repository.py` | ✅ |
| `InMemoryTokenRepository` | `app/auth/repository.py` | ✅ |
| FastAPI application entry point | `main.py` | ✅ |
| Environment variable template | `.env.example` | ✅ |
| Full engineering documentation | `docs/` | ✅ |

### Dependencies
None — this is the foundational phase.

### Repository State After Completion
Any developer can clone the repository, run `pytest tests/` successfully, start the server with `uvicorn main:app --reload`, and begin implementing a connector by following `docs/development/CONNECTOR_GUIDE.md` — without any additional explanation.

### Completion Criteria
- All shared contracts import cleanly
- `pytest tests/` passes with zero failures
- `python scripts/check_env.py` passes
- `uvicorn main:app --reload` starts without errors
- `GET /health` returns `{"status": "ok"}`

---

## Phase 2 — Outlook Authentication

**Status:** 🔄 In Progress | **Owner:** Outlook Developer | **Git Tag:** `v0.2.0`

**Suggested Commit:** `feat(auth): implement Microsoft OAuth 2.0 PKCE flow`

### Objective
Implement the Microsoft OAuth 2.0 + PKCE authentication flow that the Outlook connector requires to obtain delegated access tokens for the authenticated user.

### Deliverables

| Deliverable | File |
|---|---|
| `OutlookSettings` — Azure app config | `app/connectors/outlook/settings.py` |
| `AuthService` — PKCE flow orchestration | `app/auth/service.py` |
| Auth router — login, callback, logout | `app/auth/router.py` |
| Unit tests — token exchange | `tests/auth/test_service.py` |
| Unit tests — token refresh | `tests/auth/test_service.py` |
| Unit tests — `InMemoryTokenRepository` | `tests/auth/test_repository.py` |

### Implementation Details

- Generate `code_verifier` + `code_challenge` (PKCE, S256 method)
- Build Microsoft authorization URL with required scopes: `User.Read Calendars.Read Mail.Read offline_access`
- Exchange authorization code + code_verifier for `access_token` + `refresh_token`
- Encrypt `refresh_token` with Fernet before storing via `TokenRepository`
- Implement silent token refresh: check `token_data.is_expired` before every Graph call
- Mount auth router at `/api/v1/auth`

### Dependencies
Phase 1 — `TokenData`, `TokenRepository`, `AppSettings`

### Repository State After Completion
`GET /api/v1/auth/login` returns a valid Microsoft login URL. Completing the login flow stores a token in `InMemoryTokenRepository`. The auth test suite passes completely.

### Completion Criteria
- `GET /api/v1/auth/login` → valid Microsoft authorization URL
- `GET /api/v1/auth/callback?code=...` → `AuthorizationResponse`
- Silent token refresh verified in tests
- All `tests/auth/` tests pass

---

## Phase 3 — Microsoft Graph Client

**Status:** 📋 Planned | **Owner:** Outlook Developer | **Git Tag:** `v0.3.0`

**Suggested Commit:** `feat(outlook): implement GraphAPIClient with retry logic`

### Objective
Implement the `GraphAPIClient` — the single file responsible for all raw HTTP calls to the Microsoft Graph API.

### Deliverables

| Deliverable | File |
|---|---|
| `GraphAPIClient` | `app/connectors/outlook/graph_client.py` |
| `get_current_user()` method | |
| `get_calendar_events()` method | |
| `get_messages()` method | |
| Exponential backoff retry (429, 503) | |
| `ping()` method for health checks | |
| Unit tests with `respx` mocking | `tests/connectors/outlook/test_graph_client.py` |

### Implementation Details

- Base URL: `https://graph.microsoft.com/v1.0`
- All methods accept `access_token` as a parameter
- Retry logic: max 3 attempts, exponential backoff (1s, 2s, 4s)
- `$select` parameters on every call — never fetch full bodies
- `$top` limits to prevent unexpectedly large responses

### Dependencies
Phase 2 — `OutlookSettings`

### Repository State After Completion
A fully tested HTTP client that fetchers can accept as a constructor parameter, enabling fetchers to be tested with a mock client (no real API calls needed in tests).

### Completion Criteria
- All `GraphAPIClient` methods pass tests with `respx` mocking
- Retry logic verified against simulated 429 response
- `ping()` returns `True` on 200 and `False` on error

---

## Phase 4 — Calendar Fetcher

**Status:** 📋 Planned | **Owner:** Outlook Developer | **Git Tag:** (bundled into v0.4.0)

**Suggested Commit:** `feat(outlook): add CalendarFetcher for today's events`

### Objective
Implement `CalendarFetcher` — fetches today's calendar events from Microsoft Graph.

### Deliverables

| Deliverable | File |
|---|---|
| `CalendarFetcher` | `app/connectors/outlook/fetchers/calendar.py` |
| Unit tests — standard events | `tests/connectors/outlook/test_calendar_fetcher.py` |
| Unit tests — empty calendar | |
| Unit tests — API error handling | |
| Fixture: sample Graph calendar response | `tests/connectors/outlook/fixtures/calendar_events.json` |

### Implementation Details

- Fetch events for current day using `calendarView` endpoint
- `$select=subject,start,end,location,organizer,attendees,isOnlineMeeting,onlineMeeting,bodyPreview`
- `$orderby=start/dateTime asc`, `$top=20`
- Return raw list of event dictionaries

### Dependencies
Phase 3 — `GraphAPIClient`

### Repository State After Completion
`CalendarFetcher` returns raw event dicts. Empty calendar returns `[]`. All tests pass with a mock `GraphAPIClient`.

### Completion Criteria
- `test_fetch_returns_events_list()` passes
- `test_fetch_returns_empty_list_when_no_events()` passes
- No real HTTP calls in tests

---

## Phase 5 — Email Fetcher

**Status:** 📋 Planned | **Owner:** Outlook Developer | **Git Tag:** `v0.4.0`

**Suggested Commit:** `feat(outlook): add EmailFetcher for unread and high-importance messages`

### Objective
Implement `EmailFetcher` — fetches unread emails and high-importance emails from Microsoft Graph.

### Deliverables

| Deliverable | File |
|---|---|
| `EmailFetcher` | `app/connectors/outlook/fetchers/email.py` |
| Unit tests — unread emails | `tests/connectors/outlook/test_email_fetcher.py` |
| Unit tests — high-importance filter | |
| Unit tests — empty inbox | |
| Fixture: sample Graph messages response | `tests/connectors/outlook/fixtures/messages.json` |

### Implementation Details

- Fetch unread messages: `$filter=isRead eq false`
- Fetch high-importance messages: `$filter=importance eq 'high'`
- `$select=subject,from,receivedDateTime,importance,bodyPreview,isRead,hasAttachments`
- `$orderby=receivedDateTime desc`, `$top=25`
- Return two separate raw lists

### Dependencies
Phase 3 — `GraphAPIClient`

### Repository State After Completion
`EmailFetcher` returns separate unread and high-importance message lists. All tests pass with a mock `GraphAPIClient`.

### Completion Criteria
- Unread filter verified in tests
- High-importance filter verified in tests
- Empty inbox returns `[]` without error

---

## Phase 6 — Normalizer

**Status:** 📋 Planned | **Owner:** Outlook Developer | **Git Tag:** (bundled into v0.5.0)

**Suggested Commit:** `feat(outlook): implement OutlookNormalizer and domain models`

### Objective
Implement `OutlookNormalizer` and all connector-specific Pydantic models — the translation layer between raw Microsoft Graph JSON and Worky's internal schema.

### Deliverables

| Deliverable | File |
|---|---|
| `CalendarEvent` model | `app/connectors/outlook/models.py` |
| `Email` model | `app/connectors/outlook/models.py` |
| `OutlookUser` model | `app/connectors/outlook/models.py` |
| `OutlookContext` model | `app/connectors/outlook/models.py` |
| `OutlookNormalizer` | `app/connectors/outlook/normalizer.py` |
| Unit tests (100% coverage required) | `tests/connectors/outlook/test_normalizer.py` |

### Implementation Details

- Handle missing optional fields gracefully (`.get()` with defaults)
- Parse Microsoft's non-standard datetime format: `"2025-07-10T09:00:00.0000000"`
- Detect online meetings via `isOnlineMeeting` flag
- Separate high-importance emails from general unread in `OutlookContext`

### Dependencies
Phase 4 (calendar fixture data), Phase 5 (email fixture data)

### Repository State After Completion
`OutlookNormalizer` achieves 100% test coverage. Pure function — no I/O. All edge cases (missing attendees, online meeting detection, empty fields) handled.

### Completion Criteria
- `pytest tests/connectors/outlook/test_normalizer.py --cov=app/connectors/outlook/normalizer` → 100%
- No I/O in normalizer (verified by code review)

---

## Phase 7 — Outlook Connector

**Status:** 📋 Planned | **Owner:** Outlook Developer | **Git Tag:** `v0.5.0`

**Suggested Commit:** `feat(outlook): complete OutlookConnector integrating all layers`

### Objective
Assemble all Outlook components into a single `OutlookConnector(BaseConnector)` and integrate it into the FastAPI application.

### Deliverables

| Deliverable | File |
|---|---|
| `OutlookConnector` | `app/connectors/outlook/connector.py` |
| Outlook debug router | `app/connectors/outlook/router.py` |
| Register `OutlookConnector` in `main.py` | `main.py` |
| Integration test — full context collection | `tests/connectors/outlook/test_connector.py` |
| Integration test — partial failure (email fails) | |
| Integration test — total failure (auth error) | |

### Implementation Details

- Fetch calendar events and emails concurrently via `asyncio.gather(return_exceptions=True)`
- Return `ConnectorResult.partial()` if one fetcher fails
- Return `ConnectorResult.failed()` if both fetchers fail
- `health_check()` calls `graph_client.ping()`

### Dependencies
Phases 2–6 complete

### Repository State After Completion
`GET /api/v1/connectors/outlook/context` returns a valid `ConnectorResult` with today's calendar events and unread emails. `source_name == "outlook"`. Partial and total failure paths verified.

### Completion Criteria
- `pytest tests/connectors/outlook/` at 85%+ coverage
- SUCCESS, PARTIAL, and FAILED scenarios all pass
- `health_check()` returns `False` (not raises) on connection error
- `OutlookConnector` registered in `main.py`

---

## Phase 8 — Slack Connector

**Status:** 📋 Planned | **Owner:** Slack Developer | **Git Tag:** `v0.6.0`

**Suggested Commit:** `feat(slack): implement complete SlackConnector`

### Objective
Implement the complete Slack connector following the same pattern established by the Outlook connector. Reference: [`../templates/CONNECTOR_TEMPLATE.md`](../templates/CONNECTOR_TEMPLATE.md).

### Deliverables

| Deliverable | File |
|---|---|
| `SlackSettings` | `app/connectors/slack/settings.py` |
| `SlackAPIClient` | `app/connectors/slack/slack_client.py` |
| `MessagesFetcher` | `app/connectors/slack/fetchers/messages.py` |
| `MentionsFetcher` | `app/connectors/slack/fetchers/mentions.py` |
| `SlackContext`, `SlackMessage` models | `app/connectors/slack/models.py` |
| `SlackNormalizer` | `app/connectors/slack/normalizer.py` |
| `SlackConnector` | `app/connectors/slack/connector.py` |
| Full test suite | `tests/connectors/slack/` |

### Dependencies
Phase 1 (shared contracts); Phase 7 (Outlook connector as reference)

### Repository State After Completion
`SlackConnector` registered alongside `OutlookConnector` in `main.py`. `source_name == "slack"`. Full test suite passes. No imports from `outlook/`.

### Completion Criteria
- All connector tests pass at 85%+ coverage
- Connector follows `CONNECTOR_TEMPLATE.md` structure exactly
- `source_name` is unique and stable

---

## Phase 9 — Context Builder

**Status:** 📋 Planned | **Owner:** Team | **Git Tag:** `v0.7.0`

**Suggested Commit:** `feat(context-builder): implement ContextBuilder with concurrent connector aggregation`

### Objective
Implement `ContextBuilder` — the aggregation layer that runs all registered connectors concurrently and assembles results into a single `WorkContext`.

### Deliverables

| Deliverable | File |
|---|---|
| `ContextBuilder` | `app/context_builder/builder.py` |
| Connector DI registry | `main.py` |
| Unit test — all connectors succeed | `tests/context_builder/test_builder.py` |
| Unit test — one connector fails | |
| Unit test — all connectors fail | |
| Unit test — partial results included | |

### Implementation Details

- Accept `list[BaseConnector]` via constructor injection
- Run all connectors via `asyncio.gather(return_exceptions=False)`
- Call `WorkContext.from_connector_results()` to assemble
- Log assembly duration as metadata

### Dependencies
Phase 7 (Outlook), Phase 8 (Slack)

### Repository State After Completion
`ContextBuilder` with `[MockOutlookConnector(), MockSlackConnector()]` returns a `WorkContext` where `active_sources == ["outlook", "slack"]`. Adding a third connector requires zero changes to `ContextBuilder`.

### Completion Criteria
- `test_build_returns_workcontext_with_all_sources()` passes
- `test_build_excludes_failed_connector_from_sources()` passes
- Confirmed: adding a new connector to the list requires no other code changes

---

## Phase 10 — IBM Bob Integration

**Status:** 📋 Planned | **Owner:** Team | **Git Tag:** `v0.8.0`

**Suggested Commit:** `feat(bob): define BobService interface and implement MockBobService`

### Objective
Define the `BobService` interface and implement the IBM Bob API client. Include a `MockBobService` for development and testing.

### Deliverables

| Deliverable | File |
|---|---|
| `BobRequest`, `RecommendationSet`, `Recommendation` models | `app/bob/models.py` |
| `BobService` abstract interface | `app/bob/service.py` |
| `IBMBobService` concrete implementation | `app/bob/service.py` |
| `MockBobService` | `app/bob/mock_service.py` |
| Unit tests — mock service | `tests/bob/test_mock_service.py` |

### Implementation Details

- `BobService.analyze(work_context: WorkContext) → RecommendationSet`
- `IBMBobService` constructs the prompt from `WorkContext` and calls IBM Bob's API
- `MockBobService` returns deterministic hardcoded recommendations (no API call)
- DI configuration: inject `MockBobService` when `APP_ENV=development`

### Dependencies
Phase 9 — `WorkContext` is fully populated

### Repository State After Completion
The entire system works end-to-end using `MockBobService` without real IBM Bob credentials. Switching to `IBMBobService` is a single DI configuration change.

### Completion Criteria
- `MockBobService.analyze(work_context)` returns a valid `RecommendationSet`
- Switching to `IBMBobService` requires no code changes outside `main.py` DI config
- All `tests/bob/` tests pass

---

## Phase 11 — Recommendation Service

**Status:** 📋 Planned | **Owner:** Team | **Git Tag:** `v0.9.0`

**Suggested Commit:** `feat(recommendations): implement widget-facing API and scheduler`

### Objective
Implement the widget-facing API and the scheduled background task that drives the full pipeline.

### Deliverables

| Deliverable | File |
|---|---|
| `RecommendationResponse` model | `app/recommendations/models.py` |
| `GET /api/v1/recommendations` endpoint | `app/recommendations/router.py` |
| Scheduled background task (every 5 min) | `app/recommendations/scheduler.py` |
| Recommendation cache | `app/recommendations/cache.py` |

### Implementation Details

- Background task: `AuthService → ContextBuilder → BobService → cache.store()`
- Widget endpoint: `cache.get(user_id)` — always instant, no on-demand Bob calls
- Cache TTL: 5 minutes (matches scheduler interval)

### Dependencies
Phase 10 — `BobService` returns `RecommendationSet`

### Repository State After Completion
Desktop Widget can call `GET /api/v1/recommendations` and receive a populated `RecommendationResponse` from cache. Scheduler runs automatically on startup.

### Completion Criteria
- `GET /api/v1/recommendations` returns `RecommendationResponse` with populated recommendations
- Scheduler verified to fire every 5 minutes
- Cache TTL synchronized with scheduler interval

---

## Phase 12 — Desktop Widget Integration

**Status:** 📋 Planned | **Owner:** Team | **Git Tag:** `v0.10.0`

**Suggested Commit:** `feat(widget): connect Electron widget to recommendations endpoint`

### Objective
Connect the Electron + React Desktop Widget to the Worky backend recommendation endpoint.

### Deliverables
- Electron main process with backend HTTP client
- React widget component consuming `RecommendationResponse`
- Login flow triggering the OAuth redirect in system browser
- Auto-refresh of recommendations every 60 seconds
- System tray integration

### Dependencies
Phase 11 — Recommendations endpoint is live

### Repository State After Completion
Desktop application launches, user logs in via OAuth, widget displays AI-generated recommendations, recommendations auto-refresh every 60 seconds.

### Completion Criteria
- User can complete OAuth login flow from the desktop app
- Widget displays `recommendations` array from `RecommendationResponse`
- Widget auto-refreshes without user action

---

## Phase 13 — Production Hardening

**Status:** 📋 Planned | **Owner:** Team | **Git Tag:** `v1.0.0`

**Suggested Commit:** `chore(infra): production-ready configuration with Redis, Docker, and CI`

### Objective
Prepare the backend for a production deployment with multiple workers, real token persistence, observability, and rate-limit resilience.

### Deliverables

| Deliverable | Description |
|---|---|
| `RedisTokenRepository` | Replace `InMemoryTokenRepository` in production |
| Redis recommendation cache | Replace in-memory cache |
| Structured logging with `request_id` | Correlation ID flows through every layer |
| API rate limit handling | Respect `Retry-After` headers from Graph + Slack |
| `GET /api/v1/health/detailed` | Checks Redis, upstream API reachability |
| `Dockerfile` + `docker-compose.yml` | Reproducible local and staging environment |
| CI pipeline | Lint (`ruff`), typecheck (`mypy`), tests (`pytest`) on every PR |
| Environment-based DI switching | `InMemoryTokenRepository` in dev, `RedisTokenRepository` in prod |

### Dependencies
Phases 1–12 complete

### Repository State After Completion
Backend deployable with `docker-compose up`. CI passes on every PR. `InMemoryTokenRepository` automatically swapped for `RedisTokenRepository` when `APP_ENV=production`.

### Completion Criteria
- `docker-compose up` starts all services without errors
- CI pipeline passes: lint, typecheck, tests all green
- `GET /api/v1/health/detailed` reports all dependencies healthy
- `APP_ENV=production` injects `RedisTokenRepository` via DI

---

## Related Documents

| Document | Purpose |
|---|---|
| [`../IMPLEMENTATION_CHECKLIST.md`](../IMPLEMENTATION_CHECKLIST.md) | Phase-by-phase task tracker with checkboxes |
| [`../TEAM_RULES.md`](../TEAM_RULES.md) | Non-negotiable engineering rules |
| [`../development/CONTRIBUTING.md`](../development/CONTRIBUTING.md) | Engineering standards, PR process |
| [`../development/GIT_WORKFLOW.md`](../development/GIT_WORKFLOW.md) | Branch strategy, commits, versioning |

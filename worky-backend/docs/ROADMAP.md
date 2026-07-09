# Worky — Implementation Roadmap

> **Last updated:** Phase 1 complete
> **Format:** Each phase has a clear objective, concrete deliverables, dependencies, expected output, and current status.

---

## Summary

| Phase | Name | Status |
|---|---|---|
| [Phase 1](#phase-1--project-foundation) | Project Foundation | ✅ Complete |
| [Phase 2](#phase-2--outlook-authentication) | Outlook Authentication | 🔄 In Progress |
| [Phase 3](#phase-3--microsoft-graph-client) | Microsoft Graph Client | 📋 Planned |
| [Phase 4](#phase-4--calendar-fetcher) | Calendar Fetcher | 📋 Planned |
| [Phase 5](#phase-5--email-fetcher) | Email Fetcher | 📋 Planned |
| [Phase 6](#phase-6--normalizer) | Normalizer | 📋 Planned |
| [Phase 7](#phase-7--outlook-connector) | Outlook Connector | 📋 Planned |
| [Phase 8](#phase-8--slack-connector) | Slack Connector | 📋 Planned |
| [Phase 9](#phase-9--context-builder) | Context Builder | 📋 Planned |
| [Phase 10](#phase-10--ibm-bob-integration) | IBM Bob Integration | 📋 Planned |
| [Phase 11](#phase-11--recommendation-service) | Recommendation Service | 📋 Planned |
| [Phase 12](#phase-12--desktop-widget-integration) | Desktop Widget Integration | 📋 Planned |
| [Phase 13](#phase-13--production-hardening) | Production Hardening | 📋 Planned |

---

## Phase 1 — Project Foundation

**Status:** ✅ Complete

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
| Full repository documentation | `docs/` | ✅ |

### Dependencies
None — this is the foundational phase.

### Expected Output
A repository that any developer can clone, read the documentation, understand the architecture, and begin implementing a connector following `CONNECTOR_GUIDE.md` — without any additional explanation.

---

## Phase 2 — Outlook Authentication

**Status:** 🔄 In Progress

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

### Expected Output
A working OAuth flow: visiting `/api/v1/auth/login` redirects to Microsoft, and completing login returns a valid access token stored in `InMemoryTokenRepository`.

---

## Phase 3 — Microsoft Graph Client

**Status:** 📋 Planned

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
| Unit tests with `respx` mocking | `tests/connectors/outlook/test_graph_client.py` |

### Implementation Details

- Base URL: `https://graph.microsoft.com/v1.0`
- All methods accept `access_token` as a parameter
- Retry logic: max 3 attempts, exponential backoff (1s, 2s, 4s)
- `$select` parameters on every call — never fetch full bodies
- `$top` limits to prevent unexpectedly large responses
- `ping()` method for health checks

### Dependencies
Phase 2 — `OutlookSettings`

### Expected Output
A fully tested HTTP client that can be passed to fetchers as a constructor dependency, enabling fetchers to be tested with a mock client.

---

## Phase 4 — Calendar Fetcher

**Status:** 📋 Planned

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
- Query params: `startDateTime`, `endDateTime`, `$select=subject,start,end,location,organizer,attendees,isOnlineMeeting,onlineMeeting,bodyPreview`, `$orderby=start/dateTime asc`, `$top=20`
- Return raw list of event dictionaries

### Dependencies
Phase 3 — `GraphAPIClient`

### Expected Output
A fetcher that returns raw calendar event dictionaries that the Normalizer (Phase 6) will transform into typed models.

---

## Phase 5 — Email Fetcher

**Status:** 📋 Planned

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

### Expected Output
A fetcher returning unread and high-importance email dictionaries ready for normalization.

---

## Phase 6 — Normalizer

**Status:** 📋 Planned

### Objective
Implement the `OutlookNormalizer` and all connector-specific Pydantic models — the translation layer between raw Microsoft Graph JSON and Worky's internal schema.

### Deliverables

| Deliverable | File |
|---|---|
| `CalendarEvent` model | `app/connectors/outlook/models.py` |
| `Email` model | `app/connectors/outlook/models.py` |
| `OutlookUser` model | `app/connectors/outlook/models.py` |
| `OutlookContext` model | `app/connectors/outlook/models.py` |
| `OutlookNormalizer` | `app/connectors/outlook/normalizer.py` |
| Unit tests — standard event normalization | `tests/connectors/outlook/test_normalizer.py` |
| Unit tests — missing optional fields | |
| Unit tests — online meeting detection | |

### Implementation Details

- Handle missing optional fields gracefully (`.get()` with defaults)
- Parse Microsoft's non-standard datetime format: `"dateTime": "2025-07-10T09:00:00.0000000"`
- Detect online meetings via `isOnlineMeeting` flag
- Separate high-importance emails from general unread emails in `OutlookContext`

### Dependencies
Phase 4 — Calendar fixture data; Phase 5 — Email fixture data

### Expected Output
A pure, fully-tested normalizer. Given any valid Graph API JSON fixture, it produces a fully typed `OutlookContext` Pydantic model.

---

## Phase 7 — Outlook Connector

**Status:** 📋 Planned

### Objective
Assemble all Outlook components into a single `OutlookConnector(BaseConnector)` and integrate it into the FastAPI application.

### Deliverables

| Deliverable | File |
|---|---|
| `OutlookConnector` | `app/connectors/outlook/connector.py` |
| Outlook debug router | `app/connectors/outlook/router.py` |
| Register connector in `main.py` | `main.py` |
| Integration test — full context collection | `tests/connectors/outlook/test_connector.py` |
| Integration test — partial failure (email fails) | |
| Integration test — total failure (auth error) | |

### Implementation Details

- Fetch calendar events and emails concurrently via `asyncio.gather()`
- Use `return_exceptions=True` to handle partial failures without crashing
- Return `ConnectorResult.partial()` if one fetcher fails
- Return `ConnectorResult.failed()` if both fetchers fail
- `health_check()` calls `graph_client.ping()` — a lightweight `/me` request

### Dependencies
Phases 2–6 complete

### Expected Output
A fully working Outlook connector. `GET /api/v1/connectors/outlook/context` returns a `ConnectorResult` with today's calendar events and unread emails.

---

## Phase 8 — Slack Connector

**Status:** 📋 Planned

**Owner:** Slack connector developer

### Objective
Implement the complete Slack connector following the same pattern established by the Outlook connector.

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
Phase 1 — Shared contracts; Phase 7 — Outlook connector as a reference implementation

### Expected Output
A Slack connector that follows `BaseConnector` and can be registered alongside the Outlook connector in the DI container.

---

## Phase 9 — Context Builder

**Status:** 📋 Planned

### Objective
Implement `ContextBuilder` — the aggregation layer that runs all registered connectors concurrently and assembles their results into a single `WorkContext`.

### Deliverables

| Deliverable | File |
|---|---|
| `ContextBuilder` | `app/context_builder/builder.py` |
| Connector DI registry | `main.py` |
| Unit test — all connectors succeed | `tests/context_builder/test_builder.py` |
| Unit test — one connector fails | |
| Unit test — all connectors fail | |
| Unit test — partial results are included | |

### Implementation Details

- Accept `list[BaseConnector]` via constructor injection
- Run all connectors via `asyncio.gather(return_exceptions=False)` — connectors handle their own exceptions
- Call `WorkContext.from_connector_results()` to assemble the payload
- Log assembly duration as metadata

### Dependencies
Phase 7 (Outlook), Phase 8 (Slack)

### Expected Output
A `ContextBuilder` that aggregates any number of connectors into a single `WorkContext`. Adding a third connector requires zero changes to `ContextBuilder`.

---

## Phase 10 — IBM Bob Integration

**Status:** 📋 Planned

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

### Expected Output
A swappable Bob integration. The entire system works end-to-end using `MockBobService` before IBM Bob credentials are available.

---

## Phase 11 — Recommendation Service

**Status:** 📋 Planned

### Objective
Implement the widget-facing API and the scheduled background task that drives the full pipeline.

### Deliverables

| Deliverable | File |
|---|---|
| `RecommendationResponse` model | `app/recommendations/models.py` |
| `GET /api/v1/recommendations` endpoint | `app/recommendations/router.py` |
| Scheduled background task (every 5 min) | `app/recommendations/scheduler.py` |
| Recommendation cache (Redis or in-memory) | `app/recommendations/cache.py` |

### Implementation Details

- Background task: `AuthService → ContextBuilder → BobService → cache.store()`
- Widget endpoint: `cache.get(user_id)` — always instant, no on-demand Bob calls
- Cache TTL: 5 minutes (matches scheduler interval)

### Dependencies
Phase 10 — `BobService` returns `RecommendationSet`

### Expected Output
A working widget API. The desktop widget can call `GET /api/v1/recommendations` and receive fresh, AI-generated recommendations.

---

## Phase 12 — Desktop Widget Integration

**Status:** 📋 Planned

### Objective
Connect the Electron + React desktop widget to the Worky backend recommendation endpoint.

### Deliverables
- Electron main process with backend HTTP client
- React widget component consuming `RecommendationResponse`
- Login flow triggering the OAuth redirect
- Auto-refresh of recommendations every 60 seconds

### Dependencies
Phase 11 — Recommendations endpoint is live

### Expected Output
A working desktop application: user logs in, widget appears, recommendations update automatically.

---

## Phase 13 — Production Hardening

**Status:** 📋 Planned

### Objective
Prepare the backend for a production deployment with multiple workers, real token persistence, observability, and rate-limit resilience.

### Deliverables

| Deliverable | Description |
|---|---|
| `RedisTokenRepository` | Replace `InMemoryTokenRepository` in production |
| Redis recommendation cache | Replace in-memory cache |
| Structured logging with `request_id` | Correlation ID flows through every layer |
| API rate limit handling | Respect `Retry-After` headers from Graph + Slack |
| Health check endpoint (`/api/v1/health/detailed`) | Checks Redis, upstream API reachability |
| Docker + docker-compose | Reproducible local and staging environment |
| CI pipeline | Lint, type-check, test on every PR |
| Environment-based DI switching | `InMemoryTokenRepository` in dev, `RedisTokenRepository` in prod |

### Dependencies
Phases 1–12 complete

### Expected Output
A production-ready backend deployable behind a load balancer with multiple uvicorn workers, Redis-backed state, and full observability.

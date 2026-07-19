# Worky — Repository Structure

> **Purpose:** Define and explain every directory and file in the Worky backend repository. Any developer joining the project should be able to read this document and know exactly where to find or create any piece of code.

---

## Table of Contents

1. [Root Level](#1-root-level)
2. [app/](#2-app)
3. [app/config/](#3-appconfig)
4. [app/auth/](#4-appauth)
5. [app/connectors/](#5-appconnectors)
6. [app/connectors/outlook/](#6-appconnectorsoutlook)
7. [app/context_builder/](#7-appcontext_builder)
8. [app/bob/](#8-appbob)
9. [app/recommendations/](#9-apprecommendations)
10. [tests/](#10-tests)
11. [docs/](#11-docs)
12. [scripts/](#12-scripts)

---

## Complete Tree

Files marked **✅** exist today. Files marked **📋** are planned for future phases.

```
worky-backend/
│
├── main.py                                    ✅
├── requirements.txt                           ✅
├── pytest.ini                                 ✅
├── .env.example                               ✅
├── .gitignore                                 ✅
│
├── app/
│   ├── __init__.py                            ✅
│   │
│   ├── config/
│   │   ├── __init__.py                        ✅
│   │   └── settings.py                        ✅ AppSettings
│   │
│   ├── auth/
│   │   ├── __init__.py                        ✅
│   │   ├── models.py                          ✅ TokenData, AuthorizationResponse
│   │   ├── repository.py                      ✅ TokenRepository + InMemoryTokenRepository
│   │   ├── dependencies.py                    ✅ FastAPI DI helpers
│   │   ├── service.py                         ✅ AuthService — PKCE flow (Phase 2)
│   │   └── router.py                          ✅ /api/v1/auth/* endpoints (Phase 2)
│   │
│   ├── connectors/
│   │   ├── __init__.py                        ✅
│   │   ├── base.py                            ✅ BaseConnector ABC + exception hierarchy
│   │   ├── models.py                          ✅ ConnectorResult, ConnectorStatus
│   │   │
│   │   ├── outlook/
│   │   │   ├── __init__.py                    ✅
│   │   │   ├── settings.py                    ✅ OutlookSettings (Phase 2)
│   │   │   ├── graph_client.py                ✅ GraphAPIClient (Phase 3)
│   │   │   ├── fetchers/
│   │   │   │   ├── __init__.py                ✅ (Phase 4)
│   │   │   │   ├── calendar.py                ✅ CalendarFetcher (Phase 4)
│   │   │   │   └── email.py                   📋 EmailFetcher (Phase 5)
│   │   │   ├── normalizer.py                  📋 OutlookNormalizer (Phase 6)
│   │   │   ├── models.py                      📋 CalendarEvent, Email, OutlookContext (Phase 6)
│   │   │   ├── connector.py                   📋 OutlookConnector(BaseConnector) (Phase 7)
│   │   │   └── router.py                      📋 Debug endpoint (Phase 7)
│   │   │
│   │   └── slack/                             📋 SlackConnector (Phase 8)
│   │       ├── __init__.py
│   │       ├── settings.py
│   │       ├── connector.py
│   │       ├── slack_client.py
│   │       ├── normalizer.py
│   │       ├── models.py
│   │       ├── router.py
│   │       └── fetchers/
│   │           ├── __init__.py
│   │           ├── messages.py
│   │           └── mentions.py
│   │
│   ├── context_builder/
│   │   ├── __init__.py                        ✅
│   │   ├── models.py                          ✅ WorkContext, ConnectorSummary
│   │   └── builder.py                         📋 ContextBuilder (Phase 9)
│   │
│   ├── bob/                                   📋 Phase 10
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── service.py
│   │   └── mock_service.py
│   │
│   └── recommendations/                       📋 Phase 11
│       ├── __init__.py
│       ├── models.py
│       ├── router.py
│       ├── scheduler.py
│       └── cache.py
│
├── tests/
│   ├── __init__.py                            ✅
│   ├── conftest.py                            ✅ Shared fixtures
│   │
│   ├── auth/
│   │   ├── __init__.py                        ✅
│   │   └── test_service.py                    ✅ 31 tests (Phase 2)
│   │
│   └── connectors/
│       ├── __init__.py                        ✅
│       └── outlook/
│           ├── __init__.py                    ✅
│           ├── test_graph_client.py           ✅ 46 tests (Phase 3)
│           ├── test_calendar_fetcher.py       ✅ 12 tests (Phase 4)
│           ├── test_email_fetcher.py          📋 Phase 5
│           ├── test_normalizer.py             📋 Phase 6
│           └── test_connector.py             📋 Phase 7
│
├── docs/
│   ├── README.md                              ✅
│   ├── IMPLEMENTATION_CHECKLIST.md            ✅
│   ├── CHANGELOG.md                           ✅
│   ├── TEAM_RULES.md                          ✅
│   ├── architecture/
│   │   ├── ARCHITECTURE.md                    ✅
│   │   └── DECISIONS.md                       ✅
│   ├── development/
│   │   ├── CONNECTOR_GUIDE.md                 ✅
│   │   ├── CONTRIBUTING.md                    ✅
│   │   └── GIT_WORKFLOW.md                    ✅
│   ├── planning/
│   │   ├── ROADMAP.md                         ✅
│   │   └── TEAM_WORKFLOW.md                   ✅
│   ├── reference/
│   │   └── REPOSITORY_STRUCTURE.md            ✅
│   └── templates/
│       └── CONNECTOR_TEMPLATE.md              ✅
│
└── scripts/
    ├── generate_key.py
    └── check_env.py
```

---

## 1. Root Level

### `main.py`
The FastAPI application entry point. Responsibilities:
- Configure logging
- Instantiate the `FastAPI` app with versioned prefix and middleware
- Mount all routers (auth, connectors, recommendations)
- Wire the DI container (inject `TokenRepository`, `BobService`, connector list)

**Rule:** `main.py` is the only file that imports from multiple `app/` sub-packages simultaneously. All other files import only from their own layer or layers below them.

### `requirements.txt`
Python dependencies pinned to exact versions. All contributors use the same versions. No ranges (e.g., `fastapi>=0.111`) — exact pins (e.g., `fastapi==0.111.0`).

### `.env` / `.env.example`
`.env` contains real credentials — **never committed to version control**. `.env.example` is the committed template with placeholder values and comments. Every new environment variable added to the codebase must be documented in `.env.example` before the PR is merged.

### `.gitignore`
Must include at minimum: `.env`, `__pycache__/`, `.venv/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`.

---

## 2. `app/`

The main application package. Contains all business logic, domain contracts, and API endpoints. Every file in this directory is importable as `from app.<module> import <symbol>`.

**Rule:** `app/__init__.py` is empty (or has a single-line comment). No logic lives in `__init__.py` files at any level.

---

## 3. `app/config/`

**Purpose:** Application-level configuration only.

| File | Purpose |
|---|---|
| `settings.py` | `AppSettings` — loads global env vars (log level, env, API prefix, encryption key). Uses `lru_cache` singleton. |

**What does NOT belong here:** Any connector-specific config (OAuth client IDs, API base URLs, scopes). Those live in `app/connectors/<name>/settings.py`.

---

## 4. `app/auth/`

**Purpose:** The authentication layer. Manages the OAuth lifecycle for the signed-in user.

| File | Purpose |
|---|---|
| `models.py` | `TokenData` — the OAuth token set. `AuthorizationResponse` — returned to the desktop client after login. |
| `repository.py` | `TokenRepository` abstract interface. `InMemoryTokenRepository` (dev/test). Future: `RedisTokenRepository`. |
| `service.py` | `AuthService` — orchestrates PKCE flow: authorization URL generation, code exchange, silent token refresh. |
| `router.py` | HTTP endpoints: `GET /api/v1/auth/login`, `GET /api/v1/auth/callback`, `POST /api/v1/auth/logout`. |

**Import rule:** `app/auth/` may NOT import from `app/connectors/`, `app/context_builder/`, or `app/bob/`.

---

## 5. `app/connectors/`

**Purpose:** Houses the shared connector contracts and all connector implementations.

| File | Purpose |
|---|---|
| `base.py` | `BaseConnector` ABC. Connector exception hierarchy (`ConnectorError`, `ConnectorAuthError`, `ConnectorTimeoutError`, `ConnectorRateLimitError`). |
| `models.py` | `ConnectorResult` model. `ConnectorStatus` enum. Shared by all connectors and the Context Builder. |

**Sub-package rule:** Each enterprise application gets exactly one sub-package. Sub-packages never import from each other.

---

## 6. `app/connectors/outlook/`

**Purpose:** All code specific to the Microsoft Outlook / Microsoft Graph integration.

| File | Purpose |
|---|---|
| `settings.py` | `OutlookSettings` — Azure client ID, tenant ID, redirect URI, Graph base URL, OAuth scopes. |
| `connector.py` | `OutlookConnector(BaseConnector)` — orchestrates fetchers and normalizer, returns `ConnectorResult`. |
| `graph_client.py` | `GraphAPIClient` — all `httpx` calls to `https://graph.microsoft.com/v1.0`. No business logic. |
| `fetchers/calendar.py` | `CalendarFetcher` — calls `GraphAPIClient` for today's calendar events. Returns raw JSON list. |
| `fetchers/email.py` | `EmailFetcher` — calls `GraphAPIClient` for unread and high-importance emails. Returns raw JSON lists. |
| `normalizer.py` | `OutlookNormalizer` — pure function mapping raw Graph JSON → typed `OutlookContext`. |
| `models.py` | `CalendarEvent`, `Email`, `OutlookUser`, `OutlookContext` — internal Pydantic schemas. |
| `router.py` | Optional debug endpoint `GET /api/v1/connectors/outlook/context`. |

**The same structure is replicated for every connector.** `app/connectors/slack/` follows the identical pattern with `SlackAPIClient`, `MessagesFetcher`, `MentionsFetcher`, `SlackNormalizer`, `SlackContext`, etc.

---

## 7. `app/context_builder/`

**Purpose:** Aggregates `ConnectorResult` objects from all active connectors into a single `WorkContext`.

| File | Purpose |
|---|---|
| `models.py` | `WorkContext` — the unified payload sent to IBM Bob. `ConnectorSummary` — per-connector status record. |
| `builder.py` | `ContextBuilder` — holds `list[BaseConnector]` via DI, runs them concurrently, returns `WorkContext`. |

**Import rule:** May import from `app/connectors/base` and `app/connectors/models`. Must NOT import from `app/bob` or any connector sub-package.

---

## 8. `app/bob/`

**Purpose:** IBM Bob integration layer.

| File | Purpose |
|---|---|
| `models.py` | `BobRequest`, `Recommendation`, `RecommendationSet` — the structured output IBM Bob returns. |
| `service.py` | `BobService` abstract interface. `IBMBobService` concrete implementation calling the IBM Bob API. |
| `mock_service.py` | `MockBobService` — returns hardcoded recommendations. Used when `APP_ENV=development`. |

**Import rule:** May import from `app/context_builder/models`. Must NOT import from `app/connectors/` sub-packages or `app/auth/`.

---

## 9. `app/recommendations/`

**Purpose:** Widget-facing API. The only layer the desktop widget interacts with.

| File | Purpose |
|---|---|
| `models.py` | `RecommendationResponse` — the JSON shape returned to the desktop widget. |
| `router.py` | `GET /api/v1/recommendations` — reads from cache, returns `RecommendationResponse`. |
| `scheduler.py` | Background task that runs `ContextBuilder → BobService` every 5 minutes. |
| `cache.py` | `RecommendationCache` — stores and retrieves the latest `RecommendationSet` per user. |

---

## 10. `tests/`

**Purpose:** All test code. Mirrors the `app/` structure exactly.

| Directory / File | Purpose |
|---|---|
| `conftest.py` | Shared pytest fixtures: `mock_token_repository`, `mock_bob_service`, `mock_graph_client`, test settings override. |
| `auth/test_service.py` | Tests for `AuthService` OAuth flow (code exchange, token refresh, PKCE). |
| `auth/test_repository.py` | Tests for `InMemoryTokenRepository` (save, get, delete, exists). |
| `connectors/outlook/fixtures/` | Raw JSON files from the Graph API (recorded once; reused in all tests). |
| `connectors/outlook/test_graph_client.py` | Tests for `GraphAPIClient` using `respx` to mock `httpx`. |
| `connectors/outlook/test_calendar_fetcher.py` | Tests for `CalendarFetcher` using a mock `GraphAPIClient`. |
| `connectors/outlook/test_email_fetcher.py` | Tests for `EmailFetcher` using a mock `GraphAPIClient`. |
| `connectors/outlook/test_normalizer.py` | Tests for `OutlookNormalizer` — pure input/output, no mocking. |
| `connectors/outlook/test_connector.py` | Integration tests for `OutlookConnector` covering SUCCESS, PARTIAL, and FAILED scenarios. |

**Rule:** Tests never make real network calls. All HTTP is mocked via `respx` or injected mock clients.

---

## 11. `docs/`

**Purpose:** All project documentation, organized into logical sections.

| File / Directory | Audience | Purpose |
|---|---|---|
| `README.md` | All | Project entry point — overview, setup, status, reading order |
| `TEAM_RULES.md` | All developers | Non-negotiable engineering rules — read first |
| `IMPLEMENTATION_CHECKLIST.md` | All developers | Phase-by-phase task tracker with checkboxes |
| `architecture/ARCHITECTURE.md` | All engineers | Layered architecture, runtime flow, dependency rules |
| `architecture/DECISIONS.md` | Engineers, architects, judges | Rationale for every major decision (ADRs) |
| `development/CONNECTOR_GUIDE.md` | Connector developers | Full connector implementation guide |
| `development/CONTRIBUTING.md` | All contributors | Engineering standards, PR process, coding conventions |
| `development/GIT_WORKFLOW.md` | All contributors | Branch strategy, commits, releases |
| `planning/ROADMAP.md` | Team and stakeholders | Implementation phases, owners, tags, completion criteria |
| `planning/TEAM_WORKFLOW.md` | All contributors | Parallel development model and coordination points |
| `reference/REPOSITORY_STRUCTURE.md` | New team members | Every folder and file explained — you are here |
| `templates/CONNECTOR_TEMPLATE.md` | Connector developers | Copy-paste blueprint for new connectors |

---

## 12. `scripts/`

**Purpose:** Utility scripts for project setup and validation.

| File | Purpose |
|---|---|
| `generate_key.py` | Generates a Fernet encryption key and prints it. Run once during initial setup. |
| `check_env.py` | Validates that all required environment variables in `.env.example` are present in `.env`. Run before starting the server. |

### `generate_key.py` usage
```bash
python scripts/generate_key.py
# → TOKEN_ENCRYPTION_KEY=<generated-key>
# Copy the output into your .env file.
```

### `check_env.py` usage
```bash
python scripts/check_env.py
# → ✓ All required environment variables are set.
# or
# → ✗ Missing: TOKEN_ENCRYPTION_KEY, AZURE_CLIENT_ID
```

---

## Related Documents

| Document | Purpose |
|---|---|
| [`../README.md`](../README.md) | Project entry point |
| [`../TEAM_RULES.md`](../TEAM_RULES.md) | Engineering rules every developer must follow |
| [`../architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md) | System design and module responsibilities |
| [`../templates/CONNECTOR_TEMPLATE.md`](../templates/CONNECTOR_TEMPLATE.md) | Connector blueprint |

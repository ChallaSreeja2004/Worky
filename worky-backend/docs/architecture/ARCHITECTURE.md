# Worky Backend — Architecture

> **Audience:** All developers contributing to the Worky backend.
> **Purpose:** Define the layered architecture, module responsibilities, dependency rules, and design principles that govern this codebase.
> **Scope:** System design only. Step-by-step connector implementation instructions live in [`../development/CONNECTOR_GUIDE.md`](../development/CONNECTOR_GUIDE.md).

---

## Table of Contents

1. [Architectural Philosophy](#1-architectural-philosophy)
2. [Layered Architecture](#2-layered-architecture)
3. [Runtime Flow](#3-runtime-flow)
4. [Module Responsibilities](#4-module-responsibilities)
5. [Connector Architecture](#5-connector-architecture)
6. [Authentication Layer](#6-authentication-layer)
7. [Context Builder](#7-context-builder)
8. [IBM Bob Integration](#8-ibm-bob-integration)
9. [Recommendation Service](#9-recommendation-service)
10. [Widget Communication](#10-widget-communication)
11. [End-to-End Data Flow](#11-end-to-end-data-flow)
12. [Dependency Rules](#12-dependency-rules)
13. [SOLID Principles Applied](#13-solid-principles-applied)
14. [Clean Architecture Alignment](#14-clean-architecture-alignment)
15. [Scalability Considerations](#15-scalability-considerations)
16. [Why This Architecture](#16-why-this-architecture)

---

## 1. Architectural Philosophy

Worky's backend is designed around three core beliefs:

**1. Connectors are interchangeable plugins.**
The system must be able to add, remove, or replace an enterprise connector without touching any other part of the codebase. A new team member building the GitHub connector should never need to understand how the Outlook connector works.

**2. IBM Bob has one input and one output.**
The AI reasoning engine receives a single, well-defined `WorkContext` object and returns a `RecommendationSet`. It never receives raw API responses, never calls connectors directly, and never knows which enterprise applications are active. This isolation makes Bob testable, swappable, and version-independent.

**3. Every layer is independently testable.**
No layer directly instantiates its dependencies. All dependencies are injected. This means every component — from the `CalendarFetcher` to the `ContextBuilder` — can be unit-tested with mock objects, without requiring real API credentials, a live database, or a running IBM Bob instance.

---

## 2. Layered Architecture

The backend is organized into six distinct layers. Data flows strictly downward. No layer imports from a layer above it.

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 6 — Presentation                                        │
│  Routers · HTTP response models · CORS · versioned API paths   │
│  app/auth/router.py · app/connectors/*/router.py               │
│  app/recommendations/router.py                                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │ depends on
┌──────────────────────────────▼──────────────────────────────────┐
│  Layer 5 — Application Services                                │
│  Orchestration logic · Dependency injection · Auth flow        │
│  app/auth/service.py · app/bob/service.py                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ depends on
┌──────────────────────────────▼──────────────────────────────────┐
│  Layer 4 — Connectors                                          │
│  Per-application data collection                               │
│  app/connectors/outlook/ · app/connectors/slack/ · ...         │
└──────────────────────────────┬──────────────────────────────────┘
                               │ produces ConnectorResult →
┌──────────────────────────────▼──────────────────────────────────┐
│  Layer 3 — Context Builder                                     │
│  Aggregates ConnectorResults into WorkContext                  │
│  app/context_builder/builder.py · models.py                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ produces WorkContext →
┌──────────────────────────────▼──────────────────────────────────┐
│  Layer 2 — Domain Contracts (Shared Foundation)                │
│  Interfaces · Pydantic models · Enumerations                   │
│  app/connectors/base.py · app/connectors/models.py             │
│  app/context_builder/models.py · app/auth/models.py            │
│  app/auth/repository.py                                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ configured by
┌──────────────────────────────▼──────────────────────────────────┐
│  Layer 1 — Infrastructure / Config                             │
│  Settings · Environment · Logging                              │
│  app/config/settings.py · main.py                              │
└─────────────────────────────────────────────────────────────────┘
```

**Rule:** A module may import from its own layer and from any layer below it. It must never import from a layer above it.

---

## 3. Runtime Flow

Two distinct execution paths operate independently: a **scheduled pipeline** that runs every 5 minutes, and a **widget poll** that reads from cache at any time.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PATH A — SCHEDULED PIPELINE  (background task, every 5 minutes)        │
│                                                                          │
│  AuthService.get_valid_token(user_id)                                   │
│    → valid access_token (silent refresh if needed)                      │
│                         │                                                │
│                         ▼                                                │
│  ContextBuilder.build(user_id, access_token)                            │
│    ┌─────────────────────────────────────────────────────────────────┐  │
│    │  Connectors run concurrently (asyncio.gather)                   │  │
│    │  OutlookConnector  →  ConnectorResult (status: SUCCESS/PARTIAL) │  │
│    │  SlackConnector    →  ConnectorResult (status: SUCCESS/PARTIAL) │  │
│    │  [future]          →  ConnectorResult                           │  │
│    └─────────────────────────────────────────────────────────────────┘  │
│    WorkContext.from_connector_results(...)  →  WorkContext               │
│                         │                                                │
│                         ▼                                                │
│  BobService.analyze(work_context)                                       │
│    →  RecommendationSet                                                  │
│                         │                                                │
│                         ▼                                                │
│  RecommendationCache.store(user_id, recommendation_set, ttl=5min)       │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  PATH B — WIDGET POLL  (Desktop Widget, every 60 seconds)               │
│                                                                          │
│  GET /api/v1/recommendations                                            │
│    → RecommendationCache.get(user_id)                                   │
│    → returns RecommendationResponse  (always instant — cache read)      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why two paths?** Decoupling collection from display means the widget is always responsive. If a connector is slow or down, it affects only the scheduled pipeline — the widget still returns the previous cached result instantly.

---

## 4. Module Responsibilities

### `app/config/settings.py`
Loads all environment variables using Pydantic Settings. Owns only application-level configuration (log level, environment, API prefix, encryption key). Each connector defines its own settings class in `app/connectors/<name>/settings.py`.

### `app/auth/`

| File | Responsibility |
|---|---|
| `models.py` | `TokenData` — the OAuth token set schema. `AuthorizationResponse` — returned to the Desktop Widget after login. |
| `repository.py` | `TokenRepository` abstract interface. `InMemoryTokenRepository` for development. `RedisTokenRepository` for production. |
| `service.py` | Orchestrates the OAuth 2.0 PKCE flow: authorization URL generation, code exchange, silent token refresh. Delegates storage to `TokenRepository`. |
| `router.py` | `GET /api/v1/auth/login`, `GET /api/v1/auth/callback`, `POST /api/v1/auth/logout`. |

### `app/connectors/`

| File | Responsibility |
|---|---|
| `base.py` | `BaseConnector` abstract class. Every connector implements this. Also defines the connector exception hierarchy (`ConnectorError`, `ConnectorAuthError`, `ConnectorTimeoutError`, `ConnectorRateLimitError`). |
| `models.py` | `ConnectorResult` — the standard output of every connector. `ConnectorStatus` enum (SUCCESS / PARTIAL / FAILED). |
| `<name>/` | One sub-package per enterprise application. See [Connector Architecture](#4-connector-architecture). |

### `app/context_builder/`

| File | Responsibility |
|---|---|
| `models.py` | `WorkContext` — the unified payload sent to IBM Bob. `ConnectorSummary` — per-connector status record. |
| `builder.py` | `ContextBuilder` — runs all registered connectors concurrently, assembles their results into a `WorkContext`. |

### `app/bob/`

| File | Responsibility |
|---|---|
| `service.py` | `BobService` abstract interface. `IBMBobService` concrete implementation that calls the IBM Bob API. |
| `mock_service.py` | `MockBobService` — returns hardcoded recommendations. Used in development and all tests. |
| `models.py` | `BobRequest`, `RecommendationSet`, `Recommendation` Pydantic models. |

### `app/recommendations/`

| File | Responsibility |
|---|---|
| `router.py` | `GET /api/v1/recommendations` — the only endpoint the desktop widget calls. Retrieves the latest cached `RecommendationSet` for the user. |
| `models.py` | `RecommendationResponse` — the JSON shape returned to the widget. |

---

## 5. Connector Architecture

Each connector is a self-contained Python package under `app/connectors/<name>/` following an identical internal structure.

```
app/connectors/<name>/
├── settings.py          # Connector-specific env vars (client ID, scopes, base URL)
├── connector.py         # <Name>Connector(BaseConnector) — orchestrates fetchers
├── <name>_client.py     # Raw HTTP client — all httpx calls live here
├── fetchers/
│   ├── <entity_a>.py    # Returns raw API JSON — no normalization
│   └── <entity_b>.py    # Returns raw API JSON — no normalization
├── normalizer.py        # Pure function: raw JSON → typed Pydantic models
├── models.py            # <Name>Context and entity schemas
└── router.py            # Optional debug endpoint
```

**Every new connector follows this identical structure.** See [`../development/CONNECTOR_GUIDE.md`](../development/CONNECTOR_GUIDE.md) for step-by-step instructions and [`../templates/CONNECTOR_TEMPLATE.md`](../templates/CONNECTOR_TEMPLATE.md) for the copy-paste blueprint.

### Outlook Connector — Current Build State (v0.4.0)

The Outlook connector is being built incrementally one layer at a time. The data flow as of Phase 4:

```
Microsoft Graph API  (external)
        │  HTTP — GET /me/calendarView
        ▼
GraphAPIClient                     app/connectors/outlook/graph_client.py
  • Attaches Bearer token
  • Retries on 429 / 503 (1 s → 2 s → raise)
  • Returns raw Graph JSON envelope
        │  dict[str, Any]  {"value": [...], "@odata.context": "..."}
        ▼
CalendarFetcher                    app/connectors/outlook/fetchers/calendar.py
  • Extracts response["value"]
  • Returns [] for empty or missing key
  • Does NOT catch exceptions — propagates GraphError upward
        │  list[dict[str, Any]]   raw Graph event objects
        ▼
  (OutlookNormalizer — Phase 6)    ← not yet built
  (OutlookConnector  — Phase 7)    ← not yet built
```

Layers not yet built (`OutlookNormalizer`, `OutlookConnector`) are placeholders. The `CalendarFetcher` layer is complete and tested (12 tests, 89 total).

### Connector boundaries

| Connector must | Connector must not |
|---|---|
| Implement `BaseConnector` | Call IBM Bob |
| Return `ConnectorResult` from `get_context()` | Call the Recommendation Service |
| Normalize raw API data before returning | Call another connector |
| Handle partial failures with `ConnectorResult.partial()` | Manage token refresh |
| Never raise from `get_context()` | Store application state |

---

## 6. Authentication Layer

Worky uses **OAuth 2.0 Authorization Code Flow with PKCE** for all enterprise application integrations that require delegated user access (Outlook, Slack, GitHub).

### Why PKCE for a desktop application?

Desktop applications are *public clients* — they cannot safely embed a client secret inside a binary that is distributed to users' machines. PKCE replaces the client secret with a cryptographic challenge that is generated fresh for every login, making code interception attacks impossible even if the authorization code is captured.

### Token lifecycle

```
User login
    │
    ▼
AuthService.get_authorization_url()
    → Generates code_verifier + code_challenge (PKCE)
    → Returns Microsoft login URL
    │
    ▼
User authenticates at Microsoft
    │
    ▼
Microsoft redirects → /api/v1/auth/callback?code=...
    │
    ▼
AuthService.exchange_code_for_tokens(code, state)
    → Exchanges code + code_verifier for access_token + refresh_token
    → Encrypts refresh_token with Fernet
    → TokenRepository.save(token_data)
    │
    ▼
AuthService.get_valid_token(user_id)   ← called before every connector run
    → TokenRepository.get(user_id)
    → If token_data.is_expired:
          → Calls /token with refresh_token
          → TokenRepository.save(new_token_data)
    → Returns valid access_token
```

### Token storage security model

| Token | Storage | Encrypted | Persisted |
|---|---|---|---|
| `access_token` | In-memory only | No | Never |
| `refresh_token` | TokenRepository | Yes (Fernet) | Yes |

The `access_token` is never written to any database or file. If the process restarts, the `AuthService` uses the stored encrypted `refresh_token` to silently obtain a new `access_token` without re-prompting the user.

---

## 7. Context Builder

The Context Builder is the aggregation layer between connectors and IBM Bob.

### Responsibilities
- Hold a registry of all active `BaseConnector` instances (injected via DI)
- Run all connectors concurrently for a given user
- Handle connector failures gracefully — one failing connector must not prevent others from running
- Assemble all `ConnectorResult` objects into a single `WorkContext`
- Attach assembly metadata (duration, connector count) for observability

### Concurrency model

```python
results = await asyncio.gather(
    *[connector.get_context(user_id, token) for connector in self._connectors],
    return_exceptions=False  # connectors handle their own exceptions internally
)
work_context = WorkContext.from_connector_results(user_id, results)
```

Connectors run in parallel. If the Outlook connector takes 400ms and the Slack connector takes 300ms, the total assembly time is ~400ms, not 700ms.

### Adding a new connector

1. Create `app/connectors/<name>/connector.py` implementing `BaseConnector`
2. Add the connector to the DI registry in `main.py`
3. The Context Builder picks it up automatically — zero changes to `ContextBuilder` itself

---

## 8. IBM Bob Integration

IBM Bob is treated as a **pluggable reasoning service** behind the `BobService` interface. The concrete implementation (`IBMBobService`) calls IBM Bob's API. A `MockBobService` returns deterministic hardcoded recommendations for development and testing.

### Interface contract

```
BobService.analyze(work_context: WorkContext) → RecommendationSet
```

IBM Bob receives a single `WorkContext` object and returns a `RecommendationSet`. It never:
- Calls connectors directly
- Accesses the database
- Knows which connector implementation produced the data

### Why WorkContext and not raw connector data?

Sending raw connector data directly to Bob would couple Bob's reasoning to the output format of each connector. If the Outlook connector changes its response schema, Bob's prompts break. By normalizing everything into `WorkContext` first, Bob always receives a stable, versioned schema regardless of how many connectors are active or what their internal schemas look like.

---

## 9. Recommendation Service

The Recommendation Service is the widget-facing layer. It owns:

- The scheduled background task that triggers `ContextBuilder.build()` → `BobService.analyze()` every 5 minutes
- The recommendation cache (Redis TTL document)
- The `GET /api/v1/recommendations` endpoint that the widget polls

### Why a cache between Bob and the widget?

The widget polls for recommendations frequently (every 30–60 seconds). Without a cache, each poll would trigger a full context collection across all connectors plus an IBM Bob API call. This would:
- Exhaust enterprise API rate limits (Microsoft Graph allows ~10,000 calls per 10 minutes)
- Introduce latency on every widget render
- Generate unnecessary AI inference costs

The cache means the widget always gets an instant response. Bob is called on a controlled schedule, not on every widget poll.

---

## 10. Widget Communication

The desktop widget communicates with the backend through a single endpoint:

```
GET /api/v1/recommendations
Authorization: Bearer <access_token>

Response:
{
  "user_id": "...",
  "generated_at": "2025-07-10T09:15:00Z",
  "recommendations": [
    {
      "priority": 1,
      "category": "email",
      "title": "High-priority email from your manager",
      "description": "Re: Q3 Review — requires your response today",
      "action_url": "https://outlook.office.com/...",
      "source": "outlook"
    }
  ],
  "context_freshness": "2025-07-10T09:10:00Z"
}
```

The widget never calls connector endpoints directly. It has no knowledge of how data is collected, how Bob processes it, or which enterprise applications are connected.

---

## 11. End-to-End Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│  SCHEDULED TASK (every 5 minutes)                                   │
│                                                                      │
│  1. AuthService.get_valid_token(user_id)                            │
│       → Returns valid access_token (refreshes if expired)           │
│                                                                      │
│  2. ContextBuilder.build(user_id, access_token)                     │
│       → Runs all connectors concurrently                            │
│       → OutlookConnector.get_context() → ConnectorResult            │
│       → SlackConnector.get_context()   → ConnectorResult            │
│       → WorkContext.from_connector_results(...)  → WorkContext      │
│                                                                      │
│  3. BobService.analyze(work_context)                                │
│       → Sends WorkContext to IBM Bob API                            │
│       → Returns RecommendationSet                                   │
│                                                                      │
│  4. Cache.store(user_id, recommendation_set, ttl=5min)              │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  WIDGET POLL (every 30–60 seconds)                                  │
│                                                                      │
│  GET /api/v1/recommendations                                        │
│       → Cache.get(user_id)                                          │
│       → Returns cached RecommendationSet immediately                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 12. Dependency Rules

These rules are enforced by import conventions documented at the top of every module.

| Module | May import from | Must NOT import from |
|---|---|---|
| `connectors/models.py` | stdlib, pydantic | Any connector sub-package, context_builder, bob, auth |
| `connectors/base.py` | stdlib, connectors/models | Any connector sub-package, context_builder, bob, auth |
| `connectors/<name>/` | stdlib, pydantic, connectors/base, connectors/models | Other connector sub-packages, context_builder, bob |
| `context_builder/models.py` | stdlib, pydantic, connectors/models | Connector sub-packages, bob, auth |
| `context_builder/builder.py` | connectors/base, context_builder/models | bob, auth |
| `bob/service.py` | context_builder/models, bob/models | connectors, auth |
| `auth/repository.py` | stdlib, auth/models | connectors, context_builder, bob |
| `auth/service.py` | auth/models, auth/repository | connectors, context_builder, bob |
| `recommendations/router.py` | bob/models, auth | connectors directly |

---

## 13. SOLID Principles Applied

### Single Responsibility
Every module owns exactly one concern. `GraphAPIClient` only makes HTTP calls. `CalendarFetcher` only fetches calendar data. `Normalizer` only maps raw JSON to typed models. `AuthService` only manages the OAuth flow. None of these classes do more than one thing.

### Open / Closed
The system is open for extension (add `GitHubConnector`) and closed for modification (adding GitHub does not change `BaseConnector`, `ContextBuilder`, or any existing connector). The plugin architecture enforces this structurally.

### Liskov Substitution
`OutlookConnector`, `SlackConnector`, and any future connector are fully substitutable wherever a `BaseConnector` is expected. The `ContextBuilder` holds a `list[BaseConnector]` and calls `get_context()` without knowing which concrete type it is calling.

### Interface Segregation
`BaseConnector` defines only three methods. Connectors that need additional behavior (webhooks, polling, etc.) extend their own class without bloating the shared interface. `TokenRepository` defines only four methods — the minimum needed for any storage backend.

### Dependency Inversion
High-level modules depend on abstractions, not implementations. `ContextBuilder` depends on `BaseConnector`, not `OutlookConnector`. `AuthService` depends on `TokenRepository`, not `InMemoryTokenRepository`. `RecommendationService` depends on `BobService`, not `IBMBobService`.

---

## 14. Clean Architecture Alignment

```
Outer rings depend on inner rings. Inner rings know nothing about outer rings.

┌─────────────────────────────────────────────────┐
│  Frameworks & Drivers                           │
│  FastAPI, httpx, Redis, MongoDB, Electron       │
│  (outermost — most volatile)                    │
├─────────────────────────────────────────────────┤
│  Interface Adapters                             │
│  Routers, Normalizers, Repositories             │
├─────────────────────────────────────────────────┤
│  Application Use Cases                          │
│  AuthService, ContextBuilder, BobService        │
├─────────────────────────────────────────────────┤
│  Domain / Contracts                             │
│  BaseConnector, ConnectorResult, WorkContext    │
│  TokenRepository, RecommendationSet             │
│  (innermost — most stable)                      │
└─────────────────────────────────────────────────┘
```

The domain contracts (inner ring) never change because a framework changed (outer ring). FastAPI can be replaced with another web framework without touching `WorkContext` or `BaseConnector`.

---

## 15. Scalability Considerations

### Adding connectors
Each new connector is a new sub-package implementing `BaseConnector`. Registration is a one-line change in `main.py`. No other file changes.

### Multiple workers
The `InMemoryTokenRepository` is not safe for multi-worker deployments. The `RedisTokenRepository` must be used in production to ensure tokens are shared across all uvicorn workers.

### Rate limiting
Microsoft Graph allows ~10,000 API calls per 10 minutes per user. The scheduled context collection (every 5 minutes) makes at most 5–10 Graph API calls per run. Well within limits.

### Horizontal scaling
The backend is stateless at the application layer. All state (tokens, recommendations) lives in Redis/MongoDB. Multiple backend instances can run behind a load balancer without session affinity.

### Bob API cost control
Bob is only called when the scheduled task fires (every 5 minutes), not on every widget poll. For 1,000 active users, this is ~12,000 Bob API calls per hour — a predictable, controllable cost.

---

## 16. Why This Architecture

This architecture was chosen over simpler alternatives for four reasons:

**1. Team parallelism.** Multiple developers work on different connectors simultaneously. The `BaseConnector` contract is the only coordination point. Developers never need to wait for each other.

**2. Independent deployability.** Individual connectors can be disabled, updated, or replaced without redeploying the entire backend. If the Slack API changes, only `SlackConnector` is updated.

**3. AI isolation.** IBM Bob's reasoning quality depends on receiving clean, normalized, consistent input. Sending raw connector data would make Bob's outputs highly sensitive to connector implementation details. `WorkContext` provides a stable, versioned interface.

**4. Enterprise reliability.** Connector failures are isolated. If GitHub's API is down, the widget still shows Outlook and Slack recommendations. The `ConnectorStatus.PARTIAL` and `ConnectorStatus.FAILED` states give Bob the information it needs to reason about incomplete data.

---

## Related Documents

| Document | Purpose |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | Detailed rationale for every technology and design choice |
| [`../development/CONNECTOR_GUIDE.md`](../development/CONNECTOR_GUIDE.md) | Step-by-step connector implementation guide |
| [`../templates/CONNECTOR_TEMPLATE.md`](../templates/CONNECTOR_TEMPLATE.md) | Copy-paste connector blueprint |
| [`../TEAM_RULES.md`](../TEAM_RULES.md) | Non-negotiable engineering rules |

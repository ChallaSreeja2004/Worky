# Worky — Architecture Decision Records (ADR)

> **Purpose:** Document every major technical decision made during the design and development of the Worky backend — including the context, the alternatives considered, and the reasoning for the choice made.
>
> **Audience:** Engineers, architects, judges, mentors, and future contributors who want to understand not just *what* the system does, but *why* it was designed this way.
>
> **Format:** Each ADR is numbered, titled, dated, and includes: Context → Decision → Alternatives Considered → Rationale → Consequences.

---

## Table of Contents

- [ADR-001 — FastAPI as the backend framework](#adr-001--fastapi-as-the-backend-framework)
- [ADR-002 — Electron + React for the desktop application](#adr-002--electron--react-for-the-desktop-application)
- [ADR-003 — BaseConnector abstract interface](#adr-003--baseconnector-abstract-interface)
- [ADR-004 — ConnectorResult as a generic output contract](#adr-004--connectorresult-as-a-generic-output-contract)
- [ADR-005 — Context Builder as a dedicated aggregation layer](#adr-005--context-builder-as-a-dedicated-aggregation-layer)
- [ADR-006 — IBM Bob receives only WorkContext, not raw connector data](#adr-006--ibm-bob-receives-only-workcontext-not-raw-connector-data)
- [ADR-007 — TokenRepository pattern for OAuth token persistence](#adr-007--tokenrepository-pattern-for-oauth-token-persistence)
- [ADR-008 — OAuth 2.0 Authorization Code + PKCE (not Client Credentials)](#adr-008--oauth-20-authorization-code--pkce-not-client-credentials)
- [ADR-009 — Microsoft Graph API for Outlook integration](#adr-009--microsoft-graph-api-for-outlook-integration)
- [ADR-010 — Modular connector architecture](#adr-010--modular-connector-architecture)
- [ADR-011 — Clean Architecture layering](#adr-011--clean-architecture-layering)
- [ADR-012 — Pydantic v2 for all data models](#adr-012--pydantic-v2-for-all-data-models)
- [ADR-013 — Recommendation cache between Bob and the widget](#adr-013--recommendation-cache-between-bob-and-the-widget)
- [ADR-014 — Fernet symmetric encryption for refresh tokens](#adr-014--fernet-symmetric-encryption-for-refresh-tokens)
- [ADR-015 — Connector settings are separate from AppSettings](#adr-015--connector-settings-are-separate-from-appsettings)

---

## ADR-001 — FastAPI as the backend framework

**Date:** Project inception
**Status:** Accepted

### Context
The Worky backend needs to expose REST APIs to the desktop widget, run background tasks for context collection, and make many concurrent async calls to enterprise APIs (Microsoft Graph, Slack, GitHub). The framework choice impacts developer productivity, async support, type safety, and testability.

### Decision
Use **FastAPI** as the backend framework.

### Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Flask | No native async support. Async enterprise API calls would block the event loop. |
| Django REST Framework | Heavy, opinionated, sync-first. Overkill for a service-oriented API. Poor async story. |
| aiohttp | Low-level. Requires building routing, validation, and docs tooling from scratch. |
| Litestar | Strong contender, but smaller ecosystem and less community familiarity for a team project. |

### Rationale
FastAPI provides:
- **Native async/await** — critical since every connector call is I/O-bound (network calls to external APIs)
- **Pydantic integration** — request/response models are automatically validated and serialized
- **Automatic OpenAPI documentation** — every endpoint is documented at `/docs` for free
- **Dependency injection** — the DI system is used to inject `TokenRepository`, `BobService`, and connector lists
- **Minimal boilerplate** — a router with one endpoint is ~5 lines of code

### Consequences
- All endpoint functions must be `async def`
- `httpx` (not `requests`) is used for all outbound HTTP calls
- Tests use `httpx.AsyncClient` with FastAPI's `TestClient` wrapper

---

## ADR-002 — Electron + React for the desktop application

**Date:** Project inception
**Status:** Accepted

### Context
Worky needs a desktop widget that is always visible, cross-platform (Windows and macOS), and capable of displaying dynamic AI-generated recommendations. It must integrate with the OS (system tray, notifications) and communicate with the FastAPI backend.

### Decision
Use **Electron + React** for the desktop application.

### Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Native macOS (Swift) + Win32 | Two separate codebases for one UI. High maintenance cost. |
| Tauri (Rust + Web) | Strong contender but smaller ecosystem. Team has stronger React familiarity. |
| PyQt / Tkinter | Difficult to build modern, visually polished UIs. |
| Progressive Web App | No persistent OS-level presence. Cannot integrate with system tray. |

### Rationale
- Single codebase for Windows and macOS
- React ecosystem is familiar to most web developers
- Electron gives direct access to OS APIs (tray, notifications, native menus)
- Node.js bridge enables secure IPC between the widget UI and the OS

### Consequences
- The desktop application is a separate repository from the backend
- Communication is HTTP only — the widget calls `GET /api/v1/recommendations`
- Bundle size is larger than native alternatives — acceptable for an enterprise application

---

## ADR-003 — BaseConnector abstract interface

**Date:** Phase 1
**Status:** Accepted

### Context
Multiple developers are implementing connectors in parallel (Outlook, Slack, GitHub, Jira). Without a shared interface, each developer would invent their own method signatures and output formats. The Context Builder would then need to know the internals of every connector — a maintenance nightmare.

### Decision
Define `BaseConnector` as an **abstract base class** with three abstract members: `source_name`, `get_context()`, and `health_check()`. Every connector must implement this contract.

### Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Protocol (structural subtyping) | Less explicit. No enforcement at class definition time. |
| No shared interface — Context Builder imports each connector directly | Creates tight coupling. Context Builder must change every time a connector is added. |
| Data class with callable fields | Not idiomatic Python. No runtime enforcement. |

### Rationale
An ABC enforces the contract at class instantiation time — you cannot create a `SlackConnector` without implementing all three methods. Python raises `TypeError` immediately if a method is missing. This catches missing implementations during development, not at runtime in production.

The `get_context(user_id, access_token) → ConnectorResult` signature deliberately passes `access_token` as a parameter rather than having the connector fetch its own token. This means:
- The connector is completely stateless
- The connector is fully testable with any string as the token
- Token lifecycle is not duplicated across connectors

### Consequences
- All connectors must implement `source_name`, `get_context()`, and `health_check()`
- The Context Builder holds `list[BaseConnector]` — it never imports from a connector sub-package
- New connectors require zero changes to existing code

---

## ADR-004 — ConnectorResult as a generic output contract

**Date:** Phase 1
**Status:** Accepted

### Context
Each connector collects different types of data: Outlook has calendar events and emails; Slack has messages and mentions; GitHub has pull requests and review requests. The Context Builder needs to receive the output of all connectors in a consistent shape without needing to know which connector produced it.

### Decision
Define `ConnectorResult` with a generic `data: dict[str, Any]` field. Each connector serializes its typed output (`OutlookContext`, `SlackContext`) into this dictionary using `.model_dump()`.

### Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| `ConnectorResult[T]` generic type | Pydantic v2 generics add complexity and lose runtime erasure safety with `dict` serialization. |
| Union type: `data: OutlookContext \| SlackContext \| ...` | Every new connector requires modifying `ConnectorResult`. Violates Open/Closed Principle. |
| Each connector returns its own typed result | Context Builder must import every connector's models. Tight coupling. |

### Rationale
`dict[str, Any]` is the right type for a generic contract that must remain open for extension. Any consumer that needs typed access to connector-specific fields uses `MyConnectorContext.model_validate(result.data)` — explicit, safe, and decoupled.

The `ConnectorStatus` enum (SUCCESS/PARTIAL/FAILED) is critical because the Context Builder must distinguish between "connector succeeded", "connector got partial data", and "connector failed entirely" — and communicate this distinction to IBM Bob so Bob can reason about data gaps.

### Consequences
- Connector-specific schemas are internal to each connector package
- The Context Builder never imports connector-specific models
- Downstream consumers that need typed fields perform explicit `model_validate()` calls

---

## ADR-005 — Context Builder as a dedicated aggregation layer

**Date:** Architecture review
**Status:** Accepted

### Context
Without a dedicated Context Builder, the natural instinct is for each connector router to call IBM Bob directly. This creates one AI call per connector, multiple round-trips to Bob per context collection cycle, and tight coupling between individual connectors and the AI layer.

### Decision
Introduce a dedicated `ContextBuilder` service that aggregates all connector results into a single `WorkContext` before any AI call is made.

### Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Each connector calls Bob directly | Multiple Bob calls per cycle. Each connector must know about Bob. Untestable. |
| A single "mega-connector" that calls all APIs | Violates Single Responsibility. One team member must own and understand all enterprise APIs. |
| Bob pulls data directly from connectors | Bob would need direct knowledge of enterprise APIs. Bob's interface would be fragile. |

### Rationale
The Context Builder provides three critical guarantees:
1. **Bob has one input.** Every connector's output is normalized into `WorkContext` before Bob sees any data.
2. **Connector failures are isolated.** If GitHub times out, the Context Builder records the failure and continues. Bob receives a `WorkContext` with `github` absent from `active_sources` and reasons accordingly.
3. **Team parallelism.** Developers implement connectors independently. They never need to coordinate with the Bob integration developer.

### Consequences
- A new connector is added to the Context Builder's DI registry — zero other changes
- The Context Builder must run all connectors concurrently via `asyncio.gather()`
- `WorkContext` is the versioned API surface with IBM Bob

---

## ADR-006 — IBM Bob receives only WorkContext, not raw connector data

**Date:** Architecture review
**Status:** Accepted

### Context
An alternative approach would be to send raw connector data (e.g., the raw Microsoft Graph API response) directly to Bob. This would simplify the normalizer and connector layers. But it couples Bob's reasoning to raw API response formats.

### Decision
IBM Bob receives only a `WorkContext` — a fully normalized, structured, schema-versioned payload assembled by the Context Builder.

### Rationale
Microsoft Graph's response format has changed multiple times across API versions. If Bob's prompts referenced raw Graph field names (`bodyPreview`, `receivedDateTime`, `internetMessageHeaders`), every Microsoft API update would require updating Bob's integration. With `WorkContext`, the fields Bob sees are defined by Worky, not by Microsoft.

Additionally, Bob's reasoning quality improves when it receives domain-normalized data. Telling Bob "you have 3 unread high-importance emails" is more useful than sending it raw JSON with nested headers and MIME metadata.

### Consequences
- The Normalizer layer is required — it cannot be skipped
- `WorkContext` is a formally versioned schema. Changes require a deliberate update and documentation in this ADR file
- Bob is completely isolated from enterprise API changes

---

## ADR-007 — TokenRepository pattern for OAuth token persistence

**Date:** Architecture review
**Status:** Accepted

### Context
The original design used a module-level dictionary (`_token_store: dict[str, TokenData] = {}`) for token storage. This works in a single-process development environment but fails in production with multiple uvicorn workers — each worker has isolated memory, so tokens saved by worker 1 are invisible to worker 2.

### Decision
Define `TokenRepository` as an abstract interface. The `AuthService` depends on this interface. Concrete implementations (`InMemoryTokenRepository`, `RedisTokenRepository`, `MongoTokenRepository`) are injected via the DI container.

### Rationale
The Repository Pattern separates the *concern of storing data* from the *concern of orchestrating business logic*. The `AuthService` focuses on the OAuth flow; it never knows whether tokens are stored in RAM, Redis, or MongoDB. Swapping backends is a one-line DI configuration change.

Additionally, `InMemoryTokenRepository` is a fully functional development implementation that enables the entire system to run without external dependencies — ideal for development and unit testing.

### Consequences
- `AuthService` constructor accepts a `TokenRepository` parameter
- Production deployment requires `RedisTokenRepository` (to be implemented in Phase 13)
- Unit tests inject `InMemoryTokenRepository` directly — no database required

---

## ADR-008 — OAuth 2.0 Authorization Code + PKCE (not Client Credentials)

**Date:** Phase 2
**Status:** Accepted

### Context
Microsoft Graph supports two primary OAuth flows: **Client Credentials** (app-only, no user identity) and **Authorization Code + PKCE** (delegated, acts on behalf of the user).

### Decision
Use **Authorization Code + PKCE** for all Outlook integration.

### Rationale
Client Credentials flow requires admin consent for the entire tenant and reads *all* users' data with a single identity. Worky is a personal productivity tool — it reads *this user's* data using *this user's* identity. Delegated access (Authorization Code) is the correct model.

PKCE replaces the client secret for desktop/public clients. A client secret embedded in a desktop binary can be extracted by any user who installs the application. PKCE generates a fresh cryptographic challenge per login, making code interception attacks impossible.

### Consequences
- Each user must grant consent once per installation
- The application must be registered as a "Public client" in Azure AD
- No client secret is needed or stored
- `offline_access` scope must be requested to receive a refresh token

---

## ADR-009 — Microsoft Graph API for Outlook integration

**Date:** Phase 3
**Status:** Accepted

### Context
Microsoft provides two API options for Outlook integration: the legacy **Outlook REST API** and the modern **Microsoft Graph API**.

### Decision
Use **Microsoft Graph API v1.0** exclusively.

### Rationale
Microsoft officially deprecated the Outlook REST API (v2.0 beta) in November 2022, with full shutdown in March 2024. Microsoft Graph is the strategic, long-term, officially supported API for all Microsoft 365 services. It also provides a unified access point for future integrations (Teams, SharePoint, OneDrive) without separate authentication.

### Consequences
- All Graph calls use `https://graph.microsoft.com/v1.0/`
- `$select` parameters are mandatory on all calls to avoid fetching unnecessarily large payloads
- Rate limits: ~10,000 requests per 10 minutes per user per application

---

## ADR-010 — Modular connector architecture

**Date:** Phase 1
**Status:** Accepted

### Context
Worky ultimately integrates with six or more enterprise applications. A monolithic approach — one large class handling all API calls — would become unmaintainable. It also prevents parallel development.

### Decision
Each enterprise application integration is a **separate, self-contained Python package** with identical internal structure (settings, client, fetchers, normalizer, connector, models, router).

### Rationale
The identical internal structure means:
- A developer who has read `CONNECTOR_GUIDE.md` can implement any connector without needing to understand any other connector
- Code review is predictable — reviewers know exactly where to look for each concern
- One connector's bugs cannot affect another connector's runtime behavior
- Connectors can be disabled without removing code — simply remove from the DI registry

### Consequences
- All connectors must follow the structure in `CONNECTOR_GUIDE.md`
- PRs that deviate from the structure require an architectural discussion before merge
- The `source_name` property uniquely identifies each connector

---

## ADR-011 — Clean Architecture layering

**Date:** Architecture review
**Status:** Accepted

### Context
Without explicit layering rules, import dependencies tend to spread in all directions as the codebase grows. A router imports a connector; a connector imports a service; a service imports a router. These circular, directional violations make the codebase brittle and difficult to test.

### Decision
Enforce Clean Architecture layering: outer layers depend on inner layers; inner layers never depend on outer layers.

```
Domain Contracts → Application Services → Interface Adapters → Frameworks
```

Import rules are documented at the top of every module and enforced by code review.

### Rationale
The domain contracts (`BaseConnector`, `ConnectorResult`, `WorkContext`, `TokenRepository`) are the most stable part of the system. They change infrequently. The framework (FastAPI, httpx, Redis) changes when libraries are updated. By pointing dependencies inward (toward stable contracts) rather than outward (toward volatile frameworks), the domain layer can be tested without starting FastAPI, without a real database, and without real API credentials.

### Consequences
- Every module must document its import rules
- Architecture violations are blocking PR review issues
- New major structural additions require an ADR entry

---

## ADR-012 — Pydantic v2 for all data models

**Date:** Phase 1
**Status:** Accepted

### Context
The system exchanges structured data between many layers. Without a validation layer, a malformed Microsoft Graph response could propagate bad data all the way to IBM Bob.

### Decision
Use **Pydantic v2** for all data models throughout the codebase.

### Rationale
Pydantic v2 provides:
- Runtime type validation at every layer boundary (connector output, WorkContext, RecommendationSet)
- `.model_dump()` and `.model_validate()` for clean serialization
- `computed_field` for derived properties that are part of the model schema
- Significant performance improvements over v1 (Rust-backed core)
- Native FastAPI integration — request/response models are automatically validated

### Consequences
- All models use `model_config` instead of the v1 `class Config`
- `model_dump()` replaces `.dict()`, `model_validate()` replaces `.parse_obj()`
- `datetime` fields require `timezone.utc` — `datetime.utcnow()` is banned in favor of `datetime.now(timezone.utc)`

---

## ADR-013 — Recommendation cache between Bob and the widget

**Date:** Architecture review
**Status:** Accepted

### Context
The desktop widget needs to display recommendations responsively. If every widget render triggered a full context collection + Bob API call, it would:
- Exhaust Microsoft Graph API rate limits (10,000 calls per 10 min per user)
- Make every widget render feel slow (400–800ms for context collection + Bob latency)
- Generate unpredictable and hard-to-budget IBM Bob API costs

### Decision
Introduce a **recommendation cache** between Bob and the widget. A background task runs every 5 minutes, executes the full pipeline, and stores the result. The widget reads from cache — always instant.

### Consequences
- Recommendations are at most 5 minutes stale — acceptable for a productivity companion
- Bob API call rate is predictable and controllable
- Widget response time is constant (cache read), not variable (full pipeline)
- Cache TTL must be synchronized with the scheduler interval

---

## ADR-014 — Fernet symmetric encryption for refresh tokens

**Date:** Phase 1
**Status:** Accepted

### Context
Refresh tokens are long-lived credentials. If stored in plaintext in MongoDB or Redis and the database is compromised, every user's Microsoft, Slack, and GitHub accounts could be accessed. Refresh tokens must be encrypted at rest.

### Decision
Use **Fernet** (from the `cryptography` library) for symmetric encryption of refresh tokens before persistence.

### Rationale
Fernet provides authenticated encryption (AES-128-CBC + HMAC-SHA256). It is simple to use, part of a well-audited library, and produces encrypted ciphertext that can be stored as a string in any database. The encryption key is loaded from an environment variable (never hardcoded) and is shared across all `TokenRepository` implementations via `AppSettings`.

### Consequences
- Rotating the `TOKEN_ENCRYPTION_KEY` invalidates all stored refresh tokens — users must re-authenticate
- The key must be kept secret and backed up securely
- Only `AuthService` holds the key and decrypts tokens — the `TokenRepository` treats them as opaque strings

---

## ADR-015 — Connector settings are separate from AppSettings

**Date:** Architecture review
**Status:** Accepted

### Context
The initial `Settings` class contained both global application settings and Microsoft-specific settings (client ID, tenant ID, Graph URL, OAuth scopes). When a Slack connector is added, it would also add `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, etc. to the same class.

### Decision
Global settings live in `AppSettings` (`app/config/settings.py`). Each connector defines its own settings class in `app/connectors/<name>/settings.py`.

### Rationale
A settings class that grows to include credentials for six enterprise applications becomes impossible to understand and is a security risk — any developer importing `AppSettings` gets access to every credential. Per-connector settings classes enforce need-to-know access (only the connector's own code imports its settings) and prevent `AppSettings` from becoming a god-object.

### Consequences
- Adding a new connector never requires editing `AppSettings`
- `AppSettings` remains stable throughout the project lifecycle
- Each connector's `.env.example` section is clearly labeled and self-contained

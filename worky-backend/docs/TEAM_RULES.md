# Worky Engineering Handbook — Team Rules

> **Read this first.**
> This document contains the non-negotiable engineering rules for the Worky project.
> Every developer must read and understand these rules before writing a single line of code.
> These rules are not suggestions. They define the architecture contract the entire team depends on.

---

## The Ten Rules

### Rule 1 — Every connector implements BaseConnector
Every enterprise application connector — Outlook, Slack, GitHub, Jira, Confluence, Calendar, and all future connectors — **must** subclass `BaseConnector` and implement its three abstract members: `source_name`, `get_context()`, and `health_check()`.

There are no exceptions. A connector that does not implement `BaseConnector` cannot be registered in the system.

### Rule 2 — Every connector returns ConnectorResult
The `get_context()` method **must** always return a `ConnectorResult`. It must **never** raise an unhandled exception. All errors — authentication failures, timeouts, rate limits, partial data — are expressed through `ConnectorResult.failed()` or `ConnectorResult.partial()`.

### Rule 3 — Every connector owns exactly one enterprise application
A connector package owns exactly one external API. `OutlookConnector` fetches only Outlook data. `SlackConnector` fetches only Slack data. A single connector must never integrate two separate enterprise APIs.

### Rule 4 — Connectors never communicate with each other
No connector may import from, call, or depend on another connector. `SlackConnector` must never import anything from `app/connectors/outlook/`. Cross-connector dependencies create coupling that defeats the entire plugin architecture.

### Rule 5 — Connectors never call IBM Bob
A connector's only job is data collection. It must never call `BobService`, `ContextBuilder`, or any layer above it. The flow is strictly one-directional: Connector → ConnectorResult → Context Builder → WorkContext → IBM Bob.

### Rule 6 — IBM Bob receives only WorkContext
IBM Bob's interface accepts one input: `WorkContext`. Bob never receives raw connector data, raw API responses, or individual `ConnectorResult` objects. `WorkContext` is the stable, versioned contract between the Context Builder and IBM Bob.

### Rule 7 — The Context Builder is the only aggregation layer
No other part of the system aggregates data from multiple connectors. The Context Builder owns this responsibility exclusively. Routers, services, and the Recommendation Service never call multiple connectors themselves.

### Rule 8 — Never expose raw third-party API responses outside a connector
Raw responses from Microsoft Graph, the Slack API, or any other enterprise API must be normalized inside the connector before leaving it. The `ConnectorResult.data` dictionary must contain Worky-domain field names, not vendor-API field names.

### Rule 9 — Every connector must include tests
Before a connector PR is merged, the following tests must exist and pass:
- Unit tests for the normalizer (100% coverage — it is a pure function)
- Unit tests for each fetcher using a mock API client
- Unit tests for the connector covering SUCCESS, PARTIAL, and FAILED scenarios

No connector is considered complete without tests.

### Rule 10 — No layer may violate the documented dependency rules
The dependency rules in [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) define exactly which modules may import from which other modules. Violations are blocking review issues. If a genuine architecture need requires crossing a boundary, it must be discussed as a team, documented in [`architecture/DECISIONS.md`](architecture/DECISIONS.md), and the rules updated accordingly.

---

## The Shared Contracts

These four files are the foundation every developer builds on. They are treated as stable after Phase 1. Any modification requires a team PR review and a new ADR entry.

| Contract | File | What it defines |
|---|---|---|
| `BaseConnector` | `app/connectors/base.py` | The interface every connector implements |
| `ConnectorResult` | `app/connectors/models.py` | The standard output of every connector |
| `WorkContext` | `app/context_builder/models.py` | The unified payload sent to IBM Bob |
| `TokenRepository` | `app/auth/repository.py` | The abstract interface for token storage |

---

## The Dependency Direction

```
Domain Contracts (most stable — never change these lightly)
        ↑
Application Services  (AuthService, ContextBuilder, BobService)
        ↑
Connectors  (Outlook, Slack, GitHub — one package each)
        ↑
Presentation  (Routers, HTTP response models)
```

**Arrows point toward what a module depends on.** Inner layers know nothing about outer layers. `WorkContext` does not know that FastAPI exists. `BaseConnector` does not know that Microsoft Graph exists.

---

## Documentation Rule

Whenever the architecture changes — a new layer is added, a shared contract is modified, a new connector pattern is established — the relevant documentation must be updated in the same PR. Code changes and documentation changes are a single atomic unit of work.

---

*These rules are enforced through code review. Questions or proposed exceptions must be raised as a team discussion before implementation.*

*Next: read [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) to understand the system design.*

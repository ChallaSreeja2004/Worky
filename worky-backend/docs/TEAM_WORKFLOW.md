# Worky — Team Workflow

> **Purpose:** Explain how multiple developers collaborate on the Worky backend in parallel — each building independent connectors without blocking each other, while the shared contracts keep everything cohesive.
> **Audience:** All contributors, including developers joining mid-project.

---

## Table of Contents

1. [The Problem This Solves](#1-the-problem-this-solves)
2. [The Collaboration Model](#2-the-collaboration-model)
3. [The Shared Contract Layer](#3-the-shared-contract-layer)
4. [How Individual Connectors Are Developed](#4-how-individual-connectors-are-developed)
5. [How ConnectorResult Becomes the Integration Point](#5-how-connectorresult-becomes-the-integration-point)
6. [How the Context Builder Aggregates Everything](#6-how-the-context-builder-aggregates-everything)
7. [How IBM Bob Consumes WorkContext](#7-how-ibm-bob-consumes-workcontext)
8. [How the Widget Receives Recommendations](#8-how-the-widget-receives-recommendations)
9. [How to Add a New Connector Without Changing Existing Code](#9-how-to-add-a-new-connector-without-changing-existing-code)
10. [Developer Responsibilities Map](#10-developer-responsibilities-map)
11. [Coordination Points](#11-coordination-points)
12. [Integration Testing Between Connectors](#12-integration-testing-between-connectors)

---

## 1. The Problem This Solves

When multiple developers work on a shared backend without clear contracts, the following problems emerge:

- **Developer A changes Outlook's output format** → Developer B's Context Builder code breaks
- **Developer C adds Slack** → must understand Outlook code to know how to integrate
- **Developer D integrates IBM Bob** → doesn't know what data format to expect until all connectors are "done"
- **All developers block on each other** → the project grinds to a halt

Worky's architecture solves all of these problems by establishing **shared contracts in Phase 1** — before any connector-specific code is written. These contracts define exactly how each piece of the system communicates, allowing every developer to work in parallel.

---

## 2. The Collaboration Model

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1 — Shared Foundation (completed first, by the team together)        │
│                                                                              │
│  BaseConnector   ConnectorResult   WorkContext   TokenRepository             │
│  ─────────────   ───────────────   ───────────   ─────────────────           │
│  The contract    The output        The Bob        The auth storage            │
│  all connectors  all connectors    input          interface                   │
│  must implement  must return       contract                                   │
└──────────────────────────────────────────────────────────────────────────────┘
                               │
                     After Phase 1 completes
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  Outlook Dev   │   │   Slack Dev      │   │  Context Builder  │
│                │   │                  │   │  + Bob Dev        │
│  Implements    │   │  Implements      │   │                   │
│  OutlookConn.  │   │  SlackConnector  │   │  Reads only from  │
│  (BaseConn.)   │   │  (BaseConnector) │   │  BaseConnector    │
│                │   │                  │   │  and WorkContext   │
│  Works         │   │  Works           │   │                   │
│  independently │   │  independently   │   │  Works            │
│                │   │                  │   │  independently    │
└────────────────┘   └──────────────────┘   └──────────────────┘
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                               │
                   Connectors registered in main.py
                               │
                    Full system works end-to-end
```

All three workstreams can proceed in parallel after Phase 1. They are coordinated by the shared contracts, not by runtime dependencies on each other's code.

---

## 3. The Shared Contract Layer

The following files in Phase 1 are the **interface contracts** that all developers depend on. They are treated as stable after Phase 1 completes. Any change to these files requires team discussion and a new entry in `DECISIONS.md`.

| File | Contract |
|---|---|
| `app/connectors/base.py` | Every connector implements `BaseConnector` with `source_name`, `get_context()`, `health_check()` |
| `app/connectors/models.py` | Every connector returns `ConnectorResult` from `get_context()` |
| `app/context_builder/models.py` | IBM Bob receives a `WorkContext` assembled from `ConnectorResult` objects |
| `app/auth/repository.py` | Token storage is behind a `TokenRepository` interface |

**Rule:** No developer modifies these files without a team PR review and discussion. These are the contracts. Unilateral changes break teammates.

---

## 4. How Individual Connectors Are Developed

Every connector developer follows the same process, independently:

### Step 1 — Read the shared contracts
Before writing a single line, read:
- `app/connectors/base.py` — understand what methods you must implement
- `app/connectors/models.py` — understand the output format you must return
- `docs/CONNECTOR_GUIDE.md` — the step-by-step implementation guide

### Step 2 — Create the connector package
```bash
mkdir -p app/connectors/slack/fetchers
touch app/connectors/slack/__init__.py
touch app/connectors/slack/settings.py
touch app/connectors/slack/slack_client.py
touch app/connectors/slack/fetchers/__init__.py
touch app/connectors/slack/fetchers/messages.py
touch app/connectors/slack/fetchers/mentions.py
touch app/connectors/slack/normalizer.py
touch app/connectors/slack/models.py
touch app/connectors/slack/connector.py
touch app/connectors/slack/router.py
```

### Step 3 — Implement in order
1. `settings.py` — connector-specific env vars
2. `<name>_client.py` — raw HTTP client
3. `fetchers/` — one file per data type
4. `models.py` — connector-specific Pydantic schemas
5. `normalizer.py` — raw JSON → typed models
6. `connector.py` — orchestrate everything, return `ConnectorResult`

### Step 4 — Write tests alongside each file
Never leave testing until the end. Write tests for each file as you finish it.

### Step 5 — Register in main.py
Add your connector to the DI registry. This is the only line in the entire codebase that needs to change outside your connector's package.

### Step 6 — Open a PR following CONTRIBUTING.md

At no point do you need to understand how another connector works. You only need to understand the shared contracts (Step 1).

---

## 5. How ConnectorResult Becomes the Integration Point

`ConnectorResult` is the handshake between connector developers and the Context Builder developer. Its shape is fixed in Phase 1 and never changes.

**From the connector developer's perspective:**
```python
# You always return one of these three:
return ConnectorResult.success(source="slack", data=slack_context.model_dump())
return ConnectorResult.partial(source="slack", data=data, errors=["mentions failed"])
return ConnectorResult.failed(source="slack", errors=["auth error"])
```

**From the Context Builder developer's perspective:**
```python
# You always receive ConnectorResult objects — regardless of which connector
for result in connector_results:
    if result.is_usable:
        sources[result.source] = result.data
```

The Context Builder developer does not need to read a single line of connector code. They only depend on `ConnectorResult`.

---

## 6. How the Context Builder Aggregates Everything

Once all connectors are registered, the Context Builder runs them all concurrently and assembles the result into a `WorkContext`.

```python
# app/context_builder/builder.py

class ContextBuilder:

    def __init__(self, connectors: list[BaseConnector]) -> None:
        self._connectors = connectors      # Injected — not hardcoded

    async def build(self, user_id: str, access_token: str) -> WorkContext:
        start = time.monotonic()

        # All connectors run in parallel
        results = await asyncio.gather(
            *[c.get_context(user_id, access_token) for c in self._connectors],
            return_exceptions=False,   # Each connector handles its own exceptions
        )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        return WorkContext.from_connector_results(
            user_id=user_id,
            results=list(results),
            metadata={"assembly_duration_ms": elapsed_ms},
        )
```

**The Context Builder never imports `OutlookConnector` or `SlackConnector` directly.** It holds `list[BaseConnector]`. The actual connectors are injected in `main.py`.

### Registering connectors in main.py

```python
# main.py — the only file that knows about concrete connectors

from app.connectors.outlook.connector import OutlookConnector
from app.connectors.slack.connector import SlackConnector
from app.context_builder.builder import ContextBuilder

context_builder = ContextBuilder(
    connectors=[
        OutlookConnector(),
        SlackConnector(),
        # GitHubConnector(),     ← add future connectors here
    ]
)
```

Adding a new connector is adding one line here. No other file changes.

---

## 7. How IBM Bob Consumes WorkContext

IBM Bob is completely isolated from connector implementations. It receives one object (`WorkContext`) and returns one object (`RecommendationSet`).

```
WorkContext received by Bob:
{
  "user_id": "user-123",
  "assembled_at": "2025-07-10T09:10:00Z",
  "sources": {
    "outlook": {
      "calendar_events": [
        {"subject": "Team Standup", "start": "2025-07-10T09:30:00Z", ...}
      ],
      "emails": [
        {"subject": "Q3 Review", "importance": "high", "is_read": false, ...}
      ]
    },
    "slack": {
      "mentions": [
        {"text": "@you can you review PR #42?", "sender_name": "Alice", ...}
      ]
    }
  },
  "active_sources": ["outlook", "slack"],
  "connector_summaries": [
    {"source": "outlook", "status": "success", "error_count": 0},
    {"source": "slack",   "status": "success", "error_count": 0}
  ]
}
```

Bob uses `active_sources` to know which enterprise applications are available. Bob uses `connector_summaries` to understand data quality. Bob uses `sources` to find the actual data and reason about priorities.

Bob's response is a `RecommendationSet` — an ordered list of `Recommendation` objects with priority, category, title, description, and action URL.

---

## 8. How the Widget Receives Recommendations

The desktop widget calls exactly one endpoint:

```
GET /api/v1/recommendations
Authorization: Bearer <user-access-token>
```

It receives:
```json
{
  "user_id": "user-123",
  "generated_at": "2025-07-10T09:10:00Z",
  "recommendations": [
    {
      "priority": 1,
      "category": "meeting",
      "title": "Standup in 12 minutes",
      "description": "Team Standup at 9:30 AM — no preparation materials found",
      "source": "outlook"
    },
    {
      "priority": 2,
      "category": "email",
      "title": "High-priority email requires response",
      "description": "Q3 Review from your manager — marked high importance, unread",
      "source": "outlook"
    },
    {
      "priority": 3,
      "category": "review_request",
      "title": "You were asked to review PR #42",
      "description": "Alice: @you can you review PR #42? — 2 hours ago",
      "source": "slack"
    }
  ],
  "context_freshness": "2025-07-10T09:10:00Z"
}
```

The widget developer needs to understand:
1. This single endpoint
2. The `RecommendationResponse` Pydantic model (in `app/recommendations/models.py`)

Nothing else.

---

## 9. How to Add a New Connector Without Changing Existing Code

This is the ultimate test of the architecture. Adding a GitHub connector must require zero changes to Outlook, Slack, the Context Builder, or IBM Bob.

### What you change

| File | Change |
|---|---|
| `app/connectors/github/` | Create the entire connector package (new files) |
| `main.py` | Add `GitHubConnector()` to the connectors list |
| `.env.example` | Add a `GitHubSettings` section |
| `docs/ROADMAP.md` | Update phase status |

### What you do NOT change

| File | Why untouched |
|---|---|
| `app/connectors/base.py` | `GitHubConnector` implements the existing interface |
| `app/connectors/models.py` | `ConnectorResult` is generic — no GitHub-specific fields needed |
| `app/context_builder/models.py` | `WorkContext.sources` is a dict — GitHub data drops in as `sources["github"]` |
| `app/context_builder/builder.py` | The builder iterates `list[BaseConnector]` — GitHub is just another entry |
| `app/connectors/outlook/` | Completely untouched |
| `app/connectors/slack/` | Completely untouched |
| `app/bob/` | Bob receives `WorkContext` — the new `"github"` key in `sources` is automatically available |

This is the Open/Closed Principle in practice: **open for extension, closed for modification**.

---

## 10. Developer Responsibilities Map

| Developer | Owns | Depends on | Must NOT touch |
|---|---|---|---|
| Outlook Dev | `app/connectors/outlook/` · `app/auth/service.py` · `app/auth/router.py` | Shared contracts | `app/connectors/slack/` · `context_builder/builder.py` · `bob/` |
| Slack Dev | `app/connectors/slack/` | Shared contracts + Outlook as reference | `app/connectors/outlook/` · `context_builder/builder.py` · `bob/` |
| Context Builder Dev | `app/context_builder/builder.py` | `BaseConnector` · `ConnectorResult` · `WorkContext` | Any connector sub-package |
| Bob Dev | `app/bob/service.py` · `app/bob/models.py` | `WorkContext` | Any connector sub-package |
| Recommendations Dev | `app/recommendations/` | `BobService` · `RecommendationSet` | Connector internals |
| All Devs | Shared contracts (read-only) | Python stdlib · Pydantic | Shared contracts (write requires team PR) |

---

## 11. Coordination Points

These are the only moments where developers need to coordinate with each other:

### 1. Before Phase 1 ends
Agree on the `WorkContext` schema. Once IBM Bob is integrated, changing `WorkContext` is a versioned API change. Discuss field naming, required vs. optional fields, and the `sources` dict structure with the team before finalizing.

### 2. When registering a new connector in `main.py`
Adding a connector to the DI list in `main.py` may conflict with another developer working on the same file. Coordinate to avoid merge conflicts: agree on who merges first or use a separate PR for connector registration.

### 3. When the `source_name` of a connector is set
The `source_name` is the key used in `WorkContext.sources` and in Bob's prompts. Agree on the canonical name before deployment. Renaming after deployment breaks WorkContext compatibility.

### 4. When a shared contract needs to change
Open a PR, tag all contributors as reviewers, and document the decision in `DECISIONS.md`. Never merge a shared contract change with a single approval.

---

## 12. Integration Testing Between Connectors

Full integration testing requires all connectors to be registered and running. The recommended approach:

### Use MockConnectors in integration tests

```python
# tests/conftest.py

class MockOutlookConnector(BaseConnector):
    @property
    def source_name(self) -> str:
        return "outlook"

    async def get_context(self, user_id, access_token) -> ConnectorResult:
        return ConnectorResult.success(
            source="outlook",
            data={"calendar_events": [], "emails": []}
        )

    async def health_check(self) -> bool:
        return True


class MockSlackConnector(BaseConnector):
    @property
    def source_name(self) -> str:
        return "slack"

    async def get_context(self, user_id, access_token) -> ConnectorResult:
        return ConnectorResult.success(
            source="slack",
            data={"mentions": [], "unread_messages": []}
        )

    async def health_check(self) -> bool:
        return True
```

These mocks implement `BaseConnector` exactly as real connectors do. They can be injected into `ContextBuilder` to test the full pipeline without real API credentials.

```python
async def test_context_builder_aggregates_all_sources():
    builder = ContextBuilder(connectors=[
        MockOutlookConnector(),
        MockSlackConnector(),
    ])
    work_context = await builder.build(user_id="u1", access_token="fake")

    assert "outlook" in work_context.sources
    assert "slack" in work_context.sources
    assert work_context.total_connectors == 2
    assert work_context.successful_connectors == 2
```

This test is completely self-contained — no real Microsoft Graph, no real Slack API, no IBM Bob credentials required.

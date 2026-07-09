# Worky — Intelligent Desktop Companion

> **Powered by IBM Bob** · Reduce context switching · Surface priorities · Stay in flow

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [How Worky Works](#how-worky-works)
- [Features](#features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Core Components](#core-components)
- [Current Development Status](#current-development-status)
- [Development Roadmap](#development-roadmap)
- [Team Responsibilities](#team-responsibilities)
- [Setup Instructions](#setup-instructions)
- [Future Scope](#future-scope)
- [Documentation Reading Order](#documentation-reading-order)

---

## Problem Statement

Modern enterprise employees use between 6 and 10 applications every single working day — Outlook, Slack, GitHub, Jira, Confluence, Calendar, and more. To understand their current workload, they must manually open each application, scan for updates, mentally integrate the information, and decide what to do next.

This constant context switching carries a measurable cost:

- **Missed priorities** — a high-importance email buried under 40 unread messages
- **Delayed responses** — a pull request review request sitting unnoticed in GitHub
- **Forgotten deadlines** — a Jira ticket due today with no reminder
- **Meeting conflicts** — a calendar event clashing with a blocked focus period
- **Cognitive overload** — the mental effort of aggregating information across tools

There is no single place that tells an employee: *"Here is what matters most right now."*

---

## Solution Overview

Worky is a lightweight intelligent desktop companion that runs quietly in the background. Once installed and connected to enterprise applications, it continuously gathers work context, sends it to IBM Bob for reasoning, and surfaces personalized, prioritized recommendations directly on the desktop — without requiring the employee to open a single application.

**Worky is proactive, not reactive.** It does not wait for the user to search. It surfaces what matters before the user realizes they need it.

```
 ┌────────────────────────────────────────────────────────────────┐
 │                      Desktop Widget                           │
 │    "You have a standup in 12 minutes. 3 unreviewed PRs.       │
 │     High-priority email from your manager about Q3 review."   │
 └────────────────────────────────────────────────────────────────┘
                              ▲
                    IBM Bob Recommendations
                              ▲
           Unified Work Context (all sources combined)
                              ▲
    Outlook ── Slack ── GitHub ── Jira ── Confluence ── Calendar
```

---

## How Worky Works

This is the runtime flow from the moment an employee logs in to the moment the Desktop Widget updates.

```
  Employee signs in
        │
        ▼
  Authentication (OAuth 2.0 + PKCE)
        │  access_token issued
        ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  SCHEDULED PIPELINE  (every 5 minutes)                         │
  │                                                                 │
  │  Enterprise Connectors  (run concurrently)                     │
  │    Outlook ──── calendar events, unread emails                 │
  │    Slack ─────── unread messages, mentions                     │
  │    GitHub ─────── open PRs, review requests     [future]       │
  │    Jira ───────── overdue tickets, blockers     [future]       │
  │         │                                                       │
  │         ▼  ConnectorResult (per connector)                     │
  │  Context Builder                                               │
  │    assembles all ConnectorResults → WorkContext                │
  │         │                                                       │
  │         ▼  WorkContext (single unified payload)                │
  │  IBM Bob                                                       │
  │    reasons across all data → RecommendationSet                 │
  │         │                                                       │
  │         ▼  RecommendationSet                                   │
  │  Recommendation Cache  (TTL: 5 minutes)                        │
  └─────────────────────────────────────────────────────────────────┘
        │
        ▼
  Desktop Widget polls  GET /api/v1/recommendations  (every 60 s)
        │  reads from cache — always instant
        ▼
  Widget displays prioritized recommendations
```

**Key design insight:** IBM Bob is called on a schedule, not on every widget poll. The widget always reads from the cache — instant response regardless of how many connectors are active.

---

## Features

| Feature | Description |
|---|---|
| **Unified Work Context** | Aggregates data from all connected enterprise applications into a single normalized payload |
| **AI-Powered Prioritization** | IBM Bob analyzes the work context and identifies the most important actions |
| **Real-Time Recommendations** | Personalized, timestamped action recommendations refreshed every 5 minutes |
| **Calendar Awareness** | Surfaces upcoming meetings, conflicts, and preparation time needed |
| **Email Intelligence** | Identifies high-importance emails and unread messages requiring urgent attention |
| **Extensible Connector Architecture** | New enterprise applications can be added without changing existing code |
| **Secure OAuth Integration** | Each connector authenticates using the enterprise application's own OAuth provider |
| **Desktop Widget** | Always-visible lightweight widget requiring zero manual navigation |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Desktop Widget                                │
│                  (Electron + React — always visible)                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  GET /api/v1/recommendations
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Worky Backend  (FastAPI)                              │
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐   │
│  │ Auth Service │   │  Connectors  │   │   Recommendation Service │   │
│  │  OAuth PKCE  │   │  (per app)   │   │   (widget-facing API)    │   │
│  └──────────────┘   └──────┬───────┘   └──────────────────────────┘   │
│                            │                          ▲                 │
│            ┌───────────────┼───────────────┐          │                 │
│            ▼               ▼               ▼          │                 │
│        Outlook          Slack           GitHub    RecommendationSet     │
│        Connector        Connector       Connector      ▲                │
│            └───────────────┴───────────────┘          │                │
│                            │                          │                 │
│                            ▼                          │                 │
│               ┌────────────────────────┐              │                 │
│               │     Context Builder    │              │                 │
│               │  WorkContext assembly  │              │                 │
│               └────────────┬───────────┘              │                 │
│                            │                          │                 │
│                            ▼                          │                 │
│               ┌────────────────────────┐              │                 │
│               │      IBM Bob           ├──────────────┘                 │
│               │   Reasoning Engine     │                                │
│               └────────────────────────┘                                │
└─────────────────────────────────────────────────────────────────────────┘
```

Full architecture documentation: [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md)

---

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend API | FastAPI (Python) | Async-first, automatic OpenAPI docs, Pydantic integration |
| Data Validation | Pydantic v2 | Runtime type safety, schema-as-code, clean serialization |
| Desktop Application | Electron + React | Cross-platform, native OS integration, web-based UI |
| AI Reasoning Engine | IBM Bob | Enterprise-grade AI, context-aware recommendations |
| Outlook Integration | Microsoft Graph API | Official, feature-complete, OAuth 2.0 delegated access |
| Authentication | OAuth 2.0 + PKCE | Secure delegated auth without client secrets in binaries |
| Database | MongoDB (planned) | Flexible document store for token persistence and caching |
| Cache | Redis (planned) | Token storage across workers, recommendation TTL cache |
| HTTP Client | httpx | Native async, connection pooling, retry support |

---

## Repository Structure

```
worky-backend/
│
├── main.py                          # FastAPI application entry point
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variable template
│
├── app/
│   ├── config/
│   │   └── settings.py              # Global AppSettings
│   │
│   ├── auth/
│   │   ├── models.py                # TokenData, AuthorizationResponse
│   │   ├── repository.py            # TokenRepository interface + InMemoryImpl
│   │   ├── service.py               # OAuth PKCE flow (Phase 2)
│   │   └── router.py                # /api/v1/auth/* endpoints (Phase 2)
│   │
│   ├── connectors/
│   │   ├── base.py                  # BaseConnector ABC + exception hierarchy
│   │   ├── models.py                # ConnectorResult, ConnectorStatus
│   │   │
│   │   ├── outlook/                 # Outlook connector (Phase 3–7)
│   │   │   ├── settings.py
│   │   │   ├── connector.py
│   │   │   ├── graph_client.py
│   │   │   ├── fetchers/
│   │   │   │   ├── calendar.py
│   │   │   │   └── email.py
│   │   │   ├── normalizer.py
│   │   │   ├── models.py
│   │   │   └── router.py
│   │   │
│   │   └── slack/                   # Slack connector (Phase 8)
│   │       └── ...
│   │
│   ├── context_builder/
│   │   ├── models.py                # WorkContext, ConnectorSummary
│   │   └── builder.py               # ContextBuilder (Phase 9)
│   │
│   ├── bob/
│   │   ├── service.py               # BobService interface (Phase 10)
│   │   ├── mock_service.py          # MockBobService for dev
│   │   └── models.py                # BobRequest, RecommendationSet
│   │
│   └── recommendations/
│       ├── router.py                # Widget-facing API (Phase 11)
│       └── models.py                # RecommendationResponse
│
├── tests/
│   ├── conftest.py
│   └── connectors/
│       └── outlook/
│
└── docs/
    ├── README.md                    # ← You are here
    ├── TEAM_RULES.md                # Non-negotiable engineering rules (read first)
    ├── IMPLEMENTATION_CHECKLIST.md  # Phase-by-phase progress tracker
    ├── architecture/
    │   ├── ARCHITECTURE.md          # System design, layers, data flow
    │   └── DECISIONS.md             # Architecture Decision Records (ADRs)
    ├── development/
    │   ├── CONNECTOR_GUIDE.md       # How to implement a connector
    │   ├── CONTRIBUTING.md          # Engineering standards, PR process
    │   └── GIT_WORKFLOW.md          # Branch strategy, commits, releases
    ├── planning/
    │   ├── ROADMAP.md               # Implementation phases and milestones
    │   └── TEAM_WORKFLOW.md         # Parallel development collaboration model
    ├── reference/
    │   └── REPOSITORY_STRUCTURE.md  # Every folder and file explained
    └── templates/
        └── CONNECTOR_TEMPLATE.md    # Copy-paste connector blueprint
```

Full structure documentation: [`reference/REPOSITORY_STRUCTURE.md`](reference/REPOSITORY_STRUCTURE.md)

---

## Core Components

### BaseConnector
Abstract interface that every enterprise connector must implement. Defines `get_context(user_id, access_token) → ConnectorResult`. The Context Builder depends only on this abstraction.
→ [`app/connectors/base.py`](../app/connectors/base.py) · See [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md#4-connector-architecture)

### ConnectorResult
Standard output of every connector. Contains normalized data, status (SUCCESS / PARTIAL / FAILED), errors, and observability metadata.
→ [`app/connectors/models.py`](../app/connectors/models.py)

### WorkContext
The unified payload assembled by the Context Builder and sent to IBM Bob. IBM Bob's only input.
→ [`app/context_builder/models.py`](../app/context_builder/models.py)

### TokenRepository
Abstract interface for OAuth token persistence. Development uses `InMemoryTokenRepository`; production uses `RedisTokenRepository`.
→ [`app/auth/repository.py`](../app/auth/repository.py)

---

## Current Development Status

| Component | Status | Owner |
|---|---|---|
| Project structure | ✅ Complete | Team |
| AppSettings | ✅ Complete | Team |
| BaseConnector | ✅ Complete | Team |
| ConnectorResult | ✅ Complete | Team |
| WorkContext | ✅ Complete | Team |
| TokenRepository | ✅ Complete | Team |
| Auth Service (OAuth PKCE) | 🔄 In Progress | Outlook Dev |
| Microsoft Graph Client | 🔄 In Progress | Outlook Dev |
| Outlook Connector | 🔄 In Progress | Outlook Dev |
| Slack Connector | 📋 Planned | Slack Dev |
| Context Builder | 📋 Planned | Team |
| IBM Bob Integration | 📋 Planned | Team |
| Recommendation Service | 📋 Planned | Team |
| Desktop Widget | 📋 Planned | Team |

---

## Development Roadmap

| Phase | Milestone | Status |
|---|---|---|
| Phase 1 | Project Foundation | ✅ Complete |
| Phase 2 | Outlook Authentication | 🔄 Next |
| Phase 3 | Microsoft Graph Client | 📋 Planned |
| Phase 4 | Calendar Fetcher | 📋 Planned |
| Phase 5 | Email Fetcher | 📋 Planned |
| Phase 6 | Normalizer | 📋 Planned |
| Phase 7 | Outlook Connector | 📋 Planned |
| Phase 8 | Slack Connector | 📋 Planned |
| Phase 9 | Context Builder | 📋 Planned |
| Phase 10 | IBM Bob Integration | 📋 Planned |
| Phase 11 | Recommendation Service | 📋 Planned |
| Phase 12 | Desktop Widget Integration | 📋 Planned |
| Phase 13 | Production Hardening | 📋 Planned |

Full roadmap: [`ROADMAP.md`](ROADMAP.md)

---

## Team Responsibilities

| Developer | Responsibility |
|---|---|
| Outlook Developer | Auth service · Microsoft Graph client · Calendar fetcher · Email fetcher · Normalizer · Outlook connector |
| Slack Developer | Slack OAuth · Slack API client · Message fetcher · Mention fetcher · Slack connector |
| Future Developers | GitHub / Jira / Confluence / Calendar connectors using the same BaseConnector pattern |
| Team | Context Builder · IBM Bob integration · Recommendation Service · Widget API |

Full collaboration guide: [`planning/TEAM_WORKFLOW.md`](planning/TEAM_WORKFLOW.md)

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- pip
- A `.env` file populated from `.env.example`

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/worky-backend.git
cd worky-backend

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and fill in all required values

# 5. Start the development server
uvicorn main:app --reload --port 8000

# 6. Open API documentation
# http://localhost:8000/docs
```

### Generate a token encryption key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output as `TOKEN_ENCRYPTION_KEY` in your `.env` file.

---

## Future Scope

- **Additional connectors** — GitHub (open PRs, review requests), Jira (overdue tickets, blockers), Confluence (relevant pages), Calendar (meeting prep)
- **Proactive notifications** — push recommendations to the widget without polling
- **User preference learning** — Bob adapts recommendations based on feedback signals
- **Team-level context** — aggregate context across a team to surface cross-team blockers
- **Mobile companion** — extend the widget to iOS and Android
- **Offline mode** — serve cached recommendations when enterprise APIs are unreachable
- **Multi-tenant deployment** — enterprise-wide deployment with per-tenant connector configurations

---

## Documentation Reading Order

**New to the project? Read in this order:**

| Step | Document | Purpose |
|---|---|---|
| 1 | [`README.md`](README.md) | Project overview, setup, status — you are here |
| 2 | [`TEAM_RULES.md`](TEAM_RULES.md) | The 10 non-negotiable engineering rules |
| 3 | [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) | How the system is structured and why |
| 4 | [`development/CONNECTOR_GUIDE.md`](development/CONNECTOR_GUIDE.md) | How to implement a connector |
| 5 | [`templates/CONNECTOR_TEMPLATE.md`](templates/CONNECTOR_TEMPLATE.md) | Blueprint to copy when starting your connector |
| 6 | [`planning/ROADMAP.md`](planning/ROADMAP.md) | What is built, what is next, what you own |
| 7 | [`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md) | Your phase-by-phase task tracker |
| 8 | Begin implementation | |

**Reference documents** (read when you need them, not upfront):

| Document | When to read it |
|---|---|
| [`architecture/DECISIONS.md`](architecture/DECISIONS.md) | When you want to understand *why* a design decision was made |
| [`development/CONTRIBUTING.md`](development/CONTRIBUTING.md) | Before opening your first PR |
| [`development/GIT_WORKFLOW.md`](development/GIT_WORKFLOW.md) | When creating branches, commits, or releases |
| [`planning/TEAM_WORKFLOW.md`](planning/TEAM_WORKFLOW.md) | When coordinating with teammates |
| [`reference/REPOSITORY_STRUCTURE.md`](reference/REPOSITORY_STRUCTURE.md) | When you need to know where something lives |

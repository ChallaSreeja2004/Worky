# Worky — Connector Developer Guide

> **Audience:** Any developer implementing a new enterprise connector (Slack, GitHub, Jira, Confluence, Calendar, or future integrations).
> **Purpose:** A complete explanation of the connector pattern — what connectors are, how they are structured, how they plug into the rest of the system, and how to implement one correctly.
> **Blueprint:** For a copy-paste template, use [`../templates/CONNECTOR_TEMPLATE.md`](../templates/CONNECTOR_TEMPLATE.md).

---

## Table of Contents

1. [What is a Connector?](#1-what-is-a-connector)
2. [Where Connectors Fit in the System](#2-where-connectors-fit-in-the-system)
3. [Connector Lifecycle](#3-connector-lifecycle)
4. [Folder Structure](#4-folder-structure)
5. [File Responsibilities](#5-file-responsibilities)
6. [Step 1 — Settings](#6-step-1--settings)
7. [Step 2 — API Client](#7-step-2--api-client)
8. [Step 3 — Fetchers](#8-step-3--fetchers)
9. [Step 4 — Models](#9-step-4--models)
10. [Step 5 — Normalizer](#10-step-5--normalizer)
11. [Step 6 — Connector](#11-step-6--connector)
12. [Step 7 — Router (Optional)](#12-step-7--router-optional)
13. [ConnectorResult Reference](#13-connectorresult-reference)
14. [Authentication Pattern](#14-authentication-pattern)
15. [Error Handling](#15-error-handling)
16. [Naming Conventions](#16-naming-conventions)
17. [Design Rules](#17-design-rules)
18. [Common Mistakes](#18-common-mistakes)
19. [Testing Recommendations](#19-testing-recommendations)
20. [Checklist](#20-checklist)

---

## 1. What is a Connector?

A connector is a self-contained Python package that is responsible for **collecting structured data from exactly one enterprise application** and returning it as a `ConnectorResult`.

A connector does **one thing**. It does not:
- Communicate with IBM Bob
- Call another connector
- Send data to the Desktop Widget
- Manage user tokens (the AuthService does this)
- Store application state

Once a connector returns its `ConnectorResult`, its job is complete. The Context Builder, IBM Bob, and the Recommendation Service handle everything after that.

---

## 2. Where Connectors Fit in the System

A connector is one plugin in a larger pipeline. Understanding this pipeline is essential before writing a single line of connector code.

```
  Connector.get_context(user_id, access_token)
        │
        ▼  ConnectorResult  ─────────────────────────────────────────┐
                                                                      │
  Context Builder                                                     │
    collects ConnectorResult from all registered connectors          │
        │                                                             │
        ▼  WorkContext  (all sources aggregated)                      │
                                                                      │
  IBM Bob                                                             │
    analyzes WorkContext → RecommendationSet                          │
        │                                                             │
        ▼  RecommendationSet → cached                                 │
                                                                      │
  Recommendation Service                                              │
    serves GET /api/v1/recommendations                               │
        │                                                             │
        ▼                                                             │
  Desktop Widget displays recommendations  ◄────────────────────────┘
```

**Your connector is responsible for exactly one vertical slice of this diagram:** the `ConnectorResult` it produces. Everything to the right of that arrow is owned by other layers. You never need to understand the Bob integration to build a great connector.

---

## 3. Connector Lifecycle

Every time the Context Builder runs (every 5 minutes), each registered connector goes through this lifecycle:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CONNECTOR LIFECYCLE — one execution cycle                             │
│                                                                         │
│  1. Context Builder calls:                                             │
│       connector.get_context(user_id, access_token)                     │
│                                                                         │
│  2. Connector calls its fetchers concurrently:                         │
│       fetcher_a.fetch(access_token)  → raw API response                │
│       fetcher_b.fetch(access_token)  → raw API response                │
│                                                                         │
│  3. Connector passes raw responses to Normalizer:                      │
│       normalizer.normalize(raw_a, raw_b)  → typed Pydantic model       │
│                                                                         │
│  4. Connector wraps result:                                            │
│       ConnectorResult.success(source, data)                            │
│       ConnectorResult.partial(source, data, errors)   ← if some failed │
│       ConnectorResult.failed(source, errors)          ← if all failed  │
│                                                                         │
│  5. Context Builder receives ConnectorResult                           │
│       → Adds to WorkContext                                            │
│       → WorkContext sent to IBM Bob                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Folder Structure

Every connector follows this identical structure. Replace `<name>` with your connector's lowercase identifier (e.g., `slack`, `github`, `jira`).

```
app/connectors/<name>/
├── __init__.py
├── settings.py          # Connector-specific environment variables
├── connector.py         # <Name>Connector(BaseConnector) — the orchestrator
├── <name>_client.py     # Raw HTTP client — all API calls live here
├── fetchers/
│   ├── __init__.py
│   ├── <entity_a>.py    # One fetcher per data type (messages, mentions, PRs …)
│   └── <entity_b>.py
├── normalizer.py        # Maps raw API JSON → typed Pydantic models
├── models.py            # Connector-specific Pydantic schemas
└── router.py            # Optional: debug endpoint
```

### Example — Slack connector

```
app/connectors/slack/
├── __init__.py
├── settings.py
├── connector.py         # SlackConnector(BaseConnector)
├── slack_client.py      # SlackAPIClient
├── fetchers/
│   ├── __init__.py
│   ├── messages.py      # UnreadMessagesFetcher
│   └── mentions.py      # MentionsFetcher
├── normalizer.py        # SlackNormalizer
├── models.py            # SlackMessage, SlackMention, SlackContext
└── router.py
```

---

## 4. File Responsibilities

| File | Owns | Does NOT own |
|---|---|---|
| `settings.py` | Env vars for this connector (client ID, scopes, base URL) | App-level settings (log level, API prefix) |
| `<name>_client.py` | All raw HTTP calls to the enterprise API | Business logic, normalization, error routing |
| `fetchers/<entity>.py` | Calling the API client for one data type | HTTP logic, normalization |
| `normalizer.py` | Mapping raw API JSON → typed Pydantic models | HTTP calls, error handling |
| `models.py` | Connector-specific Pydantic schemas | Shared contracts (ConnectorResult, WorkContext) |
| `connector.py` | Orchestrating fetchers + normalizer, returning ConnectorResult | HTTP calls, normalization logic |
| `router.py` | Optional debug HTTP endpoint | Business logic |

---

## 5. Step 1 — Settings

Create `app/connectors/<name>/settings.py`. This class holds every environment variable your connector needs. It must NOT add variables to `AppSettings` in `app/config/settings.py`.

```python
# app/connectors/slack/settings.py

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackSettings(BaseSettings):
    """Slack-specific configuration. All values come from environment variables."""

    # Slack OAuth App credentials
    slack_client_id: str
    slack_client_secret: str
    slack_redirect_uri: str = "http://localhost:8000/api/v1/auth/slack/callback"

    # Slack API
    slack_api_base_url: str = "https://slack.com/api"

    @property
    def oauth_scopes(self) -> list[str]:
        """Delegated scopes required by the Slack connector."""
        return ["channels:history", "channels:read", "users:read"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_slack_settings() -> SlackSettings:
    return SlackSettings()
```

Add the variables to `.env.example` under a clearly labeled section:

```ini
# SlackSettings (app/connectors/slack/settings.py)
# SLACK_CLIENT_ID=your-slack-app-client-id
# SLACK_CLIENT_SECRET=your-slack-app-client-secret
```

---

## 6. Step 2 — API Client

Create `app/connectors/<name>/<name>_client.py`. This is the **only file in your connector that calls `httpx`** (or any HTTP library). All raw HTTP calls live here and nowhere else.

The API client:
- Accepts an `access_token` in its constructor or per-method
- Provides one async method per API call
- Returns the raw parsed JSON dictionary — no transformation
- Raises `httpx.HTTPStatusError` on non-2xx responses (let the fetcher handle it)
- Implements retry logic for transient errors (429, 503)

```python
# app/connectors/slack/slack_client.py

import httpx
from app.connectors.slack.settings import get_slack_settings


class SlackAPIClient:
    """
    Thin HTTP wrapper for the Slack Web API.

    All httpx calls in the Slack connector live here.
    Fetchers call this client — they never import httpx directly.
    This makes fetchers testable with a mock client.
    """

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._base_url = get_slack_settings().slack_api_base_url
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def get_conversations_history(
        self,
        channel_id: str,
        limit: int = 20,
    ) -> dict:
        """
        Fetch recent messages from a Slack channel.
        https://api.slack.com/methods/conversations.history
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/conversations.history",
                headers=self._headers,
                params={"channel": channel_id, "limit": limit},
            )
            response.raise_for_status()
            return response.json()

    async def get_user_mentions(self) -> dict:
        """
        Search for messages where the user was mentioned.
        https://api.slack.com/methods/search.messages
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/search.messages",
                headers=self._headers,
                params={"query": "<@me>", "sort": "timestamp"},
            )
            response.raise_for_status()
            return response.json()
```

**Key rules:**
- The client knows nothing about `ConnectorResult`, `WorkContext`, or normalization
- If the API returns paginated results, pagination logic lives in the client
- Add a `ping()` method that makes a lightweight API call for health checks

---

## 7. Step 3 — Fetchers

Create one fetcher per data type under `app/connectors/<name>/fetchers/`. A fetcher calls the API client and returns raw data. It does not normalize.

```python
# app/connectors/slack/fetchers/mentions.py

import logging
from app.connectors.slack.slack_client import SlackAPIClient

logger = logging.getLogger(__name__)


class MentionsFetcher:
    """
    Fetches messages where the authenticated user was mentioned in Slack.

    Responsibilities:
      - Call SlackAPIClient.get_user_mentions()
      - Return the raw API response
      - Raise on unrecoverable errors; return empty list on empty results

    Does NOT:
      - Normalize or transform the response
      - Call httpx directly
      - Know about ConnectorResult or WorkContext
    """

    def __init__(self, client: SlackAPIClient) -> None:
        self._client = client

    async def fetch(self) -> list[dict]:
        """
        Fetch all messages where the user was mentioned today.

        Returns
        -------
        list[dict]
            List of raw Slack message objects.  Empty list if no mentions.

        Raises
        ------
        httpx.HTTPStatusError
            If the Slack API returns a non-2xx response.
        """
        logger.debug("MentionsFetcher: fetching user mentions")
        raw = await self._client.get_user_mentions()
        messages = raw.get("messages", {}).get("matches", [])
        logger.debug("MentionsFetcher: found %d mentions", len(messages))
        return messages
```

**Key rules:**
- Accept the API client as a constructor parameter (not `access_token` directly)
- Return raw data — no Pydantic models, no transformation
- One fetcher = one data type
- Log the count of items fetched at DEBUG level

---

## 8. Step 4 — Models

Define your connector's Pydantic schemas in `app/connectors/<name>/models.py`. These are internal to your connector — they represent the *normalized* shape of your connector's data.

```python
# app/connectors/slack/models.py

from datetime import datetime
from pydantic import BaseModel, Field


class SlackMessage(BaseModel):
    """A single Slack message."""
    message_id: str
    channel_id: str
    sender_id: str
    sender_name: str
    text: str
    timestamp: datetime
    is_mention: bool = False
    permalink: str | None = None


class SlackContext(BaseModel):
    """
    The complete Slack data payload for one user.

    This is the shape of ConnectorResult.data for the Slack connector.
    The Context Builder receives this as a dict; consumers that need typed
    access call SlackContext.model_validate(result.data).
    """
    unread_messages: list[SlackMessage] = Field(default_factory=list)
    mentions: list[SlackMessage] = Field(default_factory=list)
    total_unread: int = 0
    total_mentions: int = 0
```

**Key rules:**
- Models are for *normalized* data, not raw API JSON
- The top-level model (e.g., `SlackContext`) is what gets serialized into `ConnectorResult.data`
- Keep field names domain-appropriate, not API-specific (`sender_name`, not `user_id_string`)

---

## 9. Step 5 — Normalizer

The normalizer maps raw API dictionaries into your typed Pydantic models. It is the translation layer between the enterprise API's language and Worky's language.

```python
# app/connectors/slack/normalizer.py

import logging
from datetime import datetime, timezone
from app.connectors.slack.models import SlackMessage, SlackContext

logger = logging.getLogger(__name__)


class SlackNormalizer:
    """
    Maps raw Slack API responses → typed SlackContext Pydantic model.

    This class contains pure transformation logic only.
    It does not make HTTP calls and does not raise exceptions.
    Missing or malformed fields are handled gracefully with defaults.
    """

    def normalize(
        self,
        raw_messages: list[dict],
        raw_mentions: list[dict],
    ) -> SlackContext:
        """Transform raw Slack API responses into a SlackContext."""
        messages = [self._map_message(m, is_mention=False) for m in raw_messages]
        mentions = [self._map_message(m, is_mention=True)  for m in raw_mentions]

        return SlackContext(
            unread_messages=messages,
            mentions=mentions,
            total_unread=len(messages),
            total_mentions=len(mentions),
        )

    def _map_message(self, raw: dict, is_mention: bool) -> SlackMessage:
        """Map a single raw Slack message dict to a SlackMessage model."""
        ts = raw.get("ts", "0")
        return SlackMessage(
            message_id=ts,
            channel_id=raw.get("channel", {}).get("id", ""),
            sender_id=raw.get("user", ""),
            sender_name=raw.get("username", "Unknown"),
            text=raw.get("text", ""),
            timestamp=datetime.fromtimestamp(float(ts), tz=timezone.utc),
            is_mention=is_mention,
            permalink=raw.get("permalink"),
        )
```

**Key rules:**
- The normalizer is a pure function — no side effects, no I/O
- Never let a missing field crash normalization — use `.get()` with sensible defaults
- This is the easiest layer to unit-test (no mocking needed — pure input/output)

---

## 10. Step 6 — Connector

The connector class is the orchestrator. It ties together the client, fetchers, and normalizer into a single `get_context()` call.

```python
# app/connectors/slack/connector.py

import asyncio
import logging
from app.connectors.base import BaseConnector, ConnectorAuthError
from app.connectors.models import ConnectorResult
from app.connectors.slack.slack_client import SlackAPIClient
from app.connectors.slack.fetchers.messages import MessagesFetcher
from app.connectors.slack.fetchers.mentions import MentionsFetcher
from app.connectors.slack.normalizer import SlackNormalizer

logger = logging.getLogger(__name__)


class SlackConnector(BaseConnector):
    """
    Collects unread messages and mentions from the Slack Web API.

    Implements BaseConnector — the Context Builder calls get_context()
    and receives a ConnectorResult without knowing any implementation detail.
    """

    @property
    def source_name(self) -> str:
        return "slack"

    async def get_context(
        self, user_id: str, access_token: str
    ) -> ConnectorResult:
        logger.info("SlackConnector: starting context collection for user=%s", user_id)

        client = SlackAPIClient(access_token=access_token)
        messages_fetcher = MessagesFetcher(client=client)
        mentions_fetcher = MentionsFetcher(client=client)
        normalizer = SlackNormalizer()

        errors: list[str] = []

        # Run fetchers concurrently
        raw_messages, raw_mentions = await asyncio.gather(
            messages_fetcher.fetch(),
            mentions_fetcher.fetch(),
            return_exceptions=True,
        )

        # Handle partial failures gracefully
        if isinstance(raw_messages, Exception):
            logger.warning("SlackConnector: messages fetch failed: %s", raw_messages)
            errors.append(f"Messages fetch failed: {raw_messages}")
            raw_messages = []

        if isinstance(raw_mentions, Exception):
            logger.warning("SlackConnector: mentions fetch failed: %s", raw_mentions)
            errors.append(f"Mentions fetch failed: {raw_mentions}")
            raw_mentions = []

        # Normalize
        slack_context = normalizer.normalize(
            raw_messages=raw_messages,
            raw_mentions=raw_mentions,
        )

        data = slack_context.model_dump()

        if errors and not data:
            return ConnectorResult.failed(source=self.source_name, errors=errors)
        elif errors:
            return ConnectorResult.partial(source=self.source_name, data=data, errors=errors)
        else:
            return ConnectorResult.success(source=self.source_name, data=data)

    async def health_check(self) -> bool:
        """Verify Slack API is reachable. Returns False on any failure."""
        try:
            # A lightweight call — e.g., api.test
            async with __import__("httpx").AsyncClient() as client:
                response = await client.get("https://slack.com/api/api.test")
                return response.status_code == 200
        except Exception:
            return False
```

---

## 11. Step 7 — Router (Optional)

Add a simple debug router so you can manually trigger context collection during development.

```python
# app/connectors/slack/router.py

from fastapi import APIRouter, Depends
from app.connectors.slack.connector import SlackConnector
from app.connectors.models import ConnectorResult

router = APIRouter()

@router.get("/context", response_model=ConnectorResult)
async def get_slack_context(
    user_id: str,
    access_token: str,
) -> ConnectorResult:
    """Debug endpoint — triggers a single Slack context collection cycle."""
    connector = SlackConnector()
    return await connector.get_context(user_id=user_id, access_token=access_token)
```

Mount it in `main.py`:
```python
# app.include_router(slack_router, prefix=f"{settings.api_v1_prefix}/connectors/slack", tags=["Slack"])
```

---

## 12. ConnectorResult Reference

```
ConnectorResult.success(source, data, metadata?)
    Use when: All fetchers completed successfully.
    status:   SUCCESS

ConnectorResult.partial(source, data, errors, metadata?)
    Use when: Some fetchers failed but others returned usable data.
    status:   PARTIAL
    Rule:     data must contain at least one populated field.

ConnectorResult.failed(source, errors, metadata?)
    Use when: All fetchers failed — no usable data was collected.
    status:   FAILED
    Rule:     data is always empty {}.
```

| Field | Type | Description |
|---|---|---|
| `source` | str | Must match `self.source_name` exactly |
| `status` | ConnectorStatus | SUCCESS / PARTIAL / FAILED |
| `data` | dict[str, Any] | Result of `your_context.model_dump()` |
| `errors` | list[str] | Human-readable error descriptions |
| `metadata` | dict[str, Any] | Optional: API call count, latency, etc. |

---

## 13. Authentication Pattern

**The connector never manages token refresh.** It receives a valid `access_token` as a parameter to `get_context()`. Token lifecycle — obtaining, refreshing, and storing tokens — is entirely the AuthService's responsibility.

```
# CORRECT
async def get_context(self, user_id: str, access_token: str) -> ConnectorResult:
    client = SlackAPIClient(access_token=access_token)
    ...

# WRONG — connector must not manage tokens
async def get_context(self, user_id: str) -> ConnectorResult:
    access_token = await auth_service.get_valid_token(user_id)  # ← NEVER DO THIS
    ...
```

If the `access_token` is invalid and the API returns a 401, catch it and return `ConnectorResult.failed()` with a `ConnectorAuthError` description. The calling layer will detect the auth error and trigger a token refresh.

---

## 14. Error Handling

| Scenario | What to do |
|---|---|
| One fetcher out of two fails | Return `ConnectorResult.partial()` with the successful data and the error message |
| All fetchers fail | Return `ConnectorResult.failed()` with error messages |
| Access token is invalid (401) | Return `ConnectorResult.failed()` with `ConnectorAuthError` description |
| API rate limited (429) | Retry up to 3 times with exponential backoff in the API client; if all retries fail, return `ConnectorResult.failed()` |
| Network timeout | Return `ConnectorResult.failed()` with `ConnectorTimeoutError` description |
| `get_context()` itself must NEVER raise | Always catch exceptions inside `get_context()` and return a `ConnectorResult` |

---

## 15. Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Connector package | lowercase, no hyphens | `slack/`, `github/`, `jira/` |
| Connector class | `<Name>Connector` | `SlackConnector`, `GitHubConnector` |
| API client class | `<Name>APIClient` | `SlackAPIClient`, `GitHubAPIClient` |
| Fetcher class | `<Entity>Fetcher` | `MentionsFetcher`, `PullRequestFetcher` |
| Normalizer class | `<Name>Normalizer` | `SlackNormalizer` |
| Context model | `<Name>Context` | `SlackContext`, `GitHubContext` |
| `source_name` | lowercase, hyphenated | `"slack"`, `"github"`, `"jira"` |
| Settings class | `<Name>Settings` | `SlackSettings` |

---

## 16. Design Rules

1. **One connector per enterprise application.** `SlackConnector` only fetches Slack data.
2. **All HTTP calls live in the API client.** Fetchers never call `httpx` directly.
3. **Fetchers never normalize.** They return raw API dictionaries.
4. **The normalizer is a pure function.** No I/O, no side effects.
5. **The connector never raises.** `get_context()` always returns a `ConnectorResult`.
6. **Run fetchers concurrently.** Use `asyncio.gather()`, not sequential `await`.
7. **Never import from another connector.** `SlackConnector` never imports from `outlook/`.
8. **Never import from `context_builder` or `bob`.** Connectors live one layer below these.
9. **Connector-specific settings stay in the connector's own `settings.py`.**
10. **The `source_name` must be unique and stable.** Once deployed, never rename it.

---

## 17. Common Mistakes

### ❌ Calling IBM Bob from inside a connector
```python
# WRONG
async def get_context(self, user_id, access_token):
    data = await self._fetch()
    recommendation = await bob_service.analyze(data)  # ← NEVER
```

### ❌ One fetcher calling another fetcher
```python
# WRONG
class MessagesFetcher:
    async def fetch(self):
        mentions = await MentionsFetcher(self._client).fetch()  # ← NEVER
```

### ❌ Normalizer making HTTP calls
```python
# WRONG
class SlackNormalizer:
    async def normalize(self, raw):
        extra = await self._client.get_extra()  # ← NEVER — normalizer is pure
```

### ❌ Raising an exception from `get_context()`
```python
# WRONG
async def get_context(self, user_id, access_token):
    raise ConnectorError("slack", "API is down")  # ← Context Builder will crash
```
```python
# CORRECT
async def get_context(self, user_id, access_token):
    try:
        ...
    except Exception as exc:
        return ConnectorResult.failed(self.source_name, [str(exc)])
```

### ❌ Sequential fetcher calls
```python
# WRONG — 400ms + 300ms = 700ms total
messages = await messages_fetcher.fetch()
mentions = await mentions_fetcher.fetch()

# CORRECT — max(400ms, 300ms) = 400ms total
messages, mentions = await asyncio.gather(
    messages_fetcher.fetch(), mentions_fetcher.fetch()
)
```

---

## 18. Testing Recommendations

### Unit test the normalizer (no mocking needed)
```python
def test_normalize_maps_message_text():
    normalizer = SlackNormalizer()
    raw_messages = [{"ts": "1234567890.0", "text": "Hello", "user": "U123", ...}]
    result = normalizer.normalize(raw_messages=raw_messages, raw_mentions=[])
    assert result.total_unread == 1
    assert result.unread_messages[0].text == "Hello"
```

### Unit test fetchers with a mock client
```python
import pytest
from unittest.mock import AsyncMock

async def test_mentions_fetcher_returns_empty_on_no_mentions():
    mock_client = AsyncMock()
    mock_client.get_user_mentions.return_value = {"messages": {"matches": []}}
    fetcher = MentionsFetcher(client=mock_client)
    result = await fetcher.fetch()
    assert result == []
```

### Unit test the connector with mock fetchers
```python
async def test_connector_returns_partial_when_one_fetcher_fails():
    connector = SlackConnector()
    # Mock the internal client creation ...
    result = await connector.get_context("user-1", "fake-token")
    assert result.status == ConnectorStatus.PARTIAL
    assert len(result.errors) == 1
```

### Integration test with recorded API fixtures
Store raw API responses as JSON fixture files in `tests/connectors/slack/fixtures/`. Load them in tests instead of calling the real Slack API. This lets tests run offline and in CI without credentials.

---

## 19. Checklist

Before opening a pull request for a new connector, verify:

- [ ] `source_name` is unique, lowercase, and stable
- [ ] All HTTP calls are inside the API client — nowhere else
- [ ] Fetchers accept the API client as a constructor parameter
- [ ] The normalizer is a pure function with no I/O
- [ ] `get_context()` never raises — all exceptions produce a `ConnectorResult`
- [ ] Fetchers run concurrently via `asyncio.gather()`
- [ ] Connector-specific settings are in `<name>/settings.py`, not `AppSettings`
- [ ] Variables are added to `.env.example` under a labeled section
- [ ] `__init__.py` exists in the connector package and all sub-packages
- [ ] Connector is registered in `main.py` (commented or active)
- [ ] Unit tests exist for the normalizer
- [ ] Unit tests exist for each fetcher using a mock client
- [ ] Unit tests exist for the connector covering SUCCESS, PARTIAL, and FAILED paths
- [ ] `health_check()` is implemented and returns `False` (not raises) on failure
- [ ] No imports from other connector packages
- [ ] No imports from `context_builder` or `bob`

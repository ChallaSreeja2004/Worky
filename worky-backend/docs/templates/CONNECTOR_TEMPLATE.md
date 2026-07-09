# Worky — Connector Template

> **This is a blueprint, not a guide.**
> Copy this template when starting a new connector. Replace every `<Name>` placeholder with your connector's name (e.g., `Slack`, `GitHub`, `Jira`). Replace `<name>` with its lowercase identifier (e.g., `slack`, `github`, `jira`).
>
> For a detailed explanation of each step, see [`development/CONNECTOR_GUIDE.md`](../development/CONNECTOR_GUIDE.md).

---

## 1. Identity

| Field | Your value |
|---|---|
| Connector name | `<Name>` (e.g., `Slack`) |
| Package path | `app/connectors/<name>/` |
| `source_name` | `"<name>"` (lowercase, stable, unique) |
| Settings class | `<Name>Settings` |
| API client class | `<Name>APIClient` |
| Connector class | `<Name>Connector` |
| Normalizer class | `<Name>Normalizer` |
| Context model | `<Name>Context` |

---

## 2. Folder Structure

Create exactly this structure — no more, no fewer files:

```
app/connectors/<name>/
├── __init__.py               # Empty
├── settings.py               # <Name>Settings — connector-specific env vars
├── <name>_client.py          # <Name>APIClient — all HTTP calls
├── fetchers/
│   ├── __init__.py           # Empty
│   ├── <entity_a>.py         # <EntityA>Fetcher
│   └── <entity_b>.py         # <EntityB>Fetcher
├── normalizer.py             # <Name>Normalizer — pure transformation
├── models.py                 # <Name>Context and entity Pydantic models
├── connector.py              # <Name>Connector(BaseConnector) — orchestrator
└── router.py                 # Optional debug endpoint
```

Create the test mirror immediately:

```
tests/connectors/<name>/
├── __init__.py
├── fixtures/
│   ├── <entity_a>_response.json    # Recorded API response for entity A
│   └── <entity_b>_response.json    # Recorded API response for entity B
├── test_<name>_client.py           # HTTP client tests (respx mocking)
├── test_<entity_a>_fetcher.py      # Fetcher A tests (mock client)
├── test_<entity_b>_fetcher.py      # Fetcher B tests (mock client)
├── test_normalizer.py              # Normalizer tests (no mocking)
└── test_connector.py               # Connector integration tests
```

---

## 3. Implementation Order

Implement files in this exact order. Each file depends on the one before it.

```
1. settings.py         → defines env vars (no dependencies)
2. <name>_client.py    → uses settings
3. fetchers/           → uses <name>_client.py
4. models.py           → pure Pydantic models (no dependencies)
5. normalizer.py       → uses models.py
6. connector.py        → uses fetchers + normalizer → returns ConnectorResult
7. router.py           → optional debug endpoint using connector.py
```

---

## 4. File Templates

### `settings.py`

```python
# app/connectors/<name>/settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class <Name>Settings(BaseSettings):
    """<Name>-specific configuration. All values from environment variables."""

    # OAuth credentials
    <name>_client_id: str
    <name>_client_secret: str
    <name>_redirect_uri: str = "http://localhost:8000/api/v1/auth/<name>/callback"

    # API
    <name>_api_base_url: str = "https://api.<name>.com"  # replace with real URL

    @property
    def oauth_scopes(self) -> list[str]:
        return ["scope_a", "scope_b"]  # replace with real scopes

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )


@lru_cache
def get_<name>_settings() -> <Name>Settings:
    return <Name>Settings()
```

Add to `.env.example`:
```ini
# <Name>Settings  (app/connectors/<name>/settings.py)
# <NAME>_CLIENT_ID=your-client-id
# <NAME>_CLIENT_SECRET=your-client-secret
# <NAME>_REDIRECT_URI=http://localhost:8000/api/v1/auth/<name>/callback
```

---

### `<name>_client.py`

```python
# app/connectors/<name>/<name>_client.py
import httpx
from app.connectors.<name>.settings import get_<name>_settings


class <Name>APIClient:
    """
    Thin HTTP wrapper for the <Name> API.

    All httpx calls in the <Name> connector live here.
    Fetchers call this client; they never import httpx directly.
    """

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._base_url = get_<name>_settings().<name>_api_base_url
        self._headers = {"Authorization": f"Bearer {self._token}"}

    async def get_<entity_a>(self, **params) -> dict:
        """Fetch <entity_a> from <Name> API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/<endpoint>",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def ping(self) -> bool:
        """Lightweight reachability check for health_check()."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/<lightweight_endpoint>",
                headers=self._headers,
            )
            return response.status_code == 200
```

---

### `fetchers/<entity_a>.py`

```python
# app/connectors/<name>/fetchers/<entity_a>.py
import logging
from app.connectors.<name>.<name>_client import <Name>APIClient

logger = logging.getLogger(__name__)


class <EntityA>Fetcher:
    """
    Fetches <entity_a> from the <Name> API.

    Returns raw API response dicts. Does NOT normalize.
    Raises on unrecoverable error; returns empty list when empty.
    """

    def __init__(self, client: <Name>APIClient) -> None:
        self._client = client

    async def fetch(self) -> list[dict]:
        logger.debug("<EntityA>Fetcher: fetching")
        raw = await self._client.get_<entity_a>()
        items = raw.get("<items_key>", [])
        logger.debug("<EntityA>Fetcher: found %d items", len(items))
        return items
```

---

### `models.py`

```python
# app/connectors/<name>/models.py
from datetime import datetime
from pydantic import BaseModel, Field


class <EntityA>Model(BaseModel):
    """A single <entity_a> from <Name>."""
    id: str
    # ... connector-specific fields using Worky domain names (not vendor names)


class <Name>Context(BaseModel):
    """
    The complete <Name> data payload for one user.
    This is the shape of ConnectorResult.data for the <Name> connector.
    """
    <entity_a>s: list[<EntityA>Model] = Field(default_factory=list)
    total_<entity_a>s: int = 0
    # ... add additional entities
```

---

### `normalizer.py`

```python
# app/connectors/<name>/normalizer.py
import logging
from app.connectors.<name>.models import <EntityA>Model, <Name>Context

logger = logging.getLogger(__name__)


class <Name>Normalizer:
    """
    Maps raw <Name> API responses → typed <Name>Context.

    Pure transformation function — no I/O, no side effects.
    Missing or malformed fields are handled with defaults.
    """

    def normalize(
        self,
        raw_<entity_a>s: list[dict],
        # ... add additional raw inputs
    ) -> <Name>Context:
        items = [self._map_<entity_a>(r) for r in raw_<entity_a>s]
        return <Name>Context(<entity_a>s=items, total_<entity_a>s=len(items))

    def _map_<entity_a>(self, raw: dict) -> <EntityA>Model:
        return <EntityA>Model(
            id=raw.get("id", ""),
            # ... map fields using .get() with safe defaults
        )
```

---

### `connector.py`

```python
# app/connectors/<name>/connector.py
import asyncio
import logging
from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult
from app.connectors.<name>.<name>_client import <Name>APIClient
from app.connectors.<name>.fetchers.<entity_a> import <EntityA>Fetcher
from app.connectors.<name>.fetchers.<entity_b> import <EntityB>Fetcher
from app.connectors.<name>.normalizer import <Name>Normalizer

logger = logging.getLogger(__name__)


class <Name>Connector(BaseConnector):
    """
    Collects data from <Name> and returns a ConnectorResult.

    Implements BaseConnector — the Context Builder calls get_context()
    and receives a ConnectorResult without knowing any implementation detail.
    """

    @property
    def source_name(self) -> str:
        return "<name>"  # must be unique, stable, lowercase

    async def get_context(
        self, user_id: str, access_token: str
    ) -> ConnectorResult:
        logger.info("%s: starting context collection for user=%s", self.source_name, user_id)

        client = <Name>APIClient(access_token=access_token)
        fetcher_a = <EntityA>Fetcher(client=client)
        fetcher_b = <EntityB>Fetcher(client=client)
        normalizer = <Name>Normalizer()
        errors: list[str] = []

        # Run all fetchers concurrently
        raw_a, raw_b = await asyncio.gather(
            fetcher_a.fetch(),
            fetcher_b.fetch(),
            return_exceptions=True,
        )

        # Handle partial failures
        if isinstance(raw_a, Exception):
            logger.warning("%s: <entity_a> fetch failed: %s", self.source_name, raw_a)
            errors.append(f"<EntityA> fetch failed: {raw_a}")
            raw_a = []

        if isinstance(raw_b, Exception):
            logger.warning("%s: <entity_b> fetch failed: %s", self.source_name, raw_b)
            errors.append(f"<EntityB> fetch failed: {raw_b}")
            raw_b = []

        context = normalizer.normalize(raw_a, raw_b)
        data = context.model_dump()

        if errors and not data:
            return ConnectorResult.failed(source=self.source_name, errors=errors)
        elif errors:
            return ConnectorResult.partial(source=self.source_name, data=data, errors=errors)
        else:
            return ConnectorResult.success(source=self.source_name, data=data)

    async def health_check(self) -> bool:
        """Returns False on any failure — never raises."""
        try:
            client = <Name>APIClient(access_token="")  # health check uses no token
            return await client.ping()
        except Exception:
            return False
```

---

### `router.py` (optional debug endpoint)

```python
# app/connectors/<name>/router.py
from fastapi import APIRouter
from app.connectors.<name>.connector import <Name>Connector
from app.connectors.models import ConnectorResult

router = APIRouter()

@router.get("/context", response_model=ConnectorResult)
async def get_<name>_context(user_id: str, access_token: str) -> ConnectorResult:
    """Debug endpoint — manually trigger a single <Name> context collection."""
    return await <Name>Connector().get_context(user_id=user_id, access_token=access_token)
```

Register in `main.py`:
```python
# from app.connectors.<name>.router import router as <name>_router
# app.include_router(<name>_router, prefix=f"{settings.api_v1_prefix}/connectors/<name>", tags=["<Name>"])
```

---

## 5. Register the Connector

Add to `main.py` in the connectors list:

```python
from app.connectors.<name>.connector import <Name>Connector

context_builder = ContextBuilder(
    connectors=[
        OutlookConnector(),
        SlackConnector(),
        <Name>Connector(),   # ← add here
    ]
)
```

---

## 6. Expected ConnectorResult Shape

After your connector runs, the `ConnectorResult.data` dictionary must look like this:

```json
{
  "<entity_a>s": [
    {
      "id": "...",
      "..."
    }
  ],
  "total_<entity_a>s": 3,
  "<entity_b>s": [],
  "total_<entity_b>s": 0
}
```

This dict maps directly to your `<Name>Context.model_dump()` output. Document the exact shape in your connector's `models.py`.

---

## 7. Common Mistakes

| Mistake | Correct approach |
|---|---|
| Calling Bob from inside the connector | Never. Connectors return ConnectorResult and stop there. |
| Raising from `get_context()` | Catch all exceptions; return `ConnectorResult.failed()` |
| Sequential fetcher calls | Always use `asyncio.gather()` |
| Normalizer making HTTP calls | Normalizer is a pure function — no I/O |
| Fetcher importing httpx directly | All HTTP calls live in the API client |
| Using vendor field names in models | Always use Worky domain names (e.g., `sender_name`, not `from_user_id_string`) |
| Importing from another connector | Never. Each connector package is isolated. |
| Adding connector env vars to AppSettings | Always use the connector's own `settings.py` |

---

## 8. Pre-PR Checklist

Before opening a pull request, every item must be checked:

**Structure**
- [ ] `source_name` is unique, lowercase, and permanent
- [ ] All files exist: settings, client, fetchers, normalizer, models, connector
- [ ] All `__init__.py` files are present
- [ ] Connector is registered in `main.py`
- [ ] Variables added to `.env.example` under a labeled section

**Implementation**
- [ ] `get_context()` never raises — all exceptions return `ConnectorResult`
- [ ] Fetchers run concurrently via `asyncio.gather()`
- [ ] All HTTP calls are in the API client only
- [ ] Fetchers return raw dicts only — no normalization
- [ ] Normalizer is a pure function — no I/O
- [ ] `health_check()` returns `False` (not raises) on failure

**Tests**
- [ ] Normalizer unit tests — 100% coverage
- [ ] Fetcher unit tests using mock API client
- [ ] Connector tests covering SUCCESS, PARTIAL, and FAILED paths
- [ ] Fixture JSON files stored under `tests/connectors/<name>/fixtures/`
- [ ] No real API calls in any test

**Documentation**
- [ ] `source_name` documented in the connector's `__init__.py` or module docstring
- [ ] `ConnectorResult.data` shape documented in `models.py`
- [ ] Import rules documented at the top of each file

---

*For step-by-step implementation guidance, see [`development/CONNECTOR_GUIDE.md`](../development/CONNECTOR_GUIDE.md).*
*For engineering standards and PR requirements, see [`development/CONTRIBUTING.md`](../development/CONTRIBUTING.md).*

# Worky — Implementation Checklist

> **This is the team's daily working tracker.**
> For each phase, use this document to verify completeness before moving to the next.
> Update status markers as work progresses. Link to PRs in the Git Tag column.
>
> **Status markers:** `[ ]` Not started · `[-]` In progress · `[x]` Complete

---

## How to Use This Document

1. Identify the current phase from [`planning/ROADMAP.md`](../planning/ROADMAP.md)
2. Work through every checkbox in the phase's section
3. Run validation commands before marking tasks complete
4. Create the Git tag only after all items in the phase are checked
5. Update [`planning/ROADMAP.md`](../planning/ROADMAP.md) phase status after tagging

---

## Phase 1 — Project Foundation

**Owner:** Team | **Git Tag:** `v0.1.0` | **Status:** ✅ Complete

**Suggested Commit:** `feat(shared): establish project foundation and shared contracts`

### Tasks
- [x] Create project directory structure
- [x] Create `app/config/settings.py` — `AppSettings`
- [x] Create `app/connectors/base.py` — `BaseConnector` ABC + exception hierarchy
- [x] Create `app/connectors/models.py` — `ConnectorResult`, `ConnectorStatus`
- [x] Create `app/context_builder/models.py` — `WorkContext`, `ConnectorSummary`
- [x] Create `app/auth/models.py` — `TokenData`, `AuthorizationResponse`
- [x] Create `app/auth/repository.py` — `TokenRepository`, `InMemoryTokenRepository`
- [x] Create `main.py` — FastAPI app with versioned prefix and router stubs
- [x] Create `.env.example` — grouped by settings class

### Required Files
- [x] `app/__init__.py`
- [x] `app/config/__init__.py`
- [x] `app/auth/__init__.py`
- [x] `app/connectors/__init__.py`
- [x] `app/context_builder/__init__.py`

### Tests
- [x] `ConnectorResult.success()` / `.partial()` / `.failed()` — verified
- [x] `WorkContext.from_connector_results()` — verified
- [x] `InMemoryTokenRepository` save/get/delete/exists — verified
- [x] `BaseConnector` is abstract — verified

### Documentation
- [x] All docs in `docs/` written and organized
- [x] `docs/TEAM_RULES.md` created
- [x] `docs/templates/CONNECTOR_TEMPLATE.md` created
- [x] `docs/IMPLEMENTATION_CHECKLIST.md` created (this file)

### Completion Criteria
All shared contracts importable. `python scripts/check_env.py` passes. `pytest tests/` passes. Server starts with `uvicorn main:app --reload`.

---

## Phase 2 — Outlook Authentication

**Owner:** Outlook Developer | **Git Tag:** `v0.2.0` | **Status:** ✅ Complete

**Commit:** `feat(auth): implement Microsoft OAuth 2.0 PKCE flow`

### Tasks
- [x] Create `app/connectors/outlook/settings.py` — `OutlookSettings`
- [x] Create `app/auth/service.py` — `AuthService` with PKCE
  - [x] `get_authorization_url()` — generates `code_verifier` + `code_challenge`
  - [x] `exchange_code_for_tokens()` — exchanges code for token set
  - [x] `get_valid_token()` — returns valid token, refreshes silently if expired
  - [x] `revoke_token()` — logout / token revocation
- [x] Create `app/auth/router.py`
  - [x] `GET /api/v1/auth/login` — returns authorization URL
  - [x] `GET /api/v1/auth/callback` — exchanges code for tokens
  - [x] `POST /api/v1/auth/refresh` — refreshes token silently
- [x] Mount auth router in `main.py`

### Required Files
- [x] `app/connectors/outlook/__init__.py`
- [x] `app/connectors/outlook/settings.py`
- [x] `app/auth/service.py`
- [x] `app/auth/router.py`
- [x] `app/auth/dependencies.py`

### Environment Variables (add to `.env`)
- [x] `OUTLOOK_CLIENT_ID`
- [x] `OUTLOOK_TENANT_ID`
- [x] `OUTLOOK_REDIRECT_URI`

### Tests
- [x] `tests/auth/test_service.py` — 31/31 passing
  - [x] PKCE pair generation
  - [x] Authorization URL generation
  - [x] Code exchange for tokens
  - [x] Silent token refresh
  - [x] Token revocation
  - [x] Fernet encryption round-trip

### Completion Criteria
All auth tests pass. `GET /api/v1/auth/login` returns a valid Microsoft login URL. Token exchange and refresh verified.

---

## Phase 3 — Microsoft Graph Client

**Owner:** Outlook Developer | **Git Tag:** `v0.3.0` | **Status:** ✅ Complete

**Commit:** `feat(outlook): implement GraphAPIClient with retry logic`

### Tasks
- [x] Create `app/connectors/outlook/graph_client.py` — `GraphAPIClient`
  - [x] `get_current_user()` — `GET /me`
  - [x] `get_calendar_events()` — `GET /me/calendarView` (today, UTC range)
  - [x] `get_messages()` — `GET /me/messages` (unread + high-importance)
  - [x] `ping()` — lightweight reachability check, never raises
  - [x] Exponential back-off retry (429, 503 — max 3 attempts: 1s, 2s, raise)
  - [x] `$select` parameters on every call
  - [x] `AsyncClient` constructed once outside retry loop (connection reuse)
  - [x] `GraphError` exception hierarchy (`GraphAuthError`, `GraphRateLimitError`, `GraphServiceError`)

### Required Files
- [x] `app/connectors/outlook/graph_client.py`
- [x] `tests/connectors/outlook/test_graph_client.py`

### Tests
- [x] 46 tests — all passing (post-review: 47 tests)
- [x] Constructor, all public methods, retry policy, back-off delays, exception hierarchy, `_extract_error_message`

### Validation
```bash
pytest tests/connectors/outlook/test_graph_client.py -v
```

### Completion Criteria
✅ All `GraphAPIClient` methods pass tests with `respx` mocking. Retry logic verified. Engineering review passed.

---

## Phase 4 — Calendar Fetcher

**Owner:** Outlook Developer | **Git Tag:** `v0.4.0` | **Status:** ✅ Complete

**Commit:** `feat(outlook): add CalendarFetcher for today's events`

### Tasks
- [x] Create `app/connectors/outlook/fetchers/__init__.py`
- [x] Create `app/connectors/outlook/fetchers/calendar.py` — `CalendarFetcher`
  - [x] `fetch()` — returns raw calendar event list for today
  - [x] Handles empty calendar gracefully (returns `[]`)
  - [x] Handles missing `value` key gracefully (returns `[]`)
  - [x] All `GraphError` subclasses propagate unchanged

### Required Files
- [x] `app/connectors/outlook/fetchers/__init__.py`
- [x] `app/connectors/outlook/fetchers/calendar.py`
- [x] `tests/connectors/outlook/test_calendar_fetcher.py`

### Tests
- [x] `test_returns_raw_event_list`
- [x] `test_empty_value_list_returns_empty_list`
- [x] `test_missing_value_key_returns_empty_list`
- [x] `test_graph_auth_error_propagates`
- [x] `test_graph_rate_limit_error_propagates`
- [x] `test_graph_service_error_propagates`
- [x] 12 tests total — all passing

### Validation
```bash
pytest tests/connectors/outlook/test_calendar_fetcher.py -v
# 12 passed
pytest tests/ -v
# 89 passed
```

### Completion Criteria
✅ `CalendarFetcher` returns raw event dicts. All 12 tests pass with mock `GraphAPIClient`. Engineering review: APPROVED.

---

## Phase 5 — Email Fetcher

**Owner:** Outlook Developer | **Git Tag:** (→ v0.5.0) | **Status:** 🔜 Next

**Suggested Commit:** `feat(outlook): add EmailFetcher for unread and high-importance messages`

### Tasks
- [ ] Create `app/connectors/outlook/fetchers/email.py` — `EmailFetcher`
  - [ ] `fetch_unread()` — `$filter=isRead eq false`
  - [ ] `fetch_high_importance()` — `$filter=importance eq 'high'`
  - [ ] Handles empty inbox gracefully
- [ ] Record fixture: `tests/connectors/outlook/fixtures/messages.json`

### Required Files
- [ ] `app/connectors/outlook/fetchers/email.py`
- [ ] `tests/connectors/outlook/fixtures/messages.json`
- [ ] `tests/connectors/outlook/test_email_fetcher.py`

### Tests
- [ ] `test_fetch_unread_returns_messages()`
- [ ] `test_fetch_high_importance_applies_filter()`
- [ ] `test_fetch_returns_empty_list_when_no_messages()`

### Validation
```bash
pytest tests/connectors/outlook/test_email_fetcher.py -v
```

### Completion Criteria
`EmailFetcher` returns separate unread and high-importance message lists. All tests pass with mock `GraphAPIClient`.

---

## Phase 6 — Normalizer

**Owner:** Outlook Developer | **Git Tag:** (bundled into v0.5.0) | **Status:** 📋 Planned

**Suggested Commit:** `feat(outlook): implement OutlookNormalizer and domain models`

### Tasks
- [ ] Create `app/connectors/outlook/models.py`
  - [ ] `OutlookUser` model
  - [ ] `CalendarEvent` model
  - [ ] `Email` model
  - [ ] `OutlookContext` model
- [ ] Create `app/connectors/outlook/normalizer.py` — `OutlookNormalizer`
  - [ ] `normalize(raw_events, raw_unread, raw_high_importance)` → `OutlookContext`
  - [ ] Handle missing optional fields with `.get()` defaults
  - [ ] Parse Microsoft datetime format: `"2025-07-10T09:00:00.0000000"`
  - [ ] Detect online meetings via `isOnlineMeeting` flag

### Required Files
- [ ] `app/connectors/outlook/models.py`
- [ ] `app/connectors/outlook/normalizer.py`
- [ ] `tests/connectors/outlook/test_normalizer.py`

### Tests (100% coverage required — pure function)
- [ ] `test_normalize_maps_subject_to_calendar_event()`
- [ ] `test_normalize_handles_missing_attendees()`
- [ ] `test_normalize_detects_online_meeting()`
- [ ] `test_normalize_parses_microsoft_datetime_format()`
- [ ] `test_normalize_maps_high_importance_emails()`
- [ ] `test_normalize_empty_inputs_returns_empty_context()`

### Validation
```bash
pytest tests/connectors/outlook/test_normalizer.py -v --cov=app/connectors/outlook/normalizer
```

### Completion Criteria
`OutlookNormalizer` achieves 100% test coverage. All edge cases handled. No I/O in normalizer.

---

## Phase 7 — Outlook Connector

**Owner:** Outlook Developer | **Git Tag:** `v0.5.0` | **Status:** 📋 Planned

**Suggested Commit:** `feat(outlook): complete OutlookConnector integrating all layers`

### Tasks
- [ ] Create `app/connectors/outlook/connector.py` — `OutlookConnector(BaseConnector)`
  - [ ] Concurrent fetch via `asyncio.gather(return_exceptions=True)`
  - [ ] Partial failure handling (calendar fails → email still returned)
  - [ ] Total failure handling (all fetchers fail → `ConnectorResult.failed()`)
- [ ] Create `app/connectors/outlook/router.py` — debug endpoint
- [ ] Register `OutlookConnector` in `main.py`

### Required Files
- [ ] `app/connectors/outlook/connector.py`
- [ ] `app/connectors/outlook/router.py`
- [ ] `tests/connectors/outlook/test_connector.py`

### Tests
- [ ] `test_get_context_returns_success_when_all_fetchers_succeed()`
- [ ] `test_get_context_returns_partial_when_email_fetch_fails()`
- [ ] `test_get_context_returns_partial_when_calendar_fetch_fails()`
- [ ] `test_get_context_returns_failed_when_all_fetchers_fail()`
- [ ] `test_health_check_returns_true_on_reachable_api()`
- [ ] `test_health_check_returns_false_on_unreachable_api()`

### Validation
```bash
pytest tests/connectors/outlook/ -v --cov=app/connectors/outlook
# Target: 85%+ coverage
```

### Documentation
- [ ] Update `docs/README.md` status table
- [ ] Update `docs/planning/ROADMAP.md` — Phase 7 complete

### Repository State After Completion
`GET /api/v1/connectors/outlook/context` returns a valid `ConnectorResult` with today's calendar events and unread emails.

### Git Tag
```bash
git tag -a v0.5.0 -m "Phase 7: Outlook Connector complete"
git push origin v0.5.0
```

### Completion Criteria
Full `OutlookConnector` test suite passes. Debug endpoint returns valid `ConnectorResult`. `source_name == "outlook"`. Partial and total failure paths verified.

---

## Phase 8 — Slack Connector

**Owner:** Slack Developer | **Git Tag:** `v0.6.0` | **Status:** 📋 Planned

**Suggested Commit:** `feat(slack): implement complete SlackConnector`

### Tasks
- [ ] Follow [`docs/templates/CONNECTOR_TEMPLATE.md`](../templates/CONNECTOR_TEMPLATE.md) exactly
- [ ] `app/connectors/slack/settings.py` — `SlackSettings`
- [ ] `app/connectors/slack/slack_client.py` — `SlackAPIClient`
- [ ] `app/connectors/slack/fetchers/messages.py` — `MessagesFetcher`
- [ ] `app/connectors/slack/fetchers/mentions.py` — `MentionsFetcher`
- [ ] `app/connectors/slack/models.py` — `SlackMessage`, `SlackContext`
- [ ] `app/connectors/slack/normalizer.py` — `SlackNormalizer`
- [ ] `app/connectors/slack/connector.py` — `SlackConnector(BaseConnector)`
- [ ] Register `SlackConnector` in `main.py` alongside `OutlookConnector`

### Tests
- [ ] Full test suite following same pattern as Outlook connector
- [ ] `source_name == "slack"` verified

### Completion Criteria
`SlackConnector` passes full test suite. Registered alongside `OutlookConnector`. `source_name` is unique and stable.

---

## Phase 9 — Context Builder

**Owner:** Team | **Git Tag:** `v0.7.0` | **Status:** 📋 Planned

**Suggested Commit:** `feat(context-builder): implement ContextBuilder with concurrent connector aggregation`

### Tasks
- [ ] Create `app/context_builder/builder.py` — `ContextBuilder`
  - [ ] Constructor accepts `list[BaseConnector]` (injected)
  - [ ] `build(user_id, access_token)` → `WorkContext`
  - [ ] `asyncio.gather()` for concurrent execution
  - [ ] Assembly duration recorded in `WorkContext.metadata`
- [ ] Wire `ContextBuilder` in `main.py` with all registered connectors

### Tests
- [ ] `test_build_returns_workcontext_with_all_sources()`
- [ ] `test_build_excludes_failed_connector_from_sources()`
- [ ] `test_build_runs_connectors_concurrently()`
- [ ] `test_build_records_assembly_duration_in_metadata()`

### Completion Criteria
`ContextBuilder` with `[MockOutlookConnector(), MockSlackConnector()]` returns a `WorkContext` where `active_sources == ["outlook", "slack"]`.

---

## Phase 10 — IBM Bob Integration

**Owner:** Team | **Git Tag:** `v0.8.0` | **Status:** 📋 Planned

**Suggested Commit:** `feat(bob): define BobService interface and implement MockBobService`

### Tasks
- [ ] Create `app/bob/models.py` — `Recommendation`, `RecommendationSet`
- [ ] Create `app/bob/service.py` — `BobService` ABC + `IBMBobService`
- [ ] Create `app/bob/mock_service.py` — `MockBobService`
- [ ] DI configuration: inject `MockBobService` when `APP_ENV=development`

### Tests
- [ ] `test_mock_service_returns_recommendation_set()`
- [ ] `test_mock_service_uses_workcontext_user_id()`

### Completion Criteria
`MockBobService.analyze(work_context)` returns a valid `RecommendationSet`. Switching to `IBMBobService` is a DI configuration change only.

---

## Phase 11 — Recommendation Service

**Owner:** Team | **Git Tag:** `v0.9.0` | **Status:** 📋 Planned

**Suggested Commit:** `feat(recommendations): implement widget-facing API and scheduler`

### Tasks
- [ ] Create `app/recommendations/models.py` — `RecommendationResponse`
- [ ] Create `app/recommendations/cache.py` — `RecommendationCache`
- [ ] Create `app/recommendations/scheduler.py` — background task (every 5 min)
- [ ] Create `app/recommendations/router.py` — `GET /api/v1/recommendations`
- [ ] Register router in `main.py`

### Tests
- [ ] `test_recommendations_endpoint_returns_cached_result()`
- [ ] `test_scheduler_triggers_full_pipeline()`

### Completion Criteria
Widget can call `GET /api/v1/recommendations` and receive a `RecommendationResponse` populated from the cache. Scheduler runs automatically on startup.

---

## Phase 12 — Desktop Widget Integration

**Owner:** Team | **Git Tag:** `v0.10.0` | **Status:** 📋 Planned

**Suggested Commit:** `feat(widget): connect Electron widget to recommendations endpoint`

### Tasks
- [ ] Electron main process — HTTP client for backend
- [ ] React widget component consuming `RecommendationResponse`
- [ ] Login flow opening OAuth redirect in system browser
- [ ] Auto-refresh of recommendations every 60 seconds
- [ ] System tray integration

### Completion Criteria
Desktop application launches, user logs in, widget displays AI-generated recommendations, recommendations auto-refresh.

---

## Phase 13 — Production Hardening

**Owner:** Team | **Git Tag:** `v1.0.0` | **Status:** 📋 Planned

**Suggested Commit:** `chore(infra): production-ready configuration with Redis, Docker, and CI`

### Tasks
- [ ] `app/auth/redis_repository.py` — `RedisTokenRepository(TokenRepository)`
- [ ] Redis recommendation cache — replaces in-memory
- [ ] Structured logging with `request_id` correlation
- [ ] API rate limit handling (`Retry-After` header support)
- [ ] `GET /api/v1/health/detailed` — dependency health checks
- [ ] `Dockerfile` + `docker-compose.yml`
- [ ] CI pipeline — lint (`ruff`), typecheck (`mypy`), tests (`pytest`) on every PR
- [ ] DI switch: `InMemoryTokenRepository` in dev, `RedisTokenRepository` in prod

### Completion Criteria
Backend deployable with `docker-compose up`. All tests pass in CI. `InMemoryTokenRepository` automatically swapped for `RedisTokenRepository` when `APP_ENV=production`. Health endpoint reports all dependencies.

### Git Tag
```bash
git tag -a v1.0.0 -m "Worky v1.0.0 — production-ready backend"
git push origin v1.0.0
```

---

## Validation Commands Reference

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Lint
ruff check app/ tests/

# Format check
ruff format app/ tests/ --check

# Type check
mypy app/

# Start server
uvicorn main:app --reload --port 8000

# Check all env vars present
python scripts/check_env.py
```

---

*Planning context: [`planning/ROADMAP.md`](../planning/ROADMAP.md)*
*Engineering standards: [`development/CONTRIBUTING.md`](../development/CONTRIBUTING.md)*
*Connector implementation: [`templates/CONNECTOR_TEMPLATE.md`](../templates/CONNECTOR_TEMPLATE.md)*

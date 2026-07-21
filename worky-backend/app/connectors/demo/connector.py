"""
app/connectors/demo/connector.py
==================================
DemoOutlookConnector — a BaseConnector implementation that returns realistic
synthetic Outlook data without any Microsoft credentials.

DESIGN RATIONALE
----------------
DemoOutlookConnector exists so the full Worky pipeline
(ContextBuilder → RecommendationService → BobCLIService) can be exercised
without an Azure App Registration or real Outlook mailbox.

It implements the SAME interface as OutlookConnector and returns a
ConnectorResult whose shape is IDENTICAL to what OutlookConnector returns.
No component above this layer (ContextBuilder, RecommendationService,
BobCLIService) can distinguish a demo result from a real one.

WHAT THIS CONNECTOR DOES
-------------------------
  • Returns a fixed set of realistic calendar events for today.
  • Returns a fixed set of realistic email messages.
  • Timestamps are generated relative to "now" so the data always looks fresh.
  • Always returns ConnectorResult.success() — no partial/failed states in demo.

WHAT THIS CONNECTOR DOES NOT DO
---------------------------------
  • It does NOT call any external API.
  • It does NOT require any credentials or tokens.
  • It does NOT import from app.auth.
  • It does NOT import from app.connectors.outlook.graph_client.
  • It does NOT modify OutlookConnector in any way.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.base
  • app.connectors.models
  • app.connectors.outlook.models  (to produce identical model instances)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.connectors.base import BaseConnector
from app.connectors.models import ConnectorResult
from app.connectors.outlook.models import CalendarEvent, Email, OutlookContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo data helpers
# ---------------------------------------------------------------------------

_DEMO_USER_ID = "demo-user"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """Return an ISO 8601 string without timezone suffix, matching Graph format."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.0000000")


def _build_demo_events() -> list[CalendarEvent]:
    """
    Return a realistic set of calendar events relative to the current time.

    Events are spread across the day so they always look current regardless
    of when the demo is run.
    """
    now = _now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return [
        CalendarEvent(
            id="demo-event-001",
            subject="Team Standup",
            start=_iso(today.replace(hour=9, minute=0)),
            end=_iso(today.replace(hour=9, minute=15)),
            location="Microsoft Teams",
            organizer_name="Sarah Chen",
            organizer_email="sarah.chen@contoso.com",
            is_all_day=False,
            is_cancelled=False,
            is_online_meeting=True,
            join_url="https://teams.microsoft.com/l/meetup-join/demo-standup",
            body_preview="Daily sync — blockers, progress, and today's priorities.",
        ),
        CalendarEvent(
            id="demo-event-002",
            subject="Sprint Planning",
            start=_iso(today.replace(hour=10, minute=0)),
            end=_iso(today.replace(hour=11, minute=30)),
            location="Conference Room A",
            organizer_name="James Okafor",
            organizer_email="james.okafor@contoso.com",
            is_all_day=False,
            is_cancelled=False,
            is_online_meeting=True,
            join_url="https://teams.microsoft.com/l/meetup-join/demo-sprint",
            body_preview="Planning session for Sprint 24. Review backlog and commit to deliverables.",
        ),
        CalendarEvent(
            id="demo-event-003",
            subject="Client Demo",
            start=_iso(today.replace(hour=14, minute=0)),
            end=_iso(today.replace(hour=15, minute=0)),
            location="Zoom",
            organizer_name="Maria Santos",
            organizer_email="maria.santos@contoso.com",
            is_all_day=False,
            is_cancelled=False,
            is_online_meeting=True,
            join_url="https://zoom.us/j/demo-client-demo",
            body_preview="Live product demo for Acme Corp. Prepare Q3 roadmap slides.",
        ),
        CalendarEvent(
            id="demo-event-004",
            subject="1:1 with Manager",
            start=_iso(today.replace(hour=15, minute=30)),
            end=_iso(today.replace(hour=16, minute=0)),
            location="",
            organizer_name="David Kim",
            organizer_email="david.kim@contoso.com",
            is_all_day=False,
            is_cancelled=False,
            is_online_meeting=True,
            join_url="https://teams.microsoft.com/l/meetup-join/demo-1on1",
            body_preview="Weekly check-in. Discuss performance review timeline and project priorities.",
        ),
        CalendarEvent(
            id="demo-event-005",
            subject="Architecture Review",
            start=_iso(today.replace(hour=16, minute=30)),
            end=_iso(today.replace(hour=17, minute=30)),
            location="Engineering Hub",
            organizer_name="Priya Nair",
            organizer_email="priya.nair@contoso.com",
            is_all_day=False,
            is_cancelled=False,
            is_online_meeting=False,
            join_url="",
            body_preview="Review proposed microservices split for the payments module.",
        ),
    ]


def _build_demo_emails() -> list[Email]:
    """
    Return a realistic set of email messages.

    Timestamps are offset from now so received_at always looks recent.
    """
    now = _now()

    return [
        Email(
            id="demo-email-001",
            subject="Client Presentation Tomorrow — Final Deck Needed",
            sender_name="Maria Santos",
            sender_email="maria.santos@contoso.com",
            received_at=_iso(now - timedelta(hours=1, minutes=15)),
            is_read=False,
            importance="high",
            body_preview=(
                "Hi, just a reminder that Acme Corp expects the final deck by 9 AM "
                "tomorrow. Please confirm when it's ready."
            ),
            has_attachments=False,
        ),
        Email(
            id="demo-email-002",
            subject="HR: Complete Your Onboarding Documents by Friday",
            sender_name="HR Team",
            sender_email="hr@contoso.com",
            received_at=_iso(now - timedelta(hours=3)),
            is_read=False,
            importance="normal",
            body_preview=(
                "You have 3 onboarding documents pending completion in the HR portal. "
                "Deadline: this Friday at 5 PM."
            ),
            has_attachments=True,
        ),
        Email(
            id="demo-email-003",
            subject="Code Review Request: payments-service/PR-412",
            sender_name="Alex Rivera",
            sender_email="alex.rivera@contoso.com",
            received_at=_iso(now - timedelta(hours=4, minutes=30)),
            is_read=False,
            importance="normal",
            body_preview=(
                "Opened PR #412 for the Stripe webhook handler refactor. "
                "Needs at least 2 approvals before merging."
            ),
            has_attachments=False,
        ),
        Email(
            id="demo-email-004",
            subject="Security Patch Notification — Action Required",
            sender_name="IT Security",
            sender_email="security@contoso.com",
            received_at=_iso(now - timedelta(hours=6)),
            is_read=True,
            importance="high",
            body_preview=(
                "Critical patch CVE-2024-12345 must be applied to all production "
                "nodes by end of business today. Run the patching script."
            ),
            has_attachments=True,
        ),
        Email(
            id="demo-email-005",
            subject="Sprint Planning Notes — Action Items Inside",
            sender_name="James Okafor",
            sender_email="james.okafor@contoso.com",
            received_at=_iso(now - timedelta(hours=8)),
            is_read=True,
            importance="normal",
            body_preview=(
                "Attached are the sprint planning notes. You have 3 story points "
                "assigned: WORK-441, WORK-442, WORK-445."
            ),
            has_attachments=True,
        ),
    ]


# ---------------------------------------------------------------------------
# DemoOutlookConnector
# ---------------------------------------------------------------------------

class DemoOutlookConnector(BaseConnector):
    """
    BaseConnector implementation that returns realistic synthetic Outlook data.

    Requires no Microsoft credentials, no access token, and no network calls.
    Every output model is identical in shape to what OutlookConnector returns,
    ensuring the rest of the pipeline (ContextBuilder, RecommendationService,
    BobCLIService) behaves exactly as it would with real Outlook data.

    Usage (via dependency injection):
    ::

        connector = DemoOutlookConnector()
        result = await connector.get_context(user_id="demo-user", access_token="")
    """

    # ------------------------------------------------------------------
    # BaseConnector — identity
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        """Matches the production OutlookConnector source name exactly."""
        return "outlook"

    # ------------------------------------------------------------------
    # BaseConnector — core contract
    # ------------------------------------------------------------------

    async def get_context(self, user_id: str, access_token: str) -> ConnectorResult:
        """
        Return a synthetic ConnectorResult with realistic Outlook data.

        The access_token parameter is accepted to satisfy the BaseConnector
        interface but is not used — DemoOutlookConnector requires no token.

        Always returns ConnectorResult.success() with a fully populated
        OutlookContext containing demo calendar events and email messages.
        """
        logger.info(
            "DemoOutlookConnector: returning synthetic Outlook data for user_id=%s",
            user_id,
        )

        context = OutlookContext(
            user=None,
            calendar_events=_build_demo_events(),
            emails=_build_demo_emails(),
        )

        return ConnectorResult.success(
            source=self.source_name,
            data=context.model_dump(),
            metadata={"connector": "demo", "synthetic": True},
        )

    # ------------------------------------------------------------------
    # BaseConnector — operational contract
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Always healthy — no external dependency to check."""
        return True

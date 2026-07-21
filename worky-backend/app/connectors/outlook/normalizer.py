"""
app/connectors/outlook/normalizer.py
=====================================
OutlookNormalizer — transforms raw Microsoft Graph JSON into Worky domain models.

RESPONSIBILITIES
----------------
  • Accept raw Graph dictionaries returned by CalendarFetcher and EmailFetcher.
  • Map each raw dict to the appropriate Worky domain model.
  • Return a fully populated OutlookContext.
  • Handle every optional field defensively using .get() — never assume a key exists.

WHAT THIS MODULE DOES NOT DO
-----------------------------
  • It does NOT make any HTTP requests.
  • It does NOT call GraphAPIClient.
  • It does NOT access CalendarFetcher or EmailFetcher.
  • It does NOT contain any I/O.
  • It does NOT contain business logic (filtering, sorting, prioritising).

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • app.connectors.outlook.models

It must NOT import from:
  • app.auth
  • app.config
  • app.connectors.base
  • app.connectors.models
  • app.connectors.outlook.graph_client
  • app.connectors.outlook.fetchers
  • app.context_builder
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.connectors.outlook.models import (
    CalendarEvent,
    Email,
    OutlookContext,
    OutlookUser,
)

logger = logging.getLogger(__name__)

# Graph returns datetimes with 7 fractional-second digits (.0000000).
# Strip to 3 digits (.000) which is standard ISO 8601 milliseconds, then
# ensure the string ends with "Z" so JavaScript's Date() always treats it
# as UTC.  Without "Z", Date() uses local time — making epoch comparisons
# browser-timezone-dependent.
_GRAPH_DT_FRAC = re.compile(r"\.\d+")

def _normalise_graph_datetime(dt: str) -> str:
    """
    Normalise a Graph API dateTime string to a standard UTC ISO 8601 string.

    Examples
    --------
    "2026-07-21T16:00:00.0000000Z"  →  "2026-07-21T16:00:00.000Z"
    "2026-07-21T21:30:00.0000000"   →  "2026-07-21T21:30:00.000Z"
    "2026-07-21T16:00:00Z"          →  "2026-07-21T16:00:00Z"
    ""                              →  ""
    """
    if not dt:
        return dt
    # Replace any fractional-second part with .000
    dt = _GRAPH_DT_FRAC.sub(".000", dt)
    # Ensure UTC suffix
    if not dt.endswith("Z") and "+" not in dt and dt.count("-") <= 2:
        dt = dt + "Z"
    return dt


class OutlookNormalizer:
    """
    Pure transformation layer between raw Microsoft Graph JSON and Worky models.

    All methods are stateless — the class exists only to group related
    normalization logic.  No instance state is held.

    Usage
    -----
    ::

        normalizer = OutlookNormalizer()
        context = normalizer.normalize(
            raw_events=calendar_fetcher_result,
            raw_messages=email_fetcher_result,
        )
        # context → OutlookContext
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(
        self,
        raw_events: list[dict[str, Any]],
        raw_messages: list[dict[str, Any]],
        raw_user: dict[str, Any] | None = None,
    ) -> OutlookContext:
        """
        Build an OutlookContext from the raw Graph payloads.

        Parameters
        ----------
        raw_events : list[dict[str, Any]]
            Raw calendar event dicts as returned by CalendarFetcher.fetch().
            May be an empty list.

        raw_messages : list[dict[str, Any]]
            Raw message dicts as returned by EmailFetcher.fetch().
            May be an empty list.

        raw_user : dict[str, Any] | None
            Raw user dict as returned by GraphAPIClient.get_current_user().
            Optional — pass None when user data is unavailable.

        Returns
        -------
        OutlookContext
            Fully populated normalised context.  Empty lists are used when
            the corresponding raw inputs are empty.
        """
        user = self._normalize_user(raw_user) if raw_user else None
        calendar_events = [self._normalize_event(e) for e in raw_events]
        emails = [self._normalize_message(m) for m in raw_messages]

        logger.debug(
            "OutlookNormalizer: normalised %d event(s), %d message(s)",
            len(calendar_events),
            len(emails),
        )

        return OutlookContext(
            user=user,
            calendar_events=calendar_events,
            emails=emails,
        )

    # ------------------------------------------------------------------
    # Internal normalisation helpers
    # ------------------------------------------------------------------

    def _normalize_user(self, raw: dict[str, Any]) -> OutlookUser:
        """
        Map a raw Graph /me response to an OutlookUser.

        All fields except ``id`` are optional in Graph responses.
        """
        return OutlookUser(
            id=raw.get("id", ""),
            display_name=raw.get("displayName", ""),
            email=raw.get("mail", ""),
            user_principal_name=raw.get("userPrincipalName", ""),
        )

    def _normalize_event(self, raw: dict[str, Any]) -> CalendarEvent:
        """
        Map a raw Graph calendarView item to a CalendarEvent.

        Handles missing organizer, missing location, missing onlineMeeting,
        missing subject, and missing bodyPreview defensively.

        Datetime normalisation
        ----------------------
        Graph calendarView returns dateTime strings in one of two forms
        depending on whether a Prefer: outlook.timezone header was sent:

          "2026-07-21T16:00:00.0000000Z"   — UTC (Prefer: outlook.timezone="UTC")
          "2026-07-21T21:30:00.0000000"    — calendar tz, no offset indicator

        The 7-digit fractional second (.0000000) is non-standard.  We strip
        it to plain milliseconds (.000) and ensure the Z suffix is present.
        This guarantees new Date() in any browser always parses as UTC,
        making the epoch-based Upcoming Meetings filter timezone-independent.
        """
        organizer: dict[str, Any] = raw.get("organizer") or {}
        organizer_address: dict[str, Any] = organizer.get("emailAddress") or {}

        location: dict[str, Any] = raw.get("location") or {}

        online_meeting: dict[str, Any] = raw.get("onlineMeeting") or {}
        join_url: str = online_meeting.get("joinUrl", "")
        is_online_meeting: bool = bool(join_url)

        start: dict[str, Any] = raw.get("start") or {}
        end: dict[str, Any] = raw.get("end") or {}

        return CalendarEvent(
            id=raw.get("id", ""),
            subject=raw.get("subject", ""),
            start=_normalise_graph_datetime(start.get("dateTime", "")),
            end=_normalise_graph_datetime(end.get("dateTime", "")),
            start_timezone=start.get("timeZone", "UTC"),
            location=location.get("displayName", ""),
            organizer_name=organizer_address.get("name", ""),
            organizer_email=organizer_address.get("address", ""),
            is_all_day=raw.get("isAllDay", False),
            is_cancelled=raw.get("isCancelled", False),
            is_online_meeting=is_online_meeting,
            join_url=join_url,
            body_preview=raw.get("bodyPreview", ""),
        )

    def _normalize_message(self, raw: dict[str, Any]) -> Email:
        """
        Map a raw Graph /me/messages item to an Email.

        Handles missing from, missing emailAddress, missing subject, and
        missing bodyPreview defensively.
        """
        from_field: dict[str, Any] = raw.get("from") or {}
        email_address: dict[str, Any] = from_field.get("emailAddress") or {}

        return Email(
            id=raw.get("id", ""),
            subject=raw.get("subject", ""),
            sender_name=email_address.get("name", ""),
            sender_email=email_address.get("address", ""),
            received_at=raw.get("receivedDateTime", ""),
            is_read=raw.get("isRead", False),
            importance=raw.get("importance", "normal"),
            body_preview=raw.get("bodyPreview", ""),
            has_attachments=raw.get("hasAttachments", False),
        )

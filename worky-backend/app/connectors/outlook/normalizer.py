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
from typing import Any

from app.connectors.outlook.models import (
    CalendarEvent,
    Email,
    OutlookContext,
    OutlookUser,
)

logger = logging.getLogger(__name__)


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
            start=start.get("dateTime", ""),
            end=end.get("dateTime", ""),
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

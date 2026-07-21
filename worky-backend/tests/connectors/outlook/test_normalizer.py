"""
tests/connectors/outlook/test_normalizer.py
=============================================
Unit tests for OutlookNormalizer.

OutlookNormalizer is a pure function — no I/O, no HTTP, no mocks required
for the normalizer itself.  All tests construct raw Graph-shaped dicts directly
and verify the resulting Worky domain models.

Coverage:
  • normalize() — full input, empty input
  • _normalize_user() — all fields present, all fields absent
  • _normalize_event() — full event, missing organizer, missing location,
    missing onlineMeeting, missing subject, missing bodyPreview,
    online meeting detection via joinUrl
  • _normalize_message() — full message, missing from, missing emailAddress,
    missing subject, missing bodyPreview, importance values
"""

from __future__ import annotations

from typing import Any

import pytest

from app.connectors.outlook.models import CalendarEvent, Email
from app.connectors.outlook.normalizer import OutlookNormalizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_normalizer() -> OutlookNormalizer:
    return OutlookNormalizer()


RAW_USER: dict[str, Any] = {
    "id": "user-abc",
    "displayName": "Alice Smith",
    "mail": "alice@example.com",
    "userPrincipalName": "alice@example.onmicrosoft.com",
}

RAW_EVENT: dict[str, Any] = {
    "id": "evt-001",
    "subject": "Sprint planning",
    "start": {"dateTime": "2024-06-10T09:00:00.0000000", "timeZone": "UTC"},
    "end": {"dateTime": "2024-06-10T10:00:00.0000000", "timeZone": "UTC"},
    "location": {"displayName": "Room A"},
    "organizer": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
    "isAllDay": False,
    "isCancelled": False,
    "onlineMeeting": None,
    "bodyPreview": "Let's plan the sprint.",
}

RAW_EVENT_ONLINE: dict[str, Any] = {
    "id": "evt-002",
    "subject": "1:1",
    "start": {"dateTime": "2024-06-10T11:00:00", "timeZone": "UTC"},
    "end": {"dateTime": "2024-06-10T11:30:00", "timeZone": "UTC"},
    "location": {"displayName": "Teams"},
    "organizer": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
    "isAllDay": False,
    "isCancelled": False,
    "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/join/abc"},
    "bodyPreview": "Weekly sync.",
}

RAW_MESSAGE: dict[str, Any] = {
    "id": "msg-001",
    "subject": "Q3 Review — action required",
    "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
    "receivedDateTime": "2024-06-10T08:15:00Z",
    "isRead": False,
    "importance": "high",
    "bodyPreview": "Please review the attached document.",
    "hasAttachments": True,
}


# ---------------------------------------------------------------------------
# normalize() — full pipeline
# ---------------------------------------------------------------------------

class TestNormalizeFull:

    def test_normalize_returns_outlook_context(self):
        """normalize() returns an OutlookContext."""
        from app.connectors.outlook.models import OutlookContext
        ctx = make_normalizer().normalize(
            raw_events=[RAW_EVENT],
            raw_messages=[RAW_MESSAGE],
        )
        assert isinstance(ctx, OutlookContext)

    def test_normalize_calendar_count(self):
        """normalize() maps all raw events."""
        ctx = make_normalizer().normalize(
            raw_events=[RAW_EVENT, RAW_EVENT_ONLINE],
            raw_messages=[],
        )
        assert len(ctx.calendar_events) == 2

    def test_normalize_email_count(self):
        """normalize() maps all raw messages."""
        ctx = make_normalizer().normalize(
            raw_events=[],
            raw_messages=[RAW_MESSAGE],
        )
        assert len(ctx.emails) == 1

    def test_normalize_empty_inputs(self):
        """normalize() with empty inputs returns an empty OutlookContext."""
        ctx = make_normalizer().normalize(raw_events=[], raw_messages=[])
        assert ctx.user is None
        assert ctx.calendar_events == []
        assert ctx.emails == []

    def test_normalize_with_user(self):
        """normalize() with raw_user populates user field."""
        ctx = make_normalizer().normalize(
            raw_events=[],
            raw_messages=[],
            raw_user=RAW_USER,
        )
        assert ctx.user is not None
        assert ctx.user.id == "user-abc"

    def test_normalize_without_user(self):
        """normalize() without raw_user leaves user as None."""
        ctx = make_normalizer().normalize(raw_events=[], raw_messages=[])
        assert ctx.user is None

    def test_normalize_preserves_event_order(self):
        """normalize() returns calendar_events in the same order as raw_events."""
        raw_a = {**RAW_EVENT, "id": "evt-001", "subject": "First"}
        raw_b = {**RAW_EVENT, "id": "evt-002", "subject": "Second"}
        raw_c = {**RAW_EVENT, "id": "evt-003", "subject": "Third"}
        ctx = make_normalizer().normalize(
            raw_events=[raw_a, raw_b, raw_c],
            raw_messages=[],
        )
        assert [e.id for e in ctx.calendar_events] == ["evt-001", "evt-002", "evt-003"]

    def test_normalize_preserves_message_order(self):
        """normalize() returns emails in the same order as raw_messages."""
        raw_a = {**RAW_MESSAGE, "id": "msg-001", "subject": "First"}
        raw_b = {**RAW_MESSAGE, "id": "msg-002", "subject": "Second"}
        ctx = make_normalizer().normalize(
            raw_events=[],
            raw_messages=[raw_a, raw_b],
        )
        assert [e.id for e in ctx.emails] == ["msg-001", "msg-002"]

    def test_normalize_calendar_events_are_calendar_event_instances(self):
        """Items in ctx.calendar_events are CalendarEvent instances."""
        ctx = make_normalizer().normalize(
            raw_events=[RAW_EVENT, RAW_EVENT_ONLINE],
            raw_messages=[],
        )
        for item in ctx.calendar_events:
            assert isinstance(item, CalendarEvent)

    def test_normalize_emails_are_email_instances(self):
        """Items in ctx.emails are Email instances."""
        ctx = make_normalizer().normalize(
            raw_events=[],
            raw_messages=[RAW_MESSAGE],
        )
        for item in ctx.emails:
            assert isinstance(item, Email)


# ---------------------------------------------------------------------------
# _normalize_user()
# ---------------------------------------------------------------------------

class TestNormalizeUser:

    def test_all_fields_mapped(self):
        """All Graph /me fields map to OutlookUser fields."""
        normalizer = make_normalizer()
        user = normalizer._normalize_user(RAW_USER)
        assert user.id == "user-abc"
        assert user.display_name == "Alice Smith"
        assert user.email == "alice@example.com"
        assert user.user_principal_name == "alice@example.onmicrosoft.com"

    def test_all_fields_absent(self):
        """Missing optional fields fall back to empty string."""
        normalizer = make_normalizer()
        user = normalizer._normalize_user({})
        assert user.id == ""
        assert user.display_name == ""
        assert user.email == ""
        assert user.user_principal_name == ""

    def test_partial_fields(self):
        """Only id and mail present — other fields default to empty string."""
        normalizer = make_normalizer()
        user = normalizer._normalize_user({"id": "u1", "mail": "u1@example.com"})
        assert user.id == "u1"
        assert user.email == "u1@example.com"
        assert user.display_name == ""


# ---------------------------------------------------------------------------
# _normalize_event()
# ---------------------------------------------------------------------------

class TestNormalizeEvent:

    def test_full_event_mapped_correctly(self):
        """All fields of a fully-populated event are mapped correctly."""
        normalizer = make_normalizer()
        event = normalizer._normalize_event(RAW_EVENT)
        assert event.id == "evt-001"
        assert event.subject == "Sprint planning"
        assert event.start == "2024-06-10T09:00:00.000Z"
        assert event.end == "2024-06-10T10:00:00.000Z"
        assert event.start_timezone == "UTC"
        assert event.location == "Room A"
        assert event.organizer_name == "Bob"
        assert event.organizer_email == "bob@example.com"
        assert event.is_all_day is False
        assert event.is_cancelled is False
        assert event.body_preview == "Let's plan the sprint."

    def test_online_meeting_detected_via_join_url(self):
        """is_online_meeting is True when onlineMeeting.joinUrl is present."""
        normalizer = make_normalizer()
        event = normalizer._normalize_event(RAW_EVENT_ONLINE)
        assert event.is_online_meeting is True
        assert event.join_url == "https://teams.microsoft.com/join/abc"

    def test_online_meeting_false_when_none(self):
        """is_online_meeting is False when onlineMeeting is None."""
        normalizer = make_normalizer()
        event = normalizer._normalize_event(RAW_EVENT)
        assert event.is_online_meeting is False
        assert event.join_url == ""

    def test_missing_organizer_defaults_to_empty(self):
        """Missing organizer field does not raise — defaults to empty strings."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT}
        del raw["organizer"]
        event = normalizer._normalize_event(raw)
        assert event.organizer_name == ""
        assert event.organizer_email == ""

    def test_organizer_without_email_address(self):
        """organizer present but emailAddress absent — defaults to empty strings."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT, "organizer": {}}
        event = normalizer._normalize_event(raw)
        assert event.organizer_name == ""
        assert event.organizer_email == ""

    def test_missing_location_defaults_to_empty(self):
        """Missing location field does not raise — defaults to empty string."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT}
        del raw["location"]
        event = normalizer._normalize_event(raw)
        assert event.location == ""

    def test_missing_subject_defaults_to_empty(self):
        """Missing subject field defaults to empty string."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT}
        del raw["subject"]
        event = normalizer._normalize_event(raw)
        assert event.subject == ""

    def test_missing_body_preview_defaults_to_empty(self):
        """Missing bodyPreview field defaults to empty string."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT}
        del raw["bodyPreview"]
        event = normalizer._normalize_event(raw)
        assert event.body_preview == ""

    def test_missing_start_end_default_to_empty(self):
        """Missing start/end fields default to empty string."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT}
        del raw["start"]
        del raw["end"]
        event = normalizer._normalize_event(raw)
        assert event.start == ""
        assert event.end == ""

    def test_is_cancelled_true(self):
        """isCancelled=True is mapped correctly."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT, "isCancelled": True}
        event = normalizer._normalize_event(raw)
        assert event.is_cancelled is True

    def test_is_all_day_true(self):
        """isAllDay=True is mapped correctly."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT, "isAllDay": True}
        event = normalizer._normalize_event(raw)
        assert event.is_all_day is True

    def test_completely_empty_event_does_not_raise(self):
        """An empty dict does not raise — all fields fall back to defaults."""
        normalizer = make_normalizer()
        event = normalizer._normalize_event({"id": "e1"})
        assert event.id == "e1"
        assert event.subject == ""
        assert event.is_online_meeting is False

    def test_online_meeting_key_present_join_url_absent(self):
        """onlineMeeting dict present but joinUrl key absent → is_online_meeting False."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT, "onlineMeeting": {}}
        event = normalizer._normalize_event(raw)
        assert event.is_online_meeting is False
        assert event.join_url == ""

    def test_organizer_none_explicitly(self):
        """organizer explicitly set to None → organizer fields default to empty strings."""
        normalizer = make_normalizer()
        raw = {**RAW_EVENT, "organizer": None}
        event = normalizer._normalize_event(raw)
        assert event.organizer_name == ""
        assert event.organizer_email == ""


# ---------------------------------------------------------------------------
# _normalize_message()
# ---------------------------------------------------------------------------

class TestNormalizeMessage:

    def test_full_message_mapped_correctly(self):
        """All fields of a fully-populated message are mapped correctly."""
        normalizer = make_normalizer()
        email = normalizer._normalize_message(RAW_MESSAGE)
        assert email.id == "msg-001"
        assert email.subject == "Q3 Review — action required"
        assert email.sender_name == "Alice"
        assert email.sender_email == "alice@example.com"
        assert email.received_at == "2024-06-10T08:15:00Z"
        assert email.is_read is False
        assert email.importance == "high"
        assert email.body_preview == "Please review the attached document."
        assert email.has_attachments is True

    def test_missing_from_field_defaults_to_empty(self):
        """Missing from field does not raise — sender fields default to empty."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE}
        del raw["from"]
        email = normalizer._normalize_message(raw)
        assert email.sender_name == ""
        assert email.sender_email == ""

    def test_from_without_email_address(self):
        """from present but emailAddress absent — defaults to empty strings."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE, "from": {}}
        email = normalizer._normalize_message(raw)
        assert email.sender_name == ""
        assert email.sender_email == ""

    def test_missing_subject_defaults_to_empty(self):
        """Missing subject defaults to empty string."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE}
        del raw["subject"]
        email = normalizer._normalize_message(raw)
        assert email.subject == ""

    def test_missing_body_preview_defaults_to_empty(self):
        """Missing bodyPreview defaults to empty string."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE}
        del raw["bodyPreview"]
        email = normalizer._normalize_message(raw)
        assert email.body_preview == ""

    def test_is_read_true(self):
        """isRead=True is mapped correctly."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE, "isRead": True}
        email = normalizer._normalize_message(raw)
        assert email.is_read is True

    def test_importance_normal(self):
        """importance='normal' is mapped correctly."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE, "importance": "normal"}
        email = normalizer._normalize_message(raw)
        assert email.importance == "normal"

    def test_importance_defaults_to_normal_when_absent(self):
        """Missing importance defaults to 'normal'."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE}
        del raw["importance"]
        email = normalizer._normalize_message(raw)
        assert email.importance == "normal"

    def test_has_attachments_false(self):
        """hasAttachments=False is mapped correctly."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE, "hasAttachments": False}
        email = normalizer._normalize_message(raw)
        assert email.has_attachments is False

    def test_completely_empty_message_does_not_raise(self):
        """An empty dict does not raise — all fields fall back to defaults."""
        normalizer = make_normalizer()
        email = normalizer._normalize_message({"id": "m1"})
        assert email.id == "m1"
        assert email.subject == ""
        assert email.importance == "normal"

    def test_from_none_explicitly(self):
        """from field explicitly set to None → sender fields default to empty strings."""
        normalizer = make_normalizer()
        raw = {**RAW_MESSAGE, "from": None}
        email = normalizer._normalize_message(raw)
        assert email.sender_name == ""
        assert email.sender_email == ""

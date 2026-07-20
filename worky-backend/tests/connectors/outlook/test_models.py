"""
tests/connectors/outlook/test_models.py
========================================
Unit tests for Outlook domain models.

Coverage:
  • OutlookUser — instantiation, field defaults, required field
  • CalendarEvent — instantiation, field defaults, required field
  • Email — instantiation, field defaults, required field
  • OutlookContext — instantiation, empty defaults, model_dump round-trip
"""

from __future__ import annotations

import pytest

from app.connectors.outlook.models import (
    CalendarEvent,
    Email,
    OutlookContext,
    OutlookUser,
)


# ---------------------------------------------------------------------------
# OutlookUser
# ---------------------------------------------------------------------------

class TestOutlookUser:

    def test_instantiation_with_all_fields(self):
        """OutlookUser can be constructed with all fields."""
        user = OutlookUser(
            id="user-001",
            display_name="Alice Smith",
            email="alice@example.com",
            user_principal_name="alice@example.com",
        )
        assert user.id == "user-001"
        assert user.display_name == "Alice Smith"
        assert user.email == "alice@example.com"
        assert user.user_principal_name == "alice@example.com"

    def test_id_is_required(self):
        """id is a required field — omitting it raises ValidationError."""
        with pytest.raises(Exception):
            OutlookUser()  # type: ignore[call-arg]

    def test_optional_fields_default_to_empty_string(self):
        """display_name, email, and user_principal_name default to empty string."""
        user = OutlookUser(id="u1")
        assert user.display_name == ""
        assert user.email == ""
        assert user.user_principal_name == ""

    def test_model_dump_returns_dict(self):
        """model_dump() returns a plain dict with all fields."""
        user = OutlookUser(id="u1", display_name="Bob")
        dumped = user.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["id"] == "u1"
        assert dumped["display_name"] == "Bob"

    def test_model_dump_contains_all_field_names(self):
        """model_dump() contains every declared field key."""
        user = OutlookUser(id="u1")
        dumped = user.model_dump()
        assert set(dumped.keys()) == {"id", "display_name", "email", "user_principal_name"}


# ---------------------------------------------------------------------------
# CalendarEvent
# ---------------------------------------------------------------------------

class TestCalendarEvent:

    def test_instantiation_with_all_fields(self):
        """CalendarEvent can be constructed with all fields."""
        event = CalendarEvent(
            id="evt-001",
            subject="Sprint planning",
            start="2024-06-10T09:00:00",
            end="2024-06-10T10:00:00",
            location="Room A",
            organizer_name="Bob",
            organizer_email="bob@example.com",
            is_all_day=False,
            is_cancelled=False,
            is_online_meeting=True,
            join_url="https://teams.microsoft.com/join/abc",
            body_preview="Let's plan.",
        )
        assert event.id == "evt-001"
        assert event.subject == "Sprint planning"
        assert event.is_online_meeting is True
        assert event.join_url == "https://teams.microsoft.com/join/abc"

    def test_id_is_required(self):
        """id is a required field."""
        with pytest.raises(Exception):
            CalendarEvent()  # type: ignore[call-arg]

    def test_optional_fields_have_correct_defaults(self):
        """All optional fields default to their specified values."""
        event = CalendarEvent(id="evt-001")
        assert event.subject == ""
        assert event.start == ""
        assert event.end == ""
        assert event.location == ""
        assert event.organizer_name == ""
        assert event.organizer_email == ""
        assert event.is_all_day is False
        assert event.is_cancelled is False
        assert event.is_online_meeting is False
        assert event.join_url == ""
        assert event.body_preview == ""

    def test_model_dump_returns_dict(self):
        """model_dump() returns a plain dict with all fields."""
        event = CalendarEvent(id="evt-001", subject="Standup")
        dumped = event.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["id"] == "evt-001"
        assert dumped["subject"] == "Standup"

    def test_model_dump_contains_all_field_names(self):
        """model_dump() contains every declared field key."""
        event = CalendarEvent(id="evt-001")
        dumped = event.model_dump()
        assert set(dumped.keys()) == {
            "id",
            "subject",
            "start",
            "end",
            "location",
            "organizer_name",
            "organizer_email",
            "is_all_day",
            "is_cancelled",
            "is_online_meeting",
            "join_url",
            "body_preview",
        }


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

class TestEmail:

    def test_instantiation_with_all_fields(self):
        """Email can be constructed with all fields."""
        email = Email(
            id="msg-001",
            subject="Q3 Review",
            sender_name="Alice",
            sender_email="alice@example.com",
            received_at="2024-06-10T08:15:00Z",
            is_read=False,
            importance="high",
            body_preview="Please review.",
            has_attachments=True,
        )
        assert email.id == "msg-001"
        assert email.subject == "Q3 Review"
        assert email.importance == "high"
        assert email.has_attachments is True

    def test_id_is_required(self):
        """id is a required field."""
        with pytest.raises(Exception):
            Email()  # type: ignore[call-arg]

    def test_optional_fields_have_correct_defaults(self):
        """All optional fields default to their specified values."""
        email = Email(id="msg-001")
        assert email.subject == ""
        assert email.sender_name == ""
        assert email.sender_email == ""
        assert email.received_at == ""
        assert email.is_read is False
        assert email.importance == "normal"
        assert email.body_preview == ""
        assert email.has_attachments is False

    def test_model_dump_returns_dict(self):
        """model_dump() returns a plain dict with all fields."""
        email = Email(id="msg-001", subject="Hello")
        dumped = email.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["id"] == "msg-001"
        assert dumped["subject"] == "Hello"

    def test_model_dump_contains_all_field_names(self):
        """model_dump() contains every declared field key."""
        email = Email(id="msg-001")
        dumped = email.model_dump()
        assert set(dumped.keys()) == {
            "id",
            "subject",
            "sender_name",
            "sender_email",
            "received_at",
            "is_read",
            "importance",
            "body_preview",
            "has_attachments",
        }


# ---------------------------------------------------------------------------
# OutlookContext
# ---------------------------------------------------------------------------

class TestOutlookContext:

    def test_instantiation_with_no_arguments(self):
        """OutlookContext can be constructed with no arguments (all optional)."""
        ctx = OutlookContext()
        assert ctx.user is None
        assert ctx.calendar_events == []
        assert ctx.emails == []

    def test_instantiation_with_all_fields(self):
        """OutlookContext can be constructed with all fields."""
        user = OutlookUser(id="u1")
        event = CalendarEvent(id="e1")
        email = Email(id="m1")
        ctx = OutlookContext(user=user, calendar_events=[event], emails=[email])
        assert ctx.user is not None
        assert ctx.user.id == "u1"
        assert len(ctx.calendar_events) == 1
        assert len(ctx.emails) == 1

    def test_model_dump_round_trip(self):
        """model_dump() produces a dict that model_validate() can reconstruct."""
        user = OutlookUser(id="u1", display_name="Alice")
        event = CalendarEvent(id="e1", subject="Standup")
        email = Email(id="m1", subject="Hello")
        ctx = OutlookContext(user=user, calendar_events=[event], emails=[email])
        dumped = ctx.model_dump()
        restored = OutlookContext.model_validate(dumped)
        assert restored.user is not None
        assert restored.user.id == "u1"
        assert restored.calendar_events[0].subject == "Standup"
        assert restored.emails[0].subject == "Hello"

    def test_empty_context_model_dump(self):
        """An empty OutlookContext serialises to the expected shape."""
        ctx = OutlookContext()
        dumped = ctx.model_dump()
        assert dumped["user"] is None
        assert dumped["calendar_events"] == []
        assert dumped["emails"] == []

    def test_calendar_events_default_factory_is_independent(self):
        """Two OutlookContext instances do not share the same list object."""
        ctx_a = OutlookContext()
        ctx_b = OutlookContext()
        ctx_a.calendar_events.append(CalendarEvent(id="e1"))
        assert len(ctx_b.calendar_events) == 0

    def test_emails_default_factory_is_independent(self):
        """Two OutlookContext instances do not share the same emails list."""
        ctx_a = OutlookContext()
        ctx_b = OutlookContext()
        ctx_a.emails.append(Email(id="m1"))
        assert len(ctx_b.emails) == 0

    def test_model_dump_nested_objects_are_plain_dicts(self):
        """model_dump() converts nested Pydantic models to plain dicts, not model instances."""
        user = OutlookUser(id="u1", display_name="Alice")
        event = CalendarEvent(id="e1", subject="Standup")
        email = Email(id="m1", subject="Hello")
        ctx = OutlookContext(user=user, calendar_events=[event], emails=[email])
        dumped = ctx.model_dump()
        assert isinstance(dumped["user"], dict)
        assert isinstance(dumped["calendar_events"][0], dict)
        assert isinstance(dumped["emails"][0], dict)
        # Must not be Pydantic model instances
        assert not isinstance(dumped["user"], OutlookUser)
        assert not isinstance(dumped["calendar_events"][0], CalendarEvent)
        assert not isinstance(dumped["emails"][0], Email)

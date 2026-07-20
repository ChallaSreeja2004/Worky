"""
app/connectors/outlook/models.py
=================================
Worky-internal Pydantic models for the Outlook connector.

These models represent the normalised Outlook data that the OutlookNormalizer
produces and the OutlookConnector places into ConnectorResult.data.  They are
internal domain models — not mirrors of Microsoft Graph API response shapes.

WHAT THIS MODULE DOES
---------------------
  • Define the typed schema for normalised Outlook data.
  • Serve as the validated output of OutlookNormalizer.
  • Provide the shape that ConnectorResult.data holds for the "outlook" source.

WHAT THIS MODULE DOES NOT DO
-----------------------------
  • It does NOT make any HTTP requests.
  • It does NOT call any Graph API.
  • It does NOT contain any business logic or transformation logic.
  • It does NOT import from graph_client or any fetcher.

IMPORT RULES
------------
This module may only import from:
  • Python standard library
  • Pydantic

It must NOT import from:
  • app.auth
  • app.config
  • app.connectors.base
  • app.connectors.models
  • app.connectors.outlook.graph_client
  • app.context_builder
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class OutlookUser(BaseModel):
    """
    Normalised representation of the signed-in Microsoft 365 user.

    Fields
    ------
    id : str
        Azure AD object ID.  Stable identifier across sessions.

    display_name : str
        Full name from the enterprise directory.

    email : str
        Primary SMTP address.

    user_principal_name : str
        UPN / login address (may differ from email in some tenants).
    """

    id: str = Field(..., description="Azure AD object ID.")
    display_name: str = Field(default="", description="Full name.")
    email: str = Field(default="", description="Primary SMTP address.")
    user_principal_name: str = Field(default="", description="UPN / login address.")


class CalendarEvent(BaseModel):
    """
    Normalised representation of a single Microsoft 365 calendar event.

    Fields map to the subset of Graph fields requested by
    GraphAPIClient.get_calendar_events():
    id, subject, start, end, location, organizer,
    isAllDay, isCancelled, onlineMeeting, bodyPreview.

    Fields
    ------
    id : str
        Graph event ID.

    subject : str
        Event title.  Empty string when Graph omits the field.

    start : str
        ISO 8601 start datetime string as returned by Graph.

    end : str
        ISO 8601 end datetime string as returned by Graph.

    location : str
        Display name of the meeting location.  Empty string when absent.

    organizer_name : str
        Display name of the event organiser.  Empty string when absent.

    organizer_email : str
        Email address of the event organiser.  Empty string when absent.

    is_all_day : bool
        True when the event spans the entire day.

    is_cancelled : bool
        True when the event has been cancelled.

    is_online_meeting : bool
        True when the event has an online meeting link.

    join_url : str
        Online meeting join URL.  Empty string when the event is not online.

    body_preview : str
        Short plain-text excerpt of the event body.  Empty string when absent.
    """

    id: str = Field(..., description="Graph event ID.")
    subject: str = Field(default="", description="Event title.")
    start: str = Field(default="", description="ISO 8601 start datetime string.")
    end: str = Field(default="", description="ISO 8601 end datetime string.")
    location: str = Field(default="", description="Meeting location display name.")
    organizer_name: str = Field(default="", description="Organiser display name.")
    organizer_email: str = Field(default="", description="Organiser email address.")
    is_all_day: bool = Field(default=False, description="True for all-day events.")
    is_cancelled: bool = Field(default=False, description="True for cancelled events.")
    is_online_meeting: bool = Field(default=False, description="True when a join URL is present.")
    join_url: str = Field(default="", description="Online meeting join URL.")
    body_preview: str = Field(default="", description="Short plain-text body excerpt.")


class Email(BaseModel):
    """
    Normalised representation of a single Microsoft 365 email message.

    Fields map to the subset of Graph fields requested by
    GraphAPIClient.get_messages():
    id, subject, from, receivedDateTime,
    isRead, importance, bodyPreview, hasAttachments.

    Fields
    ------
    id : str
        Graph message ID.

    subject : str
        Email subject line.  Empty string when absent.

    sender_name : str
        Display name of the sender.  Empty string when absent.

    sender_email : str
        Email address of the sender.  Empty string when absent.

    received_at : str
        ISO 8601 received datetime string as returned by Graph.

    is_read : bool
        True when the message has been read.

    importance : str
        Importance level: "low", "normal", or "high".

    body_preview : str
        Short plain-text excerpt of the email body.

    has_attachments : bool
        True when the message has one or more attachments.
    """

    id: str = Field(..., description="Graph message ID.")
    subject: str = Field(default="", description="Email subject line.")
    sender_name: str = Field(default="", description="Sender display name.")
    sender_email: str = Field(default="", description="Sender email address.")
    received_at: str = Field(default="", description="ISO 8601 received datetime string.")
    is_read: bool = Field(default=False, description="True when the message has been read.")
    importance: str = Field(default="normal", description="Importance level: low, normal, or high.")
    body_preview: str = Field(default="", description="Short plain-text body excerpt.")
    has_attachments: bool = Field(default=False, description="True when attachments are present.")


class OutlookContext(BaseModel):
    """
    The normalised Outlook payload assembled by OutlookNormalizer.

    This is the object that OutlookConnector places into ConnectorResult.data
    via model_dump().  The Context Builder passes it wholesale to WorkContext;
    IBM Bob receives it as part of the "outlook" source dictionary.

    Fields
    ------
    user : OutlookUser | None
        The signed-in user's profile.  None when user data is unavailable.

    calendar_events : list[CalendarEvent]
        Today's calendar events, sorted by start time (Graph ordering preserved).

    emails : list[Email]
        Unread and high-importance emails, sorted by received time descending
        (Graph ordering preserved).
    """

    user: Optional[OutlookUser] = Field(
        default=None,
        description="Signed-in user profile.  None when unavailable.",
    )

    calendar_events: list[CalendarEvent] = Field(
        default_factory=list,
        description="Today's calendar events.",
    )

    emails: list[Email] = Field(
        default_factory=list,
        description="Unread and high-importance email messages.",
    )

    model_config = {"frozen": False}

"""
app/connectors/outlook/__init__.py
===================================
Outlook connector package.

This package contains all modules responsible for integrating with
Microsoft Outlook via the Microsoft Graph API.

Phase 2 contents:
  settings.py — OutlookSettings (OAuth configuration)

Future phases will add:
  graph_client.py  — GraphAPIClient (Phase 3)
  fetchers/        — CalendarFetcher, EmailFetcher (Phases 4–5)
  normalizer.py    — OutlookNormalizer (Phase 6)
  models.py        — OutlookContext, CalendarEvent, Email (Phase 6)
  connector.py     — OutlookConnector(BaseConnector) (Phase 7)
"""

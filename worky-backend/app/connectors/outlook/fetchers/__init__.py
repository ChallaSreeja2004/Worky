"""
app/connectors/outlook/fetchers/
=================================
Fetcher sub-package for the Outlook connector.

Each fetcher owns a single data-collection responsibility:
  calendar.py  — CalendarFetcher  (Phase 4)
  email.py     — EmailFetcher     (Phase 5)

Fetchers sit between GraphAPIClient and the normalizer.  They call one Graph
client method, extract the ``value`` list from the response envelope, and
return raw Graph dicts unchanged.  No transformation, filtering, or error
handling belongs here.
"""

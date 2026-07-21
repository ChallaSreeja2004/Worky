"""
app/recommendations/dependencies.py
=====================================
FastAPI dependency providers for the Recommendation Service layer.

DESIGN RATIONALE
----------------
These functions are the single point of wiring between FastAPI's dependency
injection system and the Recommendation Service.  They ensure:

  • RecommendationService is never instantiated directly inside routers.
  • AuthService, ContextBuilder, and connectors are obtained through DI so
    they can be replaced with test doubles without changing the router.
  • Each dependency provider has a single responsibility.

CONNECTOR MODE
--------------
get_outlook_connector() reads CONNECTOR_MODE from AppSettings and returns
the appropriate connector:

  CONNECTOR_MODE=outlook  → OutlookConnector wired to a real GraphAPIClient
  CONNECTOR_MODE=demo     → DemoOutlookConnector (no credentials required)

No other component in the pipeline knows which connector is active.

IMPORT RULES
------------
This module may import from:
  • Python standard library
  • FastAPI
  • app.auth.dependencies
  • app.auth.service            (AuthService — type annotation only)
  • app.bob.dependencies
  • app.bob.service             (BobService interface — type annotation only)
  • app.config.settings
  • app.connectors.base         (BaseConnector — type annotation only)
  • app.connectors.demo.connector
  • app.connectors.outlook.*
  • app.context_builder.builder
  • app.recommendations.service
"""

from __future__ import annotations

from app.auth.dependencies import get_auth_service
from app.auth.service import AuthService
from app.bob.dependencies import get_bob_service
from app.bob.service import BobService
from app.config.settings import get_settings
from app.connectors.base import BaseConnector
from app.connectors.demo.connector import DemoOutlookConnector
from app.connectors.outlook.connector import OutlookConnector
from app.connectors.outlook.graph_client import GraphAPIClient
from app.connectors.outlook.normalizer import OutlookNormalizer
from app.context_builder.builder import ContextBuilder
from app.recommendations.service import RecommendationService


def get_recommendation_service() -> RecommendationService:
    """
    FastAPI dependency provider for RecommendationService.

    Constructs a RecommendationService wired to the shared BobService
    singleton returned by get_bob_service().

    Usage in a router or scheduler:
    ::

        async def my_endpoint(
            rec_service: RecommendationService = Depends(
                get_recommendation_service
            ),
        ) -> ...:
            result = await rec_service.generate(work_context)
    """
    bob_service: BobService = get_bob_service()
    return RecommendationService(bob_service=bob_service)


def get_context_builder() -> ContextBuilder:
    """
    FastAPI dependency provider for ContextBuilder.

    Returns a fresh stateless ContextBuilder.  ContextBuilder holds no
    per-user state so a new instance per request is correct and cheap.
    """
    return ContextBuilder()


def get_auth_service_dep() -> AuthService:
    """
    FastAPI dependency provider for AuthService.

    Thin wrapper around get_auth_service() from app.auth.dependencies so
    the recommendations router can declare it without importing the auth
    package directly.
    """
    return get_auth_service()


def build_outlook_connector(access_token: str) -> OutlookConnector:
    """
    Construct a fully-wired OutlookConnector for the given access token.

    Called by the router after obtaining a valid token from AuthService.
    Returns a fresh connector instance scoped to this request's token —
    GraphAPIClient is not a singleton (it carries a bearer token).

    Used only in CONNECTOR_MODE=outlook.  In demo mode the router uses
    get_outlook_connector() which returns DemoOutlookConnector instead.
    """
    client = GraphAPIClient(access_token=access_token)
    normalizer = OutlookNormalizer()
    return OutlookConnector(graph_client=client, normalizer=normalizer)


def get_outlook_connector(access_token: str = "") -> BaseConnector:
    """
    Return the active Outlook connector based on CONNECTOR_MODE.

    In production (CONNECTOR_MODE=outlook):
        Returns an OutlookConnector wired to a real GraphAPIClient carrying
        the provided access_token.  The access_token must be a valid,
        non-empty Microsoft bearer token.

    In demo mode (CONNECTOR_MODE=demo):
        Returns a DemoOutlookConnector.  The access_token parameter is
        accepted for interface compatibility but is not used.

    This is the single switchable seam in the pipeline.  All components
    above this layer (ContextBuilder, RecommendationService, BobCLIService)
    receive an identical ConnectorResult regardless of which branch is taken.
    """
    settings = get_settings()
    if settings.connector_mode == "demo":
        return DemoOutlookConnector()
    return build_outlook_connector(access_token)

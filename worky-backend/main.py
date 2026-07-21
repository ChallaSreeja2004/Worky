"""
main.py
=======
Worky Backend — FastAPI application entry point.

Responsibilities
----------------
  1. Configure structured logging.
  2. Instantiate the FastAPI application with versioned route prefixes.
  3. Register CORS middleware.
  4. Mount all routers.
  5. Wire the dependency-injection container (token repository, services).

NOTE: This file mounts only the /health endpoint for now.  The auth and
connector routers are commented in with clear markers so teammates know
exactly where to add their router as each layer is implemented.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config.settings import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Worky Backend",
    description=(
        "Intelligent desktop companion — enterprise connector API. "
        "Powered by IBM Bob."
    ),
    version="0.1.0",
    # Swagger UI is only available in development.  In production, /docs
    # returns 404 — no accidental API exposure.
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    # Electron dev server origin.  In production, replace with the packaged
    # app's custom scheme (e.g., "worky://") or remove if the API is only
    # called from localhost.
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------------------------------------------------------------------------
# Routers — mount as each layer is implemented
# ---------------------------------------------------------------------------

# Auth layer — Phase 2
app.include_router(auth_router, prefix=f"{settings.api_v1_prefix}/auth", tags=["Authentication"])

# Outlook connector — Phase 7
from app.connectors.outlook.router import router as outlook_router
app.include_router(outlook_router, prefix=f"{settings.api_v1_prefix}/connectors/outlook", tags=["Outlook"])

# Slack connector
from app.connectors.slack.router import router as slack_router
app.include_router(slack_router, prefix=f"{settings.api_v1_prefix}/connectors/slack", tags=["Slack"])

# GitHub connector
from app.connectors.github.router import router as github_router
app.include_router(github_router, prefix=f"{settings.api_v1_prefix}/connectors/github", tags=["GitHub"])

# Recommendations (widget-facing API) — Phase 12
from app.recommendations.router import router as recommendations_router
app.include_router(recommendations_router, prefix=f"{settings.api_v1_prefix}/recommendations", tags=["Recommendations"])

# Demo routers — only mounted when CONNECTOR_MODE=demo.
# Provides:
#   POST /api/v1/auth/demo               — synthetic session creation (auth_router)
#   GET  /api/v1/connectors/demo/context — synthetic Outlook context  (context_router)
# In production (CONNECTOR_MODE=outlook) these routes are never mounted,
# so they cannot be discovered or accidentally called.
if settings.connector_mode == "demo":
    from app.connectors.demo.router import auth_router as demo_auth_router
    from app.connectors.demo.router import context_router as demo_context_router
    app.include_router(demo_auth_router,    prefix=f"{settings.api_v1_prefix}/auth",            tags=["Demo"])
    app.include_router(demo_context_router, prefix=f"{settings.api_v1_prefix}/connectors/demo", tags=["Demo"])
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "DEMO MODE ACTIVE — DemoOutlookConnector is in use. "
        "Set CONNECTOR_MODE=outlook to use the production Microsoft Graph path."
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """
    Basic liveness probe.

    Returns service name and environment.  Does not check downstream
    dependencies — use /api/v1/health/detailed for dependency checks
    (to be implemented alongside the Context Builder).
    """
    return {
        "status": "ok",
        "service": "worky-backend",
        "environment": settings.app_env,
    }

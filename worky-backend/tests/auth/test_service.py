"""
tests/auth/test_service.py
==========================
Unit tests for AuthService.

ALL tests run without real Microsoft credentials.  Microsoft's token
endpoint is mocked with respx.  No test requires internet access.

Test coverage:
  • PKCE generation (verifier length, challenge derivation, uniqueness)
  • State parameter generation (uniqueness)
  • Authorization URL structure
  • exchange_code_for_tokens — success path
  • exchange_code_for_tokens — invalid state (CSRF protection)
  • exchange_code_for_tokens — Microsoft error response
  • exchange_code_for_tokens — network failure
  • get_valid_token — token is fresh (no refresh needed)
  • get_valid_token — token is expired (silent refresh)
  • get_valid_token — user not found
  • _refresh_token — success path
  • _refresh_token — Microsoft returns error
  • revoke_token — removes entry from repository
  • Fernet encrypt/decrypt round-trip
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import respx
from cryptography.fernet import Fernet
from httpx import Response

from app.auth.models import TokenData
from app.auth.repository import InMemoryTokenRepository
from app.auth.service import (
    AuthCodeExchangeError,
    AuthRefreshError,
    AuthService,
    AuthStateError,
    AuthUserNotFoundError,
)
from app.connectors.outlook.settings import OutlookSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_service(
    repo: InMemoryTokenRepository | None = None,
    encryption_key: str | None = None,
    client_secret: str = "test-client-secret",
) -> AuthService:
    """
    Build an AuthService wired to a fresh InMemoryTokenRepository and
    a test-only Fernet key, without touching real environment variables.

    client_secret defaults to a non-empty sentinel so tests that only care
    about PKCE / state / encryption do not need to specify it explicitly.
    The value is also plumbed into OutlookSettings so the validator does not
    reject a missing secret during test construction.
    """
    if repo is None:
        repo = InMemoryTokenRepository()
    if encryption_key is None:
        encryption_key = Fernet.generate_key().decode()

    outlook_settings = OutlookSettings(
        outlook_client_id="test-client-id",
        outlook_tenant_id="test-tenant-id",
        outlook_redirect_uri="http://localhost:8000/api/v1/auth/callback",
        outlook_client_secret=client_secret,
    )

    with (
        patch("app.auth.service.get_settings") as mock_app_settings,
        patch("app.auth.service.get_outlook_settings", return_value=outlook_settings),
    ):
        mock_app_settings.return_value.token_encryption_key = encryption_key
        service = AuthService(token_repository=repo)
        # Attach outlook_settings for token_url access in tests
        service._test_outlook = outlook_settings
        return service


def make_token_response(user_oid: str = "user-oid-001") -> dict:
    """
    Build a mock Microsoft token response WITH an id_token JWT.

    The id_token is a valid (but unsigned) JWT containing the user's identity.
    """
    # Build minimal JWT claims
    claims = {
        "oid": user_oid,
        "name": "Test User",
        "preferred_username": "test@example.com",
    }
    payload_json = base64.urlsafe_b64encode(
        str(claims).replace("'", '"').encode()
    ).decode().rstrip("=")

    # A minimal JWT is header.payload.signature; we skip signature verification
    # so the header and signature can be placeholders.
    id_token = f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{payload_json}.placeholder_sig"

    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
        "id_token": id_token,
    }


def make_token_response_no_id_token() -> dict:
    """
    Build a mock Microsoft token response WITHOUT an id_token.

    Simulates the case where OIDC scopes were not requested, the tenant
    policy strips the id_token, or the token endpoint simply omits it.
    AuthService must fall back to Graph /me for identity in this case.
    """
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
        # id_token intentionally absent
    }


GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"


def make_graph_me_response(
    user_id: str = "graph-user-001",
    display_name: str = "Graph User",
    mail: str | None = "graph@example.com",
    user_principal_name: str = "graph@example.com",
) -> dict:
    """Build a minimal Graph /me response."""
    return {
        "id": user_id,
        "displayName": display_name,
        "mail": mail,
        "userPrincipalName": user_principal_name,
    }


# ---------------------------------------------------------------------------
# PKCE tests
# ---------------------------------------------------------------------------

class TestPkce:

    def test_generate_pkce_pair_produces_two_distinct_strings(self):
        verifier, challenge = AuthService._generate_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert verifier != challenge

    def test_verifier_is_url_safe_base64(self):
        verifier, _ = AuthService._generate_pkce_pair()
        # Should only contain base64url-safe characters (A-Z, a-z, 0-9, -, _)
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in verifier)

    def test_challenge_is_sha256_of_verifier(self):
        verifier, challenge = AuthService._generate_pkce_pair()
        # Manually compute the challenge from the verifier
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected_challenge

    def test_each_call_produces_unique_pair(self):
        pair1 = AuthService._generate_pkce_pair()
        pair2 = AuthService._generate_pkce_pair()
        assert pair1 != pair2


# ---------------------------------------------------------------------------
# State generation tests
# ---------------------------------------------------------------------------

class TestStateGeneration:

    def test_state_is_non_empty_string(self):
        state = AuthService._generate_state()
        assert isinstance(state, str)
        assert len(state) > 0

    def test_each_state_is_unique(self):
        states = [AuthService._generate_state() for _ in range(10)]
        # All 10 states should be distinct
        assert len(set(states)) == 10


# ---------------------------------------------------------------------------
# get_authorization_url tests
# ---------------------------------------------------------------------------

class TestGetAuthorizationUrl:

    def test_returns_url_and_state(self):
        service = make_service()
        url, state = service.get_authorization_url()
        assert isinstance(url, str)
        assert isinstance(state, str)
        assert url.startswith("https://login.microsoftonline.com/")

    def test_url_contains_client_id(self):
        service = make_service()
        url, _ = service.get_authorization_url()
        assert "client_id=test-client-id" in url

    def test_url_contains_code_challenge(self):
        service = make_service()
        url, _ = service.get_authorization_url()
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url

    def test_url_contains_required_scopes(self):
        service = make_service()
        url, _ = service.get_authorization_url()
        # URL-encoded space is %20 or +; scopes_str is space-separated
        assert "User.Read" in url
        assert "offline_access" in url

    def test_state_stored_in_pkce_store(self):
        service = make_service()
        _, state = service.get_authorization_url()
        assert state in service._pkce_store

    def test_each_call_produces_unique_state(self):
        service = make_service()
        _, state1 = service.get_authorization_url()
        _, state2 = service.get_authorization_url()
        assert state1 != state2


# ---------------------------------------------------------------------------
# exchange_code_for_tokens success tests
# ---------------------------------------------------------------------------

class TestExchangeCodeForTokensSuccess:

    @respx.mock
    async def test_returns_authorization_response(self):
        service = make_service()
        url, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response())
        )

        auth_response = await service.exchange_code_for_tokens(
            code="test_code", state=state
        )

        assert auth_response.user_id == "user-oid-001"
        assert auth_response.display_name == "Test User"
        assert auth_response.email == "test@example.com"
        assert auth_response.access_token == "test_access_token"

    @respx.mock
    async def test_token_stored_in_repository(self):
        repo = InMemoryTokenRepository()
        service = make_service(repo=repo)
        url, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response())
        )

        await service.exchange_code_for_tokens(code="test_code", state=state)

        stored = await repo.get("user-oid-001")
        assert stored is not None
        assert stored.access_token == "test_access_token"

    @respx.mock
    async def test_refresh_token_is_encrypted_in_repository(self):
        repo = InMemoryTokenRepository()
        encryption_key = Fernet.generate_key().decode()
        service = make_service(repo=repo, encryption_key=encryption_key)
        url, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response())
        )

        await service.exchange_code_for_tokens(code="test_code", state=state)

        stored = await repo.get("user-oid-001")
        # The stored refresh_token should not match the plaintext one
        assert stored.refresh_token != "test_refresh_token"
        # But it should decrypt to the correct value
        fernet = Fernet(encryption_key.encode())
        decrypted = fernet.decrypt(stored.refresh_token.encode()).decode()
        assert decrypted == "test_refresh_token"

    @respx.mock
    async def test_state_removed_from_pkce_store_after_exchange(self):
        service = make_service()
        url, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response())
        )

        assert state in service._pkce_store
        await service.exchange_code_for_tokens(code="test_code", state=state)
        assert state not in service._pkce_store


# ---------------------------------------------------------------------------
# exchange_code_for_tokens failure tests
# ---------------------------------------------------------------------------

class TestExchangeCodeForTokensFailures:

    async def test_raises_auth_state_error_for_unknown_state(self):
        service = make_service()
        with pytest.raises(AuthStateError) as exc_info:
            await service.exchange_code_for_tokens(
                code="test_code", state="unknown_state"
            )
        assert "Unknown or expired state" in exc_info.value.message

    @respx.mock
    async def test_raises_auth_code_exchange_error_on_microsoft_4xx(self):
        service = make_service()
        url, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(400, json={"error_description": "Invalid code"})
        )

        with pytest.raises(AuthCodeExchangeError) as exc_info:
            await service.exchange_code_for_tokens(code="bad_code", state=state)
        assert "400" in exc_info.value.message

    @respx.mock
    async def test_raises_auth_code_exchange_error_on_network_failure(self):
        import httpx as _httpx

        service = make_service()
        url, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            side_effect=_httpx.ConnectError("connection refused")
        )

        with pytest.raises(AuthCodeExchangeError) as exc_info:
            await service.exchange_code_for_tokens(code="test_code", state=state)
        assert "Network error" in exc_info.value.message


# ---------------------------------------------------------------------------
# get_valid_token tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Graph /me fallback tests
# ---------------------------------------------------------------------------

class TestGraphMeFallback:
    """
    When the token response contains no id_token (or id_token yields
    "unknown" user_id), exchange_code_for_tokens() must call Graph /me
    and use the response for user_id, display_name, and email.
    """

    @respx.mock
    async def test_identity_from_graph_me_when_id_token_absent(self):
        """
        No id_token in token response → Graph /me is called and its fields
        are used for the AuthorizationResponse.
        """
        service = make_service()
        _, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response_no_id_token())
        )
        respx.get(GRAPH_ME_URL).mock(
            return_value=Response(200, json=make_graph_me_response(
                user_id="graph-user-001",
                display_name="Graph User",
                mail="graph@example.com",
            ))
        )

        auth_response = await service.exchange_code_for_tokens(
            code="test_code", state=state
        )

        assert auth_response.user_id == "graph-user-001"
        assert auth_response.display_name == "Graph User"
        assert auth_response.email == "graph@example.com"
        assert auth_response.access_token == "test_access_token"

    @respx.mock
    async def test_graph_me_uses_user_principal_name_when_mail_is_null(self):
        """
        Graph /me.mail is null for many work/school accounts.
        The fallback must use userPrincipalName instead.
        """
        service = make_service()
        _, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response_no_id_token())
        )
        respx.get(GRAPH_ME_URL).mock(
            return_value=Response(200, json=make_graph_me_response(
                mail=None,  # null in Graph response
                user_principal_name="upn@corp.example.com",
            ))
        )

        auth_response = await service.exchange_code_for_tokens(
            code="test_code", state=state
        )

        assert auth_response.email == "upn@corp.example.com"

    @respx.mock
    async def test_id_token_present_does_not_call_graph_me(self):
        """
        When id_token is present and yields a valid user_id, Graph /me must
        NOT be called (no extra HTTP round-trip on the happy path).
        """
        service = make_service()
        _, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response())
        )
        # Register the Graph route but do NOT mock a response — if it is
        # called, respx will raise and fail the test.
        graph_route = respx.get(GRAPH_ME_URL)

        auth_response = await service.exchange_code_for_tokens(
            code="test_code", state=state
        )

        # id_token path must win
        assert auth_response.user_id == "user-oid-001"
        assert auth_response.display_name == "Test User"
        # Graph /me must not have been called
        assert not graph_route.called

    @respx.mock
    async def test_graph_me_network_failure_returns_gracefully(self):
        """
        If Graph /me fails (network error), exchange_code_for_tokens() must
        still return an AuthorizationResponse — with "unknown" identity fields
        rather than raising an exception.  The tokens are still stored so the
        user is not locked out.
        """
        import httpx as _httpx

        service = make_service()
        _, state = service.get_authorization_url()

        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(200, json=make_token_response_no_id_token())
        )
        respx.get(GRAPH_ME_URL).mock(
            side_effect=_httpx.ConnectError("connection refused")
        )

        auth_response = await service.exchange_code_for_tokens(
            code="test_code", state=state
        )

        # Should not raise; identity fields degrade gracefully
        assert auth_response.user_id == "unknown"
        assert auth_response.display_name == ""
        assert auth_response.email == ""
        # Access token must still be returned
        assert auth_response.access_token == "test_access_token"



class TestGetValidToken:

    async def test_returns_access_token_when_not_expired(self):
        repo = InMemoryTokenRepository()
        service = make_service(repo=repo)

        # Manually store a non-expired token
        token_data = TokenData(
            user_id="user-oid-001",
            access_token="valid_token",
            refresh_token=service._encrypt("refresh_token_placeholder"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await repo.save(token_data)

        result = await service.get_valid_token("user-oid-001")
        assert result == "valid_token"

    async def test_raises_user_not_found_for_unknown_user(self):
        service = make_service()
        with pytest.raises(AuthUserNotFoundError) as exc_info:
            await service.get_valid_token("nonexistent_user")
        assert "No token found" in exc_info.value.message

    @respx.mock
    async def test_silently_refreshes_expired_token(self):
        repo = InMemoryTokenRepository()
        encryption_key = Fernet.generate_key().decode()
        service = make_service(repo=repo, encryption_key=encryption_key)

        # Store an expired token
        token_data = TokenData(
            user_id="user-oid-001",
            access_token="old_token",
            refresh_token=service._encrypt("refresh_token_placeholder"),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await repo.save(token_data)

        # Mock the refresh response from Microsoft
        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(
                200,
                json={
                    "access_token": "new_access_token",
                    "refresh_token": "new_refresh_token",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )

        result = await service.get_valid_token("user-oid-001")
        assert result == "new_access_token"

        # Verify the repository was updated
        stored = await repo.get("user-oid-001")
        assert stored.access_token == "new_access_token"

    @respx.mock
    async def test_raises_auth_refresh_error_when_microsoft_rejects_refresh(self):
        repo = InMemoryTokenRepository()
        service = make_service(repo=repo)

        # Store an expired token
        token_data = TokenData(
            user_id="user-oid-001",
            access_token="old_token",
            refresh_token=service._encrypt("refresh_token_placeholder"),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await repo.save(token_data)

        # Microsoft rejects the refresh
        respx.post(service._test_outlook.token_url).mock(
            return_value=Response(400, json={"error_description": "Invalid refresh token"})
        )

        with pytest.raises(AuthRefreshError) as exc_info:
            await service.get_valid_token("user-oid-001")
        assert "Token refresh failed" in exc_info.value.message


# ---------------------------------------------------------------------------
# _refresh_token — encryption key rotation (AuthEncryptionError path)
# ---------------------------------------------------------------------------

class TestRefreshTokenEncryptionError:

    async def test_raises_auth_refresh_error_when_refresh_token_cannot_be_decrypted(self):
        """
        If the TOKEN_ENCRYPTION_KEY is rotated after a token is stored,
        decryption fails.  _refresh_token must surface this as AuthRefreshError
        so the router can return 401 and prompt re-authentication.
        """
        repo = InMemoryTokenRepository()
        service = make_service(repo=repo)

        # Encrypt the refresh token with a DIFFERENT key than the service holds
        different_key = Fernet.generate_key().decode()
        wrong_fernet = Fernet(different_key.encode())
        badly_encrypted = wrong_fernet.encrypt(b"some_refresh_token").decode()

        token_data = TokenData(
            user_id="user-oid-001",
            access_token="old_token",
            refresh_token=badly_encrypted,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await repo.save(token_data)

        with pytest.raises(AuthRefreshError) as exc_info:
            await service.get_valid_token("user-oid-001")
        assert "TOKEN_ENCRYPTION_KEY" in exc_info.value.message


# ---------------------------------------------------------------------------
# revoke_token tests
# ---------------------------------------------------------------------------

class TestRevokeToken:

    async def test_removes_token_from_repository(self):
        repo = InMemoryTokenRepository()
        service = make_service(repo=repo)

        # Store a token
        token_data = TokenData(
            user_id="user-oid-001",
            access_token="token",
            refresh_token=service._encrypt("refresh"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        await repo.save(token_data)

        assert await repo.exists("user-oid-001")
        await service.revoke_token("user-oid-001")
        assert not await repo.exists("user-oid-001")

    async def test_revoke_nonexistent_user_does_not_raise(self):
        service = make_service()
        # Should not raise
        await service.revoke_token("nonexistent_user")


# ---------------------------------------------------------------------------
# Encryption tests
# ---------------------------------------------------------------------------

class TestEncryption:

    def test_encrypt_decrypt_round_trip(self):
        service = make_service()
        plaintext = "my_secret_refresh_token"
        encrypted = service._encrypt(plaintext)
        decrypted = service._decrypt(encrypted)
        assert decrypted == plaintext

    def test_different_encryptions_are_distinct(self):
        service = make_service()
        plaintext = "my_secret"
        encrypted1 = service._encrypt(plaintext)
        encrypted2 = service._encrypt(plaintext)
        # Fernet uses a nonce — same plaintext yields different ciphertexts
        assert encrypted1 != encrypted2
        # But both decrypt to the same plaintext
        assert service._decrypt(encrypted1) == plaintext
        assert service._decrypt(encrypted2) == plaintext


# ---------------------------------------------------------------------------
# client_secret injection tests
# ---------------------------------------------------------------------------

class TestClientSecretInjection:
    """
    Verify that client_secret is included in both the authorization-code
    exchange payload and the refresh-token payload sent to Microsoft.

    This covers the AADSTS7000218 regression: Azure AD confidential-client
    apps require client_secret (or client_assertion) in every token request.
    """

    @respx.mock
    async def test_client_secret_in_code_exchange_payload(self):
        """client_secret must appear in the authorization-code exchange POST body."""
        service = make_service(client_secret="super-secret-value")
        _, state = service.get_authorization_url()

        captured: list[dict] = []

        def capture_and_respond(request, route):
            import urllib.parse
            body = dict(urllib.parse.parse_qsl(request.content.decode()))
            captured.append(body)
            return Response(200, json=make_token_response())

        respx.post(service._test_outlook.token_url).mock(side_effect=capture_and_respond)

        await service.exchange_code_for_tokens(code="test_code", state=state)

        assert len(captured) == 1
        assert captured[0]["client_secret"] == "super-secret-value"
        assert captured[0]["grant_type"] == "authorization_code"
        # PKCE verifier must still be present
        assert "code_verifier" in captured[0]

    @respx.mock
    async def test_client_secret_in_refresh_payload(self):
        """client_secret must appear in the refresh-token POST body."""
        from cryptography.fernet import Fernet as _Fernet

        encryption_key = _Fernet.generate_key().decode()
        repo = InMemoryTokenRepository()
        service = make_service(
            repo=repo,
            encryption_key=encryption_key,
            client_secret="super-secret-value",
        )

        token_data = TokenData(
            user_id="user-oid-001",
            access_token="old_token",
            refresh_token=service._encrypt("refresh_token_placeholder"),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await repo.save(token_data)

        captured: list[dict] = []

        def capture_and_respond(request, route):
            import urllib.parse
            body = dict(urllib.parse.parse_qsl(request.content.decode()))
            captured.append(body)
            return Response(
                200,
                json={
                    "access_token": "new_access_token",
                    "refresh_token": "new_refresh_token",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )

        respx.post(service._test_outlook.token_url).mock(side_effect=capture_and_respond)

        await service.get_valid_token("user-oid-001")

        assert len(captured) == 1
        assert captured[0]["client_secret"] == "super-secret-value"
        assert captured[0]["grant_type"] == "refresh_token"




# ---------------------------------------------------------------------------
# id_token claims extraction tests
# ---------------------------------------------------------------------------

class TestExtractIdTokenClaims:

    def test_extracts_oid_name_email(self):
        service = make_service()
        # Manually build a JWT with known claims
        claims = {
            "oid": "test-oid",
            "name": "Alice",
            "preferred_username": "alice@example.com",
        }
        payload_json = base64.urlsafe_b64encode(
            str(claims).replace("'", '"').encode()
        ).decode().rstrip("=")
        id_token = f"header.{payload_json}.signature"

        user_id, display_name, email = service._extract_id_token_claims(id_token, "")
        assert user_id == "test-oid"
        assert display_name == "Alice"
        assert email == "alice@example.com"

    def test_falls_back_to_fallback_user_id_when_no_id_token(self):
        service = make_service()
        user_id, display_name, email = service._extract_id_token_claims(
            "", fallback_user_id="fallback-001"
        )
        assert user_id == "fallback-001"
        assert display_name == ""
        assert email == ""

    def test_falls_back_gracefully_on_malformed_token(self):
        service = make_service()
        user_id, display_name, email = service._extract_id_token_claims(
            "malformed.jwt", fallback_user_id="fallback-001"
        )
        assert user_id == "fallback-001"
        assert display_name == ""
        assert email == ""

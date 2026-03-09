from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

import requests
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    field_validator,
)

logger = logging.getLogger(__name__)

JsonObject = dict[str, object]


class OAuthTokenPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: StrictStr | None = None
    refresh_token: StrictStr | None = None
    id_token: StrictStr | None = None
    authorization_code: StrictStr | None = None
    code_verifier: StrictStr | None = None
    error: StrictStr | None = None
    error_description: StrictStr | None = None
    message: StrictStr | None = None
    error_code: StrictStr | None = None
    code: StrictStr | None = None
    status: StrictStr | None = None


@dataclass(frozen=True)
class DeviceCode:
    verification_url: str
    user_code: str
    device_auth_id: str
    interval_seconds: int
    expires_in_seconds: int


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str
    id_token: str


class OAuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    return verifier, pkce_challenge(verifier)


def build_authorization_url(
    *,
    state: str,
    code_challenge: str,
) -> str:
    auth_base = "https://auth.openai.com"
    params = {
        "response_type": "code",
        "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "redirect_uri": "http://localhost:1455/auth/callback",
        "scope": "openid profile email offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex_cli_rs",
    }
    query = urlencode(params, quote_via=quote)
    return f"{auth_base}/oauth/authorize?{query}"


def exchange_authorization_code(
    code: str,
    code_verifier: str,
    timeout_seconds: float | None = None,
) -> OAuthTokens:
    url = "https://auth.openai.com/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": "http://localhost:1455/auth/callback",
    }
    encoded = urlencode(payload, quote_via=quote)

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(
        url,
        data=encoded,
        headers=headers,
        timeout=timeout_seconds,
    )
    data = _safe_json(resp)
    try:
        payload = OAuthTokenPayload.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "OAuth token response invalid request_id",
        )
        raise OAuthError("invalid_response", "OAuth response invalid") from exc
    if resp.status_code >= 400:
        logger.warning(
            "OAuth token request failed, status=%s",
            resp.status_code,
        )
        raise _oauth_error_from_payload(payload, resp.status_code)

    return _parse_tokens(payload)


def _parse_tokens(payload: OAuthTokenPayload) -> OAuthTokens:
    if not payload.access_token or not payload.refresh_token or not payload.id_token:
        raise OAuthError("invalid_response", "OAuth response missing tokens")
    return OAuthTokens(
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
        id_token=payload.id_token,
    )


def _safe_json(resp: requests.Response) -> JsonObject:
    try:
        data = resp.json()
    except Exception:
        text = resp.text
        return {"error": {"message": text.strip()}}
    return data if isinstance(data, dict) else {"error": {"message": str(data)}}


def _oauth_error_from_payload(
    payload: OAuthTokenPayload, status_code: int
) -> OAuthError:
    code = _extract_error_code(payload) or f"http_{status_code}"
    message = _extract_error_message(payload) or f"OAuth request failed ({status_code})"
    return OAuthError(code, message, status_code)


def _extract_error_code(payload: OAuthTokenPayload) -> str | None:
    error = payload.error
    if isinstance(error, dict):
        code = error.get("code") or error.get("error")
        return code if isinstance(code, str) else None
    if isinstance(error, str):
        return error
    return payload.error_code or payload.code


def _extract_error_message(payload: OAuthTokenPayload) -> str | None:
    error = payload.error
    if isinstance(error, dict):
        message = error.get("message") or error.get("error_description")
        return message if isinstance(message, str) else None
    if isinstance(error, str):
        return payload.error_description or error
    return payload.message


def _is_pending_error(payload: OAuthTokenPayload) -> bool:
    code = _extract_error_code(payload)
    if code in {"authorization_pending", "slow_down"}:
        return True
    status = payload.status
    if status and status.lower() in {"pending", "authorization_pending"}:
        return True
    return False


def _expires_in_seconds(expires_at: str | None) -> int | None:
    if not expires_at:
        return None
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = (parsed - now).total_seconds()
    if delta <= 0:
        return None
    return int(delta)

"""Workload identity token provider for MCP self-authentication.

Used when MCP_AUTH_MODE=workload. The fd agent fetches its own Keycloak
token and injects it into every MCP call via MCPToolset.header_provider.

Token is cached in-memory and refreshed 30 seconds before expiry.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://keycloak.keycloak.svc.cluster.local:8080")
_REALM = os.environ.get("KEYCLOAK_REALM", "agw-dev")
_CLIENT_ID = os.environ.get("CLIENT_ID", "fd-agent")
_CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "")
_AUDIENCE = os.environ.get("AUDIENCE", "agentgateway")
_USE_TOKEN_EXCHANGE = os.environ.get("USE_TOKEN_EXCHANGE", "false").lower() == "true"
_SA_TOKEN_PATH = os.environ.get("SA_TOKEN_PATH", "/var/run/secrets/tokens/sa-token")

_GRANT_TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
_TOKEN_TYPE_JWT = "urn:ietf:params:oauth:token-type:jwt"
_TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"


class WorkloadMCPTokenProvider:
    """Sync token provider for MCP self-authentication with expiry-aware caching."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._expires_at - 30:
                return self._token
            self._token, self._expires_at = self._fetch()
            mode = "token-exchange" if _USE_TOKEN_EXCHANGE else "client_credentials"
            logger.info(
                "Obtained MCP workload identity token via %s (expires in ~%ds)",
                mode,
                int(self._expires_at - time.monotonic()),
            )
            return self._token

    def header_provider(self, readonly_context: Optional[object] = None) -> dict[str, str]:
        token = self.get_token()
        return {"Authorization": f"Bearer {token}"}

    def _fetch(self) -> tuple[str, float]:
        token_url = f"{_KEYCLOAK_URL}/realms/{_REALM}/protocol/openid-connect/token"
        data = self._build_exchange_data() if _USE_TOKEN_EXCHANGE else self._build_client_credentials_data()
        with httpx.Client(verify=False) as client:
            resp = client.post(token_url, data=data)
            resp.raise_for_status()
        payload = resp.json()
        access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 300))
        return access_token, time.monotonic() + expires_in

    def _build_client_credentials_data(self) -> dict:
        return {
            "grant_type": "client_credentials",
            "client_id": _CLIENT_ID,
            "client_secret": _CLIENT_SECRET,
        }

    def _build_exchange_data(self) -> dict:
        sa_token_path = Path(_SA_TOKEN_PATH)
        if not sa_token_path.exists():
            raise FileNotFoundError(
                f"SA token not found at {_SA_TOKEN_PATH}. "
                "Ensure the deployment has a projected ServiceAccountToken volume."
            )
        sa_token = sa_token_path.read_text().strip()
        data: dict = {
            "grant_type": _GRANT_TOKEN_EXCHANGE,
            "client_id": _CLIENT_ID,
            "subject_token": sa_token,
            "subject_token_type": _TOKEN_TYPE_JWT,
            "requested_token_type": _TOKEN_TYPE_ACCESS,
            "audience": _AUDIENCE,
        }
        if _CLIENT_SECRET:
            data["client_secret"] = _CLIENT_SECRET
        return data

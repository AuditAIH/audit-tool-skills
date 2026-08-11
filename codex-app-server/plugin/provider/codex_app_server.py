from typing import Any

import httpx
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class CodexAppServerProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        server_url = str(credentials.get("server_url") or "").strip().rstrip("/")
        if not server_url:
            raise ToolProviderCredentialValidationError("server_url cannot be empty.")
        if not server_url.startswith(("http://", "https://")):
            raise ToolProviderCredentialValidationError(
                "server_url must start with http:// or https://."
            )
        headers: dict[str, str] = {}
        api_key = str(credentials.get("api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = httpx.get(f"{server_url}/healthz", headers=headers, timeout=10.0)
            response.raise_for_status()
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to reach codex-app-server at {server_url}: {e}"
            ) from e

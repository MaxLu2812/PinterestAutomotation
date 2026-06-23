"""Low-level Pinterest API v5 client.

Handles OAuth 2.0 token management, board operations, and pin CRUD
via the Pinterest API v5 (https://api.pinterest.com/v5).
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.pinterest.com/v5"
_DEFAULT_TIMEOUT = 30.0


@dataclass
class BoardInfo:
    """Resolved board information."""

    board_id: str
    name: str
    description: str = ""


@dataclass
class TokenInfo:
    """OAuth 2.0 token state for a Pinterest account."""

    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None

    @property
    def is_expired(self) -> bool:
        """Check if the access token has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() >= self.expires_at


class PinterestClient:
    """Low-level HTTP client for Pinterest API v5.

    Provides OAuth 2.0 token management, board listing/resolution,
    and pin CRUD operations. All methods return structured results
    (dicts for success, dicts with error info on failure) — never
    throws on API errors.
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_expiry: Optional[datetime] = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._token = TokenInfo(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=token_expiry,
        )
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=_API_BASE,
            timeout=timeout,
            follow_redirects=True,
        )
        self._boards_cache: Optional[list[dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Return common headers including authorization."""
        return {
            "Authorization": f"Bearer {self._token.access_token}",
            "Content-Type": "application/json",
        }

    def _ensure_token_valid(self) -> Optional[str]:
        """Check token expiry and attempt refresh if needed.

        Returns an error string if the token is expired and cannot
        be refreshed, or None if the token is valid.
        """
        if not self._token.is_expired:
            return None
        if not self._token.refresh_token:
            return (
                "Access token has expired and no refresh token is configured. "
                "Set PINTEREST_REFRESH_TOKEN or generate a new access token."
            )
        return self._refresh_access_token()

    def _refresh_access_token(self) -> Optional[str]:
        """Attempt to refresh the access token via Pinterest OAuth.

        Returns an error string on failure, or None on success.
        """
        logger.info("Attempting to refresh Pinterest access token ...")
        try:
            resp = httpx.post(
                "https://api.pinterest.com/v5/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._token.refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
            if resp.is_success:
                data = resp.json()
                self._token.access_token = data["access_token"]
                # Pinterest tokens are typically valid for 30 days
                expires_in = data.get("expires_in", 2_592_000)
                self._token.expires_at = datetime.now() + timedelta(seconds=expires_in)
                logger.info("Access token refreshed successfully.")
                return None
            else:
                logger.error("Token refresh failed: %s %s", resp.status_code, resp.text)
                return (
                    f"Token refresh failed (HTTP {resp.status_code}): "
                    f"{resp.text[:200]}"
                )
        except httpx.RequestError as exc:
            logger.error("Token refresh request error: %s", exc)
            return f"Token refresh request failed: {exc}"

    # ------------------------------------------------------------------
    # Board operations
    # ------------------------------------------------------------------

    def get_boards(self) -> list[dict[str, Any]]:
        """List all accessible boards.

        Returns a list of board dicts (each with 'id', 'name', etc.)
        or an empty list on error.
        """
        token_error = self._ensure_token_valid()
        if token_error:
            logger.error("Cannot list boards: %s", token_error)
            return []

        try:
            resp = self._client.get(
                "/boards",
                headers=self._get_headers(),
                params={"page_size": 100},
            )
            if resp.is_success:
                data = resp.json()
                self._boards_cache = data.get("items", [])
                return self._boards_cache
            else:
                logger.error("List boards failed: %s %s", resp.status_code, resp.text)
                return []
        except httpx.RequestError as exc:
            logger.error("List boards request error: %s", exc)
            return []

    def get_board(self, board_id: str) -> Optional[dict[str, Any]]:
        """Get a single board's details by ID.

        Returns the board dict or None on error.
        """
        token_error = self._ensure_token_valid()
        if token_error:
            logger.error("Cannot get board: %s", token_error)
            return None

        try:
            resp = self._client.get(
                f"/boards/{board_id}",
                headers=self._get_headers(),
            )
            if resp.is_success:
                return resp.json()
            else:
                logger.error("Get board failed: %s %s", resp.status_code, resp.text)
                return None
        except httpx.RequestError as exc:
            logger.error("Get board request error: %s", exc)
            return None

    def resolve_board_id(self, board_name: str) -> Optional[str]:
        """Resolve a board ID from a board name using the cached board list.

        Falls back to a fresh API call if the cache is empty.

        Args:
            board_name: The human-readable board name to resolve.

        Returns:
            The board ID string, or None if not found.
        """
        if self._boards_cache is None:
            self.get_boards()

        if self._boards_cache:
            for board in self._boards_cache:
                if board.get("name", "").lower() == board_name.lower():
                    return board["id"]

        logger.warning("Board '%s' not found in accessible boards.", board_name)
        return None

    # ------------------------------------------------------------------
    # Pin operations
    # ------------------------------------------------------------------

    def create_pin(
        self,
        board_id: str,
        image_path: str,
        title: str,
        description: str,
        alt_text: str = "",
    ) -> dict[str, Any]:
        """Create a pin from a local image file.

        Uses the Pinterest Media API (POST /v5/media) to upload the image
        first, then creates the pin via POST /v5/pins.

        Args:
            board_id: The target Pinterest board ID.
            image_path: Path to the local image file.
            title: Pin title (max 100 chars).
            description: Pin description.
            alt_text: Alt text for accessibility.

        Returns:
            A dict with pin data on success (including 'id' and 'link'),
            or a dict with 'error' key on failure.
        """
        token_error = self._ensure_token_valid()
        if token_error:
            return {"error": token_error}

        # --- Step 1: Upload image via media endpoint ---
        media_result = self._upload_image(image_path)
        if "error" in media_result:
            return media_result

        media_id = media_result.get("media_id", "")

        # --- Step 2: Create the pin ---
        body: dict[str, Any] = {
            "board_id": board_id,
            "media_source": {
                "source_type": "image_base64",
                "content_type": "image/jpeg",
                "data": self._image_to_base64(image_path),
            },
            "title": title[:100],
            "description": description,
            "alt_text": alt_text,
        }

        if media_id:
            # Use the uploaded media reference if available
            body["media_source"] = {
                "source_type": "image_base64",
                "content_type": "image/jpeg",
                "data": self._image_to_base64(image_path),
            }

        try:
            resp = self._client.post(
                "/pins",
                headers=self._get_headers(),
                json=body,
            )
            if resp.is_success:
                data = resp.json()
                logger.info(
                    "[PUBLISHED] pin_id=%s url=%s",
                    data.get("id"),
                    data.get("link"),
                )
                return data
            else:
                error_msg = self._parse_error(resp)
                logger.error("Create pin failed: %s", error_msg)
                return {"error": error_msg}
        except httpx.RequestError as exc:
            logger.error("Create pin request error: %s", exc)
            return {"error": f"Request failed: {exc}"}

    def get_pin(self, pin_id: str) -> Optional[dict[str, Any]]:
        """Get pin details/analytics by ID.

        Returns the pin dict or None on error.
        """
        token_error = self._ensure_token_valid()
        if token_error:
            logger.error("Cannot get pin: %s", token_error)
            return None

        try:
            resp = self._client.get(
                f"/pins/{pin_id}",
                headers=self._get_headers(),
            )
            if resp.is_success:
                return resp.json()
            else:
                logger.error("Get pin failed: %s %s", resp.status_code, resp.text)
                return None
        except httpx.RequestError as exc:
            logger.error("Get pin request error: %s", exc)
            return None

    def delete_pin(self, pin_id: str) -> bool:
        """Delete a pin by ID.

        Returns True if deletion was successful, False on error.
        """
        token_error = self._ensure_token_valid()
        if token_error:
            logger.error("Cannot delete pin: %s", token_error)
            return False

        try:
            resp = self._client.delete(
                f"/pins/{pin_id}",
                headers=self._get_headers(),
            )
            if resp.is_success or resp.status_code == 204:
                logger.info("Deleted pin %s", pin_id)
                return True
            else:
                logger.error("Delete pin failed: %s %s", resp.status_code, resp.text)
                return False
        except httpx.RequestError as exc:
            logger.error("Delete pin request error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upload_image(self, image_path: str) -> dict[str, Any]:
        """Upload an image to Pinterest via the media endpoint.

        Returns a dict with 'media_id' on success or 'error' on failure.
        """
        path = Path(image_path)
        if not path.is_file():
            return {"error": f"Image file not found: {image_path}"}

        # Read file and encode as base64
        try:
            image_data = self._image_to_base64(image_path)
        except Exception as exc:
            return {"error": f"Failed to read image: {exc}"}

        body = {
            "media_source": {
                "source_type": "image_base64",
                "content_type": "image/jpeg",
                "data": image_data,
            }
        }

        try:
            resp = self._client.post(
                "/media",
                headers=self._get_headers(),
                json=body,
            )
            if resp.is_success:
                data = resp.json()
                return {"media_id": data.get("id", "")}
            else:
                error_msg = self._parse_error(resp)
                logger.error("Media upload failed: %s", error_msg)
                return {"error": error_msg}
        except httpx.RequestError as exc:
            logger.error("Media upload request error: %s", exc)
            return {"error": f"Media upload failed: {exc}"}

    @staticmethod
    def _image_to_base64(image_path: str) -> str:
        """Read an image file and return its base64-encoded string."""
        with open(image_path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("utf-8")

    @staticmethod
    def _parse_error(resp: httpx.Response) -> str:
        """Extract a human-readable error message from an API response."""
        try:
            data = resp.json()
            message = data.get("message", "")
            code = data.get("code", resp.status_code)
            return f"[{code}] {message}"[:300]
        except Exception:
            return f"HTTP {resp.status_code}: {resp.text[:200]}"

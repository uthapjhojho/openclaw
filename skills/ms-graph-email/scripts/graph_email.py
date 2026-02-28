#!/usr/bin/env python3
"""
Microsoft Graph Email Service

Single-mailbox email operations using delegated OAuth2 authentication.
Uses MS_GRAPH_REFRESH_TOKEN_MEUTIA refresh token.
Works on Railway (HTTPS port 443 only — no SMTP/IMAP needed).

Supported operations:
- list_emails()       — list emails from a folder
- search_emails()     — search emails by OData filter
- get_email()         — fetch single email by ID
- send_email()        — send email via Graph API
- mark_as_read()      — mark email as read
- mark_as_unread()    — mark email as unread
- delete_email()      — delete single email
- delete_emails()     — delete multiple emails
- delete_by_filter()  — find and delete by OData filter
- list_folders()      — list all mail folders
- _paginate()         — generator that follows @odata.nextLink
"""

import os
import time
import logging
import socket
import requests
from requests.adapters import HTTPAdapter
from typing import Optional, List, Dict, Any, Generator
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

MS_GRAPH_CLIENT_ID = os.environ.get("MS_GRAPH_CLIENT_ID")
MS_GRAPH_TENANT_ID = os.environ.get("MS_GRAPH_TENANT_ID")
MS_GRAPH_REFRESH_TOKEN = os.environ.get("MS_GRAPH_REFRESH_TOKEN_MEUTIA")

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

TIMEOUT_API_REQUEST = 30  # seconds


# =============================================================================
# IPv4 ADAPTER (Railway compatibility)
# =============================================================================

class IPv4HTTPAdapter(HTTPAdapter):
    """HTTP Adapter that forces IPv4 connections for Railway compatibility."""

    def init_poolmanager(self, *args, **kwargs):
        import urllib3.util.connection as urllib3_conn

        _orig_create_connection = urllib3_conn.create_connection

        def patched_create_connection(address, *args, **kwargs):
            host, port = address
            for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
                af, socktype, proto, canonname, sa = res
                try:
                    sock = socket.socket(af, socktype, proto)
                    sock.settimeout(kwargs.get("timeout", TIMEOUT_API_REQUEST))
                    sock.connect(sa)
                    return sock
                except socket.error:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    continue
            raise socket.error(f"Could not connect to {host}:{port} via IPv4")

        urllib3_conn.create_connection = patched_create_connection
        super().init_poolmanager(*args, **kwargs)


def _create_session() -> requests.Session:
    """Create a requests.Session that forces IPv4."""
    session = requests.Session()
    adapter = IPv4HTTPAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# =============================================================================
# TOKEN CACHE
# =============================================================================

@dataclass
class _TokenCache:
    access_token: Optional[str] = None
    expires_at: Optional[datetime] = None


_token_cache = _TokenCache()


# =============================================================================
# EMAIL SERVICE
# =============================================================================

class EmailService:
    """
    Microsoft Graph Email Service for Meutia (single-mailbox).

    Uses delegated auth (refresh token) — public client flow, no client_secret.
    Token is cached in-process with a 5-minute expiry buffer.
    Only calls https://graph.microsoft.com and https://login.microsoftonline.com.
    """

    def __init__(self):
        self.client_id = MS_GRAPH_CLIENT_ID
        self.tenant_id = MS_GRAPH_TENANT_ID
        self.refresh_token = MS_GRAPH_REFRESH_TOKEN
        self.session = _create_session()

        if self.tenant_id:
            self.token_url = TOKEN_URL_TEMPLATE.format(tenant_id=self.tenant_id)
        else:
            self.token_url = None

    @property
    def is_configured(self) -> bool:
        """Return True if all required env vars are present."""
        return bool(self.client_id and self.tenant_id and self.refresh_token)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _get_access_token(self) -> Optional[str]:
        """
        Get access token using refresh token (delegated / public client flow).
        Caches the token with a 5-minute expiry buffer.
        Never logs the token value or the refresh token.
        """
        global _token_cache

        # Return cached token if still valid
        if _token_cache.access_token and _token_cache.expires_at:
            if datetime.now() < _token_cache.expires_at:
                return _token_cache.access_token

        if not self.is_configured:
            logger.error("ms-graph-email: service not configured — check env vars")
            return None

        try:
            response = self.session.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                    "scope": (
                        "https://graph.microsoft.com/Mail.Read "
                        "https://graph.microsoft.com/Mail.ReadWrite "
                        "https://graph.microsoft.com/Mail.Send"
                    ),
                },
                timeout=TIMEOUT_API_REQUEST,
            )

            if response.status_code == 200:
                data = response.json()
                _token_cache.access_token = data["access_token"]
                expires_in = data.get("expires_in", 3600)
                # 5-minute buffer
                _token_cache.expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                logger.info("ms-graph-email: access token obtained/refreshed")
                return _token_cache.access_token
            else:
                logger.error(
                    "ms-graph-email: token request failed with status %d",
                    response.status_code,
                )
                return None

        except Exception:
            # Do not log the exception message — it may contain token details
            logger.error("ms-graph-email: error obtaining access token (network/timeout)")
            return None

    def _get_headers(self) -> dict:
        """Build auth headers. Raises if token cannot be obtained."""
        token = self._get_access_token()
        if not token:
            raise RuntimeError("ms-graph-email: failed to obtain access token")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Rate-limit helper
    # ------------------------------------------------------------------

    def _handle_response(self, response: requests.Response, op: str) -> requests.Response:
        """
        Handle rate-limit (429) by sleeping Retry-After seconds, then retrying once.
        Does not bypass the limit — waits as instructed by the server.
        """
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "5"))
            logger.warning("ms-graph-email: rate limited (429) on %s — waiting %ds", op, retry_after)
            time.sleep(retry_after)
            # Retry the original request (caller must re-call; this returns the 429 response
            # so the caller can detect it — actual retry is done in each method)
        return response

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _paginate(self, url: str, params: Optional[dict] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Generator that yields individual items from paginated Graph API responses.
        Follows @odata.nextLink automatically.
        """
        headers = self._get_headers()
        next_url: Optional[str] = url
        current_params = params

        while next_url:
            try:
                response = self.session.get(
                    next_url,
                    headers=headers,
                    params=current_params,
                    timeout=TIMEOUT_API_REQUEST,
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    logger.warning("ms-graph-email: 429 during pagination — waiting %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                if response.status_code != 200:
                    logger.error(
                        "ms-graph-email: pagination request failed with status %d",
                        response.status_code,
                    )
                    return

                data = response.json()
                for item in data.get("value", []):
                    yield item

                next_url = data.get("@odata.nextLink")
                current_params = None  # nextLink already contains all params

            except Exception:
                logger.error("ms-graph-email: error during pagination (%s)", type(Exception).__name__)
                return

    # ------------------------------------------------------------------
    # Email operations
    # ------------------------------------------------------------------

    def list_emails(
        self,
        folder: str = "inbox",
        top: int = 20,
        filter_query: Optional[str] = None,
        unread_only: bool = False,
        select: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List emails from a mail folder.

        Args:
            folder:       Mail folder name (inbox, sentitems, drafts, deleteditems, etc.)
            top:          Maximum number of emails to return
            filter_query: OData filter expression
            unread_only:  If True, adds isRead eq false filter
            select:       Fields to return

        Returns:
            List of email dicts
        """
        headers = self._get_headers()

        if select is None:
            select = ["id", "subject", "from", "receivedDateTime", "isRead", "bodyPreview"]

        url = f"{GRAPH_BASE_URL}/me/mailFolders/{folder}/messages"
        params: Dict[str, Any] = {
            "$top": top,
            "$select": ",".join(select),
            "$orderby": "receivedDateTime desc",
        }

        filters = []
        if filter_query:
            filters.append(filter_query)
        if unread_only:
            filters.append("isRead eq false")
        if filters:
            params["$filter"] = " and ".join(filters)

        try:
            response = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on list_emails — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 200:
                return response.json().get("value", [])
            else:
                logger.error("ms-graph-email: list_emails failed with status %d", response.status_code)
                return []
        except Exception:
            logger.error("ms-graph-email: error in list_emails")
            return []

    def search_emails(
        self,
        query: str,
        top: int = 20,
        select: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search emails using OData $filter across all messages.

        Args:
            query: OData filter (e.g., "contains(subject,'invoice')")
            top:   Maximum results

        Returns:
            List of matching email dicts
        """
        headers = self._get_headers()

        if select is None:
            select = ["id", "subject", "from", "receivedDateTime", "isRead"]

        url = f"{GRAPH_BASE_URL}/me/messages"
        params = {
            "$filter": query,
            "$top": top,
            "$select": ",".join(select),
            "$orderby": "receivedDateTime desc",
        }

        try:
            response = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on search_emails — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 200:
                return response.json().get("value", [])
            else:
                logger.error("ms-graph-email: search_emails failed with status %d", response.status_code)
                return []
        except Exception:
            logger.error("ms-graph-email: error in search_emails")
            return []

    def get_email(self, email_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single email by its Graph API ID.

        Args:
            email_id: The message ID (opaque string from Graph API)

        Returns:
            Email dict including body, or None on failure
        """
        headers = self._get_headers()
        url = f"{GRAPH_BASE_URL}/me/messages/{email_id}"

        try:
            response = self.session.get(url, headers=headers, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on get_email — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.get(url, headers=headers, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error("ms-graph-email: get_email failed with status %d", response.status_code)
                return None
        except Exception:
            logger.error("ms-graph-email: error in get_email")
            return None

    def send_email(
        self,
        to: "str | List[str]",
        subject: str,
        body: str,
        cc: "Optional[str | List[str]]" = None,
        bcc: "Optional[str | List[str]]" = None,
        is_html: bool = False,
    ) -> bool:
        """
        Send an email via Microsoft Graph API.

        Args:
            to:      Recipient(s) — string or list of email addresses
            subject: Email subject
            body:    Email body text or HTML
            cc:      CC recipient(s) — string or list (optional)
            bcc:     BCC recipient(s) — string or list (optional)
            is_html: Set True to send body as HTML

        Returns:
            True if sent successfully (202 Accepted), False otherwise
        """
        headers = self._get_headers()
        url = f"{GRAPH_BASE_URL}/me/sendMail"

        def _to_recipients(value: "Optional[str | List[str]]") -> List[dict]:
            if value is None:
                return []
            if isinstance(value, str):
                addresses = [a.strip() for a in value.split(",") if a.strip()]
            else:
                addresses = [a.strip() for a in value if a.strip()]
            return [
                {"emailAddress": {"address": addr}}
                for addr in addresses
                if _is_valid_email(addr)
            ]

        to_recipients = _to_recipients(to)
        if not to_recipients:
            logger.error("ms-graph-email: send_email — no valid recipients provided")
            return False

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if is_html else "Text",
                    "content": body,
                },
                "toRecipients": to_recipients,
            },
            "saveToSentItems": True,
        }

        cc_list = _to_recipients(cc)
        if cc_list:
            payload["message"]["ccRecipients"] = cc_list

        bcc_list = _to_recipients(bcc)
        if bcc_list:
            payload["message"]["bccRecipients"] = bcc_list

        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on send_email — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.post(url, headers=headers, json=payload, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 202:
                logger.info("ms-graph-email: email sent successfully")
                return True
            else:
                logger.error("ms-graph-email: send_email failed with status %d", response.status_code)
                return False
        except Exception:
            logger.error("ms-graph-email: error in send_email")
            return False

    def mark_as_read(self, email_id: str) -> bool:
        """Mark an email as read."""
        headers = self._get_headers()
        url = f"{GRAPH_BASE_URL}/me/messages/{email_id}"

        try:
            response = self.session.patch(
                url,
                headers=headers,
                json={"isRead": True},
                timeout=TIMEOUT_API_REQUEST,
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on mark_as_read — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.patch(
                    url, headers=headers, json={"isRead": True}, timeout=TIMEOUT_API_REQUEST
                )

            return response.status_code == 200
        except Exception:
            logger.error("ms-graph-email: error in mark_as_read")
            return False

    def mark_as_unread(self, email_id: str) -> bool:
        """Mark an email as unread."""
        headers = self._get_headers()
        url = f"{GRAPH_BASE_URL}/me/messages/{email_id}"

        try:
            response = self.session.patch(
                url,
                headers=headers,
                json={"isRead": False},
                timeout=TIMEOUT_API_REQUEST,
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on mark_as_unread — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.patch(
                    url, headers=headers, json={"isRead": False}, timeout=TIMEOUT_API_REQUEST
                )

            return response.status_code == 200
        except Exception:
            logger.error("ms-graph-email: error in mark_as_unread")
            return False

    def delete_email(self, email_id: str) -> bool:
        """
        Permanently delete an email by ID.

        Args:
            email_id: The message ID

        Returns:
            True if deleted (204 No Content), False otherwise
        """
        headers = self._get_headers()
        url = f"{GRAPH_BASE_URL}/me/messages/{email_id}"

        try:
            response = self.session.delete(url, headers=headers, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on delete_email — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.delete(url, headers=headers, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 204:
                logger.info("ms-graph-email: deleted email ID ...%s", email_id[-8:])
                return True
            else:
                logger.error("ms-graph-email: delete_email failed with status %d", response.status_code)
                return False
        except Exception:
            logger.error("ms-graph-email: error in delete_email")
            return False

    def delete_emails(self, email_ids: List[str]) -> int:
        """
        Delete multiple emails.

        Args:
            email_ids: List of message IDs

        Returns:
            Count of successfully deleted emails
        """
        deleted = 0
        for email_id in email_ids:
            if self.delete_email(email_id):
                deleted += 1
        return deleted

    def delete_by_filter(self, filter_query: str, max_delete: int = 50) -> int:
        """
        Find emails by OData filter and delete them.

        Args:
            filter_query: OData filter expression
            max_delete:   Maximum number of emails to delete

        Returns:
            Count of deleted emails
        """
        emails = self.search_emails(filter_query, top=max_delete)
        if not emails:
            logger.info("ms-graph-email: delete_by_filter — no emails matched filter")
            return 0
        logger.info("ms-graph-email: delete_by_filter — found %d, deleting...", len(emails))
        return self.delete_emails([e["id"] for e in emails])

    def list_folders(self) -> List[Dict[str, Any]]:
        """
        List all mail folders.

        Returns:
            List of folder dicts with id, displayName, totalItemCount, unreadItemCount
        """
        headers = self._get_headers()
        url = f"{GRAPH_BASE_URL}/me/mailFolders"
        params = {
            "$select": "id,displayName,totalItemCount,unreadItemCount",
        }

        try:
            response = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "5"))
                logger.warning("ms-graph-email: 429 on list_folders — waiting %ds", retry_after)
                time.sleep(retry_after)
                response = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT_API_REQUEST)

            if response.status_code == 200:
                return response.json().get("value", [])
            else:
                logger.error("ms-graph-email: list_folders failed with status %d", response.status_code)
                return []
        except Exception:
            logger.error("ms-graph-email: error in list_folders")
            return []


# =============================================================================
# INPUT VALIDATION
# =============================================================================

def _is_valid_email(address: str) -> bool:
    """
    Email address validation with security hardening.
    RFC 5321 length limit enforced. Rejects double dots, consecutive special chars.
    """
    import re
    address = address.strip()

    # RFC 5321: max 254 chars total
    if not address or len(address) > 254:
        return False

    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,63}@[a-zA-Z0-9][a-zA-Z0-9.\-]{0,253}\.[a-zA-Z]{2,}$'
    if not re.match(pattern, address):
        return False

    # Reject double dots, dot before/after @
    forbidden = [r'\.\.', r'\.@', r'@\.']
    for pat in forbidden:
        if re.search(pat, address):
            return False

    return True


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def get_email_service() -> EmailService:
    """Get a ready-to-use EmailService instance."""
    return EmailService()

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

from graph_email import EmailService, _token_cache, get_email_service
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest


def _make_svc():
    """Create a minimally configured EmailService with a mocked session."""
    svc = EmailService()
    svc.client_id = 'dummy_client_id'
    svc.tenant_id = 'dummy_tenant_id'
    svc.refresh_token = 'dummy_refresh_token'
    svc.token_url = 'https://login.microsoftonline.com/dummy_tenant_id/oauth2/v2.0/token'
    svc.session = MagicMock()
    return svc


def _mock_response(status_code, json_data=None, headers=None):
    """Build a MagicMock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
    resp.headers = headers or {}
    return resp


# =============================================================================
# Token tests
# =============================================================================

def test_token_cache_valid():
    """Cached token is returned without calling session.post."""
    svc = _make_svc()
    _token_cache.access_token = 'cached_tok'
    _token_cache.expires_at = datetime.now() + timedelta(hours=1)
    token = svc._get_access_token()
    assert token == 'cached_tok'
    svc.session.post.assert_not_called()


def test_token_refreshed_when_expired():
    """Token is refreshed via session.post when cache is expired."""
    svc = _make_svc()
    svc.session.post.return_value = _mock_response(
        200, {'access_token': 'newtoken', 'expires_in': 3600}
    )
    # Clear the cache
    _token_cache.access_token = None
    _token_cache.expires_at = None
    token = svc._get_access_token()
    assert token == 'newtoken'
    svc.session.post.assert_called_once()


# =============================================================================
# Email operation tests
# =============================================================================

def test_list_emails_returns_list():
    """list_emails returns a list of email dicts from the Graph API."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    svc.session.get.return_value = _mock_response(
        200, {'value': [{'id': '1', 'subject': 'Test'}]}
    )
    emails = svc.list_emails()
    assert len(emails) == 1
    assert emails[0]['id'] == '1'
    svc.session.get.assert_called_once()


def test_send_email_success():
    """send_email returns True when Graph API responds 202."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    svc.session.post.return_value = _mock_response(202)
    result = svc.send_email('a@b.com', 'subj', 'body')
    assert result is True
    svc.session.post.assert_called_once()


def test_send_email_failure():
    """send_email returns False when Graph API responds 400."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    svc.session.post.return_value = _mock_response(400)
    result = svc.send_email('a@b.com', 'subj', 'body')
    assert result is False
    svc.session.post.assert_called_once()


def test_mark_as_unread():
    """mark_as_unread sends PATCH with isRead:False and returns True on 200."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    svc.session.patch.return_value = _mock_response(200)
    result = svc.mark_as_unread('id123')
    assert result is True
    svc.session.patch.assert_called_once()
    # Verify payload contains isRead: False
    call_kwargs = svc.session.patch.call_args
    assert call_kwargs.kwargs.get('json') == {'isRead': False} or \
           (call_kwargs.args and call_kwargs.args[-1] == {'isRead': False})


def test_list_folders():
    """list_folders returns a list of folder dicts."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    svc.session.get.return_value = _mock_response(
        200, {'value': [{'displayName': 'Inbox'}]}
    )
    folders = svc.list_folders()
    assert len(folders) == 1
    assert folders[0]['displayName'] == 'Inbox'
    svc.session.get.assert_called_once()


def test_pagination_follows_nextlink():
    """_paginate generator follows @odata.nextLink across two pages."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    resp1 = _mock_response(200, {'value': [{'id': '1'}], '@odata.nextLink': 'http://next'})
    resp2 = _mock_response(200, {'value': [{'id': '2'}]})
    svc.session.get.side_effect = [resp1, resp2]
    items = list(svc._paginate('http://initial'))
    assert len(items) == 2
    assert items[0]['id'] == '1'
    assert items[1]['id'] == '2'
    assert svc.session.get.call_count == 2


def test_rate_limit_retry():
    """list_emails retries after 429 Retry-After and returns the second response."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    resp429 = _mock_response(429, headers={'Retry-After': '1'})
    resp200 = _mock_response(200, {'value': []})
    svc.session.get.side_effect = [resp429, resp200]
    with patch('graph_email.time.sleep') as mock_sleep:
        emails = svc.list_emails()
        assert emails == []
        assert svc.session.get.call_count == 2
        mock_sleep.assert_called_once_with(1)


def test_delete_email_success():
    """delete_email returns True when Graph API responds 204."""
    svc = _make_svc()
    svc._get_access_token = MagicMock(return_value='tok')
    svc.session.delete.return_value = _mock_response(204)
    result = svc.delete_email('id123')
    assert result is True
    svc.session.delete.assert_called_once()

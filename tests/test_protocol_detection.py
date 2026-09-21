"""Tests for protocol detection (adam/model/providers.py ProtocolDetector).

Tests:
- OpenAI-compatible endpoint → detected
- Gemini-compatible endpoint → detected
- Unknown/malformed response → unsupported
- Auth failure (401) → still identifies as openai_compatible
- Connection error → unsupported (graceful)
"""

import pytest
from unittest.mock import MagicMock, patch
from adam.model.providers import ProtocolDetector


def _mock_response(status_code: int, json_data=None, raise_exc=None):
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    if raise_exc:
        resp.json.side_effect = raise_exc
    else:
        resp.json.return_value = json_data or {}
    return resp


@pytest.fixture
def detector():
    return ProtocolDetector()


def _patch_client(responses: dict):
    """Patch httpx.Client so GET requests return specific responses by URL substring."""
    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kwargs):
            for key, resp in responses.items():
                if key in url:
                    return resp
            r = MagicMock()
            r.status_code = 404
            return r

    return patch("adam.model.providers.httpx.Client", return_value=MockClient())


def test_openai_compatible_detected(detector):
    """GET /models returning {"object": "list", "data": [...]} → openai_compatible."""
    openai_resp = _mock_response(200, {"object": "list", "data": [{"id": "gpt-4"}]})
    with _patch_client({"/models": openai_resp}):
        result = detector.detect("https://api.example.com")
    assert result == "openai_compatible"


def test_openai_compatible_data_only(detector):
    """Some OpenAI-compatible servers return {"data": [...]} without object key."""
    resp = _mock_response(200, {"data": [{"id": "custom-model"}]})
    with _patch_client({"/models": resp}):
        result = detector.detect("https://api.example.com")
    assert result == "openai_compatible"


def test_openai_compatible_detected_via_401(detector):
    """401 on /models is interpreted as an OpenAI endpoint requiring auth."""
    resp = _mock_response(401)
    with _patch_client({"/models": resp}):
        result = detector.detect("https://api.example.com")
    assert result == "openai_compatible"


def test_openai_compatible_detected_via_403(detector):
    """403 on /models is also recognised as OpenAI-compatible (auth/permission issue)."""
    resp = _mock_response(403)
    with _patch_client({"/models": resp}):
        result = detector.detect("https://api.example.com")
    assert result == "openai_compatible"


def test_gemini_compatible_detected(detector):
    """GET /v1beta/models returning {"models": [...]} → gemini_compatible."""
    # Make /models return something unrecognised (so we fall through to Gemini probe)
    models_resp = _mock_response(200, {"something": "else"})
    gemini_resp = _mock_response(200, {"models": [{"name": "gemini-3.6-flash"}]})

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kwargs):
            if "v1beta/models" in url:
                return gemini_resp
            return models_resp

    with patch("adam.model.providers.httpx.Client", return_value=MockClient()):
        result = detector.detect("https://generativelanguage.googleapis.com")
    assert result == "gemini_compatible"


def test_gemini_compatible_via_400_bad_key(detector):
    """HTTP 400 on /v1beta/models (Gemini's response to missing key) → gemini_compatible."""
    models_resp = _mock_response(404)
    gemini_resp = _mock_response(400)

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kwargs):
            if "v1beta" in url:
                return gemini_resp
            return models_resp

    with patch("adam.model.providers.httpx.Client", return_value=MockClient()):
        result = detector.detect("https://generativelanguage.googleapis.com")
    assert result == "gemini_compatible"


def test_unsupported_when_neither_detected(detector):
    """Neither probe matches → unsupported."""
    unknown_resp = _mock_response(200, {"totally": "different"})

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kwargs):
            return unknown_resp

    with patch("adam.model.providers.httpx.Client", return_value=MockClient()):
        result = detector.detect("https://weird.endpoint.example")
    assert result == "unsupported"


def test_connection_error_returns_unsupported(detector):
    """Connection error during detection → unsupported (no unhandled exception)."""
    import httpx

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kwargs):
            raise httpx.ConnectError("connection refused")

    with patch("adam.model.providers.httpx.Client", return_value=MockClient()):
        result = detector.detect("https://offline.example.com")
    assert result == "unsupported"


def test_timeout_returns_unsupported(detector):
    """Timeout during detection → unsupported (no unhandled exception)."""
    import httpx

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kwargs):
            raise httpx.TimeoutException("timed out")

    with patch("adam.model.providers.httpx.Client", return_value=MockClient()):
        result = detector.detect("https://slow.example.com")
    assert result == "unsupported"


def test_malformed_json_returns_unsupported(detector):
    """JSON parse error during detection → unsupported."""
    resp = _mock_response(200, raise_exc=ValueError("not json"))

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kwargs):
            return resp

    with patch("adam.model.providers.httpx.Client", return_value=MockClient()):
        result = detector.detect("https://bad-json.example.com")
    assert result == "unsupported"

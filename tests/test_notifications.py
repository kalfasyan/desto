from unittest.mock import MagicMock, patch


def make_response(status=200, text="{}", headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.headers = headers or {"content-type": "application/json"}
    return resp


def test_notify_with_response_success(monkeypatch):
    from desto.notifications import PushbulletNotifier

    notifier = PushbulletNotifier(api_key="test")

    with patch("desto.notifications.requests.post") as mock_post:
        mock_post.return_value = make_response(200, '{"result":"ok"}', {"x-test": "1"})
        resp = notifier.notify_with_response("title", "body")

    assert resp["ok"] is True
    assert resp["status_code"] == 200
    assert "body" in resp
    assert "headers" in resp


def test_notify_with_response_failure(monkeypatch):
    from desto.notifications import PushbulletNotifier

    notifier = PushbulletNotifier(api_key="test")

    with patch("desto.notifications.requests.post") as mock_post:
        mock_post.return_value = make_response(400, "Bad request", {"x-error": "true"})
        resp = notifier.notify_with_response("title", "body")

    assert resp["ok"] is False
    assert resp["status_code"] == 400
    assert "body" in resp
    assert "headers" in resp

import io
import json
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError


def make_response(status=200, text="{}", headers=None):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = text.encode("utf-8")
    resp.headers = headers or {"content-type": "application/json"}
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def make_http_error(status, text, headers=None):
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return HTTPError("https://api.pushbullet.com/v2/pushes", status, "error", msg, io.BytesIO(text.encode("utf-8")))


def test_notify_with_response_success():
    from desto.notifications import PushbulletNotifier

    notifier = PushbulletNotifier(api_key="test")

    with patch("desto.notifications.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_response(200, '{"result":"ok"}', {"x-test": "1"})
        resp = notifier.notify_with_response("title", "body", device_iden="dev1")

    assert resp["ok"] is True
    assert resp["status_code"] == 200
    assert resp["body"] == '{"result":"ok"}'
    assert resp["headers"] == {"x-test": "1"}

    req = mock_urlopen.call_args.args[0]
    assert req.get_method() == "POST"
    assert req.full_url == "https://api.pushbullet.com/v2/pushes"
    assert req.get_header("Access-token") == "test"
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data) == {"type": "note", "title": "title", "body": "body", "device_iden": "dev1"}
    assert mock_urlopen.call_args.kwargs["timeout"] == 5


def test_notify_with_response_failure():
    from desto.notifications import PushbulletNotifier

    notifier = PushbulletNotifier(api_key="test")

    with patch("desto.notifications.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = make_http_error(400, "Bad request", {"x-error": "true"})
        resp = notifier.notify_with_response("title", "body")

    assert resp["ok"] is False
    assert resp["status_code"] == 400
    assert resp["body"] == "Bad request"
    assert resp["headers"] == {"x-error": "true"}


def test_notify_with_response_network_error():
    from desto.notifications import PushbulletNotifier

    notifier = PushbulletNotifier(api_key="test")

    with patch("desto.notifications.urlopen", side_effect=URLError("no route")):
        resp = notifier.notify_with_response("title", "body")

    assert resp["ok"] is False
    assert resp["status_code"] is None


def test_get_devices():
    from desto.notifications import PushbulletNotifier

    notifier = PushbulletNotifier(api_key="test")
    devices = [{"iden": "a", "active": True}]

    with patch("desto.notifications.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_response(200, json.dumps({"devices": devices}))
        assert notifier.get_devices() == devices
    req = mock_urlopen.call_args.args[0]
    assert req.get_method() == "GET"
    assert req.full_url == "https://api.pushbullet.com/v2/devices"

    with patch("desto.notifications.urlopen", side_effect=make_http_error(401, "unauthorized")):
        assert notifier.get_devices() == []

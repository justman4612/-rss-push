import io
import json
from http.client import HTTPException
from email.message import Message
from unittest import TestCase, main
from unittest.mock import Mock, patch
from urllib import error, request

import dispatch


ENV = {
    "CAMPUS_REMINDER_ENDPOINT": "https://example.invalid/internal/reminders/process-due",
    "CAMPUS_SCHEDULER_TOKEN": "dummy-test-token",
    "CAMPUS_SCHEDULER_ENABLED": "true",
}
OK = {"schema_version": 1, "status": "ok", "send_mode": "smtp", "claimed": 1, "sent": 1, "failed": 0}


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload, content_type="application/json"):
        super().__init__(payload)
        self.headers = Message()
        self.headers["Content-Type"] = content_type


class DispatchTests(TestCase):
    def opener(self, value=OK):
        return Mock(open=Mock(return_value=Response(json.dumps(value).encode())))

    def test_closed_gate_prevents_network(self):
        for enabled in ("", "false", "1", "TRUE"):
            with self.subTest(enabled=enabled):
                opener = self.opener()
                with self.assertRaises(dispatch.DispatchError):
                    dispatch.dispatch(dict(ENV, CAMPUS_SCHEDULER_ENABLED=enabled), opener)
                opener.open.assert_not_called()

    def test_missing_config_prevents_network(self):
        for name in ("CAMPUS_REMINDER_ENDPOINT", "CAMPUS_SCHEDULER_TOKEN"):
            opener = self.opener()
            with self.assertRaises(dispatch.DispatchError):
                dispatch.dispatch(dict(ENV, **{name: ""}), opener)
            opener.open.assert_not_called()

    def test_rejects_unsafe_endpoint_forms(self):
        for url in ("http://example.invalid/p", "https://u:p@example.invalid/p", "https://example.invalid/p?token=x", "https://example.invalid/p#x", "https://example.invalid", "https://example.invalid:bad/p", "https://example.invalid:80/p"):
            with self.subTest(url=url), self.assertRaises(dispatch.DispatchError):
                dispatch.configuration(dict(ENV, CAMPUS_REMINDER_ENDPOINT=url))

    def test_invalid_credentials_rejected(self):
        with self.assertRaises(dispatch.DispatchError):
            dispatch.configuration(dict(ENV, CAMPUS_SCHEDULER_TOKEN="dummy\nheader"))

    def test_posts_only_request_id_and_separate_credentials(self):
        opener = self.opener()
        result = dispatch.dispatch(dict(ENV, CAMPUS_PLATFORM_TOKEN="dummy-platform", GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="2"), opener)
        self.assertEqual(result, {"claimed": 1, "sent": 1, "failed": 0})
        req = opener.open.call_args.args[0]
        self.assertEqual(req.method, "POST")
        self.assertEqual(json.loads(req.data), {"request_id": "gh-123-2"})
        self.assertEqual(req.get_header("X-campus-scheduler-token"), "dummy-test-token")
        self.assertEqual(req.get_header("Authorization"), "Bearer dummy-platform")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 45)
        opener.open.assert_called_once()

    def test_no_redirect_is_followed(self):
        handler = dispatch.NoRedirect()
        self.assertIsNone(handler.redirect_request(request.Request(ENV["CAMPUS_REMINDER_ENDPOINT"]), None, 302, "redirect", {}, "https://other.invalid/"))

    def test_network_error_is_not_retried_or_leaked(self):
        for exc in (TimeoutError("private endpoint"), error.URLError("private token"), HTTPException("private protocol")):
            opener = Mock(open=Mock(side_effect=exc))
            with self.assertRaises(dispatch.DispatchError) as caught:
                dispatch.dispatch(ENV, opener)
            self.assertNotIn("private", str(caught.exception))
            opener.open.assert_called_once()

    def test_http_error_body_is_hidden_and_not_retried(self):
        for code in (302, 401, 403, 500):
            opener = Mock(open=Mock(side_effect=error.HTTPError(ENV["CAMPUS_REMINDER_ENDPOINT"], code, "private", {}, io.BytesIO(b"secret response"))))
            with self.assertRaises(dispatch.DispatchError) as caught:
                dispatch.dispatch(ENV, opener)
            self.assertNotIn("secret", str(caught.exception))
            opener.open.assert_called_once()

    def test_send_disabled_is_not_success(self):
        with self.assertRaisesRegex(dispatch.DispatchError, "closed"):
            dispatch.dispatch(ENV, self.opener({"schema_version": 1, "status": "send_disabled"}))

    def test_rejects_mock_and_unknown_contract(self):
        for changes in ({"send_mode": "mock"}, {"schema_version": 2}, {"schema_version": True}, {"status": "unknown"}):
            with self.subTest(changes=changes), self.assertRaises(dispatch.DispatchError):
                dispatch.parse_result(json.dumps(dict(OK, **changes)))

    def test_rejects_bad_counts(self):
        for changes in ({"claimed": True}, {"sent": -1}, {"sent": "1"}, {"claimed": 0}, {"failed": 1}):
            with self.subTest(changes=changes), self.assertRaises(dispatch.DispatchError):
                dispatch.parse_result(json.dumps(dict(OK, **changes)))

    def test_rejects_error_json_without_leaking_contents(self):
        for raw in (b"secret-not-json", b"[]", b'"secret"'):
            with self.assertRaises(dispatch.DispatchError) as caught:
                dispatch.parse_result(raw)
            self.assertNotIn("secret", str(caught.exception))

    def test_rejects_non_json_and_large_body(self):
        for response in (Response(b"private", "text/html"), Response(b"x" * 16385)):
            with self.assertRaises(dispatch.DispatchError):
                dispatch.dispatch(ENV, Mock(open=Mock(return_value=response)))

    def test_validate_never_calls_network(self):
        with patch.dict("os.environ", ENV, clear=True), patch.object(dispatch.request, "build_opener") as network:
            self.assertEqual(dispatch.main(["validate"]), 0)
            network.assert_not_called()

    def test_zero_due_is_valid(self):
        self.assertEqual(dispatch.parse_result(json.dumps(dict(OK, claimed=0, sent=0))), {"claimed": 0, "sent": 0, "failed": 0})


if __name__ == "__main__":
    main()

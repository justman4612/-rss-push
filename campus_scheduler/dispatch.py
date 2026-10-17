"""Call the campus reminder service. Validation is offline; processing is opt-in."""

import argparse
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import ssl
import sys
from urllib import error, parse, request


class DispatchError(Exception):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def configuration(env):
    endpoint = env.get("CAMPUS_REMINDER_ENDPOINT", "").strip()
    token = env.get("CAMPUS_SCHEDULER_TOKEN", "").strip()
    platform_token = env.get("CAMPUS_PLATFORM_TOKEN", "").strip()
    if not endpoint or not token:
        raise DispatchError("Missing endpoint or scheduler token; no request made.")
    try:
        url = parse.urlsplit(endpoint)
        valid = (
            url.scheme == "https" and url.hostname and url.path not in ("", "/")
            and url.port in (None, 443) and not url.username and not url.password
            and not url.query and not url.fragment
            and not any(c.isspace() for c in endpoint)
        )
    except ValueError:
        valid = False
    if not valid:
        raise DispatchError("Endpoint must be an HTTPS service path without credentials or query.")
    if any(c in token + platform_token for c in ("\r", "\n")):
        raise DispatchError("Invalid credential format; no request made.")
    return endpoint, token, platform_token


def parse_result(raw):
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise DispatchError("Invalid JSON response; do not retry an uncertain send automatically.") from None
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise DispatchError("Unsupported response contract; inspect server audit before retrying.")
    if value.get("status") == "send_disabled":
        raise DispatchError("Server send gate is closed; this is not a successful reminder dispatch.")
    if value.get("status") != "ok" or value.get("send_mode") != "smtp":
        raise DispatchError("Server did not confirm SMTP processing; inspect server audit.")
    result = {}
    for key in ("claimed", "sent", "failed"):
        count = value.get(key)
        if type(count) is not int or count < 0:
            raise DispatchError("Invalid response counts; inspect server audit before retrying.")
        result[key] = count
    if result["sent"] + result["failed"] > result["claimed"]:
        raise DispatchError("Inconsistent response counts; inspect server audit.")
    if result["failed"]:
        raise DispatchError("Server reported failed deliveries; inspect server audit, no client retry.")
    return result


def dispatch(env, opener=None):
    if env.get("CAMPUS_SCHEDULER_ENABLED") != "true":
        raise DispatchError("Scheduler gate is closed; no request made.")
    endpoint, token, platform_token = configuration(env)
    run_id = env.get("GITHUB_RUN_ID", "local")
    attempt = env.get("GITHUB_RUN_ATTEMPT", "1")
    if not re.fullmatch(r"[0-9]+|local", run_id) or not re.fullmatch(r"[0-9]+", attempt):
        raise DispatchError("Invalid run identifier; no request made.")
    payload = json.dumps({"request_id": f"gh-{run_id}-{attempt}"}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Campus-Scheduler-Token": token,
    }
    if platform_token:
        headers["Authorization"] = f"Bearer {platform_token}"
    req = request.Request(endpoint, data=payload, headers=headers, method="POST")
    if opener is None:
        opener = request.build_opener(
            NoRedirect(), request.HTTPSHandler(context=ssl.create_default_context())
        )
    try:
        with opener.open(req, timeout=45) as response:
            if response.status != 200:
                raise DispatchError("Unexpected HTTP status; inspect server audit, no client retry.")
            if response.headers.get_content_type() != "application/json":
                raise DispatchError("Expected a JSON response; inspect server audit.")
            raw = response.read(16385)
            if len(raw) > 16384:
                raise DispatchError("Response too large; inspect server audit.")
    except error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise DispatchError(f"HTTP {code}; response hidden. Inspect server audit before retrying.") from None
    except (error.URLError, TimeoutError, OSError, ValueError, HTTPException):
        raise DispatchError("Connection failed or timed out; send result may be uncertain. No client retry.") from None
    return parse_result(raw)


def report(message):
    print(message)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("## Campus reminder scheduler\n\n" + message + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("validate", "process"), default="validate", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.mode == "validate":
            # Offline validation never constructs a network client or sends mail.
            configuration(os.environ)
            report("Configuration format valid. No HTTP request made; no email sent. Server not verified.")
        else:
            counts = dispatch(os.environ)
            report("SMTP processing reported by server: " + json.dumps(counts) + ". Inbox arrival not verified.")
    except DispatchError as exc:
        report(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

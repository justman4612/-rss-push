"""Explicit one-email acceptance test, not cron validation. Never retries a send."""
import os
import dispatch


def main():
    try:
        counts = dispatch.dispatch(os.environ)
        if counts != {"claimed": 1, "sent": 1, "failed": 0}:
            raise dispatch.DispatchError("One-email test did not report exactly one SMTP acceptance; inspect audit before retrying.")
        dispatch.report("One-email delayed test: claimed=1, sent=1, failed=0. Trigger is workflow_dispatch, not schedule. Inbox arrival unverified.")
        return 0
    except dispatch.DispatchError as exc:
        dispatch.report(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# Campus reminder scheduler

One operator-managed scheduler serves all users. End users do not need GitHub accounts or SMTP credentials. QQ SMTP stays on the school application's server; no SMTP credentials belong in this repository.

## Current status

Prepared client and workflows only. No verified campus HTTP endpoint or scheduler credentials have been provided. No production deployment or scheduled mail sending has been enabled. Local tests use mock HTTP and never send mail. The existing daily RSS workflow is unchanged.

## Server contract to implement and verify

The school application must expose a supported POST HTTPS route to its deterministic reminder processor. An ordinary conversational agent API is not sufficient. Do not use a temporary development preview URL as a production endpoint.

- `X-Campus-Scheduler-Token`: separate service credential, compared in constant time by the application; missing/wrong credentials fail closed before claiming rows.
- Optional `Authorization: Bearer ...`: platform API authentication, if required by the deployment. Confirm that custom scheduler headers reach the application. Do not remove platform authentication to make a test work.
- JSON body: `{"request_id":"gh-<run_id>-<attempt>"}`. This is a correlation ID, not a provider deduplication guarantee.
- Server clock, environment, schema, owner/recipient bindings, real send gate, maximum batch size and initial test allowlist are controlled on the server. Do not accept owner/email/schema/time or mock settings from this client.
- For initial end-to-end testing, the server must restrict processing to the single approved new test batch. Old pending and mock records must remain untouched.
- Successful processing response: `{"schema_version":1,"status":"ok","send_mode":"smtp","claimed":1,"sent":1,"failed":0}`. A zero-due batch uses zero counts. `sent` means SMTP accepted, not inbox arrival.
- Closed gate response: `{"schema_version":1,"status":"send_disabled"}`. The client fails visibly; it does not present this as successful dispatch.
- All non-200 responses fail. No response bodies or credentials are printed. The client makes one POST, follows no redirects and never automatically retries an uncertain SMTP outcome. Duplicate scheduling still requires database-level claiming, provider-aware handling, and audit.
- An external scheduler identity cannot bypass unresolved production schema isolation or create/read/change personal items. Do not set a deployed production instance to DEV to circumvent identity gates.

## Repository configuration (operator only)

Once the exact deployed endpoint and authentication are verified, configure repository Actions secrets:

| Secret | Value |
| --- | --- |
| `CAMPUS_REMINDER_ENDPOINT` | Exact HTTPS reminder processing route, without credentials/query string |
| `CAMPUS_SCHEDULER_TOKEN` | New dedicated service token, matching the server; not the QQ authorization code |
| `CAMPUS_PLATFORM_TOKEN` | Optional platform API credential, only if the deployment requires it |

Repository Actions variable `CAMPUS_SCHEDULER_ENABLED` must remain absent or `false` until an approved controlled trial. Only exact `true` permits any processing calls, including manual process mode. Both workflow and server send gates must be enabled deliberately for real scheduled delivery. Secrets must never be posted to issues, PRs, logs or chat.

1. Confirm application route support, authentication, production isolation and test scope. Deploy that server through the project's controlled release process.
2. Merge these workflows to the default branch. Configure endpoint/token secrets; keep the enabled variable false.
3. Run **Campus Reminder Scheduler**, mode **validate**. This checks configuration format offline and does not prove server connectivity/authentication. Server authentication and closed-gate behavior must be verified separately without sending email.
4. After explicit authorization of one new test batch and test email, configure server scope/send gate and repository enabled variable. Set the reminder more than ten minutes into the future, deadline later. Let **schedule** trigger it; manual dispatch is not periodic scheduling acceptance.
5. Record intended reminder time, Actions start time, server processing time, Message-ID and confirmed inbox receipt. Disable the repository variable and server send gate after the controlled trial. Do not blindly rerun a job after a timeout; inspect server audit first.

The cron checks every five minutes at minute 2,7,...57 (UTC). GitHub schedules may be delayed or dropped under load, and are not a punctual-delivery guarantee. In public repositories, inactive scheduled workflows can be disabled automatically; monitor the scheduler separately before wider use. A skipped job is not a health or delivery success. Routine skipped scheduled runs may still be listed by GitHub; this gate prevents processing, not creation of schedule events.

Official references: [schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [delay troubleshooting](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows), [Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## Local verification

`python -m unittest discover -s campus_scheduler -p 'test_*.py' -v`

Python standard library only. Tests use dummy credentials and mock HTTP responses. Never provide production credentials to unit tests.

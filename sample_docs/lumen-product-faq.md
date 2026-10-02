# Lumen — Product FAQ

*Fictional product from the fictional Northwind Labs. Demo data for this repository.*

## What is Lumen?

Lumen is a log search and alerting service. It ingests structured application
logs, indexes them for full-text and field search, and evaluates alert rules
against the stream as it arrives.

## Plans and pricing

Lumen has three plans. Prices are per month, billed annually.

| Plan       | Price      | Included ingest | Retention | Seats     |
| ---------- | ---------- | --------------- | --------- | --------- |
| Starter    | USD 49     | 20 GB / month   | 7 days    | 3         |
| Team       | USD 199    | 150 GB / month  | 30 days   | 15        |
| Enterprise | Custom     | Negotiated      | Up to 1 year | Unlimited |

Overage on the Starter and Team plans is billed at **USD 0.40 per GB**. There is
no overage charge on Enterprise; ingest above the negotiated volume is throttled
instead, and the account team is notified.

Monthly billing is available on Starter and Team at a 20% premium over the
annual price.

## Ingest limits

The ingest API accepts batches of up to 5 MB, or 10,000 log lines, whichever
limit is reached first. A single log line may not exceed 256 KB; longer lines
are truncated and tagged with `lumen.truncated=true`.

Per-account ingest is rate limited to 2,000 requests per minute on Starter,
10,000 on Team, and by agreement on Enterprise. Exceeding the limit returns HTTP
429 with a `Retry-After` header. The official client libraries retry
automatically with exponential backoff.

## Alerting

Alert rules are written in LQL, the Lumen Query Language. A rule is evaluated
every 60 seconds by default; the evaluation interval can be set as low as 15
seconds on Team and Enterprise. Starter accounts are fixed at 60 seconds.

Each rule supports up to five notification targets. Supported targets are
email, webhook, Slack, PagerDuty, and Opsgenie. A rule can be muted on a
schedule, for example to suppress alerts during a maintenance window.

Alert state changes are delivered at least once. Consumers should treat the
`rule_id` plus `state_changed_at` pair as an idempotency key.

## Integrations

Lumen ships first-party integrations for Kubernetes (via a DaemonSet collector),
AWS CloudWatch Logs, Fluent Bit, OpenTelemetry Collector, and syslog over TLS.
There is no first-party integration for Azure Monitor; customers use the
OpenTelemetry Collector for that path.

## Support

| Plan       | First response target | Channels                        |
| ---------- | --------------------- | ------------------------------- |
| Starter    | 2 business days       | Email                           |
| Team       | 8 business hours      | Email, chat                     |
| Enterprise | 1 hour for Sev-1      | Email, chat, phone, shared Slack |

Business hours are 09:00–18:00 UTC, Monday to Friday. Sev-1 means a complete
loss of ingest or alert delivery for the account.

## Data export and deletion

Indexed logs can be exported as newline-delimited JSON through the export API,
which streams up to 10 GB per request. Exports are available on all plans.

Deleting a Lumen account removes indexed data within 30 days. Backups are purged
on a rolling 35-day cycle, so the maximum time to full deletion is 65 days.

## Service level agreement

Enterprise contracts carry a 99.9% monthly uptime commitment for the query API,
with service credits of 10% of the monthly fee per full percentage point below
the commitment, capped at 50%. Starter and Team plans are offered without an
uptime SLA.

# Northwind Labs — Security Overview

*Fictional company. Demo data for this repository; none of this describes a real
security posture.*

## Encryption

All customer data is encrypted in transit with TLS 1.2 or higher; TLS 1.0 and
1.1 are refused at the load balancer. Data at rest is encrypted with AES-256
using keys held in a managed key service, rotated every 90 days.

Customer-managed encryption keys are available on the Enterprise plan only.
Revoking a customer-managed key makes the affected data unreadable within 15
minutes.

## Access control

Access to production systems requires hardware-backed multi-factor
authentication. There are no shared accounts and no long-lived SSH keys;
operators get short-lived certificates valid for eight hours.

Production access is granted per role, reviewed quarterly, and revoked
automatically after 30 days without use. Every production session is recorded
and retained for 400 days.

## Data retention

Operational logs are retained for 90 days. Audit logs covering authentication,
permission changes, and data exports are retained for 400 days. Customer content
follows the retention of the customer's Lumen plan.

Backups are taken every six hours, replicated to a second region, and kept for
35 days. Restore drills are run monthly, and the measured recovery point
objective is 6 hours with a recovery time objective of 4 hours.

## Incident response

Northwind Labs operates a 24/7 on-call rotation. Security incidents are
triaged within 30 minutes of detection. Confirmed incidents affecting customer
data are reported to affected customers within **72 hours** of confirmation,
with a written post-incident review published within 14 days.

Severity levels:

- **Sev-1** — confirmed unauthorised access to customer content.
- **Sev-2** — confirmed unauthorised access to metadata, or a control failure
  with customer-data exposure potential.
- **Sev-3** — control failure with no exposure path.

## Subprocessors

Northwind Labs uses three categories of subprocessor: cloud infrastructure,
email delivery, and error tracking. The current list is published on the trust
page and customers on the Team and Enterprise plans are notified 30 days before
a new subprocessor is added, with a right to object.

## Compliance

Northwind Labs completes an annual SOC 2 Type II audit covering security,
availability, and confidentiality. The report is available under NDA. A GDPR
data processing addendum is offered to all customers, with standard contractual
clauses for transfers out of the EEA.

Penetration testing is performed twice a year by an external firm; a summary
letter is shared on request, and the full report is not distributed.

## Vulnerability handling

Reports go to the security contact on the trust page. Acknowledgement is sent
within one business day. Target remediation windows, measured from triage:

| Severity | Target |
| -------- | ------ |
| Critical | 7 days |
| High     | 30 days |
| Medium   | 90 days |
| Low      | Next scheduled maintenance |

Northwind Labs does not operate a paid bug bounty programme and does not pursue
researchers who follow the published disclosure policy.

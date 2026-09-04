# Audit Rules

## Interpretation principles

- Evaluate only records from successfully collected scopes.
- Separate configuration-plane status from data-plane connectivity. An `active` status does not prove routes, security policies, DNS, or packets work end to end.
- Treat lifecycle transitions as observations unless independent time evidence proves they are stuck.
- Treat DNS synchronization as optional. `dnsStatus=close` is not a fault by itself.
- Never recommend automatic deletion, acceptance, rejection, renewal, resizing, DNS changes, or other mutations.

## Rules

| Rule | Severity | Condition | Interpretation |
|---|---:|---|---|
| `COV-001` | high | Region list query or a detail query fails for a non-permission reason | Inventory or detail coverage is incomplete |
| `COV-002` | high | API returns `401` or `403` | Authentication or read permission is insufficient |
| `COV-004` | info | API returns `404` | Check region, API version, endpoint or stale connection reference |
| `PEER-001` | high | Status is `down` or `error` | Control-plane status reports the connection unavailable or abnormal |
| `PEER-002` | medium | Status is `expired` or `consult_failed` | Connection is expired or cross-account consultation failed |
| `PEER-003` | info | Status is creating, consulting, starting, stopping, deleting or updating | Lifecycle transition observed; no stuck conclusion without transition timestamps |
| `PEER-004` | info | Status is `deleted` | Deleted state was still returned and should be reconciled with the inventory view |
| `PEER-005` | info | Status is missing or undocumented | Service-version field requires manual interpretation |
| `PEER-006` | high | Local and peer region/VPC are identical | Documented product constraints do not allow a connection from a VPC to itself |
| `PEER-007` | medium | `localRegion` conflicts with the queried region | Regional inventory and returned local-region metadata disagree |
| `PEER-008` | info | Role is missing or not initiator/acceptor | Same-region detail orientation may be ambiguous |
| `PEER-009` | medium | An active connection lacks a positive numeric bandwidth | Returned active configuration is incomplete or inconsistent |
| `PEER-010` | medium | Prepaid connection expires within 30 days | Plan manual renewal or replacement review; no renewal is executed |
| `PEER-011` | info | DNS status is wait, syncing or closing | DNS synchronization is in transition; observe and recheck if it persists |
| `PEER-012` | info | DNS status is missing or undocumented | DNS field requires manual interpretation; `close` and `open` are normal states |
| `PEER-013` | low | Detail succeeded and `deleteProtect` is false | Release protection is disabled; this is a governance observation, not a fault |
| `PEER-014` | info | Multiple IDs describe the same directed local/peer VPC tuple | Possible duplicate inventory representation; manually confirm roles and account context |

## Expiration calculation

- Parse `expiredTime` as UTC or as a timezone-less timestamp. When timezone is absent, compare it using the runtime's configured local timezone and disclose that assumption in the finding evidence.
- Apply `PEER-010` only when `paymentTiming` is `Prepaid`, parsing succeeds, and expiration is in the next 30 days.
- If expiration has passed but status has not yet become `expired`, emit `PEER-010` as high severity because status and time evidence disagree.

## Manual follow-up

- For `down`, `error`, or reachability complaints, continue with a separate read-only connectivity diagnosis that checks both VPC route tables, security groups, ACLs, CIDR overlap and DNS behavior.
- For `consult_failed`, confirm the cross-account application, account IDs and seven-day acceptance window in the console.
- For partial detail coverage, retry only after correcting read permission or transient API failure; do not fill missing fields from assumptions.

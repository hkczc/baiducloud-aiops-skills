# Audit Rules

## Interpretation Principles

- Findings describe a control-plane snapshot, not route reachability or traffic success.
- `active` and `attached` are treated as normal examples documented by current API pages.
- `attaching` and `detaching` are transitional. Without transition timestamps, they are information findings and cannot be called stuck.
- Unknown CSN statuses and instance types are retained as information because their complete enums may evolve.
- The same network resource may not be loaded into more than one CSN according to the product guide; cross-CSN duplication is checked only when account, region, type and instance ID are all present.

## Coverage and CSN Rules

| Rule | Severity | Condition | Meaning |
|---|---|---|---|
| `COV-001` | high | List/detail GET fails or pagination cannot complete | The affected scope is not fully audited |
| `COV-002` | high | HTTP 401 or 403 | Authentication or read-only authorization is insufficient |
| `COV-004` | info | HTTP 404 | Endpoint, API version, or CSN identity needs review |
| `CSN-001` | high/info | CSN status contains `fail`/`error`, or is non-empty and not `active` | Explicit failure-like status is high; other undocumented states are informational |
| `CSN-002` | high | `instanceNum` or `csnBpNum` is non-integer or negative | Metadata conflicts with the documented model |
| `CSN-003` | info | Detail `instanceNum` differs from a successfully queried network-instance count | The topology may have changed between requests, or metadata is stale |
| `CSN-004` | high/medium | Detail `csnId` or name conflicts with the list item | Identity or naming evidence differs between GETs |
| `CSN-005` | low | Active CSN successfully returns zero network instances | Empty/staged CSN needs ownership review, but is not automatically faulty |
| `CSN-006` | high | CSN list repeats the same non-empty `csnId` | List/pagination identity evidence is duplicated |
| `CSN-007` | info | Creation timestamp is present but cannot be parsed | Time evidence needs human interpretation |

## Network Instance and Topology Rules

| Rule | Severity | Condition | Meaning |
|---|---|---|---|
| `CSN-101` | high | `attachId`, `instanceId`, or `instanceRegion` is missing | The topology edge cannot be unambiguously identified |
| `CSN-102` | high | Network-instance status is `attach_failed` | CSN reports a failed attachment |
| `CSN-103` | info | Status is `attaching` or `detaching` | A transition is in progress; duration is unknown |
| `CSN-104` | info | Status is missing or outside the documented attachment enum | Service evolution or incomplete metadata needs interpretation |
| `CSN-105` | info | `instanceType` is missing or outside `vpc`, `channel`, `bec_vpc` | Preserve a potentially newer type; do not discard it |
| `CSN-106` | medium | Same CSN repeats an `attachId` | Attachment identity is duplicated |
| `CSN-107` | medium | Same CSN has multiple `attachId` values for the same account/region/type/instance ID | The network resource appears more than once in one CSN |
| `CSN-108` | high | The same complete account/region/type/instance identity appears in multiple CSNs | Product guidance says one network instance can belong to only one CSN |
| `CSN-109` | info | `instanceAccountId` or `instanceName` is missing | Ownership/naming metadata is incomplete but does not alone prove failure |
| `CSN-110` | info | One CSN spans multiple regions or account IDs | Cross-region/cross-account scope is recorded for governance review |

Selected CSN IDs not found in a successful list create `COV-001`. Duplicate checks never merge resources solely by display name.

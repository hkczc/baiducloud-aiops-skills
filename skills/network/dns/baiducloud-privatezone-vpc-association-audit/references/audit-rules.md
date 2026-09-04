# Audit Rules

## Interpretation Principles

- Findings describe PrivateZone control-plane configuration, not DNS responses or VPC connectivity.
- Association rules run only when the zone detail query succeeded and `bindVpcs` is an explicit list.
- The same VPC may legitimately use many distinct private zones.
- The same zone name may legitimately exist for disjoint VPC sets; it becomes a clear collision only when the same normalized zone name overlaps on the same VPC and region.
- A parent zone and child zone in one VPC can be a deliberate namespace boundary, so it is reported as information rather than a fault.
- VPC existence and status are not verified because this Skill does not call VPC APIs.

## Coverage and Detail Rules

| Rule | Severity | Condition | Meaning |
|---|---|---|---|
| `COV-001` | high | List/detail GET fails or pagination cannot complete | The affected scope is not fully audited |
| `COV-002` | high | HTTP 401 or 403 | Authentication or `LDReadPolicy` coverage is insufficient |
| `COV-004` | info | HTTP 404 | Endpoint, API version, or zone identity needs review |
| `PZ-001` | medium | Successful detail contains an explicit empty `bindVpcs` | The zone is not visible through any reported VPC association; staging may be intentional |
| `PZ-002` | high | Successful detail omits `bindVpcs` or returns a non-list value | Association evidence is structurally incomplete |
| `PZ-003` | high/medium | Detail `zoneId` or `zoneName` conflicts with the list item | Identity changed or response/list evidence is inconsistent |
| `PZ-004` | info | List and detail `recordCount` differ | The configuration may have changed between requests; this is not automatically corruption |
| `PZ-005` | high | `recordCount` is non-integer or negative | Metadata conflicts with the documented model |
| `PZ-006` | info | `createTime`/`updateTime` is invalid, or update precedes creation | Timestamp evidence needs review; reversed order is highlighted explicitly |

## Association and Namespace Rules

| Rule | Severity | Condition | Meaning |
|---|---|---|---|
| `PZ-101` | high | Association is missing `vpcId` or `vpcRegion` | The edge cannot be unambiguously identified |
| `PZ-102` | medium | The same zone contains duplicate `(vpcRegion, vpcId)` associations | Redundant or inconsistent association evidence |
| `PZ-103` | info | Association lacks `vpcName` | Naming metadata is incomplete but the ID/region may still identify it |
| `PZ-104` | high | One VPC ID is reported with conflicting non-empty regions | The same identifier has inconsistent regional metadata |
| `PZ-105` | medium | One `(region, VPC ID)` is reported with conflicting non-empty names | Naming metadata differs across zone details |
| `PZ-106` | high | Two zone IDs with the same normalized zone name overlap on the same `(region, VPC ID)` | The same DNS namespace is represented more than once in one VPC view |
| `PZ-107` | info | Parent and child zones are both associated with the same VPC | A more-specific private namespace may intentionally change resolution behavior |
| `PZ-108` | low | A zone with zero records is associated with one or more VPCs | It may intentionally reserve/shadow a namespace; confirm intent |
| `PZ-109` | info | A zone is associated across multiple regions | Cross-region exposure is an architecture fact for ownership review |
| `PZ-110` | high | The PrivateZone list repeats the same non-empty `zoneId` | The list snapshot contains duplicate identity evidence |

Selected zone names that do not exactly match any returned `zoneName` create a `COV-001` finding. Domain normalization is case-insensitive, removes one trailing dot, and uses IDNA for comparisons where possible.

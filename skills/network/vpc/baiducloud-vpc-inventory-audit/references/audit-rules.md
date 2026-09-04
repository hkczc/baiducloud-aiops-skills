# Audit Rules

## Contents

- Severity model
- Coverage rules
- Association rules
- Capacity and hygiene rules
- Interpretation rules

## Severity model

| Severity | Meaning |
|---|---|
| `high` | The inventory cannot support a trustworthy conclusion for a core scope |
| `medium` | A resource reference is inconsistent or capacity is near exhaustion |
| `low` | Asset hygiene or metadata is incomplete |
| `info` | Context that requires human confirmation |

## Coverage rules

| Rule ID | Condition | Severity | Interpretation |
|---|---|---|---|
| `COV-001` | VPC list query fails in a requested region | high | Mark the entire region incomplete |
| `COV-002` | A sub-product query returns 401 or 403 | high | Report the missing read-only policy |
| `COV-003` | Pagination repeats a marker or stops unexpectedly | high | Do not claim a complete inventory |
| `COV-004` | Optional API returns 404 in one region | info | Verify API availability and regional endpoint |

## Association rules

| Rule ID | Condition | Severity | Evidence |
|---|---|---|---|
| `REL-001` | Subnet references a VPC absent from the successful VPC list | medium | Region, subnet ID, referenced VPC ID |
| `REL-002` | ENI references an absent VPC or subnet | medium | Region, ENI ID, VPC ID, subnet ID |
| `REL-003` | ENI references an absent standard or enterprise security group | medium | Region, ENI ID, referenced group ID |
| `REL-004` | Route table cannot be associated with a queried VPC | medium | Region, route table ID, source response |
| `REL-005` | ACL or ACL rule references an absent subnet | medium | Region, ACL ID/rule ID, subnet ID |
| `REL-006` | Resource association is missing from the API response | info | Resource ID and missing field; request human confirmation |

Do not label a reference as absent when the referenced resource type failed collection. Emit a coverage finding instead.

## Capacity and hygiene rules

| Rule ID | Condition | Severity | Notes |
|---|---|---|---|
| `CAP-001` | `availableUnreservedIp` or `availableIp` is 16 or fewer | medium | Use the API value; do not recalculate provider-reserved addresses |
| `CAP-002` | Available IP is 10% or less of the CIDR address count | medium | Mark the ratio as approximate |
| `HYG-001` | Resource has no name | low | Exclude system-created resources only when clearly identified |
| `HYG-002` | Resource has no tags | low | Report as governance hygiene, not a network fault |
| `HYG-003` | VPC has no returned subnet | info | Could be intentional; verify collection coverage first |
| `HYG-004` | ENI is unattached or has an unexpected status | info | Report the API status without declaring it abandoned |

## Interpretation rules

- Prefer resource IDs over names when joining data.
- Preserve region as part of every join key; identical IDs across regions must not be merged.
- Do not infer packet-level reachability from inventory alone.
- Do not infer that an untagged or unattached resource is safe to delete.
- Separate API facts from conclusions in every finding.
- Mark capacity ratios as approximate because provider-reserved addresses affect usable capacity.

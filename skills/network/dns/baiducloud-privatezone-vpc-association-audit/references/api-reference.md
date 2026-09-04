# API Reference

## Service Boundary

- Product: 百度智能云智能云解析内网 DNS（Local DNS / PrivateZone）.
- Endpoint: `https://privatezone.baidubce.com`.
- Scope: global; VPC region is a response field, not an endpoint selector.
- Authentication: BCE Signature v1 with AK/SK and optional STS security token.
- This Skill permits only the two GET operations below.

## Allowed Operations

| Purpose | Method and path | Pagination | Main response fields |
|---|---|---|---|
| List PrivateZones | `GET /v1/privatezone` | `marker`, `maxKeys` (default 1000) | `zones` |
| Get one PrivateZone | `GET /v1/privatezone/{zoneId}` | none | `zoneId`, `zoneName`, `recordCount`, `createTime`, `updateTime`, `bindVpcs` |

The list response uses the `PrivateZone` model:

| Field | Meaning |
|---|---|
| `zoneId` | PrivateZone ID |
| `zoneName` | Private domain name |
| `recordCount` | Number of records reported by the service |
| `createTime`, `updateTime` | Creation and update timestamps |

The detail response adds `bindVpcs`. Each VPC association contains:

| Field | Meaning |
|---|---|
| `vpcId` | Associated VPC ID |
| `vpcName` | Associated VPC name |
| `vpcRegion` | Region of the associated VPC, such as `bj` |

Unknown response fields are preserved. An absent or non-list `bindVpcs` is treated as incomplete/invalid detail evidence, not silently converted into a confirmed empty association list.

## Pagination and Coverage

- Continue while `isTruncated` is true and pass `nextMarker` to the same GET request.
- Stop with a coverage error if `nextMarker` is missing or repeats.
- After a successful list, query every selected zone by `zoneId` to obtain `bindVpcs`.
- A successful empty zone list means the credential can see zero PrivateZones.
- A successful detail with an explicit empty `bindVpcs` means the zone currently reports no VPC associations.
- A failed detail or missing/non-list `bindVpcs` does not prove that the zone is unassociated.

## Deliberately Excluded Operations

- No VPC association/disassociation APIs.
- No PrivateZone create/delete APIs.
- No record list or record mutation APIs; `recordCount` is used only as returned metadata.
- No VPC service APIs. Therefore this Skill cannot prove VPC existence, CIDR, status, ownership, subnet coverage, or network reachability.

## Official Documentation

- PrivateZone list: https://cloud.baidu.com/doc/DNS/s/Bkk6l42dl
- PrivateZone detail and `bindVpcs`: https://cloud.baidu.com/doc/DNS/s/Jkk6lc8li
- Local DNS SDK and global endpoint: https://cloud.baidu.com/doc/DNS/s/7lr02urop
- Model appendix: https://intl.cloud.baidu.com/zh/doc/DNS/s/Ukk6c64q3-intl
- IAM policy scope: https://intl.cloud.baidu.com/en/doc/DNS/s/njwvywyto-intl-en

Official pages also link write APIs. Their presence in the documentation does not authorize their use; the runtime rejects every method other than GET.

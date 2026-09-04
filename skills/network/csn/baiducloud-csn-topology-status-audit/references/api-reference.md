# API Reference

## Service Boundary

- Product: 百度智能云云智能网（Cloud Smart Network, CSN）.
- Endpoint: `https://csn.baidubce.com`.
- Scope: global; regions appear in network-instance metadata.
- Authentication: BCE Signature v1 with AK/SK and optional STS security token.
- This Skill permits only the three GET operations below.

## Allowed Operations

| Purpose | Method and path | Pagination | Main response fields |
|---|---|---|---|
| List CSNs | `GET /v1/csn` | `marker`, `maxKeys` | `csns` |
| Get one CSN | `GET /v1/csn/{csnId}` | none | `csnId`, `name`, `description`, `status`, `instanceNum`, `csnBpNum`, creation time, `tags` |
| List loaded network instances | `GET /v1/csn/{csnId}/instance` | `marker`, `maxKeys` | `instances` |

For list APIs, `maxKeys` defaults to 1000 and the documented maximum is 1000.

## Csn Fields Used

| Field | Meaning |
|---|---|
| `csnId` | CSN ID |
| `name`, `description` | Human-readable metadata |
| `status` | CSN control-plane status; current examples show `active`, but the appendix does not publish a complete enum |
| `instanceNum` | Number of loaded network instances reported by CSN |
| `csnBpNum` | Number of bound CSN bandwidth packages |
| `createTime` or `createdTime` | Creation timestamp; current list/detail examples use different spellings |
| `tags` | Tag key/value list |

## Instance Fields and Enums

| Field | Meaning |
|---|---|
| `attachId` | Identity of the attachment inside CSN |
| `instanceType` | Documented values: `vpc`, `channel`, `bec_vpc` |
| `instanceId`, `instanceName` | Network-instance identity and name |
| `instanceRegion` | Network-instance region |
| `instanceAccountId` | Owning main-account ID |
| `status` | `attached`, `attaching`, `detaching`, or `attach_failed` |

The product guide may add newer network-instance categories before the appendix enum is updated. Preserve and report unknown values; do not discard them or infer write actions.

## Pagination and Coverage

- Continue while `isTruncated` is true and pass `nextMarker` to the same GET request.
- Stop with a coverage error if `nextMarker` is missing or repeats.
- After a successful CSN list, query both detail and the complete network-instance list for every selected CSN.
- A successful empty CSN list means the credential can see zero CSNs.
- A successful empty `instances` list means that CSN returned zero loaded network instances.
- A failed detail/list request is not equivalent to an empty result.

## Deliberately Excluded

- Route tables, associations, propagations and route entries are reserved for the separate route-association audit.
- Bandwidth-package and regional-bandwidth APIs are not called; `csnBpNum` is retained only as CSN metadata.
- No VPC, dedicated-line or edge-network APIs are called, so existence, CIDR and resource health are not verified.
- No data-plane connectivity test is performed.

## Official Documentation

- Service endpoint and initialization: https://cloud.baidu.com/doc/CSN/s/Pldla4du4
- CSN list: https://cloud.baidu.com/doc/CSN/s/Ll0ucpv6y
- CSN detail: https://cloud.baidu.com/doc/CSN/s/xl14zx3lf
- Network-instance list: https://cloud.baidu.com/doc/CSN/s/nl0unomuo
- Models and enums: https://cloud.baidu.com/doc/CSN/s/Xl511tehn
- IAM policy scope: https://cloud.baidu.com/doc/CSN/s/Bl9e6oq2t

Official pages also link write APIs. Their presence in the documentation does not authorize their use; the runtime rejects every method other than GET.

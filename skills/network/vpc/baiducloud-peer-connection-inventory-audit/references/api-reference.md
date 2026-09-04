# API and Field Reference

## Contents

- Read-only boundary
- Endpoint selection
- Collected APIs
- Detail-query role handling
- Pagination and partial results
- Normalized snapshot
- Official references

## Read-only boundary

Use HTTPS only. The bundled collector exposes only GET requests and rejects every other HTTP method before network I/O.

## Endpoint selection

Construct the default regional endpoint as `https://bcc.<region>.baidubce.com`, for example `https://bcc.bj.baidubce.com` for Beijing. Use `--endpoint REGION=https://host` only for a documented regional override.

The script rejects non-HTTPS origins, origins containing a path, and hosts outside `*.baidubce.com`, so a credential or STS token cannot be redirected to an arbitrary host.

## Collected APIs

| Purpose | Method and path | Parameters | Primary response fields |
|---|---|---|---|
| List peering connections | `GET /v1/peerconn` | optional `vpcId`; pagination `marker`, `maxKeys` | `peerConns`, `isTruncated`, `nextMarker`, `maxKeys` |
| View one connection | `GET /v1/peerconn/{peerConnId}` | optional `role` | PeerConn fields, `tags`, `deleteProtect` |

The bundled workflow intentionally omits `vpcId` so the list covers the selected region. It requests up to 1000 records per page and follows `nextMarker` while `isTruncated` is true.

## Detail-query role handling

The detail API documents `role=initiator` and `role=acceptor`. For a same-region connection, omitting `role` may return either side. Therefore, the collector copies the role returned by the list API into every detail request. If the list returns an unknown or missing role, the collector omits the parameter and records a role-quality finding rather than inventing a value.

## PeerConn fields

| Field | Meaning |
|---|---|
| `peerConnId` | Peering connection ID |
| `role` | `initiator` or `acceptor` |
| `status` | Connection lifecycle status |
| `bandwidthInMbps` | Bandwidth in Mbps |
| `localIfId`, `localIfName` | Local interface ID and name |
| `localVpcId`, `localRegion` | Local VPC and region |
| `peerVpcId`, `peerRegion` | Peer VPC and region |
| `peerAccountId` | Peer account ID when returned |
| `paymentTiming` | `Prepaid` or `Postpaid` |
| `createdTime`, `expiredTime` | Creation and optional expiration time |
| `dnsStatus` | DNS synchronization state |
| `tags` | Tags returned by the detail API |
| `deleteProtect` | Release-protection state returned by the detail API |

Documented connection statuses are `creating`, `consulting`, `consult_failed`, `active`, `down`, `starting`, `stopping`, `deleting`, `deleted`, `expired`, `error`, and `updating`.

Documented DNS statuses are `close`, `wait`, `syncing`, `open`, and `closing`. DNS synchronization is optional, so `close` alone is not an audit finding.

## Pagination and partial results

- Detect a missing or repeated `nextMarker` and stop instead of looping indefinitely.
- Store only sanitized HTTP status, service error code, request ID, API path and connection scope for failed calls.
- Never store request headers, URLs containing credentials, AK, SK, STS Token or Authorization values.
- If the list succeeds but one detail fails, retain the list record with `_detailStatus: failed`; do not treat missing detail-only fields as configuration problems.
- A list failure sets both list and detail coverage to failed or blocked. An empty successful list sets detail coverage to success with zero queries.

## Normalized snapshot

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "UTC timestamp",
  "mode": "live or offline",
  "regions": {
    "bj": {
      "endpoint": "https://bcc.bj.baidubce.com",
      "resources": {
        "peerConnections": []
      },
      "coverage": {
        "listPeerConnections": {},
        "detailPeerConnections": {}
      },
      "errors": []
    }
  }
}
```

For live collection, each connection carries `_detailStatus` with `success`, `failed`, or `skipped`. Source API fields remain unmodified except where detail fields replace same-named list fields.

## Official references

- 查询对等连接列表: https://cloud.baidu.com/doc/VPC/s/Fjwvyuemr
- 查看对等连接详情: https://cloud.baidu.com/doc/VPC/s/Sjwvyudwm
- PeerConn、PeerConnStatus 与 DnsStatus: https://cloud.baidu.com/doc/VPC/s/9jwvyubqq
- VPC 多用户访问控制: https://cloud.baidu.com/doc/VPC/s/2jwvytwrr

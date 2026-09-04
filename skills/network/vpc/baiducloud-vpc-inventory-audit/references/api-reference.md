# API and Field Reference

## Contents

- Read-only boundary
- Endpoint selection
- Collected APIs
- Pagination and partial results
- Normalized inventory schema
- Official references

## Read-only boundary

Use HTTPS only. The bundled collector exposes only GET requests and rejects any other HTTP method before network I/O.

## Endpoint selection

Construct the default regional endpoint as `https://bcc.<region>.baidubce.com`, for example:

| Region code | Endpoint |
|---|---|
| `bj` | `https://bcc.bj.baidubce.com` |
| `gz` | `https://bcc.gz.baidubce.com` |
| `su` | `https://bcc.su.baidubce.com` |
| `fsh` | `https://bcc.fsh.baidubce.com` |
| `hkg` | `https://bcc.hkg.baidubce.com` |
| `bd` | `https://bcc.bd.baidubce.com` |
| `fwh` | `https://bcc.fwh.baidubce.com` |
| `sin` | `https://bcc.sin.baidubce.com` |

Use `--endpoint REGION=https://host` for a documented region whose endpoint does not follow the template. Reject non-HTTPS overrides.
Reject overrides outside the official `*.baidubce.com` domain so credentials and STS tokens cannot be sent to an untrusted host.

## Collected APIs

| Resource | Method and path | Scope | Primary response fields |
|---|---|---|---|
| VPC | `GET /v1/vpc` | Region | `vpcs`, `nextMarker`, `isTruncated` |
| Subnet | `GET /v1/subnet` | Region or VPC | `subnets`, `availableIp`, `availableUnreservedIp` |
| Route table | `GET /v1/route?vpcId=...` | VPC | `routeTableId`, `routeRules` |
| Route rules | `GET /v1/route/rule?vpcId=...` | VPC | `routeRules`, pagination fields when returned |
| Standard security group | `GET /v2/securityGroup?vpcId=...` | VPC | `securityGroups` |
| Enterprise security group | `GET /v1/enterprise/security` | Region | `enterpriseSecurityGroups` |
| ACL summary | `GET /v1/acl?vpcId=...` | VPC | Service-version-dependent ACL collection fields |
| Subnet ACL rules | `GET /v1/acl/rule?subnetId=...` | Subnet | ACL rules and pagination fields |
| ENI | `GET /v1/eni?vpcId=...` | VPC | `enis`, security-group references, private IPs |

The collector stores unrecognized response fields in the raw snapshot. Do not discard fields merely because they are not rendered in the Markdown report.

## Pagination and partial results

- Request at most 1000 records per page.
- Continue with `nextMarker` only when `isTruncated` is true.
- Detect repeated markers and stop with an error to avoid an infinite loop.
- Record HTTP status, error code, request ID and resource type for failed calls without storing credentials or authorization headers.
- Treat `403` on one sub-product as a coverage gap, not proof that the resource type is empty.

## Normalized inventory schema

The top-level JSON object contains:

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "UTC timestamp",
  "mode": "live or offline",
  "regions": {
    "bj": {
      "endpoint": "https://bcc.bj.baidubce.com",
      "resources": {
        "vpcs": [],
        "subnets": [],
        "routeTables": [],
        "securityGroups": [],
        "enterpriseSecurityGroups": [],
        "acls": [],
        "enis": []
      },
      "coverage": {},
      "errors": []
    }
  }
}
```

Normalize identifiers using the first present field from documented variants, but retain the source record:

- VPC: `vpcId` or `id`
- Subnet: `subnetId` or `id`
- Route table: `routeTableId` or `id`
- Security group: `securityGroupId` or `id`
- Enterprise security group: `enterpriseSecurityGroupId` or `id`
- ACL: `aclId`, `aclRuleId`, or `id`
- ENI: `eniId` or `id`

## Official references

- VPC API and SDK: https://cloud.baidu.com/doc/VPC/s/Kkclobk8o
- Query VPC list: https://cloud.baidu.com/doc/VPC/s/wjwvyub23
- Query subnet list: https://cloud.baidu.com/doc/VPC/s/xjwvyu8zu
- Route table: https://intl.cloud.baidu.com/zh/doc/VPC/s/ek0bx6ga0-intl
- Security group: https://cloud.baidu.com/doc/VPC/s/ak10bj55v
- Elastic network interface: https://cloud.baidu.com/doc/VPC/s/Mlqbsgag0
- Multi-user access control: https://cloud.baidu.com/doc/VPC/s/2jwvytwrr
- Official Python SDK source: https://github.com/baidubce/bce-sdk-python

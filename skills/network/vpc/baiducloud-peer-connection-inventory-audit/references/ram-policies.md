# RAM Policies

## Required Permissions

Use a dedicated IAM sub-user or STS credential. Grant only the official read-only policy required for this Skill.

| Resource | Official read-only system policy | Purpose |
|---|---|---|
| VPC peering connection | `PEERCONNReadPolicy` | List peering instances, view instance details, and view cross-account connection applications |

This Skill calls only the first two categories of read operations: instance list and instance detail. It does not accept, reject, create, update, resize, renew, change DNS synchronization, or release a connection.

## Recommended RAM Policy

Prefer the official `PEERCONNReadPolicy`, because 百度智能云 maintains its action set as APIs evolve.

When a custom policy is mandatory, start with the following minimum read-only template. Validate the permission identifier in the target IAM console before assignment. If it is rejected, use the official system policy above instead of substituting an operate or full-control permission.

```json
{
  "version": "v1",
  "accessControlList": [
    {
      "service": "bce:network",
      "region": "*",
      "resource": [
        "*"
      ],
      "effect": "Allow",
      "permission": [
        "PEERCONN_READ"
      ]
    }
  ]
}
```

## Notes

- Do not grant `PEERCONNOperatePolicy` or `PEERCONNFullControlPolicy` for this Skill.
- Do not grant permissions with create, accept, reject, update, resize, renew, DNS-change, release, `OPERATE`, or `FULL_CONTROL` semantics.
- Replace the wildcard region with the audited regions when the IAM policy editor supports regional scoping.
- A successful list query does not prove all detail queries succeeded. Review list and detail coverage independently.
- A `403` is a coverage gap, not proof that no peering connection exists.
- Keep credentials outside the Skill package. Prefer short-lived STS credentials. If a local JSON credential file is required, restrict it with `chmod 600` and pass only its path through `--credentials-file`.

## Official Reference

- 百度智能云 VPC 多用户访问控制: https://cloud.baidu.com/doc/VPC/s/2jwvytwrr

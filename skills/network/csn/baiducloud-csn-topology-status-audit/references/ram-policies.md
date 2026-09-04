# RAM Policies

## Required Permissions

Use a dedicated IAM sub-user or STS credential. Grant only the official read-only system policy required by this Skill.

| Resource | Official read-only system policy | Purpose |
|---|---|---|
| Cloud Smart Network | `CSNReadOnlyAccessPolicy` | List CSNs, read CSN details, and view network-instance information |

This Skill does not require operate/full-control, VPC, route-change, bandwidth-package or regional-bandwidth permissions.

## Recommended RAM Policy

Prefer the official `CSNReadOnlyAccessPolicy`, because 百度智能云 maintains its exact action set as APIs evolve. If a custom policy is mandatory, start with this minimum read-only template:

```json
{
  "version": "v1",
  "accessControlList": [
    {
      "service": "bce:csn",
      "region": "*",
      "resource": [
        "*"
      ],
      "effect": "Allow",
      "permission": [
        "CSN_READ"
      ]
    }
  ]
}
```

The public guide documents the system policy and visual policy generator but does not publish raw custom-policy identifiers. Validate `service` and `permission` in the target IAM console before assignment. If either is rejected, attach the official `CSNReadOnlyAccessPolicy`; do not substitute an operate or full-control policy.

## Notes

- Do not grant `CSNOperateAccessPolicy` or `CSNFullControlPolicy` for this Skill.
- Do not grant permissions with create, update, delete, attach, detach, associate, propagate, route-change, bandwidth-change, `OPERATE`, or `FULL_CONTROL` semantics.
- CSN APIs are global; use the IAM scope recommended by the console. Network-instance regions are response metadata.
- When instance-level authorization is required, select only the intended CSNs and confirm list, detail and network-instance-list coverage.
- A successful CSN list does not prove all per-CSN queries succeeded. Review detail and network-instance coverage independently.
- A `403` is a coverage gap, not proof that a CSN or network instance does not exist.
- Keep credentials outside the Skill package. Prefer temporary STS credentials. If a JSON credential file is required, restrict it with `chmod 600` and pass only its path through `--credentials-file`.

## Official Reference

- 百度智能云 CSN 多用户访问控制: https://cloud.baidu.com/doc/CSN/s/Bl9e6oq2t

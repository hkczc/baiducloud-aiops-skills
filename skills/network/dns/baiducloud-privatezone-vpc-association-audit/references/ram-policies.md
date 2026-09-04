# RAM Policies

## Required Permissions

Use a dedicated IAM sub-user or STS credential. Grant only the official read-only system policy required by this Skill.

| Resource | Official read-only system policy | Purpose |
|---|---|---|
| Local DNS / PrivateZone | `LDReadPolicy` | Query the private-domain list and view PrivateZone details, including associated VPC metadata |

The Skill does not require VPC read permission because it does not call VPC APIs. It also does not require public DNS, resolver, operation, or full-control permissions.

## Recommended RAM Policy

Prefer the official `LDReadPolicy`, because 百度智能云 maintains its exact action set as APIs evolve. If a custom policy is mandatory, start with this read-only template:

```json
{
  "version": "v1",
  "accessControlList": [
    {
      "service": "bce:localdns",
      "region": "*",
      "resource": [
        "*"
      ],
      "effect": "Allow",
      "permission": [
        "LD_READ"
      ]
    }
  ]
}
```

The public guide documents the `LDReadPolicy` capability but does not publish raw custom-policy identifiers. Validate `service` and `permission` in the target IAM visual editor before assignment. If the editor rejects either identifier, attach the official `LDReadPolicy`; do not substitute `LDOperatePolicy` or `LDFullControlPolicy`.

## Notes

- Do not grant `LDOperatePolicy` or `LDFullControlPolicy` for this Skill.
- Do not grant permissions with create, delete, bind, unbind, associate, disassociate, update, enable, disable, `OPERATE`, or `FULL_CONTROL` semantics.
- Local DNS is global, so use the IAM scope recommended by the console; the associated VPC region is only returned metadata.
- If instance-level authorization is required, select only the intended PrivateZones and confirm both list and detail access.
- A successful list query does not prove all detail queries succeeded. Review detail coverage independently.
- A `403` is a coverage gap, not proof that a PrivateZone or association does not exist.
- Keep credentials outside the Skill package. Prefer temporary STS credentials. If a JSON credential file is required, restrict it with `chmod 600` and pass only its path through `--credentials-file`.

## Official Reference

- 百度智能云 DNS Identity and access management: https://intl.cloud.baidu.com/en/doc/DNS/s/njwvywyto-intl-en

# RAM Policies

## Required Permissions

Use a dedicated IAM sub-user or an STS credential. Grant only the official read-only system policies required by the selected collection scope.

| Resource | Official read-only system policy | Purpose |
|---|---|---|
| VPC | `VpcReadOnlyAccessPolicy` | List VPCs and read VPC details |
| Subnet | `SubnetReadOnlyAccessPolicy` | List subnets and read capacity metadata |
| Route table | `RouteReadOnlyAccessPolicy` | Read route tables and route rules |
| Standard security group | `SecurityGroupReadOnlyAccessPolicy` | List security groups and read details |
| Enterprise security group | `ESGReadAccessPolicy` | List enterprise security groups |
| ACL | `AclReadPolicy` | List VPC ACLs and subnet ACL rules |
| Elastic network interface | `ENICReadOnlyAccessPolicy` | List ENIs and read their associations |

The official system policies are preferred because 百度智能云 maintains their action sets as APIs evolve. Omit a policy only when the corresponding resource type is explicitly excluded from the audit.

## Recommended RAM Policy

When a custom policy is mandatory, use the following minimum read-only template. Validate the permission identifiers in the target IAM console before assignment; if the console rejects an identifier, use the official system policies above rather than substituting an operate or full-control permission.

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
        "VPC_READ",
        "SUBNET_READ",
        "ROUTE_READ",
        "SECURITY_GROUP_READ",
        "ESG_READ",
        "ACL_READ",
        "ENIC_READ"
      ]
    }
  ]
}
```

## Notes

- Do not grant any permission containing `OPERATE`, `FULL_CONTROL`, create, update, delete, bind, unbind, attach, detach, authorize, or revoke semantics.
- Replace the wildcard region with the audited regions when the IAM policy editor supports regional scoping.
- Narrow the resource scope when the target account supports instance-level authorization and the audit covers named VPCs only.
- `VpcReadOnlyAccessPolicy` alone does not imply read access to every VPC sub-product; attach each required sub-product policy explicitly.
- The script continues after optional-resource `403` responses and reports incomplete coverage. A successful report with permission gaps is not a complete account inventory.
- Keep credentials outside the Skill package. Prefer temporary STS credentials and expire them after validation. If a local JSON credential file is required, restrict it with `chmod 600`, pass only its path through `--credentials-file`, and delete it after the test.

## Official Reference

- 百度智能云 VPC 多用户访问控制: https://cloud.baidu.com/doc/VPC/s/2jwvytwrr

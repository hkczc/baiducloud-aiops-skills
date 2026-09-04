---
name: baiducloud-privatezone-vpc-association-audit
description: 只读查询并审计百度智能云内网 DNS PrivateZone 及其 VPC 关联，生成私有域到 VPC/地域的关联拓扑、查询覆盖率和配置异常报告。用于用户要求盘点私有域关联、检查无关联域、重复或字段异常关联、同名及父子域在同一 VPC 的解析边界，或排查 PrivateZone 可见范围时；不得用于创建或删除私有域、关联或解关联 VPC、修改解析记录，也不能替代 VPC 存在性和实际 DNS 应答验证。
---

# 百度智能云 PrivateZone 与 VPC 关联配置审计

## 只读边界

- 仅向 `https://privatezone.baidubce.com` 执行 PrivateZone 列表和详情 HTTPS `GET` 请求，以及本地文件读取与报告生成。
- 禁止执行 `POST`、`PUT`、`PATCH`、`DELETE`，禁止创建或删除私有域、关联或解关联 VPC、增删改解析记录或改变记录状态。
- 不因账号拥有更高权限而放宽限制；只输出查询事实、覆盖率、规则发现和人工复核建议。
- 不在命令参数、日志、报告或 Skill 包中写入 AK、SK、STS Token、Authorization 头。
- 详情中的 `bindVpcs` 是关联配置证据，不证明对应 VPC 当前存在、网络连通或 DNS 查询一定成功。

## 执行工作流

1. 阅读 [RAM 权限](references/ram-policies.md)，优先使用仅绑定官方 `LDReadPolicy` 的 IAM 子用户或受限 STS 凭证。
2. 阅读 [API 与字段说明](references/api-reference.md)。内网 DNS 是全局服务，不需要地域请求参数；VPC 地域来自详情中的 `vpcRegion`。
3. 检查环境变量 `BCE_ACCESS_KEY_ID`、`BCE_SECRET_ACCESS_KEY`；使用 STS 时同时检查 `BCE_SESSION_TOKEN`，不要回显。也可在 Skill 目录外放置权限为 `600` 的 JSON 凭证文件，字段为 `accessKeyId`、`secretAccessKey` 和可选的 `sessionToken`。
4. 将输出目录放在 Skill 目录外，审计全部 PrivateZone：

   ```bash
   python3 scripts/privatezone_vpc_association_audit.py \
     --output-dir /absolute/path/to/privatezone-vpc-audit-output
   ```

   使用受限凭证文件时：

   ```bash
   python3 scripts/privatezone_vpc_association_audit.py \
     --credentials-file /absolute/path/to/credentials.json \
     --output-dir /absolute/path/to/privatezone-vpc-audit-output
   ```

5. 只审计指定私有域时，使用逗号分隔的精确域名；脚本会先完整分页查询列表，再在本地做不区分大小写、忽略末尾点的精确匹配：

   ```bash
   python3 scripts/privatezone_vpc_association_audit.py \
     --zones corp.example,svc.example \
     --output-dir /absolute/path/to/privatezone-vpc-audit-output
   ```

6. 使用已有快照时进入离线模式：

   ```bash
   python3 scripts/privatezone_vpc_association_audit.py \
     --input /absolute/path/to/privatezone-vpc-snapshot.json \
     --output-dir /absolute/path/to/privatezone-vpc-audit-output
   ```

7. 先核对“采集覆盖率”。列表查询失败时无法盘点 PrivateZone；任一详情失败时，该域的 VPC 关联未知，不能当成无关联。
8. 依据 [审计规则](references/audit-rules.md)复核发现。同名私有域绑定不同 VPC、父子域同时绑定同一 VPC、零记录域或跨地域关联都可能是有意设计，除非存在明确冲突，否则仅作提示。
9. 返回：审计范围、PrivateZone 数、关联边数、唯一 VPC 数、地域分布、域到 VPC 拓扑、覆盖缺口、发现、限制与人工建议。

## 输出要求

- `inventory.json` 保存原始 API 字段、详情覆盖率和分析结果；`report.md` 保存中文审计报告。
- 每条发现包含规则编号、严重度、PrivateZone ID/名称、VPC ID/名称/地域、事实、解释和证据。
- 详情查询失败时保留列表摘要并设置 `_detailStatus=failed`；不得丢弃该域或把 `bindVpcs` 解释为空。
- 没有发现时只能说“在成功查询且规则覆盖的配置范围内未发现命中”，不得声称关联或解析一定正常。
- 域名、VPC 标识、地域与关联拓扑不得发送到未获用户授权的外部服务。

## 失败处理

- `401`：检查凭证、STS Token 和系统时间，不要求用户在对话中粘贴密钥。
- `403`：确认绑定 `LDReadPolicy`，保留成功结果并标记覆盖不完整。
- `404`：核对 Endpoint、PrivateZone ID 和 API 版本；不得改用写接口试探。
- `429` 或 `5xx`：只对相同 GET 请求做有限退避重试。
- 单个详情失败时继续查询其他域，并明确该域的关联状态“未知”而非“无关联”。

## 本地验证

以下命令不访问云环境：

```bash
python3 scripts/privatezone_vpc_association_audit.py --self-test
python3 scripts/privatezone_vpc_association_audit.py \
  --input examples/sample-privatezone-vpc.json \
  --output-dir /tmp/baiducloud-privatezone-vpc-association-audit
```

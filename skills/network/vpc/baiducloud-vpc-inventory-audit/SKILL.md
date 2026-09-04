---
name: baiducloud-vpc-inventory-audit
description: 只读查询并审计百度智能云私有网络 VPC 资产、子网、路由表、安全组、企业安全组、ACL 与弹性网卡，生成按地域和 VPC 聚合的资源清单、关联拓扑、查询覆盖率及异常引用报告。用于用户要求盘点 VPC 网络资产、梳理网络拓扑、核查资源关联、检查子网余量或确认只读查询权限时；不得用于创建、修改、绑定、解绑或删除任何云资源。
---

# 百度智能云 VPC 资产与拓扑巡检

## 坚持只读边界

- 仅执行 HTTPS `GET` 请求以及本地文件读取和报告生成。
- 禁止执行 `POST`、`PUT`、`PATCH`、`DELETE`，禁止调用名称含 create、update、delete、bind、unbind、attach、detach、authorize、revoke、operate 的云 API 或 SDK 方法。
- 不因用户账号拥有更高权限而放宽限制。
- 仅输出发现、证据和人工整改建议；不实施整改。
- 不在命令参数、日志、报告或 Skill 包中写入 AK、SK 或 STS Token。

## 执行工作流

1. 确认巡检地域。缺少地域时先询问；不要猜测地域或扫描所有地域。
2. 阅读 [RAM 权限](references/ram-policies.md)。优先要求子用户或 STS 临时凭证绑定官方只读系统策略。
3. 阅读 [API 与字段说明](references/api-reference.md)，确认地域 Endpoint 和采集范围。
4. 检查环境变量 `BCE_ACCESS_KEY_ID`、`BCE_SECRET_ACCESS_KEY`；使用 STS 时同时检查 `BCE_SESSION_TOKEN`。不要回显变量值。若执行环境无法安全继承变量，可在 Skill 目录外创建仅当前用户可读的 JSON 文件，字段为 `accessKeyId`、`secretAccessKey` 和可选的 `sessionToken`，执行 `chmod 600` 后通过 `--credentials-file` 指定；不得把凭证值放入命令参数。
5. 运行采集脚本。将输出目录设置在 Skill 目录外：

   ```bash
   python3 scripts/vpc_inventory_audit.py \
     --regions bj,gz \
     --output-dir /absolute/path/to/audit-output
   ```

   使用受限凭证文件时：

   ```bash
   python3 scripts/vpc_inventory_audit.py \
     --credentials-file /absolute/path/to/credentials.json \
     --regions bj \
     --output-dir /absolute/path/to/audit-output
   ```

6. 若用户仅提供导出的 JSON，使用离线模式：

   ```bash
   python3 scripts/vpc_inventory_audit.py \
     --input /absolute/path/to/inventory.json \
     --output-dir /absolute/path/to/audit-output
   ```

7. 先检查报告中的“采集覆盖率”。任何资源类型查询失败时，将结论标记为不完整，不把“未查询到”解释为“资源不存在”。
8. 按 [审计规则](references/audit-rules.md)复核脚本发现，区分已证实异常、可能异常和信息缺口。
9. 向用户返回：巡检范围、采集覆盖率、资源汇总、拓扑关系、发现、证据、限制和后续人工建议。

## 输出要求

- 将 `inventory.json` 作为机器可读原始快照，将 `report.md` 作为面向用户的巡检报告。
- 对每条发现给出地域、VPC ID、相关资源 ID、规则编号和证据字段。
- 不把资源名称、内网 IP、CIDR 或账号网络拓扑发送到未获用户授权的外部服务。
- 报告为空时说明“在已成功查询的范围内未发现问题”，不得声明整个账号无问题。

## 失败处理

- `401`：提示检查 AK/SK、STS Token 和系统时间，不要求用户把密钥粘贴到对话中。
- `403`：列出失败的资源类型和所需只读系统策略；保留其他成功结果。
- `404`：核对地域 Endpoint 和 API 版本；不要改用写接口试探。
- `429` 或 `5xx`：允许脚本以相同 GET 请求退避重试；不得改变请求方法。
- 单地域核心 VPC 列表查询失败时，将该地域标记为失败；不要生成虚假的空拓扑。

## 本地验证

使用随包示例验证分析和报告生成，不访问云环境：

```bash
python3 scripts/vpc_inventory_audit.py --self-test
python3 scripts/vpc_inventory_audit.py \
  --input examples/sample-inventory.json \
  --output-dir /tmp/baiducloud-vpc-inventory-audit
```

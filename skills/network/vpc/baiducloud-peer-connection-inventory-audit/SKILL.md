---
name: baiducloud-peer-connection-inventory-audit
description: 只读查询并审计百度智能云 VPC 对等连接实例，按地域盘点本端与对端 VPC、角色、状态、带宽、计费、到期时间、DNS 同步、标签和释放保护，生成查询覆盖率、连接拓扑与状态异常报告。用于用户要求梳理对等连接资产、核查实例状态、发现临近到期连接、确认详情查询权限或排查连接清单异常时；不得用于创建、接受、拒绝、修改、续费、调整带宽、开启或关闭 DNS 同步、释放对等连接。
---

# 百度智能云对等连接资产与状态巡检

## 坚持只读边界

- 仅执行 HTTPS `GET` 请求以及本地文件读取和报告生成。
- 禁止执行 `POST`、`PUT`、`PATCH`、`DELETE`，禁止调用创建、接受、拒绝、修改、续费、升降配、开启或关闭 DNS 同步、释放等接口。
- 不因账号拥有更高权限而放宽限制。
- 仅输出配置事实、查询覆盖率、风险提示和人工复核建议；不实施整改。
- 不在命令参数、日志、报告或 Skill 包中写入 AK、SK、STS Token 或 Authorization 头。

## 执行工作流

1. 确认需要巡检的地域。缺少地域时先询问，不猜测地域，也不自动扫描所有地域。
2. 阅读 [RAM 权限](references/ram-policies.md)，优先使用仅绑定官方 `PEERCONNReadPolicy` 的子用户或 STS 临时凭证。
3. 阅读 [API 与字段说明](references/api-reference.md)。列表查询后，对每个实例按列表返回的 `role` 查询详情；同地域连接不得省略 `role`。
4. 检查环境变量 `BCE_ACCESS_KEY_ID`、`BCE_SECRET_ACCESS_KEY`；使用 STS 时同时检查 `BCE_SESSION_TOKEN`。不要回显变量值。若无法安全继承环境变量，可在 Skill 目录外创建仅当前用户可读的 JSON 凭证文件，字段为 `accessKeyId`、`secretAccessKey` 和可选的 `sessionToken`，执行 `chmod 600` 后通过 `--credentials-file` 指定。凭证文件不得放入 Skill 目录。
5. 将输出目录设置在 Skill 目录外并运行：

   ```bash
   python3 scripts/peer_connection_inventory_audit.py \
     --regions bj,gz \
     --output-dir /absolute/path/to/peer-audit-output
   ```

   使用受限凭证文件时：

   ```bash
   python3 scripts/peer_connection_inventory_audit.py \
     --credentials-file /absolute/path/to/credentials.json \
     --regions bj \
     --output-dir /absolute/path/to/peer-audit-output
   ```

6. 若用户仅提供已有 JSON 快照，使用离线模式：

   ```bash
   python3 scripts/peer_connection_inventory_audit.py \
     --input /absolute/path/to/peer-connections.json \
     --output-dir /absolute/path/to/peer-audit-output
   ```

7. 先检查报告中的“采集覆盖率”。列表查询失败时，该地域没有可审计清单；任一详情查询失败时，只能依据列表字段形成部分结论。
8. 依据 [审计规则](references/audit-rules.md)复核发现。`close` 的 DNS 同步状态本身不属于故障；处于过渡状态也不等于卡死。
9. 向用户返回：巡检地域、列表与详情覆盖率、状态分布、连接拓扑、预付费到期提醒、发现、限制和人工建议。

## 输出要求

- `inventory.json` 保存机器可读快照与分析结果；`report.md` 保存巡检报告。
- 每条发现包含规则编号、严重度、地域、连接 ID、本端/对端 VPC 和证据字段。
- 保留 API 返回的未知字段，避免因文档或服务版本演进丢失证据。
- 不把 VPC ID、账号 ID、标签或网络拓扑发送到未获用户授权的外部服务。
- 没有发现时表述为“在成功查询的范围内未发现规则命中”，不得声称整个账号没有问题。

## 失败处理

- `401`：检查凭证、STS Token 和系统时间；不要要求用户在对话中粘贴密钥。
- `403`：确认绑定 `PEERCONNReadPolicy`；保留成功结果并标记覆盖不完整。
- `404`：核对地域、Endpoint、连接 ID 和 API 版本；不得改用写接口试探。
- `429` 或 `5xx`：允许脚本仅对相同 GET 请求退避重试。
- 某条详情失败时保留列表记录并标记 `_detailStatus=failed`，不得丢弃整条连接。

## 本地验证

以下命令不访问云环境：

```bash
python3 scripts/peer_connection_inventory_audit.py --self-test
python3 scripts/peer_connection_inventory_audit.py \
  --input examples/sample-peer-connections.json \
  --output-dir /tmp/baiducloud-peer-connection-inventory-audit
```

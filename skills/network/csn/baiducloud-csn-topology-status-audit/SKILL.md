---
name: baiducloud-csn-topology-status-audit
description: 只读查询并审计百度智能云云智能网 CSN 实例、详情和已加载网络实例，生成 CSN 到 VPC、专线通道及边缘网络的跨地域/跨账号拓扑、查询覆盖率和状态异常报告。用于用户要求盘点 CSN 资产、梳理网络实例挂载关系、检查加载失败或过渡状态、核对实例计数和确认只读权限时；不得用于创建、修改或删除 CSN，加载或卸载网络实例，配置路由、关联、学习关系、带宽包或地域带宽，也不能证明数据面互通。
---

# 百度智能云 CSN 拓扑与状态巡检

## 只读边界

- 仅向 `https://csn.baidubce.com` 执行 CSN 列表、CSN 详情和网络实例列表 HTTPS `GET` 请求，以及本地文件读取与报告生成。
- 禁止执行 `POST`、`PUT`、`PATCH`、`DELETE`，禁止创建、更新或删除 CSN，加载或卸载网络实例，操作路由表、关联关系、学习关系、路由、带宽包或地域带宽。
- 不因账号拥有更高权限而放宽限制；只输出配置事实、查询覆盖率、规则发现和人工复核建议。
- 不在命令参数、日志、报告或 Skill 包中写入 AK、SK、STS Token、Authorization 头。
- 控制面显示 `active`/`attached` 不等于数据面一定互通；本 Skill 不执行探测流量，也不检查路由表、带宽或安全策略。

## 执行工作流

1. 阅读 [RAM 权限](references/ram-policies.md)，优先使用仅绑定官方 `CSNReadOnlyAccessPolicy` 的 IAM 子用户或受限 STS 凭证。
2. 阅读 [API 与字段说明](references/api-reference.md)。CSN 是全局服务，不需要地域请求参数；地域来自已加载网络实例的 `instanceRegion`。
3. 检查环境变量 `BCE_ACCESS_KEY_ID`、`BCE_SECRET_ACCESS_KEY`；使用 STS 时同时检查 `BCE_SESSION_TOKEN`，不要回显。也可在 Skill 目录外使用权限为 `600` 的 JSON 凭证文件，字段为 `accessKeyId`、`secretAccessKey` 和可选的 `sessionToken`。
4. 将输出目录放在 Skill 目录外，审计账号可见的全部 CSN：

   ```bash
   python3 scripts/csn_topology_status_audit.py \
     --output-dir /absolute/path/to/csn-topology-audit-output
   ```

   使用受限凭证文件时：

   ```bash
   python3 scripts/csn_topology_status_audit.py \
     --credentials-file /absolute/path/to/credentials.json \
     --output-dir /absolute/path/to/csn-topology-audit-output
   ```

5. 只审计指定 CSN 时，使用逗号分隔的精确 ID；未匹配 ID 必须作为覆盖缺口报告：

   ```bash
   python3 scripts/csn_topology_status_audit.py \
     --csn-ids csn-aaa,csn-bbb \
     --output-dir /absolute/path/to/csn-topology-audit-output
   ```

6. 使用已有快照时进入离线模式：

   ```bash
   python3 scripts/csn_topology_status_audit.py \
     --input /absolute/path/to/csn-topology-snapshot.json \
     --output-dir /absolute/path/to/csn-topology-audit-output
   ```

7. 先核对“采集覆盖率”。CSN 列表失败时无法盘点资产；详情或网络实例列表失败时，该 CSN 的状态或拓扑不完整，不能按零实例解释。
8. 依据 [审计规则](references/audit-rules.md)复核发现。`attaching`、`detaching` 是官方过渡状态，缺少持续时间证据时不得判定卡死；未知实例类型可能来自产品演进。
9. 返回：CSN 数量、网络实例数、地域/类型/账号分布、CSN—网络实例拓扑、控制面状态、查询缺口、发现、限制和人工建议。

## 输出要求

- `inventory.json` 保存原始 API 字段、查询覆盖率和分析结果；`report.md` 保存中文巡检报告。
- 每条发现包含规则编号、严重度、CSN ID/名称、挂载 ID、网络实例 ID/类型/地域、事实、解释和证据。
- 详情或网络实例列表失败时保留 CSN 列表摘要，并分别设置 `_detailStatus`、`_instancesStatus`，不得把失败范围写成零资源。
- 未知字段、状态和类型必须保留，不得静默丢弃。
- 没有发现时只能说“在成功查询且规则覆盖的配置范围内未发现命中”，不得声称全网互通或无风险。
- 账号 ID、网络实例标识、标签和拓扑不得发送到未获用户授权的外部服务。

## 失败处理

- `401`：检查凭证、STS Token 和系统时间，不要求用户在对话中粘贴密钥。
- `403`：确认绑定 `CSNReadOnlyAccessPolicy`，保留成功结果并标记覆盖不完整。
- `404`：核对 Endpoint、CSN ID 和 API 版本；不得改用写接口试探。
- `429` 或 `5xx`：只对相同 GET 请求做有限退避重试。
- 单个 CSN 的详情或网络实例列表失败时继续查询其他 CSN，并明确该局部结果未知。

## 本地验证

以下命令不访问云环境：

```bash
python3 scripts/csn_topology_status_audit.py --self-test
python3 scripts/csn_topology_status_audit.py \
  --input examples/sample-csn-topology.json \
  --output-dir /tmp/baiducloud-csn-topology-status-audit
```

# BLB Skill 跨服务联动参考

> 唯一职责：定义 **BLB 之外** 的百度云服务（`eip` / `vpc`）怎么查、查到的数据如何归因到 BLB 问题。
> 用途：BLB 自身只读 API（`blb`）查不到的公网入口、DDoS 记录、安全组规则，通过联动 `eip` / `vpc` 服务补齐，支撑资源查询与巡检。
> 边界：本文只管「跨服务怎么查 + 怎么归因」；输出格式见 `references/output-format.md`，多步串联见 `references/orchestration.md`，成本见 `references/cost.md`，BLB 自身查询/排查流程见 `references/workflows.md`。
> **能力边界（重要）**：BLB **运行时监控指标**（带宽、连接数、QPS、七层 4xx/5xx、响应时间）**当前 BCE CLI 无法查询**，访问日志（BLS）也不在本 Skill 能力范围；这些一律标注「需控制台」，不得编造数值或结论，详见 §3。
> 全部为**只读**联动；不臆造任何数据，查不到就如实说明。命令形态已用当前机器 `bce-cli` 实测核对。

---

## 0. 通用规则

1. 联动服务与 BLB 用同一 profile / region；调用前仍按 `SKILL.md` §4 确认 profile（不展示密钥）与 region。
2. 仅调用 `Describe*` / `Query*` / `List*` / `Get*` 等只读 API，禁止任何写操作。
3. 联动结果只做「归因辅助」，不替代 BLB 自身查询；先查 BLB 自身（`output-format.md` §1.5 拓扑），再按需联动。
4. 仍查不到的能力（运行时监控指标、访问日志明细、云防火墙、风控）明确标注「需控制台」，不编造结论。

---

## 1. 联动服务总览

| 服务 | 用途 | 关键只读 API（实测存在） |
|------|------|--------------------------|
| `eip` | 公网入口绑定关系、EIP 带宽、基础 DDoS 防护与攻击记录 | `eip QueryEipList`、`eip ListBaseDdos`、`eip ListBaseDdosAttackRecord` |
| `vpc` | 子网 / 路由、安全组规则内容 | `vpc QuerySubnetList`、`vpc QuerySpecifiedSubnet`、`vpc GetSecurityGroupDetails`、`vpc QuerySecurityGroupsList` |

---

## 2. 联动查询场景

每个场景固定：**触发现象 → 调用服务/API → 关注字段 → 归因结论**。

### 2.1 VPC 安全组规则查询

- **触发**：巡检/排查中怀疑「安全组未放通监听端口或健康检查端口」。BLB 自身只有绑定/解绑安全组的 API，无法查看规则内容。
- **调用**：

  ```bash
  # 先确认 BLB 绑定的安全组 ID
  "$BCE" blb DescribeBlbSecurityGroups --region <region> --blbId <blbId>
  "$BCE" blb DescribeBlbEnterpriseSecurityGroups --region <region> --blbId <blbId>
  # 再查安全组规则内容
  "$BCE" vpc GetSecurityGroupDetails --region <region> --securityGroupId <sgId>
  "$BCE" vpc QuerySecurityGroupsList --region <region> --vpcId <vpcId>
  ```
- **关注字段**：入站规则是否放通监听端口与健康检查端口、源 IP 段是否过宽。
- **归因**：未放通监听/健康检查端口 → 后端不健康或访问不通的可能原因；规则过宽（如 `0.0.0.0/0` 放通全端口）→ 安全风险。
- **边界**：BLB 无法通过 CLI 修改安全组规则，规则变更需通过 VPC 服务或控制台操作。

### 2.2 公网入口 / 疑似 DDoS

- **触发**：公网访问不通、内网正常；或怀疑被攻击。
- **调用**：

  ```bash
  "$BCE" eip QueryEipList --region <region>                           # 确认 BLB 是否绑定 EIP、EIP 状态/带宽
  "$BCE" eip ListBaseDdos --region <region> --ips <eip>               # 基础 DDoS 防护状态
  "$BCE" eip ListBaseDdosAttackRecord --region <region> --ips <eip>   # 攻击记录
  ```
- **关注字段**：EIP 与 BLB 的绑定关系、EIP 带宽、DDoS 清洗/封堵状态、攻击记录时间。
- **归因**：无 EIP 绑定 → 公网入口缺失；EIP 带宽打满 → 扩带宽（成本见 `cost.md`）；存在清洗/封堵记录 → DDoS 影响，提示用户关注 DDoS 控制台。

### 2.3 实例暂停 / 欠费 / 不可变更

- **触发**：实例状态异常、变更被拒。
- **调用**：先 `blb DescribeBlb` 看 `status`；费用侧无 CLI 直接查询。
- **归因**：状态非 `available` 且疑似费用原因 → 提示费用侧核查（账单/费用中心见 `cost.md`，CLI 无账单明细 API）。

---

## 3. EIP 绑定 BLB 参数说明

编排流程中为公网 BLB/AppBLB 绑定 EIP 时，使用 `eip BindEip` 命令：

```bash
"$BCE" eip BindEip \
  --region <region> \
  --eip <EIP地址或eipId> \
  --instanceType blb \
  --instanceId <blbId> \
  --dry-run
```

| 参数 | 值 | 说明 |
|------|------|------|
| `--eip` | EIP 地址或 eip ID | 要绑定的弹性公网 IP |
| `--instanceType` | `blb` | 绑定目标类型固定为 `blb`（普通型和应用型 BLB 均使用此值） |
| `--instanceId` | blbId | 目标 BLB/AppBLB 实例 ID |
| `--clientToken` | uuid | 幂等 Token（可选） |

**绑定前确认**：
1. 用 `eip QueryEipList` 确认 EIP 状态为 `available`（未绑定）。
2. 用 `DescribeBlb` / `DescribeAppBlb` 确认目标实例 `status=available`。
3. 绑定属于写操作，先 `--dry-run`，通过后请求用户确认再真实执行。

**解绑**：`eip UnbindEip --eip <EIP地址> --region <region> --dry-run`。解绑公网 BLB 的 EIP 将导致公网入口断开，属于删除/解绑类高风险操作，按 `SKILL.md` §11.2 第 7 条强制 dry-run + 二次确认。

---

## 4. CLI 无法覆盖（一律标注「需控制台」）

以下能力 BCE CLI 无对应只读 API，巡检/排查报告中标注「需控制台」，**不得伪造数值或结论**：

- **BLB 运行时监控指标**：带宽、入/出流量、活跃/新建连接数、QPS、七层 4xx/5xx、平均响应时间 —— CLI 不支持，需 BLB 监控控制台。
- **七层访问日志明细** —— 需控制台开启访问日志并在控制台/日志服务查看。
- **HTTPS 证书到期时间** —— 需证书管理控制台。
- **云防火墙（CFW）拦截、业务风控拦截** —— 需对应安全产品控制台。
- **实际账单 / 欠费明细** —— 需费用中心（参考 `references/cost.md`）。

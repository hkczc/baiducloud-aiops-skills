# BLB Skill 成本与费用参考

> 唯一职责：BLB 相关的**成本查询、费用估算与组合规则**（创建费用、公网合计费用、变更差价、闲置浪费）。
> 输出复用 `references/output-format.md` §5 费用摘要模板，本文只补「合计 / 差价 / 浪费」的组合算法，不另立输出格式。
> 全部为只读询价 / 查询；金额**原样取自 CLI，不做单位换算、不臆造**。命令形态已用当前机器 `bce-cli` 实测核对。

---

## 0. 能力边界

| 能力 | CLI 支持 | API |
|------|----------|-----|
| BLB 创建前询价 | 是 | `blb BlbInquiry` |
| EIP（公网带宽）询价 | 是 | `eip EipInquiry`、`eip BandwidthPackageInquiry` |
| BLB 规格变更差价 | 间接（两次询价相减） | `blb BlbInquiry`（变更前后规格各询一次） |
| 已有实例**实际账单明细** | **否** | 当前 `bce` 顶层服务无 billing/账单服务；标注「需控制台/费用中心」 |

> 账单明细、实际扣费、消费趋势 CLI 查不到，统一引导用户到**费用中心 / 账单控制台**，不得编造金额。

---

## 1. 创建费用估算

### 1.1 仅 BLB 实例

按 `references/output-format.md` §5：`blb BlbInquiry` 询价 → §5 模板展示。

### 1.2 公网 BLB（实例 + EIP 合计）

公网 BLB = BLB 实例费用 + EIP（公网带宽）费用，需分别询价后**合计展示**：

```bash
# BLB 实例询价
"$BCE" blb BlbInquiry --region <region> --blbType <normal|application> --performanceLevel <规格> --count 1 \
  --billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}'

# EIP 询价（实测返回 prices.configPrice / prices.netrafficPrice）
"$BCE" eip EipInquiry --region <region> --bandwidthInMbps <带宽> \
  --billing '{"paymentTiming":"Postpaid","billingMethod":"ByTraffic"}'
```

合计展示模板（在 §5 费用摘要基础上增加合计区块）：

```markdown
### 公网负载均衡费用预估（实例 + EIP）

**BLB 实例**（按 output-format.md §5 表渲染）
**EIP 公网带宽**
| 计费项 | 单位 | 价格 |
|--------|------|------|
| configPrice | minute | <值> |
| netrafficPrice | GB | <值> |

> 合计说明：BLB 与 EIP 为独立计费项，分别按各自计费模式扣费；以上为单价，最终费用按实际用量计算，金额原样未换算。
数据来源：BlbInquiry + EipInquiry（region: <region>）
```

---

## 2. 规格变更差价预估

`ResizeBlb` / 计费变更前，对**变更前规格**和**变更后规格**各询价一次，展示差异：

```bash
"$BCE" blb BlbInquiry --region <region> --blbType <type> --performanceLevel <当前规格> --count 1 --billing '<同计费模式>'
"$BCE" blb BlbInquiry --region <region> --blbType <type> --performanceLevel <目标规格> --count 1 --billing '<同计费模式>'
```

展示：列出两套询价的同名计费项单价对比（变更前 / 变更后），并提示「差价为单价差异，实际差额按用量计算」。不做减法换算成总额，只并列单价。

---

## 3. 闲置资源费用浪费提示

复用 `references/inspection.md` 的闲置判定（无监听器 + 无后端）：

1. 巡检识别疑似闲置实例（只读，见 inspection.md）。
2. 对闲置实例按其当前 `paymentTiming`/`billingMethod` 用 `BlbInquiry` 取单价，提示「该实例疑似闲置但仍按 <计费模式> 持续计费」。
3. **不计算累计浪费金额**（CLI 无实际用量/时长），只做单价提示 + 引导用户评估是否释放（释放仍禁止 Agent 代执行，见 `SKILL.md` §11.1）。

---

## 4. 输出与安全规则

1. 费用类输出一律基于 `references/output-format.md` §5 模板 + 本文合计/差价区块。
2. 金额原样、不换算、不加货币符号（除非 CLI 已带）；缺失填 `-`。
3. 实际账单 / 扣费 / 趋势 → 标注「需费用中心/账单控制台」，禁止编造。
4. 询价是创建付费资源的前置（见 `SKILL.md` §7.5）；询价不等于授权创建，仍需用户明确确认。

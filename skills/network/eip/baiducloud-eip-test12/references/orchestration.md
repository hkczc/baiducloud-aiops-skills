# BLB Skill 智能工作流编排参考

> 唯一职责：把用户的**一句业务目标**拆解为跨能力的有序步骤（问答 / 查询 / 诊断 / 巡检 / 成本 / 操作），由 AI 统一编排并驱动执行，达成「用户不在文档/控制台/API/账单间来回切换」。
> 本文只负责「怎么把多步串起来」；每一步的字段/命令/输出格式仍引用对应 references，不在此重复定义：
> - 资源查询 / 实例拓扑 / 输出模板 → `references/output-format.md`
> - BLB 自身复合操作流程（创建/HTTPS/扩缩/复制） → `references/workflows.md`
> - 跨服务联动（公网/安全组） → `references/cross-service.md`
> - 巡检项 → `references/inspection.md`
> - 成本估算 → `references/cost.md`
> - 官方文档问答 → `references/doc-links.md`
> - API 参数 → `references/blb-api-reference.md` / `references/appblb-api-reference.md`
> - 命令失败恢复 → `references/troubleshooting.md`

---

## 1. 何时进入编排

用户给出的是**目标 / 多步意图**而非单个 API 动作时进入本文，例如：
- 「给这个网站配一套带 HTTPS 和健康检查的公网负载均衡」
- 「排查这个公网 BLB 为什么访问慢」
- 「帮我评估并整理这个 region 下所有 BLB 的风险和费用」

单步意图（如「查实例列表」「加一个后端」）直接走 `SKILL.md` §7 映射，不需要编排。

---

## 2. 编排五步法

所有编排遵循固定五步，**写操作的安全规则（dry-run、询价、二次确认、高风险阻断）全程不变**：

1. **理解目标**：复述用户目标，确认实例类型（普通型/AppBLB）、region、是否公网。歧义先问，不猜。
2. **现状探查（只读）**：按目标拉取现状——实例拓扑（`output-format.md` §1.5）、相关资源（VPC/子网、EIP）、必要时巡检（`inspection.md`）。
3. **生成步骤计划并展示**：把目标拆成有序步骤，标注每步的能力归属、是否写操作、依赖关系、预估费用（`cost.md`），**先展示给用户确认整体计划**，再逐步执行。
4. **逐步执行**：按顺序执行；每个写操作单独走 dry-run → 展示 → 用户确认 → 真实执行（遵守 `SKILL.md` §7.5/§11）；付费创建前先询价（`cost.md`）。任一步失败按 `troubleshooting.md` 处理并暂停，向用户汇报后再决定是否继续。
5. **验证与交付**：用只读查询验证结果——创建后等待就绪（`workflows.md` §14 waiter）、健康检查、最终输出实例拓扑总览（`output-format.md` §1.5）确认目标达成。

> 编排不绕过任何安全约束：实例释放仍禁止；删监听/服务器组的在用后端硬阻断仍生效；高风险仍二次确认。

---

## 3. 端到端编排范例

### 3.1 「给网站配一套带 HTTPS + 健康检查的公网负载均衡」

| 步 | 能力 | 动作 | 写操作 | 参考 |
|----|------|------|--------|------|
| 1 | 理解 | 确认普通型/AppBLB、region、后端 BCC、域名证书 certId | 否 | — |
| 2 | 查询 | 查 VPC/子网、确认后端 BCC、确认 certId 已存在 | 否 | SKILL.md §6 |
| 3 | 成本 | BLB 询价 + EIP 询价，合计费用预估并展示 | 否 | cost.md |
| 4 | 操作 | 创建 BLB 实例（询价确认后） | 是 | workflows.md §1 |
| 5 | 操作 | 绑定 EIP（公网入口） | 是 | cross-service.md §3 eip BindEip |
| 6 | 操作 | 创建 HTTPS 监听器（挂 certId、加密策略） | 是 | workflows.md §4/§13 |
| 7 | 操作 | 添加后端 / 配置健康检查 | 是 | workflows.md §1 |
| 8 | 验证 | waiter 等就绪 → 查健康 → 输出实例拓扑总览 | 否 | output-format.md §1.5 / workflows.md §14 |

### 3.2 「排查这个公网 BLB 为什么访问慢」

| 步 | 能力 | 动作 | 参考 |
|----|------|------|------|
| 1 | 查询 | 输出实例拓扑总览，确认监听/后端/安全组配置完整 | output-format.md §1.5 |
| 2 | 查询 | 查后端健康，排除后端配置/健康异常 | workflows.md §10 |
| 3 | 联动 | vpc 查安全组规则是否放通监听/健康检查端口 | cross-service.md §2.1 |
| 4 | 联动 | eip 查公网带宽是否打满 / DDoS 记录 | cross-service.md §2.2 |
| 5 | 交付 | 汇总 CLI 可查到的归因；**带宽/连接数/QPS/七层状态码等运行时指标与访问日志明细 CLI 不支持，标注「需控制台」**，不编造结论 | output-format.md §6 / cross-service.md §4 |

### 3.3 「评估这个 region 下所有 BLB 的风险和费用」

| 步 | 能力 | 动作 | 参考 |
|----|------|------|------|
| 1 | 查询 | DescribeBlbs + DescribeAppBlbs 取全量实例 | output-format.md §1.3 |
| 2 | 巡检 | 逐实例按巡检清单（CLI 可巡检 + 可联动）评估 | inspection.md |
| 3 | 成本 | 闲置实例费用浪费提示 + 规格费用 | cost.md |
| 4 | 交付 | 输出巡检报告（风险分级）+ 成本摘要，给优化建议 | output-format.md §6 |

### 3.4 「证书即将过期，帮我更换 BLB 上的证书」

| 步 | 能力 | 动作 | 写操作 | 参考 |
|----|------|------|--------|------|
| 1 | 理解 | 确认 blbId、region、监听端口、旧 certId、新 certId | 否 | — |
| 2 | 查询 | 查询 HTTPS/SSL 监听器当前证书配置 | 否 | output-format.md §1.5 |
| 3 | 确认 | 确认新 certId 存在（需用户提前在证书服务/控制台准备好，CLI 无证书管理服务） | 否 | workflows.md §13 |
| 4 | 操作 | UpdateBlbHttpsListener / UpdateAppBlbHttpsListener 更新 certIds | 是 | workflows.md §13 |
| 5 | 验证 | 查询监听器确认 certIds 已更新 | 否 | output-format.md §1.5 |

> **限制**：CLI 无证书管理服务（无上传/续期/申请 API），`--certIds` 只能引用已存在的证书 ID。如用户未提供新 certId，引导用户先到证书服务/控制台获取。

### 3.5 「业务扩容，把 BLB 从 small1 升级到 large1」

| 步 | 能力 | 动作 | 写操作 | 参考 |
|----|------|------|--------|------|
| 1 | 理解 | 确认 blbId、region、当前规格、目标规格 | 否 | — |
| 2 | 查询 | DescribeBlb / DescribeAppBlb 确认当前 performanceLevel 和计费 | 否 | output-format.md §1.1 |
| 3 | 成本 | BlbInquiry 分别对当前规格和目标规格询价，展示差价 | 否 | workflows.md §16 / cost.md |
| 4 | 操作 | ResizeBlb dry-run → 确认 → 真实执行 | 是 | workflows.md §16 |
| 5 | 验证 | 查询实例确认 performanceLevel 已变更 | 否 | output-format.md §1.1 |

### 3.6 「把这个 BLB 从按规格计费转为按量计费」

| 步 | 能力 | 动作 | 写操作 | 参考 |
|----|------|------|--------|------|
| 1 | 理解 | 确认 blbId、region、当前计费方式 | 否 | — |
| 2 | 查询 | DescribeBlb / DescribeAppBlb 确认 paymentTiming / billingMethod | 否 | output-format.md §1.1 |
| 3 | 确认 | 说明计费转换影响（费用结构变化、不可自动回退） | 否 | workflows.md §17 |
| 4 | 操作 | 按转换方向执行 BillingChangePreToPostBlb / BillingChangePostToPreBlb | 是 | workflows.md §17 |
| 5 | 验证 | 查询实例确认计费方式已变更 | 否 | output-format.md §1.1 |

---

## 4. 编排规则

1. **先计划后执行**：多步目标必须先展示完整步骤计划并获用户确认，不得边想边改、直接连续执行写操作。
2. **只读先行**：探查、诊断、巡检、成本预估均为只读，可连续执行；写操作必须逐个确认。
3. **能力不重复定义**：每步只引用对应 reference，本文不复制其字段/命令细节。
4. **失败即暂停**：任一步失败按 `troubleshooting.md` 汇报，暂停编排，由用户决定续行/调整/终止。
5. **安全约束最高优先**：编排不得绕过实例释放禁止、在用后端硬阻断、付费询价、高风险二次确认等规则。

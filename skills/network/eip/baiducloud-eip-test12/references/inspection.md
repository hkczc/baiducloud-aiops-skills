# BLB Skill 巡检清单参考

> 本文定义 BLB/AppBLB **可巡检哪些项**、每项的检查方法、判定规则、风险等级与修复指针。
> 触发：用户说「巡检」「体检」「检查实例有没有问题」「找出风险」「闲置/到期/安全风险排查」。
> 输出：一律走 `references/output-format.md` §6「巡检报告模板」（风险汇总 + 巡检明细，风险三级：高/中/低）。
> 能力边界：分三类——**CLI 可巡检**（`blb`/`vpc` 只读 API 直接判定，§2）、**可联动巡检**（联动 `eip`/`vpc`，§3，详见 `references/cross-service.md`）、**需控制台**（联动也查不到，必须标注来源，§4）。
> 注：BLB 运行时监控指标（带宽/连接数/QPS/七层状态码）与访问日志明细 **CLI 不支持**，统一归入 §4「需控制台」，不得编造数值。

---

## 1. 巡检执行前置

1. 按 `SKILL.md` §3 解析 `$BCE` 并 `version` 验证。
2. `configure list` 确认 profile（不展示密钥），确认 region。
3. 巡检为**纯只读**：只允许 `Describe*` / `Query*` / `BlbInquiry`，禁止任何写操作；发现风险只输出建议命令，不自动修复。
4. 先 `DescribeBlbs` + `DescribeAppBlbs` 取实例清单，再逐实例逐项巡检。

---

## 1.5 生产实例判定标准

巡检中部分项目（如"修改保护未开"）仅对**生产实例**判定为风险。CLI 无法自动识别实例是否用于生产，使用以下规则综合判定：

| 判定维度 | 生产信号 | 判定方式 |
|----------|----------|----------|
| 标签 | 含 `env=prod` / `env=production` 或类似语义标签 | `DescribeBlb` / `DescribeAppBlb` 返回的 `tags` |
| 实例状态 | 有活跃业务（已配置监听器 + 后端 + 证书） | CLI 只读查询综合判断 |
| 计费方式 | 预付费（Prepaid）或按规格后付费（BySpec）通常为长期资源 | `DescribeBlb` / `DescribeAppBlb` 返回的 `paymentTiming` / `billingMethod` |
| 修改保护 | `allowModify=false` 表示用户已主动开启保护，视为生产 | `DescribeBlb` / `DescribeAppBlb` 返回的 `allowModify` |

**判定规则**：满足以下任一条件即视为生产实例：
1. 标签中含 `env=prod` / `env=production` 或 `tier=prod` 等语义标识。
2. 已配置监听器 + 后端 + 修改保护已开启（`allowModify=false`）。
3. 预付费实例且已配置监听器和后端。

不确定时默认为生产实例，风险判定从宽。

---

## 2. CLI 可巡检项

每项：判定规则 → 风险等级 → 数据来源 → 修复指针（指针指向 `workflows.md` / `*-api-reference.md`，不在巡检中直接执行）。

| 巡检项 | 判定规则（异常条件） | 风险 | 数据来源(CLI) | 修复指针 |
|--------|----------------------|------|---------------|----------|
| 未配置监听器 | `DescribeBlbListener` / `DescribeAppBlb*Listener` 返回 `listenerList: null` 或空 | 中 | DescribeBlbListener / DescribeAppBlb*Listener | workflows.md §1/§2 创建监听器 |
| 未配置后端 | 普通型 `DescribeBlbServers` 为空；AppBLB 所有服务器组 `DescribeAppBlbServerGroupRs` 无 RS | 高 | DescribeBlbServers / DescribeAppBlbServerGroupRs | workflows.md §1/§2 添加后端 |
| 健康检查关闭 | AppBLB 服务器组端口 `enableHealthCheck=false` | 中 | DescribeAppBlbServerGroup(portList[].enableHealthCheck) | appblb-api-reference UpdateAppBlbServerGroupPort |
| 后端健康异常 | 普通型 `status!=Alive`；AppBLB `portList[].status!=available` | 高 | DescribeBlbServerHealth / DescribeAppBlbServerGroupRs | workflows.md §10 健康异常诊断 |
| 全部后端异常 | 某监听器/服务器组下所有后端均异常 | 高 | 同上 | 优先查安全组/ACL/健康检查端口 |
| 监听器后端端口/健康检查不一致 | 健康检查端口/路径与后端实际服务不符（结合 listener 配置人工判断） | 中 | DescribeBlb*Listener / DescribeAppBlbServerGroup | workflows.md §10 |
| 未绑定安全组（公网/高危场景） | `DescribeBlbSecurityGroups` 与 `DescribeBlbEnterpriseSecurityGroups` 均为空 | 中 | DescribeBlbSecurityGroups / DescribeBlbEnterpriseSecurityGroups | blb-api-reference §9 |
| 修改保护未开（生产实例） | `allowModify=true` 且为生产实例 | 低 | DescribeBlb(allowModify) | blb-api-reference UpdateBlbModifyProtection |
| 疑似闲置仍计费 | 无监听器 **且** 无后端（复用 `SKILL.md` §11.1 闲置评估逻辑） | 中 | DescribeBlbListener + DescribeBlbServers / AppBLB 等价查询 | SKILL.md §11.1（只评估，不释放） |
| AppBLB 策略目标组为空/失效 | `DescribeAppBlbPolicy` 引用的 `sgId`/`ipGroupId` 下无可用后端 | 高 | DescribeAppBlbPolicy + DescribeAppBlbServerGroupRs | workflows.md §8 |
| HTTPS 监听器缺证书 | HTTPS/SSL 监听器 `certIds` 为空 | 高 | DescribeBlbHttpsListener / DescribeAppBlbHttpsListener | workflows.md §4/§13 |

---

## 3. 可联动巡检项（联动 eip/vpc 只读查询）

以下项 BLB 自身 API 查不到，但可通过**跨服务联动**（公网/安全组）巡检，查询方法与归因见 `references/cross-service.md`。数据来源列标注对应服务 API。

| 巡检项 | 判定方向 | 风险 | 数据来源(联动) | 参考 |
|--------|----------|------|----------------|------|
| 安全组规则过宽 | 入站规则放通过宽（如 0.0.0.0/0 全端口） | 中 | vpc GetSecurityGroupDetails | cross-service.md §2.1 |
| 安全组未放通监听/健康检查端口 | 入站规则缺监听端口或健康检查端口 | 高 | vpc GetSecurityGroupDetails | cross-service.md §2.1 |
| 公网入口缺失/带宽打满 | EIP 未绑定或带宽满 | 中 | eip QueryEipList | cross-service.md §2.2 |
| DDoS 攻击影响 | 存在清洗/封堵/攻击记录 | 中 | eip ListBaseDdos(AttackRecord) | cross-service.md §2.2 |

> 联动巡检前提：用户已开通对应服务；未开通时该项降级为「需控制台」。

---

## 4. 需控制台项（联动也查不到，必须标注来源）

以下项即使联动 eip/vpc 也无法获取，巡检报告「数据来源」列固定标注 `需控制台`，**不得凭空给出结论或数值**。

| 巡检项 | 说明 | 风险 | 用户自查路径 |
|--------|------|------|--------------|
| 带宽限速 / 丢包 | 带宽指标峰值触及上限（CLI 无监控指标 API） | 高 | BLB 监控控制台 |
| 连接数风险 | 并发/新建连接数接近上限、有丢弃 | 高 | BLB 监控控制台 |
| 容量瓶颈 | 规格容量接近上限 | 中 | BLB 监控控制台 |
| 七层 4xx/5xx/超时 | 状态码异常率、响应耗时 | 中 | BLB 监控控制台 / 访问日志 |
| HTTPS 证书到期时间 | 证书剩余有效期、即将过期/已过期 | 高 | 证书管理控制台 |
| 云防火墙 / 风控影响 | 安全产品拦截导致访问异常 | 中 | 云防火墙 / 风控控制台 |
| 费用异常/欠费 | 实例欠费、不可变更 | 高 | 费用中心 / 账单（参考 `references/cost.md`） |
| 七层访问明细 | 访问日志未在控制台开启或 CLI 不可查 | 中 | 控制台开启/查看访问日志 |

---

## 5. 巡检输出规则

1. 严格按 `output-format.md` §6 模板：风险汇总表 + 巡检明细表。
2. 每条明细必须含：实例、巡检项、结果（异常/正常）、风险等级、数据来源、建议指针。
3. CLI 可巡检项给出具体数据；可联动项按 `cross-service.md`（eip/vpc）查询后给数据；需控制台项标注来源并提示用户自查，禁止编造数值或结论。
4. 巡检只读：所有修复仅作为建议（指向 references），需用户单独发起、按高风险流程二次确认后才可执行。
5. 同一会话重复巡检必须重新查询，不沿用历史缓存。

# BLB Skill 固定输出格式参考

> 唯一职责：查询 / 转发链路 / 后端健康 / 费用 / 巡检 五类结果的**唯一权威输出规范**（字段名、顺序、单位、缺失处理、Markdown 模板）。
> 不负责：怎么查（API 参数见 `*-api-reference.md`）、多步流程（见 `workflows.md`）、巡检判定规则（见 `inspection.md`）；本文只管"查到后怎么呈现"。
> 目的：消除不同模型对同一数据的自由发挥。用法：Agent 先把 CLI 原始响应映射到本文的 **内部 JSON schema**（约束字段名/顺序/单位），再按对应 **Markdown 模板** 渲染给用户。schema 只用于约束字段，不要求把 JSON 展示给用户；对外一律输出固定 Markdown。
> 字段名以本文为准；本文字段已用 `DescribeBlb` / `DescribeBlbListener` / `DescribeBlbServerHealth` / `DescribeAppBlb*` / `BlbInquiry` 的真实返回校准。静态字段与当前机器实时返回不一致时，以实时返回为准并在输出中说明差异。

---

## 0. 通用渲染规则（所有模板必须遵守）

1. **字段顺序固定**：严格按本文 schema 列出的顺序渲染，不得重排、不得增删字段列。
2. **缺失值填 `-`**：CLI 返回为 `null` / `""` / 不存在的字段，统一渲染为 `-`，不要臆造或推断。
3. **金额原样**：价格、费用字符串原样输出，**不做单位换算、不做四则运算、不加货币符号**（除非 CLI 已带）。
4. **时间原样**：`createTime` 等时间字段原样输出 CLI 返回的 UTC 字符串，不本地化。
5. **类型标注**：实例 `type` 固定映射为 `normal`(普通型) / `application`(应用型 AppBLB) / `ipv6`(普通型 IPv6) / `ipv6Application`(应用型 IPv6)，并在中文括注。
6. **脱敏强制**：任何输出不得出现 AK/SK/token/Authorization/签名；profile 只展示名称。
7. **来源标注**：每个表格/区块下用一行小字标注数据来源 CLI API（如 `数据来源：DescribeBlb`），便于核对。
8. **空结果显式说明**：列表为空（如 `listenerList: null`）必须显式输出「未配置 X」，不得省略。

---

## 1. 实例摘要（查询 BLB/AppBLB 实例）

> **查询粒度分流（先判断用户意图明确度）**：
> - **模糊查询**（如「帮我查询我的 BLB 实例资源」「看看我有哪些负载均衡」，未指定具体实例）：先用 §1.3 列表模板给**实例总览**（`DescribeBlbs` + `DescribeAppBlbs`），输出后**附一句反问**：「需要查看某个实例的详细配置/转发链路拓扑吗？」——不要一上来就对每个实例拉全量拓扑。
> - **明确单实例查询**（给了 blbId，或说「这个实例的全部信息/配置全貌/拓扑」）：一定走 §1.5 实例拓扑总览（默认聚合视图，拉全）。
> - 只看实例自身属性用 §1.1~§1.3。

**数据来源**：`DescribeBlb` / `DescribeAppBlb`（详情）；列表场景用 `DescribeBlbs` / `DescribeAppBlbs`。

### 1.1 内部 schema（字段顺序固定）

```json
{
  "blbId": "string",
  "name": "string",
  "type": "normal|application|ipv6|ipv6Application",
  "status": "string",
  "address": "string",
  "ipv6": "string",
  "vpcId": "string",
  "vpcName": "string",
  "subnetId": "string",
  "cidr": "string",
  "paymentTiming": "string",
  "billingMethod": "string",
  "allowDelete": "bool",
  "allowModify": "bool",
  "modificationProtectionReason": "string",
  "createTime": "string(UTC)",
  "tags": "list|-"
}
```

### 1.2 对外 Markdown 模板（详情）

```markdown
### 实例摘要：<name> (<blbId>)

| 字段 | 值 |
|------|----|
| 实例 ID | <blbId> |
| 名称 | <name> |
| 类型 | <type>（普通型/应用型/IPv6...） |
| 状态 | <status> |
| 内网地址 | <address> |
| IPv6 地址 | <ipv6 或 -> |
| VPC | <vpcName> (<vpcId>) |
| 子网 | <subnetId> |
| 网段 CIDR | <cidr> |
| 计费方式 | <paymentTiming> / <billingMethod> |
| 允许删除 | <allowDelete> |
| 允许修改 | <allowModify> |
| 修改保护原因 | <modificationProtectionReason 或 -> |
| 创建时间(UTC) | <createTime> |
| 标签 | <tags 或 -> |

数据来源：DescribeBlb（profile: <name>, region: <region>）
```

### 1.3 对外 Markdown 模板（列表，多实例）

> 列表 API（`DescribeBlbs`/`DescribeAppBlbs`）不返回 `cidr`/`createTime`/`listener`，缺失列填 `-` 或省略详情字段。

```markdown
### BLB 实例列表（region: <region>，共 N 个）

| 实例 ID | 名称 | 类型 | 状态 | 内网地址 | VPC | 计费 |
|---------|------|------|------|----------|-----|------|
| <blbId> | <name> | <type> | <status> | <address> | <vpcId> | <paymentTiming>/<billingMethod> |

数据来源：DescribeBlbs / DescribeAppBlbs
```

---

## 1.5 实例拓扑总览（默认聚合视图）

> 用户「查实例」「看这个 BLB 的全部信息」「实例配置全貌」时的**默认视图**：一次查询自动聚合实例属性 + 监听器 + 服务器组/IP组 + 后端 + 健康 + 安全组，让用户查一次实例拿到所有相关信息。
> 与 §3 转发链路的区别：本节是**全量资源清单**（查什么都给），§3 只渲染「请求转发路径」；二者并存，本节区块 A 直接引用 §3 渲染链路（转发链路置于拓扑最前，便于用户先看清流量走向）。
> 默认行为：**拉全**。除非用户显式只要某一项，否则按下方采集顺序把相关只读查询全部执行后聚合输出。所有查询均为只读。

### 1.5.1 聚合数据采集顺序（纯只读）

**普通型 / 普通型 IPv6 BLB：**

```bash
"$BCE" blb DescribeBlb --region <region> --blbId <blbId>                       # 实例属性（listener[] 含监听端口与健康概况）
"$BCE" blb DescribeBlbListener --region <region> --blbId <blbId> --pager       # 监听器详情
"$BCE" blb DescribeBlbServers --region <region> --blbId <blbId> --pager        # 后端服务器
"$BCE" blb DescribeBlbServerHealth --region <region> --blbId <blbId> --listenerPort <port> --pager   # 逐监听端口查健康
"$BCE" blb DescribeBlbSecurityGroups --region <region> --blbId <blbId>             # 普通安全组
"$BCE" blb DescribeBlbEnterpriseSecurityGroups --region <region> --blbId <blbId>   # 企业安全组
```

**AppBLB / AppBLB IPv6：**

```bash
"$BCE" blb DescribeAppBlb --region <region> --blbId <blbId>                            # 实例属性
"$BCE" blb DescribeAppBlbListener --region <region> --blbId <blbId> --pager               # ① 先用总览 API 拉全部监听器端口/协议列表
# 按返回的 listenerPort + type 逐个查协议级详情
"$BCE" blb DescribeAppBlbHttpListener --region <region> --blbId <blbId> --listenerPort <port> --pager   # HTTP 详情
# ... Tcp/Udp/Https/Ssl 同理
"$BCE" blb DescribeAppBlbServerGroup --region <region> --blbId <blbId> --pager         # 服务器组 + portList[] 健康检查
"$BCE" blb DescribeAppBlbServerGroupRs --region <region> --blbId <blbId> --sgId <sgId> --pager   # 逐组后端 RS（backendServerList[].portList[].status）
"$BCE" blb DescribeAppBlbIpGroup --region <region> --blbId <blbId>                     # IP 组 + backendPolicyList[]
"$BCE" blb DescribeAppBlbPolicy --region <region> --blbId <blbId> --port <port> --type <type>    # 逐监听端口查策略
"$BCE" blb DescribeBlbSecurityGroups --region <region> --blbId <blbId>             # 安全组（AppBLB 复用同名 API，无独立 DescribeAppBlbSecurityGroups）
"$BCE" blb DescribeBlbEnterpriseSecurityGroups --region <region> --blbId <blbId>   # 企业安全组（同上）
```

> **AppBLB 采集优化**：优先使用 `DescribeAppBlbListener`（总览 API）获取全部监听器端口和协议列表，再按需逐个查协议级详情（`DescribeAppBlbHttpListener` 等），避免盲查。总览 API 返回的字段较少（无完整参数），仅用于确定"查哪些端口和协议"。

### 1.5.2 聚合 JSON schema

> 字段名复用 §1（实例）、§2（监听器）、§4（后端健康）、§3（链路）已校准的 schema，本节只定义聚合的顶层结构，子对象字段以对应小节为准。

```json
{
  "instance": { "...见 §1.1 实例 schema..." },
  "listeners": [ { "...见 §2.1/§2.2 监听器 schema..." } ],
  "serverGroups": [
    {
      "id": "string", "name": "string",
      "portList": [ {"port": "int", "type": "string", "enableHealthCheck": "bool", "status": "string"} ],
      "backendServerList": [ {"instanceId": "string", "weight": "int", "portList": [{"port": "int", "status": "string"}]} ]
    }
  ],
  "ipGroups": [
    { "id": "string", "name": "string", "backendPolicyList": [ {"id": "string", "type": "string", "enableHealthCheck": "bool"} ] }
  ],
  "backends": [ { "...普通型 §4.1 / AppBLB §4.2 后端健康..." } ],
  "policies": [ {"id": "string", "frontendPort": "int", "type": "string", "priority": "int", "groupType": "ServerGroup|Ip", "ruleList": []} ],
  "securityGroups": { "normal": ["string"], "enterprise": ["string"] }
}
```

> 普通型有 `backends`（按监听）但无 `serverGroups`/`ipGroups`/`policies`；AppBLB 用 `serverGroups`/`ipGroups`/`policies`，后端健康在服务器组 RS 的 `portList[].status`。按实例类型只保留适用区块。

### 1.5.3 对外 Markdown 拓扑模板（区块顺序固定）

```markdown
## 实例拓扑：<name> (<blbId>) [<普通型|应用型 AppBLB|...>]

### A. 转发链路
（直接引用 §3 转发链路模板渲染：普通型用 §3.1，AppBLB 用 §3.2；本区块不重复字段定义）

### B. 实例摘要
（按 §1.2 实例摘要表渲染）
数据来源：DescribeBlb / DescribeAppBlb

### C. 监听器
（按 §2.3 监听摘要表渲染；无监听器输出「未配置任何监听器」）
数据来源：DescribeBlbListener / DescribeAppBlb*Listener

### D. 后端与健康
- 普通型：按监听端口分组列后端服务器（instanceId/IP/权重/健康状态，复用 §4.1/§4.3）
- AppBLB：按服务器组列（sgId/name → 端口健康检查 → RS instanceId/权重/portList[].status），再列 IP 组（id/name → backendPolicyList 协议端口/健康检查 → 成员）
- 无后端：输出「未挂载后端服务器」
数据来源：DescribeBlbServers + DescribeBlbServerHealth / DescribeAppBlbServerGroup(Rs) + DescribeAppBlbIpGroup

### E. 安全组绑定
| 类型 | 已绑定 |
|------|--------|
| 普通安全组 | <id 列表 或 未绑定> |
| 企业安全组 | <id 列表 或 未绑定> |
数据来源：DescribeBlbSecurityGroups + DescribeBlbEnterpriseSecurityGroups
```

### 1.5.4 规则

1. **默认拉全**：聚合执行 §1.5.1 全部只读查询；用户显式只要某项时才裁剪。
2. **空结果显式说明**：子查询为空（`listenerList: null`、`backendServerList: null`/`[]`、`blbSecurityGroups: []`、`enterpriseSecurityGroups: []`、`appIpGroupList` 空）必须显式输出「未配置 / 未挂载 / 未绑定」，不得省略对应区块。
3. **局部失败不中断**：任一子查询失败时，仅在对应区块标注「该项查询失败：<错误摘要>」，其余区块照常输出，并在末尾汇总失败项。
4. **类型裁剪**：普通型不渲染服务器组/IP组/策略区块；AppBLB 不渲染普通型 backendPort 列。
5. 沿用 §0 通用规则：字段顺序固定、缺失填 `-`、金额/时间原样、强制脱敏、每区块标注数据来源。
6. 同一会话重复查询同实例必须重新拉取，不沿用历史缓存。

---

## 2. 监听摘要

**数据来源**：普通型 `DescribeBlbListener` / `DescribeBlb{Tcp,Udp,Http,Https,Ssl}Listener`；AppBLB `DescribeAppBlb{...}Listener`。

### 2.1 普通型监听器 schema（字段顺序固定）

```json
{
  "listenerPort": "int",
  "listenerType": "TCP|UDP|HTTP|HTTPS|SSL",
  "backendPort": "int",
  "scheduler": "RoundRobin|LeastConnection|...",
  "healthCheckType": "string",
  "healthCheckInterval": "int(秒)",
  "healthCheckTimeoutInSecond": "int(秒)",
  "healthyThreshold": "int",
  "unhealthyThreshold": "int"
}
```

### 2.2 AppBLB 监听器 schema（无 backendPort）

```json
{
  "listenerPort": "int",
  "listenerType": "TCP|UDP|HTTP|HTTPS|SSL",
  "scheduler": "string",
  "keepSession": "bool",
  "keepSessionType": "string",
  "keepSessionTimeout": "int(秒)",
  "xForwardedFor": "bool",
  "serverTimeout": "int(秒)"
}
```

### 2.3 对外 Markdown 模板

```markdown
### 监听摘要：<blbId>

| 监听端口 | 协议 | 后端端口 | 调度算法 | 健康检查 | 间隔/超时(s) | 健康/不健康阈值 |
|----------|------|----------|----------|----------|--------------|-----------------|
| <listenerPort> | <listenerType> | <backendPort 或 -> | <scheduler> | <healthCheckType 或 -> | <interval>/<timeout> | <healthy>/<unhealthy> |

数据来源：DescribeBlbListener / DescribeAppBlb*Listener
```

> AppBLB 监听器没有 `backendPort`（后端端口在服务器组端口上），该列填 `-`，并在表下补一行「AppBLB 后端端口见服务器组端口」。

---

## 3. 转发链路（实例转发链路输出）

把「请求从监听器到后端」的完整路径渲染成固定结构，**普通型与 AppBLB 模板不同**，不得混用。

### 3.1 普通型 BLB 链路

链路模型：`监听器(port/proto) → 后端服务器(instanceId/weight/health)`

**数据来源**：`DescribeBlbListener`（监听端口）+ `DescribeBlbServers`（后端）+ `DescribeBlbServerHealth`（健康）。

```markdown
### 转发链路：<name> (<blbId>) [普通型]

监听器 80/TCP  (scheduler: RoundRobin, backendPort: 8080)
└─ 后端服务器
   ├─ i-xxxx  weight=100  health=<healthy|unhealthy|-> 
   └─ i-yyyy  weight=50   health=<...>

监听器 443/HTTPS (...)
└─ 后端服务器
   └─ ...

数据来源：DescribeBlbListener + DescribeBlbServers + DescribeBlbServerHealth
```

- 无监听器：输出「该实例未配置任何监听器」。
- 监听器存在但无后端：在该监听器下输出「未挂载后端服务器」。

### 3.2 AppBLB 链路

链路模型（4 层）：`监听器(port) → Policy(Host/Path 规则, priority) → ServerGroup(sgId) / IpGroup → 后端 RS(portList[].status)`

**数据来源**：`DescribeAppBlb*Listener`（监听端口）+ `DescribeAppBlbPolicy --port <port> --type <type>`（策略）+ `DescribeAppBlbServerGroup` / `DescribeAppBlbServerGroupRs --sgId`（服务器组与 RS）+ IP 组相关查询。

```markdown
### 转发链路：<name> (<blbId>) [应用型 AppBLB]

监听器 80/HTTP  (scheduler: LeastConnection)
└─ Policy <policyId>  priority=100  规则: <key>=<value> (如 uri=/api/*)
   └─ 目标: <groupType: ServerGroup|Ip>
      ├─ ServerGroup <sgId> (<name>)
      │  └─ 端口 80/TCP  health=<status>
      │     └─ RS: i-xxxx weight=100 portStatus=<available|...>
      └─ IpGroup <ipGroupId> (<name>)
         └─ 成员: <ip>:<port> weight=<w>

数据来源：DescribeAppBlb*Listener + DescribeAppBlbPolicy + DescribeAppBlbServerGroup(Rs) + DescribeAppBlbIpGroup*
```

- 监听器无策略：输出「监听器使用默认动作，无 Host/Path 策略」并尽量展示默认服务器组。
- `groupType=Ip` 走 IpGroup 分支，`groupType` 为服务器组走 ServerGroup 分支。

---

## 4. 后端健康概览

### 4.1 普通型 schema

**数据来源**：`DescribeBlbServerHealth --blbId <id> --listenerPort <port>`。

```json
{
  "listenerPort": "int",
  "backendServerList": [
    {"instanceId": "string", "ip": "string", "weight": "int", "status": "Alive|Dead|..."}
  ]
}
```

### 4.2 AppBLB schema

**数据来源**：`DescribeAppBlbServerGroupRs --blbId <id> --sgId <sgId>`，返回 `backendServerList[]`，每个后端的端口健康在 `portList[].status`（当前 CLI 无独立 AppBLB 健康 API）。

```json
{
  "sgId": "string",
  "backendServerList": [
    {
      "instanceId": "string",
      "weight": "int",
      "portList": [
        {"port": "int", "status": "available|...", "healthCheckPortType": "string"}
      ]
    }
  ]
}
```

### 4.3 对外 Markdown 模板

```markdown
### 后端健康概览：<blbId>

监听端口 / 服务器组：<listenerPort 或 sgId>

| 后端 | IP/端口 | 权重 | 健康状态 |
|------|---------|------|----------|
| <instanceId> | <ip>:<port> | <weight> | <status> |

汇总：健康 X / 总数 N
数据来源：DescribeBlbServerHealth / DescribeAppBlbServerGroupRs(portList[].status)
```

---

## 5. 费用摘要（费用输出格式固定）

**数据来源**：`BlbInquiry`（询价）。返回结构为 `prices[].{chargeItem, chargeUnit, originalPrice, discountPrice}`。

### 5.1 内部 schema

```json
{
  "blbType": "normal|application|ipv6|ipv6Application",
  "performanceLevel": "string",
  "count": "int",
  "billing": {"paymentTiming": "string", "billingMethod": "string"},
  "prices": [
    {"chargeItem": "string", "chargeUnit": "string", "originalPrice": "string", "discountPrice": "string"}
  ]
}
```

### 5.2 对外 Markdown 模板（询价/费用预估固定格式）

```markdown
### 费用摘要（询价结果）

- 实例类型：<blbType>（普通型/应用型/IPv6...）
- 规格：<performanceLevel 或 ->
- 数量：<count>
- 计费模式：<paymentTiming> / <billingMethod>

| 计费项 | 单位 | 原价 | 折后价 |
|--------|------|------|--------|
| <chargeItem> | <chargeUnit> | <originalPrice> | <discountPrice> |

> 说明：
> - 价格为单价，最终费用按实际用量/时长计算。
> - Postpaid+ByCapacityUnit 按用量(LCU)持续计费；Postpaid+BySpec 按规格计费；Prepaid 产生预付订单。
> - 公网访问需额外购买 EIP/带宽，费用不含在本询价内。
> - 金额原样取自 BlbInquiry，未做换算。

数据来源：BlbInquiry（region: <region>）
```

> 真实创建前必须先 `BlbInquiry` 并以本模板展示，等用户明确确认「我已知悉费用并确认创建」后才继续（见 `SKILL.md` §7.5 / `workflows.md` §9）。

---

## 6. 巡检报告模板

巡检项清单与判定规则见 `references/inspection.md`；本节只固定**报告输出结构**。

> **巡检是精简风险报告，不是实例详情**：只输出风险汇总 + 命中风险的明细，**不渲染 §1.5 实例拓扑、不逐项罗列完整配置**。正常项不必逐条列出（可在汇总里给"已检查项/正常项数量"），明细表只列**异常/有风险**的项，让用户一眼看到问题。

```markdown
### BLB 巡检报告

- 范围：profile <name> / region <region> / 实例数 N
- 巡检时间(UTC)：<time>
- 已检查项：<巡检项总数> / 正常：<正常数> / 命中风险：<风险数>

#### 风险汇总
| 风险等级 | 数量 |
|----------|------|
| 高 | X |
| 中 | Y |
| 低 | Z |

#### 风险明细（仅列异常/有风险项）
| 实例 | 巡检项 | 结果 | 风险等级 | 数据来源 | 建议 |
|------|--------|------|----------|----------|------|
| <blbId> | 未配置监听 | 异常 | 高 | DescribeBlbListener | <建议指针> |

> 无风险时：输出「本次巡检未发现风险项，已检查 <N> 项」，不展开实例配置详情。
> 标注「需控制台/监控」的项为当前 BCE CLI 只读 API 无法获取，需用户在控制台或监控侧确认。
```

规则：
1. 巡检报告**只给风险，不给完整配置**；用户若想看某实例完整配置，引导走 §1.5 实例拓扑（单独发起查询）。
2. 明细表只列异常/有风险项；正常项用汇总数量体现，不逐条铺开。
3. 风险等级固定三级（高/中/低）；CLI 查不到的项必须在「数据来源」列标注 `需控制台/监控`，不得伪造结论。

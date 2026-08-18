# AppBLB 应用型负载均衡 API 完整参考

> 唯一职责：**应用型 AppBLB（含应用型 IPv6 AppBLB）全量 CLI 命令与参数字典**，涵盖服务器组、服务器组端口、监听器、Host/Path 策略、IP 组。只负责"某个 API 有哪些参数、怎么填"。
> 不负责：普通型 BLB 参数（见 `blb-api-reference.md`）、多步操作流程（见 `workflows.md`）、输出格式（见 `output-format.md`）。
> 使用 `bce blb <API名> --help` 可查看实时帮助，`bce blb <API名> --generate-cli-skeleton` 生成 JSON 参数骨架；静态参数与实时 help 不一致时以实时 help 为准。

## 何时使用本文档

当用户操作 AppBLB、应用型 IPv6 AppBLB、服务器组、服务器组端口、AppBLB TCP/UDP/HTTP/HTTPS/SSL 监听器、Host/Path 转发策略、IP 组或 AppBLB 特有字段差异时，使用本文档确认 API 名、必填参数、复杂 JSON/List/Object 结构和高风险注意事项。

静态参考与当前机器 `"$BCE" blb <API名> --help` 不一致时，以实时 help 为准，并在回复中说明差异。

## 与 BLB 普通型的核心区别

| 维度 | BLB（普通型） | AppBLB（应用型） |
|------|--------------|-----------------|
| 后端模型 | 直接挂载后端服务器 | 服务器组 + 策略转发 |
| 监听器含 backendPort | 是 | 否（由服务器组端口管理） |
| 健康检查位置 | 监听器级别 | 服务器组端口级别 |
| 策略路由 | 不支持 | 支持（Host/Path 规则匹配） |
| X-Forwarded-For 字段名 | xForwardFor | xForwardedFor（注意 'ed'） |
| 会话保持时长字段 | keepSessionDuration | keepSessionTimeout |

---

## 目录

- [1. 实例管理](#1-实例管理)
- [2. 服务器组管理](#2-服务器组管理)
- [3. 监听器管理](#3-监听器管理)
- [4. 策略管理](#4-策略管理)
- [5. IP 组管理](#5-ip-组管理)

---

## 1. 实例管理

### CreateAppBlb — 创建 AppBLB 实例

```bash
bce blb CreateAppBlb \
  --clientToken <uuid> \
  --vpcId <vpcId> \
  --subnetId <subnetId> \
  --name "<名称>" \
  --desc "<描述>" \
  --performanceLevel <规格> \
  --billing '{"paymentTiming":"Postpaid"}' \
  --tags '[{"tagKey":"env","tagValue":"test"}]'
```

**创建应用型 IPv6 AppBLB：**
```bash
# 写操作必须先 dry-run，确认请求 body 中包含 "type": "ipv6Application"
bce blb CreateAppBlb \
  --type ipv6Application \
  --clientToken <uuid> \
  --vpcId <vpcId> \
  --subnetId <subnetId> \
  --name "<名称>" \
  --billing '{"paymentTiming":"Postpaid"}' \
  --dry-run
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| clientToken | String | **是** | 幂等 Token |
| vpcId | String | **是** | VPC ID |
| subnetId | String | **是** | 子网 ID |
| name | String | 否 | 名称 |
| desc | String | 否 | 描述 |
| type | String | 否 | 实例类型：默认 `application`；创建应用型 IPv6 AppBLB 使用 `ipv6Application`，真实执行前先 dry-run 确认请求 body |
| address | String | 否 | 指定内网 IP |
| eip | String | 否 | 绑定 EIP |
| performanceLevel | String | 否 | 性能规格（同 BLB） |
| billing | Object | 否 | 计费信息 |
| tags | List | 否 | 标签 |
| allocateIpv6 | Boolean | 否 | 是否分配 IPv6 地址；不替代 `type=ipv6Application` 的实例类型选择 |
| autoRenewLength | Integer | 否 | 自动续费时长 |
| resourceGroupId | String | 否 | 资源组 ID |
| allowDelete | Boolean | 否 | 是否允许删除，默认 true |
| allowModify | Boolean | 否 | 修改保护，默认 true（不保护） |

---

### DescribeAppBlbs — 查询 AppBLB 列表

```bash
bce blb DescribeAppBlbs \
  --name "<名称>" \
  --blbId <blbId> \
  --address "<IP>" \
  --bccId <bccId> \
  --exactlyMatch <true|false> \
  --pager
```

支持分页（marker/maxKeys/pager）。

> **AppBLB IPv6 查询注意**：当前 `DescribeAppBlbs` 不支持 `--type` 参数，不能使用 `DescribeAppBlbs --type ipv6Application` 过滤列表。需要区分 IPv6 AppBLB 时，先用普通 `DescribeAppBlbs` 查询，再按返回中的 `type`、IPv6 地址、名称或标签等字段过滤；如果返回结构没有可区分字段，应向用户说明 CLI 列表接口当前无法按 AppBLB IPv6 类型过滤。

### DescribeAppBlb — 查询 AppBLB 详情

```bash
bce blb DescribeAppBlb --blbId <blbId>
```

### UpdateAppBlb — 更新 AppBLB

```bash
bce blb UpdateAppBlb \
  --blbId <blbId> \
  --clientToken <uuid> \
  --name "<新名称>" \
  --desc "<新描述>" \
  --allowDelete <true|false>
```

### ReleaseAppBlb — 释放 AppBLB

```bash
bce blb ReleaseAppBlb --blbId <blbId>
```

> **⚠️ 危险操作**：释放后不可恢复。执行前必须先按 `SKILL.md` §11.1 校验闲置；非闲置时展示监听器、服务器组/后端、策略等依赖摘要并请用户再次确认。
>
> 释放前至少执行：
> ```bash
> bce blb DescribeAppBlbListener --region <region> --blbId <blbId> --pager
> bce blb DescribeAppBlbServerGroup --region <region> --blbId <blbId> --pager
> bce blb DescribeAppBlbPolicy --region <region> --blbId <blbId> --port <port> --type <type> --pager
> bce blb ReleaseAppBlb --region <region> --blbId <blbId> --dry-run
> ```

---

## 2. 服务器组管理

### CreateAppBlbServerGroup — 创建服务器组

```bash
bce blb CreateAppBlbServerGroup \
  --blbId <blbId> \
  --clientToken <uuid> \
  --name "<组名>" \
  --desc "<描述>" \
  --backendServerList '[{"instanceId":"i-xxx","weight":100}]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| name | String | 否 | 服务器组名称 |
| desc | String | 否 | 描述 |
| backendServerList | List | 否 | 初始后端列表（instanceId, weight） |

---

### DescribeAppBlbServerGroup — 查询服务器组

```bash
bce blb DescribeAppBlbServerGroup \
  --blbId <blbId> \
  --name "<组名>" \
  --exactlyMatch <true|false> \
  --pager
```

### DescribeAppBlbServerGroupRs — 查询服务器组已挂载的后端

```bash
bce blb DescribeAppBlbServerGroupRs \
  --blbId <blbId> \
  --sgId <sgId> \
  --pager
```

### DescribeAppBlbServerGroupMountRs — 查询服务器组关联的挂载关系

```bash
bce blb DescribeAppBlbServerGroupMountRs \
  --blbId <blbId> \
  --sgId <sgId> \
  --pager
```

### DescribeAppBlbServerGroupUnmountRs — 查询服务器组未挂载的后端

```bash
bce blb DescribeAppBlbServerGroupUnmountRs \
  --blbId <blbId> \
  --sgId <sgId> \
  --pager
```

---

### UpdateAppBlbServerGroup — 更新服务器组

```bash
bce blb UpdateAppBlbServerGroup \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --name "<新名称>" \
  --desc "<新描述>"
```

### DeleteAppBlbServerGroup — 删除服务器组

```bash
bce blb DeleteAppBlbServerGroup \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId>
```

> **⚠️ 高风险操作**：删除服务器组会移除其后端关系并影响转发策略。执行前必须二次确认 profile、region、blbId、appServerGroupId 和影响范围。

---

### AddAppBlbServerGroupRs — 添加后端服务器到服务器组

```bash
bce blb AddAppBlbServerGroupRs \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --backendServerList '[{"instanceId":"i-xxx","weight":100}]'
```

使用 --unfold 方式（推荐多服务器时使用）：
```bash
bce blb AddAppBlbServerGroupRs --unfold \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --backendServerList instanceId=i-xxx weight=100 \
  --backendServerList instanceId=i-yyy weight=50
```

### DeleteAppBlbServerGroupRs — 从服务器组移除后端

```bash
bce blb DeleteAppBlbServerGroupRs \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --backendServerIdList '["i-xxx"]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| sgId | String | **是** | 服务器组 ID |
| backendServerIdList | List | **是** | 要移除的后端服务器 ID 列表 |

> **⚠️ 高风险操作**：移除后端会影响该服务器组承载的流量。执行前必须二次确认 profile、region、blbId、sgId 和 instanceId 列表。

---

### CreateAppBlbServerGroupPort — 创建服务器组端口

```bash
bce blb CreateAppBlbServerGroupPort \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --port <端口号> \
  --type <TCP|UDP|HTTP> \
  --enableHealthCheck <true|false> \
  --healthCheck <tcp|http|udp> \
  --healthCheckPort <检查端口> \
  --healthCheckUrlPath "/health" \
  --healthCheckTimeoutInSecond 3 \
  --healthCheckIntervalInSecond 5 \
  --healthCheckDownRetry 3 \
  --healthCheckUpRetry 3 \
  --healthCheckNormalStatus "http_2xx"
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| sgId | String | **是** | 服务器组 ID |
| port | Integer | **是** | 后端端口 |
| type | String | **是** | 协议类型，支持 TCP / UDP / HTTP |
| enableHealthCheck | Boolean | 否 | 是否开启健康检查 |
| healthCheck | String | 否 | 检查协议 |
| healthCheckPort | Integer | 否 | 检查端口 |
| healthCheckUrlPath | String | 否 | HTTP 检查路径 |
| healthCheckTimeoutInSecond | Integer | 否 | 超时（秒），默认3 |
| healthCheckIntervalInSecond | Integer | 否 | 间隔（秒），默认3 |
| healthCheckDownRetry | Integer | 否 | 不健康阈值，默认3 |
| healthCheckUpRetry | Integer | 否 | 健康阈值，默认3 |
| healthCheckNormalStatus | String | 否 | 正常状态码 |
| healthCheckHost | String | 否 | 检查 Host |
| udpHealthCheckString | String | 否 | UDP 检查字符串 |

### UpdateAppBlbServerGroupPort — 更新服务器组端口健康检查配置

```bash
bce blb UpdateAppBlbServerGroupPort \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --portId <portId> \
  --enableHealthCheck <true|false> \
  --healthCheck <HTTP|TCP|UDP|ICMP> \
  --healthCheckPort <检查端口> \
  --healthCheckUrlPath "/health"
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| sgId | String | **是** | 服务器组 ID |
| portId | String | **是** | 服务器组端口 ID |
| enableHealthCheck | Boolean | 否 | 是否开启健康检查 |
| healthCheck | String | 否 | 健康检查协议，支持 HTTP / TCP / UDP / ICMP |
| healthCheckPort | Integer | 否 | 健康检查端口 |
| healthCheckUrlPath | String | 否 | HTTP 检查路径 |
| healthCheckTimeoutInSecond | Integer | 否 | 超时（秒），默认3 |
| healthCheckIntervalInSecond | Integer | 否 | 间隔（秒），默认3 |
| healthCheckDownRetry | Integer | 否 | 不健康阈值，默认3 |
| healthCheckUpRetry | Integer | 否 | 健康阈值，默认3 |
| healthCheckNormalStatus | String | 否 | 正常状态码 |
| healthCheckHost | String | 否 | 检查 Host |
| udpHealthCheckString | String | 否 | UDP 检查字符串 |

---

## 3. 监听器管理

> AppBLB 监听器没有 backendPort 参数，后端端口由服务器组端口管理。
> AppBLB 监听器也没有健康检查参数（健康检查在服务器组端口级别配置）。

### CreateAppBlbTcpListener

```bash
bce blb CreateAppBlbTcpListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 80 \
  --scheduler RoundRobin \
  --tcpSessionTimeout 900 \
  --description "<描述>"
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| listenerPort | Integer | **是** | 监听端口 |
| scheduler | String | **是** | RoundRobin / WeightLeastConn / Hash |
| tcpSessionTimeout | Integer | 否 | TCP 超时，默认900 |
| description | String | 否 | 监听器描述 |

### CreateAppBlbUdpListener

```bash
bce blb CreateAppBlbUdpListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 53 \
  --scheduler RoundRobin \
  --udpSessionTimeout 90
```

### CreateAppBlbHttpListener

```bash
bce blb CreateAppBlbHttpListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 80 \
  --scheduler LeastConnection \
  --keepSession true \
  --keepSessionType insert \
  --keepSessionTimeout 3600 \
  --xForwardedFor true \
  --serverTimeout 30 \
  --redirectPort 443
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| listenerPort | Integer | **是** | 监听端口 |
| scheduler | String | **是** | RoundRobin / LeastConnection |
| keepSession | Boolean | 否 | 会话保持，默认 false |
| keepSessionType | String | 否 | insert / rewrite |
| keepSessionTimeout | Integer | 否 | Cookie 时长（秒），默认3600 |
| keepSessionCookieName | String | 否 | rewrite 模式 Cookie 名称 |
| xForwardedFor | Boolean | 否 | 传递真实 IP（注意拼写是 For 不是 ForwardFor） |
| xForwardedProto | Boolean | 否 | 传递协议 |
| additionalAttributes | Object | 否 | gzipJson: "on"/"off" |
| serverTimeout | Integer | 否 | 后端超时，默认30 |
| redirectPort | Integer | 否 | HTTPS 重定向端口 |
| description | String | 否 | 描述 |

### CreateAppBlbHttpsListener

```bash
bce blb CreateAppBlbHttpsListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 443 \
  --scheduler LeastConnection \
  --certIds '["cert-xxxxx"]' \
  --encryptionType tls_cipher_policy_1_2 \
  --dualAuth false
```

在 HTTP 监听器基础上增加：certIds（**必填**）、encryptionType、encryptionProtocols、appliedCiphers、dualAuth、clientCertIds、additionalCertDomains。

> **证书依赖说明**：`certIds` / `clientCertIds` 只能引用已存在的证书 ID；当前 BCE CLI 无证书管理服务，证书申请/上传/续期/轮换不在本 Skill 范围。HTTPS 安全基线（加密策略 / mTLS / SNI 多域名）配置流程见 `references/workflows.md` §13。

### CreateAppBlbSslListener

```bash
bce blb CreateAppBlbSslListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 443 \
  --scheduler RoundRobin \
  --certIds '["cert-xxxxx"]'
```

### 更新/查询监听器

| 操作 | CLI 命令 |
|------|---------|
| 更新 TCP | `bce blb UpdateAppBlbTcpListener --blbId <id> --listenerPort <port> ...` |
| 更新 UDP | `bce blb UpdateAppBlbUdpListener --blbId <id> --listenerPort <port> ...` |
| 更新 HTTP | `bce blb UpdateAppBlbHttpListener --blbId <id> --listenerPort <port> ...` |
| 更新 HTTPS | `bce blb UpdateAppBlbHttpsListener --blbId <id> --listenerPort <port> ...` |
| 更新 SSL | `bce blb UpdateAppBlbSslListener --blbId <id> --listenerPort <port> ...` |
| 查询 TCP | `bce blb DescribeAppBlbTcpListener --blbId <id> --listenerPort <port> --pager` |
| 查询 UDP | `bce blb DescribeAppBlbUdpListener --blbId <id> --listenerPort <port> --pager` |
| 查询 HTTP | `bce blb DescribeAppBlbHttpListener --blbId <id> --listenerPort <port> --pager` |
| 查询 HTTPS | `bce blb DescribeAppBlbHttpsListener --blbId <id> --listenerPort <port> --pager` |
| 查询 SSL | `bce blb DescribeAppBlbSslListener --blbId <id> --listenerPort <port> --pager` |

### 删除监听器

```bash
bce blb DeleteAppBlbListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --portTypeList '[{"port":80,"type":"TCP"}]'
```

> **⚠️ 高风险操作**：删除后对应端口流量立即中断。执行前必须二次确认 profile、region、blbId、端口、协议和影响范围。

---

## 4. 策略管理

> AppBLB 策略用于基于规则将流量转发到不同的服务器组或 IP 组，实现域名/路径级别的路由。
> TCP/UDP/SSL 监听器只支持一条完全匹配策略；HTTP/HTTPS 监听器支持多条策略，需通过 `priority` 控制匹配顺序。

### CreateAppBlbPolicy — 创建转发策略

```bash
bce blb CreateAppBlbPolicy \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 80 \
  --type <forwarding|acl> \
  --appPolicyVos '[{
    "appServerGroupId":"sg-xxx",
    "backendPort":8080,
    "priority":1,
    "desc":"web服务",
    "ruleList":[
      {"key":"Host","value":"www.example.com"},
      {"key":"Path","value":"/api/*"}
    ]
  }]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| listenerPort | Integer | **是** | 监听器端口 |
| type | String | 否 | 策略类型 |
| appPolicyVos | List | **是** | 策略列表 |
| appPolicyVos[].appServerGroupId | String | 否 | 目标服务器组 ID |
| appPolicyVos[].appIpGroupId | String | 否 | 目标 IP 组 ID |
| appPolicyVos[].backendPort | Integer | 否 | 后端端口 |
| appPolicyVos[].portType | String | 否 | 端口协议类型 |
| appPolicyVos[].priority | Integer | 否 | 优先级（数字越小优先级越高） |
| appPolicyVos[].ruleList | List | 否 | 匹配规则列表 |
| appPolicyVos[].ruleList[].key | String | 否 | 规则 Key |
| appPolicyVos[].ruleList[].value | String | 否 | 规则 Value |
| appPolicyVos[].desc | String | 否 | 策略描述 |

**常用规则 Key 值：**
- `Host` — 域名匹配
- `Path` — URL 路径匹配，支持通配符 *

### DescribeAppBlbPolicy — 查询策略

```bash
bce blb DescribeAppBlbPolicy \
  --blbId <blbId> \
  --port 80 \
  --type <forwarding> \
  --pager
```

### UpdateAppBlbPolicy — 更新策略

> **重要限制**：此接口仅支持修改策略的 `priority` 与 `description`。如果要变更 `ruleList`、`appServerGroupId`、`appIpGroupId`、`backendPort` 或 `portType`，必须先 `DeleteAppBlbPolicy`，再用 `CreateAppBlbPolicy` 重建策略。

```bash
bce blb UpdateAppBlbPolicy \
  --blbId <blbId> \
  --port 80 \
  --type HTTP \
  --policyList '[{
    "policyId":"policyId1",
    "priority":1,
    "description":"updated desc"
  }]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | 否 | 幂等 Token |
| port | Integer | **是** | 监听器端口 |
| type | String | **是** | 监听器协议类型（同端口多协议时必填） |
| policyList | List | **是** | 要更新的策略列表 |
| policyList[].policyId | String | 是 | 策略 ID |
| policyList[].priority | Integer | 否 | 优先级；`priority` 和 `description` 不能同时为空 |
| policyList[].description | String | 否 | 策略描述；不能用于修改匹配规则或目标组 |

### DeleteAppBlbPolicy — 删除策略

```bash
bce blb DeleteAppBlbPolicy \
  --blbId <blbId> \
  --clientToken <uuid> \
  --port 80 \
  --policyIdList '["policyId1","policyId2"]'
```

> **⚠️ 高风险操作**：删除策略会影响 Host/Path 流量路由。执行前必须二次确认 profile、region、blbId、port、policyIdList 和影响范围。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| port | Integer | **是** | 监听器端口 |
| policyIdList | List | **是** | 要删除的策略 ID 列表 |
| type | String | 否 | 当同一端口存在多协议时必填 |

---

## 5. IP 组管理

> IP 组用于将非 BCC 实例的 IP 地址作为后端添加到 AppBLB。

### CreateAppBlbIpGroup — 创建 IP 组

```bash
bce blb CreateAppBlbIpGroup \
  --blbId <blbId> \
  --clientToken <uuid> \
  --name "<组名>" \
  --desc "<描述>" \
  --memberList '[{"ip":"10.0.0.5","port":80,"weight":100}]'
```

### DescribeAppBlbIpGroup — 查询 IP 组

```bash
bce blb DescribeAppBlbIpGroup --blbId <blbId> --pager
```

### UpdateAppBlbIpGroup — 更新 IP 组

```bash
bce blb UpdateAppBlbIpGroup \
  --blbId <blbId> \
  --clientToken <uuid> \
  --appIpGroupId <groupId> \
  --name "<新名称>"
```

### DeleteAppBlbIpGroup — 删除 IP 组

```bash
bce blb DeleteAppBlbIpGroup \
  --blbId <blbId> \
  --clientToken <uuid> \
  --appIpGroupId <groupId>
```

> **⚠️ 高风险操作**：删除 IP 组会影响依赖该 IP 组的转发策略。执行前必须二次确认 profile、region、blbId、appIpGroupId 和影响范围。

### CreateAppBlbIpGroupMember — 添加 IP 组成员

```bash
bce blb CreateAppBlbIpGroupMember \
  --blbId <blbId> \
  --ipGroupId <groupId> \
  --memberList '[{"ip":"10.0.0.6","port":80,"weight":80}]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | 否 | 幂等 Token |
| ipGroupId | String | **是** | IP 组 ID |
| memberList | List | **是** | IP 成员列表（ip, port, weight） |

### DescribeAppBlbIpGroupMember — 查询 IP 组成员

```bash
bce blb DescribeAppBlbIpGroupMember \
  --blbId <blbId> \
  --ipGroupId <groupId> \
  --pager
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| ipGroupId | String | **是** | IP 组 ID |
| marker | String | 否 | 分页标记 |
| maxKeys | Integer | 否 | 每页条数，默认1000 |

### DeleteAppBlbIpGroupMember — 删除 IP 组成员

```bash
bce blb DeleteAppBlbIpGroupMember \
  --blbId <blbId> \
  --clientToken <uuid> \
  --ipGroupId <groupId> \
  --memberIdList '["memberId1","memberId2"]'
```

> **⚠️ 高风险操作**：删除 IP 组成员会影响对应 IP 后端接收流量。执行前必须二次确认 profile、region、blbId、ipGroupId 和 memberIdList。

### CreateAppBlbIpGroupProtocol — 创建 IP 组协议配置

```bash
bce blb CreateAppBlbIpGroupProtocol \
  --blbId <blbId> \
  --clientToken <uuid> \
  --ipGroupId <groupId> \
  --type tcp \
  --port 80 \
  --healthCheck tcp \
  --healthCheckPort 80
```

### DeleteAppBlbIpGroupProtocol — 删除 IP 组协议

```bash
bce blb DeleteAppBlbIpGroupProtocol \
  --blbId <blbId> \
  --clientToken <uuid> \
  --ipGroupId <groupId> \
  --type tcp \
  --port 80
```

> **⚠️ 高风险操作**：删除 IP 组协议会影响对应 IP 后端协议端口和健康检查。执行前必须二次确认 profile、region、blbId、ipGroupId、type 和 port。

---

## 6. 补充 API

### UpdateAppBlbServerGroupRs — 更新服务器组后端权重

```bash
bce blb UpdateAppBlbServerGroupRs \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --backendServerList '[{"instanceId":"i-xxx","weight":80}]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| sgId | String | **是** | 服务器组 ID |
| backendServerList | List | **是** | 需要更新的后端列表（instanceId + weight） |

> **优雅排空替代方案**：将目标 RS 的 `weight` 置 0（范围 0-100，0=不转发新流量，不主动断开存量连接），等待人工设定的排空窗口后再 `DeleteAppBlbServerGroupRs` 摘除。完整流程见 `references/workflows.md` §15。

### DeleteAppBlbServerGroupPort — 删除服务器组端口

```bash
bce blb DeleteAppBlbServerGroupPort \
  --blbId <blbId> \
  --clientToken <uuid> \
  --sgId <sgId> \
  --portIdList '["portId1","portId2"]'
```

> **⚠️ 高风险操作**：删除服务器组端口会影响后端端口转发和健康检查。执行前必须二次确认 profile、region、blbId、sgId 和 portIdList。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| sgId | String | **是** | 服务器组 ID |
| portIdList | List | **是** | 要删除的端口 ID 列表 |

### DescribeAppBlbListener — 查询 AppBLB 所有监听器

```bash
bce blb DescribeAppBlbListener \
  --blbId <blbId> \
  --listenerPort 80 \
  --pager
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| listenerPort | Integer | 否 | 指定监听端口查询，不传则查询全部 |
| marker | String | 否 | 分页标记 |
| maxKeys | Integer | 否 | 每页条数，默认1000 |

### UpdateAppBlbIpGroupMember — 更新 IP 组成员

```bash
bce blb UpdateAppBlbIpGroupMember \
  --blbId <blbId> \
  --ipGroupId <groupId> \
  --memberList '[{"memberId":"memberId1","ip":"10.0.0.6","port":80,"weight":80}]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | 否 | 幂等 Token |
| ipGroupId | String | **是** | IP 组 ID |
| memberList | List | **是** | IP 成员列表（memberId, ip, port, weight） |

### UpdateAppBlbIpGroupProtocol — 更新 IP 组协议健康检查配置

```bash
bce blb UpdateAppBlbIpGroupProtocol \
  --blbId <blbId> \
  --ipGroupId <groupId> \
  --id <protocolId> \
  --healthCheck tcp \
  --healthCheckPort 80 \
  --healthCheckIntervalInSecond 5
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | AppBLB 实例 ID |
| clientToken | String | 否 | 幂等 Token |
| ipGroupId | String | **是** | IP 组 ID |
| id | String | **是** | IP 组协议 ID |
| healthCheck | String | 否 | 健康检查协议（TCP/UDP/HTTP/ICMP） |
| healthCheckPort | Integer | 否 | 健康检查端口 |
| healthCheckUrlPath | String | 否 | HTTP 检查路径 |
| healthCheckTimeoutInSecond | Integer | 否 | 超时（秒），默认3 |
| healthCheckIntervalInSecond | Integer | 否 | 间隔（秒），默认3 |
| healthCheckDownRetry | Integer | 否 | 不健康阈值，默认3 |
| healthCheckUpRetry | Integer | 否 | 健康阈值，默认3 |
| healthCheckNormalStatus | String | 否 | 正常状态码 |
| healthCheckHost | String | 否 | 检查 Host |
| udpHealthCheckString | String | 否 | UDP 检查字符串 |

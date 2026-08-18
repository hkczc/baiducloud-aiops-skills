# BLB 普通型负载均衡 API 完整参考

> 唯一职责：**普通型 BLB（含普通型 IPv6 BLB）全量 CLI 命令与参数字典**。只负责"某个 API 有哪些参数、怎么填"。
> 不负责：AppBLB 参数（见 `appblb-api-reference.md`）、多步操作流程（见 `workflows.md`）、输出格式（见 `output-format.md`）。
> 使用 `bce blb <API名> --help` 可查看实时帮助，`bce blb <API名> --generate-cli-skeleton` 生成 JSON 参数骨架；静态参数与实时 help 不一致时以实时 help 为准。
> 本文中的 `type=ipv6` 适用于普通型 IPv6 BLB，不代表应用型 IPv6 AppBLB。

## 何时使用本文档

当用户操作普通型 BLB、普通型 IPv6 BLB、直接后端服务器、BLB TCP/UDP/HTTP/HTTPS/SSL 监听器、安全组、企业安全组、ACL、修改保护、计费、服务型能力或 LBDC 时，使用本文档确认 API 名、必填参数、复杂 JSON/List/Object 结构和高风险注意事项。

静态参考与当前机器 `"$BCE" blb <API名> --help` 不一致时，以实时 help 为准，并在回复中说明差异。

---

## 目录

- [1. 实例管理](#1-实例管理)
- [2. 后端服务器管理](#2-后端服务器管理)
- [3. TCP 监听器](#3-tcp-监听器)
- [4. UDP 监听器](#4-udp-监听器)
- [5. HTTP 监听器](#5-http-监听器)
- [6. HTTPS 监听器](#6-https-监听器)
- [7. SSL 监听器](#7-ssl-监听器)
- [8. 监听器查询与批量删除](#8-监听器查询与批量删除)
- [9. 安全组管理](#9-安全组管理)
- [10. ACL 与修改保护](#10-acl-与修改保护)
- [11. 计费管理](#11-计费管理)
- [12. 服务型能力](#12-服务型能力)
- [13. LBDC 管理](#13-lbdc-管理)

---

## 1. 实例管理

### CreateBlb — 创建 BLB 实例

```bash
bce blb CreateBlb \
  --vpcId <vpcId> \
  --subnetId <subnetId> \
  --name "<名称>" \
  --desc "<描述>" \
  --type <ipv6> \
  --address "<指定IP>" \
  --eip "<绑定EIP地址>" \
  --allocateIpv6 <true|false> \
  --performanceLevel <规格> \
  --allowDelete <true|false> \
  --allowModify <true|false> \
  --modificationProtectionReason "<保护原因>" \
  --billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}' \
  --tags '[{"tagKey":"env","tagValue":"test"}]'
```

普通型 BLB 默认不传 `type`；创建普通型 IPv6 BLB 时传 `--type ipv6`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| vpcId | String | **是** | VPC ID |
| subnetId | String | **是** | 子网 ID |
| name | String | 否 | 名称，1-65字节，字母开头，支持字母/数字/-_./ |
| desc | String | 否 | 描述，0-450字节，支持中文 |
| type | String | 否 | 传 "ipv6" 创建普通型 IPv6 BLB，默认普通型 BLB |
| address | String | 否 | 指定内网 IP，须在子网 CIDR 范围内 |
| eip | String | 否 | 绑定已有 EIP 地址 |
| allocateIpv6 | Boolean | 否 | 是否分配 IPv6 地址 |
| performanceLevel | String | 否 | 性能规格（见下方说明） |
| tags | List | 否 | 标签列表，每项含 tagKey 和 tagValue |
| billing | Object | 否 | 计费信息（预付费时必填） |
| billing.paymentTiming | String | 否 | Postpaid / Prepaid |
| billing.billingMethod | String | 否 | BySpec（按规格）/ ByCapacityUnit（按量） |
| billing.reservation.reservationLength | Integer | 否 | 预付费时长（月） |
| autoRenewLength | Integer | 否 | 自动续费时长，1-9月或1-3年 |
| autoRenewTimeUnit | String | 否 | month / year |
| resourceGroupId | String | 否 | 资源组 ID |
| allowDelete | Boolean | 否 | 是否允许删除，默认 true |
| allowModify | Boolean | 否 | 是否允许修改（false 则开启修改保护），默认 true |
| modificationProtectionReason | String | 否 | 修改保护原因，0-128字符 |
| clientToken | String | 否 | 幂等 Token，最大64字符 |

**performanceLevel 可选值：**
small1（标准1）、small2（标准2）、medium1（增强1）、medium2（增强2）、large1（超大1）、large2（超大2）、large3（超大3）、unlimited（仅后付费按量）

---

### DescribeBlbs — 查询 BLB 列表

```bash
bce blb DescribeBlbs \
  --name "<名称>" \
  --blbId <blbId> \
  --address "<IP地址>" \
  --bccId <bccId> \
  --type <ipv6> \
  --exactlyMatch <true|false> \
  --maxKeys 1000 \
  --marker "<分页标记>" \
  --pager
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | String | 否 | 按名称过滤 |
| blbId | String | 否 | 按实例 ID 精确过滤 |
| address | String | 否 | 按内网 IP 过滤 |
| bccId | String | 否 | 过滤绑定了指定 BCC 的 BLB |
| type | String | 否 | 传 "ipv6" 查询 IPv6 BLB |
| exactlyMatch | Boolean | 否 | true=精确匹配，false=模糊匹配 |
| marker | String | 否 | 分页起始位置 |
| maxKeys | Integer | 否 | 每页最大条数，默认1000 |
| --pager | Flag | 否 | 自动翻页，聚合所有页 |

**支持分页**（input_token=marker, output_token=nextMarker, result_key=blbList）

---

### DescribeBlb — 查询 BLB 详情

```bash
bce blb DescribeBlb --blbId <blbId> --type <ipv6>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| type | String | 否 | 传 "ipv6" 查询 IPv6 类型 |

---

### UpdateBlb — 更新 BLB 配置

```bash
bce blb UpdateBlb \
  --blbId <blbId> \
  --name "<新名称>" \
  --desc "<新描述>" \
  --allowDelete <true|false> \
  --allocateIpv6 <true|false>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| name | String | 否 | 新名称 |
| desc | String | 否 | 新描述 |
| allowDelete | Boolean | 否 | 是否允许删除 |
| allocateIpv6 | Boolean | 否 | 是否分配 IPv6 |
| clientToken | String | 否 | 幂等 Token |

---

### ReleaseBlb — 释放（删除）BLB 实例

```bash
bce blb ReleaseBlb --blbId <blbId> --clientToken <uuid>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | 否 | 幂等 Token |

> **⚠️ 高风险操作**：释放后不可恢复，BLB 下所有监听器和后端关系一并删除。执行前必须先按 `SKILL.md` §11.1 校验闲置；非闲置时展示依赖摘要和清依赖建议，再请用户确认是否仍要释放。
>
> 释放前至少执行：
> ```bash
> bce blb DescribeBlbListener --region <region> --blbId <blbId> --pager
> bce blb DescribeBlbServers --region <region> --blbId <blbId> --pager
> bce blb ReleaseBlb --region <region> --blbId <blbId> --clientToken <uuid> --dry-run
> ```

---

### ResizeBlb — 变更 BLB 规格

```bash
bce blb ResizeBlb \
  --blbId <blbId> \
  --clientToken <uuid> \
  --performanceLevel <新规格>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| performanceLevel | String | 否 | 目标规格 |

---

## 2. 后端服务器管理

### AddBlbServer — 添加后端服务器

```bash
bce blb AddBlbServer \
  --blbId <blbId> \
  --clientToken <uuid> \
  --backendServerList '[{"instanceId":"i-xxx","weight":100}]'
```

使用 --unfold 方式：
```bash
bce blb AddBlbServer --unfold \
  --blbId <blbId> \
  --clientToken <uuid> \
  --backendServerList instanceId=i-xxx weight=100 \
  --backendServerList instanceId=i-yyy weight=50
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| backendServerList | List | **是** | 后端服务器列表 |
| backendServerList[].instanceId | String | 否 | BCC 实例 ID |
| backendServerList[].weight | Integer | 否 | 权重 0-100，0 表示不转发流量 |

---

### DescribeBlbServers — 查询后端服务器列表

```bash
bce blb DescribeBlbServers --blbId <blbId> --marker "<标记>" --maxKeys 1000 --pager
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| marker | String | 否 | 分页标记 |
| maxKeys | Integer | 否 | 每页条数，默认1000 |

---

### UpdateBlbServer — 更新后端服务器权重

```bash
bce blb UpdateBlbServer \
  --blbId <blbId> \
  --clientToken <uuid> \
  --backendServerList '[{"instanceId":"i-xxx","weight":80}]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| backendServerList | List | **是** | 需要更新的服务器列表（instanceId + weight） |

> **优雅排空替代方案**：BCE CLI 无原生 connection draining。将目标后端 `weight` 置 0 可停止新流量分发（不主动断开存量长连接），等待人工设定的排空窗口后再 `DeleteBlbServer` 摘除。完整流程见 `references/workflows.md` §15。

---

### DeleteBlbServer — 移除后端服务器

```bash
bce blb DeleteBlbServer \
  --blbId <blbId> \
  --clientToken <uuid> \
  --backendServerList '["i-xxx"]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| backendServerList | List | **是** | 需要移除的后端服务器 ID 列表 |

> **⚠️ 高风险操作**：移除后该服务器不再接收该 BLB 转发流量。执行前必须二次确认 profile、region、blbId、instanceId 列表和影响范围。

---

### DescribeBlbServerHealth — 查询后端服务器健康状态

```bash
bce blb DescribeBlbServerHealth \
  --blbId <blbId> \
  --listenerPort <端口> \
  --pager
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| listenerPort | Integer | **是** | 监听端口 |
| marker | String | 否 | 分页标记 |
| maxKeys | Integer | 否 | 每页条数 |

---

## 3. TCP 监听器

### CreateBlbTcpListener

```bash
bce blb CreateBlbTcpListener \
  --blbId <blbId> \
  --listenerPort 80 \
  --backendPort 8080 \
  --scheduler RoundRobin \
  --tcpSessionTimeout 900 \
  --healthCheckType TCP \
  --healthCheckTimeoutInSecond 3 \
  --healthCheckInterval 3 \
  --unhealthyThreshold 3 \
  --healthyThreshold 3
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| listenerPort | Integer | **是** | 监听端口，1-65535 |
| backendPort | Integer | **是** | 后端端口，1-65535 |
| scheduler | String | **是** | RoundRobin / WeightLeastConn / Hash |
| tcpSessionTimeout | Integer | 否 | TCP 连接超时（秒），默认900，范围10-4000 |
| healthCheckType | String | 否 | 默认 "TCP" |
| healthCheckTimeoutInSecond | Integer | 否 | 健康检查超时，默认3，范围1-60 |
| healthCheckInterval | Integer | 否 | 健康检查间隔，默认3，范围1-10 |
| unhealthyThreshold | Integer | 否 | 不健康阈值，默认3，范围2-5 |
| healthyThreshold | Integer | 否 | 健康阈值，默认3，范围2-5 |

### UpdateBlbTcpListener

```bash
bce blb UpdateBlbTcpListener \
  --blbId <blbId> \
  --listenerPort 80 \
  --backendPort 8080 \
  --scheduler RoundRobin
```

参数同创建，blbId 和 listenerPort 必填，其余按需传入。

### DescribeBlbTcpListener

```bash
bce blb DescribeBlbTcpListener --blbId <blbId> --listenerPort 80 --pager
```

---

## 4. UDP 监听器

### CreateBlbUdpListener

```bash
bce blb CreateBlbUdpListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 53 \
  --backendPort 53 \
  --scheduler RoundRobin \
  --healthCheckType UDP \
  --healthCheckString "health" \
  --healthCheckPort 53 \
  --udpSessionTimeout 90
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| listenerPort | Integer | **是** | 监听端口 |
| backendPort | Integer | **是** | 后端端口 |
| scheduler | String | **是** | RoundRobin / WeightLeastConn / Hash |
| healthCheckType | String | 否 | UDP / ICMP，默认 UDP |
| healthCheckPort | Integer | 否 | 健康检查端口，默认 backendPort |
| healthCheckString | String | 否 | UDP 检查请求字符串（UDP 协议必填），支持 hex/ASCII |
| healthCheckTimeoutInSecond | Integer | 否 | 默认3，范围1-60 |
| healthCheckInterval | Integer | 否 | 默认3，范围1-10 |
| unhealthyThreshold | Integer | 否 | 默认3，范围2-5 |
| healthyThreshold | Integer | 否 | 默认3，范围2-5 |
| udpSessionTimeout | Integer | 否 | 默认90，范围5-4000 |

### UpdateBlbUdpListener / DescribeBlbUdpListener

同 TCP 模式，API 名替换为 Udp。

---

## 5. HTTP 监听器

### CreateBlbHttpListener

```bash
bce blb CreateBlbHttpListener \
  --blbId <blbId> \
  --listenerPort 80 \
  --backendPort 8080 \
  --scheduler LeastConnection \
  --keepSession true \
  --keepSessionType insert \
  --keepSessionDuration 3600 \
  --xForwardFor true \
  --healthCheckType HTTP \
  --healthCheckURI "/health" \
  --healthCheckInterval 5 \
  --serverTimeout 30 \
  --redirectPort 443
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| listenerPort | Integer | **是** | 监听端口 |
| backendPort | Integer | **是** | 后端端口 |
| scheduler | String | **是** | RoundRobin / LeastConnection |
| keepSession | Boolean | 否 | 是否开启会话保持，默认 false |
| keepSessionType | String | 否 | insert / rewrite，默认 insert |
| keepSessionDuration | Integer | 否 | Cookie 时长（秒），默认3600，范围1-15552000 |
| keepSessionCookieName | String | 否 | rewrite 模式下的 Cookie 名称 |
| xForwardFor | Boolean | 否 | 是否通过 X-Forwarded-For 传递真实 IP |
| xForwardedProto | Boolean | 否 | 是否通过 x-forwarded-proto 传递协议 |
| additionalAttributes | Object | 否 | 附加属性，子字段 gzipJson（"on"/"off"） |
| healthCheckType | String | 否 | HTTP / TCP，默认 HTTP |
| healthCheckPort | Integer | 否 | 健康检查端口，默认 backendPort |
| healthCheckURI | String | 否 | 健康检查路径，默认 "/" |
| healthCheckTimeoutInSecond | Integer | 否 | 默认3，范围1-60 |
| healthCheckInterval | Integer | 否 | 默认3，范围1-10 |
| unhealthyThreshold | Integer | 否 | 默认3，范围2-5 |
| healthyThreshold | Integer | 否 | 默认3，范围2-5 |
| healthCheckNormalStatus | String | 否 | 正常状态码，如 "http_2xx\|http_3xx" |
| healthCheckHost | String | 否 | 健康检查 Host 头 |
| serverTimeout | Integer | 否 | 后端超时（秒），默认30，范围1-3600 |
| redirectPort | Integer | 否 | 重定向到 HTTPS 监听器的端口 |

### UpdateBlbHttpListener / DescribeBlbHttpListener

同模式，API 名替换。

---

## 6. HTTPS 监听器

### CreateBlbHttpsListener

```bash
bce blb CreateBlbHttpsListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 443 \
  --backendPort 8080 \
  --scheduler LeastConnection \
  --certIds '["cert-xxxxx"]' \
  --encryptionType tls_cipher_policy_1_2 \
  --dualAuth false \
  --healthCheckType HTTP \
  --healthCheckURI "/health"
```

**在 HTTP 监听器普通上增加以下参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| clientToken | String | **是** | 幂等 Token |
| certIds | List | **是** | 证书 ID 列表，目前仅支持一个 |
| encryptionType | String | 否 | tls_cipher_policy_default / 1_1 / 1_2 / 1_2_secure / userDefind |
| encryptionProtocols | List | 否 | 自定义时：tlsv10, tlsv11, tlsv12 |
| appliedCiphers | String | 否 | 自定义加密套件，冒号分隔 |
| dualAuth | Boolean | 否 | 是否开启双向认证，默认 false |
| clientCertIds | List | 否 | 双向认证时的客户端证书 ID |
| additionalCertDomains | List | 否 | 扩展域名列表，每项含 certId 和 Host |

### UpdateBlbHttpsListener / DescribeBlbHttpsListener

同模式，API 名替换。更新时 certIds、encryptionType 等均为可选。

> **证书依赖说明**：`certIds` / `clientCertIds` 只能引用**已存在的证书 ID**。当前 BCE CLI 顶层服务列表（apm/blb/bls/cfs/cfw/csn/dns/eip/et/pfs/privatezone/snic/vpc）中**没有证书管理服务**，证书的申请、上传、续期、轮换不在本 Skill 能力范围，需用户预先在证书服务/控制台备好 certId。HTTPS 安全基线（加密策略 / mTLS / SNI 多域名）配置流程见 `references/workflows.md` §13。

---

## 7. SSL 监听器

> SSL 监听器提供四层 TLS 终结能力。

### CreateBlbSslListener

```bash
bce blb CreateBlbSslListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --listenerPort 443 \
  --backendPort 8443 \
  --scheduler RoundRobin \
  --certIds '["cert-xxxxx"]' \
  --healthCheckType TCP
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| listenerPort | Integer | **是** | 监听端口 |
| backendPort | Integer | **是** | 后端端口 |
| scheduler | String | **是** | RoundRobin / LeastConnection / Hash |
| certIds | List | **是** | 证书 ID 列表 |
| healthCheckType | String | 否 | 默认 TCP |
| serverTimeout | Integer | 否 | 默认900，范围10-4000 |
| encryptionType | String | 否 | 同 HTTPS |
| encryptionProtocols | List | 否 | 同 HTTPS |
| appliedCiphers | String | 否 | 同 HTTPS |
| dualAuth | Boolean | 否 | 默认 false |
| clientCertIds | List | 否 | 双向认证客户端证书 |

---

## 8. 监听器查询与批量删除

### DescribeBlbListener — 查询 BLB 监听器列表

```bash
bce blb DescribeBlbListener \
  --blbId <blbId> \
  --listenerPort <端口> \
  --pager
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| listenerPort | Integer | 否 | 指定监听端口，不传则查询全部 |
| marker | String | 否 | 分页标记 |
| maxKeys | Integer | 否 | 每页条数，默认1000 |

### DeleteBlbListener — 删除 BLB 监听器

```bash
bce blb DeleteBlbListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --portList '[80, 443]'
```

或按协议类型删除：
```bash
bce blb DeleteBlbListener \
  --blbId <blbId> \
  --clientToken <uuid> \
  --portTypeList '[{"port":80,"type":"TCP"},{"port":443,"type":"HTTPS"}]'
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| clientToken | String | **是** | 幂等 Token |
| portList | List | 否 | 端口号列表（与 portTypeList 至少填一个） |
| portTypeList | List | 否 | 端口+类型列表，支持多协议同名端口 |

> **⚠️ 高风险操作**：删除后该端口上的流量转发立即中断。执行前必须二次确认 profile、region、blbId、端口、协议和影响范围。

---

## 9. 安全组管理

### BindBlbSecurityGroup — 绑定安全组

```bash
bce blb BindBlbSecurityGroup \
  --blbId <blbId> \
  --securityGroupIds '["g-xxx","g-yyy"]'
```

### UnbindBlbSecurityGroup — 解绑安全组

```bash
bce blb UnbindBlbSecurityGroup \
  --blbId <blbId> \
  --securityGroupIds '["g-xxx"]'
```

> **⚠️ 高风险操作**：解绑安全组可能改变访问控制。执行前必须二次确认 profile、region、blbId 和 securityGroupIds。

### DescribeBlbSecurityGroups — 查询已绑定安全组

```bash
bce blb DescribeBlbSecurityGroups --blbId <blbId>
```

### BindBlbEnterpriseSecurityGroup — 绑定企业安全组

```bash
bce blb BindBlbEnterpriseSecurityGroup \
  --blbId <blbId> \
  --enterpriseSecurityGroupIds '["eg-xxx"]'
```

### DescribeBlbEnterpriseSecurityGroups — 查询已绑定企业安全组

```bash
bce blb DescribeBlbEnterpriseSecurityGroups --blbId <blbId>
```

### UnbindBlbEnterpriseSecurityGroup — 解绑企业安全组

```bash
bce blb UnbindBlbEnterpriseSecurityGroup \
  --blbId <blbId> \
  --enterpriseSecurityGroupIds '["eg-xxx"]'
```

> **⚠️ 高风险操作**：解绑企业安全组可能改变访问控制。执行前必须二次确认 profile、region、blbId 和 enterpriseSecurityGroupIds。

---

## 10. ACL 与修改保护

### UpdateBlbAcl — 更新 ACL 开关

```bash
bce blb UpdateBlbAcl --blbId <blbId> --supportAcl <true|false>
```

### UpdateBlbModifyProtection — 修改保护

```bash
bce blb UpdateBlbModifyProtection \
  --blbId <blbId> \
  --allowModify <true|false> \
  --modificationProtectionReason "<原因>"
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| blbId | String | **是** | BLB 实例 ID |
| allowModify | Boolean | **是** | true=允许修改（保护关），false=禁止修改（保护开） |
| modificationProtectionReason | String | 否 | 保护原因 |

---

## 11. 计费管理

### BlbInquiry — 价格查询

```bash
bce blb BlbInquiry \
  --blbType normal \
  --performanceLevel small1 \
  --count 1 \
  --billing '{"paymentTiming":"Prepaid","billingMethod":"BySpec","reservation":{"reservationLength":1}}'
```

| 参数 | 类型 | 说明 |
|------|------|------|
| blbType | String | normal / application / ipv6 / ipv6Application |
| performanceLevel | String | 性能规格 |
| count | Integer | 购买数量，默认1 |
| billing | Object | 计费信息；`paymentTiming=Postpaid` 时需要 `billingMethod`，`paymentTiming=Prepaid` 时需要 `reservation.reservationLength` |

**使用时机**：真实 `CreateBlb` / `CreateAppBlb` / `ResizeBlb` 之前必须先询价并展示费用；dry-run 创建可跳过询价。对于公网 EIP、规格型 BLB、预付费资源，要在确认文案中说明可能产生一次性或持续账单。

典型询价：

```bash
bce blb BlbInquiry --region <region> --blbType normal --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}'
bce blb BlbInquiry --region <region> --blbType application --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"BySpec"}'
bce blb BlbInquiry --region <region> --blbType ipv6Application --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Prepaid","reservation":{"reservationLength":1}}'
```

### RefundBlb — 退款（释放预付费）

```bash
bce blb RefundBlb --blbId <blbId> --clientToken <uuid>
```

### BillingChangePreToPostBlb — 预付费转后付费

```bash
bce blb BillingChangePreToPostBlb --blbId <blbId> --clientToken <uuid>
```

### BillingChangePostToPreBlb — 后付费转预付费

```bash
bce blb BillingChangePostToPreBlb \
  --blbId <blbId> \
  --clientToken <uuid> \
  --performanceLevel small1 \
  --billingMethod BySpec \
  --reservationLength 1
```

### BillingChangeCancelToPostBlb — 取消后付费相关变更

```bash
bce blb BillingChangeCancelToPostBlb --blbId <blbId> --clientToken <uuid>
```

> **⚠️ 高风险计费操作**：退款和计费转换会影响费用与资源生命周期。执行 `RefundBlb`、`BillingChangePreToPostBlb`、`BillingChangePostToPreBlb`、`BillingChangeCancelToPostBlb` 前必须二次确认 profile、region、blbId、计费方式和影响范围。

---

## 12. 服务型能力

> 以下 API 存在于当前 CLI/schema 中，`SKILL.md` 主流程尚未展开；使用前应先结合产品语义确认是否适用于用户场景。

### CreateService — 创建服务

```bash
bce blb CreateService \
  --name <endpoint名称> \
  --serviceName <服务名> \
  --instanceId <blbId> \
  --authList '[{"uid":"*","auth":"allow"}]'
```

### DescribeServices — 查询服务列表

```bash
bce blb DescribeServices --pager
```

### DescribeService — 查询服务详情

```bash
bce blb DescribeService --service <service>
```

### UpdateService — 更新服务

```bash
bce blb UpdateService --service <service> --description "<描述>"
```

### DeleteService — 删除服务

```bash
bce blb DeleteService --service <service> --clientToken <uuid>
```

> **⚠️ 高风险操作**：删除服务会影响服务访问。执行前必须二次确认 profile、region、service 和影响范围。

### AddServiceAuth / UpdateServiceAuth / DeleteServiceAuth — 管理服务授权

```bash
bce blb AddServiceAuth --service <service> --authList '[{"uid":"<uid>","auth":"allow"}]'
bce blb UpdateServiceAuth --service <service> --authList '[{"uid":"<uid>","auth":"deny"}]'
bce blb DeleteServiceAuth --service <service> --action removeAuth --uidList '["<uid>"]'
```

### BindInstanceToService / UnbindInstanceFromService — 绑定或解绑服务实例

```bash
bce blb BindInstanceToService --service <service> --instanceId <blbId> --clientToken <uuid>
bce blb UnbindInstanceFromService --service <service> --clientToken <uuid>
```

> **⚠️ 高风险操作**：解绑实例会影响服务流量入口。执行 `UnbindInstanceFromService` 前必须二次确认 profile、region、service 和影响范围。

---

## 13. LBDC 管理

> 以下 API 存在于当前 CLI/schema 中，是否纳入 BLB Skill 主流程需要结合产品场景确认。

### CreateLbdc — 创建 LBDC

```bash
bce blb CreateLbdc \
  --name <名称> \
  --type <4Layer|7Layer> \
  --ccuCount <CCU数量> \
  --billing '{"paymentTiming":"Prepaid","billingMethod":"BySpec","reservation":{"reservationLength":1}}'
```

### 查询与变更 LBDC

```bash
bce blb DescribeLbdcs
bce blb DescribeLbdc --id <lbdcId>
bce blb DescribeLbdcBlb --id <lbdcId>
bce blb UpdateLbdc --id <lbdcId> --name <新名称>
bce blb RenewLbdc --id <lbdcId> --clientToken <uuid> --billing '{"reservation":{"reservationLength":1}}'
bce blb UpgradeLbdc --id <lbdcId> --ccuCount <新CCU数量> --clientToken <uuid>
```

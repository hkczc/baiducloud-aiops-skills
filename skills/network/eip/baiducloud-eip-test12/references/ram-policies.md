# BLB Skill 复合工作流参考

> 唯一职责：BLB/AppBLB **自身多步操作的分步流程**（创建/HTTPS/扩缩/复制/规格变更/计费转换/重定向/排查），含每步命令示例与安全卡点。
> 不负责：单个 API 参数字典（见 `*-api-reference.md`）、跨服务联动（见 `cross-service.md`）、输出格式（见 `output-format.md`）、多能力编排（见 `orchestration.md`）。
> 执行任何真实查询或写操作前，仍必须先按 `SKILL.md` 确认 BCE CLI、profile/AK（脱敏）、region、目标资源和高风险授权。
> 完整 API 参数请分别查看 `references/blb-api-reference.md` 与 `references/appblb-api-reference.md`；静态参考与当前机器 `"$BCE" ... --help` 不一致时，以实时 help 为准。

---

### 工作流索引

| 编号 | 名称 | 触发话术关键词 | 参考章节 |
|------|------|----------------|----------|
| §1 | 创建完整普通型 BLB | 创建负载均衡、创建 BLB、挂后端 | L1-L8 |
| §2 | 创建完整 AppBLB | 应用型负载均衡、AppBLB、域名转发、路径转发 | L9-L193 |
| §3 | 创建 IPv6 BLB/AppBLB | IPv6 负载均衡、IPv6 AppBLB | L196-L221 |
| §4 | 配置 HTTPS/SSL | HTTPS、绑定证书、TLS 终结 | L224-L246 |
| §5 | 扩缩后端服务器 | 加服务器、扩容、缩容、调整权重、摘除后端 | L249-L272 |
| §6 | 跨 region 复制配置 | 复制到另一个 region、迁移配置、克隆 | L275-L341 |
| §7 | 安全释放工作流（用户参考） | 删除 BLB、释放负载均衡、清理实例 | L369-L398 |
| §8 | 配置 Host/Path 策略 | 按域名转发、按路径转发、uri 转发 | L375-L395 |
| §9 | 询价工作流 | 创建 BLB、买负载均衡、费用、询价 | L398-L419 |
| §10 | 健康异常诊断闭环 | 后端不健康、健康检查失败、502/503、访问不通 | L422-L451 |
| §11 | 故障排查工作流 | 502、访问不通、没流量、证书异常 | L454-L473 |
| §12 | 标签化创建与资源分组 | 创建时打标签、绑定资源组、env/owner 标签 | L476-L503 |
| §13 | HTTPS 安全基线 | TLS 版本、加密套件、mTLS、SNI 多域名 | L505-L559 |
| §14 | 创建后等待就绪（waiter） | 等就绪、轮询状态、等后端健康再继续 | L562-L597 |
| §15 | 后端优雅排空 | 平滑下线、connection draining、先置权重 0 再摘除 | L601-L642 |
| §16 | 规格变更 | 升配、降配、变更规格、扩容 BLB、small1 升 large1 | L643+ |
| §17 | 计费模式转换 | 预付费转后付费、后付费转预付费、退款 | L790+ |
| §18 | HTTP → HTTPS 重定向 | HTTP 跳转 HTTPS、redirectPort、自动跳转 | L850+ |

---

## 1. 创建完整普通型 BLB 服务

**触发话术**：用户说“创建一个负载均衡器”、“创建 BLB”、“把几台 BCC 挂到负载均衡后面”、“创建四层/七层普通型负载均衡”。

**适用文档**：
- 普通型 BLB 实例、监听器、后端、安全组、计费参数：`references/blb-api-reference.md`
- VPC/子网、参数格式、dry-run、高风险规则：`SKILL.md`

**执行流程**：

0. **BlbInquiry 询价**
   - dry-run 创建可跳过询价；真实创建前必须先询价并展示费用。
   - 根据用户选择的类型、规格、数量和计费方式构造询价命令：
   ```bash
   "$BCE" blb BlbInquiry --region <region> --blbType normal --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}'
   "$BCE" blb BlbInquiry --region <region> --blbType normal --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"BySpec"}'
   "$BCE" blb BlbInquiry --region <region> --blbType normal --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Prepaid","reservation":{"reservationLength":1}}'
   ```
   - 展示询价响应、计费模式和可能产生的公网 EIP/规格费用后，等待用户明确确认“我已知悉费用并确认创建”或同义表述。

1. **确认上下文**
   - 确认使用的 profile 或脱敏 AK。
   - 确认 region，并在真实命令中显式追加 `--region <region>`。
   - 确认这是普通型 BLB，不是 AppBLB；不确定时先询问。
   - 创建或测试资源时确认 VPC/subnet；测试固定使用 `vpc-6ikazsm7kxe0` 与 `sbn-bjezmbw9muvm`。

2. **查询并选择 VPC/subnet**
   ```bash
   "$BCE" vpc QueryVpcList --region <region> --pager --output table rows=vpcs cols=vpcId,name,cidr
   "$BCE" vpc QuerySubnetList --region <region> --vpcId <vpcId> --pager --output table rows=subnets cols=subnetId,name,cidr,zoneName
   ```

3. **创建 BLB 实例**
   ```bash
   "$BCE" blb CreateBlb \
     --region <region> \
     --vpcId <vpcId> --subnetId <subnetId> \
     --name "<名称>" \
     --billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}' \
     --dry-run
   ```
   dry-run 通过后，请求用户确认再去掉 `--dry-run` 真实执行。

4. **提取实例信息**
   - 从创建响应中提取 `blbId`、地址、状态。
   - 如未返回完整信息，查询详情：
   ```bash
   "$BCE" blb DescribeBlb --region <region> --blbId <blbId>
   ```

5. **创建后引导并添加后端服务器**
   - 创建成功后先展示 `blbId`、地址、状态、region、VPC/subnet 和计费摘要，并询问是否继续创建监听配置、是否添加后端服务器。
   - 只有用户确认继续添加后端时，才询问后端 BCC 实例 ID、权重、后端端口。
   - 多后端可使用 JSON 或 `--unfold`。
   ```bash
   "$BCE" blb AddBlbServer --unfold \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> \
     --backendServerList instanceId=i-xxx weight=100 \
     --backendServerList instanceId=i-yyy weight=50 \
     --dry-run
   ```

6. **创建监听器**
   - 只有用户确认继续创建监听配置时，才进入监听器创建步骤。
   - TCP/UDP 属于四层；HTTP/HTTPS 属于七层；SSL 是四层 TLS 终结。
   - 普通型 BLB 监听器必须关注 `backendPort`。
   ```bash
   "$BCE" blb CreateBlbHttpListener \
     --region <region> \
     --blbId <blbId> \
     --listenerPort 80 --backendPort 8080 \
     --scheduler LeastConnection \
     --xForwardFor true \
     --dry-run
   ```

7. **验证健康状态**
   ```bash
   "$BCE" blb DescribeBlbServerHealth --region <region> --blbId <blbId> --listenerPort <端口> --pager
   ```

8. **汇总输出**
   - 汇总 profile、region、VPC/subnet、blbId、监听端口、后端服务器、访问地址、健康状态。
   - 如是生产资源，建议创建后开启修改保护。

---

## 2. 创建完整 AppBLB 服务

**触发话术**：用户说“创建应用型负载均衡”、“支持域名转发”、“支持路径转发”、“创建七层高级路由”、“创建 AppBLB”。

**适用文档**：
- AppBLB 实例、服务器组、服务器组端口、监听器、策略、IP 组参数：`references/appblb-api-reference.md`
- 普通 CLI、上下文确认、参数格式：`SKILL.md`

**执行流程**：

0. **BlbInquiry 询价**
   - dry-run 创建可跳过询价；真实创建 AppBLB / IPv6 AppBLB 前必须先询价并展示费用。
   - 按实例类型选择 `--blbType application` 或 `--blbType ipv6Application`：
   ```bash
   "$BCE" blb BlbInquiry --region <region> --blbType application --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}'
   "$BCE" blb BlbInquiry --region <region> --blbType application --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"BySpec"}'
   "$BCE" blb BlbInquiry --region <region> --blbType ipv6Application --performanceLevel small1 --count 1 --billing '{"paymentTiming":"Prepaid","reservation":{"reservationLength":1}}'
   ```
   - 展示询价响应、计费模式和可能产生的公网 EIP/规格费用后，等待用户明确确认“我已知悉费用并确认创建”或同义表述。

1. **确认上下文与类型**
   - 确认这是 AppBLB，而不是普通型 BLB。
   - 确认 profile、region、VPC/subnet、名称、计费方式。
   - AppBLB 创建需要 `clientToken`。

2. **创建 AppBLB 实例**
   ```bash
   "$BCE" blb CreateAppBlb \
     --region <region> \
     --clientToken <uuid> \
     --vpcId <vpcId> --subnetId <subnetId> \
     --name "<名称>" \
     --billing '{"paymentTiming":"Postpaid"}' \
     --dry-run
   ```

3. **创建后引导并创建服务器组**
   - 创建成功后先展示 `blbId`、地址、状态、region、VPC/subnet 和计费摘要，并询问是否继续创建监听配置、是否创建服务器组并添加后端、是否配置转发策略。
   - 只有用户确认继续创建服务器组时，才执行本步骤。
   ```bash
   "$BCE" blb CreateAppBlbServerGroup \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> \
     --name "web-server-group" \
     --dry-run
   ```

4. **添加后端到服务器组**
   ```bash
   "$BCE" blb AddAppBlbServerGroupRs \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> --sgId <sgId> \
     --backendServerList '[{"instanceId":"i-xxx","weight":100}]' \
     --dry-run
   ```

5. **创建服务器组端口并配置健康检查**
   - AppBLB 的后端端口和健康检查在服务器组端口上配置，不在监听器上配置。
   ```bash
   "$BCE" blb CreateAppBlbServerGroupPort \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> \
     --sgId <sgId> --port 8080 --type http \
     --enableHealthCheck true --healthCheck http --healthCheckUrlPath "/health" \
     --dry-run
   ```

6. **创建 AppBLB 监听器**
   - 只有用户确认继续创建监听配置时，才进入监听器创建步骤。
   - AppBLB 监听器没有 `backendPort`。
   - AppBLB HTTP/HTTPS 真实 IP 参数是 `--xForwardedFor`。
   ```bash
   "$BCE" blb CreateAppBlbHttpListener \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> \
     --listenerPort 80 --scheduler LeastConnection \
     --xForwardedFor true \
     --dry-run
   ```

7. **创建转发策略**
   - 只有用户确认继续创建 Host/Path 策略或 IP 组策略时，才进入策略创建步骤。
   - Host/Path 策略结构较深，复杂场景优先使用 `--generate-cli-skeleton` 和 `--cli-input-json file://...`。
   ```bash
   "$BCE" blb CreateAppBlbPolicy \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> --listenerPort 80 \
     --appPolicyVos '[{"appServerGroupId":"<sgId>","priority":1,"ruleList":[{"key":"Host","value":"www.example.com"}]}]' \
     --dry-run
   ```

8. **验证**
   ```bash
   "$BCE" blb DescribeAppBlb --region <region> --blbId <blbId>
   "$BCE" blb DescribeAppBlbServerGroup --region <region> --blbId <blbId> --pager
   "$BCE" blb DescribeAppBlbPolicy --region <region> --blbId <blbId> --port 80 --pager
   ```

---

## 3. 创建 IPv6 BLB / IPv6 AppBLB

**触发话术**：用户说“创建 IPv6 负载均衡”、“需要 IPv6 BLB”、“创建 IPv6 AppBLB”。

**关键区分**：

| 类型 | 创建命令 | 查询限制 |
|------|----------|----------|
| 普通型 IPv6 BLB | `CreateBlb --type ipv6` | `DescribeBlbs --type ipv6` |
| 应用型 IPv6 AppBLB | `CreateAppBlb --type ipv6Application` | `DescribeAppBlbs` 当前不能加 `--type ipv6Application` |

**IPv6 AppBLB 创建要求**：

```bash
"$BCE" blb CreateAppBlb \
  --region <region> \
  --type ipv6Application \
  --clientToken <uuid> \
  --vpcId <vpcId> --subnetId <subnetId> \
  --name "<名称>" \
  --billing '{"paymentTiming":"Postpaid"}' \
  --dry-run
```

执行真实创建前，必须确认 dry-run 请求体中包含 `"type":"ipv6Application"` 或等价字段。

---

## 4. 配置 HTTPS / SSL

**触发话术**：用户说“配置 HTTPS”、“绑定证书”、“开通 SSL”、“TLS 终结”。

**流程**：

1. 确认负载均衡类型：普通型 BLB 或 AppBLB。
2. 确认 `blbId`、region、证书 ID、监听端口、后端端口或服务器组端口。
3. 普通型 BLB HTTPS 监听器需要 `backendPort` 和 `certIds`：
   ```bash
   "$BCE" blb CreateBlbHttpsListener \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> \
     --listenerPort 443 --backendPort 8080 \
     --scheduler LeastConnection \
     --certIds '["cert-xxxxx"]' \
     --encryptionType tls_cipher_policy_1_2 \
     --dry-run
   ```
4. AppBLB HTTPS 监听器没有 `backendPort`；后端端口在服务器组端口中配置。
5. 如用户需要 HTTP → HTTPS 重定向，先查对应 API help 确认重定向参数，再 dry-run。
6. 创建后查询监听器和访问状态。

---

## 5. 扩缩后端服务器或调整权重

**触发话术**：用户说“加服务器”、“扩容”、“缩容”、“调整权重”、“摘除后端”。

**普通型 BLB**：

1. 查询当前后端：
   ```bash
   "$BCE" blb DescribeBlbServers --region <region> --blbId <blbId> --pager
   ```
2. 添加后端：`AddBlbServer`。
3. 更新权重：`UpdateBlbServer`。
4. 移除后端：`DeleteBlbServer`，属于高风险操作，必须确认影响范围。
5. 验证健康状态：`DescribeBlbServerHealth`。

**AppBLB**：

1. 查询服务器组：`DescribeAppBlbServerGroup`。
2. 查询服务器组后端：`DescribeAppBlbServerGroupRs`。
3. 添加后端：`AddAppBlbServerGroupRs`。
4. 更新后端：`UpdateAppBlbServerGroupRs`。
5. 移除后端：`DeleteAppBlbServerGroupRs`，属于高风险操作。
6. 查询服务器组端口和健康检查配置。

---

## 6. 跨 region 复制 BLB 配置

**触发话术**：用户说“把这个 BLB 复制到另一个 region”、“迁移负载均衡配置”、“在广州创建一个和北京一样的 BLB”、“跨地域克隆 AppBLB 配置”。

**核心原则**：跨 region 复制是“业务配置等价重建”，不是资源 ID 原样迁移。`blbId`、`sgId`、`policyId`、`portId`、`memberId`、`clientToken` 等运行时 ID 不复制；目标 region 的 VPC/subnet、后端实例、证书、安全组、EIP、资源组必须重新映射。

### 6.1 复制范围

| 分类 | 可复制/重建 | 需要目标 region 重新映射 | 不复制 |
|---|---|---|---|
| 实例基础 | 类型、名称、描述、规格、计费模式、标签、修改保护、删除保护 | VPC、子网、私网 IP、EIP、资源组 | blbId、创建时间、状态、健康状态、监控/流量统计 |
| 普通型监听器 | 协议、listenerPort、backendPort、调度算法、会话保持、超时、真实 IP、健康检查、证书参数 | 证书 ID、安全组 ID、后端 BCC ID | 运行时健康状态 |
| 普通型后端 | 后端权重、后端端口由监听器承载 | BCC instanceId 必须映射为目标 region 实例 | 源 region BCC ID |
| AppBLB 服务器组 | 组名、描述、RS 权重、服务器组端口、健康检查配置 | BCC instanceId、非 BCC IP、端口可达性 | sgId、portId |
| AppBLB 策略/IP 组 | Policy priority、desc、ruleList、目标组关系、IP 组成员和协议配置 | 新建后的 sgId/ipGroupId/memberId/protocolId、证书 ID | policyId、memberId、protocolId |
| 安全配置 | ACL 开关、绑定安全组/企业安全组的意图 | 目标 region 等价安全组/企业安全组 ID | 源 region 安全组 ID |

### 6.2 源配置采集

**普通型 / 普通型 IPv6 BLB**：

```bash
"$BCE" blb DescribeBlb --region <sourceRegion> --blbId <sourceBlbId> [--type ipv6]
"$BCE" blb DescribeBlbListener --region <sourceRegion> --blbId <sourceBlbId> --pager
"$BCE" blb DescribeBlbServers --region <sourceRegion> --blbId <sourceBlbId> --pager
"$BCE" blb DescribeBlbSecurityGroups --region <sourceRegion> --blbId <sourceBlbId>
"$BCE" blb DescribeBlbEnterpriseSecurityGroups --region <sourceRegion> --blbId <sourceBlbId>
```

如需协议级完整监听器参数，再按返回协议/端口逐个查询：`DescribeBlbTcpListener`、`DescribeBlbUdpListener`、`DescribeBlbHttpListener`、`DescribeBlbHttpsListener`、`DescribeBlbSslListener`。

**AppBLB / AppBLB IPv6**：

```bash
"$BCE" blb DescribeAppBlb --region <sourceRegion> --blbId <sourceBlbId>
"$BCE" blb DescribeAppBlbListener --region <sourceRegion> --blbId <sourceBlbId> --pager
"$BCE" blb DescribeAppBlbServerGroup --region <sourceRegion> --blbId <sourceBlbId> --pager
"$BCE" blb DescribeAppBlbServerGroupRs --region <sourceRegion> --blbId <sourceBlbId> --sgId <sourceSgId> --pager
"$BCE" blb DescribeAppBlbPolicy --region <sourceRegion> --blbId <sourceBlbId> --port <port> --type <type> --pager
"$BCE" blb DescribeAppBlbIpGroup --region <sourceRegion> --blbId <sourceBlbId> --pager
"$BCE" blb DescribeAppBlbIpGroupMember --region <sourceRegion> --blbId <sourceBlbId> --ipGroupId <sourceIpGroupId> --pager
```

如需协议级完整监听器参数，再按返回协议/端口逐个查询：`DescribeAppBlbTcpListener`、`DescribeAppBlbUdpListener`、`DescribeAppBlbHttpListener`、`DescribeAppBlbHttpsListener`、`DescribeAppBlbSslListener`。

### 6.3 目标映射确认

在生成目标命令前必须向用户确认：

1. 目标 `region`、profile/AK（脱敏）、VPC、subnet。
2. 是否复用名称/描述；如复用名称可能冲突，建议追加目标 region 后缀。
3. 目标后端实例映射：`源 instanceId -> 目标 instanceId`；没有映射的后端不得自动跳过，必须让用户决定。
4. 证书映射：HTTPS/SSL 监听器中的源证书 ID 必须映射到目标 region 证书 ID。
5. 安全组/企业安全组映射：源 groupId 不能跨 region 复用。
6. EIP 处理方式：不绑定、绑定目标 region 已有 EIP，或让用户先创建/提供 EIP。
7. 计费方式和规格是否保持一致；真实创建前必须走 `BlbInquiry`。

### 6.4 目标重建顺序

1. **询价**：按目标类型运行 `BlbInquiry`，展示费用并等待用户确认。
2. **创建实例**：普通型用 `CreateBlb`；AppBLB 用 `CreateAppBlb`；目标 `vpcId/subnetId/address/eip/resourceGroupId` 使用用户确认后的映射值。
3. **普通型重建**：先 `AddBlbServer` 绑定映射后的后端，再按源监听器协议逐个 `CreateBlb*Listener`，最后绑定安全组/企业安全组、ACL、修改保护。
4. **AppBLB 重建**：先 `CreateAppBlbServerGroup`，记录新 `sgId` 映射；再 `AddAppBlbServerGroupRs`、`CreateAppBlbServerGroupPort`、`CreateAppBlbIpGroup`/`CreateAppBlbIpGroupMember`/`CreateAppBlbIpGroupProtocol`、`CreateAppBlb*Listener`、`CreateAppBlbPolicy`；Policy 中的源 `appServerGroupId`/`appIpGroupId` 必须替换成新 ID。
5. **验证差异**：查询目标实例、监听器、后端、策略、安全组，输出源/目标配置差异；不比较运行时 ID、创建时间、健康状态、监控数据。

所有目标 region 写操作先 `--dry-run`；涉及真实创建、绑定、删除、修改策略、修改健康检查时按 `SKILL.md` 的高风险/付费确认规则执行。

---

## 7. 安全释放工作流（仅供用户参考，Agent 不得执行其中任何步骤）

> **重要限制**：根据 `SKILL.md` §11.1，Agent 禁止执行、dry-run 或生成可直接执行的 `ReleaseBlb` / `ReleaseAppBlb` 命令。以下完整流程仅供用户自行操作 BLB 释放时参考，Agent 只负责执行 §11.1 定义的只读闲置评估。

**触发话术**：用户说"删除 BLB"、"释放负载均衡"、"删掉 AppBLB"、"清理这个负载均衡实例"。

**核心原则**：先按 `SKILL.md` §11.1 查询依赖并判断是否闲置，再决定是直接进入释放确认，还是提示非闲置依赖并二次确认。

**普通型 / 普通型 IPv6 BLB**：

1. 查询监听器和后端：
   ```bash
   "$BCE" blb DescribeBlbListener --region <region> --blbId <blbId> --pager
   "$BCE" blb DescribeBlbServers --region <region> --blbId <blbId> --pager
   ```
2. 若无监听或无后端，视为闲置；展示摘要后执行或展示 `ReleaseBlb --dry-run`。
3. 若监听和后端都存在，展示端口、后端实例列表和清依赖建议，询问用户是先清依赖还是仍确认释放。

**AppBLB / AppBLB IPv6**：

1. 查询监听器、服务器组、服务器组后端和策略：
   ```bash
   "$BCE" blb DescribeAppBlbListener --region <region> --blbId <blbId> --pager
   "$BCE" blb DescribeAppBlbServerGroup --region <region> --blbId <blbId> --pager
   "$BCE" blb DescribeAppBlbServerGroupRs --region <region> --blbId <blbId> --sgId <sgId> --pager
   "$BCE" blb DescribeAppBlbPolicy --region <region> --blbId <blbId> --port <port> --type <type> --pager
   ```
2. 若无监听、或所有服务器组无后端、或所有监听无可用策略/默认服务器组为空，视为闲置；展示摘要后执行或展示 `ReleaseAppBlb --dry-run`。
3. 若仍有监听、后端和策略，展示完整依赖摘要和清依赖建议，询问用户是先清依赖还是仍确认释放。
4. 用户确认仍释放非闲置实例时，再次复核 profile、region、blbId、依赖范围和不可恢复影响，然后真实释放。

---

## 8. 配置 Host / Path 转发策略

**触发话术**：用户说“按域名转发”、“按路径转发”、“/api 转到一组服务器”、“www 域名转发到 web 组”。

**适用范围**：AppBLB 专属能力，普通型 BLB 不支持 Host/Path 策略路由。

**流程**：

1. 确认 AppBLB 实例、监听端口、目标服务器组。
2. 查询现有策略，避免 priority 冲突：
   ```bash
   "$BCE" blb DescribeAppBlbPolicy --region <region> --blbId <blbId> --port <listenerPort> --pager
   ```
3. 规划规则：Host、Path、优先级、目标服务器组。
4. 简单策略可用 JSON 字符串；复杂策略优先 skeleton：
   ```bash
   "$BCE" blb CreateAppBlbPolicy --generate-cli-skeleton
   "$BCE" blb CreateAppBlbPolicy --cli-input-json file://params.json --dry-run
   ```
5. 策略变更会影响流量分发，真实执行前必须确认影响范围。

---

## 9. 询价工作流

**触发话术**：用户说“创建 BLB/AppBLB”、“买一个负载均衡”、“需要公网负载均衡”、“变更规格”且即将真实执行。

| 输入信息 | 对应 CLI 参数 |
|---|---|
| 普通型 BLB | `--blbType normal` |
| AppBLB | `--blbType application` |
| 普通型 IPv6 BLB | `--blbType ipv6` |
| AppBLB IPv6 | `--blbType ipv6Application` |
| 规格 | `--performanceLevel small1..large3` |
| 后付费按量 | `--billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}'` |
| 后付费按规格 | `--billing '{"paymentTiming":"Postpaid","billingMethod":"BySpec"}'` |
| 预付费 | `--billing '{"paymentTiming":"Prepaid","reservation":{"reservationLength":<月数>}}'` |

执行顺序：

1. dry-run 创建只需提醒“dry-run 不实际产生费用”，可跳过询价。
2. 真实创建前先执行 `BlbInquiry`，按 `references/output-format.md` §5 费用摘要模板展示询价结果、计费方式、购买数量、region、规格和可能产生的公网 EIP/规格费用（金额原样不换算）。
3. 等待用户明确确认“我已知悉费用并确认创建”或同义表述。
4. 确认后才继续创建命令的 dry-run / 真实执行链路。

---

## 10. 健康异常诊断闭环

**触发话术**：用户说“后端不健康”、“健康检查失败”、“502/503”、“访问不通”、“部分机器没流量”。

**固定流程**：取实例 → 取监听端口或服务器组 → 查询健康/RS 状态 → 归因 → 给建议命令 → 等用户确认是否变更。健康/链路结果按 `references/output-format.md` §3/§4 固定模板输出。

| 现象 | 可能根因 | 建议命令 |
|---|---|---|
| 普通型单端口后端不健康 | listenerPort 对应健康检查路径/端口与后端服务不一致 | `DescribeBlbListener --blbId <id> --listenerPort <port>`；必要时建议 `UpdateBlbHttpListener` / `UpdateBlbTcpListener` dry-run |
| 普通型全部后端不健康 | 安全组/ACL 未放通或健康检查端口错误 | `DescribeBlbSecurityGroups --blbId <id>`、`DescribeBlbEnterpriseSecurityGroups --blbId <id>`、`DescribeBlbServerHealth --listenerPort <port>` |
| AppBLB 某服务器组异常 | 服务器组端口健康检查配置或后端服务异常 | `DescribeAppBlbServerGroup --blbId <id>`、`DescribeAppBlbServerGroupRs --blbId <id> --sgId <sgId>` |
| AppBLB 路径/域名访问异常 | Policy Host/Path、priority 或目标组错误 | `DescribeAppBlbPolicy --blbId <id> --port <port> --type <type>` |
| 仅部分后端异常 | 单机服务进程、端口或权重配置问题 | 建议 `UpdateBlbServer` / `UpdateAppBlbServerGroupRs` 把异常节点权重置 0 后排查 |

普通型健康查询：

```bash
"$BCE" blb DescribeBlbListener --region <region> --blbId <blbId> --pager
"$BCE" blb DescribeBlbServerHealth --region <region> --blbId <blbId> --listenerPort <port> --pager
```

AppBLB 健康诊断：

```bash
"$BCE" blb DescribeAppBlbServerGroup --region <region> --blbId <blbId> --pager
"$BCE" blb DescribeAppBlbServerGroupRs --region <region> --blbId <blbId> --sgId <sgId> --pager
```

当前 CLI 无独立 AppBLB 健康 API；使用 `DescribeAppBlbServerGroupRs` 返回中的 `portList[].status` 判断后端端口健康。

---

## 11. 故障排查工作流

**触发话术**：用户说“后端不健康”、“502”、“访问不通”、“负载均衡没流量”、“证书异常”。

**排查闭环**：先确认 profile、region、blbId 和类型；再按现象选择查询命令；最后只给建议命令或 dry-run，等待用户确认后才变更。

**分层诊断顺序**：① 先查 BLB 自身（实例拓扑 `output-format.md` §1.5、健康 §10、安全组）→ ② BLB 自身查不到根因时，再联动跨服务（公网 EIP·DDoS、安全组规则），详见 `references/cross-service.md` → ③ 运行时监控指标（带宽/连接数/QPS/七层状态码）、访问日志明细、云防火墙/风控 **CLI 不支持**，标注「需控制台」，不编造结论（见 `cross-service.md` §4）。

| 现象 | 可能根因 | 建议命令 |
|---|---|---|
| `ResourceNotFound` / 404 | region、实例 ID 或实例类型不匹配 | `DescribeBlbs --blbId <id>`、`DescribeAppBlbs --blbId <id>`，IPv6 普通型补 `--type ipv6` |
| 访问不通但实例可见 | 监听器未配置、端口错误或安全组未放通 | `DescribeBlbListener --blbId <id> --pager` / `DescribeAppBlbListener --blbId <id> --pager`、`DescribeBlbSecurityGroups --blbId <id>`，安全组规则联动 `cross-service.md` §2.1 |
| 后端不健康 | 健康检查路径/Host/端口错误或服务进程异常 | 转到本文 §10 健康异常诊断闭环 |
| HTTP 502/503 | 后端超时、健康检查失败、策略目标组为空 | 普通型查 `DescribeBlbServerHealth`；AppBLB 查 `DescribeAppBlbPolicy` + `DescribeAppBlbServerGroupRs`；后端正常仍 5xx 时，状态码分布/访问日志 CLI 不可查，标注「需控制台」（`cross-service.md` §4） |
| 访问慢/丢包/超时但后端健康 | 带宽限速、连接数接近上限 | 带宽/连接数等运行时指标 CLI 不支持，标注「需控制台」（BLB 监控控制台，见 `cross-service.md` §4）；可先排查安全组与后端配置 |
| 公网不通但内网正常/疑似攻击 | EIP 未绑定、带宽打满、DDoS | 联动 `cross-service.md` §2.2：`eip QueryEipList` + `eip ListBaseDdos` |
| HTTPS/SSL 证书异常 | 证书 ID、加密套件、双向认证配置错误 | `DescribeBlbHttpsListener` / `DescribeAppBlbHttpsListener` / `DescribeBlbSslListener` / `DescribeAppBlbSslListener` |
| AppBLB Host/Path 不生效 | priority 冲突、Host/Path 规则错误或目标组端口不匹配 | `DescribeAppBlbPolicy --blbId <id> --port <port> --type <type>`、`DescribeAppBlbServerGroupRs --sgId <sgId>` |
| 命令失败或参数报错 | API 名、flag 或 JSON 结构与当前 CLI 不一致 | 转到 `references/troubleshooting.md`，按 help/skeleton/dry-run 闭环修正 |

---

## 12. 标签化创建与资源分组

**触发话术**：用户说“创建时打标签”、“按标签归类”、“绑定资源组”、“给负载均衡加 env/owner 标签”。

**能力依据（CLI 实测）**：`CreateBlb` 支持 `--tags`（`tagKey`/`tagValue` 列表）与 `--resourceGroupId`，可在创建实例时同时打标签、归入资源组。

**已知限制**：当前 `DescribeBlbs` 没有按 tag 过滤的参数（仅 `address`/`name`/`blbId`/`bccId`/`exactlyMatch`/`type`），标签只用于创建/归集和控制台/计费侧识别，**不能用 CLI 按 tag 反查实例**。不要拼接不存在的 tag 过滤参数；如需按标签筛选，先 `DescribeBlbs` 取全量再用 `--query` 在响应字段上过滤（以返回结构为准）。

**流程**：

1. 确认 profile、region、VPC/subnet，以及要打的标签键值对和目标资源组 ID（如有）。
2. 真实创建前先 `BlbInquiry` 询价并等待确认（同 §1/§9）。
3. 创建时附加 `--tags` 与 `--resourceGroupId`：
   ```bash
   "$BCE" blb CreateBlb \
     --region <region> \
     --vpcId <vpcId> --subnetId <subnetId> \
     --name "<名称>" \
     --tags '[{"tagKey":"env","tagValue":"prod"},{"tagKey":"owner","tagValue":"team-a"}]' \
     --resourceGroupId <resourceGroupId> \
     --billing '{"paymentTiming":"Postpaid","billingMethod":"ByCapacityUnit"}' \
     --dry-run
   ```
   - List 参数也可用 `--unfold` 重复传：`--tags tagKey=env tagValue=prod`（每个 `--tags` 是一个元素）。
4. dry-run 通过后请求用户确认再去掉 `--dry-run` 真实执行。
5. 创建成功后按 `SKILL.md` §7.7 输出实例摘要，并在摘要中列出已绑定的标签与资源组。

---

## 13. HTTPS 安全基线（加密策略 / 双向认证 / SNI 多域名）

**触发话术**：用户说“收紧 TLS 版本”、“只允许 TLS1.2”、“配置加密套件”、“开双向认证 mTLS”、“一个监听器挂多个域名证书”、“配置 SNI”。

**能力依据（CLI 实测）**：

- 普通型 `CreateBlbHttpsListener` 与应用型 `CreateAppBlbHttpsListener` 均支持：
  - `--certIds`（必填，服务端证书，当前仅取一个）
  - `--encryptionType`：`tls_cipher_policy_default` / `tls_cipher_policy_1_1` / `tls_cipher_policy_1_2` / `tls_cipher_policy_1_2_secure` / `userDefind`
  - `--encryptionProtocols`：当 `encryptionType=userDefind` 时，由 `tlsv10`/`tlsv11`/`tlsv12` 组合
  - `--appliedCiphers`：自定义密码套件，多个用冒号 `:` 分隔
  - `--dualAuth`（开启双向认证）+ `--clientCertIds`（mTLS 客户端证书链，当前仅取一个）
  - `--additionalCertDomains`（扩展域名 SNI，元素含 `certId`/`Host`）

**已知限制（产品/CLI 边界，须如实告知用户）**：此 CLI **无证书管理服务**（顶层 service 仅 apm/blb/bls/cfs/cfw/csn/dns/eip/et/pfs/privatezone/snic/vpc），`--certIds` / `--clientCertIds` 只能引用**已存在的证书 ID**。证书的申请、上传、续期、轮换不在本 Skill 能力范围，需用户预先在证书服务/控制台备好 certId。

**流程**：

1. 确认负载均衡类型（普通型 BLB / AppBLB）、`blbId`、region、监听端口。
2. 确认已存在的服务端 certId；如需 mTLS 还要确认客户端 certId；如多域名需确认每个 `Host` 对应的 certId。
3. 普通型 HTTPS 安全基线（含 mTLS 与 SNI）：
   ```bash
   "$BCE" blb CreateBlbHttpsListener \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> \
     --listenerPort 443 --backendPort 8080 \
     --scheduler LeastConnection \
     --certIds '["cert-xxxxx"]' \
     --encryptionType tls_cipher_policy_1_2 \
     --dualAuth true --clientCertIds '["cert-client-yyyyy"]' \
     --additionalCertDomains '[{"certId":"cert-zzzzz","Host":"api.example.com"}]' \
     --dry-run
   ```
4. 应用型 HTTPS（无 `backendPort`，后端端口在服务器组端口配置）：
   ```bash
   "$BCE" blb CreateAppBlbHttpsListener \
     --region <region> \
     --blbId <blbId> --clientToken <uuid> \
     --listenerPort 443 --scheduler LeastConnection \
     --certIds '["cert-xxxxx"]' \
     --encryptionType tls_cipher_policy_1_2_secure \
     --dualAuth true --clientCertIds '["cert-client-yyyyy"]' \
     --additionalCertDomains '[{"certId":"cert-zzzzz","Host":"api.example.com"}]' \
     --dry-run
   ```
5. 自定义协议/套件示例（`userDefind`）：
   ```bash
   "$BCE" blb CreateBlbHttpsListener ... \
     --encryptionType userDefind \
     --encryptionProtocols '["tlsv11","tlsv12"]' \
     --appliedCiphers "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384" \
     --dry-run
   ```
6. 修改加密策略/证书属于流量影响变更，按 `SKILL.md` §11.2 高风险流程二次确认；变更已有监听器用对应 `UpdateBlbHttpsListener` / `UpdateAppBlbHttpsListener`（以实时 help 为准）。

---

## 14. 创建后等待就绪 / 健康（waiter 轮询）

**触发话术**：用户说“等它创建好”、“等实例 available”、“等后端都健康再继续”、“轮询状态”。

**能力依据（CLI 实测）**：BCE CLI **没有内置 waiter**，但可用 `DescribeBlb` / `DescribeAppBlb`（实例 `status`）、`DescribeBlbServerHealth`（普通型按 `--listenerPort`，支持 `--marker`/`--maxKeys` 分页）、`DescribeAppBlbServerGroupRs`（AppBLB 取 `portList[].status`）配合 `--query`(JMESPath)、`--output table` 自行实现轮询。轮询是只读操作，无需高风险确认。

**实例就绪轮询（普通型）**：

```bash
# 取实例状态；available 视为就绪
"$BCE" blb DescribeBlb --region <region> --blbId <blbId> --query 'status' --output text
```

建议轮询节奏：固定间隔（如 5s）重复查询，直到 `status=available` 或达到最大重试次数；超时则停止并向用户报告最后状态，不无限轮询。

**实例就绪轮询（AppBLB）**：

```bash
"$BCE" blb DescribeAppBlb --region <region> --blbId <blbId> --query 'status' --output text
```

**后端健康轮询（普通型）**：

```bash
"$BCE" blb DescribeBlbServerHealth --region <region> --blbId <blbId> --listenerPort <port> --pager \
  --query 'backendServerList[].status' --output text
```

**后端健康轮询（AppBLB，无独立健康 API）**：

```bash
"$BCE" blb DescribeAppBlbServerGroupRs --region <region> --blbId <blbId> --sgId <sgId> --pager \
  --query 'backendServerList[].portList[].status' --output text
```

> 字段名以实时 `--help` / 实际响应为准；轮询逻辑（间隔、最大次数、超时退出）由 Agent 在调用侧控制，不写死到 CLI。

---

## 15. 后端优雅排空（先置权重 0 再摘除）

**触发话术**：用户说“平滑下线后端”、“先不打流量再摘机器”、“优雅摘除”、“connection draining”。

**能力依据（CLI 实测）**：BCE CLI **没有原生 connection draining 参数**。可用 `UpdateBlbServer` / `UpdateAppBlbServerGroupRs` 的 `weight`（范围 0-100，0=不转发新流量）做替代方案：先把目标后端权重置 0 停止新连接，观察一段时间待存量连接自然结束，再摘除后端。

**已知限制**：`weight=0` 只停止新流量分发，**不主动断开已建立的长连接**；CLI 也没有"活动连接数"查询接口，排空观察窗口需人工设定。这是替代方案，不是产品级优雅排空。

**普通型 BLB 流程**：

1. 查询当前后端，确认目标 instanceId：
   ```bash
   "$BCE" blb DescribeBlbServers --region <region> --blbId <blbId> --pager
   ```
2. 将目标后端权重置 0（流量影响变更，先 dry-run 再确认）：
   ```bash
   "$BCE" blb UpdateBlbServer --unfold \
     --region <region> --blbId <blbId> --clientToken <uuid> \
     --backendServerList instanceId=i-xxx weight=0 \
     --dry-run
   ```
3. 等待人工设定的排空窗口（让存量连接结束）；期间可按 §14 轮询健康/状态观察。
4. 窗口结束后再摘除后端（高风险，按 §11.3 删除前在用后端检查与二次确认）：
   ```bash
   "$BCE" blb DeleteBlbServer --region <region> --blbId <blbId> --clientToken <uuid> --backendServerList '["i-xxx"]'
   ```
   > `DeleteBlbServer` 具体参数以 `--help` 为准。

**AppBLB 流程**：

1. 查询服务器组后端：
   ```bash
   "$BCE" blb DescribeAppBlbServerGroupRs --region <region> --blbId <blbId> --sgId <sgId> --pager
   ```
2. 将目标 RS 权重置 0：
   ```bash
   "$BCE" blb UpdateAppBlbServerGroupRs \
     --region <region> --blbId <blbId> --clientToken <uuid> --sgId <sgId> \
     --backendServerList '[{"instanceId":"i-xxx","weight":0}]' \
     --dry-run
   ```
3. 等待排空窗口后，再 `DeleteAppBlbServerGroupRs` 摘除（高风险，按 §11.3 与 §11.2 确认）。

---

## 16. 规格变更（ResizeBlb）

**触发话术**：用户说"升配"、"降配"、"变更规格"、"扩容 BLB"、"small1 升 large1"、"把规格调大"。

**适用文档**：
- `ResizeBlb` API 参数：`references/blb-api-reference.md` §1（实例管理）
- 询价与费用差价：`references/cost.md`、`references/output-format.md` §5

**执行流程**：

0. **确认上下文与当前规格**
   - 确认 profile、region、blbId、实例类型（普通型/AppBLB）。
   - 查询当前实例信息，获取当前 `performanceLevel` 和计费方式：
   ```bash
   "$BCE" blb DescribeBlb --region <region> --blbId <blbId>
   # AppBLB:
   "$BCE" blb DescribeAppBlb --region <region> --blbId <blbId>
   ```

1. **询价（差价预估）**
   - 使用 `BlbInquiry` 分别对当前规格和目标规格询价，展示差价：
   ```bash
   # 当前规格询价（作为基准）
   "$BCE" blb BlbInquiry --region <region> --blbType <blbType> --performanceLevel <当前规格> --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"BySpec"}'
   # 目标规格询价
   "$BCE" blb BlbInquiry --region <region> --blbType <blbType> --performanceLevel <目标规格> --count 1 --billing '{"paymentTiming":"Postpaid","billingMethod":"BySpec"}'
   ```
   - 按 `output-format.md` §5 模板展示两个询价结果，标明差价。
   - 等待用户明确确认规格变更及费用影响。

2. **规格变更 dry-run**
   ```bash
   "$BCE" blb ResizeBlb \
     --region <region> \
     --blbId <blbId> \
     --clientToken <uuid> \
     --performanceLevel <目标规格> \
     --dry-run
   ```
   - AppBLB 规格变更使用相同 `ResizeBlb` 命令（与普通型共用，以实时 `--help` 为准）。

3. **确认并执行**
   - dry-run 通过后，展示变更摘要（profile、region、blbId、当前规格 → 目标规格、费用变化），请求用户确认。
   - 确认后去掉 `--dry-run` 真实执行。

4. **验证**
   ```bash
   "$BCE" blb DescribeBlb --region <region> --blbId <blbId>
   ```
   - 确认 `performanceLevel` 已变更为目标规格。
   - 输出变更结果摘要。

> **注意**：规格变更属于流量影响变更（`SKILL.md` §11.2 高风险操作），必须二次确认。降配可能导致容量不足；变更后的带宽/连接数等运行时指标 CLI 不支持查询，需在 BLB 监控控制台观察（见 `cross-service.md` §4）。

---

## 17. 计费模式转换

**触发话术**：用户说"预付费转后付费"、"后付费转预付费"、"退款"、"变更计费方式"、"按量转按规格"、"取消续费"。

**适用文档**：
- 计费 API 参数：`references/blb-api-reference.md` §11（计费管理）
- 高风险确认：`SKILL.md` §11.2

**支持的转换方向**：

| 转换方向 | CLI 命令 | 说明 |
|----------|----------|------|
| 预付费 → 后付费 | `BillingChangePreToPostBlb` | 即时生效，预付费剩余时长按退费规则处理 |
| 后付费 → 预付费 | `BillingChangePostToPreBlb` | 需指定新规格、计费方式和时长 |
| 退款（释放预付费） | `RefundBlb` | 退还预付费剩余金额，资源释放 |
| 取消后付费相关变更 | `BillingChangeCancelToPostBlb` | 取消进行中的计费变更 |

**执行流程**：

1. **确认上下文**
   - 确认 profile、region、blbId、实例类型。
   - 查询当前计费信息：
   ```bash
   "$BCE" blb DescribeBlb --region <region> --blbId <blbId>
   ```

2. **说明影响并二次确认**
   - 展示当前计费方式（`paymentTiming` / `billingMethod`）。
   - 说明目标计费方式的影响：
     - **预付费 → 后付费**：预付费剩余时长将按退费规则处理，转后即按后付费计费。
     - **后付费 → 预付费**：将产生新的预付订单，需确认规格、计费方式和购买时长。
     - **退款**：资源将被释放，预付费剩余金额退还，**此操作不可逆**。
   - 展示 profile、region、blbId、当前计费 → 目标计费，等待用户二次确认。

3. **后付费转预付费：先询价**
   - `BillingChangePostToPreBlb` 需要指定 `performanceLevel`、`billingMethod`、`reservationLength`，执行前先 `BlbInquiry` 展示费用。

4. **执行 dry-run**
   ```bash
   # 预付费 → 后付费
   "$BCE" blb BillingChangePreToPostBlb \
     --region <region> --blbId <blbId> --clientToken <uuid> --dry-run
   # 后付费 → 预付费
   "$BCE" blb BillingChangePostToPreBlb \
     --region <region> --blbId <blbId> --clientToken <uuid> \
     --performanceLevel <规格> --billingMethod <BySpec|ByCapacityUnit> --reservationLength <月数> \
     --dry-run
   # 退款
   "$BCE" blb RefundBlb --region <region> --blbId <blbId> --clientToken <uuid> --dry-run
   ```

5. **确认并真实执行**
   - dry-run 通过后再次展示影响范围，请求用户最终确认。
   - 确认后去掉 `--dry-run` 执行。

6. **验证**
   - 查询实例确认计费方式已变更。
   - 输出变更结果摘要。

> **⚠️ 高风险**：所有计费转换操作均为高风险（`SKILL.md` §11.2），必须二次确认 profile、region、blbId 和计费影响。`RefundBlb` 会释放资源，不可逆。AppBLB 使用相同计费 API（与普通型共用）。

---

## 18. HTTP → HTTPS 重定向

**触发话术**：用户说"HTTP 跳转 HTTPS"、"redirectPort"、"自动跳转到 HTTPS"、"HTTP 重定向"、"开启 HTTPS 自动跳转"。

**能力依据（CLI 实测）**：`CreateBlbHttpListener` / `CreateAppBlbHttpListener` 均支持 `--redirectPort` 参数，用于配置 HTTP 请求自动 301 重定向到指定 HTTPS 端口。更新已有 HTTP 监听器时，通过 `UpdateBlbHttpListener` / `UpdateAppBlbHttpsListener` 设置 `--redirectPort`（以实时 help 为准）。

**前提条件**：目标 BLB/AppBLB 必须已存在 HTTPS 监听器（监听 443 端口并绑定证书），否则重定向无意义。

**执行流程**：

1. **确认上下文**
   - 确认实例类型（普通型 BLB / AppBLB）、blbId、region。
   - 确认已存在 HTTPS 监听器及其端口（通常为 443）：
   ```bash
   "$BCE" blb DescribeBlbListener --region <region> --blbId <blbId> --pager
   # AppBLB:
   "$BCE" blb DescribeAppBlbListener --region <region> --blbId <blbId> --pager
   ```

2. **确认 HTTP 监听器状态**
   - 查看是否已有 HTTP 监听器：
     - **已有 HTTP 监听器**：用 `UpdateBlbHttpListener` / `UpdateAppBlbHttpListener` 追加 `--redirectPort 443`。
     - **没有 HTTP 监听器**：需先创建 HTTP 监听器并设置 `--redirectPort 443`。

3. **配置重定向（普通型 BLB）**
   - 更新已有 HTTP 监听器：
   ```bash
   "$BCE" blb UpdateBlbHttpListener \
     --region <region> --blbId <blbId> --clientToken <uuid> \
     --listenerPort 80 \
     --redirectPort 443 \
     --dry-run
   ```
   - 或创建新 HTTP 监听器（带重定向）：
   ```bash
   "$BCE" blb CreateBlbHttpListener \
     --region <region> --blbId <blbId> --clientToken <uuid> \
     --listenerPort 80 --backendPort <后端端口> \
     --scheduler LeastConnection \
     --redirectPort 443 \
     --dry-run
   ```

4. **配置重定向（AppBLB）**
   - AppBLB 参数以实时 help 为准：
   ```bash
   "$BCE" blb UpdateAppBlbHttpListener \
     --region <region> --blbId <blbId> --clientToken <uuid> \
     --listenerPort 80 \
     --redirectPort 443 \
     --dry-run
   ```

5. **验证**
   - 查询 HTTP 监听器确认 `redirectPort` 已设置：
   ```bash
   "$BCE" blb DescribeBlbHttpListener --region <region> --blbId <blbId> --listenerPort 80
   ```
   - 输出配置结果摘要。

> **注意**：设置 `redirectPort` 后，该 HTTP 监听器上的所有请求将被 301 重定向到指定 HTTPS 端口。如原 HTTP 监听器仍有直接转发的后端配置，重定向生效后原有转发将不再生效。
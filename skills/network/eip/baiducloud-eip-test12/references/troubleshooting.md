# BLB Skill 命令失败恢复与排障参考

> 唯一职责：命令失败、参数不确定、复杂结构构建失败或 references 与实时 help 不一致时的**恢复闭环**，以及**错误码字典（§11）**。
> 不负责：业务诊断流程（见 `workflows.md` §10/§11）、跨服务联动（见 `cross-service.md`）；本文只管"命令执行层面的失败怎么修 + 错误码什么意思"。
> 任何真实写操作修正后仍必须先 dry-run 或重新请求用户确认；高风险操作必须二次确认。

---

## 1. 总原则

任何命令、API 名、参数名或参数结构不确定时，禁止凭经验猜测。必须进入以下闭环：

1. **发现**：读取错误信息、CLI suggestions、服务/API help 或 skeleton。
2. **验证**：确认 API 名、参数名、必填项、位置和 JSON 结构。
3. **修正**：只使用已确认存在的 API 和参数。
4. **预演**：写操作先 `--dry-run`，复杂请求必要时加 `--debug`。
5. **执行或停止**：确认无误并获得用户授权后执行；仍不确定则停止询问。

实时 help 是兜底工具，不是每条已知简单查询的默认前置步骤。对于 `DescribeBlbs`、`DescribeBlb`、`QueryVpcList`、`QuerySubnetList` 等主手册明确列出的简单查询，参数明确时可直接构造命令。

---

## 2. 何时使用 help / skeleton / dry-run / debug

| 场景 | 兜底动作 |
|------|----------|
| API 名不确定或名称相近 | `"$BCE" <service> --help` |
| 参数名不确定或疑似拼写错误 | `"$BCE" <service> <ApiName> --help` |
| 复杂 List/Object/JSON 参数 | `"$BCE" <service> <ApiName> --generate-cli-skeleton` |
| 写操作参数不确定 | 先 help/skeleton，再 `--dry-run`，通过后请求用户确认真实执行 |
| AppBLB IPv6 创建 | `CreateAppBlb --type ipv6Application --dry-run`，确认 body 中包含 `type=ipv6Application` |
| AppBLB IPv6 列表查询 | 不拼接 `--type`；普通 `DescribeAppBlbs` 后按返回字段过滤 |
| 命令执行失败 | 按本文错误分类恢复，并向用户返回错误阶段、错误码/HTTP 状态/requestId、服务端错误消息和下一步建议；不直接换一个猜测命令重试 |
| 付费创建将真实执行 | 先 `BlbInquiry`，展示费用/计费模式/可能产生账单，用户确认后才继续 |
| 释放 BLB/AppBLB | 先按 `SKILL.md` §11.1 查询监听器、后端/服务器组、策略并判断闲置；非闲置时展示依赖摘要和清依赖建议，再让用户确认是否仍释放 |
| 高风险操作存在任何歧义 | 查 help/skeleton 或停止询问用户，不继续真实执行 |
| dry-run 失败但参数看似正确 | 使用 `--debug` 获取请求细节，脱敏后分析 |

---

## 3. 错误分类与恢复策略

| 错误类型 | 恢复策略 |
|----------|----------|
| 未找到 BCE CLI | 按 `SKILL.md` 的 `$BCE` 发现顺序重新解析；只允许在 skill 包目录内排查；找不到即停止 |
| `"$BCE" version` 失败 | 检查路径是否是文件、是否可执行、是否匹配当前系统；失败即停止云资源操作 |
| 未知 service/API | 查看 CLI suggestion；执行 `"$BCE" <service> --help` 核对真实 API 名；禁止自造近似命令 |
| 未知参数/参数名疑似错误 | 执行 `"$BCE" <service> <ApiName> --help`，只使用 help 中存在的 flag |
| 必填参数缺失 | 从 API help 或 skeleton 补齐；缺少业务信息时询问用户 |
| JSON/List/Object 结构错误 | 执行 `--generate-cli-skeleton`，优先改用 `--cli-input-json file://...` |
| 分页参数错误 | 查 API help 是否支持分页；不支持时移除 `--pager` / `--total-count` |
| 输出或 JMESPath 错误 | 先输出 JSON 原始响应，再调整 `--query`、`rows=`、`cols=` |
| 认证/权限错误 | 不改命令结构；先确认 profile、region、AK/SK 是否正确且权限足够 |
| 资源不存在/404 | 不盲改参数；确认 region、resourceId、实例类型，先用列表/详情查询验证 |
| 配额/冲突/业务 400/409 | 结合服务端错误和 help 判断；不能通过猜测参数重试 |
| 网络超时/临时 5xx | 可增加 `--timeout` 或重试；写操作重试必须使用相同 `clientToken` |
| dry-run 失败 | 使用 `--debug` 获取请求细节，脱敏后汇报；停止真实执行 |
| 真实写操作失败 | 不自动重复执行；先返回失败信息，包含操作阶段、命令摘要、错误码/HTTP 状态/requestId、服务端错误消息、已确认参数和建议动作 |
| references 与实时 help 不一致 | 以当前机器 `"$BCE" ... --help` 为准，并在回复中说明差异 |

---

## 4. 失败信息返回模板

命令失败时必须把 CLI/服务端返回内容整理为用户可读信息，不能只说“执行失败”。如字段不存在，明确写“未返回”。

必填字段：

1. **失败阶段**：CLI 发现、参数构造、dry-run、真实执行、查询验证或结果解析。
2. **命令摘要**：只展示 API 名、region、resourceId 和关键参数；不得展示 AK/SK/token、Authorization、签名或完整 debug header。
3. **错误信息**：错误码、HTTP 状态码、requestId、服务端 message、CLI stderr/stdout 摘要。
4. **原因判断**：基于错误类型说明可能原因，例如权限不足、region 错误、资源不存在、配额不足、参数结构错误或业务冲突。
5. **下一步建议**：给出可验证的查询、help/skeleton、dry-run、debug 脱敏分析或需要用户补充的信息。

推荐回复形态：

```text
操作失败：<ApiName> 未完成。
- 阶段：<dry-run/真实执行/查询验证>
- 目标：region=<region>, blbId=<id或未返回>, profile=<脱敏profile>
- 错误：code=<code或未返回>, httpStatus=<status或未返回>, requestId=<requestId或未返回>, message=<服务端消息或CLI错误摘要>
- 判断：<基于错误分类的原因>
- 建议：<下一步命令或需要用户确认的信息>
```

---

## 5. BLB / AppBLB 常见易错点

### 5.1 VPC / 子网 API 名

BLB 创建前查询 VPC/子网必须使用：

```bash
"$BCE" vpc QueryVpcList
"$BCE" vpc QuerySpecifiedVpc
"$BCE" vpc QuerySubnetList
"$BCE" vpc QuerySpecifiedSubnet
```

不要套用通用云厂商命令或旧命令名，例如 `DescribeVpcs`、`DescribeSubnets`、`QueryVpcDetail`、`QuerySubnetDetail`。

### 5.2 IPv6 类型差异

| 需求 | 正确做法 | 禁止做法 |
|------|----------|----------|
| 创建普通型 IPv6 BLB | `CreateBlb --type ipv6` | 用 AppBLB 参数创建普通型 BLB |
| 查询普通型 IPv6 BLB | `DescribeBlbs --type ipv6` | 省略类型后声称只查 IPv6 |
| 创建 IPv6 AppBLB | `CreateAppBlb --type ipv6Application` | 用 `--type ipv6` 创建 AppBLB |
| 查询 IPv6 AppBLB | `DescribeAppBlbs` 后按返回字段过滤 | `DescribeAppBlbs --type ipv6Application` |

### 5.3 监听器参数差异

| 差异点 | 普通型 BLB | AppBLB |
|--------|------------|--------|
| 后端端口 | 监听器包含 `backendPort` | 监听器没有 `backendPort`，后端端口在服务器组端口配置 |
| 健康检查 | 多数协议在监听器层配置 | 在服务器组端口或 IP 组协议配置 |
| X-Forwarded-For | `--xForwardFor` | `--xForwardedFor` |
| 会话保持时长 | `keepSessionDuration` | `keepSessionTimeout` |
| 删除监听器 | `DeleteBlbListener --portList` | `DeleteAppBlbListener --portTypeList` |

### 5.4 后端模型差异

普通型 BLB 直接挂载后端服务器：

```bash
"$BCE" blb AddBlbServer
"$BCE" blb DescribeBlbServers
"$BCE" blb UpdateBlbServer
"$BCE" blb DeleteBlbServer
```

AppBLB 通过服务器组管理后端：

```bash
"$BCE" blb CreateAppBlbServerGroup
"$BCE" blb AddAppBlbServerGroupRs
"$BCE" blb DescribeAppBlbServerGroupRs
"$BCE" blb UpdateAppBlbServerGroupRs
"$BCE" blb DeleteAppBlbServerGroupRs
```

不要杜撰 `AddBackendServers`、`RemoveBackendServers` 等非 BCE CLI API 名。

---

## 6. 写操作与高风险恢复

### 普通写操作

- 修正命令后必须先执行或展示 `--dry-run`。
- 确认请求方法、endpoint、path、query、body 与用户意图一致。
- dry-run 通过后再请求用户授权真实执行。

### 高风险操作

以下操作真实执行前必须说明影响范围并二次确认：

- 付费创建：`CreateBlb`、`CreateAppBlb`。真实创建前必须先 `BlbInquiry` 并展示费用、计费模式和可能产生的公网 EIP/规格型 BLB 费用。
- 释放/删除：`ReleaseBlb`、`ReleaseAppBlb`、`DeleteBlbListener`、`DeleteAppBlbListener`、`DeleteBlbServer`、`DeleteAppBlbServerGroup`、`DeleteAppBlbServerGroupRs`、`DeleteAppBlbServerGroupPort`、`DeleteAppBlbPolicy`、`DeleteAppBlbIpGroup`、`DeleteAppBlbIpGroupMember`、`DeleteAppBlbIpGroupProtocol`、`DeleteService`。
- 解绑：`UnbindBlbSecurityGroup`、`UnbindBlbEnterpriseSecurityGroup`、`UnbindInstanceFromService`。
- 计费/退款：`RefundBlb`、`BillingChangePreToPostBlb`、`BillingChangePostToPreBlb`、`BillingChangeCancelToPostBlb`。
- 流量影响变更：监听器端口、证书、健康检查、后端端口、策略优先级、后端权重大幅调整。

生产资源未得到明确授权时，只允许查询、生成命令或 dry-run，不执行真实变更。

### 非闲置实例释放确认

释放前闲置校验发现依赖仍存在时，不要直接执行真实释放：

1. 展示依赖摘要：监听端口/协议、后端服务器或服务器组/RS、策略数量和策略 ID。
2. 给出清依赖建议：按依赖类型建议 `DeleteBlbListener`、`DeleteBlbServer`、`DeleteAppBlbListener`、`DeleteAppBlbServerGroupRs`、`DeleteAppBlbPolicy` 等真实 API。
3. 询问用户是先清依赖，还是仍确认释放非闲置实例。
4. 用户确认仍释放时，再次复核 profile、region、blbId、依赖范围和不可恢复影响；复核通过后才真实释放。

---

## 7. 幂等与重试

- 所有 POST 操作支持 `clientToken` 参数。相同 `clientToken` 的重复请求不会产生副作用，可安全重试。
- 同一写操作因超时、5xx 或客户端中断需要重试时，必须使用相同 `clientToken`，避免重复创建或重复变更。
- 如果不确定服务端是否已经处理成功，先查询目标资源状态，再决定是否重试。
- 删除、释放、退款、计费转换等高风险操作不应自动重试，必须再次确认状态和用户意图。

---

## 8. Debug 输出处理

使用 `--debug` 时可能包含请求头、签名相关信息或敏感响应。回复用户时必须：

- 隐去完整 AK/SK/token、Authorization、签名、Cookie 等敏感字段。
- 只保留方法、路径、脱敏后的 endpoint、参数摘要、错误码、requestId、服务端错误消息。
- 不把 debug 原文写入 `SKILL.md`、references 或提交内容。

---

## 9. 停止条件

同一操作连续两轮仍无法通过 help/skeleton/dry-run 确认正确命令时，停止执行。向用户说明：

1. 原始用户目标。
2. 已尝试的命令或验证动作。
3. 错误摘要。
4. 已确认的信息。
5. 仍缺失或冲突的信息。
6. 需要用户选择或补充的选项。

不要为了“继续推进”而猜测 API、参数、region、资源 ID 或凭证。

---

## 10. 运行时健康异常分类速查

| 异常类型 | 先查什么 | 建议动作 |
|---|---|---|
| 普通型后端全部不健康 | `DescribeBlbListener`、`DescribeBlbServerHealth`、`DescribeBlbSecurityGroups` | 核对健康检查端口/路径/Host 和安全组放通规则。 |
| 普通型部分后端不健康 | `DescribeBlbServers`、`DescribeBlbServerHealth --listenerPort <port>` | 检查异常 BCC 服务进程；必要时建议 `UpdateBlbServer` 把权重置 0 后排查。 |
| AppBLB 服务器组后端异常 | `DescribeAppBlbServerGroup`、`DescribeAppBlbServerGroupRs --sgId <sgId>` | 查看 `portList[].status`，核对服务器组端口健康检查配置。 |
| AppBLB Host/Path 访问异常 | `DescribeAppBlbPolicy --port <port> --type <type>` | 检查 `priority`、`ruleList`、目标 `appServerGroupId` / `appIpGroupId` 和后端端口。 |
| 间歇性不健康 | 查询监听器或服务器组端口健康检查参数 | 检查 timeout、interval、unhealthy threshold 是否过严；变更前先 dry-run 并等待确认。 |

当前 CLI 无独立 AppBLB 健康查询 API；不要杜撰 `DescribeAppBlbServerHealth`，使用服务器组 RS 的端口状态进行诊断。

---

## 11. 常见业务错误码速查

> **错误码问答入口**：用户问「XX 错误码什么意思」「返回 YY 怎么回事」时（`SKILL.md` §7.8 错误码类问答），**必须优先查本表**作答，给出含义 + 恢复策略。
> 以下错误码来源于百度智能云 BLB API 参考目录下的官方错误码文档。**错误码以实时 API 返回为准**；不在此表的错误码再联网搜索百度智能云官方文档核实（仅采纳 `cloud.baidu.com` 域名）。

### 11.1 BCE 公共错误码

| 错误码 | HTTP 状态 | 语义 | 恢复策略 |
|---|---|---|---|
| AccessDenied | 403 | 无权限访问对应的资源 | 确认 profile 对应的 AK/SK 是否有该操作权限 |
| InappropriateJSON | 400 | JSON 格式正确但语义不符合要求（缺必需项、值类型不匹配等） | 按 §2 用 help/skeleton 核对参数和必填项 |
| InternalError | 500 | 服务端未定义的其他错误 | 可使用相同 clientToken 重试；持续失败联系工单 |
| InvalidAccessKeyId | 403 | Access Key ID 不存在 | 确认 profile 配置的 AK 是否正确 |
| InvalidHTTPAuthHeader | 400 | Authorization 头域格式错误 | 通常为 CLI 内部问题，确认 CLI 版本 |
| InvalidHTTPRequest | 400 | HTTP body 格式错误（如 Encoding 不符） | 检查请求体编码 |
| InvalidURI | 400 | URI 形式不正确 | 确认 API 名和资源 ID |
| MalformedJSON | 400 | JSON 格式不合法 | 优先用 `--generate-cli-skeleton` + `--cli-input-json file://...` |
| InvalidVersion | 404 | URI 的版本号不合法 | 升级 CLI 到最新版本 |
| OptInRequired | 403 | 没有开通对应的服务 | 在控制台开通对应云服务 |
| PreconditionFailed | 412 | ETag 不匹配 | 重新获取资源最新状态后重试 |
| RequestExpired | 400 | 请求超时 | 检查本机时间同步，重新执行 |
| IdempotentParameterMismatch | 403 | clientToken 对应的 API 参数与之前请求不一致 | 使用新的 clientToken |
| SignatureDoesNotMatch | 400 | 请求签名与服务端验证不一致 | 确认 SK 是否正确 |

### 11.2 BLB 业务错误码

| 错误码 | HTTP 状态 | 语义 | 恢复策略 |
|---|---|---|---|
| InstanceNotFound | 404 | 指定的 LoadBalancer 实例不存在 | 确认 region 和 blbId，用 `DescribeBlbs` / `DescribeAppBlbs` 验证 |
| ListenerNotFound | 404 | 指定的监听器不存在 | 用 `DescribeBlbListener` / `DescribeAppBlbListener` 确认监听端口与协议 |
| BackendServerNotFound | 404 | 指定的后端服务器不存在 | 用 `DescribeBlbServers` / `DescribeAppBlbServerGroupRs` 确认 |
| ListenerAlreadyExist | 400 | 要创建的监听器已存在 | 查询当前监听器，改用 `Update*Listener` 或换端口 |
| BackendServerAlreadyExist | 400 | 要绑定的后端服务器已存在 | 改用 `Update*` 调整权重，而非重复 `Add*` |
| LastOperationNotFinished | 409 | 上一个 LoadBalancer 请求还未处理完成 | 查询实例 `status`，等待状态稳定后重试 |
| RealNameAuthenticationRequired | 403 | 当前用户未通过实名认证 | 到百度智能云完成实名认证 |
| QuotaExceeded | 413 | BLB 数量超过用户配额限制 | 联系百度云提升配额或释放闲置实例 |
| ServerRequired | 404 | 创建 BLB 时必须先拥有 BCC、DCC 或 BBC 实例 | 先在目标 region 创建 BCC/DCC/BBC |
| ListenerExceeded | 413 | 每个 BLB 实例最多可以创建 20 个监听器 | 删除不用的监听器或拆分到多个 BLB |
| ServiceBlocked | 403 | BLB 服务被封禁 | 联系技术支持 |
| InstanceCreationFailed | 400 | 创建 BLB 实例失败（资源不足、金额不足等） | 检查账户余额、目标 region 资源情况 |
| MissingParameter | 400 | 缺少必要参数 `parameterName` | 按错误消息中的 parameterName 补齐参数 |
| InvalidParameter | 400 | `parameterName` 参数不合法 | 用 `--help` 核对参数取值范围 |
| EipUnbindFailed | 400 | 解绑 EIP 失败 | 用 `eip QueryEipList` 确认 EIP 状态，必要时联系工单 |
| RedirectPortNotFound | 404 | 指定的 HTTPS 监听器不存在 | 先创建 HTTPS 监听器再配置 HTTP `--redirectPort`，见 `workflows.md` §18 |
| CertificateNotFound | 404 | 指定的证书不存在 | 在证书服务/控制台确认 certId 存在且未过期 |

> 错误码源：百度智能云 BLB API 参考 - 错误码（位于 BLB 官方文档目录树下，引用前按 `doc-links.md` 规则联网核实具体 URL）。
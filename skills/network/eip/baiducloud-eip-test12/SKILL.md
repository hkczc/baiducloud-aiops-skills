---
name: baiducloud-eip-test12
description: >
  112管理百度云负载均衡（BLB/AppBLB）服务。当用户提到负载均衡、BLB、AppBLB、应用型负载均衡、普通型负载均衡、监听器、后端服务器、健康检查、健康异常诊断、VIP、服务器组、转发策略、Host/Path 规则、IP 组、SSL/TLS 终结、四层/七层负载均衡、BCC 实例流量分发、查询 region 下的 VPC、查询 VPC 下的子网、创建负载均衡前的 VPC/子网发现、计费询价、费用确认、实例闲置评估、跨 region/跨地域复制或迁移负载均衡配置、BCE CLI 网络操作、或任何百度云网络流量管理相关需求时，必须使用此 skill。支持创建/配置/查询/复制 BLB（普通型，L4+L7）和 AppBLB（应用型，L7 高级路由）实例，支持查询 region 下的 VPC 和 VPC 下的子网，支持删除监听器（TCP/UDP/HTTP/HTTPS/SSL）、后端服务器、服务器组、转发策略等子资源，支持安全组、计费管理，覆盖 IPv4 和 IPv6，支持所有百度云 region；不支持由 agent 执行 BLB/AppBLB 实例释放或删除。
---

# BLB 负载均衡管理 Skill

## 1. 目标与边界

test此 Skill 通过百度云 BCE CLI（`bce` 命令）管理负载均衡服务。`SKILL.md` 是 agent 的主运行手册，必须能独立指导 agent 完成：理解用户意图、解析 BCE CLI、确认上下文、选择 API、构造参数、按需查 references、执行 dry-run/真实命令或输出命令。

**支持 4 种负载均衡类型：**

| 类型 | 层级 | 协议 | 关键 CLI 区分 | 特点 |
|------|------|------|----------------|------|
| BLB（普通型） | L4 + L7 | TCP/UDP/HTTP/HTTPS/SSL | `CreateBlb` 默认类型 | 直接挂载后端服务器，通用场景 |
| AppBLB（应用型） | L7 | TCP/UDP/HTTP/HTTPS/SSL | `CreateAppBlb` 默认 `type=application` | 服务器组 + 策略路由，支持域名/路径转发 |
| IPv6 BLB | L4 + L7 | 同 BLB | `CreateBlb --type ipv6`，列表查询 `DescribeBlbs --type ipv6` | 普通型 IPv6 地址版本 |
| IPv6 AppBLB | L7 | 同 AppBLB | `CreateAppBlb --type ipv6Application`；列表查询不能加 `DescribeAppBlbs --type` | 应用型 IPv6 地址版本 |

命令模式：`"$BCE" <service> <ApiName> [--param value ...]`。

BLB 和 AppBLB 都使用 `"$BCE" blb` 作为 service 前缀，通过 API 名称和关键参数区分类型，例如 `CreateBlb` vs `CreateAppBlb`。

---

## 2. Agent 执行模型

处理用户请求时按以下顺序执行：

0. **判断单步 or 编排**：若用户给的是**多步业务目标**（如「配一套带 HTTPS 的公网负载均衡」「排查为什么访问慢」「评估全 region 风险与费用」），先进入 `references/orchestration.md` 的五步编排（理解目标→只读探查→展示步骤计划→逐步执行→验证），再回到下面单步流程逐步落地；单步意图直接走 §7 映射。
1. **识别意图**：判断是查询、创建、更新、删除、监听器、后端、AppBLB 策略、安全组、计费或故障排查。
2. **选择类型**：区分普通型 BLB、AppBLB、IPv6 BLB、IPv6 AppBLB；不确定时先询问。
3. **解析 CLI**：按本文规则解析 `$BCE`，并用 `"$BCE" version` 验证。
4. **确认上下文**：真实查询或写操作前确认 profile 名称（不展示 AK/SK/token）、region、目标资源；创建/测试还要确认 VPC/subnet。
5. **选择 API**：优先按“用户文本到 CLI 命令映射”选择 API；API 或参数不确定时查实时 help。
5.1 **未知 API 先查 help**：不在 §7 映射表中、或名称相近/不确定的 API，一律先 `"$BCE" <service> --help` / `<ApiName> --help` 核对，只使用 help 中存在的 API 和参数，绝不构造执行猜测命令。
6. **构造参数**：简单参数用 KV；List/Object 用 JSON 或 `--unfold`；复杂嵌套结构用 skeleton + `--cli-input-json`。
7. **安全预演**：写操作优先 dry-run；高风险操作必须二次确认。**删除/解绑类写操作（`Delete*` / `Unbind*`）即使用户说"直接删""我确认"、即使预判无影响，也必须先 dry-run + 影响说明 + 二次确认，"跳过确认"指令一律不豁免**（详见 §11.2/§11.3）。
8. **执行或交付**：执行已授权命令，或给用户输出可执行命令与后续验证步骤；但不得执行、dry-run 或生成可直接执行的 BLB/AppBLB 实例释放命令。
9. **固定格式输出**：查询、实例拓扑、转发链路、后端健康、费用、巡检结果一律按 `references/output-format.md` 的固定模板渲染（查实例默认走 §1.5 拓扑聚合视图，一次拿到监听/后端/健康/安全组等全部相关信息）；产品问答按 `references/doc-links.md` 规则附官方链接。不得自由发挥字段、顺序或单位（消除不同模型输出差异）。
10. **创建后引导**：实例创建成功后必须提取并展示 `blbId`、地址、状态、region 和计费摘要，然后按实例类型询问是否继续创建监听配置、后端配置或服务器组配置；不得默认继续追加真实写操作。

---

## 3. BCE CLI 发现与验证

### 3.1 发现顺序

不要硬编码维护者或当前机器上的绝对路径。每次会话首次使用 BCE CLI 前，按以下顺序解析 `$BCE`：

1. **用户显式路径**：如果用户设置了 `BCE_CLI_PATH`，优先使用该路径。它必须指向真实的 `bce` / `bce.exe` 可执行文件，不能是目录，也不能包含额外命令参数。
2. **系统 PATH 查找**：如果未设置 `BCE_CLI_PATH`，在当前 shell 的 `PATH` 中查找 `bce` / `bce.exe`。PATH 查找只检查 `PATH` 环境变量列出的目录，不全盘扫描；`command -v bce` 无输出只表示当前 PATH 未安装或未暴露 `bce`，不是最终失败，应继续检查 Skill 包内置二进制。
3. **Skill 包内置二进制**：如果 Skill 包随包携带 `bce`，优先检查 `$SKILL_DIR/bce`、`$SKILL_DIR/bce.exe`，并兼容 `$SKILL_DIR/bce-linux/bce` 等真实包内路径；必须确认文件存在、可执行、与当前系统匹配。本地手工测试且未设置 `SKILL_DIR` 时，可通过 `BCE_CLI_PATH=/path/to/bce` 指向实际可执行文件。
4. **包结构排查**：如果仍未找到，只允许在 Skill 包目录内执行 `ls -laR "$SKILL_DIR"` 排查完整目录结构，再根据真实路径选择可执行文件；不得全盘扫描用户机器，也不得杜撰路径。
5. **失败即停止**：如果无法解析并验证 BCE CLI，不执行任何 BLB/VPC 查询或写操作，提示用户安装 `bce` 到 PATH、设置 `BCE_CLI_PATH`，或确认 Skill 包内 `bce` 路径。

Linux / macOS 示例：

```bash
if [ -n "$BCE_CLI_PATH" ]; then
  BCE="$BCE_CLI_PATH"
elif command -v bce >/dev/null 2>&1; then
  BCE="$(command -v bce)"
elif [ -n "$SKILL_DIR" ] && [ -x "$SKILL_DIR/bce" ]; then
  BCE="$SKILL_DIR/bce"
elif [ -n "$SKILL_DIR" ] && [ -x "$SKILL_DIR/bce-linux/bce" ]; then
  BCE="$SKILL_DIR/bce-linux/bce"
else
  if [ -n "$SKILL_DIR" ]; then
    ls -laR "$SKILL_DIR"
  fi
  echo "未找到 BCE CLI：请安装 bce 到 PATH、设置 BCE_CLI_PATH，或确认 Skill 包内 bce 可执行文件路径。"
  exit 1
fi
```

Windows PowerShell 示例：

```powershell
if ($env:BCE_CLI_PATH) {
  $BCE = $env:BCE_CLI_PATH
} else {
  $cmd = Get-Command bce -ErrorAction SilentlyContinue
  if (-not $cmd) { $cmd = Get-Command bce.exe -ErrorAction SilentlyContinue }
  if ($cmd) { $BCE = $cmd.Source }
}
```

### 3.2 验证

解析 `$BCE` 后，必须先验证 CLI 可用；路径要加引号以兼容空格：

```bash
"$BCE" version
```

验证失败时停止：路径不存在、指向目录、不可执行、版本命令失败都不能继续操作云资源。

---

## 4. 凭证与 Profile 安全策略

### 4.1 安全原则

Skill 不创建、不保存、不读取、不展示任何长期密钥。Skill 只消费当前运行环境中已经存在的 profile 或平台注入的临时凭证。

### 4.2 禁止行为

- **默认**禁止在对话中索要 AK/SK/token；仅 §4.7 路径 B（不同环境）在完成判定与风险提示后允许用户提供 AK/SK 由 Agent 代配。
- **默认**禁止执行带明文 AK/SK/token 的 `configure set`；仅 §4.7 路径 B 允许 Agent 在沙箱内执行。
- 禁止通过 `env`、`printenv`、`echo $VAR`、读取配置文件、读取环境变量等方式探测凭证。
- 禁止把 debug 输出中的 Authorization、签名、token、AK/SK 原样展示给用户。
- 禁止把 AK/SK/token 泄漏出去：不回显、不打印、不复述，不写入日志、临时文件、命令历史或外部服务（§4.7 路径 B 下 `configure set` 写入 CLI 自身 profile 文件属必要动作，不算泄漏）。

### 4.3 允许行为

- 允许执行不暴露密钥的 profile 列表查询命令。
- 允许使用用户指定的 profile 名执行只读查询。
- 允许在确认 profile、region、资源 ID 后执行真实查询。
- 允许在写操作前执行 dry-run。
- 允许提示用户在 Agent 之外自行配置 profile。

### 4.4 查询 profile 的安全方式

- 判断 profile 是否存在统一用 `configure list`，它只输出 profile 名和认证模式，不含任何 AK/SK/token：

```bash
"$BCE" configure list
```

- `configure get` 仅用于核对 region/mode 等非密钥字段，且必须确保 CLI 自身已对 AK/SK/token 脱敏后才能使用。BCE CLI 已确认脱敏（SecretAccessKey/SecurityToken 全打码、AccessKeyId 仅露前 4 位），可用于核对非密钥字段：

```bash
"$BCE" configure get <profile名>
```

- 若目标云 CLI 的 get 可能打印明文密钥，则禁止使用 get，只允许 list 或其他不含密钥的命令。

### 4.5 没有可用 profile 时的处理流程

1. 先执行 `"$BCE" configure list` 确认是否存在可用 profile。
2. 已存在目标 profile：只用 profile 名引用，进入 §4.8 上下文确认，不再向用户索要任何凭证。
3. 不存在目标 profile：在按 §4.7 判定环境并选定路径之前，立即停止，不执行任何云资源查询或写操作。
4. 按 §4.7 完成环境判定后选择路径：同环境走**路径 A**（引导用户在本地自行配置 profile，Agent 不代配、不收 AK/SK）；不同环境走**路径 B**（允许用户提供 AK/SK 由 Agent 在沙箱内代配，风险由用户自负）。

### 4.6 命令示例

凭证配置命令（AK/SK 为占位符）：

```bash
bce configure set <profile名> \
  --access-key-id <AK> \
  --secret-access-key <SK> \
  --region <region>
```

- **路径 A（同环境）**：由**用户自己**在本地 CLI 执行上面的命令，不要把 AK/SK 发给 Agent。
- **路径 B（不同环境）**：在完成 §4.7 环境判定与风险提示后，由 **Agent 在沙箱内**执行上面的命令完成代配。

Agent 日常只读命令（不暴露密钥）：

```bash
"$BCE" configure list
"$BCE" vpc QuerySubnetList --profile <profile名> --region <region>
```

### 4.7 环境判定与两条配置路径（Agent 沙箱 vs 用户本机）

前提认知：用户本机配置的 profile 不会自动同步到 Agent 沙箱；Agent 只能使用其当前运行环境中已存在的 profile。无可用 profile 时，必须先判定环境再二选一执行路径 A 或路径 B，不得跳过判定直接索要或拒收 AK/SK。

**环境判定（先自探，再询问，缺一不可）：**

1. **自探**：Agent 先判断自己能否访问用户本机的本地目录（例如用户家目录、当前工作区、`~/.bce/` 配置目录**是否存在且可访问**），据此初步判断是否与用户共享同一文件系统。自探只检查路径的可访问性 / 是否存在，**严禁读取、解析、回显 `config.json` 等文件中的 AK/SK/token 明文**（这与 §4.2 一致）；判断 profile 是否存在仍只用 `configure list`。
2. **询问**：无论自探结论如何，都要主动向用户确认环境关系——「我是运行在你本机、能访问你的本地配置，还是运行在独立的远端沙箱？」
3. 综合自探 + 用户确认结果选择路径；判定不一致或无法确认时，按更安全的路径 A 处理。

**路径 A — 同环境（Agent 可访问用户本地目录）：**

- 不接受用户在对话中发送 AK/SK，也不代为配置。
- 引导用户自行在本地 CLI 用 `configure set` 把 AK/SK 写入 profile（示例见 §4.6）。
- 用户配置完成后，Agent 重新 `configure list` 确认，之后一律只用 profile 名引用该凭证。

**路径 B — 不同环境（Agent 为远端沙箱，无法访问用户本地目录）：**

- 允许用户把 AK/SK 发到交互页面，由 Agent 在沙箱内执行带明文 flag 的 `configure set` 代为配置。
- 配置前必须明确提示用户：**风险由用户自行承担**；凭证仅在当前沙箱 session 内有效，沙箱销毁即失效。
- Agent 绝不泄漏 AK/SK：不回显、不打印、不复述明文，不写入额外日志 / 临时文件 / 外部服务；AK/SK 只允许进入 CLI 自身 profile 文件（`configure set` 的必要写入），不算泄漏。
- 配置完成后一律只用 profile 名引用该凭证。

### 4.8 执行云资源查询或变更前的上下文确认

每次真实查询或写操作之前，必须确认以下 4 项，不得直接复用未确认上下文：

1. profile 名称（只展示 profile 名，不展示任何 AK/SK/token）。
2. region，真实命令优先显式追加 `--region <region>`。
3. 操作目标资源（resourceId；创建或测试资源时还要确认 VPC / 子网）。
4. 写操作是否先执行或展示 `--dry-run`；删除、释放、解绑、退款、计费转换等高风险操作必须二次确认。

### 4.9 Region

BLB 常用 region：

| Region | 说明 |
|--------|------|
| bj | 北京 |
| gz | 广州 |
| su | 苏州 |
| bd | 保定 |
| fwh | 武汉 |
| nj | 南京 |
| yq | 阳泉 |
| cd | 成都 |
| hkg | 香港 |

每次操作前与用户确认 target region。真实命令优先通过 `--region <region>` 覆盖 profile 中的默认 region。

### 4.10 CLI 路径与非凭证环境变量

仅以下非凭证环境变量与本 Skill 相关，不得通过环境变量向 Agent 传递长期密钥：

- `BCE_CLI_PATH`：本机 `bce` / `bce.exe` 可执行文件路径，优先级高于 PATH 查找。
- `BCE_REGION`：默认 region 覆盖。
- `BCE_LANGUAGE`：输出语言。

禁止读取、打印或依赖任何承载 AK/SK/token 的环境变量；凭证来源只允许是运行环境中已存在的 profile 或平台注入的临时凭证。

---

## 5. BCE CLI 命令构建规则

### 5.1 基本语法

```bash
"$BCE" <service> <ApiName> [--param value ...] [--global-flag value ...]
```

BLB/AppBLB 统一使用：

```bash
"$BCE" blb <ApiName> [--param value ...]
```

常用全局参数：

| 参数 | 说明 |
|------|------|
| `--profile <name>` | 临时使用指定 profile，不修改默认 profile |
| `--region <region>` | 覆盖请求 region，真实命令推荐显式追加 |
| `--endpoint <host>` | 覆盖请求域名，只有用户明确要求或排障时使用 |
| `--scheme http|https` | 强制指定请求协议；目标服务不支持时会报错 |
| `--language zh-CN|en-US` | 控制输出语言 |
| `--output json|table|text` | 输出格式，默认 JSON |
| `--query <JMESPath>` | 对响应结果做 JMESPath 过滤 |
| `--pager` | 对支持分页的 List API 自动翻页 |
| `--total-count <N>` | 配合 `--pager` 限制总条数 |
| `--dry-run` | 打印请求内容，不实际发送 |
| `--debug` | 打印详细 HTTP 请求/响应，输出给用户前必须脱敏 |
| `--timeout <秒>` | HTTP 请求超时，默认 15 秒 |
| `--unfold` | 为 List/Object 参数启用 KV 点号语法 |
| `--cli-input-json file://...` | 从 JSON 文件加载请求参数 |
| `--generate-cli-skeleton` | 生成请求参数 JSON 骨架 |

### 5.2 参数传递模式

四种方式，按复杂度递增选择：

1. **简单 KV**：简单参数用 `--param value`。
2. **JSON 字符串**：1-2 层嵌套用内联 JSON，如 `--billing '{"paymentTiming":"Postpaid"}'`。
3. **KV 点记法 `--unfold`**：中等复杂 Object 或重复 List 项，如 `--unfold --backendServerList instanceId=i-xxx weight=100`。重复 List 参数可多次传同一个 `--param`。
4. **文件输入**：深层嵌套结构（如 AppBLB 策略）先 `--generate-cli-skeleton > params.json`，再 `--cli-input-json file://...`。

完整示例见 `references/workflows.md` 各工作流。

### 5.3 输出、过滤与分页

```bash
"$BCE" blb DescribeBlbs --output json
"$BCE" blb DescribeBlbs --output table rows=blbList cols=blbId,name,address,status,vpcId
"$BCE" blb DescribeBlbs --query 'blbList[?status==`available`].blbId' --output text
"$BCE" blb DescribeBlbs --pager
"$BCE" blb DescribeBlbs --pager --total-count 50
```

`--query` 先对原始响应执行，`rows=` 再对 `--query` 的结果执行。对不支持分页的 API 使用 `--pager` / `--total-count` 会报错。

### 5.4 Help、Skeleton、Dry-run、Debug

```bash
"$BCE" blb --help
"$BCE" blb <ApiName> --help
"$BCE" blb <ApiName> --generate-cli-skeleton
"$BCE" blb <ApiName> --dry-run
"$BCE" blb <ApiName> --debug
```

这些是按需触发的验证与失败恢复工具，不需要每条已知简单查询默认执行；它们不能替代 profile/region/VPC/subnet 确认，也不能跳过高风险二次确认。

---

## 6. VPC 与子网前置规则

创建 BLB/AppBLB 前必须准备 VPC ID 和子网 ID。如果用户不知道，先查询再让用户选择。

```bash
"$BCE" vpc QueryVpcList --region <region> --pager --output table rows=vpcs cols=vpcId,name,cidr
"$BCE" vpc QuerySpecifiedVpc --region <region> --vpcId <vpcId>
"$BCE" vpc QuerySubnetList --region <region> --vpcId <vpcId> --pager --output table rows=subnets cols=subnetId,name,cidr,zoneName
"$BCE" vpc QuerySpecifiedSubnet --region <region> --subnetId <subnetId>
```

注意：VPC/子网查询 API 是 `QueryVpcList`、`QuerySpecifiedVpc`、`QuerySubnetList`、`QuerySpecifiedSubnet`；不是 `DescribeVpcs`、`DescribeSubnets`、`QueryVpcDetail`、`QuerySubnetDetail`。

测试隔离：所有 CLI 命令测试都必须在私有 VPC `blb_test` 下的子网完成：VPC `vpc-6ikazsm7kxe0`（10.0.0.0/16），子网 `sbn-bjezmbw9muvm`（10.0.1.0/24，cn-bj-a）。

---

## 7. 用户文本到 CLI 命令的映射规则

先识别用户意图，再选择 BLB 类型和 API；不确定 BLB 类型时先询问，不能混用普通型 BLB 和 AppBLB 参数。

### 7.1 资源发现与实例生命周期

| 用户意图 | 普通型 BLB 命令 | AppBLB 命令 | 构建要点 |
|---|---|---|---|
| 查询 VPC | `vpc QueryVpcList` | 同左 | 必须带 `--region`，需要全量时加 `--pager`。 |
| 查询子网 | `vpc QuerySubnetList` | 同左 | 已知 VPC 时传 `--vpcId`，测试限定 `vpc-6ikazsm7kxe0`。 |
| 创建负载均衡实例 | `blb CreateBlb` | `blb CreateAppBlb` | 必须确认 profile、region、vpcId、subnetId；测试限定 `sbn-bjezmbw9muvm`；真实创建前必须先 `BlbInquiry`，并把询价结果展示给用户；创建成功后按 §7.7 输出下一步配置引导。 |
| 创建时打标签/绑定资源组 | `blb CreateBlb --tags ... --resourceGroupId ...` | `blb CreateAppBlb`（参数以 help 为准） | `CreateBlb` 实测支持 `--tags`(tagKey/tagValue 列表) 与 `--resourceGroupId`；注意 `DescribeBlbs` 无 tag 过滤参数，标签不能用于 CLI 反查，详见 `references/workflows.md` §12。 |
| 创建普通型 IPv6 BLB | `blb CreateBlb --type ipv6` | 不适用 | 写操作先 dry-run；确认 VPC/subnet；真实创建前必须先 `BlbInquiry --blbType ipv6` 并展示费用；创建成功后按普通型 BLB 引导监听器与后端服务器。 |
| 创建应用型 IPv6 AppBLB | 不适用 | `blb CreateAppBlb --type ipv6Application` | 写操作先 dry-run，确认 body 包含 `type=ipv6Application`；真实创建前必须先 `BlbInquiry --blbType ipv6Application` 并展示费用；创建成功后按 AppBLB 引导服务器组、监听器与策略。 |
| 查询实例列表 | `blb DescribeBlbs` | `blb DescribeAppBlbs` | 支持 `--pager`、`--output table rows=... cols=...`；结果按 `references/output-format.md` §1 固定模板输出；用户要看某实例完整关系时引导走「查询实例拓扑」。 |
| 查询实例拓扑/全部相关信息 | `DescribeBlb`+`DescribeBlbListener`+`DescribeBlbServers`+`DescribeBlbServerHealth`+安全组 | `DescribeAppBlb`+`DescribeAppBlb*Listener`+`DescribeAppBlbServerGroup(Rs)`+`DescribeAppBlbIpGroup`+`DescribeAppBlbPolicy`+安全组 | 用户说「查实例/看这个 BLB 全部信息/配置全貌」的**默认视图**：按 `references/output-format.md` §1.5 聚合拉全（实例+监听+服务器组/IP组+后端+健康+安全组）后按拓扑模板输出。 |
| 查询实例摘要/详情 | `blb DescribeBlb` | `blb DescribeAppBlb` | 仅看实例自身属性时用 `references/output-format.md` §1；要完整关系走上一行 §1.5。 |
| 查询监听摘要 | `blb DescribeBlbListener` | `blb DescribeAppBlb*Listener` | 按 `references/output-format.md` §2 监听摘要模板输出。 |
| 查询转发链路 | `DescribeBlbListener`+`DescribeBlbServers`(+健康) | `DescribeAppBlb*Listener`+`DescribeAppBlbPolicy`+`DescribeAppBlbServerGroup(Rs)`/IP组 | 按 `references/output-format.md` §3 转发链路模板（普通型/AppBLB 不同）渲染。 |
| 查询后端健康 | `blb DescribeBlbServerHealth` | `blb DescribeAppBlbServerGroupRs`(portList[].status) | 按 `references/output-format.md` §4 健康概览模板输出。 |
| 查询/预估费用 | `blb BlbInquiry` | 同左 | 按 `references/output-format.md` §5 费用摘要模板输出，金额原样不换算。 |
| 查询普通型 IPv6 BLB 列表 | `blb DescribeBlbs --type ipv6` | 不适用 | 已验证支持 `--type ipv6`。 |
| 查询应用型 IPv6 AppBLB 列表 | 不适用 | `blb DescribeAppBlbs` 后按返回字段过滤 | 当前 `DescribeAppBlbs` 不支持 `--type ipv6Application`，不得拼接该参数。 |
| 查询实例详情 | `blb DescribeBlb` | `blb DescribeAppBlb` | 必须传 `--blbId`。 |
| 跨 region 复制实例配置 | `DescribeBlb` + `CreateBlb` + 监听器/后端/安全组重建 | `DescribeAppBlb` + `CreateAppBlb` + 服务器组/端口/策略/IP 组重建 | 复制是“业务配置等价重建”，不是资源 ID 原样迁移；目标 region 的 VPC/subnet、后端实例、证书、安全组、EIP 必须重新映射；真实创建前必须 `BlbInquiry`。 |
| 更新实例 | `blb UpdateBlb` | `blb UpdateAppBlb` | 写操作，先确认目标实例和 region。 |
| 释放/删除实例 | 不支持由 Skill 执行 | 不支持由 Skill 执行 | 禁止执行、dry-run 或生成可直接执行的 `ReleaseBlb` / `ReleaseAppBlb` 命令；可按 §11.1 仅做只读闲置评估，并引导用户通过控制台或自行操作 CLI。 |
| 变更规格 | `blb ResizeBlb` | `blb ResizeBlb`（共用） | 写操作；需 `clientToken`，确认规格和影响；完整流程见 `references/workflows.md` §16。 |
| 修改保护 | `blb UpdateBlbModifyProtection` | 以 help/reference 为准 | 生产环境推荐开启；关闭保护属于风险变更。 |

### 7.2 监听器

| 用户意图 | 普通型 BLB 命令 | AppBLB 命令 | 构建要点 |
|---|---|---|---|
| 创建 TCP 监听器 | `blb CreateBlbTcpListener` | `blb CreateAppBlbTcpListener` | 普通型必须传 `backendPort`；AppBLB 不允许传 `backendPort`。 |
| 创建 UDP 监听器 | `blb CreateBlbUdpListener` | `blb CreateAppBlbUdpListener` | 普通型健康检查在监听器；AppBLB 健康检查在服务器组端口/IP 组协议。 |
| 创建 HTTP 监听器 | `blb CreateBlbHttpListener` | `blb CreateAppBlbHttpListener` | 普通型真实 IP 参数是 `--xForwardFor`，AppBLB 是 `--xForwardedFor`。 |
| 创建 HTTPS 监听器 | `blb CreateBlbHttpsListener` | `blb CreateAppBlbHttpsListener` | 需要证书 ID；普通型仍有 `backendPort`，AppBLB 没有。加密策略/双向认证 mTLS（`--dualAuth`+`--clientCertIds`）/SNI 多域名（`--additionalCertDomains`）配置见 `references/workflows.md` §13；证书只能引用已存在 certId（无证书管理服务）。 |
| 创建 SSL 监听器 | `blb CreateBlbSslListener` | `blb CreateAppBlbSslListener` | 需要证书 ID；参数以 help/reference 为准。 |
| 查询监听器 | 按协议 `DescribeBlb*Listener` | 按协议 `DescribeAppBlb*Listener` | 协议不确定时先查实例或服务 help。 |
| 删除监听器 | `blb DeleteBlbListener` | `blb DeleteAppBlbListener` | 高风险，确认端口、协议、影响范围；删除前必须按 §11.3 检查是否仍有在用后端，存在在用后端时硬阻断，不可 override。 |

### 7.3 后端、服务器组、策略与 IP 组

AppBLB 的路由链路分 4 层：**监听器默认动作 → Policy 路由（Host/Path 规则） → ServerGroup 绑定 → IpGroup 绑定**。不要把“创建服务器组”误当成“创建策略”，也不要用 Policy API 去维护服务器组端口或 IP 组成员。

| 用户意图 | 普通型 BLB 命令 | AppBLB 命令 | 构建要点 |
|---|---|---|---|
| 添加后端 | `blb AddBlbServer` | `blb AddAppBlbServerGroupRs` | 不存在 `AddBackendServers`；AppBLB 先确认服务器组。 |
| 查询后端 | `blb DescribeBlbServers` | `blb DescribeAppBlbServerGroupRs` | AppBLB 必须传 `--sgId`；后端状态关注返回中的 `portList[].status`。 |
| 更新后端权重 | `blb UpdateBlbServer` | `blb UpdateAppBlbServerGroupRs` | 确认 instanceId 和目标权重；可把异常节点权重临时置 0。优雅排空（先置 weight=0 → 等排空窗口 → 再摘除）见 `references/workflows.md` §15。 |
| 移除后端 | `blb DeleteBlbServer` | `blb DeleteAppBlbServerGroupRs` | 高风险，会影响流量分发。 |
| 查询后端健康 | `blb DescribeBlbServerHealth` | `blb DescribeAppBlbServerGroupRs` | 普通型按 listenerPort 查询；AppBLB 无独立健康 API，使用服务器组 RS 的端口状态。 |
| 创建服务器组 | 不适用 | `blb CreateAppBlbServerGroup` | AppBLB 专属能力，可初始化 `backendServerList`。 |
| 查询服务器组 | 不适用 | `blb DescribeAppBlbServerGroup` | 释放前、策略绑定前都应先查。 |
| 更新服务器组 | 不适用 | `blb UpdateAppBlbServerGroup` | 真实 flag 是 `--sgId`，用于改名称/描述。 |
| 删除服务器组 | 不适用 | `blb DeleteAppBlbServerGroup` | 高风险；先确认是否仍被策略或监听器引用；删除前必须按 §11.3 检查组内是否仍有在用后端 RS，存在在用后端时硬阻断，不可 override。 |
| 查询已挂载 RS | 不适用 | `blb DescribeAppBlbServerGroupMountRs` | 必须传 `--sgId`；用于判断服务器组依赖。 |
| 查询未挂载 RS | 不适用 | `blb DescribeAppBlbServerGroupUnmountRs` | 必须传 `--sgId`；用于扩容前筛选可挂载后端。 |
| 创建服务器组端口 | 不适用 | `blb CreateAppBlbServerGroupPort` | 后端端口与健康检查在这里配置。 |
| 更新服务器组端口 | 不适用 | `blb UpdateAppBlbServerGroupPort` | 用于修改健康检查协议、路径、Host、阈值等。 |
| 删除服务器组端口 | 不适用 | `blb DeleteAppBlbServerGroupPort` | 高风险，会影响后端端口转发和健康检查。 |
| 创建 Host/Path 策略 | 不适用 | `blb CreateAppBlbPolicy` | HTTP/HTTPS 可多策略；TCP/UDP/SSL 只支持一条完全匹配策略；复杂规则优先 `--cli-input-json`。 |
| 查询 Host/Path 策略 | 不适用 | `blb DescribeAppBlbPolicy` | 必须传 `--port`；同端口多协议时补 `--type`。 |
| 更新策略优先级/描述 | 不适用 | `blb UpdateAppBlbPolicy` | 只能改 `priority`/`description`；不能改 `ruleList`、目标组或后端端口，规则变更必须删除后重建。 |
| 删除策略 | 不适用 | `blb DeleteAppBlbPolicy` | 高风险，会影响 Host/Path 路由。 |
| 创建 IP 组 | 不适用 | `blb CreateAppBlbIpGroup` | 用于非 BCC IP 后端。 |
| 查询 IP 组 | 不适用 | `blb DescribeAppBlbIpGroup` | 当前 CLI 支持查询 IP 组本身。 |
| 更新 IP 组 | 不适用 | `blb UpdateAppBlbIpGroup` | 用于改名称/描述等元信息。 |
| 删除 IP 组 | 不适用 | `blb DeleteAppBlbIpGroup` | 高风险；先确认是否被策略引用。 |
| 创建 IP 组成员 | 不适用 | `blb CreateAppBlbIpGroupMember` | 成员包含 IP、端口、权重。 |
| 查询 IP 组成员 | 不适用 | `blb DescribeAppBlbIpGroupMember` | 用于核对非 BCC 后端。 |
| 更新 IP 组成员 | 不适用 | `blb UpdateAppBlbIpGroupMember` | 可调整成员 IP、端口、权重。 |
| 删除 IP 组成员 | 不适用 | `blb DeleteAppBlbIpGroupMember` | 高风险，会影响对应 IP 后端流量。 |
| 创建 IP 组协议 | 不适用 | `blb CreateAppBlbIpGroupProtocol` | 配置 IP 组协议端口与健康检查。 |
| 更新 IP 组协议 | 不适用 | `blb UpdateAppBlbIpGroupProtocol` | 当前 CLI 没有 `DescribeAppBlbIpGroupProtocol`；更新前从创建记录或 IP 组成员/策略上下文确认协议 ID。 |
| 删除 IP 组协议 | 不适用 | `blb DeleteAppBlbIpGroupProtocol` | 高风险，会影响 IP 组后端协议端口和健康检查。 |

### 7.4 安全组、ACL、计费

| 用户意图 | 常用命令 | 构建要点 |
|---|---|---|
| 绑定安全组 | `BindBlbSecurityGroup` / `BindBlbEnterpriseSecurityGroup` | 确认目标实例、groupId、region。 |
| 解绑安全组 | `UnbindBlbSecurityGroup` / `UnbindBlbEnterpriseSecurityGroup` | 高风险，必须先查询当前绑定关系并展示解绑对象、影响范围和可能导致的流量/访问控制变化，用户二次确认后才真实执行。 |
| 查询已绑定安全组 | `DescribeBlbSecurityGroups` | 查询操作，仍需确认 profile/region。 |
| 配置 ACL | `UpdateBlbAcl` 等 | 可能影响流量，写操作先 dry-run。 |
| 价格查询 | `BlbInquiry` | 创建付费资源的前置强制步骤；按 `--blbType`、`--billing.paymentTiming`、`--billing.billingMethod` 询价；dry-run 创建可跳过。公网实例+EIP 合计、规格变更差价、闲置浪费见 `references/cost.md`。 |
| 计费转换 | `BillingChange*Blb` | 高风险，必须二次确认。 |
| 退款 | `RefundBlb` | 高风险，必须二次确认并说明不可恢复/财务影响。 |

### 7.5 固定构建顺序

1. 按 BCE CLI 发现顺序解析 `$BCE`，并通过 `"$BCE" version` 验证。
2. 确认运行环境中已存在可用 profile（`"$BCE" configure list`）与 region；不存在目标 profile 时按 §4.5 停止，并按 §4.7 判定环境后走路径 A（同环境，引导用户本地自配）或路径 B（不同环境/远端沙箱，由 Agent 在沙箱内代配，风险用户自负）。
3. 若涉及创建或测试，确认 VPC/subnet；测试固定使用 `vpc-6ikazsm7kxe0` 和 `sbn-bjezmbw9muvm`。
4. 根据用户意图选择 API；如果 API 名不在本文明确清单中或存在歧义，先用 `"$BCE" <service> --help` 核对。
5. 参数构造优先使用本文映射和 references；若 references 与当前机器 help 不一致，以实时 help 为准。
6. 同一会话中已确认过的 service/API help 或 skeleton 结果可复用，避免重复查询。
7. 复杂 List/Object/JSON 参数优先用 `--generate-cli-skeleton` 确认结构，必要时改用 `--cli-input-json file://...`。
8. 跨 region 复制配置时，先导出源实例配置并生成“可复制/需映射/不可复制”清单；目标 region 的 VPC/subnet、BCC 后端实例、证书、安全组、EIP、资源组都必须由用户确认映射，不能复用源 region ID。
9. 真实写操作如属付费创建（`CreateBlb` / `CreateAppBlb`，含 `ipv6` / `ipv6Application`），先 `BlbInquiry` 询价 → 展示费用与计费模式 → 用户回复“我已知悉费用并确认创建”或同义明确确认 → 才能继续真实创建；dry-run 创建可跳过询价。
10. 写操作优先给出或执行 `--dry-run`，通过后再请求用户确认真实执行。
11. 高风险操作必须二次确认后才能真实执行。

### 7.6 健康检查与诊断

健康检查不仅要“查询状态”，还要把异常转成可执行建议。不要直接修改健康检查或摘除后端；先输出诊断结论和建议命令，等待用户确认。

| 类型 | 健康状态来源 | 固定流程 |
|---|---|---|
| 普通型 / 普通型 IPv6 BLB | `blb DescribeBlbServerHealth --blbId <id> --listenerPort <port>` | 先 `DescribeBlbListener --blbId <id> --pager` 取监听端口，再按端口轮询健康状态。 |
| AppBLB / AppBLB IPv6 | `blb DescribeAppBlbServerGroupRs --blbId <id> --sgId <sgId>` 返回中的 `portList[].status` | 先 `DescribeAppBlbServerGroup --blbId <id> --pager` 取服务器组，再逐组查询 RS；当前 CLI 无独立 AppBLB 健康查询 API。 |

诊断决策树：

- `status=unhealthy` 且健康检查为 HTTP/HTTPS：检查健康检查路径、Host、端口是否与后端实际服务一致；普通型看监听器 healthCheck 字段，AppBLB 看 `UpdateAppBlbServerGroupPort` / `UpdateAppBlbIpGroupProtocol` 支持的健康检查字段。
- 全部后端 `unhealthy` 且服务进程正常：优先检查安全组、企业安全组、ACL 是否放通监听端口和健康检查端口。
- 部分后端 `unhealthy`：检查对应 BCC/非 BCC IP 的服务进程；必要时先建议用 `UpdateBlbServer` 或 `UpdateAppBlbServerGroupRs` 把异常节点权重置 0，再继续排查。
- 间歇性 `unhealthy`：检查 `healthCheckTimeoutInSecond`、`healthCheckInterval` / `healthCheckIntervalInSecond`、`unhealthyThreshold` / `healthCheckDownRetry` 是否过严。
- 后端均健康但仍访问慢/超时/公网不通：先排查安全组规则（联动 `vpc`）与公网入口（联动 `eip` 的 EIP/DDoS），见 `references/cross-service.md`；**带宽/连接数/QPS/七层 4xx/5xx/响应时间等运行时监控指标与访问日志明细 CLI 不支持查询，一律标注「需控制台」，不编造数值或结论**（见 `cross-service.md` §4）。
- **源 IP（`sourceIp`）算法下同 BCC 做客户端+后端**：调度算法为 `SourceIp` 时，来自同一 BCC 源 IP 的请求始终被分配到同一个后端。如果后端 BCC 同时也是客户端（即后端 BCC 发起请求到自己被分配到的目标后端），由于源 IP 相同，请求始终路由到该 BCC 自身，导致"部分后端看起来不健康"或"请求超时"的假象。排查方法：检查调度算法是否为 `SourceIp`，如有 BCC 同时作为客户端和后端，建议改用 `RoundRobin` 或 `LeastConnection`，或在测试中使用不同源 IP 的客户端。

### 7.7 创建成功后的配置引导

`CreateBlb` / `CreateAppBlb` 真实执行成功后，不能只返回创建结果。必须先展示实例摘要，再询问用户是否继续配置下一步；用户未确认前不得继续执行监听器、后端、服务器组、策略等真实写操作。

| 实例类型 | 创建成功后必须提示 | 后续配置建议 |
|---|---|---|
| 普通型 / 普通型 IPv6 BLB | 是否创建监听配置；是否添加后端服务器 | 先确认监听协议、监听端口、后端端口、调度算法和健康检查，再确认 BCC instanceId/权重。 |
| AppBLB / AppBLB IPv6 | 是否创建监听配置；是否创建服务器组并添加后端；是否创建 Host/Path 策略或 IP 组策略 | 推荐顺序：服务器组 → 服务器组端口/健康检查 → 后端 RS → 监听器 → Policy/IP 组策略。 |

创建后回复模板必须包含：`profile`、`region`、`blbId`、实例类型、名称、VPC/subnet、地址/状态、计费模式/费用摘要，以及“是否继续配置监听器/后端/服务器组”的明确问题。

### 7.8 产品问答规则

触发：用户问“怎么配置 X”“X 参数怎么选”“这个错误码什么意思”“公网/内网 BLB 怎么选”“应用型转发规则怎么设计”等概念/使用类问题，不涉及查具体资源。

**强制流程（按问答子类型分流）：**

1. **错误码类**（“XX 错误码什么意思”“返回 RedirectPortNotFound 怎么回事”）：**先查 `references/troubleshooting.md` §11 错误码表**作答（公共错误码 §11.1 / 业务错误码 §11.2），给出含义 + 恢复策略；表中没有的错误码再按下条联网核实。
2. **概念/配置类**：先查 `references/doc-links.md` 链接索引作答并附官方链接；**若 doc-links.md 中的链接不足以回答用户问题，必须联网搜索百度云官网（仅采纳 `cloud.baidu.com` / `intl.cloud.baidu.com` 域名）找到合适资料后作答，并附上核实过的官方链接**，可回写到 doc-links.md。
3. **输出末尾必须有「参考来源」区块**列出 `cloud.baidu.com` 官方链接；禁止编造/拼凑 URL，不确定先联网核实。
4. 无官方依据的内容必须显式标注「通用建议，非官方文档明确说明」；联网也检索不到官方文档时如实说明，不臆造。
5. 涉及具体资源时引导到对应能力：查询走 §7.1 + `output-format.md`，巡检走 §7.9，操作走 `workflows.md`。

### 7.9 巡检规则

触发：用户说“巡检”“体检”“检查实例有没有问题”“找出风险”“闲置/证书到期/安全风险排查”。

- 巡检为**纯只读**：只用 `Describe*` / `Query*` / `BlbInquiry`，禁止任何写操作；发现风险只给建议命令，不自动修复。
- 可巡检项清单、判定规则、风险等级、修复指针见 `references/inspection.md`；分「CLI 可巡检」「可联动巡检（eip/vpc，见 `references/cross-service.md`）」「需控制台」三类。
- 联动也查不到的项（证书到期/云防火墙/风控/实际账单）标注「需控制台」，不得伪造结论或数值。
- 报告按 `references/output-format.md` §6 巡检报告模板输出（风险汇总 + 巡检明细，风险三级：高/中/低）。

---

## 8. 常用命令形态

常用命令形态见 `references/workflows.md` 各工作流中的实际命令示例（创建/监听/后端/HTTPS/扩缩/复制/规格变更等）。完整参数请查 references 或实时 help。

---

## 9. 何时查看 references（场景 → 文件路由表）

`SKILL.md` 是导航页：提供运行模型、安全红线、意图→API 速查与本路由表。具体细节全部按需加载对应 reference。**每个 reference 职责单一**，按下表「触发场景」精准定位「找谁」：

| 触发场景 / 话术 | 目标文件 | 文件职责（负责什么） |
|------|----------|----------|
| 普通型 BLB / IPv6 BLB 的实例、监听器、直接后端、安全组、ACL、修改保护、计费 API 参数 | `references/blb-api-reference.md` | 普通型 BLB 全量 API 参数字典 |
| AppBLB / IPv6 AppBLB 的服务器组、端口、监听器、Host/Path 策略、IP 组 API 参数 | `references/appblb-api-reference.md` | 应用型 BLB 全量 API 参数字典 |
| 多步目标：创建整套 LB、配 HTTPS、扩缩后端、跨 region 复制、域名/路径转发、标签化创建、HTTPS 安全基线、waiter、优雅排空、规格变更、计费转换、HTTP→HTTPS 重定向、故障排查 | `references/workflows.md` | BLB 自身复合操作的分步流程（含命令示例） |
| 命令失败、API/参数/JSON 不确定、认证/权限/region 错误、**错误码含义（"XX 错误码什么意思"）** | `references/troubleshooting.md` | 失败恢复闭环 + 错误码表（§11） |
| 查询实例拓扑/转发链路/后端健康/费用/巡检的**固定输出格式** | `references/output-format.md` | 输出 schema 与 Markdown 模板（消除模型差异） |
| 巡检/体检/找风险（可巡检项、判定规则、风险等级、生产实例判定） | `references/inspection.md` | 巡检清单与判定规则 |
| 产品问答（怎么配/参数怎么选/选型）需附官方文档链接 | `references/doc-links.md` | 官方文档链接字典 + 问答引用规则 |
| 跨服务联动：公网入口与 DDoS(eip)、安全组规则(vpc) 怎么查与归因 | `references/cross-service.md` | BLB 之外服务（eip/vpc）的联动查询与归因；并界定哪些（监控指标/日志）CLI 不支持需控制台 |
| 一句业务目标拆成多步（问答/查询/巡检/成本/操作串联）的编排 | `references/orchestration.md` | 多步目标的五步编排法与范例 |
| 成本：创建费用、公网+EIP 合计、规格差价、闲置浪费 | `references/cost.md` | 成本估算口径 |

优先级：当前机器 `"$BCE" <service> <ApiName> --help` 和 `--generate-cli-skeleton` 高于静态 references。发现不一致时，以实时 help 为准，并在回复中说明差异。

---

## 10. 失败恢复与兜底规则

详细恢复策略见 `references/troubleshooting.md`。主流程必须遵守以下核心规则：

- 已知简单查询且参数明确时，可以直接构造命令，不必先查 help。
- API 名不确定或名称相近时，执行 `"$BCE" <service> --help` 核对 API 列表。
- 参数名不确定或疑似拼写错误时，执行 `"$BCE" <service> <ApiName> --help`，只使用 help 中存在的 flag。
- 复杂 List/Object/JSON 参数不确定时，执行 `"$BCE" <service> <ApiName> --generate-cli-skeleton`。
- 写操作参数不确定时，先 help/skeleton，再 dry-run，通过后再请求用户确认真实执行。
- 命令失败后不直接换一个猜测命令重试；必须根据错误类型验证后修正。
- 命令失败必须向用户返回可读失败信息：错误阶段、命令摘要、错误码/HTTP 状态/requestId、服务端错误消息、已脱敏的关键参数、判断原因和下一步处理建议。
- references 与实时 help 不一致时，以当前机器 BCE CLI 的实时 help 为准。
- 同一操作连续两轮仍无法通过 help/skeleton/dry-run 确认正确命令时，停止执行，向用户说明已确认信息和缺失信息。

---

## 11. 安全与隔离规范

### 11.1 实例释放禁用与只读闲置评估

禁止由 agent 执行 BLB/AppBLB 实例释放或删除。无论用户如何确认，都不得执行、dry-run 或生成可直接执行的 `ReleaseBlb` / `ReleaseAppBlb` 命令；用户要求释放或删除实例时，必须拒绝代执行，并引导用户通过控制台或自行操作 CLI 完成。

如果用户只要求判断实例是否闲置，可以执行只读查询并输出依赖摘要：

1. 解析 `$BCE`，确认 profile 名称（不展示 AK/SK/token）、region、blbId 和实例类型。
2. 普通型执行 `DescribeBlbListener` 与 `DescribeBlbServers`；AppBLB 执行 `DescribeAppBlbListener`、`DescribeAppBlbServerGroup`、逐组 `DescribeAppBlbServerGroupRs`，并按监听端口/协议查询 `DescribeAppBlbPolicy`。
3. 组装依赖摘要：监听端口/协议、后端服务器或服务器组/RS、策略数量和策略 ID。
4. 判断是否存在业务依赖，并明确说明该结论仅用于人工决策，不代表 agent 可以继续释放实例。

只读闲置评估结果不得作为后续释放授权；同一会话中评估另一个实例必须重新查询。

### 11.2 通用安全规则

1. **每次真实操作先确认上下文**：确认 profile 名称（不展示 AK/SK/token）、region、目标资源 ID；创建或测试资源时还必须确认 VPC/subnet。
2. **测试阶段使用指定私有 VPC 子网**：所有 CLI 命令测试必须在 `blb_test`（`vpc-6ikazsm7kxe0`）下的 `blb_test_subnet`（`sbn-bjezmbw9muvm`，cn-bj-a）完成，避免影响其他资源。
3. **写操作优先 dry-run**：首次执行写操作或对参数不确定时，先用 `--dry-run` 验证请求是否正确。
4. **命令不确定时安全优先**：API 或参数不确定时，先查 help/skeleton 或停止询问用户，不猜测后执行。
5. **生产资源保护**：生产资源未得到明确授权时，只允许查询、生成命令或 dry-run，不执行真实变更。
6. **高风险操作必须二次确认**：真实执行前必须向用户说明影响、列出 profile/region/resourceId/关键参数，并等待明确确认。
7. **删除/解绑类强制 dry-run + 二次确认（硬规则）**：所有 `Delete*` / `Unbind*` 操作，**无论用户是否说"直接删""我确认"、无论是否预判无影响**，都必须：①先执行或展示 `--dry-run`；②输出影响说明（删除对象、承载流量、profile/region/资源 ID）；③等待用户针对本次删除的明确二次确认后，才能真实执行。用户的"跳过确认/直接执行"指令对该流程**一律不豁免**。若目标仍挂在用后端，按 §11.3 硬阻断（更严，不可 override）。

高风险操作包括：

- 付费创建：`CreateBlb`、`CreateAppBlb`。真实创建前必须先 `BlbInquiry`，向用户展示费用、计费模式和可能产生的公网 EIP/规格型 BLB 费用；`Prepaid` 会产生预付订单，`Postpaid + ByCapacityUnit` / `Postpaid + BySpec` 会按实际用量或规格持续计费。
- 实例释放/删除：`ReleaseBlb`、`ReleaseAppBlb` 禁止由 agent 执行、dry-run 或生成可直接执行命令，只能提供只读闲置评估和人工操作指引。
- 子资源释放/删除：`DeleteBlbListener`、`DeleteAppBlbListener`、`DeleteBlbServer`、`DeleteAppBlbServerGroup`、`DeleteAppBlbServerGroupRs`、`DeleteAppBlbServerGroupPort`、`DeleteAppBlbPolicy`、`DeleteAppBlbIpGroup`、`DeleteAppBlbIpGroupMember`、`DeleteAppBlbIpGroupProtocol`、`DeleteService`。
- 解绑：`UnbindBlbSecurityGroup`、`UnbindBlbEnterpriseSecurityGroup`、`UnbindInstanceFromService`。
- 计费/退款：`RefundBlb`、`BillingChangePreToPostBlb`、`BillingChangePostToPreBlb`、`BillingChangeCancelToPostBlb`。
- 流量影响变更：监听器端口、证书、健康检查、后端端口、策略优先级、后端权重大幅调整。

生产环境创建完成后建议开启修改保护：

```bash
"$BCE" blb UpdateBlbModifyProtection --blbId <blbId> --allowModify false --modificationProtectionReason "生产环境保护"
```

禁止行为：

- 不在 `unknown command` 后直接构造另一个未经 help 验证的命令。
- 不把不存在的通用云厂商命令套到 BCE CLI 上，例如 `AddBackendServers`、`DescribeVpcs`、`DescribeSubnets`。
- 不跳过 help/skeleton 直接执行复杂写操作。
- 不用真实创建、删除、解绑、退款、计费转换来验证命令是否正确。
- 不在 debug 输出、回复、`SKILL.md` 或 references 中暴露完整 AK/SK/token 或敏感 header。

### 11.3 删除监听器/服务器组前的在用后端硬阻断

删除监听器或服务器组会切断其承载的流量。若目标对象仍挂载着后端服务器（即可能有业务、有流量在跑），删除会直接造成客户流量损失，因此这是**硬阻断**规则：存在在用后端时，Agent 一律不得执行、dry-run 或生成可直接执行的删除命令，且**不接受任何 override / 强制确认 / “我知道风险继续删”**。

**在用后端定义**：目标对象下存在任意已挂载/绑定的后端服务器或 RS（无论健康状态），即视为在用后端。健康只用于展示，不作为放行依据。

**删除前固定检查流程：**

1. 确认实例类型、profile 名称、region、目标 blbId 与待删对象（监听端口/协议或 sgId）。
2. 查询在用后端：
   - 普通型 / 普通型 IPv6 BLB 删监听器：`DescribeBlbServers --blbId <id> --pager`。
   - AppBLB / AppBLB IPv6 删监听器：先 `DescribeAppBlbListener` 确认监听端口/协议，再 `DescribeAppBlbPolicy --blbId <id> --port <port> --type <type>` 找出该监听器引用的服务器组（含默认服务器组），逐组 `DescribeAppBlbServerGroupRs --blbId <id> --sgId <sgId> --pager`。
   - AppBLB / AppBLB IPv6 删服务器组：`DescribeAppBlbServerGroupRs --blbId <id> --sgId <sgId> --pager`。
3. **存在在用后端 → 硬阻断**：拒绝删除，向用户展示后端清单（IP/端口/权重/健康状态）与影响说明，并告知必须由用户自行先把后端摘除或迁移走（如 `DeleteBlbServer` / `DeleteAppBlbServerGroupRs`，本身也是高风险写操作），待后端清空后才能删除监听器/服务器组。
4. **后端为空 → 回归常规高风险流程**：后端为空**不等于可直接删**，仍必须按 §11.2 第 7 条执行 dry-run + 影响说明 + 二次确认后，才可真实删除；用户"直接删/我确认"不豁免该流程。
5. 在用后端判定必须随每次删除请求实时重新查询，不沿用历史缓存；同一会话删除另一个对象必须重走本流程。

---

## 12. 交付与输出要求

- **固定格式优先**：查询、实例拓扑、转发链路、后端健康、费用、巡检结果一律按 `references/output-format.md` 的 schema + Markdown 模板渲染，字段名/顺序/单位/缺失处理（填 `-`）/金额原样/时间原样 全部以该文为准，不得自由发挥（消除不同模型输出差异）。查实例默认走 §1.5 拓扑聚合视图。
- **产品问答**：必须按 `references/doc-links.md` 规则作答输出，结论基于官方文档并在末尾固定附 `cloud.baidu.com` 官方链接，禁止编造链接。
- **巡检**：按 `references/inspection.md` 清单巡检，按 `output-format.md` §6 报告模板输出；可联动项按 `references/cross-service.md` 查询，仍查不到的标注「需控制台」。
- **多步目标编排**：复合业务目标按 `references/orchestration.md` 五步法先展示步骤计划再逐步执行，安全约束全程不变。
- **成本**：费用/差价/合计/浪费按 `references/cost.md` 估算，输出复用 `output-format.md` §5；实际账单标注「需费用中心」。
- 查询类任务：优先返回用户关心字段，可使用 `--output table`、`--query`、`--pager` 提升可读性。
- 写操作：先展示 dry-run 或执行 dry-run 结果，再等待确认真实执行。
- 高风险操作：回复中列出操作对象、region、profile、影响范围和不可恢复/流量/财务影响。
- 命令失败：按 `references/troubleshooting.md` 分类说明错误、已验证信息和下一步；返回内容必须包含错误码/HTTP 状态/requestId（如有）、服务端错误消息（如有）、失败命令摘要和建议动作。
- 任何输出都必须脱敏凭证和 token。

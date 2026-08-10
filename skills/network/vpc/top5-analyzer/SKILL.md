---
name: top5-analyzer
description: 百度云网络服务线上 Top5 5xx 异常分析工具。当用户输入包含"top5分析"关键词，或提供格式为"LOGICAL_XXX服务5xx异常接口排序"/"XXX异常分析"的 Top5 报告时，立即使用此 skill。自动解析入参、直接基于 top5_input.py 输出数据定位根因，并可将分析结果存入如流知识库 Top5 文档（含"存入文档"关键词时触发）。支持 VPC、EIP、BLB 等百度云网络服务。
version: 1.0.0
---

# Top5 Analyzer - 线上 Top5 异常分析

解析 Top5 5xx 异常报告，直接基于 top5_input.py 输出数据定位每个接口的根本原因，并可选择将结果写入如流知识库。

## 何时使用

**⚡ 立即触发此 skill 的场景**：

- 用户输入包含 **"top5分析"** 关键词

**典型触发示例**：
- ✅ "top5分析"
- ✅ "帮我做一下 top5 分析"
- ✅ "top5分析并存入文档"

---

## 执行流程

> **重要**：全流程自动执行，不要在中间步骤停下来等待用户确认，直到最后统一输出结果。

### 第一步：判断输出模式

从用户输入中判断是否包含 **"存入文档"** 及相似关键词：

- **不含"存入文档"**：只在界面展示分析结果，不操作知识库
- **含"存入文档"**：分析完成后，将结果写入如流知识库 Top5 文档

---

### 第二步：获取 Top5 输入数据

通过 `top5-analyzer/scripts/top5_input.py` 从 SkyWalking 统计 VPC/EIP/BLB 所有 region 近七天的 5xx 异常，所有5xx异常都要放入文档，不是只写5个异常，分别生成三份报告作为后续分析的输入：

```bash
# 生成 EIP 近7天 top5 输入
python3 top5-analyzer/scripts/top5_input.py --service EIP --days 7

# 生成 VPC 近7天 top5 输入
python3 top5-analyzer/scripts/top5_input.py --service VPC --days 7

# 生成 BLB 近7天 top5 输入
python3 top5-analyzer/scripts/top5_input.py --service BLB --days 7
```

每条命令输出的文本即为对应服务的 Top5 分析输入，格式与第三步所描述的格式完全一致。


**注意**:需要获取`top5_input.py`执行之后的全量数据，这里不能因为数据庞大就截取一部分，需要全部获取，获取全量数据之后，需要按照`filter-url.md` 文件中的规则对特殊数据进行处理，之后步骤中使用的必须是经过处理之后的数据。

**VPC / EIP / BLB 分开分析、分开写入文档**：三个服务各自独立执行完整流程（第三步～第七步），最终分别写入三个独立文档（若含"存入文档"关键词）。


---

### 第三步：解析入参

将第二步按照`filter-url.md` 文件处理之后的数据作为入参，提取结构化分析数据。输出格式固定为完整 Top5 汇总报告：

```
LOGICAL_EIP服务5xx异常接口排序（近7天）
接口：POST:/v1/order_executor/execute，异常数：13

异常详细分析
Top1 POST:/v1/order_executor/execute，异常数：13，详情如下
服务：LOGICAL_EIP_GZ
5xx异常数量：3，异常分为1类

第1类异常
endpoint：/orders/getOrderForExecutorByServiceType，异常数量：3

原因1有1个异常，异常链路简要信息示例：
{"requestId":"3c7101f3-...","accountId":"","requestTime":"2026-05-07 14:03:20","errorMessage":"..."}
```

#### 提取信息

从入参中提取以下结构化信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| 服务类型 | 从 `LOGICAL_EIP_XX` 中提取 | `EIP` |
| 接口列表 | 所有异常接口及其异常数 | `POST:/v1/order_executor/execute → 13` |
| 每个接口的下游 endpoint | 第X类异常的 `endpoint：` 字段 | `/orders/getOrderForExecutorByServiceType` |
| requestId 列表 | 每条异常链路 JSON 中的 `requestId` | `3c7101f3-f557-4e6b-9bba-b1dd830bde18` |
| region | 从 `LOGICAL_EIP_GZ` 中提取地域 | `gz` |
| accountId | 从异常链路 JSON 中提取 | `4c8b125778374a898b17f6c9d4967c0d` 或空 |
| requestTime | 从异常链路 JSON 中提取 | `2026-05-07 14:03:20` |
| errorMessage | 从异常链路 JSON 中提取 | `uuid: xxx, accountId: null` |

**地域映射**（从 serviceCode 后缀提取）：

| serviceCode 后缀 | region |
|-----------------|--------|
| `_BJ` | `bj` |
| `_GZ` | `gz` |
| `_SU` | `su` |
| `_CD` | `cd` |
| `_YQ` | `yq` |
| `_HKG` | `hkg` |
| `_BD` | `bd` |
| `_FWH` | `fwh` |
| `_NJ` | `nj` |

---

### 第四步：读写分类 & Top5 筛选
本步骤的数据来源是第三步处理输出的数据
#### 4.1 特殊接口预定义

以下接口直接使用预定义的读写类型，无需额外判断：

| 接口 | 接口类型 |
|------|----------|
| `POST:/api/logical/eip/v1/price` | 读 |
| `POST:/api/logical/eip/v1/eip/gip/status` | 读 |
| `POST:/v1/order_executor/execute` | 写 |
| `GET:/v1/order_executor/check` | 写 |


#### 4.2 VPC 服务特殊归并规则

在对接口进行分类和排序**之前**，如果VPC服务中包含nat和ipv6gateway的接口，需将以下 VPC 接口迁移到 EIP 服务中一起参与 EIP 的排序：

- 路径中包含 `nat`（大小写不敏感）的接口
- 路径中包含 `ipv6gateway`（大小写不敏感）的接口

**效果**：这些接口从 VPC 接口列表中移除，加入 EIP 接口列表，最终在界面输出和文档写入时均归入 EIP 服务，VPC 服务中不展示。

#### 4.3 判断读写类型

根据接口的 HTTP 方法和 URL 路径语义综合判断，同时结合 SkyWalking 链路中的 endpointName、下游调用信息辅助确认：

| 判断依据 | 读接口 | 写接口 |
|---------|--------|--------|
| HTTP 方法 | `GET` | `PUT`、`DELETE` |
| POST 语义 | 路径末段含 `list`、`query`、`get`、`show`、`check`、`detail`、`status`、`info` 等查询语义 | 路径末段含 `create`、`update`、`delete`、`execute`、`import`、`bind`、`unbind`、`add`、`remove` 等变更语义 |
| SkyWalking 链路 | 下游调用为只读操作（SELECT、GET 等） | 下游调用包含写操作（INSERT、UPDATE、DELETE 等） |

**无法确定时**：可以先把该url执行第五步bls日志分析，根据日志分析进行确定。

#### 4.4 读写分开排序，各取 Top5

分别对每个服务（VPC / EIP 含 NAT&IPv6Gateway / BLB）的**读接口**和**写接口**按异常数从高到低排序：

- 读接口取前 5 名（TOP1～TOP5），超出部分**丢弃，不参与后续 BLS 分析和文档写入**
- 写接口取前 5 名（TOP1～TOP5），超出部分同上丢弃

> **后续第五步（BLS 日志分析）仅针对筛选后的接口执行，被丢弃的接口不做任何分析。**

---

### 第五步：BLS 日志分析（调用 alert-analyzer 流程）

在第四步数据处理之后，每个服务最多包含十个不同的url(即五个写请求和五个读请求)，并且经过第二步中的 `filter-url.md` 归并后，相同接口模式的多条链路已聚合为同一类。**每类异常只需取其中一条代表性链路执行分析，同类其余链路直接复用该根因结论，不重复查询。**

> **无论 errorMessage 是否为空，都必须对每一类异常执行本步骤。**

#### 5.1 执行分析

对每一类异常的代表性链路，**执行 `alert-analyzer/SKILL.md` 中第二步（BLS 日志查询）、第三步（代码定位分析）、第四步（根因分析）、第五步（生成报告）的完整流程**，以 `requestId` + `requestTime` + `log-store` 为入口，**跳过 alert-analyzer 第一步**（无需告警 ID）。

查询参数推导规则：

```python
# 从入参直接推导
service_type = service_code.split('_')[1].lower()   # eip
region = service_code.split('_')[-1].lower()        # bj
log_store = f"logical-{service_type}-debug-{region}"
query_start = requestTime - 10min
query_end   = requestTime + 10min

#### 5.2 输出映射

alert-analyzer 分析完毕后，将报告内容按如下规则填入第六步（报告中有哪些章节写哪些，没有输出的章节不强求）：

| alert-analyzer 报告章节 | 填入位置 |
|------------------------|---------|
| `## 3. 日志分析` + `## 4. 代码定位` + `## 5. 根因分析` + `## 6. 解决方案` | **备注** → `BLS分析` 字段（完整内容） |
| `## 5. 根因分析` + `## 6. 解决方案` | **失败原因** 字段（只写结论，不写堆栈） |

---

### 第六步：整理分析结果并输出

**失败原因**和**备注**必须基于第五步 BLS 日志分析的结果撰写：

- **失败原因**：基于 alert-analyzer 输出报告的 `## 5. 根因分析` 和 `## 6. 解决方案`，清晰说明该接口抛出 5xx 的真正原因及解决方案，只写结论，不写堆栈
- **备注**：将每条异常链路的 region / requestId / requestTime / endpoint 及 alert-analyzer 完整分析报告（日志分析、代码定位、根因分析、解决方案）按规范格式整理

如果用户提示词中包含"存入文档"或相近语句，那么不需要再界面输出；不存入文档则在界面输出，按以下格式在界面输出分析结果：

```
## 异常分析结果

### 服务：LOGICAL_EIP | 分析时间：YYYY-MM-DD

---

#### 读接口

#### Top1 GET:/api/logical/eip/v1/list（异常数：1）

**接口类型**：读
**服务模块**：logical-eip

**失败原因**：
1. 调用 /api/logical/bcc/v1/instance/listServersByUuids 超时（SocketTimeoutException: Read timed out）

**详细信息**：

1. 第1类异常

  1.1 region:bj reqId：4ec55516-d283-4ef7-903a-be65819f9bc1 time:2026-05-07 05:22:17
      endpoint：/api/logical/bcc/v1/instance/listServersByUuids

      BLS分析：
        下游调用：GET http://bcc.bce-internal.baidu.com/... → 无响应（SocketTimeoutException: Read timed out）
        根因：BCC 服务响应超时
        解决方案：联系 BCC 团队排查超时原因，或调整超时配置

---

#### 写接口

#### Top1 POST:/v1/order_executor/execute（异常数：13）

**接口类型**：写
**服务模块**：logical-eip

**失败原因**：
1. 调用 /orders/getOrderForExecutorByServiceType 返回 404，Order 服务不存在对应订单（OrderNotFoundException: uuid=88c2e3bd, accountId=null），导致上层抛出 500

**详细信息**：

1. 第1类异常

  1.1 region:bj reqId：a00b8fae-c478-4719-b5ee-f8a9acd60932 time:2026-05-07 14:07:49
      endpoint：/orders/getOrderForExecutorByServiceType

      BLS分析：
        下游调用：POST http://order.bce-internal.baidu.com/orders/getOrderForExecutorByServiceType → HTTP 404 {"code":"OrderNotFoundException"}
        根因：Order 服务中订单不存在（uuid=88c2e3bd, accountId=null）
        解决方案：检查订单是否已被删除，或业务侧避免对不存在的订单发起执行

  1.2 region:gz reqId：3c7101f3-f557-4e6b-9bba-b1dd830bde18 time:2026-05-07 14:03:20
      ...（同类异常依次列出）

---
```

---

### 第七步：存入文档（仅含"存入文档"关键词时执行）

**注意**：如果某个服务近七天无5XX异常请求，则不用创建文档和表格，也不用填写信息

#### 7.1 确定文档位置

知识库目录结构：

```
https://ku.baidu-int.com/knowledge/HFVrC7hq1Q/KzHUM_sAtc/r4rCaTKEDW/FjMURwR5g049EE（总目录）
  └─ EIP/（第一级：按服务类型，doc_id 需查询）
      └─ 2026/（第二级：按年份，doc_id 需查询）
          └─ 线上Top5报错-2026.05.13（按当天日期命名）
```

**确定各级目录 doc_id**：通过 `ku-doc-manage` 的 `query-repo` 查询子文档列表，找到对应名称的目录。

```bash
export SKILL_DIR=<ku-doc-manage路径>

# 查询总目录下的服务类型子目录
$SKILL_DIR/bin/ku query-repo \
  --repo-id r4rCaTKEDW \
  --parent-doc-id FjMURwR5g049EE

# 找到 EIP 目录 doc_id 后，查询年份子目录
$SKILL_DIR/bin/ku query-repo \
  --repo-id r4rCaTKEDW \
  --parent-doc-id <EIP目录doc_id>
```

**文档命名规则**：`线上Top5报错-{YYYY}.{MM}.{DD}`（当天日期，如 `线上Top5报错-2026.05.13`）

#### 7.2 创建文档和表格

查询年份目录下的文档列表，检查是否已存在当天命名的文档：

- **已存在**：跳过创建，直接执行 **7.3 填充表格**
- **不存在**：创建文档后执行 **7.3 填充表格**

**创建文档**（ku-doc-manage 使用数字员工身份认证，无需 token 配置）：

模板文档 doc_id：`CG7474RARog9RS`，先读取其内容作为表格模板：

```bash
$SKILL_DIR/bin/ku query-content --doc-id CG7474RARog9RS --protocol 2
```

然后创建新文档，将模板表格内容写入新文档，表头只写文字，不需要带#号等符号：

```bash
$SKILL_DIR/bin/ku create-doc \
  --repo-id r4rCaTKEDW \
  --parent-doc-id <年份目录doc_id> \
  --title "线上Top5报错-{YYYY}.{MM}.{DD}" \
  --content "<模板表格的 Markdown 内容>"
```

#### 7.3 填充表格

> **⚠️ 强制**：写入表格必须通过 `edit-content --operations` 以 JSON `table` 节点结构写入，**禁止**用 `create-doc --content` 写 markdown 表格（单元格内含换行会导致表格结构崩塌）。备注等多行内容，在 `table-cell.children` 中用多个 `paragraph` 节点表示，不得在字符串中嵌入 `\n`。
>
> **⚠️ 严禁创建新文档**：填充过程中如遇任何问题（写入失败、内容有误等），只能在当天已有文档（doc_id 不变）上重新调用 `edit-content --operations` 覆盖写入，**禁止**通过 `create-doc` 创建新文档来替代修复。

**`--operations` 格式（必须严格遵守）**：

```json
[
  {
    “mode”: “cover”,
    “withNewCard”: true,
    “json”: [
      {
        “type”: “table”,
        “sticky”: false,
        “data”: { “headless”: false },
        “children”: [
          {
            “type”: “table-row”,
            “children”: [
              {
                “type”: “table-cell”,
                “data”: { “rowspan”: 1, “colspan”: 1 },
                “children”: [
                  { “type”: “paragraph”, “children”: [{ “text”: “单元格内容” }] }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
]
```

> **常见错误**：不要使用 `[{“type”: “insert”, “node”: {...}}]` 格式——该格式 API 会返回 success 但实际不写入任何内容。正确格式是顶层数组元素必须包含 `mode`（`cover` 或 `append`）和 `json` 字段。

**注意**
1. 严格按照 `top5-analyzer/references/top5-doc-write.md` 中的规则，使用`ku-doc-manage`将分析结果整理为表格行写入文档，如果用到`edit-content`,username使用ai_consolenet，表格格式严格按照模板文档 doc_id：`CG7474RARog9RS`，编写规则严格按照`top5-analyzer/references/top5-doc-write.md`中的规则
2. 所有信息必须写入表格，**禁止出现**”BLS日志未查询”等相关字样，skywalking中查询出来的请求bls一定要查询

**备注字段格式**（对应 `top5-doc-write.md` 中的备注规范）：

```
{序号}. 第{序号}类异常

  {序号}.{子序号} region:{region} reqId：{requestId} time:{requestTime}
      endpoint：{err_endpoint}

      BLS分析：
        {alert-analyzer 报告中 ## 3/4/5/6 章节的完整内容}
```

---

#### 7.4 验证表格内容

填充表格完成后，**必须**通过 `ku-doc-manage` 读取文档内容，验证写入是否正确：

```bash
$SKILL_DIR/bin/ku query-content --doc-id <doc_id> --protocol 2
```

对照 `top5-doc-write.md` 中所有列的规则，逐列验证：

1. **表头**：必须包含以下所有列（顺序一致）：`业务方向`、`TOP`、`服务模块`、`接口类型（读/写）`、`API名称（同步/异步）`、`总5xx错误请求数/周`、`失败原因`、`优化目标（解决方案）`、`排期`、`有无大客户`、`备注`
2. **业务方向**：填写值与文档所在目录服务一致（VPC/EIP/BLB），不能错填为其他服务
3. **TOP**：读接口和写接口分别从 TOP1 开始独立排序，读接口在上、写接口在下，读和写最多分别包括五个接口
4. **服务模块**：填写正确的 logical 服务名（logical-vpc / logical-eip / logical-blb）
5. **接口类型（读/写）**：基于 BLS 分析实际判断，不能凭空猜测
6. **API名称**：格式为 `{HTTP方法}:{路径}`，路径中动态参数已按 filter-url.md 归并
7. **总5xx错误请求数/周**：与 top5_input.py 输出的异常数一致，归并后需加总
8. **失败原因**：非空，按类别编号，包含下游服务、错误信息及解决方案结论
9. **优化目标**、**排期**、**有无大客户**：留空
10. **备注**：每条包含 “region / reqId / time / endpoint / BLS分析” 全部必填字段，**并且检查“region / reqId / time”等字段对应的值是否填写正确，务必根据region和reqId去bls日志中查询一遍，确保可以根绝region和reqId唯一锁定该接口的日志，如果查询不到对应的bls日志，那么就重新分析此接口，一直到确保可以根据region和reqId正确查询到bls日志为止，“region / reqId / time”等字段不正确的话必须修改并重新填写**，同类异常超过2条只展示2条
11. **接口总数**：文档中写入的数据行总数（去除表头）必须与经 `第四步、读写分类 & Top5 筛选` 之后的接口总数一致；若发现行数不符，说明有接口被遗漏或重复写入，必须重新填充

**如果发现以下任一问题，立即在原文档上重新执行填充表格（重新调用 `edit-content --operations`，使用同一 doc_id）**：

- 表头缺少任意列或列名不正确
- 文档 `text` 字段无数据行（只有表头或为空）
- 任意数据列的内容为空（优化目标/排期/有无大客户除外）
- 备注中缺少 region / reqId / time / endpoint / BLS分析 任一字段
- 业务方向与文档所在服务目录不匹配
- 写入的数据与分析结果不一致
- 文档数据行总数与经 `第四步、读写分类 & Top5 筛选` 之后的接口总数不一致（有接口遗漏或重复）

> **⚠️ 严禁创建新文档**：7.3 填充和 7.4 验证过程中，无论出现何种问题，**禁止**通过 `create-doc` 创建新文档来替代修复。只能在当天已有文档（doc_id 不变）上重新调用 `edit-content --operations` 覆盖写入。唯一允许创建新文档的时机是 **7.2 中确认当天文档不存在**时。

---

### 第八步：输出完成通知

所有服务分析及写入操作完成后，在界面输出完成通知。

#### 仅界面输出时（不含"存入文档"）

```
✅ Top5 分析完成
```

#### 写入文档时（含"存入文档"）

在完成通知中附上各服务对应的文档链接（doc_id 为第七步创建或查询到的文档 ID）；若某个服务本周无 5xx 异常数据，则在对应行注明：

```
✅ Top5 分析完成，结果已写入如流知识库：

- VPC：https://ku.baidu-int.com/knowledge/HFVrC7hq1Q/KzHUM_sAtc/r4rCaTKEDW/{vpc_doc_id}
- EIP：该服务本周无 5xx 异常请求
- BLB：https://ku.baidu-int.com/knowledge/HFVrC7hq1Q/KzHUM_sAtc/r4rCaTKEDW/{blb_doc_id}
```

---

## 工具说明

### top5_input.py

**位置**：`top5-analyzer/scripts/top5_input.py`

```bash
# 生成 EIP 近7天 top5 输入
python3 top5-analyzer/scripts/top5_input.py --service EIP --days 7

# 生成 VPC 近7天 top5 输入
python3 top5-analyzer/scripts/top5_input.py --service VPC --days 7

# 生成 BLB 近7天 top5 输入
python3 top5-analyzer/scripts/top5_input.py --service BLB --days 7

# 显示详细调试日志
python3 top5-analyzer/scripts/top5_input.py --service EIP --verbose
```

输出数据包含每条异常的：`requestId` / `accountId` / `requestTime` / `errorMessage` / `err_endpoint` / region（从 serviceCode 后缀提取）。获取数据后必须执行第五步 BLS 日志分析，提取每条异常的真正根因。

### ku-doc-manage bin/ku

**位置**：`ku-doc-manage/bin/ku`

认证方式：默认使用数字员工身份认证（AK/SK），无需额外 token 配置。

```bash
export SKILL_DIR=<ku-doc-manage绝对路径>
chmod +x $SKILL_DIR/bin/ku

# 查询文档列表
$SKILL_DIR/bin/ku query-repo --repo-id <repoId> --parent-doc-id <docId>

# 读取文档内容
$SKILL_DIR/bin/ku query-content --doc-id <docId> --protocol 2

# 创建文档
$SKILL_DIR/bin/ku create-doc \
  --repo-id <repoId> \
  --parent-doc-id <parentDocId> \
  --title "<标题>" \
  --content "<Markdown内容>"
```

---

## 注意事项

1. **不含"存入文档"时**：只输出界面分析结果，不执行任何知识库操作
2. **VPC/EIP/BLB 分开处理**：三个服务各自独立分析，分别写入三个独立文档
3. **多地域归并**：相同接口、相同下游 endpoint、相同 error 的不同地域请求，在备注中归并为同一类（1.1、1.2、1.3...）
4. **工作目录**：执行脚本时在项目根目录 `net-skill/` 下执行，或使用脚本绝对路径

???? **表格填充详细规则**请查看 `references/top5-doc-write.md`

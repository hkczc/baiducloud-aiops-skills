# 知识库 Top5 文档表格填充规则

本文档定义如何将 top5-analyzer 的分析结果填充到知识库 Top5 文档（如流知识库）的表格中。

---

    
## 表格列说明与填写规则

### 1. 业务方向

根据 top5 分析的服务类型填写，一定要确认好文档位置对应的什么业务fang，对号入座，例如不要在VPC的目录下面的文档把业务服务写成了BLB等类似情况。

| 服务 | 填写值 |
|------|--------|
| VPC  | VPC    |
| EIP  | EIP    |
| BLB  | BLB    |
| NAT  | EIP    |

示例：`EIP`

---

### 2. TOP 与 接口类型（读/写）

- 根据bls分析实际判断接口是**读接口**还是**写接口**，不能凭空猜测，要保证准确性：
  - 读接口：`GET`、`POST`（查询类）
  - 写接口：`POST`（创建/修改）、`PUT`、`DELETE`
  **比如**
  POST:/v1/order_executor/execute是写接口
  POST:/api/logical/eip/v1/eip/gip/status是读接口

- 读写分开独立排序，并且在表格中，读接口在上面，写接口在下面
  - 读接口按异常数从大到小排列 TOP1、TOP2、...
  - 写接口按异常数从大到小排列 TOP1、TOP2、...
  - 读接口和写接口最多只有五个，即TOP1~TOP5

示例：

```
TOP1，接口类型：读
TOP2，接口类型：读
TOP1，接口类型：写
```

---

### 3. 服务模块

根据服务类型填写对应的 logical 服务名。

| 服务 | 填写值        |
|------|---------------|
| VPC  | logical-vpc   |
| EIP  | logical-eip   |
| BLB  | logical-blb   |

示例：`logical-eip`

---

### 4. API名称（同步/异步）

填写 top5 分析中异常的接口 URL（含 HTTP 方法）。

格式：`{HTTP方法}:{路径}`

示例：`POST:/v1/order_executor/execute`

---

### 5. 总5xx错误请求数/周

按 URL 粒度填写该接口的异常总数。

> 来源：top5 分析报告中"Top1 POST:/v1/order_executor/execute，异常数：13"

示例：`13`

---

### 6. 失败原因

内容来源于 alert-analyzer 分析报告的 `## 5. 根因分析` 和 `## 6. 解决方案` 章节，按异常种类逐条编写，只写结论，不写堆栈。每类给出简要结论，每条结论之间要换行，保证行号在每行的最前面，有几类异常失败原因就写几类，和备注中对齐。

格式：
```
1. 结论描述（调用哪个下游、返回什么错误；解决方案）
2. 结论描述（调用哪个下游、返回什么错误；解决方案）
3. 结论描述（调用哪个下游、返回什么错误；解决方案）
```

示例：
```
1. 调用 /orders/getOrderForExecutorByServiceType 返回 404，Order 服务订单不存在（OrderNotFoundException，uuid=88c2e3bd, accountId=null）；建议业务侧避免对不存在的订单发起执行请求
2. 调用 /api/logical/bcc/v1/instance/listServersByUuids 超时（SocketTimeoutException: Read timed out）；建议联系 BCC 团队排查超时原因或调整超时配置
3. 调用 /json-api/v1/eip/gip/status 返回 text/plain，SDK 反序列化失败（MessageBodyReader not found）；建议修复响应 Content-Type 或调整 SDK 反序列化策略
```

---

### 7. 优化目标（解决方案）

**不需要填写**，留空。

---

### 8. 排期

**不需要填写**，留空。

---

### 9. 有无大客户

**不需要填写**，留空。

---

### 10. 备注

按异常种类逐条编写，每类异常下列出所有对应的请求信息（来自 alert-analyzer 分析结果），每条结论之间要回车，保证行号在每行的最前面，如果同类异常的reqId超过两个，那么只展示两个即可，小于等于两个的都进行展示。

#### 格式规范

```
{序号}. 第{序号}类异常

  {序号}.{子序号} region:{region} reqId：{requestId} time:{requestTime}
      endpoint：{异常 endpoint}

      BLS分析：
        {alert-analyzer 报告中 ## 3. 日志分析 / ## 4. 代码定位 / ## 5. 根因分析 / ## 6. 解决方案 的完整内容，有哪些章节写哪些}
```
**注意**，以上信息中**region/reqId/time/endpoint不可省略，一定要填写。region/reqId/time 从 bls日志中 获取，确保可以根据region和reqId唯一查询到该接口近七天对应的bls日志，BLS分析内容来自 alert-analyzer 输出报告，以上内容务必保证真实，必须可以在skywalking和bls中近七天的日志中明确查出来。**

> **写入说明**：上述多行备注写入表格时，每一行对应 `table-cell` 的一个 `paragraph` 子节点，不能拼接成含 `\n` 的单一字符串。须通过 `edit-content --operations` JSON 方式写入。

#### 示例

```
1. 第1类异常

  1.1 region:bj reqId：a00b8fae-c478-4719-b5ee-f8a9acd60932 time:2026-05-07 14:07:49
      endpoint：/orders/getOrderForExecutorByServiceType

      BLS分析：
        下游调用：POST http://order.bce-internal.baidu.com/orders/getOrderForExecutorByServiceType → HTTP 404 {"code":"OrderNotFoundException","message":"uuid: 88c2e3bd, accountId: null"}
        根因：Order 服务中订单不存在（uuid=88c2e3dbd49d4dc4810bcfa9155c9a5e, accountId=null）
        代码定位：OrderExecutorController.execute(line 68) → OrderClient.getOrderForExecutor(line 118)
        解决方案：检查订单是否已被删除，或业务侧避免对不存在的订单发起执行请求

  1.2 region:gz reqId：3c7101f3-f557-4e6b-9bba-b1dd830bde18 time:2026-05-07 14:03:20
      endpoint：/orders/getOrderForExecutorByServiceType

      BLS分析：
        下游调用：POST http://order.bce-internal.baidu.com/orders/getOrderForExecutorByServiceType → HTTP 404 {"code":"OrderNotFoundException","message":"uuid: 7acfde94, accountId: null"}
        根因：Order 服务中订单不存在（uuid=7acfde94adfd45f183b77329787506b8, accountId=null）
        解决方案：同上

2. 第2类异常

  2.1 region:bj reqId：4ec55516-d283-4ef7-903a-be65819f9bc1 time:2026-05-07 05:22:17
      endpoint：/api/logical/bcc/v1/instance/listServersByUuids

      BLS分析：
        下游调用：GET http://bcc.bce-internal.baidu.com/api/logical/bcc/v1/instance/listServersByUuids → 无响应（SocketTimeoutException: Read timed out）
        根因：BCC 服务响应超时，调用方设置了 15s 异步超时未收到响应
        堆栈：
          SocketTimeoutException: Read timed out
          at BccServiceClient.listServers(BccServiceClient.java:88)
          at EipServiceImpl.getEipDetail(EipServiceImpl.java:142)
        解决方案：联系 BCC 团队排查超时原因，或调整超时配置增加容错重试
```

---

## 完整填写示例（对应 2026-05-07 LOGICAL_EIP 分析）

| 业务方向 | TOP | 服务模块 | 接口类型（读/写） | API名称（同步/异步） | 总5xx错误请求数/周 | 失败原因 | 优化目标 | 排期 | 有无大客户 | 备注 |
|---------|-----|---------|----------------|--------------------|--------------------|---------|---------|------|-----------|------|
| EIP | TOP1 | logical-eip | 读 | GET:/api/logical/eip/v1/list | 1 | 1. 调用 BCC /api/logical/bcc/v1/instance/listServersByUuids 超时（SocketTimeoutException: Read timed out） | | |  | 见下方备注格式 |
| EIP | TOP2 | logical-eip | 读 | POST:/api/logical/eip/v1/eip/gip/status | 1 | 1. 调用 /json-api/v1/eip/gip/status 返回 text/plain，SDK 反序列化失败（MessageBodyReader not found） | | |  | 见上方备注格式 |
| EIP | TOP1 | logical-eip | 写 | POST:/v1/order_executor/execute | 13 | 1. 调用 /orders/getOrderForExecutorByServiceType 返回 404，Order 服务订单不存在（OrderNotFoundException，accountId: null） | | |  | 见上方备注格式 |

---

## 注意事项

1. **TOP 排序独立**：读接口和写接口分别从 TOP1 开始排序，互不干扰
2. **多地域相同根因**：同一类异常（相同下游 endpoint + 相同 error）的不同地域请求，归并到同一个序号下（1.1、1.2、1.3...）

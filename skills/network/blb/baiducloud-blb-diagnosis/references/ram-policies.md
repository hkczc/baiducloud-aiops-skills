# 接口过滤与归并规则

## 1. 归并规则

以下接口在输出或写入文档时，统一归并为一个 TOP，使用标准化路径表示（路径中的动态参数统一用变量替代，不写具体入参）。

### 示例

| 原始接口 | 归并后 TOP |
|---------|-----------|
| `PUT /billing/resources/0c0b3c9dbb6e41308d3bfd587d908922/et/resources/dcphy-6qz6s6qpf3ws` | `PUT /billing/resources/{accountId}/{service}/resources/{resourceId}` |
| `PUT /billing/resources/7b11001f03b64e43843b6159501fdf0e/et/resources/dcphy-9zbhp4z204u0` | `PUT /billing/resources/{accountId}/{service}/resources/{resourceId}` |
| `POST /api/logical/appblb/v1/blbrs/lb-a6bba18f/create` | `POST /api/logical/appblb/v1/blbrs/{lbId}/create` |
| `POST /api/logical/appblb/v1/blbrs/lb-1d2c0030/create` | `POST /api/logical/appblb/v1/blbrs/{lbId}/create` |
| `GET /v1/eiptp/tp-uJ4PcnwA6r` | `GET /v1/eiptp/tp-{tpId}` |
| `GET /v1/eiptp/tp-jsal9a8hu9` | `GET /v1/eiptp/tp-{tpId}` |

> 以此类推，所有路径中的动态 ID 字段均用 `{变量名}` 形式统一替代，但是GET /v1/eiptp 和 GET /v1/eiptp/{id}这两个不是一类，不能归并，上面说的归并是把路径中带实参的用变量表示，URL中/数量不一样的不是一类



## 2. 过滤规则

以下接口在输出或写入文档时直接忽略，不统计、不展示：

| 规则 | 说明 |
|------|------|
| `GET:/actuator/health` | 健康检查请求，非业务异常，过滤掉 |
| `POST:/` | 非业务接口，过滤掉 |
| `POST:/jars/upload` | 非业务接口，过滤掉 |
| `PUT:/billing/resources/{accountId}/{service}/resources/{resourceId}` | VPC服务中如果出现此接口，那么过滤掉，EIP服务和BLB服务的不需要过滤 |





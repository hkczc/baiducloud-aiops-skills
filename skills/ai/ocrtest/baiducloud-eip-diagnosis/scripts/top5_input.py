#!/usr/bin/env python3
"""
Top5 异常输入数据生成脚本

从 SkyWalking 统计 VPC/EIP/BLB 所有 region 近七天的 5xx 异常，
生成 top5-analyzer skill 所需的输入格式。

用法：
  python3 top5-analyzer/scripts/top5_input.py --service EIP
  python3 top5-analyzer/scripts/top5_input.py --service VPC
  python3 top5-analyzer/scripts/top5_input.py --service BLB
  python3 top5-analyzer/scripts/top5_input.py --service EIP --days 7
  python3 top5-analyzer/scripts/top5_input.py --service EIP --verbose
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional


# -----------------------------------------------------------------------
# SkyWalking 配置
# -----------------------------------------------------------------------

# Region -> SkyWalking GraphQL 地址（与 skywalking_query.py 保持一致）
REGION_ENDPOINTS = {
    'su':  'http://10.11.106.20:8099/graphql',
    'bj':  'http://10.169.19.151:8099/graphql',
    'gz':  'http://10.169.26.164:8099/graphql',
    'hkg': 'http://10.169.26.164:8099/graphql',
    'sin': 'http://10.169.26.164:8099/graphql',
    'fwh': 'http://10.11.227.162:8099/graphql',
    'sh':  'http://10.11.227.162:8099/graphql',
    'nj':  'http://10.11.227.162:8099/graphql',
    'yq':  'http://10.11.227.162:8099/graphql',
    'bd':  'http://10.11.61.68:8099/graphql',
    'cd':  'http://10.11.227.162:8099/graphql',
}

# 服务 -> 关注的 region 列表
SERVICE_REGIONS = {
    'EIP': ['bj', 'gz', 'su', 'cd', 'yq', 'hkg', 'sin', 'fwh', 'nj', 'bd'],
    'VPC': ['bj', 'gz', 'su', 'cd', 'yq', 'hkg', 'sin', 'fwh', 'nj', 'bd'],
    'BLB': ['bj', 'gz', 'su', 'cd', 'yq', 'hkg', 'sin', 'fwh', 'nj', 'bd'],
}

# region 代码 -> serviceCode 后缀（大写）
REGION_TO_SUFFIX = {
    'bj':  'BJ',
    'gz':  'GZ',
    'su':  'SU',
    'cd':  'CD',
    'yq':  'YQ',
    'hkg': 'HKG',
    'sin': 'SIN',
    'fwh': 'FWH',
    'sh':  'SH',
    'nj':  'NJ',
    'bd':  'BD',
}

# 服务类型 -> SkyWalking 服务名前缀
SERVICE_CODE_PREFIX = {
    'EIP': 'LOGICAL_EIP',
    'VPC': 'LOGICAL_VPC',
    'BLB': 'LOGICAL_BLB',
}

# 每页拉取的 trace 数量
PAGE_SIZE = 100
# 并发拉取 trace detail 的线程数
DETAIL_CONCURRENCY = 20
# 需要查询的 HTTP 5xx 状态码（标准范围 500-511）
HTTP_5XX_CODES = [str(c) for c in range(500, 512)]


# -----------------------------------------------------------------------
# GraphQL 查询语句
# -----------------------------------------------------------------------

QUERY_SERVICE_ID = """
query searchService($serviceCode: String!) {
  services: searchService(serviceCode: $serviceCode) {
    id
    name
  }
}
"""

QUERY_BASIC_TRACES = """
query queryTraces($condition: TraceQueryCondition) {
  data: queryBasicTraces(condition: $condition) {
    traces {
      key: segmentId
      endpointNames
      start
      isError
      traceIds
    }
    total
  }
}
"""

QUERY_TRACE_DETAIL = """
query queryTrace($traceId: ID!) {
  trace: queryTrace(traceId: $traceId) {
    spans {
      spanId
      parentSpanId
      serviceCode
      endpointName
      isError
      tags {
        key
        value
      }
      logs {
        time
        data {
          key
          value
        }
      }
    }
  }
}
"""


# -----------------------------------------------------------------------
# 基础 HTTP 工具
# -----------------------------------------------------------------------

def graphql_request(endpoint: str, query: str, variables: dict, timeout: int = 30):
    """执行 GraphQL POST 请求"""
    payload = json.dumps({"query": query, "variables": variables}).encode('utf-8')
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


# -----------------------------------------------------------------------
# 服务 ID 查询
# -----------------------------------------------------------------------

def get_service_id(sw_endpoint: str, service_code: str) -> Optional[str]:
    """
    通过 serviceCode（如 LOGICAL_EIP_BJ）查询 SkyWalking 中的服务 ID。
    返回 service ID，查不到返回 None。
    """
    result = graphql_request(sw_endpoint, QUERY_SERVICE_ID, {"serviceCode": service_code})
    if "error" in result:
        return None
    data = result.get("data") or {}
    if not isinstance(data, dict):
        return None
    svc = data.get("services")
    if not svc:
        return None
    if not isinstance(svc, dict):
        return None
    return svc.get("id")


# -----------------------------------------------------------------------
# 数据拉取
# -----------------------------------------------------------------------

def fetch_5xx_traces_direct(sw_endpoint: str, service_id: str,
                             start_str: str, end_str: str,
                             verbose: bool = False) -> list[dict[str, object]]:
    """
    直接通过 http.status_code tag 过滤，逐个状态码查询 5xx trace 列表。
    无需拉取全量 error trace 再后置过滤，彻底规避 SW 10000 条上限问题。
    """
    all_traces = []

    for code in HTTP_5XX_CODES:
        page = 1
        code_traces = []

        while True:
            variables = {
                "condition": {
                    "serviceId": service_id,
                    "queryDuration": {
                        "start": start_str,
                        "end": end_str,
                        "step": "SECOND"
                    },
                    "traceState": "ERROR",
                    "tags": [{"key": "http.status_code", "value": code}],
                    "paging": {
                        "pageNum": page,
                        "pageSize": PAGE_SIZE,
                        "needTotal": True
                    },
                    "queryOrder": "BY_START_TIME"
                }
            }

            result = graphql_request(sw_endpoint, QUERY_BASIC_TRACES, variables)
            if "error" in result:
                if verbose:
                    print(f"    [warn] status_code={code} 查询失败: {result['error']}", file=sys.stderr)
                break

            data_outer = result.get("data") or {}
            if not isinstance(data_outer, dict):
                break
            data = data_outer.get("data") or {}
            if not isinstance(data, dict):
                break
            traces = data.get("traces", [])
            total = data.get("total", 0)

            code_traces.extend(traces)

            if verbose and total > 0:
                print(f"    [status={code}] 第{page}页：{len(traces)} 条，累计 {len(code_traces)}/{total}", file=sys.stderr)

            if len(code_traces) >= total or not traces:
                break
            page += 1

        if verbose and code_traces:
            print(f"    [status={code}] 共 {len(code_traces)} 条", file=sys.stderr)

        all_traces.extend(code_traces)

    return all_traces


def fetch_trace_detail(sw_endpoint: str, trace_id: str):
    """拉取单条 trace 的详细 span 信息"""
    result = graphql_request(sw_endpoint, QUERY_TRACE_DETAIL, {"traceId": trace_id})
    if "error" in result:
        return None
    data = result.get("data") or {}
    if not isinstance(data, dict):
        return None
    return data.get("trace")


def is_5xx_trace(trace_detail) -> bool:
    """
    检查 trace 入口 span 的 http.status_code 是否为 5xx。
    无 http.status_code tag 时返回 False。
    """
    if not trace_detail:
        return False
    spans = trace_detail.get("spans", [])
    entry_span = next(
        (s for s in spans if s.get("spanId") == 0 and s.get("parentSpanId") == -1),
        None
    )
    if not entry_span:
        return False
    for tag in entry_span.get("tags", []):
        if tag.get("key") == "http.status_code":
            try:
                code = int(tag.get("value", "0"))
                return 500 <= code <= 599
            except ValueError:
                return False
    return False


# -----------------------------------------------------------------------
# 信息提取
# -----------------------------------------------------------------------

def start_ms_to_str(start_ms_str: str) -> str:
    """将 basic trace 的 start 字段（毫秒字符串）转为 'YYYY-MM-DD HH:MM:SS'"""
    try:
        ms = int(start_ms_str)
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def extract_detail_info(trace_detail: dict[str, object]) -> dict[str, str]:
    """
    从 trace 详情中提取 requestId / accountId / errorMessage / error_endpoint。
    """
    spans = trace_detail.get("spans", []) if trace_detail else []
    info = {
        "request_id": "",
        "account_id": "",
        "error_message": "",
        "error_endpoint": "",
    }
    if not spans:
        return info

    entry_span = next(
        (s for s in spans if s.get("spanId") == 0 and s.get("parentSpanId") == -1),
        spans[0]
    )

    for tag in entry_span.get("tags", []):
        k, v = tag.get("key", ""), tag.get("value", "")
        if k in ("req-id", "request-id", "requestId"):
            info["request_id"] = v
        elif k in ("account-id", "accountId", "userId"):
            info["account_id"] = v

    # 下游异常 span（isError=true，非入口）
    error_spans = [s for s in spans if s.get("isError") and s.get("spanId") != 0]
    if error_spans:
        err = error_spans[0]
        info["error_endpoint"] = err.get("endpointName", "")
        for log in err.get("logs", []):
            for d in log.get("data", []):
                if d.get("key") in ("message", "error.message", "Message"):
                    info["error_message"] = d.get("value", "")[:300]
                    break
            if info["error_message"]:
                break

    # 若无下游异常 span，从入口 span 的 logs 中提取 errorMessage
    if not info["error_message"]:
        for log in entry_span.get("logs", []):
            for d in log.get("data", []):
                if d.get("key") in ("message", "error.message", "Message"):
                    info["error_message"] = d.get("value", "")[:300]
                    break
            if info["error_message"]:
                break

    return info


def fetch_and_filter_5xx(sw_endpoint: str, basic_trace):
    """
    并发任务函数：对单条 basic trace 拉取 detail，若为 5xx 则返回提取的 info，否则返回 None。
    """
    ep = (basic_trace.get("endpointNames") or [""])[0]
    if not ep:
        return None

    request_time = start_ms_to_str(basic_trace.get("start", ""))
    trace_ids = basic_trace.get("traceIds") or []
    if not trace_ids:
        return None

    detail = fetch_trace_detail(sw_endpoint, trace_ids[0])
    if not detail or not is_5xx_trace(detail):
        return None

    info = extract_detail_info(detail)
    return {
        "endpoint":      ep,
        "err_endpoint":  info.get("error_endpoint") or ep,
        "request_id":    info.get("request_id", ""),
        "account_id":    info.get("account_id", ""),
        "request_time":  request_time,
        "error_message": info.get("error_message", ""),
    }


# -----------------------------------------------------------------------
# 核心分析
# -----------------------------------------------------------------------

def analyze_service(service_type: str, days: int,
                    sample_limit: int = 3,
                    verbose: bool = False) -> str:
    """
    统计指定服务所有 region 近 days 天的 5xx 异常，生成 top5 分析输入文本。
    只统计 HTTP 状态码为 5xx 的异常请求（通过 trace detail 中 http.status_code tag 过滤）。
    使用并发方式拉取 trace detail，提高处理效率。
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    start_str = start_time.strftime("%Y-%m-%d %H%M%S")
    end_str = end_time.strftime("%Y-%m-%d %H%M%S")

    if verbose:
        print(f"[{service_type}] 时间范围：{start_str} ~ {end_str}", file=sys.stderr)

    regions = SERVICE_REGIONS[service_type]
    service_prefix = SERVICE_CODE_PREFIX[service_type]

    # 聚合结构：entry_endpoint -> service_code -> [trace detail info]
    endpoint_map: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))

    for region in regions:
        sw_endpoint = REGION_ENDPOINTS.get(region)
        if not sw_endpoint:
            if verbose:
                print(f"  [skip] region {region} 无 SkyWalking 配置", file=sys.stderr)
            continue

        service_code = f"{service_prefix}_{REGION_TO_SUFFIX[region]}"

        service_id = get_service_id(sw_endpoint, service_code)
        if not service_id:
            if verbose:
                print(f"  [skip] {service_code} 在 SkyWalking 中未找到", file=sys.stderr)
            continue

        if verbose:
            print(f"  [{region}] {service_code} id={service_id}，按状态码直接查询 5xx traces ...", file=sys.stderr)

        five_xx_traces = fetch_5xx_traces_direct(sw_endpoint, service_id, start_str, end_str, verbose)
        if verbose:
            print(f"  [{region}] 共 {len(five_xx_traces)} 条 5xx trace，并发拉取详情 ...", file=sys.stderr)

        # 并发拉取 trace detail 提取 requestId/accountId/errorMessage
        valid_count = 0
        with ThreadPoolExecutor(max_workers=DETAIL_CONCURRENCY) as executor:
            futures = {
                executor.submit(fetch_and_filter_5xx, sw_endpoint, t): t
                for t in five_xx_traces
            }
            for future in as_completed(futures):
                result = future.result()
                if result is None:
                    continue
                valid_count += 1
                ep = result["endpoint"]
                endpoint_map[ep][service_code].append(result)

        if verbose:
            print(f"  [{region}] 有效 5xx trace：{valid_count} 条", file=sys.stderr)

    if not endpoint_map:
        return f"LOGICAL_{service_type}服务近{days}天无5xx异常记录。\n"

    # 按总异常数降序排列
    ranked = sorted(
        [(ep, sum(len(v) for v in svc.values()), svc)
         for ep, svc in endpoint_map.items()],
        key=lambda x: -x[1]
    )

    lines = []
    lines.append(f"LOGICAL_{service_type}服务5xx异常接口排序（近{days}天）")
    for ep, total, _ in ranked:
        lines.append(f"接口：{ep}，异常数：{total}")
    lines.append("")
    lines.append("Top5异常详细分析")

    for rank, (ep, total, svc_map) in enumerate(ranked, 1):
        lines.append(f"Top{rank} {ep}，异常数：{total}，详情如下")

        for service_code in sorted(svc_map.keys()):
            detail_items = svc_map[service_code]
            svc_total = len(detail_items)

            # 先聚合再输出，确保类数统计准确
            class_map: dict[str, list[dict[str, str]]] = defaultdict(list)
            for d in detail_items:
                class_map[d["err_endpoint"]].append(d)

            lines.append(f"服务：{service_code}")
            lines.append(f"5xx异常数量：{svc_total}，异常分为{len(class_map)}类")
            lines.append("")

            class_idx = 1
            for err_ep, items in class_map.items():
                lines.append(f"第{class_idx}类异常")
                lines.append(f"endpoint：{err_ep}，异常数量：{len(items)}")
                lines.append("")

                # 每类只展示前 sample_limit 个示例
                samples = items[:sample_limit]
                if len(samples) == 1:
                    item = samples[0]
                    lines.append("异常链路简要信息示例：")
                    lines.append(json.dumps({
                        "requestId":    item["request_id"],
                        "accountId":    item["account_id"],
                        "requestTime":  item["request_time"],
                        "errorMessage": item["error_message"],
                    }, ensure_ascii=False))
                else:
                    for reason_idx, item in enumerate(samples, 1):
                        lines.append(f"原因{reason_idx}有1个异常，异常链路简要信息示例：")
                        lines.append(json.dumps({
                            "requestId":    item["request_id"],
                            "accountId":    item["account_id"],
                            "requestTime":  item["request_time"],
                            "errorMessage": item["error_message"],
                        }, ensure_ascii=False))
                        lines.append("")

                class_idx += 1

        lines.append("")

    return "\n".join(lines)


# -----------------------------------------------------------------------
# CLI 入口
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="从 SkyWalking 统计 VPC/EIP/BLB 近七天 5xx 异常，生成 top5 分析输入",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 生成 EIP 近7天 top5 输入（直接作为 top5-analyzer skill 的输入）
  python3 top5-analyzer/scripts/top5_input.py --service EIP

  # 生成 VPC 近7天报告，显示详细日志
  python3 top5-analyzer/scripts/top5_input.py --service VPC --days 7 --verbose

  # 生成 BLB 报告
  python3 top5-analyzer/scripts/top5_input.py --service BLB
        """
    )
    parser.add_argument("--service", required=True, choices=["EIP", "VPC", "BLB"],
                        help="服务类型：EIP / VPC / BLB")
    parser.add_argument("--days", type=int, default=7,
                        help="统计时间范围（天），默认 7 天")
    parser.add_argument("--sample", type=int, default=3,
                        help="每类异常展示的示例 trace 数（用于推导 requestId），默认 3")
    parser.add_argument("--verbose", action="store_true",
                        help="输出详细调试日志到 stderr")

    args = parser.parse_args()

    report = analyze_service(
        service_type=args.service,
        days=args.days,
        sample_limit=args.sample,
        verbose=args.verbose,
    )

    print(report)


if __name__ == "__main__":
    main()

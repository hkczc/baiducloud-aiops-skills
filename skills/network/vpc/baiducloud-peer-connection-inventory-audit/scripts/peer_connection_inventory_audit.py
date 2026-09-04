#!/usr/bin/env python3
"""Read-only Baidu AI Cloud VPC peering inventory and status audit.

The network client rejects every HTTP method except GET before network I/O.
Credentials come from environment variables or an explicitly selected,
owner-only JSON file outside the Skill package.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import math
import os
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
KNOWN_STATUSES = {
    "creating",
    "consulting",
    "consult_failed",
    "active",
    "down",
    "starting",
    "stopping",
    "deleting",
    "deleted",
    "expired",
    "error",
    "updating",
}
TRANSITIONAL_STATUSES = {
    "creating",
    "consulting",
    "starting",
    "stopping",
    "deleting",
    "updating",
}
KNOWN_DNS_STATUSES = {"close", "wait", "syncing", "open", "closing"}
TRANSITIONAL_DNS_STATUSES = {"wait", "syncing", "closing"}
KNOWN_ROLES = {"initiator", "acceptor"}


class ApiFailure(RuntimeError):
    """Sanitized API failure that never carries request authorization data."""

    def __init__(
        self,
        status: int | None,
        message: str,
        *,
        code: str | None = None,
        request_id: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.request_id = request_id
        self.path = path

    def to_dict(self, operation: str, scope: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "operation": operation,
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "requestId": self.request_id,
            "path": self.path,
        }
        if scope:
            result["scope"] = scope
        return {key: value for key, value in result.items() if value is not None}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _quote(value: Any, *, keep_slash: bool = False) -> str:
    from urllib.parse import quote

    safe = "/.~-_" if keep_slash else ".~-_"
    return quote("" if value is None else str(value), safe=safe)


def canonical_query(params: dict[str, Any] | None) -> str:
    if not params:
        return ""
    pairs: list[str] = []
    for key, value in params.items():
        if isinstance(value, bool):
            value = str(value).lower()
        pairs.append(f"{_quote(key)}={_quote(value)}")
    return "&".join(sorted(pairs))


def bce_authorization(
    access_key: str,
    secret_key: str,
    host: str,
    path: str,
    params: dict[str, Any] | None,
    *,
    timestamp: str,
    session_token: str | None = None,
    expiration_seconds: int = 1800,
) -> tuple[str, dict[str, str]]:
    """Build BCE v1 authorization for a GET request."""

    canonical_uri = _quote(path, keep_slash=True)
    auth_prefix = f"bce-auth-v1/{access_key}/{timestamp}/{expiration_seconds}"
    signing_key = hmac.new(
        secret_key.encode("utf-8"), auth_prefix.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    signed = {"host": host, "x-bce-date": timestamp}
    if session_token:
        signed["x-bce-security-token"] = session_token
    signed_names = sorted(signed)
    canonical_headers = "\n".join(
        f"{_quote(name.lower())}:{_quote(str(signed[name]).strip())}" for name in signed_names
    )
    string_to_sign = "\n".join(
        ("GET", canonical_uri, canonical_query(params), canonical_headers)
    )
    signature = hmac.new(
        signing_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = f"{auth_prefix}/{';'.join(signed_names)}/{signature}"
    headers = {
        "Host": host,
        "x-bce-date": timestamp,
        "Authorization": authorization,
        "Accept": "application/json",
        "Content-Type": "application/json;charset=utf-8",
        "User-Agent": "baiducloud-peer-connection-inventory-audit/1.0",
    }
    if session_token:
        headers["x-bce-security-token"] = session_token
    return authorization, headers


class ReadOnlyBceClient:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        session_token: str | None = None,
        *,
        timeout: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        from urllib.parse import urlparse

        endpoint = endpoint.rstrip("/")
        if not endpoint.startswith("https://"):
            raise ValueError("Endpoint must use HTTPS")
        parsed = urlparse(endpoint)
        if not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Endpoint must be an HTTPS origin without a path, query, or fragment")
        if not parsed.hostname.endswith(".baidubce.com"):
            raise ValueError("Endpoint host must be an official *.baidubce.com domain")
        self.endpoint = endpoint
        self.host = parsed.netloc
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.timeout = timeout
        self.max_retries = max_retries

    def request_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        method: str = "GET",
    ) -> dict[str, Any]:
        if method.upper() != "GET":
            raise ValueError("Read-only guard rejected non-GET request")
        if not path.startswith("/"):
            raise ValueError("API path must start with /")

        query = canonical_query(params)
        url = f"{self.endpoint}{path}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(self.max_retries + 1):
            timestamp = utc_now()
            _, headers = bce_authorization(
                self.access_key,
                self.secret_key,
                self.host,
                path,
                params,
                timestamp=timestamp,
                session_token=self.session_token,
            )
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
                    if not payload:
                        return {}
                    parsed = json.loads(payload.decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise ApiFailure(
                            response.status,
                            "Expected a JSON object response",
                            request_id=response.headers.get("x-bce-request-id"),
                            path=path,
                        )
                    return parsed
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                detail = _parse_error_body(body)
                if exc.code in RETRYABLE_STATUS and attempt < self.max_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise ApiFailure(
                    exc.code,
                    str(detail.get("message") or f"HTTP {exc.code}"),
                    code=_optional_string(detail.get("code")),
                    request_id=exc.headers.get("x-bce-request-id")
                    or _optional_string(detail.get("requestId")),
                    path=path,
                ) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.max_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                reason = getattr(exc, "reason", None)
                raise ApiFailure(None, f"Network error: {reason or exc}", path=path) from None
            except json.JSONDecodeError as exc:
                raise ApiFailure(None, f"Invalid JSON response: {exc}", path=path) from None

        raise ApiFailure(None, "Request failed after retries", path=path)

    def paginate(
        self,
        path: str,
        item_fields: Iterable[str],
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query = dict(params or {})
        query.setdefault("maxKeys", 1000)
        marker: str | None = None
        seen_markers: set[str] = set()
        items: list[dict[str, Any]] = []
        while True:
            if marker:
                query["marker"] = marker
            response = self.request_json(path, query)
            page = _first_list(response, item_fields)
            items.extend(item for item in page if isinstance(item, dict))
            if not bool(response.get("isTruncated")):
                break
            next_marker = response.get("nextMarker")
            if not next_marker or str(next_marker) in seen_markers:
                raise ApiFailure(
                    None,
                    "Pagination stopped because nextMarker was missing or repeated",
                    code="PaginationLoop",
                    path=path,
                )
            marker = str(next_marker)
            seen_markers.add(marker)
        return items


def _parse_error_body(body: str) -> dict[str, Any]:
    try:
        value = json.loads(body)
        return value if isinstance(value, dict) else {"message": body[:500]}
    except json.JSONDecodeError:
        return {"message": body[:500]}


def _first_list(data: dict[str, Any], fields: Iterable[str]) -> list[Any]:
    for field in fields:
        value = data.get(field)
        if isinstance(value, list):
            return value
    return []


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _peer_id(record: dict[str, Any]) -> str | None:
    return _optional_string(record.get("peerConnId") or record.get("id"))


def _detail_params(record: dict[str, Any]) -> dict[str, str] | None:
    role = str(record.get("role") or "").lower()
    return {"role": role} if role in KNOWN_ROLES else None


def _new_region(endpoint: str) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "resources": {"peerConnections": []},
        "coverage": {
            "listPeerConnections": {
                "status": "notAttempted",
                "count": 0,
                "queries": 0,
                "failedQueries": 0,
            },
            "detailPeerConnections": {
                "status": "notAttempted",
                "count": 0,
                "queries": 0,
                "failedQueries": 0,
                "skippedRecords": 0,
            },
        },
        "errors": [],
    }


def collect_region(
    region: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    session_token: str | None,
    timeout: float,
    max_retries: int,
) -> dict[str, Any]:
    region_data = _new_region(endpoint)
    client = ReadOnlyBceClient(
        endpoint,
        access_key,
        secret_key,
        session_token,
        timeout=timeout,
        max_retries=max_retries,
    )
    list_coverage = region_data["coverage"]["listPeerConnections"]
    detail_coverage = region_data["coverage"]["detailPeerConnections"]
    list_coverage["queries"] = 1

    try:
        summaries = client.paginate("/v1/peerconn", ("peerConns",))
    except ApiFailure as exc:
        list_coverage["status"] = "failed"
        list_coverage["failedQueries"] = 1
        detail_coverage["status"] = "blocked"
        detail_coverage["reason"] = "Peer connection list query failed"
        region_data["errors"].append(exc.to_dict("listPeerConnections", region))
        return region_data

    list_coverage["status"] = "success"
    list_coverage["count"] = len(summaries)
    records: list[dict[str, Any]] = []

    for summary in summaries:
        peer_conn_id = _peer_id(summary)
        if not peer_conn_id:
            item = dict(summary)
            item["_detailStatus"] = "skipped"
            detail_coverage["skippedRecords"] += 1
            records.append(item)
            continue

        detail_coverage["queries"] += 1
        path = f"/v1/peerconn/{_quote(peer_conn_id)}"
        try:
            detail = client.request_json(path, _detail_params(summary))
            item = dict(summary)
            item.update(detail)
            item.setdefault("peerConnId", peer_conn_id)
            item["_detailStatus"] = "success"
            detail_coverage["count"] += 1
            records.append(item)
        except ApiFailure as exc:
            item = dict(summary)
            item["_detailStatus"] = "failed"
            records.append(item)
            detail_coverage["failedQueries"] += 1
            region_data["errors"].append(
                exc.to_dict("detailPeerConnections", peer_conn_id)
            )

    if not summaries:
        detail_coverage["status"] = "success"
    elif detail_coverage["failedQueries"] or detail_coverage["skippedRecords"]:
        detail_coverage["status"] = "partial"
    else:
        detail_coverage["status"] = "success"
    region_data["resources"]["peerConnections"] = records
    return region_data


def _read_credentials_file(path: Path) -> tuple[str, str, str | None]:
    """Read credentials without following symlinks or accepting broad permissions."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Credentials file must be a regular file")
        if metadata.st_uid != os.geteuid():
            raise ValueError("Credentials file must be owned by the current user")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("Credentials file permissions are too broad; run chmod 600")
        if metadata.st_size > 65536:
            raise ValueError("Credentials file is unexpectedly large")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            payload = json.load(handle)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise ValueError("Credentials file must contain a JSON object")
    access_key = str(payload.get("accessKeyId") or "").strip()
    secret_key = str(payload.get("secretAccessKey") or "").strip()
    session_token = str(payload.get("sessionToken") or "").strip() or None
    if not access_key or not secret_key:
        raise ValueError("Credentials file requires accessKeyId and secretAccessKey")
    return access_key, secret_key, session_token


def _parse_regions(value: str | None) -> list[str]:
    if not value:
        raise ValueError("--regions is required in live mode")
    regions: list[str] = []
    for item in value.split(","):
        region = item.strip().lower()
        if not region:
            continue
        if not all(character.isalnum() or character == "-" for character in region):
            raise ValueError(f"Invalid region code: {region}")
        if region not in regions:
            regions.append(region)
    if not regions:
        raise ValueError("At least one region is required")
    return regions


def _parse_endpoints(values: list[str]) -> dict[str, str]:
    from urllib.parse import urlparse

    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--endpoint must use REGION=https://host")
        region, endpoint = value.split("=", 1)
        region = region.strip().lower()
        endpoint = endpoint.strip().rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Endpoint overrides must use HTTPS")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Endpoint overrides must be origins without path, query, or fragment")
        if not parsed.hostname.endswith(".baidubce.com"):
            raise ValueError("Endpoint overrides must use an official *.baidubce.com host")
        result[region] = endpoint
    return result


def collect_live(args: argparse.Namespace) -> dict[str, Any]:
    if args.credentials_file:
        access_key, secret_key, session_token = _read_credentials_file(args.credentials_file)
    else:
        access_key = os.environ.get("BCE_ACCESS_KEY_ID")
        secret_key = os.environ.get("BCE_SECRET_ACCESS_KEY")
        session_token = os.environ.get("BCE_SESSION_TOKEN")
    if not access_key or not secret_key:
        raise ValueError(
            "Set BCE_ACCESS_KEY_ID and BCE_SECRET_ACCESS_KEY in the environment; "
            "or use --credentials-file with an owner-only JSON file; "
            "do not pass credentials on the command line"
        )

    endpoints = _parse_endpoints(args.endpoint or [])
    inventory: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "mode": "live",
        "regions": {},
    }
    for region in _parse_regions(args.regions):
        endpoint = endpoints.get(region, f"https://bcc.{region}.baidubce.com")
        inventory["regions"][region] = collect_region(
            region,
            endpoint,
            access_key,
            secret_key,
            session_token,
            args.timeout,
            args.max_retries,
        )
    return inventory


def load_inventory(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        inventory = json.load(handle)
    if not isinstance(inventory, dict) or not isinstance(inventory.get("regions"), dict):
        raise ValueError("Inventory must be a JSON object containing a regions object")
    inventory.setdefault("schemaVersion", SCHEMA_VERSION)
    inventory.setdefault("generatedAt", utc_now())
    inventory["mode"] = "offline"
    for region, data in inventory["regions"].items():
        if not isinstance(data, dict):
            raise ValueError(f"Region {region} must be an object")
        resources = data.setdefault("resources", {})
        peer_connections = resources.setdefault("peerConnections", [])
        if not isinstance(peer_connections, list):
            raise ValueError(f"Region {region} peerConnections must be a list")
        coverage = data.setdefault("coverage", {})
        coverage.setdefault(
            "listPeerConnections",
            {
                "status": "unknown",
                "count": len(peer_connections),
                "queries": 0,
                "failedQueries": 0,
            },
        )
        coverage.setdefault(
            "detailPeerConnections",
            {
                "status": "unknown",
                "count": sum(
                    1 for item in peer_connections
                    if isinstance(item, dict) and item.get("_detailStatus") == "success"
                ),
                "queries": 0,
                "failedQueries": 0,
            },
        )
        data.setdefault("errors", [])
        data.setdefault("endpoint", "offline")
    return inventory


def _finding(
    rule_id: str,
    severity: str,
    region: str,
    record: dict[str, Any] | None,
    fact: str,
    interpretation: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = record or {}
    return {
        "ruleId": rule_id,
        "severity": severity,
        "region": region,
        "peerConnId": _peer_id(record),
        "localVpcId": _optional_string(record.get("localVpcId")),
        "peerVpcId": _optional_string(record.get("peerVpcId")),
        "fact": fact,
        "interpretation": interpretation,
        "evidence": evidence or {},
    }


def _parse_timestamp(value: Any) -> tuple[dt.datetime | None, bool]:
    if not isinstance(value, str) or not value.strip():
        return None, False
    text = value.strip()
    parsed: dt.datetime | None = None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None, False
    assumed_local = parsed.tzinfo is None
    if assumed_local:
        parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed.astimezone(dt.timezone.utc), assumed_local


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def analyze_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    total_connections = 0
    detail_success = 0
    status_distribution: Counter[str] = Counter()
    role_distribution: Counter[str] = Counter()
    dns_distribution: Counter[str] = Counter()
    region_pairs: Counter[str] = Counter()
    prepaid_count = 0
    expiring_30_days = 0
    release_protection_disabled = 0
    now = dt.datetime.now(dt.timezone.utc)

    for region, region_data in inventory.get("regions", {}).items():
        records = region_data.get("resources", {}).get("peerConnections", [])
        if not isinstance(records, list):
            continue
        total_connections += len(records)

        for error in region_data.get("errors", []):
            status_code = error.get("status")
            rule_id = (
                "COV-002"
                if status_code in (401, 403)
                else "COV-004"
                if status_code == 404
                else "COV-001"
            )
            severity = "info" if rule_id == "COV-004" else "high"
            findings.append(
                _finding(
                    rule_id,
                    severity,
                    region,
                    {"peerConnId": error.get("scope")}
                    if error.get("operation") == "detailPeerConnections"
                    else None,
                    f"{error.get('operation', 'query')} 查询失败，状态为 {status_code or 'network-error'}",
                    "该范围的对等连接清单或详情覆盖不完整",
                    evidence={
                        key: error.get(key)
                        for key in ("operation", "status", "code", "requestId", "path", "scope")
                        if error.get(key) is not None
                    },
                )
            )

        tuple_records: defaultdict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for item in records:
            if not isinstance(item, dict):
                continue
            if item.get("_detailStatus") == "success":
                detail_success += 1

            status = str(item.get("status") or "").lower()
            role = str(item.get("role") or "").lower()
            dns_status = str(item.get("dnsStatus") or "").lower()
            local_region = str(item.get("localRegion") or "")
            peer_region = str(item.get("peerRegion") or "")
            local_vpc = str(item.get("localVpcId") or "")
            peer_vpc = str(item.get("peerVpcId") or "")

            status_distribution[status or "missing"] += 1
            role_distribution[role or "missing"] += 1
            dns_distribution[dns_status or "missing"] += 1
            region_pairs[f"{local_region or region}->{peer_region or 'missing'}"] += 1

            if status in {"down", "error"}:
                findings.append(
                    _finding(
                        "PEER-001",
                        "high",
                        region,
                        item,
                        f"对等连接状态为 {status}",
                        "控制面报告连接不可用或异常，需要人工排查",
                        evidence={"status": status},
                    )
                )
            elif status in {"expired", "consult_failed"}:
                findings.append(
                    _finding(
                        "PEER-002",
                        "medium",
                        region,
                        item,
                        f"对等连接状态为 {status}",
                        "连接已到期或跨账号协商失败",
                        evidence={"status": status},
                    )
                )
            elif status in TRANSITIONAL_STATUSES:
                findings.append(
                    _finding(
                        "PEER-003",
                        "info",
                        region,
                        item,
                        f"对等连接处于过渡状态 {status}",
                        "仅记录状态；缺少状态变更时间，不能判断是否卡住",
                        evidence={"status": status, "createdTime": item.get("createdTime")},
                    )
                )
            elif status == "deleted":
                findings.append(
                    _finding(
                        "PEER-004",
                        "info",
                        region,
                        item,
                        "列表仍返回 deleted 状态的连接",
                        "与控制台资产视图人工核对即可，不执行自动清理",
                        evidence={"status": status},
                    )
                )
            elif status not in KNOWN_STATUSES:
                findings.append(
                    _finding(
                        "PEER-005",
                        "info",
                        region,
                        item,
                        f"对等连接状态为 {status or 'missing'}",
                        "状态缺失或未在当前官方枚举中，需要人工解释",
                        evidence={"status": status or None},
                    )
                )

            if local_region and peer_region and local_vpc and peer_vpc:
                tuple_records[(local_region, local_vpc, peer_region, peer_vpc)].append(item)
                if local_region == peer_region and local_vpc == peer_vpc:
                    findings.append(
                        _finding(
                            "PEER-006",
                            "high",
                            region,
                            item,
                            "本端与对端地域、VPC ID 完全相同",
                            "返回配置与产品约束不一致，需要核对源数据",
                            evidence={
                                "localRegion": local_region,
                                "peerRegion": peer_region,
                                "localVpcId": local_vpc,
                                "peerVpcId": peer_vpc,
                            },
                        )
                    )

            if local_region and local_region.lower() != str(region).lower():
                findings.append(
                    _finding(
                        "PEER-007",
                        "medium",
                        region,
                        item,
                        f"查询地域为 {region}，返回 localRegion={local_region}",
                        "地域清单与连接本端元数据不一致",
                        evidence={"queriedRegion": region, "localRegion": local_region},
                    )
                )

            if role not in KNOWN_ROLES:
                findings.append(
                    _finding(
                        "PEER-008",
                        "info",
                        region,
                        item,
                        f"连接角色为 {role or 'missing'}",
                        "同地域详情的端点方向可能不明确",
                        evidence={"role": role or None},
                    )
                )

            if status == "active" and not _positive_number(item.get("bandwidthInMbps")):
                findings.append(
                    _finding(
                        "PEER-009",
                        "medium",
                        region,
                        item,
                        "active 连接未返回正数带宽",
                        "活动状态与带宽字段不一致或详情字段不完整",
                        evidence={
                            "status": status,
                            "bandwidthInMbps": item.get("bandwidthInMbps"),
                            "detailStatus": item.get("_detailStatus"),
                        },
                    )
                )

            payment_timing = str(item.get("paymentTiming") or "")
            if payment_timing.lower() == "prepaid":
                prepaid_count += 1
                expiration, assumed_local = _parse_timestamp(item.get("expiredTime"))
                if expiration is not None:
                    days_remaining = (expiration - now).total_seconds() / 86400
                    if days_remaining <= 30:
                        expiring_30_days += 1
                        severity = "high" if days_remaining < 0 else "medium"
                        display_days = math.floor(days_remaining) if days_remaining < 0 else math.ceil(days_remaining)
                        findings.append(
                            _finding(
                                "PEER-010",
                                severity,
                                region,
                                item,
                                f"预付费连接距离到期约 {display_days} 天",
                                "需要人工评估续费或替代方案；本 Skill 不执行续费",
                                evidence={
                                    "paymentTiming": payment_timing,
                                    "expiredTime": item.get("expiredTime"),
                                    "daysRemaining": round(days_remaining, 2),
                                    "assumedLocalTimezone": assumed_local,
                                },
                            )
                        )

            if dns_status in TRANSITIONAL_DNS_STATUSES:
                findings.append(
                    _finding(
                        "PEER-011",
                        "info",
                        region,
                        item,
                        f"DNS 同步状态为 {dns_status}",
                        "DNS 同步处于过渡状态；若持续存在再人工复查",
                        evidence={"dnsStatus": dns_status},
                    )
                )
            elif dns_status not in KNOWN_DNS_STATUSES:
                findings.append(
                    _finding(
                        "PEER-012",
                        "info",
                        region,
                        item,
                        f"DNS 同步状态为 {dns_status or 'missing'}",
                        "字段缺失或不在当前官方枚举中；close 和 open 均可为正常配置",
                        evidence={"dnsStatus": dns_status or None},
                    )
                )

            if item.get("_detailStatus") == "success" and item.get("deleteProtect") is False:
                release_protection_disabled += 1
                findings.append(
                    _finding(
                        "PEER-013",
                        "low",
                        region,
                        item,
                        "连接未开启释放保护",
                        "这是防误操作治理观察，不代表连接故障",
                        evidence={"deleteProtect": False},
                    )
                )

        for topology, duplicates in tuple_records.items():
            identifiers = sorted({_peer_id(item) for item in duplicates if _peer_id(item)})
            if len(identifiers) > 1:
                findings.append(
                    _finding(
                        "PEER-014",
                        "info",
                        region,
                        duplicates[0],
                        "同一有向本端/对端 VPC 组合返回多个连接 ID",
                        "可能是角色或账号视角导致的重复表示，需要人工确认",
                        evidence={
                            "topology": {
                                "localRegion": topology[0],
                                "localVpcId": topology[1],
                                "peerRegion": topology[2],
                                "peerVpcId": topology[3],
                            },
                            "peerConnIds": identifiers,
                        },
                    )
                )

    findings.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity")), 9),
            str(item.get("region") or ""),
            str(item.get("ruleId") or ""),
            str(item.get("peerConnId") or ""),
        )
    )
    return {
        "generatedAt": utc_now(),
        "sourceGeneratedAt": inventory.get("generatedAt"),
        "summary": {
            "peerConnections": total_connections,
            "detailSuccess": detail_success,
            "prepaidConnections": prepaid_count,
            "expiringWithin30Days": expiring_30_days,
            "releaseProtectionDisabled": release_protection_disabled,
            "statusDistribution": dict(sorted(status_distribution.items())),
            "roleDistribution": dict(sorted(role_distribution.items())),
            "dnsStatusDistribution": dict(sorted(dns_distribution.items())),
            "regionPairs": dict(sorted(region_pairs.items())),
        },
        "findingCounts": {
            severity: sum(1 for item in findings if item.get("severity") == severity)
            for severity in ("high", "medium", "low", "info")
        },
        "findings": findings,
    }


def _md(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(inventory: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = [
        "# 百度智能云对等连接资产与状态巡检报告",
        "",
        f"- 快照时间：{_md(inventory.get('generatedAt'))}",
        f"- 报告时间：{_md(analysis.get('generatedAt'))}",
        f"- 模式：{_md(inventory.get('mode'))}",
        f"- 地域：{', '.join(sorted(inventory.get('regions', {})))}",
        "- 安全边界：仅执行 GET 查询；未执行任何云资源变更。",
        "",
        "## 采集覆盖率",
        "",
        "| 地域 | 查询层级 | 状态 | 成功记录 | 查询数 | 失败查询 | 跳过记录 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for region, region_data in sorted(inventory.get("regions", {}).items()):
        for operation in ("listPeerConnections", "detailPeerConnections"):
            coverage = region_data.get("coverage", {}).get(operation, {})
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} |".format(
                    _md(region),
                    _md(operation),
                    _md(coverage.get("status", "unknown")),
                    _md(coverage.get("count", 0)),
                    _md(coverage.get("queries", 0)),
                    _md(coverage.get("failedQueries", 0)),
                    _md(coverage.get("skippedRecords", 0)),
                )
            )

    summary = analysis.get("summary", {})
    lines.extend(
        [
            "",
            "## 资产汇总",
            "",
            "| 连接数 | 详情成功 | 预付费 | 30 天内到期 | 未开启释放保护 |",
            "|---:|---:|---:|---:|---:|",
            "| {} | {} | {} | {} | {} |".format(
                summary.get("peerConnections", 0),
                summary.get("detailSuccess", 0),
                summary.get("prepaidConnections", 0),
                summary.get("expiringWithin30Days", 0),
                summary.get("releaseProtectionDisabled", 0),
            ),
            "",
            f"- 状态分布：{_md(summary.get('statusDistribution', {}))}",
            f"- 角色分布：{_md(summary.get('roleDistribution', {}))}",
            f"- DNS 状态分布：{_md(summary.get('dnsStatusDistribution', {}))}",
            f"- 地域方向：{_md(summary.get('regionPairs', {}))}",
            "",
            "## 连接拓扑",
            "",
            "| 查询地域 | 连接 ID | 角色 | 状态 | 本端 | 对端 | 带宽 Mbps | 计费 | 到期时间 | DNS | 详情 |",
            "|---|---|---|---|---|---|---:|---|---|---|---|",
        ]
    )
    for region, region_data in sorted(inventory.get("regions", {}).items()):
        records = region_data.get("resources", {}).get("peerConnections", [])
        for item in records:
            if not isinstance(item, dict):
                continue
            local = f"{item.get('localRegion') or region}/{item.get('localVpcId') or '-'}"
            peer = f"{item.get('peerRegion') or '-'}/{item.get('peerVpcId') or '-'}"
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    _md(region),
                    _md(_peer_id(item)),
                    _md(item.get("role")),
                    _md(item.get("status")),
                    _md(local),
                    _md(peer),
                    _md(item.get("bandwidthInMbps")),
                    _md(item.get("paymentTiming")),
                    _md(item.get("expiredTime")),
                    _md(item.get("dnsStatus")),
                    _md(item.get("_detailStatus", "unknown")),
                )
            )

    counts = analysis.get("findingCounts", {})
    lines.extend(
        [
            "",
            "## 发现",
            "",
            f"高：{counts.get('high', 0)}；中：{counts.get('medium', 0)}；低：{counts.get('low', 0)}；信息：{counts.get('info', 0)}。",
            "",
            "| 严重度 | 规则 | 地域 | 连接 ID | 本端 VPC | 对端 VPC | 事实 | 判断 |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for finding in analysis.get("findings", []):
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                _md(finding.get("severity")),
                _md(finding.get("ruleId")),
                _md(finding.get("region")),
                _md(finding.get("peerConnId")),
                _md(finding.get("localVpcId")),
                _md(finding.get("peerVpcId")),
                _md(finding.get("fact")),
                _md(finding.get("interpretation")),
            )
        )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 本报告只反映成功返回的控制面配置，不代表数据面端到端连通性。",
            "- 任一 failed、partial、blocked 或 unknown 覆盖状态都会限制结论完整性。",
            "- DNS 同步关闭不等于故障，过渡状态也不等于卡死。",
            "- 报告不执行或建议自动执行任何连接变更；整改需由人工另行评审。",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    output_dir: Path,
    inventory: dict[str, Any],
    analysis: dict[str, Any],
    *,
    overwrite: bool,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = output_dir / "inventory.json"
    report_path = output_dir / "report.md"
    if not overwrite:
        existing = [path for path in (inventory_path, report_path) if path.exists()]
        if existing:
            raise FileExistsError(
                "Refusing to overwrite existing output: " + ", ".join(str(path) for path in existing)
            )
    payload = dict(inventory)
    payload["analysis"] = analysis
    with inventory_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    with report_path.open("w", encoding="utf-8") as handle:
        handle.write(render_markdown(inventory, analysis))
    return inventory_path, report_path


def self_test() -> None:
    sample = Path(__file__).resolve().parents[1] / "examples" / "sample-peer-connections.json"
    inventory = load_inventory(sample)
    analysis = analyze_inventory(inventory)
    rule_ids = {item["ruleId"] for item in analysis["findings"]}
    expected = {"PEER-001", "PEER-011", "PEER-013"}
    missing = expected - rule_ids
    if missing:
        raise AssertionError(f"Sample analysis missed expected rules: {sorted(missing)}")

    client = ReadOnlyBceClient("https://bcc.bj.baidubce.com", "ak", "sk")
    try:
        client.request_json("/v1/peerconn", method="POST")
    except ValueError as exc:
        if "non-GET" not in str(exc):
            raise
    else:
        raise AssertionError("Read-only guard did not reject POST")

    try:
        ReadOnlyBceClient("https://example.com", "ak", "sk")
    except ValueError as exc:
        if "baidubce.com" not in str(exc):
            raise
    else:
        raise AssertionError("Endpoint guard accepted an untrusted host")

    page_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_pages(path: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        page_calls.append((path, dict(params or {})))
        if params and params.get("marker") == "page-2":
            return {"peerConns": [{"peerConnId": "peer-2"}], "isTruncated": False}
        return {
            "peerConns": [{"peerConnId": "peer-1"}],
            "isTruncated": True,
            "nextMarker": "page-2",
        }

    client.request_json = fake_pages  # type: ignore[method-assign]
    paged = client.paginate("/v1/peerconn", ("peerConns",))
    if [item.get("peerConnId") for item in paged] != ["peer-1", "peer-2"]:
        raise AssertionError("Pagination did not collect both pages")
    if len(page_calls) != 2 or page_calls[1][1].get("marker") != "page-2":
        raise AssertionError("Pagination did not use nextMarker exactly once")

    def repeated_marker(*_: Any, **__: Any) -> dict[str, Any]:
        return {"peerConns": [], "isTruncated": True, "nextMarker": "same-marker"}

    client.request_json = repeated_marker  # type: ignore[method-assign]
    try:
        client.paginate("/v1/peerconn", ("peerConns",))
    except ApiFailure as exc:
        if exc.code != "PaginationLoop":
            raise
    else:
        raise AssertionError("Pagination guard did not reject a repeated marker")

    if _detail_params({"role": "acceptor"}) != {"role": "acceptor"}:
        raise AssertionError("Detail query did not preserve the documented role")
    if _detail_params({"role": "unknown"}) is not None:
        raise AssertionError("Detail query invented an undocumented role")

    authorization, headers = bce_authorization(
        "test-ak",
        "test-sk",
        "bcc.bj.baidubce.com",
        "/v1/vpc",
        {"maxKeys": 1000},
        timestamp="2026-08-13T08:00:00Z",
    )
    expected_signature = (
        "bce-auth-v1/test-ak/2026-08-13T08:00:00Z/1800/host;x-bce-date/"
        "cc1821bf523e9a38f8c086c48b2874f1555c7f672c4fa7ccd91e9d0de24dc889"
    )
    if authorization != expected_signature or headers.get("Authorization") != authorization:
        raise AssertionError("Signer output no longer matches the official SDK test vector")

    with tempfile.TemporaryDirectory() as temporary_dir:
        credentials_path = Path(temporary_dir) / "credentials.json"
        credentials_path.write_text(
            json.dumps({"accessKeyId": "file-ak", "secretAccessKey": "file-sk"}),
            encoding="utf-8",
        )
        credentials_path.chmod(0o600)
        loaded = _read_credentials_file(credentials_path)
        if loaded != ("file-ak", "file-sk", None):
            raise AssertionError("Credentials file loader returned unexpected values")
        credentials_path.chmod(0o644)
        try:
            _read_credentials_file(credentials_path)
        except ValueError as exc:
            if "permissions" not in str(exc):
                raise
        else:
            raise AssertionError("Credentials file loader accepted broad permissions")

    print(
        "Self-test passed: fixture analysis, GET-only and endpoint guards, pagination, "
        "detail-role handling, credential-file guards, and deterministic signer"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Baidu AI Cloud VPC peering inventory and status audit"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--input", type=Path, help="Analyze an existing normalized inventory JSON")
    mode.add_argument("--self-test", action="store_true", help="Run local tests without network access")
    parser.add_argument("--regions", help="Comma-separated BCE region codes for live collection")
    parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Owner-only (chmod 600) JSON credential file outside the Skill package",
    )
    parser.add_argument(
        "--endpoint",
        action="append",
        help="HTTPS endpoint override in REGION=https://host form; may be repeated",
    )
    parser.add_argument("--output-dir", type=Path, help="Directory for inventory.json and report.md")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=3, help="GET retry count for 429 and 5xx")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing output files")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        if not args.output_dir:
            parser.error("--output-dir is required unless --self-test is used")
        inventory = load_inventory(args.input) if args.input else collect_live(args)
        analysis = analyze_inventory(inventory)
        inventory_path, report_path = write_outputs(
            args.output_dir, inventory, analysis, overwrite=args.overwrite
        )
        print(f"Inventory: {inventory_path}")
        print(f"Report: {report_path}")
        incomplete = any(
            data.get("coverage", {}).get(operation, {}).get("status") != "success"
            for data in inventory.get("regions", {}).values()
            for operation in ("listPeerConnections", "detailPeerConnections")
        )
        return 2 if incomplete else 0
    except (ApiFailure, FileExistsError, OSError, ValueError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only Baidu AI Cloud PrivateZone-to-VPC association audit."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import re
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
ENDPOINT = "https://privatezone.baidubce.com"
HOST = "privatezone.baidubce.com"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
BEIJING_TZ = dt.timezone(dt.timedelta(hours=8))


class ApiFailure(RuntimeError):
    """Sanitized API failure without authorization material."""

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


def bce_headers(
    access_key: str,
    secret_key: str,
    path: str,
    params: dict[str, Any] | None,
    *,
    timestamp: str,
    session_token: str | None = None,
    expiration_seconds: int = 1800,
) -> dict[str, str]:
    canonical_uri = _quote(path, keep_slash=True)
    auth_prefix = f"bce-auth-v1/{access_key}/{timestamp}/{expiration_seconds}"
    signing_key = hmac.new(
        secret_key.encode("utf-8"), auth_prefix.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    signed = {"host": HOST, "x-bce-date": timestamp}
    if session_token:
        signed["x-bce-security-token"] = session_token
    signed_names = sorted(signed)
    canonical_headers = "\n".join(
        f"{_quote(name.lower())}:{_quote(str(signed[name]).strip())}" for name in signed_names
    )
    string_to_sign = "\n".join(("GET", canonical_uri, canonical_query(params), canonical_headers))
    signature = hmac.new(
        signing_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    result = {
        "Host": HOST,
        "x-bce-date": timestamp,
        "Authorization": f"{auth_prefix}/{';'.join(signed_names)}/{signature}",
        "Accept": "application/json",
        "Content-Type": "application/json;charset=utf-8",
        "User-Agent": "baiducloud-privatezone-vpc-association-audit/1.0",
    }
    if session_token:
        result["x-bce-security-token"] = session_token
    return result


class ReadOnlyBceClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        session_token: str | None = None,
        *,
        timeout: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.timeout = timeout
        self.max_retries = max_retries

    def _redact(self, text: str) -> str:
        result = text[:500]
        for value in (self.access_key, self.secret_key, self.session_token):
            if value:
                result = result.replace(value, "[REDACTED]")
        return result

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
        url = f"{ENDPOINT}{path}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(self.max_retries + 1):
            timestamp = utc_now()
            headers = bce_headers(
                self.access_key,
                self.secret_key,
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
                detail = _parse_error_body(exc.read().decode("utf-8", errors="replace"))
                if exc.code in RETRYABLE_STATUS and attempt < self.max_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise ApiFailure(
                    exc.code,
                    self._redact(str(detail.get("message") or f"HTTP {exc.code}")),
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
                raise ApiFailure(
                    None, self._redact(f"Network error: {reason or exc}"), path=path
                ) from None
            except json.JSONDecodeError as exc:
                raise ApiFailure(None, f"Invalid JSON response: {exc}", path=path) from None
        raise ApiFailure(None, "Request failed after retries", path=path)

    def paginate(
        self,
        path: str,
        item_fields: Iterable[str],
        params: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query = dict(params or {})
        query.setdefault("maxKeys", 1000)
        marker: str | None = None
        seen_markers: set[str] = set()
        items: list[dict[str, Any]] = []
        queries = 0
        while True:
            if marker:
                query["marker"] = marker
            response = self.request_json(path, query)
            queries += 1
            items.extend(item for item in _first_list(response, item_fields) if isinstance(item, dict))
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
        return items, queries


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


def _normalize_zone_name(value: Any) -> str:
    text = str(value or "").strip().rstrip(".")
    if not text:
        return ""
    try:
        return text.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return text.lower()


def _valid_zone_name(value: str) -> bool:
    normalized = _normalize_zone_name(value)
    if not normalized or len(normalized) > 253 or ".." in normalized:
        return False
    for label in normalized.split("."):
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not re.fullmatch(r"[a-z0-9_-]+", label):
            return False
    return True


def _parse_requested_zones(value: str | None) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if not _valid_zone_name(item):
            raise ValueError(f"Invalid private zone name: {item}")
        normalized = _normalize_zone_name(item)
        if normalized not in result:
            result.append(normalized)
    return result


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _read_credentials_file(path: Path) -> tuple[str, str, str | None]:
    skill_root = Path(__file__).resolve().parents[1]
    if _is_within(path, skill_root):
        raise ValueError("Credentials file must be outside the Skill directory")
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

    requested = _parse_requested_zones(args.zones)
    inventory: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "mode": "live",
        "endpoint": ENDPOINT,
        "selection": {"requestedZones": requested, "unmatchedZones": []},
        "coverage": {
            "listPrivateZones": {
                "status": "notAttempted",
                "count": 0,
                "queries": 0,
                "failedQueries": 0,
            },
            "detailPrivateZones": {
                "status": "notAttempted",
                "successfulZones": 0,
                "failedZones": 0,
                "queries": 0,
            },
        },
        "zones": [],
        "errors": [],
    }
    client = ReadOnlyBceClient(
        access_key,
        secret_key,
        session_token,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    try:
        summaries, query_count = client.paginate("/v1/privatezone", ("zones",))
    except ApiFailure as exc:
        inventory["coverage"]["listPrivateZones"].update(status="failed", failedQueries=1)
        inventory["coverage"]["detailPrivateZones"].update(
            status="blocked", reason="PrivateZone list query failed"
        )
        inventory["errors"].append(exc.to_dict("listPrivateZones"))
        return inventory

    inventory["coverage"]["listPrivateZones"].update(
        status="success", count=len(summaries), queries=query_count
    )
    if requested:
        selected = [
            item for item in summaries
            if _normalize_zone_name(item.get("zoneName")) in requested
        ]
        matched = {
            _normalize_zone_name(item.get("zoneName")) for item in selected
        }
        inventory["selection"]["unmatchedZones"] = [
            name for name in requested if name not in matched
        ]
    else:
        selected = summaries

    detail_coverage = inventory["coverage"]["detailPrivateZones"]
    for summary in selected:
        item = dict(summary)
        item["_listSnapshot"] = dict(summary)
        zone_id = str(summary.get("zoneId") or "").strip()
        if not zone_id:
            item["_detailStatus"] = "failed"
            detail_coverage["failedZones"] += 1
            inventory["errors"].append(
                {
                    "operation": "detailPrivateZone",
                    "code": "MissingZoneId",
                    "message": "PrivateZone list item did not contain zoneId",
                    "scope": _optional_string(summary.get("zoneName")),
                }
            )
            inventory["zones"].append(item)
            continue
        detail_coverage["queries"] += 1
        path = f"/v1/privatezone/{_quote(zone_id)}"
        try:
            detail = client.request_json(path)
            item.update(detail)
            item.setdefault("zoneId", zone_id)
            item["_detailStatus"] = "success"
            detail_coverage["successfulZones"] += 1
        except ApiFailure as exc:
            item["_detailStatus"] = "failed"
            detail_coverage["failedZones"] += 1
            inventory["errors"].append(exc.to_dict("detailPrivateZone", zone_id))
        inventory["zones"].append(item)

    if detail_coverage["failedZones"]:
        detail_coverage["status"] = (
            "partial" if detail_coverage["successfulZones"] else "failed"
        )
    else:
        detail_coverage["status"] = "success"
    return inventory


def load_inventory(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        inventory = json.load(handle)
    if not isinstance(inventory, dict) or not isinstance(inventory.get("zones"), list):
        raise ValueError("Inventory must be a JSON object containing a zones list")
    inventory.setdefault("schemaVersion", SCHEMA_VERSION)
    inventory.setdefault("generatedAt", utc_now())
    inventory["mode"] = "offline"
    inventory.setdefault("endpoint", "offline")
    inventory.setdefault("selection", {"requestedZones": [], "unmatchedZones": []})
    inventory.setdefault("errors", [])
    successful = 0
    failed = 0
    for index, zone in enumerate(inventory["zones"]):
        if not isinstance(zone, dict):
            raise ValueError(f"Zone at index {index} must be an object")
        status = zone.setdefault("_detailStatus", "unknown")
        if status == "success":
            successful += 1
        elif status == "failed":
            failed += 1
    coverage = inventory.setdefault("coverage", {})
    coverage.setdefault(
        "listPrivateZones",
        {
            "status": "unknown",
            "count": len(inventory["zones"]),
            "queries": 0,
            "failedQueries": 0,
        },
    )
    coverage.setdefault(
        "detailPrivateZones",
        {
            "status": "unknown",
            "successfulZones": successful,
            "failedZones": failed,
            "queries": 0,
        },
    )
    return inventory


def _finding(
    rule_id: str,
    severity: str,
    zone: dict[str, Any] | None,
    vpc: dict[str, Any] | None,
    fact: str,
    interpretation: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    zone = zone or {}
    vpc = vpc or {}
    return {
        "ruleId": rule_id,
        "severity": severity,
        "zoneId": _optional_string(zone.get("zoneId")),
        "zoneName": _optional_string(zone.get("zoneName")),
        "vpcId": _optional_string(vpc.get("vpcId")),
        "vpcName": _optional_string(vpc.get("vpcName")),
        "vpcRegion": _optional_string(vpc.get("vpcRegion")),
        "fact": fact,
        "interpretation": interpretation,
        "evidence": evidence or {},
    }


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
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
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed.astimezone(dt.timezone.utc)


def _list_snapshot(zone: dict[str, Any]) -> dict[str, Any]:
    snapshot = zone.get("_listSnapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _edge_key(vpc: dict[str, Any]) -> tuple[str, str] | None:
    vpc_id = str(vpc.get("vpcId") or "").strip()
    region = str(vpc.get("vpcRegion") or "").strip().lower()
    if not vpc_id or not region:
        return None
    return region, vpc_id


def _is_parent_zone(parent: str, child: str) -> bool:
    return bool(parent and child and parent != child and child.endswith(f".{parent}"))


def analyze_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    region_distribution: Counter[str] = Counter()
    zones_per_region: defaultdict[str, set[str]] = defaultdict(set)
    unique_vpcs: set[tuple[str, str]] = set()
    association_count = 0
    zone_edges: list[tuple[dict[str, Any], str, set[tuple[str, str]]]] = []
    vpc_regions: defaultdict[str, set[str]] = defaultdict(set)
    vpc_names: defaultdict[tuple[str, str], set[str]] = defaultdict(set)

    zones_by_id = {
        str(zone.get("zoneId") or ""): zone
        for zone in inventory.get("zones", [])
        if isinstance(zone, dict) and zone.get("zoneId")
    }
    for error in inventory.get("errors", []):
        if not isinstance(error, dict):
            continue
        status_code = error.get("status")
        rule_id = (
            "COV-002"
            if status_code in (401, 403)
            else "COV-004"
            if status_code == 404
            else "COV-001"
        )
        severity = "info" if rule_id == "COV-004" else "high"
        zone = zones_by_id.get(str(error.get("scope") or ""))
        findings.append(
            _finding(
                rule_id,
                severity,
                zone,
                None,
                f"{error.get('operation', 'query')} 查询失败，状态为 {status_code or 'network-error'}",
                "该范围的 PrivateZone 或 VPC 关联覆盖不完整",
                evidence={
                    key: error.get(key)
                    for key in ("operation", "status", "code", "requestId", "path", "scope")
                    if error.get(key) is not None
                },
            )
        )

    unmatched = inventory.get("selection", {}).get("unmatchedZones", [])
    if isinstance(unmatched, list):
        for zone_name in unmatched:
            findings.append(
                _finding(
                    "COV-001",
                    "high",
                    {"zoneName": zone_name},
                    None,
                    "指定私有域未在成功返回的列表中精确匹配",
                    "可能是域不存在、当前身份不可见或名称输入有误，不能视为已审计",
                    evidence={"requestedZone": zone_name},
                )
            )

    listed_ids: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for zone in inventory.get("zones", []):
        if not isinstance(zone, dict):
            continue
        snapshot = _list_snapshot(zone)
        list_zone_id = str(snapshot.get("zoneId") or zone.get("zoneId") or "").strip()
        if list_zone_id:
            listed_ids[list_zone_id].append(zone)

        if zone.get("_detailStatus") != "success":
            continue

        detail_zone_id = str(zone.get("zoneId") or "").strip()
        detail_zone_name = str(zone.get("zoneName") or "").strip()
        list_zone_name = str(snapshot.get("zoneName") or "").strip()
        if snapshot and list_zone_id and detail_zone_id != list_zone_id:
            findings.append(
                _finding(
                    "PZ-003",
                    "high",
                    zone,
                    None,
                    "详情 zoneId 与列表项不一致",
                    "PrivateZone 身份证据冲突",
                    evidence={"listZoneId": list_zone_id, "detailZoneId": detail_zone_id},
                )
            )
        if snapshot and _normalize_zone_name(list_zone_name) != _normalize_zone_name(detail_zone_name):
            findings.append(
                _finding(
                    "PZ-003",
                    "medium",
                    zone,
                    None,
                    "详情 zoneName 与列表项不一致",
                    "名称可能在两次查询之间变化，或返回证据不一致",
                    evidence={"listZoneName": list_zone_name, "detailZoneName": detail_zone_name},
                )
            )

        record_count = zone.get("recordCount")
        if not isinstance(record_count, int) or isinstance(record_count, bool) or record_count < 0:
            findings.append(
                _finding(
                    "PZ-005",
                    "high",
                    zone,
                    None,
                    f"recordCount 为 {record_count!r}",
                    "记录数量必须是非负整数",
                    evidence={"recordCount": record_count},
                )
            )
        if snapshot and snapshot.get("recordCount") != record_count:
            findings.append(
                _finding(
                    "PZ-004",
                    "info",
                    zone,
                    None,
                    "列表与详情的 recordCount 不一致",
                    "两次 GET 之间可能发生了配置变化",
                    evidence={
                        "listRecordCount": snapshot.get("recordCount"),
                        "detailRecordCount": record_count,
                    },
                )
            )

        create_raw = zone.get("createTime")
        update_raw = zone.get("updateTime")
        created = _parse_timestamp(create_raw)
        updated = _parse_timestamp(update_raw)
        if create_raw and created is None:
            findings.append(_finding("PZ-006", "info", zone, None, "createTime 无法解析", "时间字段需要人工解释", evidence={"createTime": create_raw}))
        if update_raw and updated is None:
            findings.append(_finding("PZ-006", "info", zone, None, "updateTime 无法解析", "时间字段需要人工解释", evidence={"updateTime": update_raw}))
        if created is not None and updated is not None and updated < created:
            findings.append(_finding("PZ-006", "medium", zone, None, "updateTime 早于 createTime", "时间顺序与资源生命周期不一致", evidence={"createTime": create_raw, "updateTime": update_raw}))

        if "bindVpcs" not in zone or not isinstance(zone.get("bindVpcs"), list):
            findings.append(
                _finding(
                    "PZ-002",
                    "high",
                    zone,
                    None,
                    "详情未返回列表类型的 bindVpcs",
                    "无法确认该 PrivateZone 的 VPC 关联",
                    evidence={"bindVpcsType": type(zone.get("bindVpcs")).__name__},
                )
            )
            continue

        bind_vpcs = zone["bindVpcs"]
        if not bind_vpcs:
            findings.append(
                _finding(
                    "PZ-001",
                    "medium",
                    zone,
                    None,
                    "详情查询成功且 bindVpcs 为空",
                    "该私有域当前未向任何返回的 VPC 暴露；可能是暂存配置",
                    evidence={"associationCount": 0},
                )
            )

        edge_groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        valid_edges: set[tuple[str, str]] = set()
        for value in bind_vpcs:
            if not isinstance(value, dict):
                findings.append(_finding("PZ-101", "high", zone, None, "bindVpcs 包含非对象项", "关联边无法解析", evidence={"valueType": type(value).__name__}))
                continue
            association_count += 1
            vpc_id = str(value.get("vpcId") or "").strip()
            region = str(value.get("vpcRegion") or "").strip().lower()
            vpc_name = str(value.get("vpcName") or "").strip()
            if not vpc_id or not region:
                findings.append(
                    _finding(
                        "PZ-101",
                        "high",
                        zone,
                        value,
                        "VPC 关联缺少 vpcId 或 vpcRegion",
                        "该关联边不能被唯一识别",
                        evidence={"vpcId": value.get("vpcId"), "vpcRegion": value.get("vpcRegion")},
                    )
                )
            if not vpc_name:
                findings.append(_finding("PZ-103", "info", zone, value, "VPC 关联缺少 vpcName", "名称元数据不完整，但 ID 和地域仍可用于识别", evidence={"vpcId": vpc_id or None, "vpcRegion": region or None}))
            key = _edge_key(value)
            if key is not None:
                valid_edges.add(key)
                unique_vpcs.add(key)
                edge_groups[key].append(value)
                region_distribution[key[0]] += 1
                zones_per_region[key[0]].add(detail_zone_id or list_zone_id)
                vpc_regions[key[1]].add(key[0])
                if vpc_name:
                    vpc_names[key].add(vpc_name)

        for key, duplicates in edge_groups.items():
            if len(duplicates) > 1:
                findings.append(
                    _finding(
                        "PZ-102",
                        "medium",
                        zone,
                        duplicates[0],
                        f"同一 PrivateZone 重复返回 {len(duplicates)} 条相同地域/VPC 关联",
                        "关联证据可能冗余或不一致",
                        evidence={"vpcRegion": key[0], "vpcId": key[1], "occurrences": len(duplicates)},
                    )
                )

        if (
            isinstance(record_count, int)
            and not isinstance(record_count, bool)
            and record_count == 0
            and valid_edges
        ):
            findings.append(
                _finding(
                    "PZ-108",
                    "low",
                    zone,
                    None,
                    "零记录 PrivateZone 仍关联到 VPC",
                    "可能用于预留或屏蔽命名空间，需要确认设计意图",
                    evidence={"recordCount": 0, "validAssociationCount": len(valid_edges)},
                )
            )

        regions = sorted({key[0] for key in valid_edges})
        if len(regions) > 1:
            findings.append(
                _finding(
                    "PZ-109",
                    "info",
                    zone,
                    None,
                    "PrivateZone 关联到多个地域的 VPC",
                    "这是跨地域解析暴露范围，需纳入架构和变更责任边界",
                    evidence={"regions": regions},
                )
            )
        zone_edges.append((zone, _normalize_zone_name(detail_zone_name), valid_edges))

    for zone_id, duplicates in listed_ids.items():
        if len(duplicates) > 1:
            findings.append(
                _finding(
                    "PZ-110",
                    "high",
                    duplicates[0],
                    None,
                    f"PrivateZone 列表重复返回 zoneId {zone_id}",
                    "列表快照包含重复身份，需要核对分页和服务返回",
                    evidence={"zoneId": zone_id, "occurrences": len(duplicates)},
                )
            )

    for vpc_id, regions in vpc_regions.items():
        if len(regions) > 1:
            findings.append(
                _finding(
                    "PZ-104",
                    "high",
                    None,
                    {"vpcId": vpc_id},
                    "同一 VPC ID 出现在多个地域",
                    "VPC 地域元数据相互冲突",
                    evidence={"vpcId": vpc_id, "regions": sorted(regions)},
                )
            )
    for (region, vpc_id), names in vpc_names.items():
        if len(names) > 1:
            findings.append(
                _finding(
                    "PZ-105",
                    "medium",
                    None,
                    {"vpcId": vpc_id, "vpcRegion": region},
                    "同一地域/VPC ID 返回多个非空名称",
                    "VPC 命名元数据在不同 PrivateZone 详情间不一致",
                    evidence={"vpcRegion": region, "vpcId": vpc_id, "vpcNames": sorted(names)},
                )
            )

    for left_index, (left_zone, left_name, left_edges) in enumerate(zone_edges):
        left_id = str(left_zone.get("zoneId") or "")
        for right_zone, right_name, right_edges in zone_edges[left_index + 1 :]:
            right_id = str(right_zone.get("zoneId") or "")
            if left_id and right_id and left_id == right_id:
                continue
            overlap = sorted(left_edges & right_edges)
            if not overlap:
                continue
            if left_name and left_name == right_name:
                for region, vpc_id in overlap:
                    findings.append(
                        _finding(
                            "PZ-106",
                            "high",
                            left_zone,
                            {"vpcId": vpc_id, "vpcRegion": region},
                            "同名 PrivateZone 的不同 zoneId 关联到同一 VPC",
                            "同一 VPC 视图中出现重复私有 DNS 命名空间",
                            evidence={
                                "normalizedZoneName": left_name,
                                "zoneIds": sorted(filter(None, (left_id, right_id))),
                                "vpcRegion": region,
                                "vpcId": vpc_id,
                            },
                        )
                    )
            elif _is_parent_zone(left_name, right_name) or _is_parent_zone(right_name, left_name):
                parent = left_name if _is_parent_zone(left_name, right_name) else right_name
                child = right_name if parent == left_name else left_name
                for region, vpc_id in overlap:
                    findings.append(
                        _finding(
                            "PZ-107",
                            "info",
                            left_zone,
                            {"vpcId": vpc_id, "vpcRegion": region},
                            "父域与子域 PrivateZone 同时关联到同一 VPC",
                            "更具体的私有域可能有意形成独立解析边界，需要确认所有权",
                            evidence={"parentZone": parent, "childZone": child, "vpcRegion": region, "vpcId": vpc_id},
                        )
                    )

    findings.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity")), 9),
            str(item.get("zoneName") or ""),
            str(item.get("ruleId") or ""),
            str(item.get("vpcRegion") or ""),
            str(item.get("vpcId") or ""),
        )
    )
    return {
        "summary": {
            "zoneCount": len([zone for zone in inventory.get("zones", []) if isinstance(zone, dict)]),
            "associationCount": association_count,
            "uniqueVpcCount": len(unique_vpcs),
            "findingsBySeverity": dict(Counter(item["severity"] for item in findings)),
            "associationDistributionByRegion": dict(sorted(region_distribution.items())),
            "zoneCountByAssociatedRegion": {
                region: len(zone_ids) for region, zone_ids in sorted(zones_per_region.items())
            },
        },
        "findings": findings,
    }


def _markdown(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_report(inventory: dict[str, Any]) -> str:
    analysis = inventory.get("analysis", {})
    summary = analysis.get("summary", {})
    findings = analysis.get("findings", [])
    list_coverage = inventory.get("coverage", {}).get("listPrivateZones", {})
    detail_coverage = inventory.get("coverage", {}).get("detailPrivateZones", {})
    lines = [
        "# 百度智能云 PrivateZone 与 VPC 关联配置审计报告",
        "",
        f"- 生成时间：{_markdown(inventory.get('generatedAt'))}",
        f"- 模式：{_markdown(inventory.get('mode'))}",
        f"- Endpoint：{_markdown(inventory.get('endpoint'))}",
        f"- PrivateZone 数：{summary.get('zoneCount', 0)}",
        f"- 关联边数：{summary.get('associationCount', 0)}",
        f"- 唯一地域/VPC 数：{summary.get('uniqueVpcCount', 0)}",
        "",
        "## 采集覆盖率",
        "",
        "| 操作 | 状态 | 成功/数量 | 失败 | GET 请求数 |",
        "|---|---|---:|---:|---:|",
        f"| PrivateZone 列表 | {_markdown(list_coverage.get('status'))} | {list_coverage.get('count', 0)} | {list_coverage.get('failedQueries', 0)} | {list_coverage.get('queries', 0)} |",
        f"| PrivateZone 详情 | {_markdown(detail_coverage.get('status'))} | {detail_coverage.get('successfulZones', 0)} | {detail_coverage.get('failedZones', 0)} | {detail_coverage.get('queries', 0)} |",
        "",
    ]
    unmatched = inventory.get("selection", {}).get("unmatchedZones", [])
    if unmatched:
        lines.extend([f"指定但未精确匹配的私有域：{', '.join(_markdown(item) for item in unmatched)}", ""])

    lines.extend([
        "## 关联拓扑",
        "",
        "| PrivateZone | Zone ID | 记录数 | 详情覆盖 | VPC 地域 | VPC ID | VPC 名称 |",
        "|---|---|---:|---|---|---|---|",
    ])
    for zone in inventory.get("zones", []):
        if not isinstance(zone, dict):
            continue
        bind_vpcs = zone.get("bindVpcs")
        if zone.get("_detailStatus") != "success" or not isinstance(bind_vpcs, list):
            lines.append(f"| {_markdown(zone.get('zoneName'))} | {_markdown(zone.get('zoneId'))} | {_markdown(zone.get('recordCount'))} | {_markdown(zone.get('_detailStatus'))} | - | - | - |")
        elif not bind_vpcs:
            lines.append(f"| {_markdown(zone.get('zoneName'))} | {_markdown(zone.get('zoneId'))} | {_markdown(zone.get('recordCount'))} | success | 无关联 | - | - |")
        else:
            for index, vpc in enumerate(bind_vpcs):
                vpc = vpc if isinstance(vpc, dict) else {}
                lines.append(
                    f"| {_markdown(zone.get('zoneName')) if index == 0 else '↳'} | "
                    f"{_markdown(zone.get('zoneId')) if index == 0 else '↳'} | "
                    f"{_markdown(zone.get('recordCount')) if index == 0 else '↳'} | "
                    f"success | {_markdown(vpc.get('vpcRegion'))} | {_markdown(vpc.get('vpcId'))} | {_markdown(vpc.get('vpcName'))} |"
                )

    lines.extend([
        "",
        "## 地域分布",
        "",
        f"- 关联边：`{json.dumps(summary.get('associationDistributionByRegion', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- 关联 PrivateZone 数：`{json.dumps(summary.get('zoneCountByAssociatedRegion', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## 发现",
        "",
    ])
    if not findings:
        lines.append("在成功查询且规则覆盖的配置范围内未发现规则命中。")
    else:
        lines.extend([
            "| 严重度 | 规则 | PrivateZone | VPC | 事实 |",
            "|---|---|---|---|---|",
        ])
        for item in findings:
            zone_label = f"{item.get('zoneName') or '-'} / {item.get('zoneId') or '-'}"
            vpc_label = f"{item.get('vpcRegion') or '-'} / {item.get('vpcId') or '-'}"
            lines.append(f"| {_markdown(item.get('severity'))} | {_markdown(item.get('ruleId'))} | {_markdown(zone_label)} | {_markdown(vpc_label)} | {_markdown(item.get('fact'))} |")
        lines.extend(["", "### 证据与解释", ""])
        for item in findings:
            identity = f"{item.get('zoneName') or '-'} / {item.get('vpcRegion') or '-'} / {item.get('vpcId') or '-'}"
            lines.extend([
                f"- **{_markdown(item.get('severity')).upper()} {item.get('ruleId')} — {_markdown(identity)}**：{_markdown(item.get('fact'))}",
                f"  - 解释：{_markdown(item.get('interpretation'))}",
                f"  - 证据：`{json.dumps(item.get('evidence', {}), ensure_ascii=False, sort_keys=True)}`",
            ])

    lines.extend([
        "",
        "## 限制",
        "",
        "- 本报告只反映 PrivateZone 控制面在采集时刻返回的关联配置。",
        "- 未调用 VPC API，不能证明 VPC 存在、状态正常、CIDR 正确或网络可达。",
        "- 未执行 DNS 查询，不验证私有域应答、递归/转发路径、记录内容或业务可用性。",
        "- 同名域用于隔离不同 VPC、父子域形成独立边界、零记录域和跨地域关联都可能是有意设计。",
        "- 查询失败的范围不计为无资源或无关联，也不能形成无风险结论。",
        "",
    ])
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_outputs(inventory: dict[str, Any], output_dir: Path) -> None:
    skill_root = Path(__file__).resolve().parents[1]
    if _is_within(output_dir, skill_root):
        raise ValueError("Output directory must be outside the Skill directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        output_dir / "inventory.json",
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write(output_dir / "report.md", render_report(inventory))


def self_test() -> None:
    assert canonical_query({"maxKeys": 1000, "marker": "a b"}) == "marker=a%20b&maxKeys=1000"
    headers = bce_headers(
        "ak",
        "sk",
        "/v1/privatezone",
        {"maxKeys": 1000},
        timestamp="2026-01-01T00:00:00Z",
    )
    assert headers["Authorization"].startswith("bce-auth-v1/ak/")
    client = ReadOnlyBceClient("ak", "sk", max_retries=0)
    try:
        client.request_json("/v1/privatezone", method="POST")
    except ValueError as exc:
        assert "non-GET" in str(exc)
    else:
        raise AssertionError("Read-only guard did not reject POST")
    assert _normalize_zone_name("CORP.Example.") == "corp.example"
    assert _is_parent_zone("corp.example", "api.corp.example")

    sample = {
        "selection": {"unmatchedZones": []},
        "errors": [],
        "zones": [
            {
                "zoneId": "z1",
                "zoneName": "corp.example",
                "recordCount": 0,
                "createTime": "2026-01-01 00:00:00",
                "updateTime": "2026-01-02 00:00:00",
                "bindVpcs": [{"vpcId": "v1", "vpcName": "one", "vpcRegion": "bj"}],
                "_detailStatus": "success",
            },
            {
                "zoneId": "z2",
                "zoneName": "CORP.EXAMPLE.",
                "recordCount": 1,
                "createTime": "2026-01-01 00:00:00",
                "updateTime": "2026-01-02 00:00:00",
                "bindVpcs": [
                    {"vpcId": "v1", "vpcName": "two", "vpcRegion": "bj"},
                    {"vpcId": "v1", "vpcName": "two", "vpcRegion": "bj"},
                ],
                "_detailStatus": "success",
            },
            {
                "zoneId": "z3",
                "zoneName": "empty.example",
                "recordCount": 2,
                "createTime": "2026-01-01 00:00:00",
                "updateTime": "2026-01-02 00:00:00",
                "bindVpcs": [],
                "_detailStatus": "success",
            },
        ],
    }
    rule_ids = {item["ruleId"] for item in analyze_inventory(sample)["findings"]}
    assert {"PZ-001", "PZ-102", "PZ-105", "PZ-106", "PZ-108"}.issubset(rule_ids)
    print("self-test: ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Baidu AI Cloud PrivateZone-to-VPC association audit"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--input", type=Path, help="Offline inventory JSON")
    mode.add_argument("--self-test", action="store_true", help="Run local tests without network access")
    parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Owner-only JSON credential file outside the Skill directory",
    )
    parser.add_argument("--zones", help="Comma-separated exact PrivateZone names; live mode only")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory outside the Skill for inventory.json and report.md",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        choices=range(0, 6),
        help="Retries for the same GET request",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            self_test()
            return 0
        if not args.output_dir:
            parser.error("--output-dir is required unless --self-test is used")
        if args.input:
            if args.credentials_file or args.zones:
                parser.error("--credentials-file and --zones cannot be used with --input")
            inventory = load_inventory(args.input)
        else:
            inventory = collect_live(args)
        inventory["analysis"] = analyze_inventory(inventory)
        write_outputs(inventory, args.output_dir)
        summary = inventory["analysis"]["summary"]
        print(
            "audit complete: "
            f"zones={summary['zoneCount']} "
            f"associations={summary['associationCount']} "
            f"unique_vpcs={summary['uniqueVpcCount']} "
            f"findings={len(inventory['analysis']['findings'])}"
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

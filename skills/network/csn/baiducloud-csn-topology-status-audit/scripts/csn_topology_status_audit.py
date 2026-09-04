#!/usr/bin/env python3
"""Read-only Baidu AI Cloud CSN topology and status audit."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
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
ENDPOINT = "https://csn.baidubce.com"
HOST = "csn.baidubce.com"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
KNOWN_INSTANCE_STATUSES = {"attached", "attaching", "detaching", "attach_failed"}
TRANSITIONAL_INSTANCE_STATUSES = {"attaching", "detaching"}
KNOWN_INSTANCE_TYPES = {"vpc", "channel", "bec_vpc"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


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
        "User-Agent": "baiducloud-csn-topology-status-audit/1.0",
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
        query_count = 0
        while True:
            if marker:
                query["marker"] = marker
            response = self.request_json(path, query)
            query_count += 1
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
        return items, query_count


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


def _parse_requested_ids(value: str | None) -> list[str]:
    result: list[str] = []
    for raw in (value or "").split(","):
        item = raw.strip()
        if not item:
            continue
        if not all(character.isalnum() or character in "-_" for character in item):
            raise ValueError(f"Invalid CSN ID: {item}")
        if item not in result:
            result.append(item)
    return result


def _coverage_status(success: int, failed: int, skipped: int = 0) -> str:
    if failed or skipped:
        return "failed" if success == 0 else "partial"
    return "success"


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

    client = ReadOnlyBceClient(
        access_key,
        secret_key,
        session_token,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    requested_ids = _parse_requested_ids(args.csn_ids)
    inventory: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "mode": "live",
        "endpoint": ENDPOINT,
        "selection": {"requestedCsnIds": requested_ids, "unmatchedCsnIds": []},
        "coverage": {
            "listCsns": {"status": "pending", "count": 0, "queries": 0, "failedQueries": 0},
            "detailCsns": {
                "status": "pending", "successfulCsns": 0, "failedCsns": 0,
                "skippedCsns": 0, "queries": 0,
            },
            "listInstances": {
                "status": "pending", "successfulCsns": 0, "failedCsns": 0,
                "skippedCsns": 0, "queries": 0, "instanceCount": 0,
            },
        },
        "csns": [],
        "errors": [],
    }
    list_coverage = inventory["coverage"]["listCsns"]
    try:
        summaries, query_count = client.paginate("/v1/csn", ("csns",))
        list_coverage.update(status="success", count=len(summaries), queries=query_count)
    except ApiFailure as exc:
        list_coverage.update(status="failed", queries=1, failedQueries=1)
        inventory["coverage"]["detailCsns"].update(status="blocked")
        inventory["coverage"]["listInstances"].update(status="blocked")
        inventory["errors"].append(exc.to_dict("listCsns"))
        return inventory

    if requested_ids:
        available = {_optional_string(item.get("csnId")) for item in summaries}
        inventory["selection"]["unmatchedCsnIds"] = [
            item for item in requested_ids if item not in available
        ]
        selected = [item for item in summaries if _optional_string(item.get("csnId")) in requested_ids]
    else:
        selected = summaries

    detail_coverage = inventory["coverage"]["detailCsns"]
    instance_coverage = inventory["coverage"]["listInstances"]
    for summary in selected:
        item = dict(summary)
        item["_listSnapshot"] = dict(summary)
        item["instances"] = []
        csn_id = _optional_string(summary.get("csnId"))
        if not csn_id:
            item["_detailStatus"] = "skipped"
            item["_instancesStatus"] = "skipped"
            detail_coverage["skippedCsns"] += 1
            instance_coverage["skippedCsns"] += 1
            inventory["csns"].append(item)
            continue

        detail_path = f"/v1/csn/{_quote(csn_id)}"
        detail_coverage["queries"] += 1
        try:
            detail = client.request_json(detail_path)
            item.update(detail)
            item.setdefault("csnId", csn_id)
            item["_detailStatus"] = "success"
            detail_coverage["successfulCsns"] += 1
        except ApiFailure as exc:
            item["_detailStatus"] = "failed"
            detail_coverage["failedCsns"] += 1
            inventory["errors"].append(exc.to_dict("detailCsns", csn_id))

        instance_path = f"/v1/csn/{_quote(csn_id)}/instance"
        try:
            instances, query_count = client.paginate(instance_path, ("instances",))
            instance_coverage["queries"] += query_count
            item["instances"] = instances
            item["_instancesStatus"] = "success"
            instance_coverage["successfulCsns"] += 1
            instance_coverage["instanceCount"] += len(instances)
        except ApiFailure as exc:
            item["_instancesStatus"] = "failed"
            instance_coverage["failedCsns"] += 1
            inventory["errors"].append(exc.to_dict("listInstances", csn_id))
        inventory["csns"].append(item)

    detail_coverage["status"] = _coverage_status(
        detail_coverage["successfulCsns"], detail_coverage["failedCsns"], detail_coverage["skippedCsns"]
    )
    instance_coverage["status"] = _coverage_status(
        instance_coverage["successfulCsns"],
        instance_coverage["failedCsns"],
        instance_coverage["skippedCsns"],
    )
    return inventory


def load_inventory(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        inventory = json.load(handle)
    if not isinstance(inventory, dict) or not isinstance(inventory.get("csns"), list):
        raise ValueError("Inventory must be a JSON object containing a csns list")
    inventory.setdefault("schemaVersion", SCHEMA_VERSION)
    inventory.setdefault("generatedAt", utc_now())
    inventory["mode"] = "offline"
    inventory.setdefault("endpoint", "offline")
    inventory.setdefault("selection", {"requestedCsnIds": [], "unmatchedCsnIds": []})
    inventory.setdefault("errors", [])
    coverage = inventory.setdefault("coverage", {})
    csns = inventory["csns"]
    coverage.setdefault(
        "listCsns", {"status": "unknown", "count": len(csns), "queries": 0, "failedQueries": 0}
    )
    coverage.setdefault(
        "detailCsns",
        {
            "status": "unknown",
            "successfulCsns": sum(
                1 for item in csns if isinstance(item, dict) and item.get("_detailStatus") == "success"
            ),
            "failedCsns": 0,
            "skippedCsns": 0,
            "queries": 0,
        },
    )
    coverage.setdefault(
        "listInstances",
        {
            "status": "unknown",
            "successfulCsns": sum(
                1 for item in csns if isinstance(item, dict) and item.get("_instancesStatus") == "success"
            ),
            "failedCsns": 0,
            "skippedCsns": 0,
            "queries": 0,
            "instanceCount": sum(
                len(item.get("instances", []))
                for item in csns if isinstance(item, dict) and isinstance(item.get("instances"), list)
            ),
        },
    )
    for index, item in enumerate(csns):
        if not isinstance(item, dict):
            raise ValueError(f"csns[{index}] must be an object")
        if not isinstance(item.setdefault("instances", []), list):
            raise ValueError(f"csns[{index}].instances must be a list")
        item.setdefault("_detailStatus", "unknown")
        item.setdefault("_instancesStatus", "unknown")
    return inventory


def _finding(
    rule_id: str,
    severity: str,
    csn: dict[str, Any] | None,
    fact: str,
    interpretation: str,
    *,
    instance: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    csn = csn or {}
    instance = instance or {}
    return {
        "ruleId": rule_id,
        "severity": severity,
        "csnId": _optional_string(csn.get("csnId")),
        "csnName": _optional_string(csn.get("name")),
        "attachId": _optional_string(instance.get("attachId")),
        "instanceId": _optional_string(instance.get("instanceId")),
        "instanceType": _optional_string(instance.get("instanceType")),
        "instanceRegion": _optional_string(instance.get("instanceRegion")),
        "instanceAccountId": _optional_string(instance.get("instanceAccountId")),
        "fact": fact,
        "interpretation": interpretation,
        "evidence": evidence or {},
    }


def _parse_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    try:
        dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt.datetime.strptime(text, pattern)
            return True
        except ValueError:
            continue
    return False


def _valid_nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _complete_identity(instance: dict[str, Any]) -> tuple[str, str, str, str] | None:
    values = tuple(
        str(instance.get(field) or "").strip()
        for field in ("instanceAccountId", "instanceRegion", "instanceType", "instanceId")
    )
    return values if all(values) else None


def analyze_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    csns = [item for item in inventory.get("csns", []) if isinstance(item, dict)]
    status_distribution: Counter[str] = Counter()
    instance_status_distribution: Counter[str] = Counter()
    type_distribution: Counter[str] = Counter()
    region_distribution: Counter[str] = Counter()
    account_distribution: Counter[str] = Counter()
    total_instances = 0
    detail_success = 0
    instances_success = 0
    cross_csn: defaultdict[tuple[str, str, str, str], list[tuple[str, dict[str, Any], dict[str, Any]]]] = defaultdict(list)

    for error in inventory.get("errors", []):
        if not isinstance(error, dict):
            continue
        status_code = error.get("status")
        rule_id = "COV-002" if status_code in (401, 403) else "COV-004" if status_code == 404 else "COV-001"
        severity = "info" if rule_id == "COV-004" else "high"
        scope = _optional_string(error.get("scope"))
        record = next((item for item in csns if _optional_string(item.get("csnId")) == scope), None)
        findings.append(
            _finding(
                rule_id,
                severity,
                record or ({"csnId": scope} if scope else None),
                f"{error.get('operation', 'query')} 查询失败，状态为 {status_code or 'network-error'}",
                "该范围的 CSN 详情或网络实例拓扑覆盖不完整",
                evidence={
                    key: error.get(key)
                    for key in ("operation", "status", "code", "requestId", "path", "scope")
                    if error.get(key) is not None
                },
            )
        )

    for unmatched in inventory.get("selection", {}).get("unmatchedCsnIds", []):
        findings.append(
            _finding(
                "COV-001", "high", {"csnId": unmatched},
                "指定的 CSN ID 未在成功取得的列表中匹配",
                "该指定范围未被审计；核对 ID 和当前账号可见性",
                evidence={"requestedCsnId": unmatched},
            )
        )

    csn_id_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for csn in csns:
        csn_id = str(csn.get("csnId") or "")
        if csn_id:
            csn_id_groups[csn_id].append(csn)
    for csn_id, duplicates in csn_id_groups.items():
        if len(duplicates) > 1:
            findings.append(
                _finding(
                    "CSN-006", "high", duplicates[0],
                    "CSN 列表重复返回相同的非空 csnId",
                    "列表或分页身份数据重复，需要核对接口结果",
                    evidence={"csnId": csn_id, "occurrences": len(duplicates)},
                )
            )

    for csn in csns:
        csn_status = str(csn.get("status") or "").strip().lower()
        status_distribution[csn_status or "missing"] += 1
        if csn.get("_detailStatus") == "success":
            detail_success += 1
            if "fail" in csn_status or "error" in csn_status:
                findings.append(
                    _finding("CSN-001", "high", csn, f"CSN 状态为 {csn_status}", "控制面返回失败类状态，需要人工排查", evidence={"status": csn_status})
                )
            elif csn_status and csn_status != "active":
                findings.append(
                    _finding("CSN-001", "info", csn, f"CSN 状态为 {csn_status}", "该状态不在当前文档示例中，保留并人工解释", evidence={"status": csn_status})
                )

            for field in ("instanceNum", "csnBpNum"):
                if field in csn and not _valid_nonnegative_integer(csn.get(field)):
                    findings.append(
                        _finding("CSN-002", "high", csn, f"{field} 不是非负整数", "详情元数据与文档模型不一致", evidence={field: csn.get(field)})
                    )

            snapshot = csn.get("_listSnapshot")
            if isinstance(snapshot, dict):
                listed_id = _optional_string(snapshot.get("csnId"))
                detail_id = _optional_string(csn.get("csnId"))
                if listed_id and detail_id and listed_id != detail_id:
                    findings.append(
                        _finding("CSN-004", "high", csn, "列表和详情返回的 csnId 不一致", "对象身份证据冲突，需要核对查询结果", evidence={"listCsnId": listed_id, "detailCsnId": detail_id})
                    )
                listed_name = _optional_string(snapshot.get("name"))
                detail_name = _optional_string(csn.get("name"))
                if listed_name is not None and detail_name is not None and listed_name != detail_name:
                    findings.append(
                        _finding("CSN-004", "medium", csn, "列表和详情返回的 CSN 名称不一致", "可能是两次查询之间发生变更，需要人工核对", evidence={"listName": listed_name, "detailName": detail_name})
                    )
            created_time = csn.get("createdTime", csn.get("createTime"))
            if created_time not in (None, "") and not _parse_timestamp(created_time):
                findings.append(
                    _finding("CSN-007", "info", csn, "CSN 创建时间无法按常见格式解析", "保留原始时间证据并人工解释", evidence={"createdTime": created_time})
                )

        instances = csn.get("instances", []) if isinstance(csn.get("instances"), list) else []
        if csn.get("_instancesStatus") != "success":
            continue
        instances_success += 1
        total_instances += len(instances)
        if csn.get("_detailStatus") == "success" and _valid_nonnegative_integer(csn.get("instanceNum")):
            if csn.get("instanceNum") != len(instances):
                findings.append(
                    _finding("CSN-003", "info", csn, "详情 instanceNum 与成功查询到的网络实例数量不一致", "两次查询之间可能有变更，或计数字段尚未同步", evidence={"instanceNum": csn.get("instanceNum"), "queriedInstanceCount": len(instances)})
                )
        if csn.get("_detailStatus") == "success" and csn_status == "active" and not instances:
            findings.append(
                _finding("CSN-005", "low", csn, "active CSN 成功查询到零个网络实例", "可能是空置或预配置 CSN，需要确认归属和用途", evidence={"status": csn_status, "queriedInstanceCount": 0})
            )

        attach_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        identity_groups: defaultdict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        regions: set[str] = set()
        accounts: set[str] = set()
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            attach_id = str(instance.get("attachId") or "").strip()
            instance_id = str(instance.get("instanceId") or "").strip()
            instance_region = str(instance.get("instanceRegion") or "").strip()
            account_id = str(instance.get("instanceAccountId") or "").strip()
            instance_type = str(instance.get("instanceType") or "").strip().lower()
            status_value = str(instance.get("status") or "").strip().lower()
            instance_status_distribution[status_value or "missing"] += 1
            type_distribution[instance_type or "missing"] += 1
            region_distribution[instance_region or "missing"] += 1
            account_distribution[account_id or "missing"] += 1
            if instance_region:
                regions.add(instance_region)
            if account_id:
                accounts.add(account_id)
            missing = [field for field, value in (("attachId", attach_id), ("instanceId", instance_id), ("instanceRegion", instance_region)) if not value]
            if missing:
                findings.append(
                    _finding("CSN-101", "high", csn, f"网络实例缺少 {', '.join(missing)}", "拓扑边无法被唯一识别", instance=instance, evidence={"missingFields": missing})
                )
            if status_value == "attach_failed":
                findings.append(
                    _finding("CSN-102", "high", csn, "网络实例状态为 attach_failed", "CSN 控制面报告加载失败，需要人工排查", instance=instance, evidence={"status": status_value})
                )
            elif status_value in TRANSITIONAL_INSTANCE_STATUSES:
                findings.append(
                    _finding("CSN-103", "info", csn, f"网络实例处于过渡状态 {status_value}", "缺少状态持续时间，不能判定操作卡住", instance=instance, evidence={"status": status_value})
                )
            elif status_value not in KNOWN_INSTANCE_STATUSES:
                findings.append(
                    _finding("CSN-104", "info", csn, f"网络实例状态为 {status_value or 'missing'}", "状态缺失或不在当前官方枚举中，需要人工解释", instance=instance, evidence={"status": status_value or None})
                )
            if instance_type not in KNOWN_INSTANCE_TYPES:
                findings.append(
                    _finding("CSN-105", "info", csn, f"网络实例类型为 {instance_type or 'missing'}", "可能是产品演进产生的新类型，保留原始值", instance=instance, evidence={"instanceType": instance_type or None})
                )
            if not account_id or not str(instance.get("instanceName") or "").strip():
                absent = [name for name, value in (("instanceAccountId", account_id), ("instanceName", str(instance.get("instanceName") or "").strip())) if not value]
                findings.append(
                    _finding("CSN-109", "info", csn, f"网络实例缺少 {', '.join(absent)}", "归属或命名元数据不完整，但不单独证明故障", instance=instance, evidence={"missingFields": absent})
                )
            if attach_id:
                attach_groups[attach_id].append(instance)
            identity = _complete_identity(instance)
            if identity:
                identity_groups[identity].append(instance)
                cross_csn[identity].append((str(csn.get("csnId") or ""), csn, instance))

        for attach_id, group in attach_groups.items():
            if len(group) > 1:
                findings.append(
                    _finding("CSN-106", "medium", csn, "同一 CSN 重复返回相同 attachId", "挂载身份重复，需要核对列表数据", instance=group[0], evidence={"attachId": attach_id, "occurrences": len(group)})
                )
        for identity, group in identity_groups.items():
            attach_ids = sorted({str(item.get("attachId") or "") for item in group if item.get("attachId")})
            if len(attach_ids) > 1:
                findings.append(
                    _finding("CSN-107", "medium", csn, "同一网络资源在一个 CSN 中对应多个 attachId", "资源可能重复加载，需要人工核对", instance=group[0], evidence={"identity": list(identity), "attachIds": attach_ids})
                )
        if len(regions) > 1 or len(accounts) > 1:
            parts = []
            if len(regions) > 1:
                parts.append("多个地域")
            if len(accounts) > 1:
                parts.append("多个账号")
            findings.append(
                _finding("CSN-110", "info", csn, f"该 CSN 覆盖{'和'.join(parts)}", "记录跨地域或跨账号治理范围；这本身不是故障", evidence={"regions": sorted(regions), "accountIds": sorted(accounts)})
            )

    for identity, records in cross_csn.items():
        csn_ids = sorted({record[0] for record in records if record[0]})
        if len(csn_ids) > 1:
            findings.append(
                _finding("CSN-108", "high", records[0][1], "同一完整网络实例身份出现在多个 CSN", "产品约束要求一个网络实例只能加载到一个 CSN，需要核对配置", instance=records[0][2], evidence={"identity": list(identity), "csnIds": csn_ids})
            )

    findings.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity")), 9),
            str(item.get("ruleId") or ""),
            str(item.get("csnId") or ""),
            str(item.get("attachId") or ""),
        )
    )
    unique_identities = len(cross_csn)
    analysis = {
        "summary": {
            "csnCount": len(csns),
            "detailSuccessCount": detail_success,
            "instanceListSuccessCsnCount": instances_success,
            "networkInstanceCount": total_instances,
            "uniqueCompleteNetworkIdentityCount": unique_identities,
            "findingCount": len(findings),
            "severityCounts": dict(Counter(item["severity"] for item in findings)),
        },
        "distributions": {
            "csnStatus": dict(sorted(status_distribution.items())),
            "instanceStatus": dict(sorted(instance_status_distribution.items())),
            "instanceType": dict(sorted(type_distribution.items())),
            "instanceRegion": dict(sorted(region_distribution.items())),
            "instanceAccountId": dict(sorted(account_distribution.items())),
        },
        "findings": findings,
    }
    inventory["analysis"] = analysis
    return analysis


def _display(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_report(inventory: dict[str, Any], analysis: dict[str, Any]) -> str:
    summary = analysis["summary"]
    coverage = inventory.get("coverage", {})
    lines = [
        "# 百度智能云 CSN 拓扑与状态巡检报告",
        "",
        f"- 生成时间（UTC）：{_display(inventory.get('generatedAt'))}",
        f"- 模式：{_display(inventory.get('mode'))}",
        f"- CSN 数量：{summary['csnCount']}",
        f"- 成功取得详情：{summary['detailSuccessCount']}",
        f"- 成功取得网络实例列表的 CSN：{summary['instanceListSuccessCsnCount']}",
        f"- 网络实例记录数：{summary['networkInstanceCount']}",
        f"- 完整且唯一的网络实例身份数：{summary['uniqueCompleteNetworkIdentityCount']}",
        f"- 发现数：{summary['findingCount']}",
        "",
        "## 查询覆盖率",
        "",
        "| 范围 | 状态 | 成功 | 失败/跳过 | 请求数 | 记录数 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    list_cov = coverage.get("listCsns", {})
    detail_cov = coverage.get("detailCsns", {})
    instance_cov = coverage.get("listInstances", {})
    lines.extend([
        f"| CSN 列表 | {_display(list_cov.get('status'))} | - | {_display(list_cov.get('failedQueries', 0))} | {_display(list_cov.get('queries', 0))} | {_display(list_cov.get('count', 0))} |",
        f"| CSN 详情 | {_display(detail_cov.get('status'))} | {_display(detail_cov.get('successfulCsns', 0))} | {_display(detail_cov.get('failedCsns', 0) + detail_cov.get('skippedCsns', 0))} | {_display(detail_cov.get('queries', 0))} | - |",
        f"| 网络实例列表 | {_display(instance_cov.get('status'))} | {_display(instance_cov.get('successfulCsns', 0))} | {_display(instance_cov.get('failedCsns', 0) + instance_cov.get('skippedCsns', 0))} | {_display(instance_cov.get('queries', 0))} | {_display(instance_cov.get('instanceCount', 0))} |",
        "",
        "## CSN—网络实例拓扑",
        "",
        "| CSN | CSN 状态 | 挂载 ID | 类型 | 地域 | 网络实例 | 名称 | 挂载状态 | 账号 ID |",
        "|---|---|---|---|---|---|---|---|---|",
    ])
    for csn in inventory.get("csns", []):
        if not isinstance(csn, dict):
            continue
        csn_label = f"{_display(csn.get('name'))} ({_display(csn.get('csnId'))})"
        instances = csn.get("instances", []) if isinstance(csn.get("instances"), list) else []
        if not instances:
            lines.append(f"| {csn_label} | {_display(csn.get('status'))} | - | - | - | - | - | {_display(csn.get('_instancesStatus'))} | - |")
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            lines.append(
                f"| {csn_label} | {_display(csn.get('status'))} | {_display(instance.get('attachId'))} | {_display(instance.get('instanceType'))} | {_display(instance.get('instanceRegion'))} | {_display(instance.get('instanceId'))} | {_display(instance.get('instanceName'))} | {_display(instance.get('status'))} | {_display(instance.get('instanceAccountId'))} |"
            )
    lines.extend(["", "## 分布", ""])
    for title, key in (("CSN 状态", "csnStatus"), ("网络实例状态", "instanceStatus"), ("网络实例类型", "instanceType"), ("地域", "instanceRegion"), ("账号", "instanceAccountId")):
        values = analysis["distributions"].get(key, {})
        lines.append(f"- {title}：" + ("，".join(f"{_display(name)}={count}" for name, count in values.items()) or "无"))
    lines.extend(["", "## 发现", ""])
    if not analysis["findings"]:
        lines.append("在成功查询且规则覆盖的配置范围内未发现命中。此结论不代表数据面互通或不存在其他风险。")
    else:
        for finding in analysis["findings"]:
            location = "/".join(filter(None, (_optional_string(finding.get("csnId")), _optional_string(finding.get("attachId")), _optional_string(finding.get("instanceId"))))) or "全局"
            lines.extend([
                f"### [{finding['severity'].upper()}] {finding['ruleId']} · {location}",
                "",
                f"- 事实：{finding['fact']}",
                f"- 解释：{finding['interpretation']}",
                f"- 证据：`{json.dumps(finding.get('evidence', {}), ensure_ascii=False, sort_keys=True)}`",
                "",
            ])
    lines.extend([
        "## 限制",
        "",
        "- 本报告仅使用 CSN 列表、详情和网络实例列表 GET 响应，不检查路由表、关联、学习关系、带宽包、地域带宽、VPC 路由或安全策略。",
        "- `active` 或 `attached` 仅代表控制面状态，不能证明端到端流量可达。",
        "- `attaching`、`detaching` 缺少持续时间证据，不能据此判定卡住。",
        "- 查询失败的范围保持未知，不能按零资源解释。",
        "",
    ])
    return "\n".join(lines)


def _validate_output_dir(path: Path) -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    resolved = path.expanduser().resolve()
    if _is_within(resolved, skill_root):
        raise ValueError("Output directory must be outside the Skill directory")
    return resolved


def _atomic_write(path: Path, data: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path.exists():
            temporary_path.unlink()


def write_outputs(output_dir: Path, inventory: dict[str, Any], report: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(output_dir, 0o700)
    except OSError:
        pass
    _atomic_write(output_dir / "inventory.json", json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(output_dir / "report.md", report)


def self_test() -> None:
    assert canonical_query({"maxKeys": 1000, "marker": "a b"}) == "marker=a%20b&maxKeys=1000"
    headers = bce_headers("ak", "sk", "/v1/csn", {"maxKeys": 1000}, timestamp="2026-01-01T00:00:00Z")
    assert headers["Authorization"].startswith("bce-auth-v1/ak/")
    client = ReadOnlyBceClient("ak", "sk", max_retries=0)
    try:
        client.request_json("/v1/csn", method="POST")
        raise AssertionError("non-GET request was not rejected")
    except ValueError as exc:
        assert "non-GET" in str(exc)
    sample = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "mode": "offline",
        "selection": {"requestedCsnIds": [], "unmatchedCsnIds": []},
        "coverage": {},
        "errors": [],
        "csns": [{
            "csnId": "csn-a", "name": "demo", "status": "active", "instanceNum": 1,
            "csnBpNum": 0, "_detailStatus": "success", "_instancesStatus": "success",
            "instances": [{"attachId": "attach-a", "instanceId": "vpc-a", "instanceRegion": "bj", "instanceType": "vpc", "instanceAccountId": "account-a", "instanceName": "vpc-a", "status": "attach_failed"}],
        }],
    }
    rules = {item["ruleId"] for item in analyze_inventory(sample)["findings"]}
    assert "CSN-102" in rules
    assert "CSN-101" not in rules
    print("self-test: ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Baidu AI Cloud CSN topology/status audit")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--input", type=Path, help="Offline inventory JSON")
    mode.add_argument("--self-test", action="store_true", help="Run local tests without cloud access")
    parser.add_argument("--credentials-file", type=Path, help="Owner-only JSON credential file outside the Skill")
    parser.add_argument("--csn-ids", help="Comma-separated exact CSN IDs; live mode only")
    parser.add_argument("--output-dir", type=Path, help="Output directory outside the Skill")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=3, help="Retries for GET 429/5xx/network errors")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        if not args.output_dir:
            parser.error("--output-dir is required except with --self-test")
        if args.input and (args.credentials_file or args.csn_ids):
            parser.error("--credentials-file and --csn-ids are live-mode options")
        if args.timeout <= 0 or args.max_retries < 0 or args.max_retries > 10:
            parser.error("--timeout must be positive and --max-retries must be between 0 and 10")
        output_dir = _validate_output_dir(args.output_dir)
        inventory = load_inventory(args.input) if args.input else collect_live(args)
        analysis = analyze_inventory(inventory)
        write_outputs(output_dir, inventory, render_report(inventory, analysis))
        summary = analysis["summary"]
        print(
            "audit complete: "
            f"csns={summary['csnCount']} "
            f"instances={summary['networkInstanceCount']} "
            f"unique_instances={summary['uniqueCompleteNetworkIdentityCount']} "
            f"findings={summary['findingCount']}"
        )
        return 0
    except (OSError, ValueError, ApiFailure, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

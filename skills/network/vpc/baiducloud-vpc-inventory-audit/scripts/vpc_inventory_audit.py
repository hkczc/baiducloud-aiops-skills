#!/usr/bin/env python3
"""Read-only Baidu AI Cloud VPC inventory collector and topology auditor.

The network client in this file rejects every HTTP method except GET before
performing network I/O. Credentials are read from environment variables or an
explicitly selected, owner-only local JSON file outside the Skill package.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA_VERSION = "1.0"
RESOURCE_KEYS = (
    "vpcs",
    "subnets",
    "routeTables",
    "securityGroups",
    "enterpriseSecurityGroups",
    "acls",
    "enis",
)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ApiFailure(RuntimeError):
    """A sanitized API failure that never contains authorization material."""

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

    def to_dict(self, resource_type: str, scope: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "resourceType": resource_type,
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
    pairs = []
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

    method = "GET"
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
        (method, canonical_uri, canonical_query(params), canonical_headers)
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
        "User-Agent": "baiducloud-vpc-inventory-audit/1.0",
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
        endpoint = endpoint.rstrip("/")
        if not endpoint.startswith("https://"):
            raise ValueError("Endpoint must use HTTPS")
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        if not parsed.hostname or parsed.path not in ("", "/"):
            raise ValueError("Endpoint must be an HTTPS origin without a path")
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
                    detail.get("message") or f"HTTP {exc.code}",
                    code=detail.get("code"),
                    request_id=exc.headers.get("x-bce-request-id") or detail.get("requestId"),
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
            truncated = bool(response.get("isTruncated"))
            next_marker = response.get("nextMarker")
            if not truncated:
                break
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


def _resource_id(record: dict[str, Any], *fields: str) -> str | None:
    for field in fields:
        value = record.get(field)
        if value not in (None, ""):
            return str(value)
    return None


def _list_field(record: dict[str, Any], *fields: str) -> list[str]:
    for field in fields:
        value = record.get(field)
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, dict):
                    item_id = _resource_id(
                        item,
                        "securityGroupId",
                        "enterpriseSecurityGroupId",
                        "id",
                    )
                    if item_id:
                        result.append(item_id)
                elif item not in (None, ""):
                    result.append(str(item))
            return result
    return []


def _tags(record: dict[str, Any]) -> list[Any]:
    value = record.get("tags")
    return value if isinstance(value, list) else []


def _new_region(endpoint: str) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "resources": {key: [] for key in RESOURCE_KEYS},
        "coverage": {
            key: {"status": "notAttempted", "count": 0, "queries": 0, "failedQueries": 0}
            for key in RESOURCE_KEYS
        },
        "errors": [],
    }


def _record_query(
    region_data: dict[str, Any],
    resource_type: str,
    scope: str,
    query: Callable[[], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    coverage = region_data["coverage"][resource_type]
    coverage["queries"] += 1
    try:
        records = query()
        region_data["resources"][resource_type].extend(records)
        coverage["count"] = len(region_data["resources"][resource_type])
        coverage["status"] = "success" if coverage["failedQueries"] == 0 else "partial"
        return records
    except ApiFailure as exc:
        coverage["failedQueries"] += 1
        coverage["status"] = "failed" if coverage["count"] == 0 else "partial"
        region_data["errors"].append(exc.to_dict(resource_type, scope))
        return []


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

    vpcs = _record_query(
        region_data,
        "vpcs",
        region,
        lambda: client.paginate("/v1/vpc", ("vpcs",)),
    )
    subnets = _record_query(
        region_data,
        "subnets",
        region,
        lambda: client.paginate("/v1/subnet", ("subnets",)),
    )
    _record_query(
        region_data,
        "enterpriseSecurityGroups",
        region,
        lambda: client.paginate(
            "/v1/enterprise/security", ("enterpriseSecurityGroups", "securityGroups")
        ),
    )

    for vpc in vpcs:
        vpc_id = _resource_id(vpc, "vpcId", "id")
        if not vpc_id:
            continue

        def route_query(vpc_id: str = vpc_id) -> list[dict[str, Any]]:
            response = client.request_json("/v1/route", {"vpcId": vpc_id})
            tables = _first_list(response, ("routeTables",))
            if tables:
                for table in tables:
                    if isinstance(table, dict):
                        table.setdefault("vpcId", vpc_id)
                return [item for item in tables if isinstance(item, dict)]
            if response:
                response.setdefault("vpcId", vpc_id)
                return [response]
            return []

        _record_query(region_data, "routeTables", vpc_id, route_query)
        _record_query(
            region_data,
            "securityGroups",
            vpc_id,
            lambda vpc_id=vpc_id: client.paginate(
                "/v2/securityGroup", ("securityGroups",), {"vpcId": vpc_id}
            ),
        )

        def acl_summary(vpc_id: str = vpc_id) -> list[dict[str, Any]]:
            response = client.request_json("/v1/acl", {"vpcId": vpc_id})
            records = _first_list(response, ("acls", "aclEntrys", "aclEntries", "aclRules", "rules"))
            if records:
                normalized = []
                for record in records:
                    if isinstance(record, dict):
                        record.setdefault("vpcId", vpc_id)
                        record.setdefault("recordType", "vpcAcl")
                        normalized.append(record)
                return normalized
            if response:
                response.setdefault("vpcId", vpc_id)
                response.setdefault("recordType", "vpcAclSummary")
                return [response]
            return []

        _record_query(region_data, "acls", vpc_id, acl_summary)
        _record_query(
            region_data,
            "enis",
            vpc_id,
            lambda vpc_id=vpc_id: client.paginate(
                "/v1/eni", ("enis",), {"vpcId": vpc_id}
            ),
        )

    for subnet in subnets:
        subnet_id = _resource_id(subnet, "subnetId", "id")
        if not subnet_id:
            continue

        def acl_rules(subnet_id: str = subnet_id) -> list[dict[str, Any]]:
            records = client.paginate(
                "/v1/acl/rule",
                ("aclRules", "rules", "aclEntrys", "aclEntries"),
                {"subnetId": subnet_id},
            )
            for record in records:
                record.setdefault("subnetId", subnet_id)
                record.setdefault("recordType", "subnetAclRule")
            return records

        _record_query(region_data, "acls", subnet_id, acl_rules)

    for resource_type in RESOURCE_KEYS:
        coverage = region_data["coverage"][resource_type]
        if coverage["queries"] == 0:
            if resource_type in ("routeTables", "securityGroups", "acls", "enis") and not vpcs:
                coverage["status"] = "blocked"
                coverage["reason"] = "No successfully collected VPC ID was available"
            else:
                coverage["status"] = "success"
        coverage["count"] = len(region_data["resources"][resource_type])

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
    regions = _parse_regions(args.regions)
    endpoints = _parse_endpoints(args.endpoint or [])
    inventory = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "mode": "live",
        "regions": {},
    }
    for region in regions:
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


def _parse_regions(value: str | None) -> list[str]:
    if not value:
        raise ValueError("--regions is required in live mode")
    regions = []
    for item in value.split(","):
        region = item.strip().lower()
        if not region:
            continue
        if not all(ch.isalnum() or ch == "-" for ch in region):
            raise ValueError(f"Invalid region code: {region}")
        if region not in regions:
            regions.append(region)
    if not regions:
        raise ValueError("At least one region is required")
    return regions


def _parse_endpoints(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--endpoint must use REGION=https://host")
        region, endpoint = value.split("=", 1)
        region = region.strip().lower()
        endpoint = endpoint.strip().rstrip("/")
        if not endpoint.startswith("https://"):
            raise ValueError("Endpoint overrides must use HTTPS")
        from urllib.parse import urlparse

        hostname = urlparse(endpoint).hostname or ""
        if not hostname.endswith(".baidubce.com"):
            raise ValueError("Endpoint overrides must use an official *.baidubce.com host")
        result[region] = endpoint
    return result


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
        coverage = data.setdefault("coverage", {})
        data.setdefault("errors", [])
        data.setdefault("endpoint", "offline")
        for key in RESOURCE_KEYS:
            resources.setdefault(key, [])
            coverage.setdefault(
                key,
                {"status": "unknown", "count": len(resources[key]) if isinstance(resources[key], list) else 0},
            )
    return inventory


def _coverage_success(region_data: dict[str, Any], resource_type: str) -> bool:
    status = region_data.get("coverage", {}).get(resource_type, {}).get("status")
    return status == "success"


def _finding(
    rule_id: str,
    severity: str,
    region: str,
    resource_type: str,
    resource_id: str | None,
    fact: str,
    interpretation: str,
    *,
    vpc_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ruleId": rule_id,
        "severity": severity,
        "region": region,
        "vpcId": vpc_id,
        "resourceType": resource_type,
        "resourceId": resource_id,
        "fact": fact,
        "interpretation": interpretation,
        "evidence": evidence or {},
    }


def analyze_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    totals = {key: 0 for key in RESOURCE_KEYS}

    for region, region_data in inventory.get("regions", {}).items():
        resources = region_data.get("resources", {})
        for key in RESOURCE_KEYS:
            records = resources.get(key, [])
            if isinstance(records, list):
                totals[key] += len(records)

        for error in region_data.get("errors", []):
            resource_type = str(error.get("resourceType", "unknown"))
            status = error.get("status")
            rule_id = "COV-002" if status in (401, 403) else "COV-004" if status == 404 else "COV-001"
            severity = "high" if rule_id in ("COV-001", "COV-002") else "info"
            findings.append(
                _finding(
                    rule_id,
                    severity,
                    region,
                    resource_type,
                    error.get("scope"),
                    f"采集失败，状态为 {status or 'network-error'}",
                    "该资源类型的清单覆盖不完整",
                    evidence={
                        key: error.get(key)
                        for key in ("status", "code", "requestId", "path", "scope")
                        if error.get(key) is not None
                    },
                )
            )

        vpcs = resources.get("vpcs", [])
        subnets = resources.get("subnets", [])
        routes = resources.get("routeTables", [])
        security_groups = resources.get("securityGroups", [])
        esgs = resources.get("enterpriseSecurityGroups", [])
        acls = resources.get("acls", [])
        enis = resources.get("enis", [])

        vpc_ids = {_resource_id(item, "vpcId", "id") for item in vpcs}
        vpc_ids.discard(None)
        subnet_ids = {_resource_id(item, "subnetId", "id") for item in subnets}
        subnet_ids.discard(None)
        sg_ids = {_resource_id(item, "securityGroupId", "id") for item in security_groups}
        sg_ids.discard(None)
        esg_ids = {_resource_id(item, "enterpriseSecurityGroupId", "id") for item in esgs}
        esg_ids.discard(None)

        if _coverage_success(region_data, "vpcs"):
            for subnet in subnets:
                subnet_id = _resource_id(subnet, "subnetId", "id")
                vpc_id = _resource_id(subnet, "vpcId")
                if vpc_id and vpc_id not in vpc_ids:
                    findings.append(
                        _finding(
                            "REL-001",
                            "medium",
                            region,
                            "subnet",
                            subnet_id,
                            f"子网引用了 VPC {vpc_id}，但成功返回的 VPC 列表中不存在该 ID",
                            "该引用关系不一致，需要人工确认",
                            vpc_id=vpc_id,
                            evidence={"referencedVpcId": vpc_id},
                        )
                    )

        if _coverage_success(region_data, "subnets"):
            for eni in enis:
                eni_id = _resource_id(eni, "eniId", "id")
                vpc_id = _resource_id(eni, "vpcId")
                subnet_id = _resource_id(eni, "subnetId")
                missing = []
                if subnet_id and subnet_id not in subnet_ids:
                    missing.append(f"subnet {subnet_id}")
                if _coverage_success(region_data, "vpcs") and vpc_id and vpc_id not in vpc_ids:
                    missing.append(f"VPC {vpc_id}")
                if missing:
                    findings.append(
                        _finding(
                            "REL-002",
                            "medium",
                            region,
                            "eni",
                            eni_id,
                            f"弹性网卡引用了未返回的 {'、'.join(missing)}",
                            "已采集清单中的弹性网卡关联关系不一致",
                            vpc_id=vpc_id,
                            evidence={"vpcId": vpc_id, "subnetId": subnet_id},
                        )
                    )

        for eni in enis:
            eni_id = _resource_id(eni, "eniId", "id")
            vpc_id = _resource_id(eni, "vpcId")
            missing_groups = []
            if _coverage_success(region_data, "securityGroups"):
                missing_groups.extend(
                    group_id
                    for group_id in _list_field(eni, "securityGroupIds", "securityGroups")
                    if group_id not in sg_ids
                )
            if _coverage_success(region_data, "enterpriseSecurityGroups"):
                missing_groups.extend(
                    group_id
                    for group_id in _list_field(
                        eni, "enterpriseSecurityGroupIds", "enterpriseSecurityGroups"
                    )
                    if group_id not in esg_ids
                )
            if missing_groups:
                findings.append(
                    _finding(
                        "REL-003",
                        "medium",
                        region,
                        "eni",
                        eni_id,
                        f"弹性网卡引用了成功返回列表中不存在的安全组：{', '.join(sorted(set(missing_groups)))}",
                        "确认安全组是否超出查询范围，或弹性网卡引用是否已失效",
                        vpc_id=vpc_id,
                        evidence={"missingSecurityGroupIds": sorted(set(missing_groups))},
                    )
                )

        if _coverage_success(region_data, "vpcs"):
            for route in routes:
                route_id = _resource_id(route, "routeTableId", "id")
                vpc_id = _resource_id(route, "vpcId")
                if not vpc_id:
                    findings.append(
                        _finding(
                            "REL-006",
                            "info",
                            region,
                            "routeTable",
                            route_id,
                            "路由表响应未包含 VPC 关联字段",
                            "使用路由表详情查询人工确认关联关系",
                            evidence={"routeTableId": route_id},
                        )
                    )
                elif vpc_id not in vpc_ids:
                    findings.append(
                        _finding(
                            "REL-004",
                            "medium",
                            region,
                            "routeTable",
                            route_id,
                            f"路由表引用了 VPC {vpc_id}，但成功返回的 VPC 列表中不存在该 ID",
                            "路由表关联关系不一致",
                            vpc_id=vpc_id,
                            evidence={"referencedVpcId": vpc_id},
                        )
                    )

        if _coverage_success(region_data, "subnets"):
            for acl in acls:
                subnet_id = _resource_id(acl, "subnetId")
                if subnet_id and subnet_id not in subnet_ids:
                    acl_id = _resource_id(acl, "aclId", "aclRuleId", "id")
                    findings.append(
                        _finding(
                            "REL-005",
                            "medium",
                            region,
                            "acl",
                            acl_id,
                            f"ACL 记录引用了子网 {subnet_id}，但成功返回的子网列表中不存在该 ID",
                            "ACL 关联关系不一致",
                            evidence={"referencedSubnetId": subnet_id},
                        )
                    )

        for subnet in subnets:
            subnet_id = _resource_id(subnet, "subnetId", "id")
            vpc_id = _resource_id(subnet, "vpcId")
            available = subnet.get("availableUnreservedIp")
            if not isinstance(available, int):
                available = subnet.get("availableIp")
            cidr = subnet.get("cidr")
            approximate_ratio: float | None = None
            if isinstance(available, int) and isinstance(cidr, str):
                try:
                    total = ipaddress.ip_network(cidr, strict=False).num_addresses
                    approximate_ratio = available / total if total else None
                except ValueError:
                    approximate_ratio = None
            if isinstance(available, int) and available <= 16:
                findings.append(
                    _finding(
                        "CAP-001",
                        "medium",
                        region,
                        "subnet",
                        subnet_id,
                        f"子网仅剩 {available} 个可用且未预留的 IP 地址",
                        "地址容量接近耗尽",
                        vpc_id=vpc_id,
                        evidence={"availableIp": available, "cidr": cidr},
                    )
                )
            elif approximate_ratio is not None and approximate_ratio <= 0.10:
                findings.append(
                    _finding(
                        "CAP-002",
                        "medium",
                        region,
                        "subnet",
                        subnet_id,
                        f"可用 IP 数约为 CIDR 地址总数的 {approximate_ratio:.1%}",
                        "地址容量可能接近耗尽；因云平台保留地址存在，该比例仅为近似值",
                        vpc_id=vpc_id,
                        evidence={"availableIp": available, "cidr": cidr},
                    )
                )

        typed_records = (
            [("vpc", item, _resource_id(item, "vpcId", "id")) for item in vpcs]
            + [("subnet", item, _resource_id(item, "subnetId", "id")) for item in subnets]
            + [("securityGroup", item, _resource_id(item, "securityGroupId", "id")) for item in security_groups]
            + [("eni", item, _resource_id(item, "eniId", "id")) for item in enis]
        )
        for resource_type, record, resource_id in typed_records:
            vpc_id = _resource_id(record, "vpcId")
            if not record.get("name") and not record.get("isDefault"):
                findings.append(
                    _finding(
                        "HYG-001",
                        "low",
                        region,
                        resource_type,
                        resource_id,
                        "资源未返回名称",
                        "资源命名治理不完整",
                        vpc_id=vpc_id,
                    )
                )
            if not _tags(record):
                findings.append(
                    _finding(
                        "HYG-002",
                        "low",
                        region,
                        resource_type,
                        resource_id,
                        "资源未返回标签",
                        "资源标签治理不完整；这不代表网络故障",
                        vpc_id=vpc_id,
                    )
                )

        if _coverage_success(region_data, "subnets"):
            subnet_vpcs = {_resource_id(item, "vpcId") for item in subnets}
            for vpc in vpcs:
                vpc_id = _resource_id(vpc, "vpcId", "id")
                if vpc_id and vpc_id not in subnet_vpcs:
                    findings.append(
                        _finding(
                            "HYG-003",
                            "info",
                            region,
                            "vpc",
                            vpc_id,
                            "该 VPC 未返回任何子网",
                            "VPC 可能是有意留空，需要确认业务归属",
                            vpc_id=vpc_id,
                        )
                    )

        for eni in enis:
            eni_id = _resource_id(eni, "eniId", "id")
            vpc_id = _resource_id(eni, "vpcId")
            status = str(eni.get("status") or "unknown")
            instance_id = _resource_id(eni, "instanceId")
            if not instance_id or status.lower() not in {"inuse", "in-use", "available"}:
                findings.append(
                    _finding(
                        "HYG-004",
                        "info",
                        region,
                        "eni",
                        eni_id,
                        f"弹性网卡挂载关系或状态需要确认：instanceId={instance_id or 'none'}，status={status}",
                        "不得据此推断弹性网卡已废弃或可以删除",
                        vpc_id=vpc_id,
                        evidence={"instanceId": instance_id, "status": status},
                    )
                )

    findings.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item["severity"], 9),
            item["region"],
            item["ruleId"],
            str(item.get("resourceId") or ""),
        )
    )
    return {
        "generatedAt": utc_now(),
        "sourceGeneratedAt": inventory.get("generatedAt"),
        "totals": totals,
        "findingCounts": {
            severity: sum(1 for item in findings if item["severity"] == severity)
            for severity in ("high", "medium", "low", "info")
        },
        "findings": findings,
    }


def _md(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(inventory: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = [
        "# 百度智能云 VPC 资产与拓扑巡检报告",
        "",
        f"- 快照时间：{_md(inventory.get('generatedAt'))}",
        f"- 报告时间：{_md(analysis.get('generatedAt'))}",
        f"- 模式：{_md(inventory.get('mode'))}",
        f"- 地域：{', '.join(sorted(inventory.get('regions', {})))}",
        "- 安全边界：仅执行 GET 查询；未执行任何云资源变更。",
        "",
        "## 采集覆盖率",
        "",
        "| 地域 | 资源类型 | 状态 | 数量 | 查询数 | 失败查询数 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for region, region_data in sorted(inventory.get("regions", {}).items()):
        for resource_type in RESOURCE_KEYS:
            coverage = region_data.get("coverage", {}).get(resource_type, {})
            lines.append(
                "| {} | {} | {} | {} | {} | {} |".format(
                    _md(region),
                    _md(resource_type),
                    _md(coverage.get("status", "unknown")),
                    _md(coverage.get("count", 0)),
                    _md(coverage.get("queries", "-")),
                    _md(coverage.get("failedQueries", "-")),
                )
            )

    totals = analysis.get("totals", {})
    lines.extend(
        [
            "",
            "## 资源汇总",
            "",
            "| VPC | 子网 | 路由表 | 普通安全组 | 企业安全组 | ACL记录 | 弹性网卡 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                totals.get("vpcs", 0),
                totals.get("subnets", 0),
                totals.get("routeTables", 0),
                totals.get("securityGroups", 0),
                totals.get("enterpriseSecurityGroups", 0),
                totals.get("acls", 0),
                totals.get("enis", 0),
            ),
            "",
            "## VPC 拓扑摘要",
            "",
            "| 地域 | VPC ID | 名称 | CIDR | 子网 | 路由表 | 普通安全组 | ENI |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for region, region_data in sorted(inventory.get("regions", {}).items()):
        resources = region_data.get("resources", {})
        for vpc in resources.get("vpcs", []):
            vpc_id = _resource_id(vpc, "vpcId", "id")
            count = lambda key: sum(
                1 for item in resources.get(key, []) if _resource_id(item, "vpcId") == vpc_id
            )
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    _md(region),
                    _md(vpc_id),
                    _md(vpc.get("name")),
                    _md(vpc.get("cidr")),
                    count("subnets"),
                    count("routeTables"),
                    count("securityGroups"),
                    count("enis"),
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
            "| 严重度 | 规则 | 地域 | VPC | 资源 | 事实 | 判断 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for finding in analysis.get("findings", []):
        resource = f"{finding.get('resourceType')}:{finding.get('resourceId') or '-'}"
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                _md(finding.get("severity")),
                _md(finding.get("ruleId")),
                _md(finding.get("region")),
                _md(finding.get("vpcId")),
                _md(resource),
                _md(finding.get("fact")),
                _md(finding.get("interpretation")),
            )
        )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 本报告基于成功返回的配置数据，不代表数据面连通性测试。",
            "- 任何 failed、partial、blocked 或 unknown 覆盖状态都会限制结论完整性。",
            "- 报告不建议自动删除、解绑或修改任何资源；整改需由人工另行评审。",
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
    sample = Path(__file__).resolve().parents[1] / "examples" / "sample-inventory.json"
    inventory = load_inventory(sample)
    analysis = analyze_inventory(inventory)
    rule_ids = {item["ruleId"] for item in analysis["findings"]}
    expected = {"CAP-001", "REL-002", "REL-003"}
    missing = expected - rule_ids
    if missing:
        raise AssertionError(f"Sample analysis missed expected rules: {sorted(missing)}")

    client = ReadOnlyBceClient("https://bcc.bj.baidubce.com", "ak", "sk")
    try:
        client.request_json("/v1/vpc", method="POST")
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

    page_calls = []

    def fake_pages(path: str, params: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
        page_calls.append((path, dict(params or {})))
        if params and params.get("marker") == "page-2":
            return {"vpcs": [{"vpcId": "vpc-2"}], "isTruncated": False}
        return {
            "vpcs": [{"vpcId": "vpc-1"}],
            "isTruncated": True,
            "nextMarker": "page-2",
        }

    client.request_json = fake_pages  # type: ignore[method-assign]
    paged = client.paginate("/v1/vpc", ("vpcs",))
    if [item.get("vpcId") for item in paged] != ["vpc-1", "vpc-2"] or len(page_calls) != 2:
        raise AssertionError("Pagination did not collect both pages exactly once")

    def repeated_marker(*_: Any, **__: Any) -> dict[str, Any]:
        return {"vpcs": [], "isTruncated": True, "nextMarker": "same-marker"}

    client.request_json = repeated_marker  # type: ignore[method-assign]
    try:
        client.paginate("/v1/vpc", ("vpcs",))
    except ApiFailure as exc:
        if exc.code != "PaginationLoop":
            raise
    else:
        raise AssertionError("Pagination guard did not reject a repeated marker")

    authorization, headers = bce_authorization(
        "test-ak",
        "test-sk",
        "bcc.bj.baidubce.com",
        "/v1/vpc",
        {"maxKeys": 1000},
        timestamp="2026-08-13T08:00:00Z",
    )
    if not authorization.startswith("bce-auth-v1/test-ak/2026-08-13T08:00:00Z/1800/"):
        raise AssertionError("Unexpected authorization prefix")
    if headers.get("Authorization") != authorization:
        raise AssertionError("Authorization header mismatch")
    expected_signature = (
        "bce-auth-v1/test-ak/2026-08-13T08:00:00Z/1800/host;x-bce-date/"
        "cc1821bf523e9a38f8c086c48b2874f1555c7f672c4fa7ccd91e9d0de24dc889"
    )
    if authorization != expected_signature:
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
        "Self-test passed: fixture analysis, GET-only and endpoint guards, "
        "pagination guards, credential-file guards, and deterministic signer"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Baidu AI Cloud VPC inventory and topology audit"
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
        if args.input:
            inventory = load_inventory(args.input)
        else:
            inventory = collect_live(args)
        analysis = analyze_inventory(inventory)
        inventory_path, report_path = write_outputs(
            args.output_dir, inventory, analysis, overwrite=args.overwrite
        )
        print(f"Inventory: {inventory_path}")
        print(f"Report: {report_path}")
        core_failed = any(
            data.get("coverage", {}).get("vpcs", {}).get("status") != "success"
            for data in inventory.get("regions", {}).values()
        )
        return 2 if core_failed else 0
    except (ApiFailure, FileExistsError, OSError, ValueError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

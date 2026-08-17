"""Small, dependency-free checks for an OpenAI-compatible vLLM service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from time import perf_counter
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


Opener = Callable[..., Any]
_METRIC_NAME = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)")


@dataclass(frozen=True)
class CheckResult:
    """The result of one service check."""

    name: str
    status: str
    detail: str
    latency_ms: float | None = None

    @property
    def passed(self) -> bool:
        return self.status in {"pass", "skipped"}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditReport:
    """A collection of checks with render helpers."""

    results: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": {
                "pass": sum(item.status == "pass" for item in self.results),
                "fail": sum(item.status == "fail" for item in self.results),
                "skipped": sum(item.status == "skipped" for item in self.results),
            },
            "results": [item.to_dict() for item in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            "# ModelOps Sentinel audit report",
            "",
            f"Overall: **{'PASS' if self.ok else 'FAIL'}**",
            "",
            "| Check | Status | Latency | Detail |",
            "| --- | --- | ---: | --- |",
        ]
        for item in self.results:
            latency = "-" if item.latency_ms is None else f"{item.latency_ms:.1f} ms"
            detail = item.detail.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {item.name} | {item.status.upper()} | {latency} | {detail} |")
        return "\n".join(lines) + "\n"


class ServiceAuditor:
    """Audit a vLLM endpoint and its optional Prometheus server."""

    def __init__(
        self,
        vllm_url: str,
        *,
        api_key: str | None = None,
        prometheus_url: str | None = None,
        timeout: float = 10.0,
        opener: Opener = urlopen,
    ) -> None:
        self.vllm_url = vllm_url.rstrip("/")
        self.api_key = api_key
        self.prometheus_url = prometheus_url.rstrip("/") if prometheus_url else None
        self.timeout = timeout
        self._opener = opener

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> tuple[int, str, float]:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if authenticated and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(url, data=data, headers=headers, method=method)
        started = perf_counter()
        with self._opener(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
        return status, body, (perf_counter() - started) * 1000

    @staticmethod
    def _failure(name: str, error: Exception) -> CheckResult:
        if isinstance(error, HTTPError):
            detail = f"HTTP {error.code}: {error.reason}"
        elif isinstance(error, URLError):
            detail = f"connection error: {error.reason}"
        else:
            detail = f"{type(error).__name__}: {error}"
        return CheckResult(name, "fail", detail)

    def check_health(self) -> CheckResult:
        try:
            status, _, latency = self._request(f"{self.vllm_url}/health")
            ok = 200 <= status < 300
            return CheckResult(
                "vLLM health",
                "pass" if ok else "fail",
                f"HTTP {status}",
                latency,
            )
        except Exception as error:  # network errors are report data
            return self._failure("vLLM health", error)

    def check_metrics(self) -> CheckResult:
        try:
            status, body, latency = self._request(f"{self.vllm_url}/metrics")
            metric_names: set[str] = set()
            for line in body.splitlines():
                if not line or line.startswith("#"):
                    continue
                match = _METRIC_NAME.match(line)
                if match:
                    metric_names.add(match.group(1))
            ok = 200 <= status < 300 and bool(metric_names)
            detail = f"HTTP {status}; {len(metric_names)} unique metric names"
            return CheckResult(
                "vLLM metrics",
                "pass" if ok else "fail",
                detail,
                latency,
            )
        except Exception as error:
            return self._failure("vLLM metrics", error)

    def check_chat(self, model: str, prompt: str) -> CheckResult:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 64,
            "temperature": 0.0,
        }
        try:
            status, body, latency = self._request(
                f"{self.vllm_url}/v1/chat/completions",
                method="POST",
                payload=payload,
                authenticated=True,
            )
            parsed = json.loads(body)
            choices = parsed.get("choices") or []
            content = ""
            if choices:
                content = (choices[0].get("message") or {}).get("content") or ""
            ok = 200 <= status < 300 and bool(content.strip())
            detail = (
                f"HTTP {status}; non-empty answer ({len(content)} chars)"
                if ok
                else f"HTTP {status}; response did not contain a non-empty answer"
            )
            return CheckResult(
                "chat completion",
                "pass" if ok else "fail",
                detail,
                latency,
            )
        except Exception as error:
            return self._failure("chat completion", error)

    def check_prometheus_targets(self) -> CheckResult:
        if not self.prometheus_url:
            return CheckResult("Prometheus targets", "skipped", "URL not configured")
        try:
            status, body, latency = self._request(
                f"{self.prometheus_url}/api/v1/targets"
            )
            parsed = json.loads(body)
            active = ((parsed.get("data") or {}).get("activeTargets") or [])
            up = sum(target.get("health") == "up" for target in active)
            down = len(active) - up
            ok = 200 <= status < 300 and parsed.get("status") == "success" and up > 0 and down == 0
            return CheckResult(
                "Prometheus targets",
                "pass" if ok else "fail",
                f"{up} up, {down} down",
                latency,
            )
        except Exception as error:
            return self._failure("Prometheus targets", error)

    def audit(self, *, model: str | None = None, prompt: str = "Reply with OK.") -> AuditReport:
        results: list[CheckResult] = [self.check_health(), self.check_metrics()]
        if model:
            results.append(self.check_chat(model, prompt))
        else:
            results.append(CheckResult("chat completion", "skipped", "model not configured"))
        results.append(self.check_prometheus_targets())
        return AuditReport(tuple(results))


def format_terminal(results: Iterable[CheckResult]) -> str:
    """Render a compact terminal table without third-party dependencies."""

    rows = [("CHECK", "STATUS", "LATENCY", "DETAIL")]
    for item in results:
        latency = "-" if item.latency_ms is None else f"{item.latency_ms:.1f} ms"
        rows.append((item.name, item.status.upper(), latency, item.detail))
    widths = [max(len(row[index]) for row in rows) for index in range(4)]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )


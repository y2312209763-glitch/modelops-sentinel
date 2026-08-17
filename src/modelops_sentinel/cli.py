"""Command-line interface for ModelOps Sentinel."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .auditor import ServiceAuditor, format_terminal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modelops-sentinel",
        description="Audit vLLM health, chat, metrics, and Prometheus targets.",
    )
    parser.add_argument(
        "--vllm-url",
        default=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--model", default=os.getenv("VLLM_MODEL"))
    parser.add_argument("--api-key", default=os.getenv("VLLM_API_KEY"))
    parser.add_argument("--prometheus-url", default=os.getenv("PROMETHEUS_URL"))
    parser.add_argument("--prompt", default="Reply with OK.")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--format",
        choices=("table", "json", "markdown"),
        default="table",
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    auditor = ServiceAuditor(
        args.vllm_url,
        api_key=args.api_key,
        prometheus_url=args.prometheus_url,
        timeout=args.timeout,
    )
    report = auditor.audit(model=args.model, prompt=args.prompt)

    if args.format == "json":
        rendered = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
    elif args.format == "markdown":
        rendered = report.to_markdown()
    else:
        rendered = format_terminal(report.results) + "\n"

    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, List

from .agent import LocalCodexAgent


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local Codex-style agent for project analysis, coding help, and safe file edits."
    )
    parser.add_argument(
        "--config",
        help="Path to an alternate JSON config file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Ask the agent a natural-language question.")
    ask_parser.add_argument("goal", help="User goal or question.")
    ask_parser.add_argument("--project", help="Project directory to inspect.")

    scan_parser = subparsers.add_parser("scan", help="Scan a project directory.")
    scan_parser.add_argument("--project", help="Project directory to inspect.")

    models_parser = subparsers.add_parser("models", help="Show configured model routing.")
    models_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    doctor_parser = subparsers.add_parser("doctor", help="Check provider health and config.")
    doctor_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    edit_parser = subparsers.add_parser(
        "edit",
        help="Ask the coding model to rewrite a file and optionally apply the result.",
    )
    edit_parser.add_argument("--file", required=True, help="Target file to edit.")
    edit_parser.add_argument("--instruction", required=True, help="Edit instruction.")
    edit_parser.add_argument(
        "--task-type",
        choices=["coding", "debug", "refactor", "test"],
        default="refactor",
        help="Routing hint for the model router.",
    )
    edit_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the replacement file but do not overwrite the target.",
    )

    args = parser.parse_args(argv)
    agent = LocalCodexAgent(args.config)

    if args.command == "ask":
        response = agent.handle_request(args.goal, project_path=args.project)
        _print_response(response)
        return 0

    if args.command == "scan":
        project = args.project or agent.settings["default_project"]
        scanned = agent.scan_project(project)
        print(scanned["report"])
        return 0

    if args.command == "models":
        rows = agent.model_inventory()
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            print(_format_table(rows, ["name", "provider", "roles", "available", "description"]))
        return 0

    if args.command == "doctor":
        report = agent.doctor()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"Config: {report['config_path']}")
            print(f"Default project: {report['default_project']}")
            print("")
            print("Providers:")
            for name, status in report["providers"].items():
                print(f"- {name}: ok={status.get('ok')} reason={status.get('reason')}")
            print("")
            print("Models:")
            print(_format_table(report["models"], ["name", "provider", "roles", "available"]))
        return 0

    if args.command == "edit":
        response = agent.edit_file(
            args.file,
            args.instruction,
            task_type=args.task_type,
            apply_changes=not args.dry_run,
        )
        _print_response(response)
        return 0

    parser.print_help()
    return 1


def _print_response(response) -> None:
    print(f"Task type: {response.task_type}")
    print(f"Model: {response.routing.model} ({response.routing.provider})")
    print(f"Reason: {response.routing.reason}")
    if response.project_path:
        print(f"Project: {response.project_path}")
    if response.files_written:
        print(f"Files written: {', '.join(response.files_written)}")
    if response.backup_paths:
        print(f"Backups: {', '.join(response.backup_paths)}")
    print("")
    print(response.output)


def _format_table(rows: Iterable[dict], columns: List[str]) -> str:
    rows = list(rows)
    if not rows:
        return "(no rows)"

    widths = {column: len(column) for column in columns}
    for row in rows:
        for column in columns:
            widths[column] = max(widths[column], len(str(row.get(column, ""))))

    header = " | ".join(column.ljust(widths[column]) for column in columns)
    divider = "-+-".join("-" * widths[column] for column in columns)
    lines = [header, divider]
    for row in rows:
        lines.append(
            " | ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns)
        )
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))

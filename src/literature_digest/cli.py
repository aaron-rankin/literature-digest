"""CLI entrypoint: `literature-digest <subcommand>`.

Subcommands:
    run [--area <slug>] [--limit N] [--debug]   Run the pipeline (all areas or
                                                 just one; --limit caps articles
                                                 screened, for dry runs against
                                                 a local LLM)
    list-areas            Print configured areas and exit
    test-imap             IMAP connection sanity check (Phase 3)
    test-llm              LLM credentials sanity check
    render                Re-render reports from the last run without re-fetching

Uses stdlib argparse + rich for output (no extra deps beyond what's already declared).
"""

from __future__ import annotations

import argparse
import sys
import webbrowser

from rich.console import Console
from rich.table import Table

from literature_digest.config import Settings, discover_areas
from literature_digest.pipeline import run_all
from literature_digest.screen import LLMClient

console = Console()


def cmd_list_areas(args: argparse.Namespace) -> int:
    settings = Settings()
    areas = discover_areas(settings)
    table = Table(title="Configured research areas")
    table.add_column("slug", style="cyan")
    table.add_column("name")
    table.add_column("terms", justify="right")
    table.add_column("threshold", justify="right")
    for area in areas:
        threshold = area.threshold if area.threshold is not None else "(default)"
        table.add_row(
            area.slug,
            area.name,
            str(len(area.terms)),
            str(threshold),
        )
    console.print(table)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    index_path = run_all(
        only_area=args.area, limit=args.limit, debug=args.debug, local=args.local
    )
    if args.open:
        webbrowser.open(f"file://{index_path.resolve()}")
    return 0


def cmd_test_imap(args: argparse.Namespace) -> int:
    console.print("[yellow]PLACEHOLDER[/] test-imap not implemented until Phase 3.")
    return 0


def cmd_test_llm(args: argparse.Namespace) -> int:
    settings = Settings()
    base_note = f"  api_base=[cyan]{settings.lit_api_base}[/]" if settings.lit_api_base else ""
    console.print(f"Model: [cyan]{settings.lit_model}[/]{base_note}")
    client = LLMClient(settings)
    try:
        data = client.complete_json(
            'Reply with JSON only: {"ok": true, "note": "<one short sentence>"}',
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        )
    except Exception as exc:
        console.print(f"[bold red]FAILED[/] {exc!r}")
        return 1
    console.print(f"[bold green]OK[/] {data}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    console.print("[yellow]PLACEHOLDER[/] render-from-state not implemented yet.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="literature-digest",
        description="Bi-weekly literature digest pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the pipeline (all areas or just --area).")
    p_run.add_argument("--area", help="Only run this area slug.")
    p_run.add_argument("--open", action="store_true", help="Open the index in a browser when done.")
    p_run.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of new articles screened/summarized per area (for dry runs).",
    )
    p_run.add_argument(
        "--debug",
        action="store_true",
        help="Print per-article screening/summarization results as they happen.",
    )
    p_run.add_argument(
        "--local",
        action="store_true",
        help="Run fully offline from data/fixtures/<area>/ (no Scopus/OpenAlex/"
        "Crossref calls); writes to state.local.db and re-processes every run.",
    )
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list-areas", help="Print configured research areas.")
    p_list.set_defaults(func=cmd_list_areas)

    p_imap = sub.add_parser("test-imap", help="IMAP connection sanity check.")
    p_imap.set_defaults(func=cmd_test_imap)

    p_llm = sub.add_parser("test-llm", help="LLM credentials sanity check.")
    p_llm.set_defaults(func=cmd_test_llm)

    p_render = sub.add_parser("render", help="Re-render reports from the last run.")
    p_render.set_defaults(func=cmd_render)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Long runs are often piped to a file/background task; without this,
    # Python block-buffers non-TTY stdout and progress only appears at exit.
    sys.stdout.reconfigure(line_buffering=True)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

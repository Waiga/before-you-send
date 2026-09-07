"""The command line: one file in, one report out, and an exit code a script can use."""

from __future__ import annotations

import argparse
import sys

from before_you_send import __version__
from before_you_send.document import UnreadableDocument
from before_you_send.findings import Level, Report
from before_you_send.report import to_json, to_text
from before_you_send.run import inspect_document

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_UNREADABLE = 2

THRESHOLDS = {"high": Level.HIGH, "medium": Level.MEDIUM, "low": Level.LOW}

DESCRIPTION = (
    "Reads a PDF and reports what is still inside it that you may not mean to send: "
    "text under a box that was never removed, earlier versions of the document, "
    "attached files, and the names left in its properties. Nothing leaves your machine."
)

EPILOGUE = (
    "It does not tell you a document is safe to send. It tells you what it found, "
    "and where it could not see."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="before-you-send",
        description=DESCRIPTION,
        epilog=EPILOGUE,
    )
    parser.add_argument("path", help="the PDF to read")
    parser.add_argument(
        "--version",
        action="version",
        version=f"before-you-send {__version__}",
        help="print the version and exit",
    )
    parser.add_argument(
        "--show-content",
        action="store_true",
        help=(
            "include what was found, not just where it is. Off by default, so a report "
            "can be shared without carrying the thing it found."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="explain why each finding matters",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="text for a person, json for a script",
    )
    parser.add_argument(
        "--fail-on",
        choices=("high", "medium", "low", "never"),
        default="medium",
        help=(
            "the level at which to exit non-zero, for use in a pipeline "
            "(default: medium)"
        ),
    )
    return parser


def _should_fail(report: Report, threshold: str) -> bool:
    if threshold == "never":
        return False
    worst = report.worst_level()
    if worst is None:
        return False
    return worst.rank >= THRESHOLDS[threshold].rank


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        report = inspect_document(args.path)
    except UnreadableDocument as error:
        print(f"Cannot read this file.\n\n{error}", file=sys.stderr)
        print(
            "\nNothing was examined, so nothing is reported. That is not a clean "
            "result.",
            file=sys.stderr,
        )
        return EXIT_UNREADABLE

    if args.format == "json":
        print(to_json(report, show_content=args.show_content))
    else:
        print(to_text(report, show_content=args.show_content, verbose=args.verbose))

    return EXIT_FINDINGS if _should_fail(report, args.fail_on) else EXIT_CLEAN


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

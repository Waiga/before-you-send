"""The command line: one file in, one report out, and an exit code a script can use."""

from __future__ import annotations

import argparse
import sys

from before_you_send import __version__
from before_you_send.document import MissingDependency, UnreadableDocument
from before_you_send.findings import Level, Report
from before_you_send.report import to_json, to_text
from before_you_send.run import inspect_document

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_UNREADABLE = 2
# A fourth code, because "this file is bad" and "this tool is incomplete" are not
# the same event and a pipeline should not have to guess which one it got. Exit 2
# sends an operator to look at their document. When a package is missing the
# document has not been called into question at all, and sending somebody to
# examine a file that was never examined is the defect this code exists to end.
# Nothing that was correct before regresses: anything treating non-zero as "do not
# send" still holds, and a check for exactly 2 now correctly declines to match.
# It covers two events, not one. Either nothing could be examined, because the
# document would not open without the package, or some of it could not, because a
# single check or a single page walk needed the package and the rest of the run was
# fine. Both are the same sentence to the person running it: this tool is
# incomplete, so do not read what it printed as the whole picture.
EXIT_TOOL_INCOMPLETE = 3

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
    except MissingDependency as error:
        # Checked before UnreadableDocument, which it subclasses.
        print(f"This tool is missing something it needs.\n\n{error}", file=sys.stderr)
        print(
            "\nNothing was examined, so nothing is reported. That is not a clean "
            "result.",
            file=sys.stderr,
        )
        return EXIT_TOOL_INCOMPLETE
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

    if report.missing_packages:
        # The report is printed first and in full. The document was opened, the
        # pages were read, and every check that could run did: throwing that away
        # because one check was short a package would be the tool deciding a
        # partial truth is worth less than nothing, which is the opposite of the
        # position it takes everywhere else.
        #
        # The code still has to be 3. Exit 0 is the only code a pipeline reads as
        # "send it", and a check that never ran cannot have found anything, so a
        # clean-looking 0 here would be the whole defect again one level up: an
        # honest NOT CHECKED entry that a person can read and a script cannot.
        #
        # It is returned ahead of the findings code on purpose. Both are non-zero
        # and both mean do not send, so nothing that gated on non-zero changes.
        # The difference is that the findings are printed either way, while "this
        # report has a hole in it, and an install will fix it" has nowhere else to
        # go. --fail-on is not consulted, because it selects which finding levels
        # matter and a missing package is not a finding.
        print(
            "\nThis tool is missing something it needs. "
            f"{len(report.missing_packages)} thing(s) could not be examined because "
            "a package is not installed, and each one is named in the report above. "
            "What they would have found is unknown, so this is not a clean result.",
            file=sys.stderr,
        )
        return EXIT_TOOL_INCOMPLETE

    return EXIT_FINDINGS if _should_fail(report, args.fail_on) else EXIT_CLEAN


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

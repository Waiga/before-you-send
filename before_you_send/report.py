"""Turning a Report into something a person or a script can read.

Recovered content stays out of the output unless the caller asks for it. The whole
point of this tool is that a document is about to be sent somewhere, and a report
about it is the thing most likely to be pasted into a chat window on the way. A
report that quotes the secret it found has moved the secret rather than contained it.

The other rule this file enforces is that "no findings" is never printed on its own.
If there were places the tool could not see, they are printed in the same breath.
"""

from __future__ import annotations

import json

from before_you_send.findings import Level, Report

LEVEL_LABEL = {Level.HIGH: "HIGH  ", Level.MEDIUM: "MEDIUM", Level.LOW: "LOW   "}


def _printable(text: str) -> str:
    """Strip control characters out of anything recovered from the document.

    What a finding recovered is attacker-controlled text. Written straight to a
    terminal, an escape sequence in a document's title can clear the screen and
    print a clean bill of health of its own over the top of the real report.
    """
    return "".join(" " if ch < " " or ch == "\x7f" else ch for ch in text)

NOT_CHECKED_ALWAYS = [
    (
        "Whether anything found here is actually a secret",
        (
            "The tool reports that something is present and not visible. Whether that "
            "matters is a judgement about the content, and it does not read the "
            "content for meaning."
        ),
    ),
    (
        "Anything inside a picture",
        (
            "Images are not examined. Text in a screenshot, a signature, a scanned "
            "page, or a chart drawn as an image is invisible to this tool, and a "
            "sensitive document that was flattened into pictures will look empty here."
        ),
    ),
    (
        "Whether the visible text should be visible",
        (
            "Content that is plainly on the page and plainly readable is not a "
            "finding, however confidential it is. This tool looks for what a sender "
            "does not know is there."
        ),
    ),
]


SAMPLE_LIMIT = 400


def _sample(text: str) -> str:
    """Recovered content, made safe to print and bounded in length.

    A document decides how long this is, not the tool. One real paper in testing
    carried 398 embedded files and printed all 398 names on a single line. The
    cap is not cosmetic: this string is attacker-controlled and goes to a
    terminal.
    """
    text = _printable(text)
    if len(text) <= SAMPLE_LIMIT:
        return text
    return text[:SAMPLE_LIMIT].rstrip() + f" … ({len(text) - SAMPLE_LIMIT} more characters)"


def _clean_dict(entry: dict) -> dict:
    if "sample" in entry:
        entry["sample"] = _sample(entry["sample"])
    return entry


def to_json(report: Report, show_content: bool = False) -> str:
    payload = {
        "file": report.path,
        "pages_read": report.pages_read,
        "picture_pages": report.picture_pages,
        "short_runs_skipped": report.short_runs,
        "counts": report.counts(),
        "findings": [
            _clean_dict(f.as_dict(show_content)) for f in report.sorted_findings()
        ],
        "could_not_see": [b.as_dict() for b in report.blindspots],
        "not_checked": [u.as_dict() for u in report.unchecked]
        + [{"topic": t, "reason": r} for t, r in NOT_CHECKED_ALWAYS],
        # Empty on every ordinary run. Non-empty means a check could not run for
        # want of a package, so this report has a hole in it that is the tool's
        # fault and not the file's. A script should be able to learn that without
        # matching on prose, which is why it is a field rather than only a sentence.
        "missing_packages": list(report.missing_packages),
        "content_included": show_content,
    }
    return json.dumps(payload, indent=2)


def _rule(char: str = "-", width: int = 72) -> str:
    return char * width


def _wrap(text: str, width: int) -> list:
    words, out, line = text.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def to_text(report: Report, show_content: bool = False, verbose: bool = False) -> str:
    lines: list = []
    counts = report.counts()
    total = sum(counts.values())

    lines.append(f"Before You Send: {report.path}")
    lines.append(_rule("="))
    lines.append(
        f"Read {report.pages_read} page(s). {total} finding(s): "
        f"{counts['high']} high, {counts['medium']} medium, {counts['low']} low."
    )
    if report.blindspots:
        lines.append(f"{len(report.blindspots)} place(s) could not be seen into.")
    if report.picture_pages:
        # This line is printed on every run that has picture pages, clean ones
        # included. A document flattened into images produces no findings at all,
        # and without this the report of one is indistinguishable from the report
        # of a document that was genuinely read and was genuinely clear.
        lines.append(
            f"{report.picture_pages} of {report.pages_read} page(s) are mostly "
            "picture, and pictures are not read."
        )
    lines.append("")

    if not report.findings:
        lines.append("Found nothing in what could be read.")
        lines.append("")
        lines.append("That is not the same as 'safe to send'. Read what could not be")
        lines.append("seen and what was not checked, below, before treating it as one.")
        lines.append("")
    else:
        current = None
        for finding in report.sorted_findings():
            if finding.level is not current:
                current = finding.level
                lines.append(finding.level.value.upper())
                lines.append(_rule())
            lines.append(
                f"{LEVEL_LABEL[finding.level]}  {finding.page}  {finding.location}"
                f"  [{finding.check}]"
            )
            lines.append(f"        {finding.summary}")
            if verbose and finding.detail:
                for chunk in _wrap(finding.detail, 62):
                    lines.append(f"        {chunk}")
            if show_content and finding.sample is not None:
                lines.append(f"        content: {_sample(finding.sample)}")
            lines.append("")

    if report.blindspots:
        lines.append("COULD NOT SEE")
        lines.append(_rule())
        for spot in report.blindspots:
            lines.append(f"  - {spot.page}  {spot.location}")
            for chunk in _wrap(spot.reason, 66):
                lines.append(f"      {chunk}")
        lines.append("")

    lines.append("NOT CHECKED")
    lines.append(_rule())
    for item in report.unchecked:
        lines.append(f"  - {item.topic}")
        for chunk in _wrap(item.reason, 66):
            lines.append(f"      {chunk}")
    for topic, reason in NOT_CHECKED_ALWAYS:
        lines.append(f"  - {topic}")
        for chunk in _wrap(reason, 66):
            lines.append(f"      {chunk}")
    lines.append("")

    if not show_content and any(f.sample is not None for f in report.findings):
        lines.append(
            "What was found was withheld. Re-run with --show-content to include it."
        )

    return "\n".join(lines)

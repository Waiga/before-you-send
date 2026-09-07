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


def to_json(report: Report, show_content: bool = False) -> str:
    payload = {
        "file": report.path,
        "pages_read": report.pages_read,
        "counts": report.counts(),
        "findings": [f.as_dict(show_content) for f in report.sorted_findings()],
        "could_not_see": [b.as_dict() for b in report.blindspots],
        "not_checked": [u.as_dict() for u in report.unchecked]
        + [{"topic": t, "reason": r} for t, r in NOT_CHECKED_ALWAYS],
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

    lines.append(f"Before You Send — {report.path}")
    lines.append(_rule("="))
    lines.append(
        f"Read {report.pages_read} page(s). {total} finding(s): "
        f"{counts['high']} high, {counts['medium']} medium, {counts['low']} low."
    )
    if report.blindspots:
        lines.append(f"{len(report.blindspots)} place(s) could not be seen into.")
    lines.append("")

    if not report.findings:
        lines.append("Nothing checkable stood out.")
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
                lines.append(f"        content: {finding.sample}")
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

"""Running every check over one document and collecting what they found."""

from __future__ import annotations

from before_you_send.checks import DOCUMENT_CHECKS, PAGE_CHECKS
from before_you_send.checks.visibility import PAGE_IMAGE_SHARE, picture_share
from before_you_send.content import Box, read_page
from before_you_send.document import load
from before_you_send.findings import Report


def _page_box(page) -> Box | None:
    """The visible area of a page: the crop box if there is one, else the media box."""
    for attribute in ("cropbox", "mediabox"):
        try:
            box = getattr(page, attribute, None)
            if box is None:
                continue
            x0, y0, x1, y1 = (float(v) for v in (box.left, box.bottom, box.right, box.top))
            if x1 > x0 and y1 > y0:
                return Box(x0, y0, x1, y1)
        except Exception:
            continue
    return None


def inspect_document(path: str) -> Report:
    """Open a document and run every check against it.

    A check that fails takes itself out of the report and nothing else, and says so.
    A check that crashed and a check that found nothing are not the same result, and
    a report that cannot tell them apart is worthless.
    """
    doc = load(path)
    report = Report(path=doc.path, pages_read=doc.page_count)
    widths_estimated = False
    text_unrecoverable = False

    for number, page in enumerate(doc.pages, start=1):
        label = f"page {number}"
        content = read_page(doc.reader, page)
        widths_estimated = widths_estimated or content.estimated_widths
        text_unrecoverable = text_unrecoverable or content.unrecoverable_text

        if content.unreadable_reason:
            report.note_blindspot(label, "whole page", content.unreadable_reason)
            continue
        if content.truncated:
            report.note_blindspot(
                label,
                "whole page",
                "the page holds more drawing instructions than this tool will follow, "
                "so the rest of it was not examined",
            )

        box = _page_box(page)
        if picture_share(content, box) >= PAGE_IMAGE_SHARE:
            report.picture_pages += 1
        for check in PAGE_CHECKS:
            try:
                check(report, label, content, box)
            except Exception as error:
                report.note_unchecked(
                    f"{check.__name__} on {label}",
                    f"the check did not complete ({type(error).__name__}), so this page "
                    "was not examined for it",
                )

    for check in DOCUMENT_CHECKS:
        try:
            check(report, doc)
        except Exception as error:
            report.note_unchecked(
                check.__name__,
                f"the check did not complete ({type(error).__name__}), so the document "
                "was not examined for it",
            )

    if report.short_runs:
        report.note_unchecked(
            "Text runs of one or two characters",
            f"{report.short_runs} run(s) that short were passed over. A run that "
            "short cannot carry a name, a number of consequence or a word, and in "
            "testing on real documents they were almost always a plot marker, a "
            "rule or a maths glyph rather than anything concealed",
        )

    if report.picture_pages:
        report.note_unchecked(
            "What is inside the pictures",
            f"{report.picture_pages} of {report.pages_read} page(s) are mostly "
            "picture. Nothing inside a picture is examined, so on those pages this "
            "run has very little to say. A document flattened into images will come "
            "back with nothing found and will not be empty",
        )

    if text_unrecoverable:
        report.note_unchecked(
            "What some of the text says",
            "a font here addresses its glyphs by number and carries no map from "
            "those numbers to characters, so runs in it are located and measured "
            "exactly but what they say cannot be recovered and is not guessed at",
        )

    if widths_estimated:
        report.note_unchecked(
            "Exact text extents",
            "at least one font here does not declare its character widths, so how much "
            "of a line is covered by something is an estimate rather than a measurement",
        )

    return report

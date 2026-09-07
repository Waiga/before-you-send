"""Running every check over one document and collecting what they found."""

from __future__ import annotations

from before_you_send.checks import DOCUMENT_CHECKS, PAGE_CHECKS
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

    for number, page in enumerate(doc.pages, start=1):
        label = f"page {number}"
        content = read_page(doc.reader, page)
        widths_estimated = widths_estimated or content.estimated_widths

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

    if widths_estimated:
        report.note_unchecked(
            "Exact text extents",
            "at least one font here does not declare its character widths, so how much "
            "of a line is covered by something is an estimate rather than a measurement",
        )

    return report

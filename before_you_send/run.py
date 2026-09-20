"""Running every check over one document and collecting what they found."""

from __future__ import annotations

from before_you_send.checks import DOCUMENT_CHECKS, PAGE_CHECKS
from before_you_send.checks.visibility import PAGE_IMAGE_SHARE, picture_share
from before_you_send.content import Box, read_page
from before_you_send.document import load, missing_package_errors, package_requirement
from before_you_send.findings import Report


def _page_box(page) -> Box | None:
    """The visible area of a page: the crop box if there is one, else the media box.

    A box this cannot work out is not worth failing a run over, so a malformed one
    costs the page its area and nothing else. A missing package is let past,
    because falling back to no area here is not a harmless degradation: with no
    area the picture share of the page computes as zero, and zero is exactly the
    number that suppresses the warning about a page that is mostly picture. A
    silent swallow there would turn a missing library into a quieter report.
    """
    short_of_something = missing_package_errors()

    for attribute in ("cropbox", "mediabox"):
        try:
            box = getattr(page, attribute, None)
            if box is None:
                continue
            x0, y0, x1, y1 = (float(v) for v in (box.left, box.bottom, box.right, box.top))
            if x1 > x0 and y1 > y0:
                return Box(x0, y0, x1, y1)
        except short_of_something:
            raise
        except Exception:
            continue
    return None


def inspect_document(path: str) -> Report:
    """Open a document and run every check against it.

    A check that fails takes itself out of the report and nothing else, and says so.
    A check that crashed and a check that found nothing are not the same result, and
    a report that cannot tell them apart is worthless.

    There is a third thing in that set, and it is the one this file kept getting
    wrong. A check that could not run because this installation is short a package
    has not crashed and has not found nothing. It never happened. Told apart from
    the other two it is a one line install; folded in with them it is a Python
    exception class printed next to somebody's page, and the reader is left to
    infer that their document did something unusual. Every place below that can
    receive that news handles it before the broad handler, on purpose.
    """
    short_of_something = missing_package_errors()

    doc = load(path)
    report = Report(path=doc.path, pages_read=doc.page_count)
    widths_estimated = False
    text_unrecoverable = False

    for number, page in enumerate(doc.pages, start=1):
        label = f"page {number}"
        content = read_page(doc.reader, page)
        widths_estimated = widths_estimated or content.estimated_widths
        text_unrecoverable = text_unrecoverable or content.unrecoverable_text

        if content.missing_package:
            report.note_missing_package_blindspot(
                label,
                "whole page",
                content.missing_package,
                "nothing painted on this page was examined at all, because its "
                "drawing instructions are what could not be read",
            )
            continue
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

        try:
            box = _page_box(page)
        except short_of_something as error:
            report.note_missing_package(
                f"How much of {label} is picture",
                package_requirement(error),
                "the area of the page could not be read without it, so how much of "
                "this page is picture is not known and is not guessed at",
            )
            box = None
        if picture_share(content, box) >= PAGE_IMAGE_SHARE:
            report.picture_pages += 1
        for check in PAGE_CHECKS:
            try:
                check(report, label, content, box)
            except short_of_something as error:
                # The defect this release exists to close. Falling through to the
                # broad handler below wrote "the check did not complete
                # (DependencyError)" into the report, which names a Python class
                # at a reader who wanted to know whether a file was safe to send,
                # and quietly attributes our missing dependency to their page.
                report.note_missing_package(
                    f"{check.__name__} on {label}",
                    package_requirement(error),
                    "this page was not examined for it",
                )
            except Exception as error:
                report.note_unchecked(
                    f"{check.__name__} on {label}",
                    f"the check did not complete ({type(error).__name__}), so this page "
                    "was not examined for it",
                )

    for check in DOCUMENT_CHECKS:
        try:
            check(report, doc)
        except short_of_something as error:
            report.note_missing_package(
                check.__name__,
                package_requirement(error),
                "the document was not examined for it",
            )
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

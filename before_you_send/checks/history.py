"""What the file remembers about its own past.

A PDF can be edited without rewriting it. The original bytes stay exactly where they
are and a new section is appended that points past them. Nothing is deleted. A page
"removed" and saved this way is still in the file, in full, and comes back out with
ordinary tools.

This is also how every digital signature works, so the check has to say which case
it is looking at rather than treating one as the other.
"""

from __future__ import annotations

from before_you_send.findings import Finding, Level


def _has_signature(doc) -> bool:
    """True when the document carries a signature field, which requires an update."""
    try:
        root = doc.reader.trailer["/Root"].get_object()
        form = root.get("/AcroForm")
        if form is None:
            return False
        fields = form.get_object().get("/Fields")
        if fields is None:
            return False
        for field in fields.get_object():
            field = field.get_object()
            if str(field.get("/FT", "")) == "/Sig" and field.get("/V") is not None:
                return True
    except Exception:
        return False
    return False


def earlier_versions_retained(report, doc) -> None:
    """Earlier revisions of the document still present in the bytes."""
    revisions = doc.raw.count(b"%%EOF")
    if revisions < 2:
        return

    # A cross-reference section that names a previous one is what makes the older
    # objects reachable. Without it the trailing %%EOF markers prove nothing.
    if b"/Prev" not in doc.raw:
        return

    earlier = revisions - 1
    signed = _has_signature(doc)

    if signed and earlier == 1:
        report.add(
            Finding(
                check="earlier_versions_retained",
                level=Level.LOW,
                page="document",
                location="file structure",
                summary=(
                    "The file contains 1 earlier version of itself, and it carries a "
                    "signature, which is the ordinary reason for that."
                ),
                detail=(
                    "Signing a PDF appends to it rather than rewriting it, so one "
                    "earlier version is expected here and is not evidence of anything. "
                    "What was in that earlier version is still readable, so if the "
                    "document was edited before it was signed, the pre-edit content "
                    "is in the file."
                ),
            )
        )
        return

    report.add(
        Finding(
            check="earlier_versions_retained",
            level=Level.MEDIUM if signed else Level.HIGH,
            page="document",
            location="file structure",
            summary=(
                f"The file contains {earlier} earlier version(s) of itself, kept in "
                "full alongside the current one."
            ),
            detail=(
                "PDFs are commonly edited by appending, which leaves every previous "
                "version intact inside the same file. Text deleted from a page, a page "
                "removed, or a value changed in an earlier draft can still be read out "
                "of the older section. Saving the document again as a new file, rather "
                "than saving over it, is what discards the history."
                + (
                    " This document is also signed, and signing accounts for one of "
                    "these updates."
                    if signed
                    else ""
                )
            ),
        )
    )

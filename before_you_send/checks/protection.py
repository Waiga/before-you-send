"""Protection that was intended, started, or only appears to be there.

Each of these is a case where somebody took a deliberate step to conceal or restrict
something, and the step did not do what they believe it did.
"""

from __future__ import annotations

from before_you_send.findings import Finding, Level


def unapplied_redaction_marks(report, doc) -> None:
    """Regions marked for redaction where the redaction was never carried out.

    Marking is one step, applying is another. Save between the two and the file
    contains a map of exactly which passages are sensitive, with all of them intact.
    """
    marks: list = []
    for number, page in enumerate(doc.pages, start=1):
        try:
            annots = page.get("/Annots")
            if annots is None:
                continue
            for annot in annots.get_object():
                if str(annot.get_object().get("/Subtype", "")) == "/Redact":
                    marks.append(number)
        except Exception:
            continue

    if not marks:
        return

    pages = sorted(set(marks))
    report.add(
        Finding(
            check="unapplied_redaction_marks",
            level=Level.HIGH,
            page="document",
            location=f"page(s) {', '.join(str(p) for p in pages)}",
            summary=(
                f"{len(marks)} region(s) are marked for redaction but the redaction "
                "has not been applied."
            ),
            detail=(
                "Marking text for redaction and applying the redaction are two separate "
                "actions. Until the second one runs, every marked passage is still in "
                "the file, and the marks themselves now point at precisely the parts "
                "somebody judged too sensitive to release."
            ),
        )
    )


def hidden_layers(report, doc) -> None:
    """Layers switched off, whose content is still in the file."""
    try:
        root = doc.reader.trailer["/Root"].get_object()
        properties = root.get("/OCProperties")
        if properties is None:
            return
        default = properties.get_object().get("/D")
        if default is None:
            return
        off = default.get_object().get("/OFF")
        if off is None or len(off.get_object()) == 0:
            return
        count = len(off.get_object())
    except Exception:
        return

    report.add(
        Finding(
            check="hidden_layers",
            level=Level.MEDIUM,
            page="document",
            location="optional content",
            summary=f"{count} layer(s) are set to be hidden when the document opens.",
            detail=(
                "Layers are a display setting, not a deletion. Everything on a hidden "
                "layer is in the file and any reader can switch it back on. Draft "
                "markings, internal annotations and alternate versions are commonly "
                "parked this way."
            ),
        )
    )


def encryption_without_a_password(report, doc) -> None:
    """Restrictions that any reader can ignore."""
    if not doc.owner_password_only:
        return
    report.add(
        Finding(
            check="encryption_without_a_password",
            level=Level.LOW,
            page="document",
            location="document security",
            summary=(
                "The document is marked as restricted but opens with no password at "
                "all."
            ),
            detail=(
                "This kind of protection records a request that readers not copy or "
                "print the document. Honouring it is up to the viewer, and the file "
                "opened here without a password. It is a statement of intent, not a "
                "control, and it should not be relied on to keep anything private."
            ),
        )
    )

"""Things carried inside the document that are not part of the document.

A PDF is a container. It can hold whole other files, scripts that run when it opens,
and form fields whose values are stored separately from the page they appear on. All
three survive being emailed, and none of them are visible when reading the pages.
"""

from __future__ import annotations

from before_you_send.annotations import scan
from before_you_send.findings import Finding, Level

ACTIVE_KEYS = {
    "/JavaScript": "a script",
    "/JS": "a script",
    "/Launch": "a command to open another program or file",
    "/SubmitForm": "an instruction to send the form's contents somewhere",
    "/ImportData": "an instruction to load data from a file",
}

# Hidden and NoView, from the annotation flags. Either one means a form field is
# present and holding a value the reader will not see.
FLAG_HIDDEN = 1 << 1
FLAG_NOVIEW = 1 << 5


def _root(doc):
    try:
        return doc.reader.trailer["/Root"].get_object()
    except Exception:
        return None


def embedded_files(report, doc) -> None:
    """Whole files attached to the document."""
    names: list = []

    try:
        for attachment in doc.reader.attachment_list:
            label = getattr(attachment, "name", None)
            names.append(str(label) if label else "unnamed attachment")
    except Exception:
        pass

    if not names:
        # Older producers attach through annotations rather than the name tree.
        found = scan(doc.pages)
        found.note_gap(report, "embedded_files")
        for _, annot in found.items:
            try:
                if str(annot.get("/Subtype", "")) == "/FileAttachment":
                    names.append(str(annot.get("/FS", "attachment")))
            except Exception:
                continue

    if not names:
        return

    report.add(
        Finding(
            check="embedded_files",
            level=Level.HIGH,
            page="document",
            location="attachments",
            summary=f"{len(names)} whole file(s) are attached inside this document.",
            detail=(
                "An attached file travels with the PDF and is extracted in one step. "
                "It is frequently the spreadsheet the document was built from, which "
                "contains far more than the document chose to show. Nothing about the "
                "pages indicates it is there."
            ),
            sample=" | ".join(names),
        )
    )


def active_content(report, doc) -> None:
    """Scripts and automatic actions that run when the document is opened or used."""
    found: dict = {}

    root = _root(doc)
    if root is not None:
        try:
            if root.get("/OpenAction") is not None:
                action = root["/OpenAction"].get_object()
                if isinstance(action, dict):
                    kind = str(action.get("/S", ""))
                    if kind in ACTIVE_KEYS:
                        found.setdefault(kind, []).append("runs when the file is opened")
        except Exception:
            pass
        try:
            names = root.get("/Names")
            if names is not None and names.get_object().get("/JavaScript") is not None:
                found.setdefault("/JavaScript", []).append("stored in the document")
        except Exception:
            pass
        try:
            if root.get("/AA") is not None:
                found.setdefault("/JavaScript", []).append("attached to a document event")
        except Exception:
            pass

    for number, page in enumerate(doc.pages, start=1):
        try:
            if page.get("/AA") is not None:
                found.setdefault("/JavaScript", []).append(f"attached to page {number}")
        except Exception:
            pass
    annotations = scan(doc.pages)
    annotations.note_gap(report, "active_content")
    for number, annot in annotations.items:
        try:
            action = annot.get("/A")
            if action is None:
                continue
            kind = str(action.get_object().get("/S", ""))
            if kind in ACTIVE_KEYS:
                found.setdefault(kind, []).append(f"on page {number}")
        except Exception:
            continue

    if not found:
        return

    described = ", ".join(sorted({ACTIVE_KEYS[k] for k in found}))
    report.add(
        Finding(
            check="active_content",
            level=Level.HIGH,
            page="document",
            location="document actions",
            summary=f"The document contains {described}.",
            detail=(
                "A PDF can do things as well as show things. Whether this particular "
                "action is harmful is not something this tool judges, and it does not "
                "read the script. What it can say is that the document is not inert, "
                "which many recipients assume a PDF is."
            ),
            sample=" | ".join(f"{k}: {', '.join(v)}" for k, v in sorted(found.items())),
        )
    )


def form_field_values(report, doc) -> None:
    """Form fields still holding what somebody typed into them."""
    try:
        fields = doc.reader.get_fields()
    except Exception:
        fields = None
    if not fields:
        return

    filled: list = []
    for name, field in fields.items():
        try:
            value = field.get("/V")
        except Exception:
            continue
        if value is None or not str(value).strip():
            continue
        filled.append((str(name), str(value)))

    if not filled:
        return

    hidden = 0
    widgets = scan(doc.pages)
    widgets.note_gap(report, "form_field_values")
    for _, annot in widgets.items:
        try:
            if str(annot.get("/Subtype", "")) != "/Widget":
                continue
            flags = int(annot.get("/F", 0))
            if flags & (FLAG_HIDDEN | FLAG_NOVIEW) and annot.get("/V") is not None:
                hidden += 1
        except Exception:
            continue

    report.add(
        Finding(
            check="form_field_values",
            level=Level.HIGH if hidden else Level.MEDIUM,
            page="document",
            location="form fields",
            summary=(
                f"{len(filled)} form field(s) still hold a value"
                + (f", {hidden} of them not shown on the page." if hidden else ".")
            ),
            detail=(
                "A filled form keeps its answers as data, separate from what is drawn "
                "on the page. Printing to PDF or flattening the form fixes this; "
                "sending the filled form does not."
                + (
                    " Some of these fields are marked hidden, so their values do not "
                    "appear when the document is read but are still in the file."
                    if hidden
                    else ""
                )
            ),
            sample=" | ".join(f"{n}: {v}" for n, v in filled),
        )
    )

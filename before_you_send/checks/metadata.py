"""Who made this, on what machine, and what they called it.

None of this is hidden. All of it is two clicks away in any viewer, which is exactly
why nobody looks at it before sending. A document's properties routinely carry the
author's account name, the internal filename it was saved under, and the folder it
was built in.
"""

from __future__ import annotations

import re

from before_you_send.annotations import scan
from before_you_send.findings import Finding, Level

DESCRIPTIVE_FIELDS = ("/Title", "/Subject", "/Keywords")

# A value that looks like somewhere on somebody's disk rather than a description.
PATH_LIKE = re.compile(
    r"""(
          [A-Za-z]:\\                 # C:\ ...
        | \\\\[^\\]+\\                # \\server\share
        | /(?:Users|home)/[^/\s]+     # /Users/name or /home/name
        | /Volumes/[^/\s]+            # a mounted disk
    )""",
    re.VERBOSE,
)


def _info(doc) -> dict:
    try:
        meta = doc.reader.metadata
        if meta is None:
            return {}
        return {str(k): str(v) for k, v in meta.items() if v is not None}
    except Exception:
        return {}


def document_author(report, doc) -> None:
    """A named author recorded in the document properties."""
    info = _info(doc)
    author = (info.get("/Author") or "").strip()
    if not author:
        return
    report.add(
        Finding(
            check="document_author",
            level=Level.MEDIUM,
            page="document",
            location="document properties",
            summary=f"The document names an author ({len(author)} characters).",
            detail=(
                "This is usually the account name of whoever created the file, and it "
                "travels with the document. It is often not the person the recipient "
                "is expecting, particularly when a document was drafted by one team "
                "and sent by another."
            ),
            sample=author,
        )
    )


def descriptive_metadata(report, doc) -> None:
    """Title, subject or keywords left on the document."""
    info = _info(doc)
    present = [f for f in DESCRIPTIVE_FIELDS if (info.get(f) or "").strip()]
    if not present:
        return
    labels = ", ".join(f.lstrip("/").lower() for f in present)
    report.add(
        Finding(
            check="descriptive_metadata",
            level=Level.LOW,
            page="document",
            location="document properties",
            summary=f"The document carries {labels}.",
            detail=(
                "Exporting from a word processor usually copies the original filename "
                "into the title. That filename is frequently more candid than the "
                "document, because nobody expects it to be read."
            ),
            sample=" | ".join(f"{f.lstrip('/')}: {info[f]}" for f in present),
        )
    )


def build_path_in_metadata(report, doc) -> None:
    """A filesystem path left behind in the document properties."""
    info = _info(doc)
    hits = {key: value for key, value in info.items() if PATH_LIKE.search(value)}
    if not hits:
        return
    report.add(
        Finding(
            check="build_path_in_metadata",
            level=Level.MEDIUM,
            page="document",
            location="document properties",
            summary=(
                f"{len(hits)} document property value(s) contain a filesystem path."
            ),
            detail=(
                "A path names a user account, a machine, and often a project or client "
                "folder. It is one of the few things in a document that describes the "
                "sender's organisation rather than the document's subject."
            ),
            sample=" | ".join(f"{k.lstrip('/')}: {v}" for k, v in hits.items()),
        )
    )


def xmp_metadata(report, doc) -> None:
    """A second, separate metadata record that can disagree with the first."""
    try:
        xmp = doc.reader.xmp_metadata
    except Exception:
        xmp = None
    if xmp is None:
        return

    info = _info(doc)
    info_author = (info.get("/Author") or "").strip()

    xmp_authors: list = []
    try:
        for value in xmp.dc_creator or []:
            value = str(value).strip()
            if value:
                xmp_authors.append(value)
    except Exception:
        pass

    disagrees = bool(xmp_authors) and bool(info_author) and info_author not in xmp_authors

    if disagrees:
        report.add(
            Finding(
                check="xmp_metadata",
                level=Level.MEDIUM,
                page="document",
                location="XMP metadata",
                summary=(
                    "The document carries two separate author records and they do not "
                    "match."
                ),
                detail=(
                    "A PDF stores properties in two places. Editing tools often update "
                    "one and leave the other, so the second record can name whoever "
                    "held the document earlier. Clearing the visible author does not "
                    "clear this one."
                ),
                sample=f"properties: {info_author} | XMP: {', '.join(xmp_authors)}",
            )
        )
        return

    if xmp_authors:
        report.add(
            Finding(
                check="xmp_metadata",
                level=Level.LOW,
                page="document",
                location="XMP metadata",
                summary="A second metadata record also names an author.",
                detail=(
                    "Clearing the author in a viewer's properties dialog does not "
                    "always clear this copy, so it is worth checking separately."
                ),
                sample=", ".join(xmp_authors),
            )
        )


def annotation_authors(report, doc) -> None:
    """Comments and markup, and the names attached to them."""
    found = scan(doc.pages)
    found.note_gap(report, "annotation_authors")

    named: list = []
    with_text = 0
    for number, annot in found.items:
        try:
            subtype = str(annot.get("/Subtype", ""))
            if subtype in ("/Link", "/Widget", "/Popup"):
                continue
            who = annot.get("/T")
            what = annot.get("/Contents")
            if who is not None and str(who).strip():
                named.append((number, str(who).strip()))
            if what is not None and str(what).strip():
                with_text += 1
        except Exception:
            continue

    if not named and not with_text:
        return

    people = sorted({who for _, who in named})
    report.add(
        Finding(
            check="annotation_authors",
            level=Level.MEDIUM,
            page="document",
            location="annotations",
            summary=(
                f"{len(named)} annotation(s) name an author"
                + (f" and {with_text} carry comment text" if with_text else "")
                + f", across {len({p for p, _ in named}) or doc.page_count} page(s)."
            ),
            detail=(
                "Comments, highlights and sticky notes stay in the file and carry the "
                "name of whoever made them. Many viewers hide them until the reader "
                "turns comments on, so a document can look finished and still contain "
                "the discussion that produced it."
            ),
            sample=" | ".join(people),
        )
    )

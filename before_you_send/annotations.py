"""Reading a page's annotations without letting one bad entry hide the rest.

An /Annots array can contain a reference to an object that is not there, or an entry
that is not a dictionary at all. Wrapping the whole loop in one try means the first
broken entry ends the loop, every annotation after it is never looked at, and the
report says nothing was found. That is the failure mode this module exists to stop:
the difference between "there were none" and "I could not read them" has to survive
all the way to the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnnotationScan:
    """The annotations that could be read, and a count of those that could not."""

    items: list = field(default_factory=list)  # (page number, annotation dictionary)
    unreadable: int = 0
    pages_affected: set = field(default_factory=set)

    def note_gap(self, report, topic: str) -> None:
        """Record unreadable entries so they cannot be mistaken for absent ones."""
        if not self.unreadable:
            return
        pages = ", ".join(str(p) for p in sorted(self.pages_affected))
        report.note_unchecked(
            topic,
            f"{self.unreadable} annotation(s) on page(s) {pages} could not be read, so "
            "anything they contain was not examined",
        )


def scan(pages) -> AnnotationScan:
    """Every readable annotation across the document, with the failures counted."""
    found = AnnotationScan()
    for number, page in enumerate(pages, start=1):
        try:
            annots = page.get("/Annots")
            if annots is None:
                continue
            annots = annots.get_object()
            entries = list(annots)
        except Exception:
            found.unreadable += 1
            found.pages_affected.add(number)
            continue

        for entry in entries:
            try:
                annot = entry.get_object()
                if not hasattr(annot, "get"):
                    raise TypeError("annotation is not a dictionary")
                found.items.append((number, annot))
            except Exception:
                found.unreadable += 1
                found.pages_affected.add(number)
    return found

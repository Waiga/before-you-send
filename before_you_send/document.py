"""Opening a PDF without trusting it, and saying plainly when it cannot be opened.

A file handed to this tool is by definition one somebody is unsure about. It may be
truncated, mislabelled, encrypted, or built by software that read the specification
loosely. None of that should produce a stack trace, and none of it should quietly
produce an empty report that reads like a clean bill of health.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

MAX_BYTES = 200 * 1024 * 1024
READABLE_SUFFIXES = {".pdf"}

PDF_HEADER = b"%PDF-"


class UnreadableDocument(Exception):
    """The file could not be opened well enough to say anything honest about it."""


@dataclass
class LoadedDocument:
    """One PDF, opened once, with the raw bytes kept for whole-file questions.

    Some of what this tool looks for is not in the object graph at all. Whether an
    earlier version of the file is still present is a question about the bytes, so
    the bytes are carried alongside the parsed document rather than re-read later.
    """

    path: str
    reader: object
    raw: bytes
    owner_password_only: bool = False
    pages: list = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def _describe_open_failure(path: Path, error: Exception) -> str:
    name = type(error).__name__
    head = b""
    try:
        with path.open("rb") as handle:
            head = handle.read(1024)
    except Exception:
        pass

    if PDF_HEADER not in head:
        return (
            "The file does not begin with a PDF header. It is either not a PDF, or "
            "it is damaged at the very start. Renaming a file does not change what "
            "is inside it."
        )
    return (
        f"The file starts like a PDF but could not be parsed ({name}). It is most "
        "likely truncated or damaged. A partial read would produce a report that "
        "looks clean because nothing could be examined, so nothing is reported."
    )


def load(path_text: str) -> LoadedDocument:
    """Open a PDF, or raise UnreadableDocument with a reason a person can act on."""
    from pypdf import PdfReader

    path = Path(path_text)

    if not path.exists():
        raise UnreadableDocument(f"There is no file at {path_text}.")
    if path.is_dir():
        raise UnreadableDocument(f"{path_text} is a folder, not a file.")

    size = path.stat().st_size
    if size == 0:
        raise UnreadableDocument("The file is empty.")
    if size > MAX_BYTES:
        raise UnreadableDocument(
            f"The file is {size // (1024 * 1024)} MB, over the {MAX_BYTES // (1024 * 1024)} MB "
            "limit this tool will read. The limit exists so a malformed or hostile "
            "file cannot exhaust memory."
        )

    suffix = path.suffix.lower()
    if suffix and suffix not in READABLE_SUFFIXES:
        raise UnreadableDocument(
            f"This tool reads PDF files. {suffix} is not one, and no attempt was made "
            "to guess at its contents."
        )

    raw = path.read_bytes()

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as error:
        raise UnreadableDocument(_describe_open_failure(path, error))

    owner_password_only = False
    if getattr(reader, "is_encrypted", False):
        try:
            opened = reader.decrypt("")
        except Exception:
            opened = 0
        if not opened:
            raise UnreadableDocument(
                "The file is encrypted and needs a password to open. Nothing inside it "
                "could be examined, which is not the same as nothing being there."
            )
        owner_password_only = True

    try:
        pages = list(reader.pages)
    except Exception as error:
        raise UnreadableDocument(_describe_open_failure(path, error))

    if not pages:
        raise UnreadableDocument("The file parsed, but contains no pages.")

    return LoadedDocument(
        path=str(path),
        reader=reader,
        raw=raw,
        owner_password_only=owner_password_only,
        pages=pages,
    )

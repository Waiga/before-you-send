"""A very small PDF writer, used only to build test fixtures.

Fixtures are assembled from literal bytes rather than produced by a rendering
library, for three reasons. Paint order is the fact several checks turn on, and here
it is written down explicitly instead of being whatever a layout engine happened to
emit. Nothing binary is committed, so a reviewer reads every fixture in the diff.
And no fixture can accidentally carry real content, because every byte in it was
typed here.

This is deliberately not part of the shipped package. It writes PDFs; the tool only
ever reads them.
"""

from __future__ import annotations

HELVETICA = b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"


def assemble(objects: list, root: int = 1, trailer_extra: str = "") -> bytes:
    """Lay out numbered objects with a correct cross-reference table."""
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: list = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    size = len(objects) + 1
    out += b"xref\n0 %d\n" % size
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<</Size %d/Root %d 0 R%s>>\n" % (size, root, trailer_extra.encode())
    out += b"startxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(out)


def stream(body: bytes, extra: str = "") -> bytes:
    return b"<</Length %d%s>>\nstream\n" % (len(body), extra.encode()) + body + b"\nendstream"


def one_page(
    content: bytes,
    page_extra: str = "",
    resources: str = "/Font<</F1 5 0 R>>",
    extra_objects: list | None = None,
    catalog_extra: str = "",
    trailer_extra: str = "",
    media_box: str = "[0 0 612 792]",
    font: bytes = HELVETICA,
) -> bytes:
    """A single-page document whose content stream is exactly ``content``.

    Object numbers are fixed so fixtures can refer to them: 1 catalog, 2 pages,
    3 page, 4 contents, 5 the font. Anything in ``extra_objects`` starts at 6.
    """
    objects = [
        b"<</Type/Catalog/Pages 2 0 R" + catalog_extra.encode() + b">>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        (
            b"<</Type/Page/Parent 2 0 R/MediaBox"
            + media_box.encode()
            + b"/Resources<<"
            + resources.encode()
            + b">>/Contents 4 0 R"
            + page_extra.encode()
            + b">>"
        ),
        stream(content),
        font,
    ]
    objects.extend(extra_objects or [])
    return assemble(objects, trailer_extra=trailer_extra)


def many_pages(contents: list, media_box: str = "[0 0 612 792]") -> bytes:
    """A document of several pages, each with its own content stream.

    Object numbers: 1 catalog, 2 pages, then page/contents in pairs from 3, and the
    shared font last. Needed for anything about repetition, which cannot be shown
    on a single page.
    """
    count = len(contents)
    font_number = 3 + 2 * count
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(count))
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        f"<</Type/Pages/Kids[{kids}]/Count {count}>>".encode(),
    ]
    for index, body in enumerate(contents):
        objects.append(
            (
                f"<</Type/Page/Parent 2 0 R/MediaBox{media_box}"
                f"/Resources<</Font<</F1 {font_number} 0 R>>>>"
                f"/Contents {4 + 2 * index} 0 R>>"
            ).encode()
        )
        objects.append(stream(body))
    objects.append(HELVETICA)
    return assemble(objects)


def with_second_revision(base: bytes, replacements: dict) -> bytes:
    """Append an incremental update that rewrites some objects in place.

    This is how a PDF is edited without rewriting the file: the original bytes stay
    exactly where they are, and a second section at the end points past them. The
    old objects are still present and still readable.
    """
    previous_xref = int(base.rsplit(b"startxref", 1)[1].split()[0])
    out = bytearray(base)
    offsets: dict = {}
    for number, body in sorted(replacements.items()):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n"
    for number, offset in sorted(offsets.items()):
        out += b"%d 1\n" % number
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<</Size %d/Root 1 0 R/Prev %d>>\n" % (max(offsets) + 1, previous_xref)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(out)


# --- content stream pieces -------------------------------------------------


def text(what: str, x: float, y: float, size: float = 12, render_mode: int | None = None):
    """A text-showing run at an absolute position.

    The render mode is set back to 0 before the block ends. Text state is part of
    the graphics state and is *not* reset by ET, so without this every later run in
    the fixture would inherit the mode. That inheritance is real and worth checking,
    but it should be asked for deliberately: see ``raw_text``.
    """
    escaped = what.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    if render_mode is None:
        return b"BT /F1 %g Tf %g %g Td (%s) Tj ET\n" % (size, x, y, escaped.encode("latin-1"))
    return b"BT /F1 %g Tf %d Tr %g %g Td (%s) Tj 0 Tr ET\n" % (
        size,
        render_mode,
        x,
        y,
        escaped.encode("latin-1"),
    )


def leaves_render_mode(what: str, x: float, y: float, render_mode: int, size: float = 12):
    """A run that leaves the render mode set, the way a careless generator does.

    The mode is required rather than defaulted, because the whole point of this
    helper is that it changes state for everything after it.
    """
    escaped = what.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return b"BT /F1 %g Tf %d Tr %g %g Td (%s) Tj ET\n" % (
        size,
        render_mode,
        x,
        y,
        escaped.encode("latin-1"),
    )


def colored_text(what: str, x: float, y: float, rgb: tuple, size: float = 12) -> bytes:
    r, g, b = rgb
    return b"%g %g %g rg " % (r, g, b) + text(what, x, y, size)


def fill_rect(x: float, y: float, w: float, h: float, rgb: tuple = (0, 0, 0)) -> bytes:
    r, g, b = rgb
    return b"%g %g %g rg %g %g %g %g re f\n" % (r, g, b, x, y, w, h)


def stroke_rect(x: float, y: float, w: float, h: float, rgb: tuple = (0, 0, 0)) -> bytes:
    r, g, b = rgb
    return b"%g %g %g RG %g %g %g %g re S\n" % (r, g, b, x, y, w, h)


def transparent_rect(x: float, y: float, w: float, h: float, rgb: tuple = (1, 1, 0)) -> bytes:
    """A highlight: a fill that lets what is underneath show through."""
    r, g, b = rgb
    return b"/GS1 gs %g %g %g rg %g %g %g %g re f\n" % (r, g, b, x, y, w, h)


def draw_image(x: float, y: float, w: float, h: float, name: str = "Im1") -> bytes:
    return b"q %g 0 0 %g %g %g cm /%s Do Q\n" % (w, h, x, y, name.encode())


# --- reusable objects ------------------------------------------------------

TINY_IMAGE = stream(
    b"\x80",
    "/Type/XObject/Subtype/Image/Width 1/Height 1"
    "/ColorSpace/DeviceGray/BitsPerComponent 8",
)

TRANSPARENT_GSTATE = b"<</Type/ExtGState/ca 0.3>>"


def info_object(**fields) -> bytes:
    """A document properties object. Values are written as literal strings."""
    parts = []
    for key, value in fields.items():
        escaped = str(value).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        parts.append(b"/%s(%s)" % (key.encode(), escaped.encode("latin-1")))
    return b"<<" + b"".join(parts) + b">>"


def annotation(subtype: str, rect: str = "[70 670 270 690]", extra: str = "") -> bytes:
    return b"<</Type/Annot/Subtype/%s/Rect%s%s>>" % (
        subtype.encode(),
        rect.encode(),
        extra.encode(),
    )


# --- pieces for the harder cases -------------------------------------------


def clip_to(x: float, y: float, w: float, h: float) -> bytes:
    """Restrict everything painted after this to a rectangle."""
    return b"%g %g %g %g re W n\n" % (x, y, w, h)


def saved(inner: bytes) -> bytes:
    """Wrap content in a saved graphics state, the way a real generator does."""
    return b"q\n" + inner + b"Q\n"


def with_state(name: str, inner: bytes) -> bytes:
    return b"q /%s gs\n" % name.encode() + inner + b"Q\n"


MULTIPLY_STATE = b"<</Type/ExtGState/BM/Multiply>>"
SOFT_MASK_STATE = b"<</Type/ExtGState/SMask<</Type/Mask/S/Luminosity>>>>"
SEPARATION_SPACE = b"[/Separation/PANTONE#20286#20C/DeviceCMYK 7 0 R]"
TINT_TRANSFORM = b"<</FunctionType 2/Domain[0 1]/C0[0 0 0 0]/C1[1 0.7 0 0.2]/N 1>>"


def form(inner: bytes, bbox: str = "[0 0 40 40]", matrix: str = "") -> bytes:
    extra = "/Type/XObject/Subtype/Form/BBox" + bbox + "/Resources<<>>"
    if matrix:
        extra += "/Matrix" + matrix
    return stream(inner, extra)


def appearance(inner: bytes, bbox: str = "[0 0 220 16]") -> bytes:
    return stream(inner, "/Type/XObject/Subtype/Form/BBox" + bbox + "/Resources<<>>")


def type3_font(width: int = 100, scale: str = "0.01") -> bytes:
    """A Type 3 font whose widths are in its own glyph space, not thousandths."""
    widths = " ".join([str(width)] * 26)
    return (
        b"<</Type/Font/Subtype/Type3/FontMatrix[" + scale.encode() + b" 0 0 "
        + scale.encode() + b" 0 0]/FontBBox[0 0 100 100]"
        b"/CharProcs<<>>/Encoding<</Type/Encoding>>"
        b"/FirstChar 65/LastChar 90/Widths[" + widths.encode() + b"]>>"
    )


def narrow_font() -> bytes:
    """A font that declares widths for only part of the range it is used with."""
    return (
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica"
        b"/FirstChar 65/LastChar 67/Widths[667 667 722]>>"
    )


def utf16_string(text: str) -> bytes:
    """A hex string, which survives to the reader without re-encoding."""
    return b"<FEFF" + text.encode("utf-16-be").hex().upper().encode() + b">"

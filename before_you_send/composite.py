"""Composite fonts: the ones that address glyphs by number instead of by character.

A Type0 font does not use one byte per character. Its content stream carries glyph
identifiers — most often two bytes each, under the Identity-H encoding — and the
widths live on a descendant font keyed by those identifiers. Reading such a string
as though its bytes were characters produces two consequences, both bad and both
silent:

*The count is wrong.* Two bytes read as two characters doubles the length of every
run, which doubles the width of the box drawn around it. The fraction of a run
covered by a shape is measured against that box, and the fraction is what decides
whether a passage was redacted. A box twice too wide halves the coverage and drops
it under the threshold, so the finding never appears. That is a false negative on
the tool's flagship check.

*The text is wrong.* What comes back is not the document's text but its glyph
numbers reinterpreted as characters, so anything printed from it is nonsense.

This matters far more than it sounds. Traced through a 60-document sample of real
published PDFs, Type0 was the single largest reason the tool could not measure a
run: 480 font references against 61 for every other cause combined. Word,
InDesign, Chrome's print-to-PDF, LibreOffice and modern TeX all emit them, which is
to say most documents anybody would think to check before sending one.

Only Identity-H and Identity-V are handled. Any other encoding uses a CMap that maps
codes to glyphs in ways this module does not read, and a width taken against the
wrong glyph would be worse than an admitted estimate, so those keep estimating.
"""

from __future__ import annotations

import re

IDENTITY_ENCODINGS = ("/Identity-H", "/Identity-V")

_BF_CHAR = re.compile(rb"beginbfchar(.*?)endbfchar", re.DOTALL)
_BF_RANGE = re.compile(rb"beginbfrange(.*?)endbfrange", re.DOTALL)
_HEX = re.compile(rb"<([0-9A-Fa-f]+)>")
_RANGE_LINE = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>")


def is_identity(font) -> bool:
    """Whether this composite font addresses glyphs by a plain two-byte number."""
    try:
        return str(font.get("/Encoding", "")) in IDENTITY_ENCODINGS
    except Exception:
        return False


def descendant_widths(font) -> dict:
    """Widths in em units, keyed by glyph identifier.

    ``/W`` comes in two shapes, which may be mixed in one array: a start
    identifier followed by a list of widths, or a first and last identifier
    followed by one width for all of them. ``/DW`` covers everything else and
    defaults to 1000 thousandths, which the specification sets.
    """
    try:
        descendants = font.get("/DescendantFonts")
        if descendants is None:
            return {}
        descendant = descendants.get_object()[0].get_object()
    except Exception:
        return {}

    try:
        default = float(descendant.get("/DW", 1000)) / 1000.0
    except Exception:
        default = 1.0

    table: dict = {}
    try:
        array = descendant.get("/W")
        array = list(array.get_object()) if array is not None else []
    except Exception:
        array = []

    index = 0
    while index < len(array):
        try:
            first = int(array[index].get_object())
        except Exception:
            break
        if index + 1 >= len(array):
            break
        following = array[index + 1].get_object()
        if isinstance(following, list):
            for offset, width in enumerate(following):
                try:
                    table[first + offset] = float(width.get_object()) / 1000.0
                except Exception:
                    continue
            index += 2
            continue
        try:
            last = int(following)
            width = float(array[index + 2].get_object()) / 1000.0
        except Exception:
            break
        # A run of identifiers sharing one width. Bounded, because the identifier
        # space is 16 bits wide and a malformed pair could otherwise ask for
        # billions of entries.
        if 0 <= first <= last <= 0xFFFF:
            for identifier in range(first, last + 1):
                table[identifier] = width
        index += 3

    return {"default": default, "widths": table}


def to_unicode(font) -> dict:
    """A glyph identifier to text map, read from the font's /ToUnicode stream.

    Without one there is no way to say what a glyph number means, and this module
    says nothing rather than guessing. The geometry does not depend on it: widths
    are keyed by identifier, so a run is measured correctly whether or not its text
    can be recovered.
    """
    try:
        stream = font.get("/ToUnicode")
        if stream is None:
            return {}
        data = stream.get_object().get_data()
    except Exception:
        return {}

    mapping: dict = {}
    try:
        for block in _BF_CHAR.findall(data):
            pairs = _HEX.findall(block)
            for index in range(0, len(pairs) - 1, 2):
                code = int(pairs[index], 16)
                mapping[code] = _text_from_hex(pairs[index + 1])
        for block in _BF_RANGE.findall(data):
            for low, high, start in _RANGE_LINE.findall(block):
                first, last = int(low, 16), int(high, 16)
                if not (0 <= first <= last <= 0xFFFF) or last - first > 0xFFFF:
                    continue
                base = int(start, 16)
                for offset in range(last - first + 1):
                    mapping[first + offset] = _text_from_code(base + offset)
    except Exception:
        return mapping
    return mapping


def _text_from_hex(raw: bytes) -> str:
    try:
        return bytes.fromhex(raw.decode("ascii")).decode("utf-16-be", "replace")
    except Exception:
        return ""


def _text_from_code(value: int) -> str:
    try:
        return chr(value) if value < 0x110000 else ""
    except Exception:
        return ""


def codes(raw: bytes) -> list:
    """The two-byte glyph identifiers in a string operand, in order."""
    if len(raw) % 2:
        raw = raw[:-1]
    return [(raw[i] << 8) | raw[i + 1] for i in range(0, len(raw), 2)]

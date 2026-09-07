"""Walks a page's drawing instructions and records what was painted, and in what order.

Geometry alone cannot tell a covered secret from a styled heading. A black box over
black text, and white heading text on a black bar, are the same overlap. The
difference is *when* each thing was painted:

    text, then box   ->  the box was put there to hide the text
    box, then text   ->  the box is a background the text sits on

That ordering is recorded in the file itself, so the distinction is a fact rather
than a tuned threshold. Everything downstream depends on this module preserving it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Matrix = tuple  # (a, b, c, d, e, f)
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

MAX_FORM_DEPTH = 8
MAX_OPERATIONS = 400_000

INVISIBLE_RENDER_MODES = {3, 7}


def multiply(m: Matrix, n: Matrix) -> Matrix:
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def apply(m: Matrix, x: float, y: float) -> tuple:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


@dataclass(frozen=True)
class Box:
    """An axis-aligned rectangle in page space."""

    x0: float
    y0: float
    x1: float
    y1: float

    @staticmethod
    def around(points) -> Box | None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        if not xs:
            return None
        return Box(min(xs), min(ys), max(xs), max(ys))

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def overlap_area(self, other: Box) -> float:
        w = min(self.x1, other.x1) - max(self.x0, other.x0)
        h = min(self.y1, other.y1) - max(self.y0, other.y0)
        return w * h if w > 0 and h > 0 else 0.0

    def covered_by(self, other: Box) -> float:
        """How much of this box lies inside ``other``, from 0.0 to 1.0."""
        if self.area <= 0:
            return 0.0
        return self.overlap_area(other) / self.area

    def __str__(self) -> str:
        return f"({self.x0:.0f}, {self.y0:.0f})-({self.x1:.0f}, {self.y1:.0f})"


@dataclass
class TextRun:
    order: int
    text: str
    box: Box
    fill: tuple | None
    render_mode: int
    font_size: float
    alpha: float
    width_estimated: bool


@dataclass
class FilledShape:
    order: int
    box: Box
    fill: tuple | None
    alpha: float


@dataclass
class DrawnImage:
    order: int
    box: Box
    name: str


@dataclass
class PageContent:
    """Everything painted on one page, in the order it was painted."""

    text_runs: list = field(default_factory=list)
    fills: list = field(default_factory=list)
    images: list = field(default_factory=list)
    truncated: bool = False
    unreadable_reason: str | None = None
    estimated_widths: bool = False


@dataclass
class _State:
    ctm: Matrix = IDENTITY
    fill: tuple | None = (0.0, 0.0, 0.0)
    alpha: float = 1.0


def _gray(v) -> tuple:
    v = float(v)
    return (v, v, v)


def _cmyk(c, m, y, k) -> tuple:
    c, m, y, k = (float(v) for v in (c, m, y, k))
    return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))


def _colour_from(operands) -> tuple | None:
    """A colour from sc/scn operands, or None when it is not knowable.

    Patterns and separations name a colour indirectly. Guessing at one would mean
    guessing at whether a shape is opaque, so an unknown colour stays unknown.
    """
    numbers = [o for o in operands if isinstance(o, (int, float))]
    if len(numbers) != len(operands) or not numbers:
        return None
    if len(numbers) == 1:
        return _gray(numbers[0])
    if len(numbers) == 3:
        return tuple(float(v) for v in numbers)
    if len(numbers) == 4:
        return _cmyk(*numbers)
    return None


def _font_widths(font) -> tuple:
    """Glyph widths in em units for a font, and whether the font declared them.

    A font that declares no widths gets an average. That estimate is carried into
    the report rather than hidden, because it is the one number in this tool that
    is genuinely approximate.
    """
    try:
        font = font.get_object()
        if str(font.get("/Subtype", "")) == "/Type0":
            return {}, False
        widths = font.get("/Widths")
        first = font.get("/FirstChar")
        if widths is None or first is None:
            return {}, False
        widths = widths.get_object()
        first = int(first.get_object())
        table = {}
        for offset, w in enumerate(widths):
            try:
                table[first + offset] = float(w.get_object()) / 1000.0
            except Exception:
                continue
        return (table, True) if table else ({}, False)
    except Exception:
        return {}, False


def _floats(operands) -> list | None:
    """Every operand as a float, or None if any one of them is not a number.

    Operands come out of somebody else's file and are not guaranteed to be numbers.
    Coercing once here keeps the operator loop free of error handling.
    """
    try:
        return [float(v) for v in operands]
    except Exception:
        return None


def _alpha_of(extg) -> float | None:
    """The fill opacity named by an ExtGState, if it names one."""
    try:
        ca = extg.get_object().get("/ca")
        return float(ca) if ca is not None else None
    except Exception:
        return None


def _resolve(resources, category: str, name):
    try:
        group = resources.get(category)
        if group is None:
            return None
        return group.get_object().get(str(name))
    except Exception:
        return None


class _Walker:
    """A single pass over the operator stream, keeping graphics and text state."""

    def __init__(self, reader, content: PageContent):
        self.reader = reader
        self.content = content
        self.order = 0

    def next_order(self) -> int:
        self.order += 1
        return self.order

    def run(self, operations, resources, ctm: Matrix, depth: int) -> None:
        state = _State(ctm=ctm)
        stack: list = []
        path_points: list = []

        text_matrix: Matrix = IDENTITY
        line_matrix: Matrix = IDENTITY
        font_size = 0.0
        render_mode = 0
        leading = 0.0
        char_spacing = 0.0
        word_spacing = 0.0
        horizontal_scale = 1.0
        widths: dict = {}
        widths_declared = False

        for operands, operator in operations:
            if self.order > MAX_OPERATIONS:
                self.content.truncated = True
                return
            op = operator.decode("latin-1") if isinstance(operator, bytes) else str(operator)

            if op == "q":
                stack.append(_State(state.ctm, state.fill, state.alpha))
            elif op == "Q":
                if stack:
                    state = stack.pop()
            elif op == "cm" and len(operands) == 6:
                values = _floats(operands)
                if values is not None:
                    state.ctm = multiply(tuple(values), state.ctm)
            elif op == "gs":
                extg = _resolve(resources, "/ExtGState", operands[0] if operands else None)
                alpha = _alpha_of(extg) if extg is not None else None
                if alpha is not None:
                    state.alpha = alpha

            elif op == "rg" and len(operands) == 3:
                state.fill = tuple(float(v) for v in operands)
            elif op == "g" and len(operands) == 1:
                state.fill = _gray(operands[0])
            elif op == "k" and len(operands) == 4:
                state.fill = _cmyk(*operands)
            elif op in ("sc", "scn"):
                state.fill = _colour_from(operands)
            elif op == "cs":
                # Selecting a colour space resets the colour. For a pattern space
                # that colour is not a number we can reason about.
                name = str(operands[0]) if operands else ""
                state.fill = None if name == "/Pattern" else (0.0, 0.0, 0.0)

            elif op == "re" and len(operands) == 4:
                values = _floats(operands)
                if values is not None:
                    x, y, w, h = values
                    for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                        path_points.append(apply(state.ctm, px, py))
            elif op in ("m", "l") and len(operands) == 2:
                values = _floats(operands)
                if values is not None:
                    path_points.append(apply(state.ctm, values[0], values[1]))
            elif op in ("c", "v", "y"):
                values = _floats(operands)
                if values is not None:
                    for i in range(0, len(values) - 1, 2):
                        path_points.append(apply(state.ctm, values[i], values[i + 1]))

            elif op in ("f", "F", "f*", "B", "B*", "b", "b*"):
                box = Box.around(path_points)
                if box is not None and box.area > 0:
                    self.content.fills.append(
                        FilledShape(self.next_order(), box, state.fill, state.alpha)
                    )
                path_points = []
            elif op in ("S", "s", "n"):
                # A stroked outline does not hide what is beneath it.
                path_points = []

            elif op == "BT":
                text_matrix = line_matrix = IDENTITY
            elif op == "Tf" and len(operands) == 2:
                try:
                    font_size = float(operands[1])
                except Exception:
                    font_size = 0.0
                font = _resolve(resources, "/Font", operands[0])
                widths, widths_declared = _font_widths(font) if font is not None else ({}, False)
                if not widths_declared:
                    self.content.estimated_widths = True
            elif op == "Tr" and operands:
                try:
                    render_mode = int(operands[0])
                except Exception:
                    render_mode = 0
            elif op == "TL" and operands:
                leading = _number(operands[0], leading)
            elif op == "Tc" and operands:
                char_spacing = _number(operands[0], char_spacing)
            elif op == "Tw" and operands:
                word_spacing = _number(operands[0], word_spacing)
            elif op == "Tz" and operands:
                horizontal_scale = _number(operands[0], 100.0) / 100.0
            elif op == "Tm" and len(operands) == 6:
                values = _floats(operands)
                if values is not None:
                    text_matrix = line_matrix = tuple(values)
            elif op in ("Td", "TD") and len(operands) == 2:
                tx, ty = _number(operands[0], 0.0), _number(operands[1], 0.0)
                if op == "TD":
                    leading = -ty
                line_matrix = multiply((1, 0, 0, 1, tx, ty), line_matrix)
                text_matrix = line_matrix
            elif op == "T*":
                line_matrix = multiply((1, 0, 0, 1, 0, -leading), line_matrix)
                text_matrix = line_matrix

            elif op in ("Tj", "TJ", "'", '"'):
                if op in ("'", '"'):
                    line_matrix = multiply((1, 0, 0, 1, 0, -leading), line_matrix)
                    text_matrix = line_matrix
                if op == '"' and len(operands) >= 3:
                    word_spacing = _number(operands[0], word_spacing)
                    char_spacing = _number(operands[1], char_spacing)
                shown, advance = self._measure(
                    operands[-1] if operands else "",
                    widths,
                    font_size,
                    char_spacing,
                    word_spacing,
                    horizontal_scale,
                )
                if shown:
                    box = self._text_box(text_matrix, state.ctm, font_size, advance)
                    if box is not None:
                        self.content.text_runs.append(
                            TextRun(
                                order=self.next_order(),
                                text=shown,
                                box=box,
                                fill=state.fill,
                                render_mode=render_mode,
                                font_size=font_size,
                                alpha=state.alpha,
                                width_estimated=not widths_declared,
                            )
                        )
                text_matrix = multiply((1, 0, 0, 1, advance, 0), text_matrix)

            elif op == "Do" and operands:
                self._do_xobject(operands[0], resources, state.ctm, depth)
            elif op in ("INLINE IMAGE", "BI"):
                box = Box.around(
                    [apply(state.ctm, x, y) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
                )
                if box is not None and box.area > 0:
                    self.content.images.append(DrawnImage(self.next_order(), box, "inline image"))

    def _measure(self, pieces, widths, font_size, char_spacing, word_spacing, scale) -> tuple:
        """The characters shown, and how far the text position advances."""
        items = pieces if isinstance(pieces, list) else [pieces]
        shown: list = []
        advance = 0.0
        for item in items:
            if isinstance(item, (int, float)):
                advance -= float(item) / 1000.0 * font_size
                continue
            try:
                as_text = str(item)
            except Exception:
                continue
            shown.append(as_text)
            for character in as_text:
                code = ord(character)
                advance += widths.get(code, 0.5) * font_size + char_spacing
                if code == 32:
                    advance += word_spacing
        return "".join(shown), advance * scale

    def _text_box(self, text_matrix, ctm, font_size, advance) -> Box | None:
        """A run's outline, from the baseline out to rough ascender and descender."""
        if font_size <= 0:
            font_size = 1.0
        full = multiply(text_matrix, ctm)
        corners = [
            apply(full, 0.0, -0.25 * font_size),
            apply(full, advance, -0.25 * font_size),
            apply(full, advance, 0.75 * font_size),
            apply(full, 0.0, 0.75 * font_size),
        ]
        box = Box.around(corners)
        return box if box is not None and box.area > 0 else None

    def _do_xobject(self, name, resources, ctm: Matrix, depth: int) -> None:
        from pypdf.generic import ContentStream

        xobject = _resolve(resources, "/XObject", name)
        if xobject is None:
            return
        try:
            xobject = xobject.get_object()
            subtype = str(xobject.get("/Subtype", ""))
        except Exception:
            return

        if subtype == "/Image":
            box = Box.around([apply(ctm, x, y) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))])
            if box is not None and box.area > 0:
                self.content.images.append(DrawnImage(self.next_order(), box, str(name)))
            return

        if subtype != "/Form" or depth >= MAX_FORM_DEPTH:
            return
        try:
            inner_ctm = ctm
            matrix = xobject.get("/Matrix")
            if matrix is not None:
                inner_ctm = multiply(
                    tuple(float(v.get_object()) for v in matrix.get_object()), ctm
                )
            inner_resources = xobject.get("/Resources")
            inner_resources = (
                inner_resources.get_object() if inner_resources is not None else resources
            )
            self.run(ContentStream(xobject, self.reader).operations, inner_resources,
                     inner_ctm, depth + 1)
        except Exception:
            return


def _number(value, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def read_page(reader, page) -> PageContent:
    """Interpret one page's drawing instructions, degrading to a stated reason."""
    from pypdf.generic import ContentStream

    content = PageContent()
    try:
        contents = page.get("/Contents")
        if contents is None:
            return content
        stream = ContentStream(contents, reader)
        resources = page.get("/Resources")
        resources = resources.get_object() if resources is not None else {}
        _Walker(reader, content).run(stream.operations, resources, IDENTITY, 0)
    except Exception as error:
        content.unreadable_reason = (
            f"the page's drawing instructions could not be read ({type(error).__name__})"
        )
    return content

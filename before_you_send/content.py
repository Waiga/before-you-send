"""Walks a page's drawing instructions and records what was painted, and in what order.

Geometry alone cannot tell a covered secret from a styled heading. A black box over
black text, and white heading text on a black bar, are the same overlap. The
difference is *when* each thing was painted:

    text, then box   ->  the box was put there to hide the text
    box, then text   ->  the box is a background the text sits on

Order is not enough on its own, because a shape is not painted everywhere its path
reaches. Three things bound it, and all three are modelled here:

    a clipping path      set by W, trims everything painted after it
    a form's /BBox       a hard boundary on everything that form draws
    blending and masks   a shape that lets what is underneath show through

Get any of those wrong and an ordinary chart, logo or highlighter mark is reported as
a redaction. So the extent of a fill matters exactly as much as the order of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Matrix = tuple  # (a, b, c, d, e, f)
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

MAX_FORM_DEPTH = 8

# Budgets. These count *every* operator and *every* form invocation, not only the
# ones that paint something. A few forms that call each other can otherwise describe
# billions of nodes in under a kilobyte, and a budget spent only on painted output
# never notices.
MAX_OPERATIONS = 2_000_000
MAX_FORM_INVOCATIONS = 20_000

INVISIBLE_RENDER_MODES = {3, 7}

# Text smaller than this on the page cannot be read at any zoom.
MIN_READABLE_FONT_SIZE = 0.5

# Colour spaces where the operands of sc/scn are a tint or an index, not a colour.
INDIRECT_COLOUR_SPACES = {"/Separation", "/DeviceN", "/Indexed", "/Pattern"}
DEVICE_COLOUR_SPACES = {
    "/DeviceRGB",
    "/DeviceGray",
    "/DeviceCMYK",
    "/CalRGB",
    "/CalGray",
    "/ICCBased",
    "/Lab",
}


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

    def holds(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def intersect(self, other: Box | None) -> Box | None:
        """The part of this box inside ``other``, or None if they do not meet.

        An ``other`` of None means unbounded, which is what an unset clip is.
        """
        if other is None:
            return self
        box = Box(
            max(self.x0, other.x0),
            max(self.y0, other.y0),
            min(self.x1, other.x1),
            min(self.y1, other.y1),
        )
        return box if box.area > 0 else None

    def __str__(self) -> str:
        return f"({self.x0:.0f}, {self.y0:.0f})-({self.x1:.0f}, {self.y1:.0f})"


# A clip that admits nothing.
#
# ``None`` as a clip means unbounded, and ``Box.intersect`` returns ``None`` when two
# boxes do not meet. Those two meanings collide: an empty clip written back as
# ``None`` turns "nothing may be drawn" into "everything may be drawn", which is the
# wrong direction — it drops an enclosing clip and lets a shape cover text it should
# have been trimmed away from. A degenerate rectangle carries the empty meaning
# unambiguously, because intersecting anything with it is empty in turn.
EMPTY_CLIP = Box(0.0, 0.0, 0.0, 0.0)


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
    clipped_away: bool = False
    too_small_to_read: bool = False


@dataclass
class FilledShape:
    order: int
    box: Box
    fill: tuple | None
    alpha: float
    see_through: bool = False
    # The annotation subtype this shape was painted by, when it came from an
    # annotation's appearance rather than from the page itself. A redaction mark and
    # a highlight are drawn over the text they refer to *by definition*, so the fact
    # that they sit on top of it is not evidence of anything and belongs to the check
    # that owns them.
    annotation: str | None = None

    @property
    def conceals(self) -> bool:
        """Whether this shape can be relied on to hide what it covers."""
        return self.fill is not None and self.alpha >= 0.9 and not self.see_through

    @property
    def opacity_unknown(self) -> bool:
        """Covers something, and we cannot say whether it conceals it."""
        return self.fill is None and self.alpha >= 0.9 and not self.see_through


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
    see_through: bool = False
    clip: Box | None = None
    direct_colour: bool = True

    def copy(self) -> _State:
        return _State(
            self.ctm, self.fill, self.alpha, self.see_through, self.clip, self.direct_colour
        )


def _gray(v) -> tuple:
    v = float(v)
    return (v, v, v)


def _cmyk(c, m, y, k) -> tuple:
    c, m, y, k = (float(v) for v in (c, m, y, k))
    return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))


def _floats(operands) -> list | None:
    """Every operand as a float, or None if any one of them is not a number.

    Operands come out of somebody else's file and are not guaranteed to be numbers.
    Coercing once here keeps the operator loop free of error handling.
    """
    try:
        return [float(v) for v in operands]
    except Exception:
        return None


def _colour_from(operands) -> tuple | None:
    """A colour from sc/scn operands in a device space, or None if not knowable."""
    numbers = _floats(operands)
    if not numbers:
        return None
    if len(numbers) == 1:
        return _gray(numbers[0])
    if len(numbers) == 3:
        return tuple(numbers)
    if len(numbers) == 4:
        return _cmyk(*numbers)
    return None


def _space_is_direct(space) -> bool:
    """Whether numbers in this colour space are the colour, or only stand for one.

    In a Separation or DeviceN space, ``1`` means full ink of some named colourant,
    which can be any colour at all. Reading it as grey 1.0 turns a solid dark bar
    into a white one and inverts every verdict that depends on it. When a space does
    not name the colour directly, the colour is unknown, and unknown is recorded.
    """
    try:
        space = space.get_object()
    except Exception:
        return False
    name = str(space)
    if name in DEVICE_COLOUR_SPACES:
        return True
    if name in INDIRECT_COLOUR_SPACES:
        return False
    try:
        first = str(space[0])
    except Exception:
        return False
    return first in DEVICE_COLOUR_SPACES


def _extgstate(extg) -> tuple:
    """Fill opacity, and whether this state makes a shape see-through.

    ``/ca`` is only one of three ways a shape stops concealing what is under it. A
    blend mode other than Normal composites with what is behind, which is exactly
    how a flattened highlighter mark is drawn, and a soft mask fades it. Reading
    only ``/ca`` reports every highlight in a document as a redaction.
    """
    alpha = None
    see_through = False
    try:
        extg = extg.get_object()
    except Exception:
        return None, False
    try:
        ca = extg.get("/ca")
        if ca is not None:
            alpha = float(ca)
    except Exception:
        pass
    try:
        blend = extg.get("/BM")
        if blend is not None:
            names = [str(b) for b in blend] if isinstance(blend, list) else [str(blend)]
            if any(n not in ("/Normal", "/Compatible") for n in names):
                see_through = True
    except Exception:
        pass
    try:
        smask = extg.get("/SMask")
        if smask is not None and str(smask) != "/None":
            see_through = True
    except Exception:
        pass
    return alpha, see_through


def _font_widths(font) -> tuple:
    """Glyph widths in em units, and whether the font declared them.

    Widths are normally thousandths of an em, but a Type 3 font measures them in its
    own glyph space and supplies a /FontMatrix to convert. Dividing those by 1000
    regardless is out by whatever that matrix says, which for a typical bitmap font
    is a factor of ten.
    """
    try:
        font = font.get_object()
        if str(font.get("/Subtype", "")) == "/Type0":
            return {}, False
        widths = font.get("/Widths")
        first = font.get("/FirstChar")
        if widths is None or first is None:
            return {}, False

        scale = 1 / 1000.0
        matrix = font.get("/FontMatrix")
        if matrix is not None:
            try:
                scale = float(matrix.get_object()[0].get_object())
            except Exception:
                scale = 1 / 1000.0

        widths = widths.get_object()
        first = int(first.get_object())
        table = {}
        for offset, w in enumerate(widths):
            try:
                table[first + offset] = float(w.get_object()) * scale
            except Exception:
                continue
        return (table, True) if table else ({}, False)
    except Exception:
        return {}, False


def _resolve(resources, category: str, name):
    try:
        group = resources.get(category)
        if group is None:
            return None
        return group.get_object().get(str(name))
    except Exception:
        return None


class _Budget:
    """Shared across nested forms, so recursion cannot get around it."""

    def __init__(self):
        self.operations = 0
        self.form_invocations = 0
        self.exhausted = False

    def spend_operation(self) -> bool:
        self.operations += 1
        if self.operations > MAX_OPERATIONS:
            self.exhausted = True
        return not self.exhausted

    def spend_form(self) -> bool:
        self.form_invocations += 1
        if self.form_invocations > MAX_FORM_INVOCATIONS:
            self.exhausted = True
        return not self.exhausted


class _Walker:
    """A single pass over the operator stream, keeping graphics and text state."""

    def __init__(self, reader, content: PageContent):
        self.reader = reader
        self.content = content
        self.order = 0
        self.budget = _Budget()
        self.annotation: str | None = None

    def next_order(self) -> int:
        self.order += 1
        return self.order

    def run(
        self,
        operations,
        resources,
        ctm: Matrix,
        depth: int,
        clip: Box | None,
        inherited: _State | None = None,
    ) -> None:
        """Interpret one content stream.

        A form XObject inherits the whole graphics state of whoever invoked it, not
        just the transform and the clip. Producers rely on that: Illustrator,
        InDesign, Acrobat's flattener and Ghostscript all set the blend mode or the
        alpha *outside* the form and then invoke it, so a watermark or a highlighter
        mark reads as fully opaque black paint if the form starts from defaults.
        That turns ordinary design into the tool's loudest finding, which is the
        worst possible place to be wrong.
        """
        state = _State(ctm=ctm, clip=clip)
        if inherited is not None:
            state.fill = inherited.fill
            state.alpha = inherited.alpha
            state.see_through = inherited.see_through
            state.direct_colour = inherited.direct_colour
        stack: list = []
        path_points: list = []
        pending_clip = False

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
            if not self.budget.spend_operation():
                self.content.truncated = True
                return
            op = operator.decode("latin-1") if isinstance(operator, bytes) else str(operator)

            if op == "q":
                stack.append(state.copy())
            elif op == "Q":
                if stack:
                    state = stack.pop()
            elif op == "cm" and len(operands) == 6:
                values = _floats(operands)
                if values is not None:
                    state.ctm = multiply(tuple(values), state.ctm)
            elif op == "gs":
                extg = _resolve(resources, "/ExtGState", operands[0] if operands else None)
                if extg is not None:
                    alpha, see_through = _extgstate(extg)
                    if alpha is not None:
                        state.alpha = alpha
                    if see_through:
                        state.see_through = True

            elif op == "rg" and len(operands) == 3:
                values = _floats(operands)
                state.fill = tuple(values) if values else None
                state.direct_colour = True
            elif op == "g" and len(operands) == 1:
                state.fill, state.direct_colour = _gray(operands[0]), True
            elif op == "k" and len(operands) == 4:
                state.fill, state.direct_colour = _cmyk(*operands), True
            elif op in ("sc", "scn"):
                state.fill = _colour_from(operands) if state.direct_colour else None
            elif op == "cs":
                space = _resolve(resources, "/ColorSpace", operands[0] if operands else None)
                if space is None:
                    state.direct_colour = (str(operands[0]) if operands else "") in (
                        DEVICE_COLOUR_SPACES
                    )
                else:
                    state.direct_colour = _space_is_direct(space)
                state.fill = (0.0, 0.0, 0.0) if state.direct_colour else None

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
            elif op in ("W", "W*"):
                pending_clip = True

            elif op in ("f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "n"):
                path_box = Box.around(path_points)
                # A stroke draws an outline. It does not hide what is inside it.
                if op not in ("S", "s", "n") and path_box is not None:
                    visible = path_box.intersect(state.clip)
                    if visible is not None:
                        self.content.fills.append(
                            FilledShape(
                                self.next_order(),
                                visible,
                                state.fill,
                                state.alpha,
                                state.see_through,
                                self.annotation,
                            )
                        )
                if pending_clip:
                    # A clip path that bounds nothing — a zero-size rectangle, or a
                    # path of a single point — admits nothing, and must not be
                    # written back as the unbounded clip.
                    narrowed = path_box.intersect(state.clip) if path_box else None
                    state.clip = narrowed if narrowed is not None else EMPTY_CLIP
                    pending_clip = False
                path_points = []

            elif op == "BT":
                text_matrix = line_matrix = IDENTITY
            elif op == "Tf" and len(operands) == 2:
                font_size = _number(operands[1], 0.0)
                font = _resolve(resources, "/Font", operands[0])
                widths, widths_declared = _font_widths(font) if font is not None else ({}, False)
            elif op == "Tr" and operands:
                render_mode = int(_number(operands[0], 0.0))
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
                shown, advance, guessed = self._measure(
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
                        estimated = guessed or not widths_declared
                        if estimated:
                            self.content.estimated_widths = True
                        self.content.text_runs.append(
                            TextRun(
                                order=self.next_order(),
                                text=shown,
                                box=box,
                                fill=state.fill,
                                render_mode=render_mode,
                                font_size=font_size,
                                alpha=state.alpha,
                                width_estimated=estimated,
                                clipped_away=box.intersect(state.clip) is None,
                                too_small_to_read=(
                                    self._on_page_size(text_matrix, state.ctm, font_size)
                                    < MIN_READABLE_FONT_SIZE
                                ),
                            )
                        )
                text_matrix = multiply((1, 0, 0, 1, advance, 0), text_matrix)

            elif op == "Do" and operands:
                self._do_xobject(operands[0], resources, state, depth)
            elif op in ("INLINE IMAGE", "BI"):
                box = Box.around(
                    [apply(state.ctm, x, y) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
                )
                visible = box.intersect(state.clip) if box else None
                if visible is not None:
                    self.content.images.append(
                        DrawnImage(self.next_order(), visible, "inline image")
                    )

    def _measure(self, pieces, widths, font_size, char_spacing, word_spacing, scale) -> tuple:
        """The characters shown, how far the position advances, and whether we guessed.

        A font can declare widths and still not cover every code used with it. When
        that happens the fallback is the same average as an undeclared font, and the
        report has to say so rather than present the result as measured.
        """
        items = pieces if isinstance(pieces, list) else [pieces]
        shown: list = []
        advance = 0.0
        guessed = False
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
                if code in widths:
                    advance += widths[code] * font_size
                else:
                    advance += 0.5 * font_size
                    guessed = True
                advance += char_spacing
                if code == 32:
                    advance += word_spacing
        return "".join(shown), advance * scale, guessed

    def _on_page_size(self, text_matrix, ctm, font_size) -> float:
        """How tall one em ends up on the page, after every transform."""
        full = multiply(text_matrix, ctm)
        x0, y0 = apply(full, 0.0, 0.0)
        x1, y1 = apply(full, 0.0, font_size)
        return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5

    def _text_box(self, text_matrix, ctm, font_size, advance) -> Box | None:
        """A run's outline, from the baseline out to rough ascender and descender."""
        height = font_size if font_size > 0 else 1.0
        full = multiply(text_matrix, ctm)
        corners = [
            apply(full, 0.0, -0.25 * height),
            apply(full, advance, -0.25 * height),
            apply(full, advance, 0.75 * height),
            apply(full, 0.0, 0.75 * height),
        ]
        box = Box.around(corners)
        return box if box is not None and box.area > 0 else None

    def _do_xobject(self, name, resources, state: _State, depth: int) -> None:
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
            box = Box.around(
                [apply(state.ctm, x, y) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
            )
            visible = box.intersect(state.clip) if box else None
            if visible is not None:
                self.content.images.append(DrawnImage(self.next_order(), visible, str(name)))
            return

        if subtype != "/Form" or depth >= MAX_FORM_DEPTH:
            return
        if not self.budget.spend_form():
            self.content.truncated = True
            return
        try:
            inner_ctm = state.ctm
            matrix = xobject.get("/Matrix")
            if matrix is not None:
                values = _floats([v.get_object() for v in matrix.get_object()])
                if values is not None and len(values) == 6:
                    inner_ctm = multiply(tuple(values), state.ctm)

            # A form's /BBox is a hard boundary on everything it draws. Without it, a
            # small stamp whose internal path is larger reads as covering the page.
            inner_clip = state.clip
            bbox = xobject.get("/BBox")
            if bbox is not None:
                values = _floats([v.get_object() for v in bbox.get_object()])
                if values is not None and len(values) == 4:
                    x0, y0, x1, y1 = values
                    around = Box.around(
                        [
                            apply(inner_ctm, px, py)
                            for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
                        ]
                    )
                    if around is not None:
                        inner_clip = around.intersect(state.clip)
                        if inner_clip is None:
                            return  # the form draws entirely outside the visible area

            inner_resources = xobject.get("/Resources")
            inner_resources = (
                inner_resources.get_object() if inner_resources is not None else resources
            )
            self.run(
                ContentStream(xobject, self.reader).operations,
                inner_resources,
                inner_ctm,
                depth + 1,
                inner_clip,
                inherited=state,
            )
        except Exception:
            return


def _number(value, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


# Annotation flags: an annotation with either of these set paints nothing.
_ANNOT_HIDDEN = 1 << 1
_ANNOT_NOVIEW = 1 << 5


def _appearance_of(annot):
    """The normal appearance stream an annotation actually draws, if it has one."""
    try:
        appearance = annot.get("/AP")
        if appearance is None:
            return None
        normal = appearance.get_object().get("/N")
        if normal is None:
            return None
        normal = normal.get_object()
        # A sub-dictionary of states (a checkbox, say) selects one through /AS.
        if "/BBox" not in normal:
            state = annot.get("/AS")
            if state is None:
                return None
            normal = normal.get(str(state))
            normal = normal.get_object() if normal is not None else None
        return normal
    except Exception:
        return None


def _appearance_matrix(appearance, rect) -> Matrix | None:
    """The transform that puts an appearance stream inside the annotation's rectangle.

    The stream draws in its own coordinates. The viewer maps its bounding box, after
    the stream's own /Matrix, onto the annotation's rectangle on the page.
    """
    try:
        bbox = _floats([v.get_object() for v in appearance["/BBox"].get_object()])
        if bbox is None or len(bbox) != 4:
            return None
        matrix = IDENTITY
        declared = appearance.get("/Matrix")
        if declared is not None:
            values = _floats([v.get_object() for v in declared.get_object()])
            if values is not None and len(values) == 6:
                matrix = tuple(values)

        x0, y0, x1, y1 = bbox
        transformed = Box.around(
            [apply(matrix, px, py) for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        )
        rect = _floats([v.get_object() for v in rect])
        if transformed is None or rect is None or len(rect) != 4:
            return None
        rx0, ry0, rx1, ry1 = min(rect[0], rect[2]), min(rect[1], rect[3]), \
            max(rect[0], rect[2]), max(rect[1], rect[3])

        width = transformed.x1 - transformed.x0
        height = transformed.y1 - transformed.y0
        sx = (rx1 - rx0) / width if width > 0 else 1.0
        sy = (ry1 - ry0) / height if height > 0 else 1.0
        placement = (sx, 0.0, 0.0, sy, rx0 - transformed.x0 * sx, ry0 - transformed.y0 * sy)
        return multiply(matrix, placement)
    except Exception:
        return None


def _walk_annotations(reader, page, walker) -> None:
    """Walk what each annotation paints, on top of the page's own content.

    Markup tools do not edit the page. They add an annotation whose appearance
    stream is drawn over it, so a filled black square dropped on a name by a review
    tool never touches the content stream at all. Ignoring these means the most
    common way people try to obscure something is the one way this tool cannot see.
    """
    from pypdf.generic import ContentStream

    try:
        annots = page.get("/Annots")
        if annots is None:
            return
        annots = annots.get_object()
    except Exception:
        return

    for entry in annots:
        try:
            annot = entry.get_object()
            flags = int(annot.get("/F", 0))
            if flags & (_ANNOT_HIDDEN | _ANNOT_NOVIEW):
                continue
            appearance = _appearance_of(annot)
            rect = annot.get("/Rect")
            if appearance is None or rect is None:
                continue
            placement = _appearance_matrix(appearance, rect.get_object())
            if placement is None:
                continue
            bbox = _floats([v.get_object() for v in appearance["/BBox"].get_object()])
            clip = None
            if bbox is not None and len(bbox) == 4:
                x0, y0, x1, y1 = bbox
                clip = Box.around(
                    [
                        apply(placement, px, py)
                        for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
                    ]
                )
            resources = appearance.get("/Resources")
            resources = resources.get_object() if resources is not None else {}
            walker.annotation = str(annot.get("/Subtype", "")) or None
            try:
                walker.run(
                    ContentStream(appearance, reader).operations, resources, placement, 1, clip
                )
            finally:
                walker.annotation = None
        except Exception:
            walker.annotation = None
            continue


def read_page(reader, page) -> PageContent:
    """Interpret one page's drawing instructions, degrading to a stated reason."""
    from pypdf.generic import ContentStream

    content = PageContent()
    try:
        resources = page.get("/Resources")
        resources = resources.get_object() if resources is not None else {}
        walker = _Walker(reader, content)
        contents = page.get("/Contents")
        if contents is not None:
            stream = ContentStream(contents, reader)
            walker.run(stream.operations, resources, IDENTITY, 0, None)
        # Annotations paint after the page, so they keep walking the same counter.
        _walk_annotations(reader, page, walker)
    except Exception as error:
        content.unreadable_reason = (
            f"the page's drawing instructions could not be read ({type(error).__name__})"
        )
    return content

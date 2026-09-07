"""What is on the page but cannot be seen, and what is there that we cannot see under.

This is where the tool earns or loses its credibility. Every check here has a
plausible innocent twin, and the job is to separate them with a fact from the file
rather than a tuned number:

    covered text            twin: a heading on a dark bar      separated by paint order
    text matching its
    background              twin: white text on a dark bar     separated by the bar's colour
    text off the page       twin: content bleeding off an edge separated by needing zero overlap
    an image over text      twin: a logo beside a paragraph    not separated, and so not a finding
"""

from __future__ import annotations

from before_you_send.content import INVISIBLE_RENDER_MODES, Box
from before_you_send.findings import Finding, Level

# How much of a run must be under later paint before it counts as covered. Text that
# merely clips the edge of a box is the normal result of two elements sitting close
# together, and is not evidence of anything.
COVER_THRESHOLD = 0.6

# Below this, a fill lets what is under it show through, so it hides nothing.
OPAQUE_ALPHA = 0.9

# How close two colours must be before text is unreadable against its background.
COLOUR_TOLERANCE = 0.08

WHITE = (1.0, 1.0, 1.0)


def _opaque(shape) -> bool:
    return shape.fill is not None and shape.alpha >= OPAQUE_ALPHA


def _close(a, b, tolerance: float = COLOUR_TOLERANCE) -> bool:
    if a is None or b is None:
        return False
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


def _union_area(boxes) -> float:
    """Area covered by one or more rectangles, counting overlaps once."""
    boxes = [b for b in boxes if b.area > 0]
    if not boxes:
        return 0.0
    if len(boxes) == 1:
        return boxes[0].area
    xs = sorted({b.x0 for b in boxes} | {b.x1 for b in boxes})
    ys = sorted({b.y0 for b in boxes} | {b.y1 for b in boxes})
    total = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(b.x0 <= cx <= b.x1 and b.y0 <= cy <= b.y1 for b in boxes):
                total += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return total


def _clip(inner: Box, outer: Box) -> Box:
    return Box(
        max(inner.x0, outer.x0),
        max(inner.y0, outer.y0),
        min(inner.x1, outer.x1),
        min(inner.y1, outer.y1),
    )


def covered_text(report, page_label: str, content, page_box) -> None:
    """Text that something opaque was painted over afterwards.

    This is the failure everyone has heard of and most people believe they are safe
    from: a black rectangle drawn on top of a name. The text was never removed. Any
    reader can select it, copy it, or extract it in one command.
    """
    if not content.text_runs or not content.fills:
        return

    for run in content.text_runs:
        if run.render_mode in INVISIBLE_RENDER_MODES:
            continue  # reported by invisible_text, and reporting it twice helps nobody
        later = [
            _clip(shape.box, run.box)
            for shape in content.fills
            if shape.order > run.order and _opaque(shape) and run.box.overlap_area(shape.box) > 0
        ]
        if not later:
            continue
        coverage = _union_area(later) / run.box.area if run.box.area else 0.0
        if coverage < COVER_THRESHOLD:
            continue

        about = "about " if run.width_estimated else ""
        report.add(
            Finding(
                check="covered_text",
                level=Level.HIGH,
                page=page_label,
                location=str(run.box),
                summary=(
                    f"{len(run.text)} characters of text have an opaque shape painted "
                    f"over them, covering {about}{coverage:.0%} of the run."
                ),
                detail=(
                    "The shape was painted after the text, which is what a redaction "
                    "looks like and is not what a background looks like. Covering text "
                    "does not remove it: the characters are still in the file and can "
                    "be selected, copied or extracted. To remove text you have to "
                    "delete it, not draw over it."
                ),
                sample=run.text,
            )
        )


def invisible_text(report, page_label: str, content, page_box) -> None:
    """Text drawn in a mode that paints nothing at all.

    Mode 3 renders no glyphs. It is how a scanner stores the OCR layer beneath a
    page image, which is legitimate, and it is also how text survives being
    "removed" by a tool that only stopped drawing it.
    """
    for run in content.text_runs:
        if run.render_mode not in INVISIBLE_RENDER_MODES:
            continue
        report.add(
            Finding(
                check="invisible_text",
                level=Level.HIGH,
                page=page_label,
                location=str(run.box),
                summary=(
                    f"{len(run.text)} characters are set to render mode "
                    f"{run.render_mode}, which draws nothing on the page."
                ),
                detail=(
                    "Nothing appears here when the page is viewed or printed, but the "
                    "characters are present in the file and extract normally. This is "
                    "expected under a scanned page, where it is the searchable text "
                    "layer. Anywhere else it is content someone can read and nobody "
                    "can see."
                ),
                sample=run.text,
            )
        )


def text_matching_background(report, page_label: str, content, page_box) -> None:
    """Text the same colour as whatever is behind it.

    White on white is the oldest trick in the format. The check has to be careful:
    white text on a dark bar is ordinary design, and the only thing separating the
    two cases is the colour of what was painted underneath first.
    """
    for run in content.text_runs:
        if run.fill is None or run.render_mode in INVISIBLE_RENDER_MODES:
            continue

        beneath = [
            shape
            for shape in content.fills
            if shape.order < run.order
            and _opaque(shape)
            and run.box.covered_by(shape.box) >= COVER_THRESHOLD
        ]
        background = beneath[-1].fill if beneath else WHITE
        where = "the shape painted behind it" if beneath else "the page itself"

        if not _close(run.fill, background):
            continue

        report.add(
            Finding(
                check="text_matching_background",
                level=Level.HIGH,
                page=page_label,
                location=str(run.box),
                summary=(
                    f"{len(run.text)} characters are drawn in the same colour as "
                    f"{where}, so nothing appears there."
                ),
                detail=(
                    "The text is present, extractable and selectable. Anyone who "
                    "selects the region, or runs any text extraction tool, gets it "
                    "back. Colour is not concealment."
                ),
                sample=run.text,
            )
        )


def text_outside_page(report, page_label: str, content, page_box) -> None:
    """Text positioned entirely off the visible page.

    Content that merely bleeds over an edge is normal in anything designed for print,
    so this only fires when a run does not touch the page area at all.
    """
    if page_box is None:
        return
    for run in content.text_runs:
        if run.box.overlap_area(page_box) > 0:
            continue
        report.add(
            Finding(
                check="text_outside_page",
                level=Level.MEDIUM,
                page=page_label,
                location=str(run.box),
                summary=(
                    f"{len(run.text)} characters sit entirely outside the visible "
                    "page area."
                ),
                detail=(
                    "Nothing is displayed or printed from here, but the text is in the "
                    "file and extracts normally. This is usually a draft line, an "
                    "internal note, or an element moved aside rather than deleted."
                ),
                sample=run.text,
            )
        )


def image_over_text(report, page_label: str, content, page_box) -> None:
    """An image painted over text: the one place this tool must admit it is blind.

    Everything else here works by reading instructions. An image is pixels. The tool
    can prove something was drawn on top of text and cannot read what the picture
    shows, so this is recorded as a blind spot and never as a finding. A tool that
    reported "no problems" on a page like this would be actively dangerous.
    """
    if not content.images or not content.text_runs:
        return
    for image in content.images:
        under = [
            run
            for run in content.text_runs
            if run.order < image.order and run.box.covered_by(image.box) >= COVER_THRESHOLD
        ]
        if not under:
            continue
        report.note_blindspot(
            page=page_label,
            location=str(image.box),
            reason=(
                f"an image was painted over {len(under)} run(s) of text. Whether the "
                "image hides that text, or is simply drawn across it, cannot be "
                "decided without looking at the picture, which this tool does not do."
            ),
        )

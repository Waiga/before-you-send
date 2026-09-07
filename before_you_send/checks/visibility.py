"""What is on the page but cannot be seen, and what is there that we cannot see under.

This is where the tool earns or loses its credibility. Every check here has a
plausible innocent twin, and the job is to separate them with a fact from the file
rather than a tuned number:

    covered text        twin: a heading on a dark bar     separated by paint order
    text the colour of
    its background      twin: white text on a dark bar    separated by the bar's colour
    text off the page   twin: content bleeding off an edge separated by needing zero overlap
    invisible text      twin: the text layer of a scan    separated by the page image
    an image over text  twin: a logo beside a paragraph   not separated, so not a finding

Where a twin cannot be separated at all, the case belongs in the blind spots and not
in the findings.
"""

from __future__ import annotations

from before_you_send.content import INVISIBLE_RENDER_MODES
from before_you_send.findings import Finding, Level

# Annotations that are drawn over the text they refer to as a matter of definition.
# A redaction mark sits on the passage it marks; a highlight sits on the words it
# highlights. Their overlap with text is what they are, not evidence that somebody
# concealed something, and the redaction marks already have a check of their own.
# Reported here as well, a FOIA release with forty pending redactions produces one
# correct finding and forty duplicates of it.
MARKUP_ANNOTATIONS = frozenset(
    {"/Redact", "/Highlight", "/Underline", "/StrikeOut", "/Squiggly", "/Widget"}
)

# How much of a run must be under later paint before it counts as covered. Text that
# merely clips the edge of a box is the normal result of two elements sitting close
# together, and is not evidence of anything.
COVER_THRESHOLD = 0.6

# How close two colours must be before text is unreadable against its background.
COLOUR_TOLERANCE = 0.08

# An image this much of the page is a scanned sheet, not an illustration.
PAGE_IMAGE_SHARE = 0.5

# Coverage is worked out from at most this many shapes. Beyond it the answer becomes
# a lower bound, which under-reports rather than over-reports. Anything with hundreds
# of separate opaque shapes over one line is a halftone or a chart, not a redaction.
MAX_SHAPES_CONSIDERED = 40

WHITE = (1.0, 1.0, 1.0)

# A run this short is not judged at all. One or two characters cannot carry a name,
# a number of consequence, or a word, and nobody conceals a secret by covering a
# single glyph. What they are, overwhelmingly, is drawing: a plot marker painted
# across an axis label, a table rule crossing a letter, a maths glyph set in its own
# tiny text object. Measured over 450 real published PDFs, single and double character
# runs were 57% of every covered_text finding, 70% of every clipped one, and 100% of
# every "too small to read" one — all of them false. This is a deliberate blindness
# and it is stated in the report, because a threshold that is not disclosed is just
# an undocumented bug.
MIN_RUN_CHARS = 3


def _too_short(report, run) -> bool:
    """True when a run is too short to be worth judging. Counted, never silent."""
    if len(run.text.strip()) >= MIN_RUN_CHARS:
        return False
    report.note_short_run()
    return True


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
    if len(boxes) > MAX_SHAPES_CONSIDERED:
        boxes = sorted(boxes, key=lambda b: -b.area)[:MAX_SHAPES_CONSIDERED]
    xs = sorted({b.x0 for b in boxes} | {b.x1 for b in boxes})
    ys = sorted({b.y0 for b in boxes} | {b.y1 for b in boxes})
    total = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(b.holds(cx, cy) for b in boxes):
                total += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return total


def _start_point(run) -> tuple:
    """A point just inside the beginning of a run.

    Whether something is *behind* text is decided here rather than by area overlap,
    because the width of a run is estimated for any font that declares no widths.
    A bar sized snugly to real ink does not contain an over-wide estimated box, and
    judging by area would report the bar as absent and the text as invisible.
    """
    return (run.box.x0 + 0.5, (run.box.y0 + run.box.y1) / 2)


def picture_share(content, page_box) -> float:
    """How much of the page is covered by pictures, counting overlaps once."""
    if page_box is None or page_box.area <= 0 or not content.images:
        return 0.0
    inside = [i.box.intersect(page_box) for i in content.images]
    covered = _union_area([b for b in inside if b is not None])
    return min(1.0, covered / page_box.area)


def _page_images(content, page_box) -> list:
    """The images that together make up a scanned sheet, if this page is one.

    A scan is not always one picture. Fax-derived pipelines, MFP firmware and
    anything built from TIFF strips store a page as a stack of horizontal bands,
    and mixed-raster and JBIG2 encoders split it into layers where no single
    piece reaches half the page. Asking whether *one* image covers the page
    answers "no" for all of them, and the searchable text layer underneath then
    reports as dozens of separate high findings — the exact outcome this guard
    was written to prevent, on the exact documents most likely to be scanned.

    So the question is asked of the pictures together, not one at a time.
    """
    if picture_share(content, page_box) < PAGE_IMAGE_SHARE:
        return []
    return list(content.images)


def covered_text(report, page_label: str, content, page_box) -> None:
    """Text that something opaque was painted over afterwards.

    This is the failure everyone has heard of and most people believe they are safe
    from: a black rectangle drawn on top of a name. The text was never removed. Any
    reader can select it, copy it, or extract it in one command.
    """
    if not content.text_runs or not content.fills:
        return

    for run in content.text_runs:
        if run.render_mode in INVISIBLE_RENDER_MODES or run.clipped_away:
            continue  # already reported by another check; saying it twice helps nobody
        if _too_short(report, run):
            continue

        later = [
            s
            for s in content.fills
            if s.order > run.order and s.annotation not in MARKUP_ANNOTATIONS
        ]
        covering = [
            run.box.intersect(s.box) for s in later if s.conceals and run.box.overlap_area(s.box)
        ]
        covering = [box for box in covering if box is not None]

        if covering:
            coverage = _union_area(covering) / run.box.area if run.box.area else 0.0
            if coverage >= COVER_THRESHOLD:
                about = "about " if run.width_estimated else ""
                report.add(
                    Finding(
                        check="covered_text",
                        level=Level.HIGH,
                        page=page_label,
                        location=str(run.box),
                        summary=(
                            f"{len(run.text)} characters of text have an opaque shape "
                            f"painted over them, covering {about}{coverage:.0%} of the run."
                        ),
                        detail=(
                            "The shape was painted after the text, which is what a "
                            "redaction looks like and is not what a background looks "
                            "like. Covering text does not remove it: the characters are "
                            "still in the file and can be selected, copied or extracted. "
                            "To remove text you have to delete it, not draw over it."
                        ),
                        sample=run.text,
                    )
                )
                continue

        # A shape whose colour is named indirectly may or may not conceal. Saying
        # nothing about it would be the same mistake as calling it a redaction.
        unknown = [
            run.box.intersect(s.box)
            for s in later
            if s.opacity_unknown and run.box.overlap_area(s.box)
        ]
        unknown = [box for box in unknown if box is not None]
        if unknown and _union_area(unknown) / run.box.area >= COVER_THRESHOLD:
            report.note_blindspot(
                page=page_label,
                location=str(run.box),
                reason=(
                    "a shape was painted over text, and the file names its colour "
                    "indirectly through a pattern or a spot colour. Whether it hides "
                    "the text or is a tint you can read through cannot be decided "
                    "from the instructions alone."
                ),
            )


def invisible_text(report, page_label: str, content, page_box) -> None:
    """Text drawn in a mode that paints nothing at all.

    Mode 3 renders no glyphs. It is how a scanner stores the searchable layer under
    a page image, which is entirely legitimate and extremely common, and it is also
    how text survives being "removed" by a tool that merely stopped drawing it.

    The page image settles which one this is. Reporting eight hundred high findings
    on a scanned contract would be the fastest way to make somebody stop running the
    tool, and every one of them would be technically true and practically useless.
    """
    hidden = [r for r in content.text_runs if r.render_mode in INVISIBLE_RENDER_MODES]
    if not hidden:
        return

    scan = _page_images(content, page_box)
    if scan:
        under_the_scan = [
            r for r in hidden
            if any(r.box.covered_by(i.box) >= COVER_THRESHOLD for i in scan)
        ]
        if under_the_scan:
            report.add(
                Finding(
                    check="scanned_text_layer",
                    level=Level.LOW,
                    page=page_label,
                    location=str(scan[0].box),
                    summary=(
                        f"{len(under_the_scan)} run(s) of text draw nothing and sit "
                        "within the picture that fills this page, which is what a "
                        "scanned page looks like."
                    ),
                    detail=(
                        "Scanning software stores the recognised text invisibly behind "
                        "the picture so the page can be searched. That is expected and "
                        "is reported here only so you know the text is extractable. It "
                        "is worth a look if this document was ever meant to be a "
                        "picture and nothing more."
                    ),
                    sample=" | ".join(r.text for r in under_the_scan[:20]),
                )
            )
        hidden = [r for r in hidden if r not in under_the_scan]

    for run in hidden:
        if _too_short(report, run):
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
                    "characters are in the file and extract normally. Under a scanned "
                    "page image this is the ordinary searchable text layer. Anywhere "
                    "else it is content someone can read and nobody can see."
                ),
                sample=run.text,
            )
        )


def text_matching_background(report, page_label: str, content, page_box) -> None:
    """Text the same colour as whatever is behind it.

    White on white is the oldest trick in the format. The check has to be careful in
    two directions: white text on a dark bar is ordinary design, and text over a
    photograph has a background this tool cannot see, so it cannot claim the page is
    what lies behind it.
    """
    for run in content.text_runs:
        if run.render_mode in INVISIBLE_RENDER_MODES or run.clipped_away:
            continue
        if _too_short(report, run):
            continue
        if run.fill is None:
            # The file names this text's colour indirectly, through a spot colour, a
            # pattern or a DeviceN space, so whether it matches its background cannot
            # be decided from the drawing instructions. Dropping it silently would
            # report "checked and clean" about text that was never checked at all —
            # the mirror of the case covered_text already records below.
            report.note_blindspot(
                page=page_label,
                location=str(run.box),
                reason=(
                    "text is drawn in a colour the file names indirectly, through a "
                    "spot colour or a pattern. Whether it is the same colour as what "
                    "is behind it cannot be decided from the instructions alone."
                ),
            )
            continue

        x, y = _start_point(run)

        behind_image = any(
            image.order < run.order and image.box.holds(x, y) for image in content.images
        )
        if behind_image:
            continue  # the background is a picture, and pictures are not read here

        beneath = [s for s in content.fills if s.order < run.order and s.box.holds(x, y)]
        opaque_beneath = [s for s in beneath if s.conceals]

        if beneath and not opaque_beneath:
            continue  # something is behind it whose colour is not knowable

        background = opaque_beneath[-1].fill if opaque_beneath else WHITE
        where = "the shape painted behind it" if opaque_beneath else "the page itself"

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


def text_clipped_away(report, page_label: str, content, page_box) -> None:
    """Text excluded by a clipping path, which draws none of it."""
    for run in content.text_runs:
        if not run.clipped_away:
            continue
        if _too_short(report, run):
            continue
        report.add(
            Finding(
                check="text_clipped_away",
                level=Level.HIGH,
                page=page_label,
                location=str(run.box),
                summary=(
                    f"{len(run.text)} characters lie entirely outside the clipping "
                    "path in force, so none of it is drawn."
                ),
                detail=(
                    "A clipping path limits where later drawing appears. Text outside "
                    "it is never painted, and is never removed either. It extracts "
                    "exactly like any other text on the page."
                ),
                sample=run.text,
            )
        )


def text_too_small_to_read(report, page_label: str, content, page_box) -> None:
    """Text scaled down to nothing, which is a way of hiding it in plain sight."""
    for run in content.text_runs:
        if not run.too_small_to_read or run.render_mode in INVISIBLE_RENDER_MODES:
            continue
        if _too_short(report, run):
            continue
        report.add(
            Finding(
                check="text_too_small_to_read",
                level=Level.HIGH,
                page=page_label,
                location=str(run.box),
                summary=(
                    f"{len(run.text)} characters are drawn at effectively zero size "
                    "and cannot be read at any zoom."
                ),
                detail=(
                    "Shrinking text to nothing leaves it fully present in the file. It "
                    "extracts at full size and reads normally. Legitimate reasons for "
                    "this are rare."
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
        if _too_short(report, run):
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
    scan = _page_images(content, page_box)
    for image in content.images:
        if any(image is part for part in scan):
            continue  # a whole scanned page is covered by scanned_text_layer
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

"""One test per defect found by attacking the tool, so none of them can come back.

These were found after the first suite was already green, by building documents
specifically designed to fool the checks. Most of them are false positives on
completely ordinary files — a chart, a logo, a highlighter mark, a scanned page —
which is the failure that would make somebody stop running the tool for good.

Each test names the real-world document shape it stands for.
"""

from __future__ import annotations

import json
import time

import pdfbuild as P
import pytest

from before_you_send.cli import main
from before_you_send.findings import Level
from before_you_send.run import inspect_document

SECRET = "Account 8891 0042 3317"
FONT = "/Font<</F1 5 0 R>>"


@pytest.fixture
def build(tmp_path):
    def _build(name: str, data: bytes) -> str:
        path = tmp_path / f"{name}.pdf"
        path.write_bytes(data)
        return str(path)

    return _build


def checks(path: str) -> set:
    return {f.check for f in inspect_document(path).findings}


# --- extent, not just order -------------------------------------------------


def test_a_chart_clipped_to_its_frame_is_not_a_redaction(build):
    """A matplotlib or browser-printed figure: clip to the plot, then fill it.

    Without a clipping path the backdrop reads as covering the whole page, and the
    caption six hundred points away is reported as a covered secret.
    """
    figure = P.saved(
        P.clip_to(60, 80, 300, 200)
        + P.fill_rect(0, 0, 612, 792, (0.12, 0.12, 0.12))
    )
    path = build(
        "clipped_chart",
        P.one_page(P.text("Figure 3 shows the decline in unit margin.", 72, 700) + figure),
    )
    assert "covered_text" not in checks(path)


def test_a_logo_stamp_is_bounded_by_its_own_box(build):
    """A form XObject's /BBox is a hard boundary on everything it draws."""
    path = build(
        "logo_stamp",
        P.one_page(
            P.text("Ordinary visible body text on the page", 72, 700)
            + P.saved(b"1 0 0 1 500 740 cm /Fx Do\n"),
            resources=FONT + "/XObject<</Fx 6 0 R>>",
            extra_objects=[P.form(P.fill_rect(-600, -600, 1400, 1400))],
        ),
    )
    assert "covered_text" not in checks(path)


def test_text_excluded_by_a_clipping_path_is_reported(build):
    """The other side of the same fact: a clip can hide text outright."""
    hidden = P.saved(P.clip_to(0, 0, 0, 0) + P.text(SECRET, 72, 500))
    path = build("clipped_away", P.one_page(P.text("Visible", 72, 700) + hidden))
    assert "text_clipped_away" in checks(path)


# --- how opaque is opaque ---------------------------------------------------


def test_a_flattened_highlighter_mark_is_not_a_cover(build):
    """Multiply blending is how a highlight is flattened. Text shows straight through."""
    mark = P.with_state("GSM", P.fill_rect(70, 694, 250, 18, (1, 1, 0)))
    path = build(
        "highlighter",
        P.one_page(
            P.text("The indemnity clause survives termination.", 72, 700) + mark,
            resources=FONT + "/ExtGState<</GSM 6 0 R>>",
            extra_objects=[P.MULTIPLY_STATE],
        ),
    )
    assert "covered_text" not in checks(path)


def test_a_soft_masked_shape_is_not_a_cover(build):
    """A soft mask fades a shape. It does not conceal what is under it."""
    faded = P.with_state("GSS", P.fill_rect(70, 694, 250, 18))
    path = build(
        "soft_mask",
        P.one_page(
            P.text("A line of ordinary body text", 72, 700) + faded,
            resources=FONT + "/ExtGState<</GSS 6 0 R>>",
            extra_objects=[P.SOFT_MASK_STATE],
        ),
    )
    assert "covered_text" not in checks(path)


# --- colours that are not what the numbers say ------------------------------


def _spot_colour_page(content: bytes) -> bytes:
    return P.one_page(
        content,
        resources=FONT + "/ColorSpace<</CS0 6 0 R>>",
        extra_objects=[P.SEPARATION_SPACE, P.TINT_TRANSFORM],
    )


def test_a_spot_colour_bar_is_not_read_as_white(build):
    """In a Separation space, 1 is full ink, not white.

    Read as grey 1.0 a solid dark brand bar becomes a white one, and the white
    heading sitting on it is reported as invisible text.
    """
    content = b"/CS0 cs 1 scn 60 690 300 26 re f\n" + P.colored_text(
        "CONFIDENTIAL DRAFT", 72, 698, (1, 1, 1)
    )
    path = build("spot_colour", _spot_colour_page(content))
    assert "text_matching_background" not in checks(path)


def test_a_shape_of_unknown_colour_over_text_is_a_blind_spot(build):
    """Declining to guess is right; saying nothing at all is not."""
    content = P.text(SECRET, 72, 700) + b"/CS0 cs 1 scn 68 694 300 20 re f\n"
    report = inspect_document(build("unknown_colour", _spot_colour_page(content)))
    assert [f.check for f in report.findings if f.check == "covered_text"] == []
    assert len(report.blindspots) == 1
    assert "indirectly" in report.blindspots[0].reason


# --- what is behind the text ------------------------------------------------


def test_a_white_caption_on_a_photograph_is_not_white_on_white(build):
    """The background is a picture, and pictures are not read here."""
    path = build(
        "caption_on_photo",
        P.one_page(
            P.draw_image(60, 600, 400, 200)
            + P.colored_text("Fig 1. The new campus", 72, 620, (1, 1, 1)),
            resources=FONT + "/XObject<</Im1 6 0 R>>",
            extra_objects=[P.TINY_IMAGE],
        ),
    )
    assert "text_matching_background" not in checks(path)


def test_a_bar_sized_to_narrow_glyphs_is_still_seen_as_the_background(build):
    """Whether something is behind text must not depend on the width estimate.

    Helvetica declares no widths, so a run of narrow letters is estimated at roughly
    twice its real extent. Judged by area, the snug bar behind it looks absent and
    the heading is reported as white on white.
    """
    narrow = "iiii llll tttt ffff"
    content = P.fill_rect(70, 694, 62, 20, (0.1, 0.1, 0.4)) + P.colored_text(
        narrow, 72, 700, (1, 1, 1)
    )
    path = build("snug_bar", P.one_page(content))
    assert "text_matching_background" not in checks(path)


# --- the scanned page -------------------------------------------------------


def test_a_scanned_page_gives_one_low_finding_not_forty_high_ones(build):
    """The commonest document this tool will ever meet.

    Every line of the searchable layer draws nothing, which is exactly what it is
    supposed to do. Reporting each one at high would mean eight hundred findings on
    a twenty-page contract, all true and all useless.
    """
    lines = b"".join(
        P.text(f"Line {i} of the scanned agreement", 72, 720 - 14 * i, render_mode=3)
        for i in range(40)
    )
    path = build(
        "scanned",
        P.one_page(
            P.draw_image(0, 0, 612, 792) + lines,
            resources=FONT + "/XObject<</Im1 6 0 R>>",
            extra_objects=[P.TINY_IMAGE],
        ),
    )
    report = inspect_document(path)
    assert [f.check for f in report.findings] == ["scanned_text_layer"]
    assert report.findings[0].level is Level.LOW


def test_invisible_text_away_from_a_page_image_is_still_high(build):
    """The suppression is about the scan, not about invisible text in general."""
    path = build("invisible_only", P.one_page(P.text(SECRET, 72, 700, render_mode=3)))
    assert "invisible_text" in checks(path)


# --- annotations ------------------------------------------------------------


def test_text_under_an_opaque_annotation_is_caught(build):
    """Markup tools do not edit the page; they add a shape drawn on top of it.

    A filled black square dropped on a name by a review tool never touches the
    content stream, so a tool that only reads the page misses the most common way
    people try to obscure something.
    """
    annot = (
        b"<</Type/Annot/Subtype/Square/Rect[70 694 290 710]/F 4/AP<</N 6 0 R>>>>"
    )
    path = build(
        "annotation_cover",
        P.one_page(
            P.text(SECRET, 72, 700),
            page_extra="/Annots[7 0 R]",
            extra_objects=[P.appearance(P.fill_rect(0, 0, 220, 16)), annot],
        ),
    )
    # object 6 is the appearance, object 7 the annotation that points at it
    assert "covered_text" in checks(path)


def test_a_hidden_annotation_paints_nothing_and_covers_nothing(build):
    """An annotation flagged hidden is not drawn, so it hides nothing either."""
    annot = (
        b"<</Type/Annot/Subtype/Square/Rect[70 694 290 710]/F 2/AP<</N 6 0 R>>>>"
    )
    path = build(
        "hidden_annotation",
        P.one_page(
            P.text("Visible body text", 72, 700),
            page_extra="/Annots[7 0 R]",
            extra_objects=[P.appearance(P.fill_rect(0, 0, 220, 16)), annot],
        ),
    )
    assert "covered_text" not in checks(path)


def test_one_broken_annotation_does_not_silence_the_others(build):
    """A missing object in /Annots must not end the loop and report nothing.

    The difference between "there were none" and "I could not read them" has to
    survive to the output, or a malformed file looks like a clean one.
    """
    redact = P.annotation("Redact", extra="/T(Legal Review)")
    path = build(
        "broken_annotation",
        P.one_page(
            P.text(SECRET, 72, 700),
            page_extra="/Annots[99 0 R 6 0 R]",
            extra_objects=[redact],
        ),
    )
    report = inspect_document(path)
    assert "unapplied_redaction_marks" in {f.check for f in report.findings}
    assert any("could not be read" in u.reason for u in report.unchecked)


# --- the file's history, read structurally ----------------------------------


def test_an_attachment_containing_eof_is_not_an_earlier_version(build):
    """%%EOF appears inside any uncompressed attachment. It is not a revision."""
    inner = P.one_page(P.text("an attached document", 72, 700))
    path = build(
        "attachment_with_eof",
        P.one_page(
            P.text("See attached", 72, 700),
            catalog_extra="/Names<</EmbeddedFiles<</Names[(inner.pdf) 6 0 R]>>>>",
            extra_objects=[
                b"<</Type/Filespec/F(inner.pdf)/EF<</F 7 0 R>>>>",
                P.stream(inner, "/Type/EmbeddedFile"),
            ],
        ),
    )
    assert "earlier_versions_retained" not in checks(path)


def test_a_bookmark_prev_key_is_not_an_earlier_version(build):
    """/Prev is also an ordinary key on bookmarks, threads and page trees."""
    path = build(
        "outline_prev",
        P.one_page(
            P.text("A document with bookmarks", 72, 700),
            catalog_extra="/Outlines 6 0 R",
            extra_objects=[b"<</Type/Outlines/Count 0/Prev 6 0 R>>"],
        ),
    )
    assert "earlier_versions_retained" not in checks(path)


def test_a_real_revision_is_still_counted_exactly(build):
    base = P.one_page(P.text(SECRET, 72, 700))
    once = P.with_second_revision(base, {4: P.stream(P.text("clean", 72, 700))})
    twice = P.with_second_revision(once, {4: P.stream(P.text("cleaner", 72, 700))})
    for name, data, expected in (("one", once, 1), ("two", twice, 2)):
        report = inspect_document(build(f"revisions_{name}", data))
        found = [f for f in report.findings if f.check == "earlier_versions_retained"]
        assert len(found) == 1
        assert f"{expected} earlier version" in found[0].summary


# --- the width estimate -----------------------------------------------------


def test_type3_widths_are_read_in_their_own_glyph_space(build):
    """A Type 3 font measures widths through its /FontMatrix, not in thousandths.

    Dividing by 1000 regardless under-estimates a typical bitmap font tenfold, and a
    small box then appears to cover a whole line.
    """
    body = b"BT /F1 12 Tf 72 700 Td (AAAAAAAAAAAAAAAAAAAA) Tj ET\n"
    path = build(
        "type3",
        P.one_page(body + P.fill_rect(70, 694, 26, 20), font=P.type3_font()),
    )
    assert "covered_text" not in checks(path)


def test_a_width_the_font_does_not_declare_is_reported_as_an_estimate(build):
    """A font can declare widths and still not cover every code used with it.

    When the fallback is used the report has to say "about", and has to keep the
    caveat, rather than presenting a guess as a measurement.
    """
    body = b"BT /F1 12 Tf 72 700 Td (WWWWWWWWWWWWWWWWWWWW) Tj ET\n"
    path = build(
        "partial_widths",
        P.one_page(body + P.fill_rect(70, 694, 122, 20), font=P.narrow_font()),
    )
    report = inspect_document(path)
    covered = [f for f in report.findings if f.check == "covered_text"]
    if covered:
        assert "about" in covered[0].summary
    assert any("Exact text extents" in u.topic for u in report.unchecked)


# --- text scaled to nothing -------------------------------------------------


def test_text_at_effectively_zero_size_is_found(build):
    body = b"BT /F1 0.01 Tf 72 700 Td (%s) Tj ET\n" % SECRET.encode()
    path = build("tiny_text", P.one_page(body))
    assert "text_too_small_to_read" in checks(path)


# --- budgets ----------------------------------------------------------------


def test_a_tiny_file_that_describes_billions_of_nodes_terminates(build):
    """Twenty forms calling each other eight deep is 2.6e10 nodes in under a kilobyte.

    A budget spent only when something is painted never notices, because none of
    these nodes paint anything.
    """
    fan = P.stream(
        b"/Fx Do " * 20,
        "/Type/XObject/Subtype/Form/BBox[0 0 10 10]/Resources<</XObject<</Fx 6 0 R>>>>",
    )
    path = build(
        "form_bomb",
        P.one_page(
            P.text("hello", 72, 700) + b"/Fx Do\n",
            resources=FONT + "/XObject<</Fx 6 0 R>>",
            extra_objects=[fan],
        ),
    )
    started = time.monotonic()
    report = inspect_document(path)
    assert time.monotonic() - started < 20, "the walk did not terminate promptly"
    assert report.blindspots, "a truncated walk must be reported, not silently accepted"


def test_a_page_of_many_small_shapes_finishes_quickly(build):
    """A halftone, a map or a scatter plot puts hundreds of fills over one caption."""
    stipple = b"".join(
        P.fill_rect(70 + (i % 50) * 4, 694 + (i // 50) * 2, 3, 2) for i in range(1500)
    )
    path = build("stipple", P.one_page(P.text("A caption", 72, 700) + stipple))
    started = time.monotonic()
    inspect_document(path)
    assert time.monotonic() - started < 10, "coverage arithmetic did not stay bounded"


# --- the output itself ------------------------------------------------------


def test_control_characters_from_a_document_cannot_rewrite_the_report(build, capsys):
    """A title can carry escape sequences. Printed raw, they repaint the terminal."""
    hostile = "\x1b[2J\x1b[H\x1b[32mNo problems found.\x1b[0m"
    info = b"<</Title" + P.utf16_string(hostile) + b">>"
    path = build(
        "hostile_title",
        P.one_page(P.text("A page", 72, 700), extra_objects=[info], trailer_extra="/Info 6 0 R"),
    )
    main([path, "--show-content"])
    out = capsys.readouterr().out
    assert "\x1b" not in out
    main([path, "--show-content", "--format", "json"])
    assert "\x1b" not in json.dumps(json.loads(capsys.readouterr().out))

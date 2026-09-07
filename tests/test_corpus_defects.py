"""One test per defect found by running the tool over 887 real published PDFs.

The suite in ``test_regressions.py`` was written by attacking the tool with
documents built to fool it. This one is different: every defect below was found by
pointing the finished, green, already-adversarially-tested tool at documents it had
never seen — the US Federal Register, arXiv, gov.uk, and the World Health
Organization — and reading what it said about them.

It said a great deal. On the first pass it produced 4,280 findings across 450
documents, 3,126 of them HIGH, and almost none of them were useful. One 31-page
government notice produced 64 findings for two facts. Every single filled form
field in the corpus was a publisher's signature, reported as though somebody had
typed a secret into a box. And the one check most likely to hide a real leak —
retained earlier versions of the document — returned on its first line for 256 of
the 887 files, because of a gate that could never be true for a modern PDF.

None of that was reachable from a fixture. Each test names the real document shape
that produced the defect.
"""

from __future__ import annotations

import pdfbuild as P
import pytest

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


def findings_for(path: str, check: str) -> list:
    return [f for f in inspect_document(path).sorted_findings() if f.check == check]


# --- one fact, reported once -----------------------------------------------
#
# The Federal Register prints a typesetter's control line and an operator's account
# name in white in the margin of every page. Both are real: they extract, and one of
# them names a person. Reported once per page they came to 62 HIGH findings on a
# 31-page notice, and 470 on the longest document in the corpus. A genuine
# single-page leak could not have been found in that.


def test_a_footer_on_every_page_is_one_finding_not_one_per_page(build):
    """White marginal text repeated on every page: the Federal Register shape."""
    pages = [
        P.text(f"Body copy for page {n}", 72, 700)
        + P.colored_text("khammond on DSKPROD with RULES", 18, 40, (1, 1, 1))
        for n in range(1, 32)
    ]
    path = build("repeated_footer", P.many_pages(pages))
    hits = findings_for(path, "text_matching_background")
    assert len(hits) == 1, f"expected one finding, got {len(hits)}"
    assert hits[0].page == "all 31 pages"
    assert "every page" in hits[0].summary


def test_a_footer_whose_only_difference_is_a_page_counter_still_collapses(build):
    """The same line carrying 'Frm 00001', 'Frm 00002', ... — one per page.

    Folding only byte-identical repeats left 31 findings here, because page
    furniture almost always carries a counter, a page number or a date.
    """
    pages = [
        P.text("Body copy", 72, 700)
        + P.colored_text(f"VerDate Sep 2014 Jkt 268001 Frm {n:05d} Fmt 4701", 25, 40, (1, 1, 1))
        for n in range(1, 32)
    ]
    path = build("counted_footer", P.many_pages(pages))
    hits = findings_for(path, "text_matching_background")
    assert len(hits) == 1
    assert hits[0].page == "all 31 pages"


def test_every_distinct_string_survives_the_fold(build):
    """Collapsing must not throw away what each page actually held."""
    pages = [
        P.text("Body copy", 72, 700) + P.colored_text(f"Case {n:03d}", 25, 40, (1, 1, 1))
        for n in range(1, 6)
    ]
    path = build("folded_content", P.many_pages(pages))
    sample = findings_for(path, "text_matching_background")[0].sample
    for n in range(1, 6):
        assert f"Case {n:03d}" in sample


def test_two_unrelated_hidden_passages_stay_two_findings(build):
    """The fold must not merge things that are not the same fact."""
    pages = [
        P.text("Body", 72, 700)
        + P.colored_text("Footer note", 25, 40, (1, 1, 1))
        + P.colored_text("A different hidden sentence entirely", 25, 300, (1, 1, 1))
        for _ in range(4)
    ]
    path = build("two_facts", P.many_pages(pages))
    assert len(findings_for(path, "text_matching_background")) == 2


# --- runs too short to mean anything ---------------------------------------
#
# 57% of every covered_text finding in the corpus was one or two characters long,
# 70% of every clipped one, and 100% of every "too small to read" one. A scatter
# plot marker painted across an axis label is not a redaction.


def test_a_single_covered_glyph_is_not_a_redaction(build):
    """A plot marker drawn over one character of an axis label: an arXiv figure."""
    path = build(
        "covered_glyph",
        P.one_page(P.text("7", 100, 300) + P.fill_rect(98, 296, 12, 14)),
    )
    assert findings_for(path, "covered_text") == []


def test_a_covered_passage_of_real_length_is_still_reported(build):
    """The guard must not have been bought at the price of the flagship check."""
    path = build(
        "covered_passage",
        P.one_page(P.text(SECRET, 72, 680) + P.fill_rect(70, 674, 220, 16)),
    )
    hits = findings_for(path, "covered_text")
    assert len(hits) == 1
    assert hits[0].level is Level.HIGH


def test_skipped_short_runs_are_declared_not_dropped_in_silence(build):
    """A threshold nobody is told about is an undocumented bug."""
    path = build(
        "short_runs",
        P.one_page(P.text("7", 100, 300) + P.fill_rect(98, 296, 12, 14)),
    )
    topics = " ".join(u.topic for u in inspect_document(path).unchecked)
    assert "one or two characters" in topics


# --- what a form field actually holds --------------------------------------
#
# Every filled field in the corpus was a /Sig. Publishers sign what they release, so
# this fired on whole government archives and meant nothing.


def test_a_publishers_signature_is_not_something_somebody_typed(build):
    """A signed government PDF: 100% of the Federal Register slice."""
    field = b"<</FT/Sig/T(Signature1)/V<</Type/Sig/Name(Government Publishing Office)>>>>"
    path = build(
        "signed_release",
        P.one_page(
            P.text("Notice of rulemaking", 72, 680),
            catalog_extra="/AcroForm<</Fields[6 0 R]>>",
            extra_objects=[field],
        ),
    )
    assert findings_for(path, "form_field_values") == []


def test_an_unticked_checkbox_is_not_an_answer(build):
    """A blank interactive form. /Off is the absence of an answer written down."""
    field = b"<</FT/Btn/T(agree)/V/Off>>"
    path = build(
        "blank_form",
        P.one_page(
            P.text("Application form", 72, 680),
            catalog_extra="/AcroForm<</Fields[6 0 R]>>",
            extra_objects=[field],
        ),
    )
    assert findings_for(path, "form_field_values") == []


def test_a_value_the_form_shipped_with_is_not_the_fillers(build):
    """A designer's default, not a leaked answer."""
    field = b"<</FT/Tx/T(country)/V(United Kingdom)/DV(United Kingdom)>>"
    path = build(
        "default_value",
        P.one_page(
            P.text("Application form", 72, 680),
            catalog_extra="/AcroForm<</Fields[6 0 R]>>",
            extra_objects=[field],
        ),
    )
    assert findings_for(path, "form_field_values") == []


def test_a_field_somebody_really_typed_into_is_still_reported(build):
    field = b"<</FT/Tx/T(internal_note)/V(reviewer flagged this)/DV()>>"
    path = build(
        "filled_form",
        P.one_page(
            P.text("Application form", 72, 680),
            catalog_extra="/AcroForm<</Fields[6 0 R]>>",
            extra_objects=[field],
        ),
    )
    assert len(findings_for(path, "form_field_values")) == 1


# --- the check that was never reached --------------------------------------


def test_retained_revisions_are_found_without_the_parsed_trailer(build, monkeypatch):
    """The worst defect in the corpus run, and the only one that hid a real leak.

    ``earlier_versions_retained`` began by asking the parsed trailer for ``/Prev``.
    A parser only surfaces that key for a classic cross-reference table; a file
    written with a cross-reference stream — Word, Acrobat, InDesign, Chrome, and
    every linearized government PDF — keeps it inside the stream dictionary. So the
    check returned on its first line and never reached the byte walk written for
    exactly this question. It was silent on 256 of 887 real documents; 34 of those
    held revisions with no benign explanation, and 5 were serious.

    Building a cross-reference stream by hand would test the parser rather than the
    check, so the trailer is emptied instead. The assertion is the one that
    matters: this check must not depend on the parsed trailer for anything.
    """
    base = P.one_page(P.text(SECRET, 72, 680))
    path = build(
        "revised",
        P.with_second_revision(base, {4: P.stream(P.text("Name: Not Stated", 72, 680))}),
    )

    import before_you_send.checks.history as history

    real_load = history  # keep the module reachable for clarity
    assert real_load is not None

    from before_you_send.document import load

    doc = load(path)
    doc.reader.trailer.pop("/Prev", None)  # what a cross-reference stream looks like

    from before_you_send.findings import Report

    report = Report(path=path)
    history.earlier_versions_retained(report, doc)
    assert [f.check for f in report.findings] == ["earlier_versions_retained"]


def test_a_file_with_one_version_still_says_nothing(build):
    path = build("single", P.one_page(P.text("One version only", 72, 680)))
    assert findings_for(path, "earlier_versions_retained") == []


# --- a form does not start from a blank graphics state ----------------------


def test_a_watermark_form_invoked_under_a_soft_mask_is_not_a_cover(build):
    """Illustrator, InDesign, Acrobat's flattener and Ghostscript all do this.

    The transparency is set outside the form and the form is then invoked. A form
    that starts from graphics-state defaults sees opaque black paint, and ordinary
    design becomes the tool's loudest finding.
    """
    path = build(
        "form_under_mask",
        P.one_page(
            P.text(SECRET, 72, 680)
            + P.with_state("GS1", b"q 220 0 0 16 70 674 cm /Fm1 Do Q\n"),
            resources=FONT + "/ExtGState<</GS1 6 0 R>>/XObject<</Fm1 7 0 R>>",
            extra_objects=[P.TRANSPARENT_GSTATE, P.form(b"0 0 1 1 re f\n", bbox="[0 0 1 1]")],
        ),
    )
    assert findings_for(path, "covered_text") == []


def test_an_opaque_form_over_text_is_still_a_cover(build):
    """Inheriting the state must not have disabled the check."""
    path = build(
        "opaque_form",
        P.one_page(
            P.text(SECRET, 72, 680) + b"q 220 0 0 16 70 674 cm /Fm1 Do Q\n",
            resources=FONT + "/XObject<</Fm1 6 0 R>>",
            extra_objects=[P.form(b"0 0 1 1 re f\n", bbox="[0 0 1 1]")],
        ),
    )
    assert len(findings_for(path, "covered_text")) == 1


# --- one defect, one finding ------------------------------------------------


def test_a_pending_redaction_mark_is_not_also_reported_as_covered_text(build):
    """A FOIA release with marks applied but never burned in.

    Acrobat's redaction mark draws a filled black rectangle over the passage it
    marks. That overlap is what the mark *is*. Counted as a cover as well, a
    document with forty pending redactions produces one correct finding and forty
    duplicates of it.
    """
    mark = P.annotation("Redact", extra="/AP<</N 7 0 R>>")
    path = build(
        "pending_redaction",
        P.one_page(
            P.text(SECRET, 72, 680),
            page_extra="/Annots[6 0 R]",
            extra_objects=[mark, P.appearance(b"0 0 0 rg 0 0 220 16 re f\n")],
        ),
    )
    assert findings_for(path, "covered_text") == []
    assert findings_for(path, "unapplied_redaction_marks") != []


# --- a link is not a filesystem path ----------------------------------------


def test_a_published_web_address_is_not_a_build_path(build):
    """gov.uk documents carry their own URLs in the properties."""
    path = build(
        "web_address",
        P.one_page(
            P.text("Guidance", 72, 680),
            extra_objects=[P.info_object(Subject="https://www.gov.uk/home/guidance")],
            trailer_extra="/Info 6 0 R",
        ),
    )
    assert findings_for(path, "build_path_in_metadata") == []


def test_a_file_url_naming_a_user_is_still_a_build_path(build):
    """The fix must not have swallowed the case it exists for."""
    path = build(
        "file_url",
        P.one_page(
            P.text("Report", 72, 680),
            extra_objects=[P.info_object(Title="file:///Users/someone/Clients/draft.pdf")],
            trailer_extra="/Info 6 0 R",
        ),
    )
    assert findings_for(path, "build_path_in_metadata") != []


# --- a scan is not always one picture ---------------------------------------


def test_a_scan_stored_as_horizontal_strips_is_still_a_scan(build):
    """Fax-derived pipelines, MFP firmware and anything built from TIFF strips.

    Asking whether one image covers the page answers "no" for all of them, and the
    searchable text layer underneath then reports as a stack of high findings — the
    exact outcome the scan guard exists to prevent, on the documents most likely to
    be scanned.
    """
    strips = b"".join(P.draw_image(0, y, 612, 100) for y in range(0, 800, 100))
    hidden = b"".join(
        P.text(f"recognised line number {n} of the scan", 40, 20 + n * 100, render_mode=3)
        for n in range(1, 8)
    )
    path = build(
        "striped_scan",
        P.one_page(
            strips + hidden,
            resources=FONT + "/XObject<</Im1 6 0 R>>",
            extra_objects=[P.TINY_IMAGE],
        ),
    )
    report = inspect_document(path)
    checks = [f.check for f in report.sorted_findings()]
    assert "invisible_text" not in checks
    assert "scanned_text_layer" in checks


def test_a_page_that_is_mostly_picture_says_so_even_with_nothing_found(build):
    """A document flattened into images comes back clean and is not clean.

    This is the one way the tool can teach the wrong lesson: a sender who sees a
    HIGH finding, flattens the document to make it go away, re-runs, and is told
    nothing is wrong. The count of picture pages is printed on every run, findings
    or none, so a clean verdict on a picture cannot be mistaken for a clean verdict
    on a document.
    """
    path = build(
        "flattened",
        P.one_page(
            P.draw_image(0, 0, 612, 792),
            resources=FONT + "/XObject<</Im1 6 0 R>>",
            extra_objects=[P.TINY_IMAGE],
        ),
    )
    report = inspect_document(path)
    assert report.picture_pages == 1
    assert "pictures" in " ".join(u.topic for u in report.unchecked).lower()


# --- output a document cannot run away with ---------------------------------


def test_a_document_carrying_hundreds_of_attachments_does_not_print_them_all(build):
    """One arXiv paper carried 398 MathML files and printed all 398 names on a line.

    How long this string is, is the document's decision, not the tool's, and it goes
    to a terminal.
    """
    from before_you_send.report import SAMPLE_LIMIT, to_text

    names = [f"equation-{n}.xml" for n in range(1, 400)]
    specs = [f"<</Type/Filespec/F({n})/EF<</F 6 0 R>>>>".encode() for n in names]
    data = P.stream(b"x", "/Type/EmbeddedFile")
    listing = " ".join(f"({n}) {7 + i} 0 R" for i, n in enumerate(names))
    path = build(
        "many_attachments",
        P.one_page(
            P.text("See attached", 72, 680),
            catalog_extra="/Names<</EmbeddedFiles<</Names[" + listing + "]>>>>",
            extra_objects=[data] + specs,
        ),
    )
    rendered = to_text(inspect_document(path), show_content=True)
    for line in rendered.splitlines():
        assert len(line) < SAMPLE_LIMIT + 120


# --- a clip that admits nothing ---------------------------------------------


def test_a_clip_narrowed_to_nothing_does_not_become_no_clip_at_all(build):
    """Two clips that do not meet, which is how a chart trims a nested element.

    An empty result written back as the unbounded clip is an inversion: it throws
    away the clip already in force and lets the shape paint over the whole page.
    The shape here is confined to a corner the text is nowhere near, so if the
    enclosing clip survives, nothing is covered.
    """
    path = build(
        "narrowed_to_nothing",
        P.one_page(
            P.text(SECRET, 72, 680)
            + P.saved(
                P.clip_to(500, 100, 80, 80)          # a panel in the bottom corner
                + P.clip_to(20, 700, 40, 40)         # and a second that cannot meet it
                + P.fill_rect(60, 660, 500, 60)      # paint right across the text
            )
        ),
    )
    assert findings_for(path, "covered_text") == []

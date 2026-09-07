"""What each check finds, and — first — what it must refuse to find.

The quiet tests come first on purpose. A tool like this is only worth running if a
clean document comes back clean, so the cases that must stay silent are the ones
that decide whether any of the rest is worth anything.
"""

from __future__ import annotations

from before_you_send.findings import Level
from before_you_send.run import inspect_document


def checks(path: str) -> set:
    return {f.check for f in inspect_document(path).findings}


def only(path: str, name: str):
    found = [f for f in inspect_document(path).findings if f.check == name]
    assert len(found) == 1, f"expected exactly one {name}, got {len(found)}"
    return found[0]


# --- must stay silent -------------------------------------------------------


def test_a_clean_document_reports_nothing(clean_document):
    report = inspect_document(clean_document)
    assert report.findings == [], [f.check for f in report.findings]


def test_a_heading_on_a_dark_bar_is_not_a_redaction(ok_dark_header):
    """The whole tool turns on this one. Same geometry, opposite paint order."""
    assert checks(ok_dark_header) == set()


def test_a_box_over_deleted_text_is_not_a_finding(ok_real_redaction):
    assert checks(ok_real_redaction) == set()


def test_an_outlined_box_hides_nothing(ok_outlined_box):
    assert "covered_text" not in checks(ok_outlined_box)


def test_a_panel_clipping_the_end_of_a_line_is_not_a_cover(ok_edge_overlap):
    assert "covered_text" not in checks(ok_edge_overlap)


def test_a_see_through_highlight_is_not_a_cover(ok_highlight):
    assert "covered_text" not in checks(ok_highlight)


def test_white_text_on_a_dark_bar_is_readable_and_not_reported(ok_white_on_dark):
    assert "text_matching_background" not in checks(ok_white_on_dark)


def test_text_bleeding_off_an_edge_is_not_off_the_page(ok_bleed):
    assert "text_outside_page" not in checks(ok_bleed)


def test_an_image_beside_text_is_not_a_blind_spot(ok_image_beside_text):
    assert inspect_document(ok_image_beside_text).blindspots == []


def test_a_document_with_one_version_has_no_history(ok_single_revision):
    assert "earlier_versions_retained" not in checks(ok_single_revision)


# --- must fire --------------------------------------------------------------


def test_text_under_a_later_box_is_high(fake_redaction):
    finding = only(fake_redaction, "covered_text")
    assert finding.level is Level.HIGH
    assert "100%" in finding.summary


def test_text_that_draws_nothing_is_high(invisible_text):
    assert only(invisible_text, "invisible_text").level is Level.HIGH


def test_white_text_on_the_page_itself_is_high(white_on_white):
    finding = only(white_on_white, "text_matching_background")
    assert finding.level is Level.HIGH
    assert "the page itself" in finding.summary


def test_text_parked_off_the_page_is_found(off_page_text):
    assert only(off_page_text, "text_outside_page").level is Level.MEDIUM


def test_an_earlier_version_of_the_file_is_found(incremental_update):
    finding = only(incremental_update, "earlier_versions_retained")
    assert finding.level is Level.HIGH
    assert "1 earlier version" in finding.summary


def test_an_attached_file_is_high(embedded_file):
    finding = only(embedded_file, "embedded_files")
    assert finding.level is Level.HIGH
    assert finding.sample == "model.xlsx"


def test_a_script_that_runs_on_open_is_high(javascript_on_open):
    assert only(javascript_on_open, "active_content").level is Level.HIGH


def test_a_hidden_form_field_holding_a_value_is_high(filled_hidden_form):
    finding = only(filled_hidden_form, "form_field_values")
    assert finding.level is Level.HIGH
    assert "not shown on the page" in finding.summary


def test_marks_without_an_applied_redaction_are_high(marked_but_not_redacted):
    assert only(marked_but_not_redacted, "unapplied_redaction_marks").level is Level.HIGH


def test_a_layer_switched_off_is_found(hidden_layer):
    assert only(hidden_layer, "hidden_layers").level is Level.MEDIUM


def test_a_named_author_is_found(named_author):
    assert only(named_author, "document_author").sample == "A. Reviewer"


def test_a_filesystem_path_in_the_properties_is_found(build_path_leak):
    assert only(build_path_leak, "build_path_in_metadata").level is Level.MEDIUM


def test_comments_and_the_names_on_them_are_found(reviewer_comments):
    finding = only(reviewer_comments, "annotation_authors")
    assert finding.level is Level.MEDIUM
    assert "Second Reviewer" in finding.sample


# --- the blind spot ---------------------------------------------------------


def test_an_image_over_text_is_a_blind_spot_not_a_finding(image_over_text):
    """The one case the tool must admit it cannot judge."""
    report = inspect_document(image_over_text)
    assert len(report.blindspots) == 1
    assert "cannot be decided" in report.blindspots[0].reason
    assert "covered_text" not in {f.check for f in report.findings}


def test_a_signature_explains_a_single_update_and_is_downgraded(signed_document):
    finding = only(signed_document, "earlier_versions_retained")
    assert finding.level is Level.LOW
    assert "signature" in finding.summary


def test_text_that_inherited_its_background_colour_is_caught(inherited_fill):
    """Found by the clean-document control, which is what a control is for."""
    finding = only(inherited_fill, "text_matching_background")
    assert finding.level is Level.HIGH
    assert "the shape painted behind it" in finding.summary


def test_an_unreset_render_mode_makes_later_runs_invisible_too(render_mode_leaks):
    """Not a false positive: the mode really does carry past the end of the block."""
    found = [f for f in inspect_document(render_mode_leaks).findings
             if f.check == "invisible_text"]
    assert len(found) == 2

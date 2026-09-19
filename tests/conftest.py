"""Fixture documents.

Every one of these is built from literals in this file. Nothing here came from a
real document, and no PDF is committed to the repository — they are written to a
temporary directory when a test asks for one.

The names are deliberately split into two groups. Fixtures whose name starts with
``ok_`` must produce no finding for the check they are aimed at; they are the
innocent twins of the ones that must fire, and they are the reason to trust the rest.
"""

from __future__ import annotations

import pdfbuild as P
import pytest

SECRET = "Account 8891 0042 3317"
FONT_RESOURCES = "/Font<</F1 5 0 R>>"


@pytest.fixture
def write(tmp_path):
    """Write raw PDF bytes to a file and hand back the path."""

    def _write(name: str, data: bytes) -> str:
        path = tmp_path / f"{name}.pdf"
        path.write_bytes(data)
        return str(path)

    return _write


# --- text hidden under something -------------------------------------------


@pytest.fixture
def fake_redaction(write):
    """A black box painted over text that was never removed."""
    return write(
        "fake_redaction",
        P.one_page(P.text(SECRET, 72, 680) + P.fill_rect(70, 674, 220, 16)),
    )


@pytest.fixture
def ok_dark_header(write):
    """A heading in white on a dark bar. Same overlap, opposite paint order."""
    return write(
        "ok_dark_header",
        P.one_page(
            P.fill_rect(70, 674, 220, 16, (0.1, 0.1, 0.3))
            + P.colored_text("Quarterly Summary", 72, 680, (1, 1, 1))
        ),
    )


@pytest.fixture
def ok_real_redaction(write):
    """A box where the text really was deleted. The honest version of the first one."""
    return write("ok_real_redaction", P.one_page(P.fill_rect(70, 674, 220, 16)))


@pytest.fixture
def ok_outlined_box(write):
    """A box drawn as an outline. It covers the text visually but hides nothing."""
    return write(
        "ok_outlined_box",
        P.one_page(P.text("Visible line of text", 72, 680) + P.stroke_rect(70, 674, 220, 16)),
    )


@pytest.fixture
def ok_edge_overlap(write):
    """A panel that clips the end of a line, which is ordinary page furniture."""
    return write(
        "ok_edge_overlap",
        P.one_page(
            P.text("A fairly long sentence of body text here", 72, 680)
            + P.fill_rect(250, 674, 300, 16)
        ),
    )


@pytest.fixture
def ok_highlight(write):
    """A see-through highlight over text."""
    return write(
        "ok_highlight",
        P.one_page(
            P.text("Highlighted for review", 72, 680) + P.transparent_rect(70, 674, 220, 16),
            resources=FONT_RESOURCES + "/ExtGState<</GS1 6 0 R>>",
            extra_objects=[P.TRANSPARENT_GSTATE],
        ),
    )


# --- text that paints nothing ----------------------------------------------


@pytest.fixture
def invisible_text(write):
    return write("invisible_text", P.one_page(P.text(SECRET, 72, 680, render_mode=3)))


@pytest.fixture
def white_on_white(write):
    return write(
        "white_on_white", P.one_page(P.colored_text(SECRET, 72, 680, (1, 1, 1)))
    )


@pytest.fixture
def ok_white_on_dark(write):
    """White text on a dark bar painted first: readable, and not a finding."""
    return write(
        "ok_white_on_dark",
        P.one_page(
            P.fill_rect(70, 674, 220, 16, (0, 0, 0))
            + P.colored_text("Section Heading", 72, 680, (1, 1, 1))
        ),
    )


@pytest.fixture
def off_page_text(write):
    return write("off_page_text", P.one_page(P.text(SECRET, 900, 680)))


@pytest.fixture
def ok_bleed(write):
    """Text running off the right edge, as anything designed for print does."""
    return write("ok_bleed", P.one_page(P.text("Running off the edge here", 560, 680)))


# --- what cannot be seen ---------------------------------------------------


@pytest.fixture
def image_over_text(write):
    return write(
        "image_over_text",
        P.one_page(
            P.text(SECRET, 72, 680) + P.draw_image(70, 674, 220, 16),
            resources=FONT_RESOURCES + "/XObject<</Im1 6 0 R>>",
            extra_objects=[P.TINY_IMAGE],
        ),
    )


@pytest.fixture
def ok_image_beside_text(write):
    """A logo next to a paragraph, overlapping nothing."""
    return write(
        "ok_image_beside_text",
        P.one_page(
            P.text("Body copy on the left", 72, 680) + P.draw_image(400, 674, 60, 60),
            resources=FONT_RESOURCES + "/XObject<</Im1 6 0 R>>",
            extra_objects=[P.TINY_IMAGE],
        ),
    )


# --- the file's own history ------------------------------------------------


@pytest.fixture
def incremental_update(write):
    """A second revision that replaces the page content. The first is still there."""
    base = P.one_page(P.text(SECRET, 72, 680))
    return write(
        "incremental_update",
        P.with_second_revision(base, {4: P.stream(P.text("Name: Not Stated", 72, 680))}),
    )


@pytest.fixture
def ok_single_revision(write):
    return write("ok_single_revision", P.one_page(P.text("One version only", 72, 680)))


@pytest.fixture
def signed_document(write):
    """One incremental update, explained by a signature."""
    base = P.one_page(
        P.text("Agreement", 72, 680),
        catalog_extra="/AcroForm<</Fields[6 0 R]>>",
        extra_objects=[b"<</FT/Sig/T(Signature1)/V<</Type/Sig>>>>"],
    )
    return write(
        "signed_document",
        P.with_second_revision(base, {4: P.stream(P.text("Agreement", 72, 680))}),
    )


# --- carried payloads ------------------------------------------------------


@pytest.fixture
def embedded_file(write):
    spec = b"<</Type/Filespec/F(model.xlsx)/EF<</F 7 0 R>>>>"
    data = P.stream(b"not a real spreadsheet", "/Type/EmbeddedFile")
    return write(
        "embedded_file",
        P.one_page(
            P.text("See attached", 72, 680),
            catalog_extra="/Names<</EmbeddedFiles<</Names[(model.xlsx) 6 0 R]>>>>",
            extra_objects=[spec, data],
        ),
    )


@pytest.fixture
def javascript_on_open(write):
    return write(
        "javascript_on_open",
        P.one_page(
            P.text("Ordinary looking page", 72, 680),
            catalog_extra="/OpenAction<</S/JavaScript/JS(app.alert\\(1\\))>>",
        ),
    )


@pytest.fixture
def filled_hidden_form(write):
    widget = (
        b"<</Type/Annot/Subtype/Widget/Rect[70 670 270 690]/FT/Tx"
        b"/T(internal_note)/V(reviewer flagged this)/F 2>>"
    )
    return write(
        "filled_hidden_form",
        P.one_page(
            P.text("Application", 72, 680),
            page_extra="/Annots[6 0 R]",
            catalog_extra="/AcroForm<</Fields[6 0 R]>>",
            extra_objects=[widget],
        ),
    )


# --- protection that did not happen ----------------------------------------


@pytest.fixture
def marked_but_not_redacted(write):
    return write(
        "marked_but_not_redacted",
        P.one_page(
            P.text(SECRET, 72, 680),
            page_extra="/Annots[6 0 R]",
            extra_objects=[P.annotation("Redact")],
        ),
    )


@pytest.fixture
def hidden_layer(write):
    return write(
        "hidden_layer",
        P.one_page(
            P.text("Final copy", 72, 680),
            catalog_extra="/OCProperties<</OCGs[6 0 R]/D<</OFF[6 0 R]>>>>",
            extra_objects=[b"<</Type/OCG/Name(Draft notes)>>"],
        ),
    )


# --- what the document says about its author -------------------------------


@pytest.fixture
def named_author(write):
    return write(
        "named_author",
        P.one_page(
            P.text("Report", 72, 680),
            extra_objects=[P.info_object(Author="A. Reviewer")],
            trailer_extra="/Info 6 0 R",
        ),
    )


@pytest.fixture
def build_path_leak(write):
    return write(
        "build_path_leak",
        P.one_page(
            P.text("Report", 72, 680),
            extra_objects=[
                P.info_object(Title="/Users/someone/Clients/Draft v3 CONFIDENTIAL.docx")
            ],
            trailer_extra="/Info 6 0 R",
        ),
    )


@pytest.fixture
def reviewer_comments(write):
    note = P.annotation(
        "Text", extra="/T(Second Reviewer)/Contents(Do not send this version)"
    )
    return write(
        "reviewer_comments",
        P.one_page(
            P.text("Draft", 72, 680),
            page_extra="/Annots[6 0 R]",
            extra_objects=[note],
        ),
    )


# --- encrypted, and open to anybody ----------------------------------------


@pytest.fixture
def aes_encrypted_empty_password(tmp_path):
    """A PDF encrypted with AES-256 that opens for everyone, with no password.

    The one fixture here not assembled from literal bytes, and it cannot be: AES-256
    is AES-256, and writing one by hand would mean implementing the cipher in this
    file. It is still generated rather than committed, so no binary enters the
    repository, and every input to it is written above in plain sight.

    The shape is routine rather than exotic. A publisher encrypts to record a
    request that readers not copy or print, sets no user password so the document
    opens for anybody, and 15 of 250 gov.uk documents in one measured corpus were
    exactly this. Reading one needs the cryptography package, which the tool did not
    depend on before 0.3.0. It told the sender the file was truncated or damaged.
    """
    import io

    from pypdf import PdfReader, PdfWriter

    plain = P.one_page(P.text(SECRET, 72, 680) + P.fill_rect(70, 674, 220, 16))
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(plain)))
    # An owner password and no user password: restrictions asked for, and a
    # document that opens without being asked for anything.
    writer.encrypt(
        user_password="", owner_password="not the empty string", algorithm="AES-256"
    )
    buffer = io.BytesIO()
    writer.write(buffer)

    path = tmp_path / "aes_encrypted_empty_password.pdf"
    path.write_bytes(buffer.getvalue())
    return str(path)


# --- the control -----------------------------------------------------------


@pytest.fixture
def clean_document(write):
    """An ordinary page with nothing hidden in it. Must report nothing at all."""
    body = (
        P.fill_rect(60, 700, 240, 20, (0.9, 0.9, 0.9))
        + P.colored_text("Summary of Findings", 66, 706, (0, 0, 0))
        + P.colored_text("The figures below are unaudited.", 72, 660, (0, 0, 0))
        + P.colored_text("Prepared for internal discussion.", 72, 640, (0, 0, 0))
        + P.stroke_rect(60, 620, 480, 120)
    )
    return write("clean_document", P.one_page(body))


@pytest.fixture
def inherited_fill(write):
    """A heading drawn without resetting the colour used for the bar behind it.

    This is not a contrived case. A generator that sets a fill for a shape and then
    shows text without setting one again produces text the same colour as its own
    background, and it is genuinely unreadable.
    """
    return write(
        "inherited_fill",
        P.one_page(
            P.fill_rect(60, 700, 240, 20, (0.9, 0.9, 0.9)) + P.text("Section", 66, 706)
        ),
    )


@pytest.fixture
def render_mode_leaks(write):
    """A generator that sets an invisible render mode and never sets it back.

    Text state is part of the graphics state, so it survives the end of a text
    block. Every run after the first is invisible too, and all of them extract.
    """
    return write(
        "render_mode_leaks",
        P.one_page(
            P.leaves_render_mode("Scanned layer", 72, 700, render_mode=3)
            + P.text("Follow-up note nobody can see", 72, 680)
        ),
    )

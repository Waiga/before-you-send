"""Builds the example documents, so none has to be committed.

Every value in here is invented. There is no PDF in this repository and no data of
anyone's in these files: run this script and you get them, and they are ignored by
git so they never come back the other way.

    python examples/make_examples.py

Then:

    before-you-send examples/leaky-letter.pdf
    before-you-send examples/careful-letter.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))

import pdfbuild as P  # noqa: E402


def leaky_letter() -> bytes:
    """A letter with seven separate things in it the sender would not expect."""
    body = (
        # a heading on a bar: painted bar first, then text. Not a finding.
        P.fill_rect(60, 700, 300, 22, (0.15, 0.2, 0.35))
        + P.colored_text("Settlement Summary", 66, 706, (1, 1, 1))
        # the classic: text, then a black box over it
        + P.colored_text("Counterparty: Harrowgate Mills Ltd", 72, 660, (0, 0, 0))
        + P.fill_rect(70, 654, 240, 16)
        # text that draws nothing at all
        + P.text("Internal note: settle at or above 41,500", 72, 630, render_mode=3)
        # white text on the white page
        + P.colored_text("Reserve figure 58,000", 72, 610, (1, 1, 1))
        # parked off the edge of the page, out of sight
        + P.colored_text("DRAFT - do not circulate", 900, 590, (0, 0, 0))
        # an image over a line of text: the tool must say it cannot see under this
        + P.colored_text("Signed on behalf of the company", 72, 560, (0, 0, 0))
        + P.draw_image(70, 554, 220, 16)
        + P.colored_text("Prepared for discussion only.", 72, 520, (0, 0, 0))
    )
    base = P.one_page(
        body,
        resources="/Font<</F1 5 0 R>>/XObject<</Im1 6 0 R>>",
        page_extra="/Annots[8 0 R]",
        catalog_extra="/Names<</EmbeddedFiles<</Names[(workings.xlsx) 7 0 R]>>>>",
        extra_objects=[
            P.TINY_IMAGE,
            b"<</Type/Filespec/F(workings.xlsx)/EF<</F 9 0 R>>>>",
            P.annotation(
                "Text",
                rect="[300 640 320 660]",
                extra="/T(M. Alvarez)/Contents(Can we drop the reserve line?)",
            ),
            P.stream(b"invented placeholder, not a spreadsheet", "/Type/EmbeddedFile"),
            P.info_object(
                Author="m.alvarez",
                Title="/Users/malvarez/Clients/Harrowgate/settlement v6 FINAL.docx",
            ),
        ],
        trailer_extra="/Info 10 0 R",
    )
    # and an edit, saved the way that keeps the old version inside the file
    return P.with_second_revision(
        base, {4: P.stream(body.replace(b"41,500", b"39,000"))}
    )


def careful_letter() -> bytes:
    """The same letter, written so there is nothing left in it. Reports nothing."""
    body = (
        P.fill_rect(60, 700, 300, 22, (0.15, 0.2, 0.35))
        + P.colored_text("Settlement Summary", 66, 706, (1, 1, 1))
        + P.colored_text("Counterparty: [redacted]", 72, 660, (0, 0, 0))
        + P.colored_text("Prepared for discussion only.", 72, 520, (0, 0, 0))
        + P.stroke_rect(60, 500, 480, 230)
    )
    return P.one_page(body)


def main() -> None:
    for name, data in (
        ("leaky-letter", leaky_letter()),
        ("careful-letter", careful_letter()),
    ):
        path = HERE / f"{name}.pdf"
        path.write_bytes(data)
        print(f"wrote {path.relative_to(HERE.parent)} ({len(data):,} bytes)")


if __name__ == "__main__":
    main()

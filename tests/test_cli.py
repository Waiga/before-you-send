"""The command line: exit codes, refusals, and the promise that a report is safe to share.

The privacy tests are the important ones here. This tool exists because a document is
about to leave somebody's machine, and its report is the thing most likely to be
pasted into a chat on the way out. A report that quotes the secret has moved the
secret rather than contained it.
"""

from __future__ import annotations

import json

import pytest

from before_you_send.cli import EXIT_CLEAN, EXIT_FINDINGS, EXIT_UNREADABLE, main

SECRET = "Account 8891 0042 3317"


# --- exit codes -------------------------------------------------------------


def test_a_clean_document_exits_zero(clean_document, capsys):
    assert main([clean_document]) == EXIT_CLEAN


def test_a_high_finding_exits_one(fake_redaction, capsys):
    assert main([fake_redaction]) == EXIT_FINDINGS


def test_fail_on_never_always_exits_zero(fake_redaction, capsys):
    assert main([fake_redaction, "--fail-on", "never"]) == EXIT_CLEAN


def test_fail_on_high_ignores_a_low_finding(signed_document, capsys):
    assert main([signed_document, "--fail-on", "high"]) == EXIT_CLEAN


def test_fail_on_low_catches_a_low_finding(signed_document, capsys):
    assert main([signed_document, "--fail-on", "low"]) == EXIT_FINDINGS


# --- privacy ----------------------------------------------------------------


def test_what_was_found_is_withheld_by_default(fake_redaction, capsys):
    main([fake_redaction])
    out = capsys.readouterr().out
    assert SECRET not in out
    assert "8891" not in out
    assert "covered_text" in out
    assert "--show-content" in out


def test_show_content_includes_it_when_asked(fake_redaction, capsys):
    main([fake_redaction, "--show-content"])
    assert SECRET in capsys.readouterr().out


def test_json_withholds_it_too(fake_redaction, capsys):
    main([fake_redaction, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["content_included"] is False
    assert "sample" not in payload["findings"][0]
    assert SECRET not in json.dumps(payload)


def test_verbose_explains_without_quoting(fake_redaction, capsys):
    main([fake_redaction, "--verbose"])
    out = capsys.readouterr().out
    assert "Covering text does not remove it" in out
    assert SECRET not in out


# --- refusals ---------------------------------------------------------------


def test_a_missing_file_is_refused_by_name(tmp_path, capsys):
    assert main([str(tmp_path / "nope.pdf")]) == EXIT_UNREADABLE
    assert "There is no file at" in capsys.readouterr().err


def test_a_folder_is_refused(tmp_path, capsys):
    assert main([str(tmp_path)]) == EXIT_UNREADABLE
    assert "is a folder" in capsys.readouterr().err


def test_an_empty_file_is_refused(tmp_path, capsys):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    assert main([str(path)]) == EXIT_UNREADABLE
    assert "empty" in capsys.readouterr().err


def test_a_different_format_is_refused_by_name(tmp_path, capsys):
    path = tmp_path / "notes.docx"
    path.write_bytes(b"PK\x03\x04 not a pdf")
    assert main([str(path)]) == EXIT_UNREADABLE
    assert "This tool reads PDF files" in capsys.readouterr().err


def test_a_file_that_is_not_a_pdf_says_so_plainly(tmp_path, capsys):
    path = tmp_path / "image.pdf"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 400)
    assert main([str(path)]) == EXIT_UNREADABLE
    assert "does not begin with a PDF header" in capsys.readouterr().err


def test_a_refusal_says_that_nothing_examined_is_not_clean(tmp_path, capsys):
    path = tmp_path / "image.pdf"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 400)
    main([str(path)])
    assert "That is not a clean result" in capsys.readouterr().err


# --- honesty in the output --------------------------------------------------


def test_a_clean_run_refuses_to_call_itself_safe(clean_document, capsys):
    main([clean_document])
    out = capsys.readouterr().out
    assert "not the same as 'safe to send'" in out
    assert "NOT CHECKED" in out


def test_a_blind_spot_is_printed_separately_from_findings(image_over_text, capsys):
    main([image_over_text])
    out = capsys.readouterr().out
    assert "COULD NOT SEE" in out
    assert "could not be seen into" in out


def test_json_keeps_blind_spots_out_of_the_findings_list(image_over_text, capsys):
    main([image_over_text, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"] == []
    assert len(payload["could_not_see"]) == 1


@pytest.mark.parametrize("flag", ["--help"])
def test_help_does_not_promise_safety(flag, capsys):
    with pytest.raises(SystemExit):
        main([flag])
    out = capsys.readouterr().out
    assert "does not tell you a document is safe to send" in out

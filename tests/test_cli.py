"""The command line: exit codes, refusals, and the promise that a report is safe to share.

The privacy tests are the important ones here. This tool exists because a document is
about to leave somebody's machine, and its report is the thing most likely to be
pasted into a chat on the way out. A report that quotes the secret has moved the
secret rather than contained it.
"""

from __future__ import annotations

import json

import pytest

from before_you_send.cli import (
    EXIT_CLEAN,
    EXIT_FINDINGS,
    EXIT_TOOL_INCOMPLETE,
    EXIT_UNREADABLE,
    main,
)

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


# --- our fault, said as ours ------------------------------------------------


def _parser_missing_its_library(monkeypatch):
    """Make the parser raise for a missing package, whatever is installed here."""
    import pypdf
    from pypdf.errors import DependencyError

    def refuse(*args, **kwargs):
        raise DependencyError("cryptography>=3.1 is required for AES algorithm")

    monkeypatch.setattr(pypdf, "PdfReader", refuse)


def test_a_missing_library_gets_its_own_exit_code(clean_document, monkeypatch, capsys):
    """Exit 2 sends an operator to look at their document. Here the document is fine.

    A pipeline should not have to guess which of the two it got, so this is a code
    of its own rather than the refusal code reused.
    """
    _parser_missing_its_library(monkeypatch)
    assert main([clean_document]) == EXIT_TOOL_INCOMPLETE
    assert EXIT_TOOL_INCOMPLETE not in (EXIT_CLEAN, EXIT_FINDINGS, EXIT_UNREADABLE)


def test_a_missing_library_blames_the_tool_and_not_the_file(
    clean_document, monkeypatch, capsys
):
    _parser_missing_its_library(monkeypatch)
    main([clean_document])
    err = capsys.readouterr().err

    assert "This tool is missing something it needs" in err
    assert "cryptography" in err
    assert "pip install" in err
    assert "truncated" not in err
    assert "damaged" not in err


def test_a_missing_library_still_refuses_to_look_clean(
    clean_document, monkeypatch, capsys
):
    """The posture that must survive the fix: nothing examined is not a clean result."""
    _parser_missing_its_library(monkeypatch)
    code = main([clean_document])
    err = capsys.readouterr().err

    assert code != EXIT_CLEAN
    assert "Nothing was examined, so nothing is reported" in err
    assert "That is not a clean result" in err


def test_an_encrypted_document_that_opens_for_anyone_is_reported_not_refused(
    aes_encrypted_empty_password, capsys
):
    """The real file, end to end, through the command line."""
    assert main([aes_encrypted_empty_password, "--fail-on", "low"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "encryption_without_a_password" in out
    assert "Cannot read this file" not in out


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


# --- our fault, said as ours, when only part of the run is affected ---------


def _check_missing_its_library(monkeypatch, message="Pillow is required to do image extraction"):
    """Make one document check fail the way a missing package fails."""
    from pypdf.errors import DependencyError

    import before_you_send.run as run

    def needs_a_package_we_do_not_have(*args, **kwargs):
        raise DependencyError(message)

    monkeypatch.setattr(run, "DOCUMENT_CHECKS", (needs_a_package_we_do_not_have,))


def test_a_check_that_could_not_load_does_not_exit_clean(
    clean_document, monkeypatch, capsys
):
    """A run missing a check is a run with a hole in it, whatever it printed.

    Exit 0 is the only code a pipeline reads as "send it". A check that never ran
    cannot have found anything, and the code has to say so or the honest NOT
    CHECKED entry is visible to a person and invisible to the script that gates
    the send.
    """
    _check_missing_its_library(monkeypatch)
    assert main([clean_document]) == EXIT_TOOL_INCOMPLETE


def test_a_check_that_could_not_load_outranks_the_findings_code(
    fake_redaction, monkeypatch, capsys
):
    """Exit 1 and exit 3 are both "do not send". Only one of them is news.

    A pipeline that gets 1 has a report it can act on. A pipeline that gets 3 has
    a report with a hole in it and an install to fix, and that is the fact that
    would otherwise be lost, because the findings are printed either way.
    """
    _check_missing_its_library(monkeypatch)
    assert main([fake_redaction]) == EXIT_TOOL_INCOMPLETE


def test_a_check_that_could_not_load_survives_fail_on_never(
    fake_redaction, monkeypatch, capsys
):
    """--fail-on chooses which findings matter. A missing package is not a finding."""
    _check_missing_its_library(monkeypatch)
    assert main([fake_redaction, "--fail-on", "never"]) == EXIT_TOOL_INCOMPLETE


def test_a_check_that_could_not_load_still_prints_everything_that_did_run(
    fake_redaction, monkeypatch, capsys
):
    """The opposite failure: throwing away a good report because one check is short.

    The document was opened and read. Every other check ran. Refusing to print
    that would be the tool deciding a partial truth is worth less than nothing.
    """
    _check_missing_its_library(monkeypatch)
    main([fake_redaction])
    out = capsys.readouterr().out
    # The reason is word wrapped to the report width, so the sentence is read back
    # the way a person reads it rather than the way the lines happen to fall.
    flowed = " ".join(out.split())

    assert "covered_text" in out
    assert "NOT CHECKED" in out
    assert "Pillow is required to do image extraction" in flowed
    assert "Your file is not the problem" in flowed
    assert "DependencyError" not in out


def test_a_check_that_could_not_load_says_so_on_stderr_too(
    clean_document, monkeypatch, capsys
):
    """Somebody reading only the error stream must not see silence."""
    _check_missing_its_library(monkeypatch)
    main([clean_document])
    err = capsys.readouterr().err

    assert "This tool is missing something it needs" in err
    assert "not a clean result" in err
    assert "truncated" not in err
    assert "damaged" not in err
    assert "DependencyError" not in err


def test_json_says_a_package_was_missing_in_a_field_a_script_can_read(
    clean_document, monkeypatch, capsys
):
    """A script reading JSON should not have to match on prose to learn this."""
    _check_missing_its_library(monkeypatch)
    main([clean_document, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["missing_packages"] == ["Pillow is required to do image extraction"]
    assert any("not installed" in item["reason"] for item in payload["not_checked"])


def test_json_on_an_ordinary_run_reports_no_missing_packages(fake_redaction, capsys):
    main([fake_redaction, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["missing_packages"] == []

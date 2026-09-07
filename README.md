# Before You Send

Reads a PDF and tells you what is still inside it that you may not mean to send.

```
$ before-you-send settlement.pdf

Before You Send — settlement.pdf
========================================================================
Read 1 page(s). 9 finding(s): 6 high, 2 medium, 1 low.
1 place(s) could not be seen into.

HIGH
------------------------------------------------------------------------
HIGH    page 1  (72, 657)-(258, 669)  [covered_text]
        34 characters of text have an opaque shape painted over them,
        covering about 100% of the run.

HIGH    page 1  (72, 627)-(312, 639)  [invisible_text]
        40 characters are set to render mode 3, which draws nothing.

HIGH    document  attachments  [embedded_files]
        1 whole file(s) are attached inside this document.

COULD NOT SEE
------------------------------------------------------------------------
  - page 1  (70, 554)-(290, 570)
      an image was painted over 1 run(s) of text. Whether the image
      hides that text, or is simply drawn across it, cannot be decided
      without looking at the picture, which this tool does not do.
```

A black box drawn over a name does not remove the name. The characters are still
in the file, and anyone can select them, copy them, or pull them out in one
command. The same is true of a page you deleted and saved, a comment you thought
nobody would open, and the spreadsheet somebody attached to the document six
versions ago.

None of this is exotic. It is the ordinary result of treating a PDF as a picture
of a document when it is actually a container.

This tool does not tell you a file is safe to send. It tells you what it found,
where it found it, and — separately, and always — where it could not see.

## Install

Python 3.9 or newer. The only dependency is `pypdf`.

```bash
git clone https://github.com/Waiga/before-you-send
cd before-you-send
pip install -e .
```

It is not published to PyPI, so `pip install before-you-send` will not work.
Install it from source, as above.

## Use

```bash
before-you-send letter.pdf                  # where things are, not what they say
before-you-send letter.pdf --verbose        # add why each finding matters
before-you-send letter.pdf --show-content   # include what was actually found
before-you-send letter.pdf --format json    # for scripts
```

Exit codes, for a pipeline: `0` nothing at or above the threshold, `1` something
found, `2` the file could not be read. The threshold is `--fail-on high|medium|low|never`
and defaults to `medium`.

Try it on the examples, which the repository generates rather than stores:

```bash
python examples/make_examples.py
before-you-send examples/leaky-letter.pdf --verbose
before-you-send examples/careful-letter.pdf
```

## What it checks

| Check | Level | What it means |
|---|---|---|
| `covered_text` | high | Something opaque was painted over text *after* the text. The text was never removed. |
| `invisible_text` | high | Text set to a render mode that draws nothing. Extracts normally. |
| `text_matching_background` | high | Text the same colour as the page or the shape behind it. |
| `unapplied_redaction_marks` | high | Passages marked for redaction where the redaction was never applied. |
| `embedded_files` | high | Whole files carried inside the document. |
| `active_content` | high | Scripts, launch actions, or automatic form submissions. |
| `form_field_values` | high / medium | Form fields still holding what somebody typed. High when the field is hidden. |
| `earlier_versions_retained` | high / medium / low | Previous versions of the file kept inside it. Low when a signature explains it. |
| `text_outside_page` | medium | Text parked entirely outside the visible page. |
| `hidden_layers` | medium | Layers switched off. The content is still there. |
| `annotation_authors` | medium | Comments and markup, and the names attached to them. |
| `document_author` | medium | A named author in the document properties. |
| `build_path_in_metadata` | medium | A filesystem path left in the properties, naming a user or a client folder. |
| `xmp_metadata` | medium / low | A second author record, which editing tools often forget to update. |
| `descriptive_metadata` | low | Title, subject or keywords — frequently the original filename. |
| `encryption_without_a_password` | low | Restrictions the file asks for but cannot enforce. |

## What it does not check

Stated in the output of every run, not just here.

**Anything inside a picture.** Images are not examined. Text in a screenshot, a
scanned page, or a chart saved as an image is invisible to this tool. A document
flattened into pictures will look empty here and will not be.

**Whether what it found is actually a secret.** It reports that something is
present and not visible. Whether that matters is a judgement about the content,
and the tool does not read for meaning.

**Whether the visible text should be visible.** Content plainly on the page is
never a finding, however confidential. This looks only for what a sender does not
know is there.

When an image is painted over text, the tool says so as a **blind spot** — a
located place it can prove something is drawn at and cannot see under. Blind
spots are printed separately from findings and are never counted as findings,
because a report that says "no problems" about a page it could not read is worse
than no report.

## How it tells a redaction from a design choice

This is the one thing worth explaining, because it is where a tool like this
usually becomes useless.

A black box over black text, and white heading text on a black bar, are the same
overlap. Geometry cannot separate them. What separates them is the order the two
things were painted, which the file records:

```
text, then box   ->  the box was put there to hide the text     reported
box, then text   ->  the box is a background the text sits on   not reported
```

That is a fact read out of the file, not a threshold that had to be tuned. The
test suite holds both cases as a matched pair, along with the other innocent
twins: an outlined box that covers nothing, a see-through highlight, a panel
clipping the end of a line, text bleeding off an edge, and a signature that
explains an extra revision. Each must stay silent, and a run of the suite that
loses one of them fails.

## Privacy

The file is read on your machine and nothing is sent anywhere. There is no
account, no API key, and no network call in the tool at all.

The report withholds what it found by default. You get `page 1 (72, 657)-(258, 669)`
and a character count, not the account number underneath. That is deliberate: the
report of a document you are worried about is itself the thing most likely to be
pasted into a chat window. Use `--show-content` when you actually want to see it.

It never writes to the file it is reading, and it has no repair mode. A tool that
silently strips something you needed is a data-loss tool wearing a safety label.

## How this compares

The detection here is not new. Several of these problems have been known for as
long as the format has existed, and there is good software for parts of it.

For **metadata specifically**, [ExifTool](https://exiftool.org/) reads and writes
it comprehensively, and [mat2](https://0xacab.org/jvoisin/mat2) removes it across
many formats. Both are mature, free, and better at that one job than this is.

For **covered and invisible text**, the tools that exist are mostly web services
you upload the document to — which is the wrong shape for a file you are worried
about — or paid consistency-checking add-ins sold to firms rather than people.
[pdfalyzer](https://pypi.org/project/pdfalyzer/) is free and local but aimed at
malware forensics, and it is GPL-licensed.

What this puts together in one place: local only, permissively licensed, one
dependency, content withheld by default, an exit code for CI, and a report that
separates what it found from what it could not see.

If a check here is wrong, or a document is misreported, that is the most useful
issue you can open.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

Every test fixture is built from literal bytes in `tests/pdfbuild.py`. No PDF is
committed to this repository, and none of the examples came from a real document.

## Licence

MIT.

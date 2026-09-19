# Before You Send

Reads a PDF and tells you what is still inside it that you may not mean to send.

```
$ before-you-send letter.pdf

Before You Send: letter.pdf
========================================================================
Read 1 page(s). 10 finding(s): 5 high, 4 medium, 1 low.
1 place(s) could not be seen into.

HIGH
------------------------------------------------------------------------
HIGH    page 1  (72, 657)-(257, 669)  [covered_text]
        34 characters of text have an opaque shape painted over them, covering 100% of the run.

HIGH    document  file structure  [earlier_versions_retained]
        The file contains 1 earlier version(s) of itself, kept in full alongside the current one.

HIGH    document  attachments  [embedded_files]
        1 whole file(s) are attached inside this document.

HIGH    page 1  (72, 627)-(277, 639)  [invisible_text]
        40 characters are set to render mode 3, which draws nothing on the page.

HIGH    page 1  (72, 607)-(190, 619)  [text_matching_background]
        21 characters are drawn in the same colour as the page itself, so nothing appears there.

[4 medium and 1 low finding omitted here]

COULD NOT SEE
------------------------------------------------------------------------
  - page 1  (70, 554)-(290, 570)
      an image was painted over 1 run(s) of text. Whether the image
      hides that text, or is simply drawn across it, cannot be decided
      without looking at the picture, which this tool does not do.

[the NOT CHECKED section, printed on every run, omitted here]
```

A black box drawn over a name does not remove the name. The characters are still
in the file, and anyone can select them, copy them, or pull them out in one
command. The same is true of a page you deleted and saved, a comment you thought
nobody would open, and the spreadsheet somebody attached to the document six
versions ago.

None of this is exotic. It is the ordinary result of treating a PDF as a picture
of a document when it is actually a container.

This tool does not tell you a file is safe to send. It tells you what it found,
where it found it and, separately and always, where it could not see.

One fact is reported once. Something painted in the same place on every page is a
header, a footer or a watermark, and printing it once per page buries the finding on
page 137 that actually matters. Every run also states how many pages are mostly
picture, findings or none, because a document flattened into images comes back with
nothing found and is not empty.

## Install

Python 3.9 or newer. It depends on `pypdf`, and on the `cryptography` package
that pypdf needs to open a file encrypted with AES. Both arrive with the install;
there is nothing to add by hand.

```bash
pip install before-you-send
```

Or from source:

```bash
git clone https://github.com/Waiga/before-you-send
cd before-you-send
pip install -e .
```

## Use

```bash
before-you-send letter.pdf                  # where things are, not what they say
before-you-send letter.pdf --verbose        # add why each finding matters
before-you-send letter.pdf --show-content   # include what was actually found
before-you-send letter.pdf --format json    # for scripts
```

Exit codes, for a pipeline: `0` nothing at or above the threshold, `1` something
found, `2` the file could not be read, `3` this tool is missing a package it needs,
so it read nothing and the file itself was never called into question. The threshold is `--fail-on high|medium|low|never`
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
| `text_clipped_away` | high | Text excluded by a clipping path, so none of it is drawn. |
| `text_too_small_to_read` | high | Text scaled to effectively zero size. |
| `text_outside_page` | medium | Text parked entirely outside the visible page. |
| `hidden_layers` | medium | Layers switched off. The content is still there. |
| `annotation_authors` | medium | Comments and markup, and the names attached to them. |
| `document_author` | medium | A named author in the document properties. |
| `build_path_in_metadata` | medium | A filesystem path left in the properties, naming a user or a client folder. |
| `xmp_metadata` | medium / low | A second author record, which editing tools often forget to update. |
| `descriptive_metadata` | low | Title, subject or keywords. Frequently the original filename. |
| `encryption_without_a_password` | low | Restrictions the file asks for but cannot enforce. |
| `scanned_text_layer` | low | Invisible text under a page-sized image: the searchable layer of a scan, reported so you know it extracts. |

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

**Runs of one or two characters.** Too short to carry a name, a number of
consequence, or a word, and on real documents almost always a plot marker, a table
rule or a mathematical glyph. Measured over 450 published PDFs they were 57% of
every covered-text finding and 100% of every "too small to read" one, and all of
them were wrong. The count of runs passed over is printed in every report, because a
threshold nobody is told about is just an undocumented bug.

**What text says, when a font gives no way to know.** A composite font addresses
glyphs by number. Where it carries no map from those numbers to characters, runs in
it are located and measured exactly and their text is not guessed at. Composite fonts
using an encoding other than Identity keep having their widths estimated, for the
same reason: a width read against the wrong glyph is worse than an admitted estimate.

When an image is painted over text, the tool says so as a **blind spot**: a
located place it can prove something is drawn at and cannot see under. The same
goes for a shape whose colour the file names indirectly, through a pattern or a
spot colour, where whether it conceals anything cannot be decided from the
drawing instructions at all. Blind spots are printed separately from findings and
are never counted as findings, because a report that says "no problems" about a
page it could not read is worse than no report.

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

Order alone is not enough, because a shape is not painted everywhere its path
reaches. Three things bound it, and all three had to be modelled before this was
usable on real documents:

- **a clipping path**, which trims everything drawn after it. Without it, every
  chart from matplotlib or a browser's print-to-PDF reports its own caption as a
  covered secret.
- **a form's bounding box**, a hard limit on what that form draws. Without it, a
  small logo stamp whose artwork is larger than its box appears to cover the page.
- **blending and soft masks**, which let what is underneath show through. A
  flattened highlighter mark is an opaque yellow rectangle drawn over text, and
  reading only its alpha value reports every highlight in a document.

The order is a fact from the file. The verdict is not purely a fact: it is gated
by a coverage threshold, an opacity threshold, a colour tolerance and, for any
font that does not declare its character widths (which includes Helvetica and
Times), an estimate of how wide a line of text really is. Where that estimate is
load-bearing the report says "about", and it is listed under what was not checked.

The test suite holds every innocent twin as a matched pair against the case it
resembles: an outlined box that covers nothing, a see-through highlight, a
multiply-blended highlighter, a panel clipping the end of a line, a clipped
chart, a bounded logo stamp, a spot-colour brand bar, a white caption on a
photograph, a scanned page's searchable text layer, text bleeding off an edge,
and a signature that explains an extra revision. Each must stay silent, and a run
that loses one of them fails.

## Against real documents

The suite passes, and that was never the question. A tool like this can be green on
every test it wrote for itself and still be useless on the first real file it meets,
so it was pointed at 931 published PDFs it had nothing to do with: the US Federal
Register, arXiv, gov.uk, the World Health Organization, US court filings, and
scanned FOIA releases from the FBI's reading room. Six producers, which matters more
than six sources: a Word document, a LaTeX paper and an InDesign report fail in
different ways.

**How this was measured.** Which 931 documents, where each came from and (the
part that matters most in this section) which of four measurement passes each
figure below belongs to: [`docs/corpus-manifest.md`](https://github.com/Waiga/before-you-send/blob/main/docs/corpus-manifest.md),
with the document list in [`docs/corpus/documents.tsv`](https://github.com/Waiga/before-you-send/blob/main/docs/corpus/documents.tsv).
The numbers here are not all from the same run, and the manifest says which is
which. It also records what was not kept, including 567 source URLs that a
collection script overwrote.

It found thirteen classes of defect. The first pass produced **4,280 findings across
450 documents, 3,126 of them HIGH**, and almost none of them worth reading.

| | before | after |
|---|---|---|
| findings, same 450 documents | 4,280 | 1,703 |
| of which HIGH | 3,126 | 954 |
| median per document | 6 | 3 |
| worst document | 604 | 177 |

Across the full 931, the median document now reports 3 findings and the 90th
percentile reports 4. Nothing crashed, timed out, or came back unreadable.

Four are worth naming, because none of them could have been found any other way:

**The check most likely to hide a real leak never ran.** `earlier_versions_retained`
began by asking the parsed trailer for `/Prev`. A parser only surfaces that key for a
classic cross-reference table, and every modern PDF (Word, Acrobat, InDesign,
Chrome, every linearized government file) uses a cross-reference stream instead, so
the check returned on its first line and never reached the byte walk written for
exactly this question. Measured over the 887 documents collected at that point, it
was silent on **256 of them**. Most of those are
linearization, which it knows how to excuse; 34 are retained earlier versions with no
benign explanation, and 5 are serious. Every fixture in the suite used a classic xref
table, so no test could have seen it.

**A border was being read as a block.** One 175-page government table produced
**8,638** covered-text findings, 96% of every covered-text finding across the 931
documents and 67% of every finding of any kind. Rendered, the page is an ordinary
Word table: white cells, black gridlines, entirely readable.
A word processor draws a cell edge as an outer outline and an inner one in a single
path; measured as one rectangle, a hollow frame becomes a solid block of ink over
everything inside it. That document now reports 4 findings, all true.

**Composite fonts were being guessed at.** A Type0 font addresses glyphs by number,
two bytes at a time, and keeps its widths on a descendant font. Read as though the
bytes were characters, a run measures about twice as wide as it is, and that width
is the denominator of the coverage fraction that decides whether a passage was
redacted. Twice too wide halves the coverage, drops it under the threshold, and the
finding never appears. On the Word and InDesign slice, documents relying on estimated
widths fell from 78% to 47%. That was measured on a 32-document sample of UK
government and WHO PDFs, first page only.

**One fact was being reported once per page.** The Federal Register prints a
typesetter's control line and an operator's account name in white in the margin of
every page. Both are real, and one of them names a person. Reported per page they
came to 62 HIGH findings on a 31-page notice and 232 on a 116-page one, which is the
same as reporting nothing: a genuine single-page leak could not have been found in
that. It now reports 3, and the two HIGH ones are true.

### What that does and does not establish

It establishes that the tool survives real-world PDFs, and it measures how often it
cries wolf. Every number above is a false-positive number.

It is much weaker evidence about the failure that actually hurts somebody, which is
the one where a document *is* leaking and the report says nothing. Ordinary published
documents are overwhelmingly documents where nobody tried to hide anything, so they
exercise that path barely at all.

So the corpus was also run through an independent check for it: every page extracted
with `pdftotext` and separately rendered and read with OCR, on the theory that text
which extracts but is not on the rendered page is text somebody cannot see. Across
450 documents that turned up two candidates, and both were OCR failing on dense
numeric tables rather than the tool missing anything. That is real evidence and it is
not proof. It is one independent check, on a population where concealment is rare.

Concretely: this has not been validated against a corpus of documents where people
actually attempted redaction and got it wrong. If you have one, that is the most
useful thing you could point this at.

### A second corpus, and a different question

Everything above is about false positives, over the 931 documents of 7 September
2026. This is a separate measurement over a separate corpus, and none of its
numbers belong to the section above.

On **19 September 2026** a new corpus was collected from four public APIs: 850
documents attempted, **838 read**, made up of 300 US Federal Register notices, 250
gov.uk publications, 147 WHO reports and 141 arXiv papers, 919 MB in all. The
question was not how often the tool cries wolf. It was how much of its own past a
published PDF actually keeps, asked as four questions, each sharper than the last:

1. does the file chain to an earlier cross-reference section at all
2. does `earlier_versions_retained` call that a HIGH finding
3. does any object actually exist in two versions inside the file
4. does any **page** point at a different content stream than it used to

The four answers are far apart, and only the last one means what a reader tends to
assume the first one means. **The tool answers the first two.** It does not separate
structural history from genuinely replaced page content, and nothing in this
repository should be read as claiming it does. Questions 3 and 4 are answered by
[`scripts/measure_history.py`](https://github.com/Waiga/before-you-send/blob/main/scripts/measure_history.py),
a second implementation that walks the bytes itself and imports nothing from this
package, precisely so the two can be checked against each other.

To reproduce it, rebuild the corpus and run one command:

```bash
python scripts/collect_urls.py fedreg urls_fedreg.tsv   # and govuk, who, arxiv
python scripts/download.py corpus/
python scripts/measure_history.py corpus/
```

The documents themselves are not in this repository and will not be: they are other
people's copyrighted material and close to a gigabyte of it. What is committed is
[`docs/corpus/history-corpus-2026-09-19.tsv`](https://github.com/Waiga/before-you-send/blob/main/docs/corpus/history-corpus-2026-09-19.tsv),
850 rows carrying the source, filename, size, SHA-256 and download URL of every one.
Unlike the 7 September manifest, every row here has its URL.

`measure_history.py` is committed exactly as it was run, reformatting included,
because a tidied copy is no longer the program that produced the numbers. That is
also why its `obj_dict` docstring records a bug in the measuring code rather than
quietly removing it: a fixed length read window ran off the end of short objects
into whatever was stored next, and a catalogue and two fonts were counted as
replaced pages until it was caught.

The same caution as above applies, and harder. These are published documents, and a
population where nobody was trying to conceal anything tells you very little about
the case where somebody was.

## Privacy

The file is read on your machine and nothing is sent anywhere. There is no
account, no API key, and no network call in the tool at all.

The report withholds what it found by default. You get `page 1 (72, 657)-(258, 669)`
and a character count, not the account number underneath. That is deliberate: the
report of a document you are worried about is itself the thing most likely to be
pasted into a chat window. Use `--show-content` when you actually want to see it.

Control characters in anything recovered from the document are stripped before
printing, so a hostile file cannot use its own title to repaint your terminal.

The report header echoes the path you gave it, which may itself name a client or
a matter. Worth knowing before pasting one.

It never writes to the file it is reading, and it has no repair mode. A tool that
silently strips something you needed is a data-loss tool wearing a safety label.

## How this compares

The detection here is not new. Several of these problems have been known for as
long as the format has existed, and there is good software for parts of it.

For **metadata specifically**, [ExifTool](https://exiftool.org/) reads and writes
it comprehensively, and [mat2](https://0xacab.org/jvoisin/mat2) removes it across
many formats. Both are mature, free, and better at that one job than this is.

For **covered and invisible text**, the tools that exist are mostly web services
you upload the document to (which is the wrong shape for a file you are worried
about) or paid consistency-checking add-ins sold to firms rather than people.
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

`tests/test_regressions.py` holds one test per defect found by deliberately
attacking the tool after the first suite was already passing. Most of those
defects were false positives on entirely ordinary documents, which is the failure
worth guarding hardest against.

`tests/test_corpus_defects.py` holds the tests for the thirteen defects found
afterwards, by running the finished tool over 931 real published PDFs it had never seen. Every one
of them names the document shape that produced it, and every one was checked to fail
without its fix. A test that passes either way is not a test.

## Licence

MIT.

## Author

[Waiga Arya](https://www.linkedin.com/in/waigaarya/), Director of Business Strategy and
Innovation at Sadaway Pvt. Ltd. These tools were built for my own operating problems first.

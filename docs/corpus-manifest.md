# Corpus manifest

Every number in the README's "Against real documents" section was produced
against the material described here. This document exists so that a stranger can
obtain the same material and check.

It matters more here than elsewhere in this repository, because that section is
**not one measurement**. It is four passes over four different document counts —
450, 887, 931 and smaller samples — and the README quotes figures from all of
them within a few paragraphs of each other. Section 3 is the mapping.

Where something was not recorded at the time, this document says so rather than
reconstructing it.

## 1. The corpus: 931 published PDFs

**What it is.** 931 PDFs collected from six public sources on **7 September
2026**, chosen for producer diversity rather than source count — a Word
document, a LaTeX paper, an InDesign report and a scanner fail in different
ways.

**The list.** [`docs/corpus/documents.tsv`](corpus/documents.tsv) — 931 rows
plus a header:

| column | meaning |
|---|---|
| `source` | which of the six families the document came from |
| `local_name` | the filename every result file refers to |
| `bytes` | size of the downloaded file |
| `sha256` | SHA-256 of the downloaded bytes, unmodified |
| `in_pass1_450` | whether it was in the 450-document first pass |
| `in_pass2_887` | whether it was in the 887-document second pass |
| `source_url` | the download URL, where it survives — see the warning below |

**The six sources, and how many documents each contributed:**

| `source` | what it is | documents |
|---|---|---|
| `govuk` | gov.uk publishing assets — mostly Word-produced | 320 |
| `fedreg` | US Federal Register notices — a GPO / Acrobat Distiller pipeline | 300 |
| `arxiv` | arXiv preprints — pdfTeX / LaTeX, matplotlib figures | 150 |
| `who` | World Health Organization publications — InDesign | 117 |
| `court` | US court filings via CourtListener RECAP | 29 |
| `scan` | scanned FOIA releases from the FBI Vault | 15 |
| | **total** | **931** |

The files were written to disk exactly as served, so `sha256` is directly
comparable against a fresh download. Nothing crashed, timed out or came back
unreadable across the 931.

### ⚠️ 567 of the 931 source URLs are not recoverable

The URL list was collected in stages, and a later collection script **wrote to
the same filename as the earlier one and overwrote it**. What survives:

| `source` | URLs recovered | of |
|---|---|---|
| `govuk` | 320 | 320 |
| `court` | 29 | 29 |
| `scan` | 15 | 15 |
| `arxiv` | **0** | 150 |
| `fedreg` | **0** | 300 |
| `who` | **0** | 117 |

For those 567 rows the `source_url` column is empty. It has been left empty
rather than reconstructed: a plausible-looking URL that is not the one actually
fetched would be worse than a blank.

**The WHO 117 are a partial exception.** Their download URLs are gone, but the
step before them survives: the collection resolved WHO IRIS *item UUIDs* into
PDF bitstream URLs, and the UUID list was written to a file the overwrite did
not touch. 200 item UUIDs survive, of which the first 120 were resolved and 117
yielded a PDF. So the WHO subset is re-derivable in principle by re-running the
resolution described below against those UUIDs. That path has not been walked
here, so treat it as a lead rather than a verified route; IRIS content URLs may
since have moved.

**What is still checkable about them.** The download script named every file
`<source>_<first 12 hex characters of SHA-1 of the URL>.pdf`. That rule is
stated here so a reader holding a candidate URL can test membership directly:

```bash
python3 -c 'import hashlib,sys; print(hashlib.sha1(sys.argv[1].encode()).hexdigest()[:12])' "<url>"
```

If the result appears in `local_name`, that URL is in the corpus; the `sha256`
column then says whether the bytes are still the same. So the corpus is not
enumerable for those three sources, but it *is* verifiable one document at a
time — and every figure in the README is a false-positive rate, for which
knowing the exact population matters more than being able to re-download it.

**The collection rules that produced them**, recorded even though the resulting
lists are gone, because they say what kind of population it is:

- `fedreg` — the Federal Register API, `documents.json`, `order=newest`, pages 1
  to 3 at 100 per page. So: the 300 most recently published notices as of 7
  September 2026.
- `arxiv` — the arXiv API, 25 most recent submissions in each of `cs.CR`,
  `econ.GN`, `stat.AP`, `physics.med-ph`, `math.PR` and `q-bio.QM`.
- `who` — WHO IRIS, `server/api/discover/search/objects`, four pages of 50, then
  each item's `ORIGINAL` bundle resolved to its first PDF bitstream through
  `server/api/core/items/<uuid>/bundles`. 200 items collected, the first 120
  attempted, 117 resolved.
- `govuk` — the gov.uk search API filtered to guidance and regulation, ordered
  by `-public_timestamp`, each result's content record read for PDF
  attachments. The resulting link list was shuffled with `random.seed(7)` and
  the first 320 taken.
- `court` — CourtListener RECAP search for `redacted`, four pages.
- `scan` — the FBI Vault RSS listing of file-type items, 200 per page.

Re-running `fedreg` or `arxiv` today returns a different set, because "most
recent" has moved. `govuk`'s seed is recorded but shuffles a list that has also
moved on. The manifest is the authority on which documents were used.

**Licence and redistribution.** US Federal Register notices, US court filings
and FBI FOIA releases are US Government works in the public domain; gov.uk
material is Open Government Licence v3.0; WHO publications are CC BY-NC-SA;
arXiv preprints carry per-paper licences chosen by their authors. **No document
is redistributed here.** The manifest carries names, sizes, hashes and such URLs
as survive.

## 2. The four measurement passes

| pass | documents | tool state | result file |
|---|---|---|---|
| 1 | 450 | pre-fix | `results.json` |
| 2 | 887 | after the first ten fixes | `results_fixed.json` |
| 3 | 931 | after the composite-font fix, **before** the border fix | *overwritten* |
| 4 | 931 | final | `results_final.json` |

Passes 1, 2 and 4 survive as working files on the author's machine. **Pass 3
does not**: the run that produced it wrote to the same filename as pass 4, which
later overwrote it. Its totals survive only as printed output in the harness
transcript of the session that produced it — `TOTAL 931`, `covered_text 8968`,
`total findings 12805`, worst document 8,642 findings. That is where the
README's 8,638 and its two percentages come from, and it is why they cannot be
re-derived from a file.

None of the four result files is published. They are working files, not
artefacts a third party can obtain.

## 3. Which figure came from which pass

This is the section to read before quoting anything from the README.

**The before-and-after table** is like for like: pass 1 against pass 4,
restricted on both sides to the same 450 documents. Every cell is a direct read.

| README row | before (pass 1) | after (pass 4, same 450) |
|---|---|---|
| findings, same 450 documents | 4,280 | 1,703 |
| of which HIGH | 3,126 | 954 |
| median per document | 6 | 3 |
| worst document | 604 | 177 |

**"Across the full 931, the median document now reports 3 findings and the 90th
percentile reports 4"** — pass 4, all 931. Its totals are 3,979 findings, 1,916
of them HIGH.

**The four named defects** each come from a different pass, and this is the part
the README does not make explicit:

- **`earlier_versions_retained` never ran** — "silent on **256 of them**", with
  34 unexplained retained revisions and 5 serious. **Pass 2, over 887
  documents.** The README says 887 for the silence figure, which is right.
- **A border read as a block** — "**8,638** covered-text findings, 96% of every
  covered-text finding across the 931 documents and 67% of every finding of any
  kind". **Pass 3, over 931 documents**, the overwritten one. The arithmetic
  behind the two percentages: 8,638 of 8,968 covered-text findings is 96.3%, and
  8,638 of 12,805 findings of every kind is 67.5%. That document is a 175-page
  gov.uk table; it reports 4 findings in pass 4.
- **Composite fonts guessed at** — "documents relying on estimated widths fell
  from 78% to 47%". A **32-document sample** of UK government and WHO PDFs,
  first page only. The README names this population.
- **One fact reported once per page** — 62 HIGH findings on a 31-page notice and
  232 on a 116-page one. Per-document counts, not corpus figures.

**"Measured over 450 published PDFs they were 57% of…"** (the one- and
two-character covered-text findings, earlier in the README) — pass 1.

**The OCR cross-check** — "Across 450 documents that turned up two candidates" —
pass 1's document set, checked independently by extracting each page with
`pdftotext` and separately rendering and OCR-reading it, on the theory that text
which extracts but is not on the rendered page is text somebody cannot see. Both
candidates were OCR failing on dense numeric tables.

**"Thirteen classes of defect"** — the count of defect classes the whole exercise
produced, and the subject of `tests/test_corpus_defects.py`. Not a per-pass
figure.

## 4. A note on figures already corrected

Commit `e9f257f` corrected two numbers in this section that the corpus run did
not support: the 8,638's two qualifiers had been stated against the wrong
denominator and the wrong pass, and a "470 worst document" figure appeared that
no pass ever produced. The composite-font result was given its population at the
same time. This manifest documents the corrected state; the commit message
records what was wrong and how it was found.

## 5. What a third party can and cannot reproduce

| claim | status |
|---|---|
| which 931 documents, as identities | **reproducible** — names, hashes and pass membership ship here |
| membership of a candidate URL | **checkable** — the SHA-1 filename rule is published |
| re-downloading the corpus | **partly** — 364 of 931 URLs survive; the 117 WHO documents have a re-derivation path; the 450 arXiv and Federal Register URLs do not |
| which pass each figure belongs to | **reproducible** — section 3 |
| the pass 1, 2 and 4 figures | backed by surviving result files, **not published** |
| the pass 3 figures, including 8,638 and its percentages | **not reproducible** — the result file was overwritten; transcript only |
| the measurement harness | **not published** |

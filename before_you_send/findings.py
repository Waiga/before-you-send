"""The vocabulary of a report: findings, blind spots, and honest gaps.

Three kinds of thing come out of a run, and keeping them apart is the whole point.

A *finding* is something the tool located and can describe.
A *blind spot* is a specific place the tool can see something at, but cannot see
under or into. It is not a finding and must never be counted as one.
An *unchecked* item is a whole class of thing this tool does not examine at all.

A tool that collapses the second and third into "no problems found" is lying, and
this file exists so that cannot happen by accident.

Cutting across all three is a fourth question: whose fault the gap is. Almost
always it is nobody's, because the tool was built not to look there. Sometimes it
is ours, because a package we depend on is not installed and a check could not
run. That case gets its own wording and its own field, because the default way of
describing a gap reads as a statement about the document, and here that reading is
false.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    """How much a finding should worry someone about to send the file.

    HIGH   content a reader could recover that the sender probably believes is gone
    MEDIUM content that is present and readable, and is usually meant to be private
    LOW    a trace that identifies a person or a tool without exposing content
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {"high": 3, "medium": 2, "low": 1}[self.value]


@dataclass(frozen=True)
class Finding:
    """One checkable observation, anchored to a place in the document.

    ``detail`` describes structure and must never carry the recovered content.
    Anything that would reproduce what was hidden belongs in ``sample``, which is
    withheld unless the caller explicitly asks for it. The report is the thing most
    likely to be pasted into a chat window, so it defaults to saying where, not what.
    """

    check: str
    level: Level
    page: str
    location: str
    summary: str
    detail: str = ""
    sample: str | None = None

    def as_dict(self, show_content: bool = False) -> dict:
        out = {
            "check": self.check,
            "level": self.level.value,
            "page": self.page,
            "location": self.location,
            "summary": self.summary,
        }
        if self.detail:
            out["detail"] = self.detail
        if show_content and self.sample is not None:
            out["sample"] = self.sample
        return out


@dataclass(frozen=True)
class Blindspot:
    """A located region the tool knows is there and cannot see under.

    An image covering text is the ordinary case. The tool can prove something is
    drawn there and cannot read what is beneath it. Reporting that as clean would
    be the single most dangerous thing this tool could do.
    """

    page: str
    location: str
    reason: str

    def as_dict(self) -> dict:
        return {"page": self.page, "location": self.location, "reason": self.reason}


@dataclass(frozen=True)
class Unchecked:
    """A whole class of thing the tool deliberately does not examine."""

    topic: str
    reason: str

    def as_dict(self) -> dict:
        return {"topic": self.topic, "reason": self.reason}



_DIGITS = re.compile(r"\d+")


def _shape(sample: str | None) -> str | None:
    """A recovered string with its numbers taken out.

    Page furniture is rarely identical page to page: a footer carries a page
    number, a typesetter's control line carries a frame counter, a stamp carries a
    date. Keying on the exact string leaves one finding per page for what is
    plainly one piece of boilerplate — in testing, a 31-page notice still reported
    31 copies of the same footer after identical repeats had already been folded.
    Numbers are the part that varies, so they are what the key ignores.

    This is deliberately not clever. Two genuinely different passages that differ
    only in their digits, at identical coordinates on different pages, are folded
    together — and that is the right answer too, because it says the same thing is
    covered in the same place throughout. Every distinct string is kept, so
    --show-content still shows what each page actually held.
    """
    if sample is None:
        return None
    return _DIGITS.sub("#", sample)


def collapse(findings: list[Finding], pages_read: int = 0) -> list[Finding]:
    """Fold a finding repeated verbatim in the same place on many pages into one.

    A header, a footer, a watermark or a typesetter's control line is one fact
    about a document, not one fact per page. Reported per page it buries the
    single-page finding that actually matters. A 31-page government notice in
    testing produced 62 HIGH lines for two facts, and the worst case in the same
    corpus produced 232 for two; a real leak on a single page of that document
    could not have been found in the output.

    Repetition is evidence in its own right, so the collapsed finding says how
    many pages carry it. Something painted in the same place on every page is
    page furniture, which is a different thing from a passage somebody tried to
    hide, and the reader needs to be able to tell them apart at a glance.

    Only findings that are identical in check, level, location, wording and
    recovered content are folded together. Two different passages that merely
    happen to share a check stay separate, because they are separate facts.
    """
    groups: dict = {}
    for finding in findings:
        key = (
            finding.check,
            finding.level,
            finding.location,
            finding.summary,
            finding.detail,
            _shape(finding.sample),
        )
        groups.setdefault(key, []).append(finding)

    out: list[Finding] = []
    for members in groups.values():
        first = members[0]
        if len(members) == 1:
            out.append(first)
            continue
        pages = {m.page for m in members}
        count = len(pages)
        if pages_read and count >= pages_read:
            where, tail = f"all {count} pages", "on every page of the document"
        else:
            where, tail = f"{count} pages", f"in the same place on {count} pages"
        samples = [m.sample for m in members if m.sample is not None]
        distinct = list(dict.fromkeys(samples))
        out.append(
            Finding(
                check=first.check,
                level=first.level,
                page=where,
                location=first.location,
                summary=f"{first.summary} The same thing appears {tail}.",
                detail=(
                    first.detail
                    + " It repeats page after page in the same position, which is "
                    "where a header, a footer, a watermark or a typesetter's "
                    "control line lives. That does not make it harmless. It is "
                    "still in the file and it still extracts, but it is one piece of "
                    "boilerplate rather than something hidden on a particular page."
                ).strip(),
                sample=" | ".join(distinct) if distinct else first.sample,
            )
        )
    return out


def missing_package_reason(requirement: str, consequence: str) -> str:
    """One sentence for a gap that is the tool's fault, in the tool's own voice.

    Three things have to be in it and one thing has to be out of it.

    In: that the document is not what is wrong, because that is the accusation
    this whole class of message exists to stop making; what is missing, in the
    words of whatever asked for it; and how to get it.

    Out: the name of the exception class. "DependencyError" is not information a
    person can act on. It is the tool talking to itself in front of a reader who
    came here to find out whether a file is safe to send.

    Also out: any promise that pip will fix it. Usually it will, and it is offered
    as the usual answer. But not everything pypdf asks for is a Python package.
    One of the two things it can ask for by name is the jbig2dec binary, and
    telling somebody to pip install their way to a system binary sends them round
    a loop that cannot close. What is named is named; what to type is a suggestion.
    """
    # The requirement arrives as pypdf's own sentence and the consequence is
    # written at the call site, so the join between them is the one place the two
    # can read as one badly punctuated run-on. Capitalised here rather than at
    # every call site, because there are five of them and only one has to be
    # forgotten for the report to look sloppy at exactly the moment it is asking
    # to be trusted.
    consequence = consequence[:1].upper() + consequence[1:]
    return (
        "Your file is not the problem. Something this tool needs is not installed, "
        f"and it could not run without it: {requirement}. {consequence}. Install "
        "what it needs and run this again. For a Python package that usually means "
        "pip install --upgrade before-you-send."
    )


@dataclass
class Report:
    """Everything one run learned about one file."""

    path: str
    findings: list[Finding] = field(default_factory=list)
    blindspots: list[Blindspot] = field(default_factory=list)
    unchecked: list[Unchecked] = field(default_factory=list)
    pages_read: int = 0
    short_runs: int = 0
    picture_pages: int = 0
    missing_packages: list = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def note_blindspot(self, page: str, location: str, reason: str) -> None:
        self.blindspots.append(Blindspot(page, location, reason))

    def note_unchecked(self, topic: str, reason: str) -> None:
        self.unchecked.append(Unchecked(topic, reason))

    def note_missing_package(self, topic: str, requirement: str, consequence: str) -> None:
        """Record something this installation could not look at for want of a package.

        This is the fourth kind of gap and it is not like the other three. A
        finding, a blind spot and an unchecked topic are all statements about the
        document. This one is a statement about the tool, and the difference
        matters more here than anywhere else in the report: told badly, it sends
        somebody to hunt for a fault in a file that does not have one.

        It is filed as an unchecked topic because that is where a reader looks for
        what was not examined, and recorded separately as well, because a script
        reading the exit code or the JSON has to be able to learn it without
        matching on prose.
        """
        self.missing_packages.append(requirement)
        self.note_unchecked(topic, missing_package_reason(requirement, consequence))

    def note_missing_package_blindspot(
        self, page: str, location: str, requirement: str, consequence: str
    ) -> None:
        """The same fact, where the gap is a place on a page rather than a topic.

        A page whose drawing instructions could not be read is a place the tool
        could not see into, which is what a blind spot is, and it is counted in the
        header line that says so. Only the reason changes: it names the package
        instead of naming the exception that carried the news.
        """
        self.missing_packages.append(requirement)
        self.note_blindspot(page, location, missing_package_reason(requirement, consequence))

    def note_short_run(self) -> None:
        """Record that a run was passed over for being one or two characters long."""
        self.short_runs += 1

    def sorted_findings(self) -> list[Finding]:
        """What the reader sees: one entry per distinct fact, worst first.

        Repetition is folded here rather than in each check, so a check stays a
        statement about one run of text and does not have to know about the rest
        of the document. Everything a check reported is still in ``findings``.
        """
        return sorted(
            collapse(self.findings, self.pages_read),
            key=lambda f: (-f.level.rank, f.check, f.page, f.location),
        )

    def counts(self) -> dict[str, int]:
        """Counted the way they are printed, so the header cannot contradict the body."""
        counts = {"high": 0, "medium": 0, "low": 0}
        for f in self.sorted_findings():
            counts[f.level.value] += 1
        return counts

    def worst_level(self) -> Level | None:
        if not self.findings:
            return None
        return max((f.level for f in self.findings), key=lambda level: level.rank)

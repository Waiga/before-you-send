"""The vocabulary of a report: findings, blind spots, and honest gaps.

Three kinds of thing come out of a run, and keeping them apart is the whole point.

A *finding* is something the tool located and can describe.
A *blind spot* is a specific place the tool can see something at, but cannot see
under or into. It is not a finding and must never be counted as one.
An *unchecked* item is a whole class of thing this tool does not examine at all.

A tool that collapses the second and third into "no problems found" is lying, and
this file exists so that cannot happen by accident.
"""

from __future__ import annotations

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


@dataclass
class Report:
    """Everything one run learned about one file."""

    path: str
    findings: list[Finding] = field(default_factory=list)
    blindspots: list[Blindspot] = field(default_factory=list)
    unchecked: list[Unchecked] = field(default_factory=list)
    pages_read: int = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def note_blindspot(self, page: str, location: str, reason: str) -> None:
        self.blindspots.append(Blindspot(page, location, reason))

    def note_unchecked(self, topic: str, reason: str) -> None:
        self.unchecked.append(Unchecked(topic, reason))

    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (-f.level.rank, f.check, f.page, f.location),
        )

    def counts(self) -> dict[str, int]:
        counts = {"high": 0, "medium": 0, "low": 0}
        for f in self.findings:
            counts[f.level.value] += 1
        return counts

    def worst_level(self) -> Level | None:
        if not self.findings:
            return None
        return max((f.level for f in self.findings), key=lambda level: level.rank)

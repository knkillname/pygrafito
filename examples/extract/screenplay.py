# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Extract aggregate cast and place graphs from local screenplay files.

The adapter never copies dialogue or action text into its output. It reads a caller-supplied file
and emits handles, weights, counts, and a ``basis`` property only.
"""

import argparse
import collections
import dataclasses
import itertools
import json
import pathlib
import re
import shutil
import subprocess
import typing

from pygrafito import PygrafitoError


class ExtractionError(PygrafitoError):
    """Raised when a source file cannot be parsed."""


@dataclasses.dataclass(frozen=True, slots=True)
class Pair:
    """One weighted pair between two characters.

    Parameters
    ----------
    source : str
        First character handle.
    target : str
        Second character handle.
    weight : int
        Number of shared scenes, pages, windows, or turns.
    """

    source: str
    target: str
    weight: int


@dataclasses.dataclass(frozen=True, slots=True)
class Transition:
    """One weighted transition between two places.

    Parameters
    ----------
    source : str
        Place the scene leaves.
    target : str
        Place the next scene enters.
    weight : int
        Number of transitions.
    """

    source: str
    target: str
    weight: int


@dataclasses.dataclass(frozen=True, slots=True)
class Extraction:
    """Aggregate result of one source file.

    Parameters
    ----------
    characters : tuple[str, ...]
        Character handles found in the source.
    co_occurrence : tuple[Pair, ...]
        Weighted co-occurrence pairs.
    turns : tuple[Pair, ...]
        Weighted speaker transitions.
    places : tuple[str, ...]
        Place handles found in the source.
    transitions : tuple[Transition, ...]
        Weighted place transitions.
    basis : str
        How co-occurrence was measured.
    """

    characters: tuple[str, ...]
    co_occurrence: tuple[Pair, ...]
    turns: tuple[Pair, ...]
    places: tuple[str, ...] = ()
    transitions: tuple[Transition, ...] = ()
    basis: str = "shared_scene"

    def cast_document(self) -> dict[str, object]:
        """Return a ``cast``-shaped document.

        Returns
        -------
        dict[str, object]
            Nodes and relationships using the example dataset schema.
        """
        nodes = [
            {
                "key": character,
                "labels": ["Character"],
                "properties": {"designation": character.replace("-", " ").title()},
            }
            for character in self.characters
        ]
        relationships: list[dict[str, object]] = [
            {
                "from": pair.source,
                "to": pair.target,
                "labels": ["SHARES_SCENE"],
                "directed": False,
                "properties": {"weight": pair.weight, "basis": self.basis},
            }
            for pair in self.co_occurrence
        ]
        relationships.extend(
            {
                "from": pair.source,
                "to": pair.target,
                "labels": ["SPEAKS_AFTER"],
                "directed": True,
                "properties": {"weight": pair.weight, "basis": "dialogue_turn"},
            }
            for pair in self.turns
        )
        return {
            "name": "extracted-cast",
            "revision": 1,
            "nodes": nodes,
            "relationships": relationships,
        }

    def places_document(self) -> dict[str, object]:
        """Return a ``places``-shaped document.

        Returns
        -------
        dict[str, object]
            Nodes and transitions using the example dataset schema.
        """
        nodes = [
            {
                "key": place,
                "labels": ["Place"],
                "properties": {"designation": place.replace("-", " ").title()},
            }
            for place in self.places
        ]
        relationships = [
            {
                "from": transition.source,
                "to": transition.target,
                "labels": ["NEXT_LOCATION"],
                "directed": True,
                "properties": {"weight": transition.weight, "basis": "scene_transition"},
            }
            for transition in self.transitions
        ]
        return {
            "name": "extracted-places",
            "revision": 1,
            "nodes": nodes,
            "relationships": relationships,
        }


class Screenplay:
    """Extract aggregates from a formatted screenplay."""

    HEADING: typing.ClassVar[re.Pattern[str]] = re.compile(
        r"^\s*(?:\d+\s{2,})(?P<place>[A-Z][A-Z0-9 .'&/-]+?)\s{2,}\d+\s*$"
    )
    CUE: typing.ClassVar[re.Pattern[str]] = re.compile(r"^\s{5,}(?P<name>[A-Z][A-Z0-9 .'#-]*?)\s*$")
    GENERIC: typing.ClassVar[frozenset[str]] = frozenset(
        {
            "BOY",
            "GIRL",
            "KID",
            "MAN",
            "WOMAN",
            "VOICE",
            "GUARD",
            "GUARDS",
            "WARRIOR",
            "LIEUTENANT",
            "PROGRAM",
            "PROGRAMS",
            "SCREEN",
            "CROWD",
            "COMPUTER",
            "RADIO",
            "ANNOUNCER",
            "HEAD GUARD",
        }
    )
    PLACES: typing.ClassVar[tuple[tuple[tuple[str, ...], str], ...]] = (
        (("SOLAR SAILER",), "solar-sailer"),
        (("I/O TOWER", "I/0 TOWER", "1/0 TOWER"), "io-tower"),
        (("VIDEO ARCADE", "ARCADE"), "video-arcade"),
        (("LASER",), "laser-lab"),
        (("GAME GRID",), "game-grid"),
        (("TRAINING",), "training-arena"),
        (("MAZE",), "maze"),
        (("CITY",), "city"),
        (("CELL",), "holding-cell"),
        (("TANK",), "tank"),
        (("DILLINGER",), "dillingers-office"),
        (("ALAN",), "alans-office"),
        (("BACK ROOM",), "flynns-back-room"),
        (("HELIPORT",), "heliport"),
        (("ICOM", "ENCOM"), "encom-building"),
        (("REAL WORLD",), "real-world"),
        (("ELECTRONIC WORLD",), "the-grid"),
    )

    @classmethod
    def extract(cls, path: str | pathlib.Path) -> Extraction:
        """Extract cast and place aggregates from a screenplay.

        Parameters
        ----------
        path : str | pathlib.Path
            Screenplay file.

        Returns
        -------
        Extraction
            Aggregate result without dialogue or action text.

        Raises
        ------
        ExtractionError
            If the file cannot be read or no characters are found.
        """
        source = pathlib.Path(path)
        if not source.exists():
            message = f"screenplay does not exist: {source}"
            raise ExtractionError(message)
        scenes: list[tuple[str | None, set[str]]] = []
        current_place: str | None = None
        current_characters: set[str] = set()
        characters: list[str] = []
        turns: list[str] = []
        places: list[str] = []
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
            heading = cls.HEADING.match(line)
            if heading:
                if current_place is not None or current_characters:
                    scenes.append((current_place, current_characters))
                current_place = cls._place(heading.group("place"))
                if current_place is not None:
                    places.append(current_place)
                current_characters = set()
                continue
            cue = cls.CUE.match(line)
            if cue:
                name = cue.group("name").strip()
                if name in cls.GENERIC:
                    continue
                handle = cls._handle(name)
                if handle not in characters:
                    characters.append(handle)
                current_characters.add(handle)
                turns.append(handle)
        if current_place is not None or current_characters:
            scenes.append((current_place, current_characters))
        if not characters:
            message = f"no character cues found in {source}"
            raise ExtractionError(message)
        co_occurrence: collections.Counter[tuple[str, str]] = collections.Counter()
        for _place, present in scenes:
            for first, second in itertools.combinations(sorted(present), 2):
                co_occurrence[(first, second)] += 1
        transitions: collections.Counter[tuple[str, str]] = collections.Counter()
        for (first, _), (second, _) in itertools.pairwise(scenes):
            if first is not None and second is not None and first != second:
                transitions[(first, second)] += 1
        return Extraction(
            characters=tuple(characters),
            co_occurrence=cls._pairs(co_occurrence),
            turns=cls._pairs(cls._turn_counter(turns)),
            places=tuple(dict.fromkeys(places)),
            transitions=cls._transitions(transitions),
            basis="shared_scene",
        )

    @classmethod
    def _place(cls, heading: str) -> str | None:
        """Map a scene heading to a place handle.

        Parameters
        ----------
        heading : str
            Uppercase heading text.

        Returns
        -------
        str | None
            Place handle, or ``None`` when the heading is unrecognized.
        """
        upper = heading.upper()
        for needles, handle in cls.PLACES:
            if any(needle in upper for needle in needles):
                return handle
        return None

    @classmethod
    def _handle(cls, name: str) -> str:
        """Convert a cue to a stable handle.

        Parameters
        ----------
        name : str
            Cue text.

        Returns
        -------
        str
            Lowercase handle.
        """
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    @classmethod
    def _pairs(cls, counter: collections.Counter[tuple[str, str]]) -> tuple[Pair, ...]:
        """Convert a pair counter to a sorted tuple.

        Parameters
        ----------
        counter : collections.Counter[tuple[str, str]]
            Pair weights.

        Returns
        -------
        tuple[Pair, ...]
            Sorted weighted pairs.
        """
        return tuple(
            Pair(source, target, weight) for (source, target), weight in sorted(counter.items())
        )

    @classmethod
    def _transitions(
        cls,
        counter: collections.Counter[tuple[str, str]],
    ) -> tuple[Transition, ...]:
        """Convert a transition counter to a sorted tuple.

        Parameters
        ----------
        counter : collections.Counter[tuple[str, str]]
            Transition weights.

        Returns
        -------
        tuple[Transition, ...]
            Sorted weighted transitions.
        """
        return tuple(
            Transition(source, target, weight)
            for (source, target), weight in sorted(counter.items())
        )

    @classmethod
    def _turn_counter(cls, turns: list[str]) -> collections.Counter[tuple[str, str]]:
        """Count adjacent speaker turns.

        Parameters
        ----------
        turns : list[str]
            Speaker handles in order.

        Returns
        -------
        collections.Counter[tuple[str, str]]
            Turn weights.
        """
        counter: collections.Counter[tuple[str, str]] = collections.Counter()
        for first, second in itertools.pairwise(turns):
            if first != second:
                counter[(first, second)] += 1
        return counter


class Transcript:
    """Extract aggregates from a plain speaker-prefixed transcript."""

    SPEAKER: typing.ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<name>[A-Z][A-Za-z0-9 .'-]{0,30}):\s"
    )
    GENERIC: typing.ClassVar[frozenset[str]] = frozenset(
        {
            "AI Voice",
            "Announcer",
            "Bodyguard",
            "Clerk",
            "Cop",
            "Crowd",
            "Female AI Voice",
            "Female Program",
            "Female Voice",
            "Guard",
            "Guard Program",
            "Gunman",
            "Interviewer",
            "Male AI Voice",
            "Male Program",
            "Male Voice",
            "News Anchor",
            "Security",
            "Security Guard",
            "Technician",
            "Techie",
        }
    )
    WINDOW: typing.ClassVar[int] = 8

    @classmethod
    def extract(cls, path: str | pathlib.Path) -> Extraction:
        """Extract cast aggregates from a transcript.

        Parameters
        ----------
        path : str | pathlib.Path
            Transcript file.

        Returns
        -------
        Extraction
            Aggregate result without dialogue text.

        Raises
        ------
        ExtractionError
            If the file cannot be read or no speaker cues are found.
        """
        source = pathlib.Path(path)
        if not source.exists():
            message = f"transcript does not exist: {source}"
            raise ExtractionError(message)
        sequence: list[str] = []
        characters: list[str] = []
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
            match = cls.SPEAKER.match(line)
            if match is None or match.group("name") in cls.GENERIC:
                continue
            handle = Screenplay._handle(match.group("name"))
            if handle not in characters:
                characters.append(handle)
            sequence.append(handle)
        if not sequence:
            message = f"no speaker cues found in {source}"
            raise ExtractionError(message)
        pairs: collections.Counter[tuple[str, str]] = collections.Counter()
        for start in range(len(sequence)):
            window = sorted(set(sequence[start : start + cls.WINDOW]))
            for first, second in itertools.combinations(window, 2):
                pairs[(first, second)] += 1
        return Extraction(
            characters=tuple(characters),
            co_occurrence=Screenplay._pairs(pairs),
            turns=Screenplay._pairs(Screenplay._turn_counter(sequence)),
            basis="dialogue_window",
        )


class PdfTranscript(Transcript):
    """Extract aggregates from a PDF transcript through ``pdftotext``."""

    PAGE: typing.ClassVar[re.Pattern[str]] = re.compile(r"Page \d+/\d+")

    @classmethod
    @typing.override
    def extract(cls, path: str | pathlib.Path) -> Extraction:
        """Extract cast aggregates from a PDF transcript.

        Parameters
        ----------
        path : str | pathlib.Path
            PDF file.

        Returns
        -------
        Extraction
            Aggregate result without dialogue text.

        Raises
        ------
        ExtractionError
            If ``pdftotext`` is unavailable, the file is unreadable, or no
            speaker cues are found.
        """
        source = pathlib.Path(path)
        if not source.exists():
            message = f"transcript does not exist: {source}"
            raise ExtractionError(message)
        if shutil.which("pdftotext") is None:
            message = (
                "pdftotext is required for PDF sources; install poppler-utils "
                "or export the PDF to text and use --format transcript"
            )
            raise ExtractionError(message)
        completed = subprocess.run(
            ["pdftotext", "-layout", str(source), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            message = f"pdftotext failed for {source}"
            raise ExtractionError(message)
        pages = cls.PAGE.split(completed.stdout)
        sequence: list[str] = []
        characters: list[str] = []
        pairs: collections.Counter[tuple[str, str]] = collections.Counter()
        for page in pages:
            present: list[str] = []
            for line in page.splitlines():
                match = cls.SPEAKER.match(line.strip())
                if match is None or match.group("name") in cls.GENERIC:
                    continue
                handle = Screenplay._handle(match.group("name"))
                if handle not in characters:
                    characters.append(handle)
                sequence.append(handle)
                if handle not in present:
                    present.append(handle)
            for first, second in itertools.combinations(sorted(present), 2):
                pairs[(first, second)] += 1
        if not sequence:
            message = f"no speaker cues found in {source}"
            raise ExtractionError(message)
        return Extraction(
            characters=tuple(characters),
            co_occurrence=Screenplay._pairs(pairs),
            turns=Screenplay._pairs(Screenplay._turn_counter(sequence)),
            basis="same_page",
        )


class Main:
    """Command-line entry point for the local extractor."""

    @classmethod
    def run(cls, argv: typing.Sequence[str] | None = None) -> int:
        """Extract one source and write aggregate JSON.

        Parameters
        ----------
        argv : typing.Sequence[str] | None, optional
            Argument list, by default ``None``.

        Returns
        -------
        int
            Process exit code.
        """
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("path", help="screenplay or transcript file")
        parser.add_argument(
            "--format",
            choices=("screenplay", "transcript", "pdf"),
            default="screenplay",
        )
        parser.add_argument("--kind", choices=("cast", "places"), default="cast")
        parser.add_argument("--output", help="destination JSON file")
        arguments = parser.parse_args(argv)
        adapters = {
            "screenplay": Screenplay,
            "transcript": Transcript,
            "pdf": PdfTranscript,
        }
        extraction = adapters[arguments.format].extract(arguments.path)
        document = (
            extraction.cast_document() if arguments.kind == "cast" else extraction.places_document()
        )
        payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if arguments.output:
            pathlib.Path(arguments.output).write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0


if __name__ == "__main__":
    raise SystemExit(Main.run())

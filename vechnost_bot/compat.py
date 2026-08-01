"""The couples compatibility test: content, scoring, and result assembly.

Deliberately imports neither FastAPI nor python-telegram-bot — the web API,
the bot, and the tests all use this module directly.

Individual answers go in; they never come out. The result carries zones,
verdict texts and question numbers, and nothing that would let one partner
reconstruct the other's answers.
"""

from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from .i18n import Language

CONTENT_DIR = Path(__file__).parent.parent / "data" / "library"

SPHERE_COUNT = 8
QUESTIONS_PER_SPHERE = 5
TOTAL_QUESTIONS = SPHERE_COUNT * QUESTIONS_PER_SPHERE

Zone = Literal["strength", "growth", "crisis"]


class Sphere(BaseModel):
    id: str
    title: str
    questions: list[str]
    synergy: str
    imbalance: str
    crisis: str


class SphereResult(BaseModel):
    id: str
    title: str
    zone: Zone
    verdict: str
    score: float
    divergent: list[int]


class AttentionEntry(BaseModel):
    sphere: SphereResult
    framing: str


class CompatResult(BaseModel):
    percent: int
    spheres: list[SphereResult]
    strengths: list[SphereResult]
    strengths_fallback: str | None = None
    attention: list[AttentionEntry]
    divergent_all: list[int]
    recommendation: str
    critical_blocks: list[str]


@cache
def _content(language: Language) -> dict:
    """Parsed content. Non-Russian falls back to the Russian file."""
    path = CONTENT_DIR / f"compat_{language.value}.yaml"
    if not path.exists():
        path = CONTENT_DIR / "compat_ru.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_spheres(language: Language = Language.RUSSIAN) -> list[Sphere]:
    """The eight spheres, in authored order."""
    return [Sphere(**s) for s in _content(language).get("spheres", [])]


def scale_labels(language: Language = Language.RUSSIAN) -> list[str]:
    """The five answer labels; index 0 is the value 1."""
    return list(_content(language).get("scale", []))


def _zone(avg_a: float, avg_b: float, max_gap: int) -> Zone:
    """
    Classify one sphere.

    Order matters: a single four-point gap is a crisis even when both
    averages are high, because it means the partners live in different
    realities on that question.
    """
    if (avg_a < 3 and avg_b < 3) or max_gap > 3:
        return "crisis"
    if avg_a >= 4 and avg_b >= 4:
        return "strength"
    return "growth"


def build_result(
    a: list[int], b: list[int], language: Language = Language.RUSSIAN
) -> CompatResult:
    """Compare two completed answer sets. Raises ValueError on bad input."""
    if len(a) != TOTAL_QUESTIONS or len(b) != TOTAL_QUESTIONS:
        raise ValueError(f"both answer sets must hold {TOTAL_QUESTIONS} answers")
    if not all(1 <= v <= 5 for v in (*a, *b)):
        raise ValueError("answers must be in 1..5")

    content = _content(language)
    spheres = load_spheres(language)
    results: list[SphereResult] = []

    for index, sphere in enumerate(spheres):
        start = index * QUESTIONS_PER_SPHERE
        slice_a = a[start:start + QUESTIONS_PER_SPHERE]
        slice_b = b[start:start + QUESTIONS_PER_SPHERE]
        avg_a = sum(slice_a) / QUESTIONS_PER_SPHERE
        avg_b = sum(slice_b) / QUESTIONS_PER_SPHERE
        gaps = [abs(x - y) for x, y in zip(slice_a, slice_b, strict=True)]
        zone = _zone(avg_a, avg_b, max(gaps))
        verdict = {
            "strength": sphere.synergy,
            "growth": sphere.imbalance,
            "crisis": sphere.crisis,
        }[zone]
        results.append(SphereResult(
            id=sphere.id,
            title=sphere.title,
            zone=zone,
            verdict=verdict,
            score=(avg_a + avg_b) / 2,
            # 1-based and global: sphere 8's questions are 36..40.
            divergent=[start + i + 1 for i, gap in enumerate(gaps) if gap >= 3],
        ))

    percent = round((sum(r.score for r in results) / len(results) - 1) / 4 * 100)

    strengths = sorted(
        [r for r in results if r.zone == "strength"],
        key=lambda r: r.score,
        reverse=True,
    )[:3]

    attention = [
        AttentionEntry(
            sphere=result,
            framing=content["framings"]["gap" if result.divergent else "both_low"],
        )
        for result in sorted(results, key=lambda r: r.score)[:2]
    ]

    divergent_all = sorted(n for r in results for n in r.divergent)

    return CompatResult(
        percent=percent,
        spheres=results,
        strengths=strengths,
        strengths_fallback=None if strengths else content["strengths_fallback"],
        attention=attention,
        divergent_all=divergent_all,
        recommendation=content["recommendation"].format(
            numbers=", ".join(str(n) for n in divergent_all)
        ),
        critical_blocks=[
            content["critical_block"].format(
                sphere=r.title,
                numbers=", ".join(str(n) for n in r.divergent) or "—",
            )
            for r in results if r.zone == "crisis"
        ],
    )

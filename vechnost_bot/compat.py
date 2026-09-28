"""The couples compatibility test: content, scoring, and result assembly.

Deliberately imports neither FastAPI nor python-telegram-bot — the web API,
the bot, and the tests all use this module directly.

Individual answers go in; they never come out. The result carries the
overall percent, each sphere's zone and verdict, and the numbers and texts
of the questions where the answers diverge, and nothing more: every other
part of it - which spheres are listed, in what order, with which framing -
is a function of those alone, never of a hidden score.

That is not the same as nothing being inferable, and the product says so
to the people taking the test. A partner who knows their own answer to a
divergent question knows the other's to within one or two values (a gap
of three or more from a 2 can only be a 5), a zone bounds the other's
average on that sphere, and the percent their overall total. What must
not happen is the result telling more than that.
"""

from functools import cache
from typing import Literal

import yaml
from pydantic import BaseModel

from .i18n import Language
from .paths import DATA

CONTENT_DIR = DATA / "library"

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
    """One sphere as a partner sees it.

    Deliberately carries no numeric score. A sphere's score is
    `(avg_a + avg_b) / 2` over five questions, so a partner who knows their
    own five answers could solve `sum_b = 10 * score - sum_a` exactly — at
    the boundaries (a sphere sum of 25) that pins every individual answer.
    The score stays inside `build_result` and feeds only `percent`; it used
    to order `strengths` and `attention` as well, and an order by score is
    the same leak one comparison at a time.
    """

    id: str
    title: str
    zone: Zone
    verdict: str
    divergent: list[int]


class AttentionEntry(BaseModel):
    sphere: SphereResult
    framing: str | None = None


class CompatResult(BaseModel):
    percent: int
    spheres: list[SphereResult]
    strengths: list[SphereResult]
    strengths_fallback: str | None = None
    attention: list[AttentionEntry]
    divergent_all: list[int]
    # The text of every divergent question, keyed by its global 1-based
    # number. "Обсудите вопросы №12, 14" is not actionable when neither
    # partner remembers what question 12 asked; both partners answered all
    # forty, so the texts reveal nothing. Texts only — never any answer.
    questions: dict[int, str]
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


def _both_low(avg_a: float, avg_b: float) -> bool:
    """True when both partners averaged under 3 on a sphere: one of the two
    ways into the crisis zone. Only `_zone` asks; see `_framing` for why the
    framing does not."""
    return avg_a < 3 and avg_b < 3


def _zone(avg_a: float, avg_b: float, max_gap: int) -> Zone:
    """
    Classify one sphere.

    Order matters: a single four-point gap is a crisis even when both
    averages are high, because it means the partners live in different
    realities on that question.
    """
    if _both_low(avg_a, avg_b) or max_gap > 3:
        return "crisis"
    if avg_a >= 4 and avg_b >= 4:
        return "strength"
    return "growth"


def _framing(result: SphereResult, framings: dict[str, str]) -> str | None:
    """Why a sphere that needs the talk needs it, read off the result alone.

    A divergent question means one partner answered 4 or 5 and the other 1
    or 2, so "one of you has enough here, the other does not" is true of
    that question whatever the averages. A crisis with no divergent
    question can only be two averages under 3 - a gap of four would have
    been divergent - so "both_low" says nothing the zone does not. A
    middling sphere with neither gets no sentence rather than a false one.

    It used to prefer "both_low" whenever both averages were under 3, which
    told a partner under 3 that the other was under 3 as well, on a sphere
    whose zone alone did not say so.
    """
    if result.divergent:
        return framings["gap"]
    if result.zone == "crisis":
        return framings["both_low"]
    return None


def build_result(a: list[int], b: list[int], language: Language = Language.RUSSIAN) -> CompatResult:
    """Compare two completed answer sets. Raises ValueError on bad input."""
    if len(a) != TOTAL_QUESTIONS or len(b) != TOTAL_QUESTIONS:
        raise ValueError(f"both answer sets must hold {TOTAL_QUESTIONS} answers")
    if not all(1 <= v <= 5 for v in (*a, *b)):
        raise ValueError("answers must be in 1..5")

    content = _content(language)
    spheres = load_spheres(language)
    results: list[SphereResult] = []
    # Parallel to `results`: the sphere's `(avg_a + avg_b) / 2`, kept out of
    # SphereResult because it is invertible (see its docstring). It feeds
    # `percent` and nothing else.
    scores: list[float] = []

    for index, sphere in enumerate(spheres):
        start = index * QUESTIONS_PER_SPHERE
        slice_a = a[start : start + QUESTIONS_PER_SPHERE]
        slice_b = b[start : start + QUESTIONS_PER_SPHERE]
        avg_a = sum(slice_a) / QUESTIONS_PER_SPHERE
        avg_b = sum(slice_b) / QUESTIONS_PER_SPHERE
        gaps = [abs(x - y) for x, y in zip(slice_a, slice_b, strict=True)]
        zone = _zone(avg_a, avg_b, max(gaps))
        verdict = {
            "strength": sphere.synergy,
            "growth": sphere.imbalance,
            "crisis": sphere.crisis,
        }[zone]
        results.append(
            SphereResult(
                id=sphere.id,
                title=sphere.title,
                zone=zone,
                verdict=verdict,
                # 1-based and global: sphere 8's questions are 36..40.
                divergent=[start + i + 1 for i, gap in enumerate(gaps) if gap >= 3],
            )
        )
        scores.append((avg_a + avg_b) / 2)

    percent = round((sum(scores) / len(scores) - 1) / 4 * 100)

    # Both lists follow the authored order of the spheres and hold every
    # sphere that qualifies. They used to be the three best-scoring
    # strengths and the two worst-scoring others: an order by score, like a
    # score, lets a partner who knows their own answers solve for the
    # other's, one comparison at a time (backend audit B-25).
    strengths = [result for result in results if result.zone == "strength"]

    # The attention block only ever holds spheres that are *not* a strength -
    # a sphere can't be both "where you are a team" and "worth talking
    # about" at once, and a couple with eight strong spheres does not get
    # told to go have a difficult conversation about their best area. If
    # none qualify, attention is empty and the caller renders nothing.
    attention = [
        AttentionEntry(sphere=result, framing=_framing(result, content["framings"]))
        for result in results
        if result.zone != "strength"
    ]

    divergent_all = sorted(n for r in results for n in r.divergent)
    flat_questions = [q for sphere in spheres for q in sphere.questions]

    return CompatResult(
        percent=percent,
        spheres=results,
        strengths=strengths,
        strengths_fallback=None if strengths else content["strengths_fallback"],
        attention=attention,
        divergent_all=divergent_all,
        questions={n: flat_questions[n - 1] for n in divergent_all},
        recommendation=content["recommendation"].format(
            numbers=", ".join(str(n) for n in divergent_all)
        ),
        critical_blocks=[
            content["critical_block"].format(
                sphere=r.title,
                numbers=", ".join(str(n) for n in r.divergent) or "—",
            )
            for r in results
            if r.zone == "crisis"
        ],
    )

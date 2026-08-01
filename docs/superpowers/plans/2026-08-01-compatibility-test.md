# Compatibility Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a 40-question compatibility test that two partners take separately, and that reports where they agree, where they diverge, and which questions to talk about — without ever showing either partner the other's answers.

**Architecture:** `compat.py` is the domain layer (content loading, scoring, result assembly) with no web or Telegram imports, mirroring `library.py`. `payments/compat_api.py` serves it over `/api/compat`, modelled on `payments/rooms.py`. State lives in a new `compat_tests` table with no TTL. The Mini App gets a fourth home button and four screens.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2 (async), Alembic, PyYAML, pytest (asyncio auto mode), vanilla JS in a single-file Mini App.

**Spec:** [`docs/superpowers/specs/2026-08-01-compatibility-test-design.md`](../specs/2026-08-01-compatibility-test-design.md)

**Content source:** [`docs/superpowers/specs/2026-08-01-compatibility-test-source-content.md`](../specs/2026-08-01-compatibility-test-source-content.md) — the 40 questions, 24 verdict texts, framings and blocks verbatim. Task 1 transcribes from it. Do not invent content and do not look for it elsewhere.

## Global Constraints

- Branch is `feature/compatibility-test`, cut from `master` at d900ca3. One commit per task.
- **Privacy is the feature's spine.** A partner's individual answers must never appear in any HTTP response, in any state, to anyone. Tests assert this directly; treat a leak as a failed task, not a rough edge.
- Question numbering is 1-based and load-bearing: the result tells couples to discuss "вопросы №…" by the authored numbers. Questions keep the positions the content source gives them.
- Pytest config lives in `pyproject.toml`. **Never** create a `pytest.ini` — a `[tool:pytest]` header there silently disables the pyproject config.
- **Lint:** CI runs `ruff check .`. The repo is already red — 527 errors on master, none of them ours. The bar is **zero new findings**, not a clean repo: `python -m ruff check <files you touched>` must be clean. Traps that cost fix rounds on the previous branch: never place an import anywhere but the top-of-file block (E402), and prefer `@cache` over `@lru_cache(maxsize=None)` (UP033).
- Content is Russian-only. Do not create `_en`/`_cs` content files. UI chrome strings still go in all three languages.
- YAML files are UTF-8, LF, two-space indent. Beware an unescaped `": "` inside a Russian sentence — YAML parses that item as a mapping instead of a string. Quote such items. This defect appeared three times on the previous branch.
- Run `pytest -q` once before every commit. The known pre-existing baseline is **7 failures and 186 errors** (a `ScopeMismatch` on a session-scoped `event_loop` fixture in `tests/conftest.py`, plus tests needing a local Redis). Environmental, not a regression. Anything else red is.
- Windows shell: the console mangles Cyrillic on stdout. A `UnicodeEncodeError` from `python -c` is an encoding artifact, not corrupt data — prefix with `PYTHONIOENCODING=utf-8` or write to a file.

---

### Task 1: Content and the scoring layer

The heart of the feature, and the only part that is pure computation. Built first so the arithmetic is proven before any HTTP or database code exists.

**Files:**
- Create: `data/library/compat_ru.yaml`
- Create: `vechnost_bot/compat.py`
- Test: `tests/test_compat.py`

**Interfaces:**
- Consumes: `vechnost_bot.i18n.Language`.
- Produces:
  - `SPHERE_COUNT = 8`, `QUESTIONS_PER_SPHERE = 5`, `TOTAL_QUESTIONS = 40`
  - `Zone` — `Literal["strength", "growth", "crisis"]`
  - `Sphere` — Pydantic model: `id: str`, `title: str`, `questions: list[str]`, `synergy: str`, `imbalance: str`, `crisis: str`
  - `load_spheres(language: Language = Language.RUSSIAN) -> list[Sphere]` — eight, in authored order
  - `scale_labels(language: Language = Language.RUSSIAN) -> list[str]` — five, index 0 is value 1
  - `SphereResult` — Pydantic model: `id`, `title`, `zone: Zone`, `verdict: str`, `score: float`, `divergent: list[int]`
  - `AttentionEntry` — Pydantic model: `sphere: SphereResult`, `framing: str | None`. **`framing` is genuinely optional.** A sphere reaches the attention block whenever it is one of the two lowest-scoring, which happens even to a couple with no problem anywhere. Neither authored framing is true about such a sphere, so it gets none. Serialized, the key is present with the JSON value `null` — consumers must guard, not assume a string.
  - `build_result(a: list[int], b: list[int], language: Language = Language.RUSSIAN) -> CompatResult`
  - `CompatResult` — Pydantic model: `percent: int`, `spheres: list[SphereResult]`, `strengths: list[SphereResult]`, `strengths_fallback: str | None`, `attention: list[AttentionEntry]`, `divergent_all: list[int]`, `recommendation: str`, `critical_blocks: list[str]`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the compatibility test's content and scoring."""

import pytest

from vechnost_bot.compat import (
    QUESTIONS_PER_SPHERE,
    SPHERE_COUNT,
    TOTAL_QUESTIONS,
    build_result,
    load_spheres,
    scale_labels,
)
from vechnost_bot.i18n import Language

SPHERE_IDS = [
    "values", "money", "communication", "intimacy",
    "home", "trust", "social", "empathy",
]


def test_content_loads_with_the_authored_shape():
    spheres = load_spheres(Language.RUSSIAN)
    assert [s.id for s in spheres] == SPHERE_IDS
    assert len(spheres) == SPHERE_COUNT
    for sphere in spheres:
        assert len(sphere.questions) == QUESTIONS_PER_SPHERE
        assert all(q.strip() for q in sphere.questions)
        assert sphere.title.strip()
        assert sphere.synergy.strip()
        assert sphere.imbalance.strip()
        assert sphere.crisis.strip()


def test_forty_questions_and_no_duplicates():
    flat = [q for s in load_spheres(Language.RUSSIAN) for q in s.questions]
    assert len(flat) == TOTAL_QUESTIONS == 40
    assert len(set(flat)) == 40


def test_five_scale_labels():
    labels = scale_labels(Language.RUSSIAN)
    assert len(labels) == 5
    assert all(label.strip() for label in labels)


def test_perfect_agreement_is_100_percent_and_all_strengths():
    result = build_result([5] * 40, [5] * 40)
    assert result.percent == 100
    assert all(s.zone == "strength" for s in result.spheres)
    assert result.divergent_all == []
    assert result.critical_blocks == []
    assert result.strengths_fallback is None
    assert len(result.strengths) == 3


def test_total_disagreement_is_zero_percent_and_all_crisis():
    result = build_result([1] * 40, [1] * 40)
    assert result.percent == 0
    assert all(s.zone == "crisis" for s in result.spheres)
    assert len(result.critical_blocks) == 8
    assert result.strengths == []
    assert result.strengths_fallback is not None


def test_gap_of_two_is_growth_and_not_divergent():
    """5 vs 3 throughout is the spec's example of Зона роста, not a talking point."""
    result = build_result([5] * 40, [3] * 40)
    assert all(s.zone == "growth" for s in result.spheres)
    assert result.divergent_all == []


def test_gap_of_three_is_divergent_but_not_crisis():
    a = [4] * 40
    b = [4] * 40
    b[0] = 1                      # question 1, gap of 3
    result = build_result(a, b)
    assert result.spheres[0].zone == "growth"
    assert result.divergent_all == [1]
    assert result.spheres[0].divergent == [1]


def test_single_gap_of_four_makes_the_sphere_critical():
    a = [5] * 40
    b = [5] * 40
    b[2] = 1                      # question 3, gap of 4
    result = build_result(a, b)
    assert result.spheres[0].zone == "crisis"
    assert result.spheres[1].zone == "strength"
    assert 3 in result.divergent_all


@pytest.mark.parametrize(
    "value_a,value_b,expected",
    [
        (2, 2, "crisis"),     # both below 3
        (2, 3, "growth"),     # only one below 3 — not a crisis
        (3, 3, "growth"),     # 3.0 is the boundary and does not trip it
        (4, 4, "strength"),
    ],
)
def test_zone_boundaries(value_a, value_b, expected):
    a = [value_a] * 5 + [4] * 35
    b = [value_b] * 5 + [4] * 35
    assert build_result(a, b).spheres[0].zone == expected


def test_average_just_under_three_is_a_crisis():
    """2.8 is "below 3" as much as 2 is — the rule is the average, not the label."""
    a = [3, 3, 3, 3, 2] + [4] * 35     # avg 2.8
    b = [3, 3, 3, 2, 2] + [4] * 35     # avg 2.6
    assert build_result(a, b).spheres[0].zone == "crisis"


def test_verdict_text_matches_the_zone():
    spheres = load_spheres(Language.RUSSIAN)
    strong = build_result([5] * 40, [5] * 40)
    assert strong.spheres[0].verdict == spheres[0].synergy
    weak = build_result([1] * 40, [1] * 40)
    assert weak.spheres[0].verdict == spheres[0].crisis


def test_question_numbers_are_one_based_and_global():
    """Sphere 8's questions are numbered 36-40, not 1-5."""
    a = [4] * 40
    b = [4] * 40
    b[39] = 1                     # last question overall
    result = build_result(a, b)
    assert result.divergent_all == [40]
    assert result.spheres[7].divergent == [40]


def test_recommendation_lists_the_divergent_numbers():
    a = [4] * 40
    b = [4] * 40
    b[0] = 1
    b[39] = 1
    result = build_result(a, b)
    assert "1" in result.recommendation
    assert "40" in result.recommendation


def test_attention_carries_two_spheres_with_a_framing():
    result = build_result([2] * 40, [2] * 40)
    assert len(result.attention) == 2
    for entry in result.attention:
        assert entry.framing.strip()
        assert entry.sphere.zone == "crisis"


def test_result_never_contains_raw_answers():
    """The whole feature's privacy promise, asserted on the serialized model."""
    a = [1, 2, 3, 4, 5] * 8
    b = [5, 4, 3, 2, 1] * 8
    dumped = build_result(a, b).model_dump_json()
    assert "answers" not in dumped


def test_wrong_length_input_raises():
    with pytest.raises(ValueError):
        build_result([5] * 39, [5] * 40)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_compat.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vechnost_bot.compat'`.

- [ ] **Step 3: Write the content file**

`data/library/compat_ru.yaml`, transcribed from the content source. Shape:

```yaml
scale:
  - Категорически нет
  - Скорее нет
  - Затрудняюсь ответить
  - Скорее да
  - Полностью да

framings:
  gap: >-
    Вы по-разному ощущаете эту сферу. Один из вас удовлетворён, а другой
    чувствует дефицит. Это почва для скрытых обид.
  both_low: >-
    Это ваша общая болевая точка. Вы оба чувствуете проблему здесь, и это
    хорошая новость — вы признаёте реальность и можете начать работу.

recommendation: >-
  Обсудите вопросы №{numbers} из теста сегодня вечером за чаем.

critical_block: >-
  💡 Рекомендация: ваша ситуация в сфере «{sphere}» требует внимания. Не
  ждите, пока это станет причиной разрыва или крупной ссоры. Обсудите
  сегодня вопросы №{numbers}. А лучше — запишитесь на поддерживающую
  сессию к семейному психологу, чтобы разобраться в этой сфере бережно и
  с вниманием друг к другу.

# Written by the implementer, not the product owner. Flagged in the spec
# for rewriting.
strengths_fallback: >-
  Пока ни одна сфера не вышла в зону силы — и это не приговор, а точка,
  с которой видно, куда расти.

spheres:
  - id: values
    title: Ценности и цели
    questions:
      - Мы одинаково видим наше будущее через 5–10 лет (дети, место жительства, карьера).
      # ... 5 total
    synergy: >-
      ...
    imbalance: >-
      ...
    crisis: >-
      ...
  # ... 8 spheres total, in the source's order
```

Sphere ids in order: `values`, `money`, `communication`, `intimacy`, `home`, `trust`, `social`, `empathy`.

- [ ] **Step 4: Write the scoring module**

```python
"""The couples compatibility test: content, scoring, and result assembly.

Deliberately imports neither FastAPI nor python-telegram-bot — the web API,
the bot, and the tests all use this module directly.

Individual answers go in; they never come out. The result carries zones,
verdict texts and question numbers, and nothing that would let one partner
reconstruct the other's answers.
"""

from functools import cache
from pathlib import Path
from typing import Literal, Optional

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
    strengths_fallback: Optional[str] = None
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
        gaps = [abs(x - y) for x, y in zip(slice_a, slice_b)]
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
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_compat.py -q`
Expected: PASS — 19 tests (the zone-boundary case is parametrized four ways).

- [ ] **Step 6: Lint and full suite**

Run: `python -m ruff check vechnost_bot/compat.py tests/test_compat.py` → zero errors.
Run: `pytest -q` → the documented baseline, nothing new.

- [ ] **Step 7: Commit**

```bash
git add data/library/compat_ru.yaml vechnost_bot/compat.py tests/test_compat.py
git commit -m "Add the compatibility test's content and scoring

Forty questions in eight spheres with their verdict texts, and the scoring
that turns two answer sets into zones, percentages and the numbers of the
questions a couple answered differently. Raw answers go in and never come
out.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Persistence

**Files:**
- Modify: `vechnost_bot/payments/models.py` (append after the `Room` model)
- Modify: `vechnost_bot/payments/repositories.py` (append after `RoomRepository`)
- Create: `alembic/versions/c4a1e77b2f90_add_compat_tests_table.py`
- Test: `tests/test_compat_repository.py`

**Interfaces:**
- Consumes: `TOTAL_QUESTIONS` from Task 1.
- Produces:
  - `CompatTest` — SQLAlchemy model, table `compat_tests`
  - `CompatTestRepository.get_by_code(session, code) -> Optional[CompatTest]`
  - `CompatTestRepository.create(session, code, creator_telegram_user_id, creator_name) -> CompatTest`
  - `CompatTestRepository.latest_completed_for(session, telegram_user_id) -> Optional[CompatTest]`
  - `CompatTestRepository.delete_superseded(session, pair_key, keep_id) -> int` — returns how many rows it removed

**Note on `create_all`.** A new *table* needs no `_ensure_*` hook: `create_tables()` runs `Base.metadata.create_all`, which creates missing tables. `_ensure_user_columns` exists only because `create_all` never *alters* existing tables, so it covers new columns on `users`. Do not add a hook for this table.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for compatibility-test persistence."""

import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vechnost_bot.payments.models import Base, CompatTest
from vechnost_bot.payments.repositories import CompatTestRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_create_and_fetch_by_code(session):
    created = await CompatTestRepository.create(
        session, code="ABC123", creator_telegram_user_id=1, creator_name="A"
    )
    assert created.creator_answers == [None] * 40
    assert created.guest_answers == [None] * 40
    assert created.pair_key is None
    assert created.finished_at is None

    found = await CompatTestRepository.get_by_code(session, "ABC123")
    assert found is not None and found.id == created.id


async def test_unknown_code_is_none(session):
    assert await CompatTestRepository.get_by_code(session, "NOPE99") is None


async def test_latest_completed_for_returns_only_finished_sessions(session):
    from datetime import datetime

    unfinished = await CompatTestRepository.create(
        session, code="AAA111", creator_telegram_user_id=7, creator_name="A"
    )
    unfinished.guest_telegram_user_id = 8
    await session.flush()
    assert await CompatTestRepository.latest_completed_for(session, 7) is None

    unfinished.finished_at = datetime.utcnow()
    await session.flush()
    found = await CompatTestRepository.latest_completed_for(session, 7)
    assert found is not None and found.code == "AAA111"
    # The guest can read it too.
    assert (await CompatTestRepository.latest_completed_for(session, 8)).code == "AAA111"


async def test_delete_superseded_removes_other_rows_for_the_same_pair(session):
    from datetime import datetime

    old = await CompatTestRepository.create(
        session, code="OLD111", creator_telegram_user_id=1, creator_name="A"
    )
    old.guest_telegram_user_id = 2
    old.pair_key = "1:2"
    old.finished_at = datetime.utcnow()

    other_pair = await CompatTestRepository.create(
        session, code="OTH111", creator_telegram_user_id=1, creator_name="A"
    )
    other_pair.guest_telegram_user_id = 3
    other_pair.pair_key = "1:3"
    other_pair.finished_at = datetime.utcnow()

    new = await CompatTestRepository.create(
        session, code="NEW111", creator_telegram_user_id=2, creator_name="B"
    )
    new.guest_telegram_user_id = 1
    new.pair_key = "1:2"
    new.finished_at = datetime.utcnow()
    await session.flush()

    removed = await CompatTestRepository.delete_superseded(session, "1:2", keep_id=new.id)
    assert removed == 1
    assert await CompatTestRepository.get_by_code(session, "OLD111") is None
    assert await CompatTestRepository.get_by_code(session, "NEW111") is not None
    assert await CompatTestRepository.get_by_code(session, "OTH111") is not None
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_compat_repository.py -q`
Expected: FAIL — `ImportError: cannot import name 'CompatTest'`.

- [ ] **Step 3: Add the model**

In `vechnost_bot/payments/models.py`, after the `Room` class:

```python
class CompatTest(Base):
    """A couples compatibility test: two partners answer 40 questions apart."""

    __tablename__ = "compat_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    creator_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    guest_telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    guest_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # list[int | None], 40 entries; null means unanswered.
    creator_answers: Mapped[dict] = mapped_column(JSONEncodedDict, nullable=False)
    guest_answers: Mapped[dict] = mapped_column(JSONEncodedDict, nullable=False)
    # "<lower id>:<higher id>", set when the guest joins.
    pair_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_compat_code", "code"),
        Index("idx_compat_pair", "pair_key"),
    )

    def __repr__(self) -> str:
        return f"<CompatTest(code='{self.code}', finished={self.finished_at is not None})>"
```

- [ ] **Step 4: Add the repository**

In `vechnost_bot/payments/repositories.py`, after `RoomRepository`:

```python
class CompatTestRepository:
    """Repository for compatibility-test sessions."""

    @staticmethod
    async def get_by_code(session: AsyncSession, code: str) -> Optional[CompatTest]:
        """Get a session by its invite code."""
        result = await session.execute(
            select(CompatTest).where(CompatTest.code == code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        code: str,
        creator_telegram_user_id: int,
        creator_name: Optional[str],
    ) -> CompatTest:
        """Create a session with both answer sets empty."""
        test = CompatTest(
            code=code,
            creator_telegram_user_id=creator_telegram_user_id,
            creator_name=creator_name,
            creator_answers=[None] * TOTAL_QUESTIONS,
            guest_answers=[None] * TOTAL_QUESTIONS,
        )
        session.add(test)
        await session.flush()
        logger.info(f"Created compat test {code} by {creator_telegram_user_id}")
        return test

    @staticmethod
    async def latest_completed_for(
        session: AsyncSession, telegram_user_id: int
    ) -> Optional[CompatTest]:
        """The caller's most recently completed session, as either participant."""
        result = await session.execute(
            select(CompatTest)
            .where(
                CompatTest.finished_at.is_not(None),
                or_(
                    CompatTest.creator_telegram_user_id == telegram_user_id,
                    CompatTest.guest_telegram_user_id == telegram_user_id,
                ),
            )
            .order_by(CompatTest.finished_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_superseded(
        session: AsyncSession, pair_key: str, keep_id: int
    ) -> int:
        """
        Delete this pair's other sessions.

        Retaking replaces the previous result rather than adding to a history,
        so the answers behind a superseded result do not linger in the
        database.
        """
        result = await session.execute(
            delete(CompatTest).where(
                CompatTest.pair_key == pair_key, CompatTest.id != keep_id
            )
        )
        await session.flush()
        return result.rowcount or 0
```

Add to the file's imports at the top: `CompatTest` to the existing `from .models import …` line, and `delete` to the existing `from sqlalchemy import select, or_` line — `or_` is already imported. Also `from ..compat import TOTAL_QUESTIONS`. All at the top of the file; a mid-file import is an E402 and fails the lint gate.

- [ ] **Step 5: Write the migration**

`alembic/versions/c4a1e77b2f90_add_compat_tests_table.py`:

```python
"""add_compat_tests_table

Revision ID: c4a1e77b2f90
Revises: b7e2f81c93d4
Create Date: 2026-08-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4a1e77b2f90'
down_revision: Union[str, None] = 'b7e2f81c93d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'compat_tests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('creator_telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('creator_name', sa.String(), nullable=True),
        sa.Column('guest_telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('guest_name', sa.String(), nullable=True),
        sa.Column('creator_answers', sa.Text(), nullable=False),
        sa.Column('guest_answers', sa.Text(), nullable=False),
        sa.Column('pair_key', sa.String(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('idx_compat_code', 'compat_tests', ['code'])
    op.create_index('idx_compat_pair', 'compat_tests', ['pair_key'])


def downgrade() -> None:
    op.drop_index('idx_compat_pair', table_name='compat_tests')
    op.drop_index('idx_compat_code', table_name='compat_tests')
    op.drop_table('compat_tests')
```

Confirm `b7e2f81c93d4` is still the alembic head before committing: `python -m alembic heads`. If it is not, set `down_revision` to whatever is.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_compat_repository.py -q`
Expected: PASS — 4 tests.

- [ ] **Step 7: Lint and full suite**

Run: `python -m ruff check vechnost_bot/payments/models.py vechnost_bot/payments/repositories.py tests/test_compat_repository.py alembic/versions/c4a1e77b2f90_add_compat_tests_table.py` → zero errors.
Run: `pytest -q` → the documented baseline.

- [ ] **Step 8: Commit**

```bash
git add vechnost_bot/payments/models.py vechnost_bot/payments/repositories.py alembic/versions/c4a1e77b2f90_add_compat_tests_table.py tests/test_compat_repository.py
git commit -m "Store compatibility tests, and drop a pair's superseded ones

A new compat_tests table with no TTL: a completed test is meant to be
re-read. Retaking deletes the pair's previous sessions outright rather than
keeping answers nobody can see or erase.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The API

**Files:**
- Create: `vechnost_bot/payments/compat_api.py`
- Modify: `vechnost_bot/payments/web.py` (the imports block and the `include_router` calls near the top of the app setup)
- Test: `tests/test_compat_api.py`

**Interfaces:**
- Consumes: everything from Tasks 1 and 2.
- Produces: `router: APIRouter` mounted at `/api/compat`; `_caller(authorization, guest_id) -> tuple[int, str]`.

Model the identity handling on `vechnost_bot/payments/rooms.py::_identity`, which accepts Telegram `initData` and falls back to an `X-Guest-Id` header when payments are disabled. Read that function before writing this one.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the compatibility test's HTTP API."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.payments.web import app

client = TestClient(app)
HEAD_A = {"X-Guest-Id": "partner-a"}
HEAD_B = {"X-Guest-Id": "partner-b"}
HEAD_C = {"X-Guest-Id": "stranger"}


def _create(headers=HEAD_A):
    return client.post("/api/compat", headers=headers).json()


def _answer_all(code, headers, value):
    for index in range(40):
        res = client.post(
            f"/api/compat/{code}/answer",
            headers=headers,
            json={"index": index, "value": value},
        )
        assert res.status_code == 200, res.text


def test_create_returns_a_six_character_code():
    body = _create()
    assert len(body["code"]) == 6
    assert body["answered"] == 0
    assert body["partner_answered"] == 0
    assert body["finished"] is False


def test_join_then_both_answer_then_result():
    code = _create()["code"]
    joined = client.post(f"/api/compat/{code}/join", headers=HEAD_B).json()
    assert joined["started"] is True

    _answer_all(code, HEAD_A, 5)
    state = client.get(f"/api/compat/{code}", headers=HEAD_B).json()
    assert state["partner_answered"] == 40
    assert state["answered"] == 0
    assert state["finished"] is False

    assert client.get(f"/api/compat/{code}/result", headers=HEAD_A).status_code == 409

    _answer_all(code, HEAD_B, 5)
    result = client.get(f"/api/compat/{code}/result", headers=HEAD_A).json()
    assert result["percent"] == 100
    assert len(result["spheres"]) == 8


def test_state_never_carries_the_partners_answers():
    """The feature's privacy promise, asserted on raw response text."""
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    for index in range(40):
        client.post(
            f"/api/compat/{code}/answer",
            headers=HEAD_A,
            json={"index": index, "value": (index % 5) + 1},
        )
    body = client.get(f"/api/compat/{code}", headers=HEAD_B).text
    assert "creator_answers" not in body
    assert "guest_answers" not in body
    assert "answers" not in body


def test_result_never_carries_raw_answers():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(code, HEAD_A, 4)
    _answer_all(code, HEAD_B, 2)
    body = client.get(f"/api/compat/{code}/result", headers=HEAD_A).text
    assert "creator_answers" not in body
    assert "guest_answers" not in body


def test_a_third_party_is_refused():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    assert client.get(f"/api/compat/{code}", headers=HEAD_C).status_code == 403


def test_unknown_code_is_404():
    assert client.get("/api/compat/ZZZZZZ", headers=HEAD_A).status_code == 404


def test_answer_validates_its_input():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    for payload in ({"index": 40, "value": 3}, {"index": 0, "value": 6},
                    {"index": -1, "value": 3}, {"index": 0, "value": 0}):
        res = client.post(f"/api/compat/{code}/answer", headers=HEAD_A, json=payload)
        assert res.status_code == 422, payload


def test_answering_before_a_partner_joins_is_refused():
    code = _create()["code"]
    res = client.post(
        f"/api/compat/{code}/answer", headers=HEAD_A, json={"index": 0, "value": 3}
    )
    assert res.status_code == 409


def test_a_second_guest_cannot_join():
    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    assert client.post(f"/api/compat/{code}/join", headers=HEAD_C).status_code == 409


def test_mine_returns_the_latest_completed_session():
    assert client.get("/api/compat/mine", headers=HEAD_C).status_code == 404

    code = _create()["code"]
    client.post(f"/api/compat/{code}/join", headers=HEAD_B)
    _answer_all(code, HEAD_A, 5)
    _answer_all(code, HEAD_B, 5)

    mine = client.get("/api/compat/mine", headers=HEAD_A).json()
    assert mine["code"] == code
    assert mine["result"]["percent"] == 100
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_compat_api.py -q`
Expected: FAIL — 404 on every route; the router does not exist.

- [ ] **Step 3: Write the router**

```python
"""The couples compatibility test over HTTP.

Mirrors rooms.py: its own router, its own initData handling, access checked
at creation so the creator's payment covers both partners.

No endpoint here ever serializes a partner's answers. State carries counts;
the result carries zones, verdicts and question numbers.
"""

import logging
import secrets
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..compat import TOTAL_QUESTIONS, build_result, load_spheres, scale_labels
from ..config import settings
from ..i18n import Language
from .database import get_db
from .repositories import CompatTestRepository
from .services import user_has_access
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compat", tags=["compat"])

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class AnswerRequest(BaseModel):
    index: int = Field(ge=0, lt=TOTAL_QUESTIONS)
    value: int = Field(ge=1, le=5)


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def _language(lang: str) -> Language:
    try:
        return Language(lang)
    except ValueError:
        return Language.RUSSIAN


def _caller(
    authorization: Optional[str], guest_id: Optional[str]
) -> tuple[int, str]:
    """Resolve the caller, exactly as rooms.py does."""
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() == "tma" and init_data:
        try:
            parsed = validate_init_data(init_data, settings.telegram_bot_token)
            user = parsed["user"]
            return int(user["id"]), user.get("first_name") or "Player"
        except InitDataError as e:
            logger.warning(f"Compat initData rejected: {e}")
            raise HTTPException(status_code=401, detail="unauthorized")

    if not settings.enable_payment and guest_id:
        pseudo = int.from_bytes(guest_id.encode()[:6].ljust(6, b"_"), "big")
        return pseudo, "Player"

    raise HTTPException(status_code=401, detail="unauthorized")


async def _load(session, code: str, user_id: int):
    test = await CompatTestRepository.get_by_code(session, code.strip().upper())
    if not test:
        raise HTTPException(status_code=404, detail="test not found")
    if user_id not in (test.creator_telegram_user_id, test.guest_telegram_user_id):
        raise HTTPException(status_code=403, detail="not a participant in this test")
    return test


def _answered(answers: list) -> int:
    return sum(1 for value in answers if value is not None)


def _state(test, user_id: int) -> dict[str, Any]:
    """State for one caller. Carries counts, never the partner's values."""
    is_creator = user_id == test.creator_telegram_user_id
    mine = test.creator_answers if is_creator else test.guest_answers
    theirs = test.guest_answers if is_creator else test.creator_answers
    return {
        "code": test.code,
        "your_role": "creator" if is_creator else "guest",
        "started": test.guest_telegram_user_id is not None,
        "answered": _answered(mine),
        "partner_answered": _answered(theirs),
        "total": TOTAL_QUESTIONS,
        "finished": test.finished_at is not None,
        "players": {"creator": test.creator_name, "guest": test.guest_name},
    }


@router.get("/questions")
async def questions(lang: str = "ru") -> dict[str, Any]:
    """The questions and the answer scale. No auth: this is public content."""
    language = _language(lang)
    return {
        "scale": scale_labels(language),
        "spheres": [
            {"id": s.id, "title": s.title, "questions": s.questions}
            for s in load_spheres(language)
        ],
        "total": TOTAL_QUESTIONS,
    }


@router.post("")
async def create(
    lang: str = "ru",
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _caller(authorization, x_guest_id)
    if settings.enable_payment and not await user_has_access(user_id):
        raise HTTPException(status_code=402, detail="payment required")

    async with get_db() as session:
        code = _generate_code()
        while await CompatTestRepository.get_by_code(session, code):
            code = _generate_code()
        test = await CompatTestRepository.create(
            session,
            code=code,
            creator_telegram_user_id=user_id,
            creator_name=name,
        )
        return _state(test, user_id)


@router.post("/{code}/join")
async def join(
    code: str,
    lang: str = "ru",
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    user_id, name = _caller(authorization, x_guest_id)

    async with get_db() as session:
        test = await CompatTestRepository.get_by_code(session, code.strip().upper())
        if not test:
            raise HTTPException(status_code=404, detail="test not found")
        if test.creator_telegram_user_id == user_id:
            pass  # creator re-opening their own test
        elif test.guest_telegram_user_id is None:
            test.guest_telegram_user_id = user_id
            test.guest_name = name
            low, high = sorted((test.creator_telegram_user_id, user_id))
            test.pair_key = f"{low}:{high}"
            test.updated_at = datetime.utcnow()
            await session.flush()
        elif test.guest_telegram_user_id != user_id:
            raise HTTPException(status_code=409, detail="test is full")
        return _state(test, user_id)


@router.get("/mine")
async def mine(
    lang: str = "ru",
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """The caller's latest completed test, with its result."""
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        test = await CompatTestRepository.latest_completed_for(session, user_id)
        if not test:
            raise HTTPException(status_code=404, detail="no completed test")
        result = build_result(test.creator_answers, test.guest_answers, language)
        return {"code": test.code, "result": result.model_dump()}


@router.get("/{code}")
async def state(
    code: str,
    lang: str = "ru",
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)
    async with get_db() as session:
        return _state(await _load(session, code, user_id), user_id)


@router.post("/{code}/answer")
async def answer(
    code: str,
    body: AnswerRequest,
    lang: str = "ru",
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)

    async with get_db() as session:
        test = await _load(session, code, user_id)
        if test.guest_telegram_user_id is None:
            raise HTTPException(status_code=409, detail="partner has not joined yet")

        is_creator = user_id == test.creator_telegram_user_id
        answers = list(test.creator_answers if is_creator else test.guest_answers)
        answers[body.index] = body.value
        if is_creator:
            test.creator_answers = answers
        else:
            test.guest_answers = answers

        both_done = (
            _answered(test.creator_answers) == TOTAL_QUESTIONS
            and _answered(test.guest_answers) == TOTAL_QUESTIONS
        )
        if both_done and test.finished_at is None:
            test.finished_at = datetime.utcnow()
            if test.pair_key:
                await CompatTestRepository.delete_superseded(
                    session, test.pair_key, keep_id=test.id
                )
        test.updated_at = datetime.utcnow()
        await session.flush()
        return _state(test, user_id)


@router.get("/{code}/result")
async def result(
    code: str,
    lang: str = "ru",
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    user_id, _ = _caller(authorization, x_guest_id)
    language = _language(lang)

    async with get_db() as session:
        test = await _load(session, code, user_id)
        if test.finished_at is None:
            raise HTTPException(status_code=409, detail="both partners must finish")
        return build_result(
            test.creator_answers, test.guest_answers, language
        ).model_dump()
```

**Route order matters:** `/mine` is declared before `/{code}` so FastAPI does not match the literal path as a code. Keep it there.

- [ ] **Step 4: Mount the router**

In `vechnost_bot/payments/web.py`, beside the existing router imports and mounts:

```python
from .compat_api import router as compat_router
```

```python
app.include_router(compat_router)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_compat_api.py -q`
Expected: PASS — 10 tests.

- [ ] **Step 6: Lint and full suite**

Run: `python -m ruff check vechnost_bot/payments/compat_api.py vechnost_bot/payments/web.py tests/test_compat_api.py` → zero errors.
Run: `pytest -q` → the documented baseline.

- [ ] **Step 7: Commit**

```bash
git add vechnost_bot/payments/compat_api.py vechnost_bot/payments/web.py tests/test_compat_api.py
git commit -m "Serve the compatibility test over /api/compat

Both partners answer through the same endpoints and see each other's
progress as a count. No response carries a partner's answers at any stage —
tests assert it on the raw response body.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The Mini App

**Files:**
- Modify: `webapp/index.html`

**Interfaces:**
- Consumes: `/api/compat/*` from Task 3.
- Produces: nothing other tasks depend on.

There is no automated test for this file; the repo has no Mini App test infrastructure, and `CLAUDE.md` says to verify Mini App changes in a browser. Manual verification is the standard here — do not build a harness.

**Use the helpers that already exist in this file.** Do not invent `api()`, `t()`, or a `state` object; there is no such thing here.

- `$(id)` — `document.getElementById`
- `T()` — the I18N table for the current language, read as `T().someKey`
- `fmt(tpl, vars)` — substitutes `{placeholders}`
- `lang` — module-scope language string
- `show(id)`, `toast(msg)`, `escapeHTML(s)`, `haptic(kind)`
- `coopFetch(path, opts)` — fetch with `lang` appended and the `X-Guest-Id` + `Authorization` headers already set; `opts.method` and `opts.json` are supported, and it throws an `Error` carrying `.status`
- `startCoopPoll(onState)` / `stopCoopPoll()` — a 2.5s poller keyed on `C.code`; **the test needs its own poller**, because `startCoopPoll` hardcodes `/api/rooms/`. Write `startCompatPoll`/`stopCompatPoll` alongside it in the same shape.
- Existing classes to reuse: `top`, `icon-btn`, `title`, `coop-box`, `coop-input`, `code-display`, `waiting-dots`, `btn btn-play`, `btn btn-second`, `chip`

- [ ] **Step 1: Add the home button**

In `#home`, after `#btnLibrary`:

```html
<button class="btn btn-second" id="btnCompat" data-i18n="compatBtn"></button>
```

- [ ] **Step 2: Add the four screens**

After the `#libraryDetail` section:

```html
<section class="screen" id="compat">
  <div class="top">
    <button class="icon-btn" id="compatBack">←</button>
    <div class="title" data-i18n="compatTitle"></div>
    <div style="width:40px"></div>
  </div>
  <div class="coop-box">
    <p data-i18n="compatIntro"></p>
    <button class="btn btn-play" id="btnCompatCreate" data-i18n="compatCreate" style="margin-top:0"></button>
    <p data-i18n="coopOr"></p>
    <input class="coop-input" id="compatCodeInput" maxlength="6" autocomplete="off" spellcheck="false">
    <button class="btn btn-second" id="btnCompatJoin" data-i18n="coopJoinBtn" style="margin-top:0"></button>
    <button class="btn btn-second" id="btnCompatMine" data-i18n="compatMine" style="margin-top:14px"></button>
  </div>
</section>

<section class="screen" id="compatInvite">
  <div class="top">
    <button class="icon-btn" id="compatInviteBack">←</button>
    <div class="title" data-i18n="inviteTitle"></div>
    <div style="width:40px"></div>
  </div>
  <div class="coop-box">
    <p data-i18n="compatInviteHint"></p>
    <div class="code-display" id="compatCode"></div>
    <button class="btn btn-play" id="btnCompatShare" data-i18n="inviteShare" style="margin-top:0"></button>
    <p class="waiting-dots" id="compatWaiting"></p>
  </div>
</section>

<section class="screen" id="compatQuiz">
  <div class="top">
    <button class="icon-btn" id="compatQuizBack">←</button>
    <div class="title" id="compatSphereTitle"></div>
    <div style="width:40px"></div>
  </div>
  <div class="progress-wrap">
    <div class="progress-track"><div class="progress-fill" id="compatProgress"></div></div>
    <div class="progress-num" id="compatProgressNum"></div>
  </div>
  <div id="compatQuestion"></div>
  <div id="compatScale"></div>
  <p class="waiting-dots" id="compatPartnerProgress"></p>
</section>

<section class="screen" id="compatResult">
  <div class="top">
    <button class="icon-btn" id="compatResultBack">←</button>
    <div class="title" data-i18n="compatResultTitle"></div>
    <div style="width:40px"></div>
  </div>
  <div id="compatResultBody"></div>
</section>
```

- [ ] **Step 3: Add the UI strings**

In the `I18N` object, add to each of `ru`, `en`, `cs`:

```js
// ru
compatBtn: '💞 Тест совместимости', compatTitle: 'Тест совместимости',
compatIntro: '40 вопросов о восьми сферах вашей жизни. Отвечаете порознь — результат видите вместе. Партнёр никогда не увидит ваши ответы, только то, в чём вы разошлись.',
compatCreate: 'Начать тест', compatMine: 'Прошлый результат',
compatInviteHint: 'Отправь этот код партнёру. Отвечать можно, как только он войдёт.',
compatWaitingPartner: 'Партнёр ответил на {n} из {total}',
compatDone: 'Ты ответил(а) на все 40. Ждём партнёра…',
compatResultTitle: 'Ваш результат',
compatStrengths: 'Сферы, где вы команда', compatAttention: 'Требуют разговора',
compatAll: 'По всем сферам', compatZoneStrength: 'Сфера силы',
compatZoneGrowth: 'Зона роста', compatZoneCrisis: 'Критическая зона',
compatNoResult: 'У вас пока нет пройденного теста',
compatPaywall: 'Тест совместимости входит в полный доступ',
```

```js
// en
compatBtn: '💞 Compatibility test', compatTitle: 'Compatibility test',
compatIntro: 'Forty questions across eight areas of your life. You answer apart and read the result together. Your partner never sees your answers — only where the two of you diverged.',
compatCreate: 'Start the test', compatMine: 'Previous result',
compatInviteHint: 'Send this code to your partner. You can start answering as soon as they join.',
compatWaitingPartner: 'Your partner has answered {n} of {total}',
compatDone: "You've answered all 40. Waiting for your partner…",
compatResultTitle: 'Your result',
compatStrengths: 'Where you are a team', compatAttention: 'Worth talking about',
compatAll: 'Every area', compatZoneStrength: 'Strength',
compatZoneGrowth: 'Room to grow', compatZoneCrisis: 'Needs attention',
compatNoResult: "You haven't completed a test yet",
compatPaywall: 'The compatibility test is part of full access',
```

```js
// cs
compatBtn: '💞 Test kompatibility', compatTitle: 'Test kompatibility',
compatIntro: 'Čtyřicet otázek o osmi oblastech vašeho života. Odpovídáte odděleně, výsledek čtete spolu. Partner nikdy neuvidí vaše odpovědi — jen to, v čem se lišíte.',
compatCreate: 'Začít test', compatMine: 'Předchozí výsledek',
compatInviteHint: 'Pošli tento kód partnerovi. Odpovídat můžeš, jakmile se připojí.',
compatWaitingPartner: 'Partner odpověděl na {n} ze {total}',
compatDone: 'Odpověděl(a) jsi na všech 40. Čekáme na partnera…',
compatResultTitle: 'Váš výsledek',
compatStrengths: 'Kde jste tým', compatAttention: 'Stojí za rozhovor',
compatAll: 'Všechny oblasti', compatZoneStrength: 'Silná stránka',
compatZoneGrowth: 'Prostor k růstu', compatZoneCrisis: 'Vyžaduje pozornost',
compatNoResult: 'Zatím jsi žádný test nedokončil(a)',
compatPaywall: 'Test kompatibility je součástí plného přístupu',
```

- [ ] **Step 4: Wire up the screens**

```js
  /* ---------------- compatibility test ---------------- */
  const CT = { code: null, st: null, timer: null, questions: null, idx: 0, answers: [] };

  function stopCompatPoll() {
    if (CT.timer) { clearInterval(CT.timer); CT.timer = null; }
  }

  function startCompatPoll() {
    stopCompatPoll();
    CT.timer = setInterval(async () => {
      if (!CT.code) return;
      try {
        const st = await coopFetch('/api/compat/' + CT.code);
        CT.st = st;
        onCompatState(st);
      } catch (e) {
        if (e.status === 404) { stopCompatPoll(); toast(T().coopGone); show('compat'); }
      }
    }, 2500);
  }

  function onCompatState(st) {
    if (st.finished) { stopCompatPoll(); loadCompatResult(CT.code); return; }
    if ($('compatInvite').classList.contains('active') && st.started) { enterCompatQuiz(); return; }
    if ($('compatQuiz').classList.contains('active')) {
      $('compatPartnerProgress').textContent =
        fmt(T().compatWaitingPartner, { n: st.partner_answered, total: st.total });
    }
  }

  async function loadCompatQuestions() {
    if (CT.questions) return CT.questions;
    const data = await coopFetch('/api/compat/questions');
    CT.questions = [];
    data.spheres.forEach(s => s.questions.forEach(q =>
      CT.questions.push({ sphere: s.title, text: q })));
    CT.scale = data.scale;
    return CT.questions;
  }

  async function compatCreate() {
    $('loader').classList.add('show');
    try {
      const st = await coopFetch('/api/compat', { method: 'POST', json: {} });
      CT.code = st.code; CT.st = st; CT.idx = 0; CT.answers = new Array(st.total).fill(null);
      $('compatCode').textContent = st.code;
      $('compatWaiting').textContent = T().inviteWaiting;
      show('compatInvite');
      startCompatPoll();
    } catch (e) {
      if (e.status === 402) toast(T().compatPaywall); else toast(T().loadError);
    } finally { $('loader').classList.remove('show'); }
  }

  async function compatJoin(code) {
    $('loader').classList.add('show');
    try {
      const st = await coopFetch('/api/compat/' + code + '/join', { method: 'POST', json: {} });
      CT.code = st.code; CT.st = st; CT.idx = 0; CT.answers = new Array(st.total).fill(null);
      startCompatPoll();
      if (st.finished) loadCompatResult(st.code); else enterCompatQuiz();
    } catch (e) {
      if (e.status === 409) toast(T().coopFull);
      else if (e.status === 404) toast(T().coopGone);
      else toast(T().loadError);
    } finally { $('loader').classList.remove('show'); }
  }

  async function enterCompatQuiz() {
    await loadCompatQuestions();
    show('compatQuiz');
    renderCompatQuestion();
  }

  function renderCompatQuestion() {
    const total = CT.questions.length;
    if (CT.idx >= total) {
      $('compatQuestion').innerHTML = '<p class="lib-question">' + escapeHTML(T().compatDone) + '</p>';
      $('compatScale').innerHTML = '';
      return;
    }
    const q = CT.questions[CT.idx];
    $('compatSphereTitle').textContent = q.sphere;
    $('compatProgress').style.width = (CT.idx / total * 100) + '%';
    $('compatProgressNum').textContent = (CT.idx + 1) + ' / ' + total;
    $('compatQuestion').innerHTML = '<p class="lib-question">' + escapeHTML(q.text) + '</p>';
    $('compatScale').innerHTML = CT.scale.map((label, i) =>
      `<button class="btn btn-second compat-opt" data-value="${i + 1}">${escapeHTML(label)}</button>`
    ).join('');
    $('compatScale').querySelectorAll('.compat-opt').forEach(btn => {
      btn.onclick = () => submitCompatAnswer(parseInt(btn.dataset.value, 10));
    });
  }

  async function submitCompatAnswer(value) {
    haptic('light');
    const index = CT.idx;
    CT.idx += 1;
    renderCompatQuestion();
    try {
      const st = await coopFetch('/api/compat/' + CT.code + '/answer', {
        method: 'POST', json: { index, value }
      });
      CT.st = st;
      if (st.finished) { stopCompatPoll(); loadCompatResult(CT.code); }
    } catch (e) {
      CT.idx = index;
      renderCompatQuestion();
      toast(T().loadError);
    }
  }

  async function loadCompatResult(code) {
    $('loader').classList.add('show');
    try {
      const data = await coopFetch('/api/compat/' + code + '/result');
      $('compatResultBody').innerHTML = renderCompatResult(data);
      show('compatResult');
    } catch (e) {
      toast(T().loadError);
    } finally { $('loader').classList.remove('show'); }
  }

  const COMPAT_ZONE_LABEL = () => ({
    strength: T().compatZoneStrength,
    growth: T().compatZoneGrowth,
    crisis: T().compatZoneCrisis
  });

  function renderCompatResult(r) {
    const zoneLabel = COMPAT_ZONE_LABEL();
    const sphereCard = (s, extra) => `
      <div class="lib-card compat-${s.zone}">
        <div class="lib-card-title">${escapeHTML(s.title)} · ${escapeHTML(zoneLabel[s.zone])}</div>
        ${extra || ''}
        <div class="lib-card-line">${escapeHTML(s.verdict)}</div>
        ${s.divergent.length ? `<div class="lib-card-line">№ ${s.divergent.join(', ')}</div>` : ''}
      </div>`;

    const strengths = r.strengths.length
      ? r.strengths.map(s => sphereCard(s)).join('')
      : `<p class="lib-card-line">${escapeHTML(r.strengths_fallback)}</p>`;

    return `
      <div class="compat-percent">${r.percent}%</div>
      <h3 class="compat-h">${escapeHTML(T().compatStrengths)}</h3>
      ${strengths}
      <h3 class="compat-h">${escapeHTML(T().compatAttention)}</h3>
      ${r.attention.map(a => sphereCard(a.sphere, a.framing
        ? `<div class="lib-card-line"><i>${escapeHTML(a.framing)}</i></div>`
        : '')).join('')}
      <div class="lib-card"><div class="lib-card-line">${escapeHTML(r.recommendation)}</div></div>
      ${r.critical_blocks.map(b =>
        `<div class="lib-card compat-crisis"><div class="lib-card-line">${escapeHTML(b)}</div></div>`).join('')}
      <h3 class="compat-h">${escapeHTML(T().compatAll)}</h3>
      ${r.spheres.map(s => sphereCard(s)).join('')}`;
  }

  $('btnCompat').onclick = () => { haptic('light'); show('compat'); };
  $('compatBack').onclick = () => { stopCompatPoll(); show('home'); };
  $('compatInviteBack').onclick = () => { stopCompatPoll(); CT.code = null; show('compat'); };
  $('compatQuizBack').onclick = () => { stopCompatPoll(); show('compat'); };
  $('compatResultBack').onclick = () => show('compat');
  $('btnCompatCreate').onclick = compatCreate;
  $('btnCompatJoin').onclick = () => {
    const code = ($('compatCodeInput').value || '').trim().toUpperCase();
    if (code.length === 6) compatJoin(code);
  };
  $('btnCompatMine').onclick = async () => {
    try {
      const data = await coopFetch('/api/compat/mine');
      $('compatResultBody').innerHTML = renderCompatResult(data.result);
      show('compatResult');
    } catch (e) {
      toast(e.status === 404 ? T().compatNoResult : T().loadError);
    }
  };
  $('btnCompatShare').onclick = () => {
    const msg = fmt(T().coopInviteMsg, { bot: BOT_URL || '', code: CT.code });
    try {
      if (tg) tg.openTelegramLink('https://t.me/share/url?url=' + encodeURIComponent(msg));
      else navigator.clipboard.writeText(msg);
      haptic('light');
    } catch (e) { toast(T().shareError); }
  };
```

Then add the four screens to the Telegram BackButton if-chain, beside the existing branches:

```js
        else if ($('compatResult').classList.contains('active')) show('compat');
        else if ($('compatQuiz').classList.contains('active')) { stopCompatPoll(); show('compat'); }
        else if ($('compatInvite').classList.contains('active')) { stopCompatPoll(); CT.code = null; show('compat'); }
        else if ($('compat').classList.contains('active')) show('home');
```

- [ ] **Step 5: Add the styles**

```css
.compat-opt{margin:8px 0;width:100%}
.compat-percent{font-size:56px;font-weight:700;text-align:center;margin:20px 0 6px}
.compat-h{margin:22px 0 8px;font-size:15px;opacity:.7;text-transform:uppercase;letter-spacing:.06em}
.compat-strength{border-left:3px solid rgba(120,220,160,.7)}
.compat-growth{border-left:3px solid rgba(255,200,120,.7)}
.compat-crisis{border-left:3px solid rgba(255,120,150,.8)}
#compatQuestion,#compatScale{padding:0 16px}
#compatResultBody{flex:1;overflow-y:auto;padding:0 16px 32px}
```

- [ ] **Step 6: Verify in a browser**

```bash
ENABLE_PAYMENT=FALSE python -m uvicorn vechnost_bot.payments.web:app --port 8000
```

Open `http://localhost:8000/app/` in two browser profiles (or one normal and one private window — the `guestId` lives in localStorage, so two windows sharing storage will look like the same person). Then:

1. Window A: Тест совместимости → Начать тест → a six-character code appears.
2. Window B: enter that code → Присоединиться → the question flow starts.
3. Window A: the invite screen advances to the question flow on its own within ~3 seconds.
4. Answer all 40 in A; B's screen shows "Партнёр ответил на 40 из 40".
5. Answer all 40 in B; both windows land on the result within ~3 seconds.
6. The result shows a percentage, the strengths block, two attention spheres with their framings, the recommendation, and all eight spheres.
7. Back out and press "Прошлый результат" — the same result loads.
8. Confirm no response in the network tab carries the other partner's answers.

Report what you saw, screen by screen.

- [ ] **Step 7: Commit**

```bash
git add webapp/index.html
git commit -m "Add the compatibility test to the Mini App

A fourth home button and four screens: create or join, the invite code, the
question flow with the partner's progress, and the result.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The notification, and the docs

**Files:**
- Create: `vechnost_bot/compat_notify.py`
- Modify: `vechnost_bot/payments/compat_api.py` (the `answer` endpoint, where `finished_at` is set)
- Modify: `data/translations_ru.yaml`, `data/translations_en.yaml`, `data/translations_cs.yaml`
- Modify: `CLAUDE.md`, `README.md`
- Test: `tests/test_compat_notify.py`

**Interfaces:**
- Consumes: `CompatTest` from Task 2, the `answer` endpoint from Task 3.
- Produces: `notify_result_ready(test) -> None`, awaited from the API when a test completes.

The second partner may finish hours after the first. Without a push, the result is never read.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the compatibility-test completion push."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.compat_notify import notify_result_ready


async def test_both_partners_are_messaged():
    test = MagicMock(
        code="ABC123",
        creator_telegram_user_id=1,
        guest_telegram_user_id=2,
    )
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with patch("vechnost_bot.compat_notify._bot", return_value=bot):
        await notify_result_ready(test)

    assert bot.send_message.await_count == 2
    assert {call.kwargs["chat_id"] for call in bot.send_message.await_args_list} == {1, 2}


async def test_a_blocked_partner_does_not_stop_the_other():
    from telegram.error import Forbidden

    test = MagicMock(
        code="ABC123",
        creator_telegram_user_id=1,
        guest_telegram_user_id=2,
    )
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[Forbidden("blocked"), None])

    with patch("vechnost_bot.compat_notify._bot", return_value=bot):
        await notify_result_ready(test)

    assert bot.send_message.await_count == 2


async def test_no_bot_configured_is_silent():
    test = MagicMock(creator_telegram_user_id=1, guest_telegram_user_id=2)
    with patch("vechnost_bot.compat_notify._bot", return_value=None):
        await notify_result_ready(test)      # must not raise
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_compat_notify.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vechnost_bot.compat_notify'`.

- [ ] **Step 3: Write the notifier**

```python
"""Tell both partners their compatibility result is ready.

The second partner often finishes hours after the first, so without this the
result is computed and never read.
"""

import logging
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

from .config import settings
from .i18n import Language, get_text

logger = logging.getLogger(__name__)


def _bot() -> Optional[Bot]:
    """The bot to send with, or None when no token is configured."""
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def _keyboard() -> Optional[InlineKeyboardMarkup]:
    url = settings.webapp_url
    if not url:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            get_text("compat.open_button", Language.RUSSIAN),
            url=url,
        )
    ]])


async def notify_result_ready(test) -> None:
    """Message both participants. One blocked partner must not stop the other."""
    bot = _bot()
    if bot is None:
        return

    text = get_text("compat.ready", Language.RUSSIAN)
    keyboard = _keyboard()

    for user_id in (test.creator_telegram_user_id, test.guest_telegram_user_id):
        if not user_id:
            continue
        try:
            await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)
        except Forbidden:
            logger.info(f"Compat notify: user {user_id} blocked the bot")
        except Exception as e:
            logger.warning(f"Compat notify failed for {user_id}: {e}")
```

- [ ] **Step 4: Call it when the test completes**

In `vechnost_bot/payments/compat_api.py`, inside the `answer` endpoint where `finished_at` is set, after `await session.flush()` and before the return, add the call — and import `notify_result_ready` at the **top** of the file, not inline (E402):

```python
        if just_finished:
            await notify_result_ready(test)
```

Set a `just_finished = False` local before the `if both_done ...` block and flip it to `True` inside, so the notification fires exactly once and only after the row is flushed.

- [ ] **Step 5: Add the translation keys**

`data/translations_ru.yaml`:

```yaml
compat:
  ready: "💞 Ваш тест совместимости готов. Откройте результат вдвоём — так интереснее."
  open_button: "Посмотреть результат"
```

`data/translations_en.yaml`:

```yaml
compat:
  ready: "💞 Your compatibility result is ready. Open it together — it reads better that way."
  open_button: "See the result"
```

`data/translations_cs.yaml`:

```yaml
compat:
  ready: "💞 Váš výsledek testu kompatibility je hotový. Otevřete ho spolu — tak to má smysl."
  open_button: "Zobrazit výsledek"
```

- [ ] **Step 6: Update the docs**

In `CLAUDE.md`'s architecture notes, after the `rooms.py` bullet:

```markdown
- **The compatibility test** is the second two-partner feature and follows the
  same shape: `compat.py` is the domain layer (content, scoring, result
  assembly, no web or Telegram imports), `payments/compat_api.py` serves it,
  and `compat_tests` stores it. Unlike rooms it has **no TTL** — a completed
  test is meant to be re-read — and retaking deletes the pair's previous
  sessions rather than keeping a history.
- **A partner's individual answers never leave the server.** `/api/compat`
  returns counts and, once both finish, zones, verdict texts and the numbers
  of the questions they answered differently. Tests assert this on the raw
  response body; keep them that way.
```

In `README.md`'s feature list, after the Library bullet:

```markdown
- **Compatibility test.** Forty questions across eight areas, taken separately
  by both partners and compared. The result names the areas where they are a
  team, the two worth talking about, and the exact questions they answered
  differently — without showing either partner the other's answers.
```

Also add `vechnost_bot/compat.py`, `vechnost_bot/compat_notify.py` and `payments/compat_api.py` to the README's project layout, and move the compatibility test out of the Roadmap's "next" list into what has shipped.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_compat_notify.py tests/test_compat_api.py -q`
Expected: PASS.

- [ ] **Step 8: Lint and full suite**

Run: `python -m ruff check vechnost_bot/compat_notify.py vechnost_bot/payments/compat_api.py tests/test_compat_notify.py` → zero errors.
Run: `pytest -q` → the documented baseline.

- [ ] **Step 9: Commit**

```bash
git add vechnost_bot/compat_notify.py vechnost_bot/payments/compat_api.py data/translations_ru.yaml data/translations_en.yaml data/translations_cs.yaml tests/test_compat_notify.py CLAUDE.md README.md
git commit -m "Tell both partners when the compatibility result is ready

The second partner often finishes hours later; without a push the result is
computed and never read. One blocked partner does not stop the other.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification before opening the PR

- [ ] `pytest -q` matches the documented baseline — no new failures.
- [ ] `python -m ruff check .` totals no more than master's 527.
- [ ] The Mini App was driven end to end in two browser windows, through create, join, both answering, and the result.
- [ ] `GET /api/compat/{code}` and `/result` were inspected in the network tab and carry no partner answers.
- [ ] Retaking a completed test and finishing it removes the previous row:

```bash
python -c "import sqlite3;print(sqlite3.connect('vechnost.db').execute('select code,pair_key,finished_at from compat_tests').fetchall())"
```

- [ ] `git log --oneline master..HEAD` shows five commits, one per task.

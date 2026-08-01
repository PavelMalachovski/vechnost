# Library Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Library — a browsable second section of the VECHNOST Mini App holding date ideas, the 36 questions, two sets of practices, and a year of self-reflection prompts that replace the daily card push.

**Architecture:** Content lives in per-module YAML under `data/library/`, loaded by a dependency-free `library.py`. A `library_api.py` router (modelled on the existing `rooms.py`) serves it with the paywall enforced server-side. The Mini App gains two screens. `daily_card.py` is rewritten to push the reflection question of the day instead of a deck card.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, PyYAML, pytest (asyncio auto mode), vanilla JS in a single-file Mini App.

**Spec:** [`docs/superpowers/specs/2026-08-01-library-design.md`](../specs/2026-08-01-library-design.md)

**Content source:** [`docs/superpowers/specs/2026-08-01-library-source-content.md`](../specs/2026-08-01-library-source-content.md) holds all 601 Library items verbatim, sectioned to match the YAML files. Tasks 2–4 transcribe from it — do not invent content, and do not go looking for it elsewhere.

## Global Constraints

- Branch is `feature/library-section`, cut from `master`. One commit per task.
- Pytest config lives in `pyproject.toml`. **Never** create `pytest.ini` — a `[tool:pytest]` header there silently disables the pyproject config.
- All three language question files must keep **identical deck sizes**. `rooms.py` builds the card order from the creator's language and serves text in the requester's language; divergent sizes hand a partner a blank card.
- New user-facing text goes in all three languages (`ru`/`en`/`cs`). This applies to UI strings and to deck questions. It does **not** apply to Library content, which is Russian-only in this phase by explicit decision.
- The server never serializes paid content for an unpaid caller. Enforce access in the API, not in the client.
- Freemium constants live only in `freemium.py`.
- YAML files are UTF-8, LF, two-space indent, block scalars for long strings.
- Tests run offline: no network, no live Tribute, no Redis outside the `redis` marker.
- Run `pytest -q` before every commit. A commit whose suite is red is a failed task.

---

### Task 1: Replace deck questions in all three languages

Unrelated to the Library; lands first so the content edit is reviewable on its own.

**Files:**
- Modify: `data/questions.yaml`
- Modify: `data/questions_en.yaml`
- Modify: `data/questions_cs.yaml`
- Test: `tests/test_questions_content.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: deck sizes `Acquaintance` L1/L2 = 30, L3 = 33; `For Couples` L1/L2/L3 = 30; `Sex` questions = 79, tasks = 14; `Provocation` = 34 — identical across all three files. Task 7's tests do not depend on these counts.

**Mapping rule.** The Nth replacement text goes to the Nth number *in the order the numbers were given*. For `Sex` that order is `1, 3, 27, 30, 31, 33, 45, 40, 51, 70` — note 45 precedes 40. Texts beyond the number list are appended to the end of the deck.

**Two source typos are corrected** (flag these in the commit message): "Какую **делать** нашего первого поцелуя" → "деталь"; "Если бы **нудно** было выбрать" → "нужно".

- [ ] **Step 1: Write the failing parity test**

```python
"""Deck content invariants that must hold across all languages."""

from pathlib import Path

import pytest
import yaml

DATA = Path(__file__).parent.parent / "data"
FILES = ["questions.yaml", "questions_en.yaml", "questions_cs.yaml"]

EXPECTED_SIZES = {
    ("Acquaintance", 1, "questions"): 30,
    ("Acquaintance", 2, "questions"): 30,
    ("Acquaintance", 3, "questions"): 33,
    ("For Couples", 1, "questions"): 30,
    ("For Couples", 2, "questions"): 30,
    ("For Couples", 3, "questions"): 30,
    ("Sex", None, "questions"): 79,
    ("Sex", None, "tasks"): 14,
    ("Provocation", None, "questions"): 34,
}


def _sizes(filename: str) -> dict:
    data = yaml.safe_load((DATA / filename).read_text(encoding="utf-8"))
    sizes = {}
    for theme, theme_data in data["themes"].items():
        if "levels" in theme_data:
            for level, level_data in theme_data["levels"].items():
                for kind, items in level_data.items():
                    sizes[(theme, level, kind)] = len(items)
        else:
            for kind, items in theme_data.items():
                sizes[(theme, None, kind)] = len(items)
    return sizes


@pytest.mark.parametrize("filename", FILES)
def test_deck_sizes_match_spec(filename):
    assert _sizes(filename) == EXPECTED_SIZES


def test_all_languages_have_identical_deck_sizes():
    reference = _sizes(FILES[0])
    for filename in FILES[1:]:
        assert _sizes(filename) == reference, f"{filename} diverged from {FILES[0]}"


def test_russian_provocation_uses_partnersha():
    data = yaml.safe_load((DATA / "questions.yaml").read_text(encoding="utf-8"))
    joined = " ".join(data["themes"]["Provocation"]["questions"])
    assert "партнёр(ка)" not in joined
    assert "партнёрша" in joined


@pytest.mark.parametrize("filename", FILES)
def test_no_duplicate_questions_within_a_deck(filename):
    data = yaml.safe_load((DATA / filename).read_text(encoding="utf-8"))
    for theme, theme_data in data["themes"].items():
        decks = (
            [(f"{theme} L{lv}", d) for lv, d in theme_data["levels"].items()]
            if "levels" in theme_data
            else [(theme, theme_data)]
        )
        for label, deck in decks:
            for kind, items in deck.items():
                assert len(set(items)) == len(items), f"{label} {kind} has duplicates"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_questions_content.py -q`
Expected: FAIL — sizes are currently 30 / 76 / 30, and `партнёр(ка)` is still present.

- [ ] **Step 3: Apply the Russian replacements**

In `data/questions.yaml`, `themes → Sex → questions`, replace by 1-based position:

| # | New text |
|---|---|
| 1 | Какое прикосновение к своему телу ты любишь больше всего? |
| 3 | Какой твой наряд заставляет тебя чувствовать себя богом/богиней секса? |
| 27 | Если бы тебе разрешили одно эгоистичное желание сегодня, что бы это было? |
| 30 | Какая твоя фантазия кажется тебе «слишком смелой»? Почему ты её ещё не реализовал(а)? |
| 31 | Что в твоём теле вызывает у тебя самый большой восторг? |
| 33 | Какое из своих желаний ты подавляешь чаще всего, чтобы быть «удобным(ой)»? |
| 45 | Какую роль ты играешь в отношениях чаще всего: лидера, соратника или искусителя? |
| 40 | Что в твоём партнёре возбуждает твой ум больше всего? |
| 51 | Какую черту в партнёре ты хотел(а) бы «присвоить» себе? |
| 70 | Что в твоём поведении заставляет партнёра терять голову? Ты пользуешься этим осознанно? |

Append to the end of the same list (positions 77–79):

- Если бы ты видел(а) нашу пару со стороны в ресторане, что бы ты о них подумал(а)?
- Ты чувствуешь себя свободным(ой), когда ты влюблён(а), или когда ты один (одна)?
- Какая «запретная» мысль посещала тебя сегодня?

`themes → For Couples → levels → 1 → questions`:

| # | New text |
|---|---|
| 7 | Если бы ты должен/должна сделать снимок меня в момент абсолютного счастья, что бы я там делал(а)? |
| 22 | Ты в комнате с завязанными глазами, и вокруг 20 девушек/парней. Никто из нас не может говорить. Как среди них ты узнаешь меня? |

`themes → For Couples → levels → 2 → questions`:

| # | New text |
|---|---|
| 3 | Если бы ты потерял(а) память и все воспоминания обо мне, что бы могло помочь тебе вспомнить меня? |
| 24 | Если бы мы только встретились, как бы ты привлекал(а) моё внимание? |
| 30 | Какую информацию обо мне знаешь ты, но не знает почти никто, потому что я этого не показываю? |

`themes → Acquaintance → levels → 3 → questions`:

| # | New text |
|---|---|
| 3 | Если бы у нашей любви был вкус, что бы это было? |
| 13 | Какую деталь нашего первого поцелуя ты помнишь до сих пор? |
| 24 | Представь, что мы на день поменялись телами — какие три вещи ты бы сделал(а) первыми? |
| 26 | Чему тебя научила моя любовь? |
| 28 | Какая версия наших отношений тебе нравится больше всего? |
| 30 | Если бы мы потерялись в торговом центре, где бы ты искал(а) меня в первую очередь? |

Append (positions 31–33):

- Если бы тебе нужно было описать одно моё самое любимое место, что бы это было и почему?
- Какими 5 словами ты бы описал(а) меня человеку, который меня не знает?
- За что меня невозможно не полюбить?

`themes → Provocation → questions`:

| # | New text |
|---|---|
| 2 | Если бы тебе предложили деньги — сумму, которая закроет все твои проблемы и оставит на безбедную жизнь, — но тебе нужно бросить меня и никогда не возвращаться, ты бы согласился/согласилась? |
| 6 | Если бы я не понравился(лась) твоей маме или человеку, который для тебя авторитет, ты бы стал(а) бороться за наши отношения? |
| 9 | Что ты знаешь обо мне такого, что могло бы меня ранить или навредить мне? |
| 10 | Если бы меня задержала полиция, как думаешь, за что бы это было? |
| 12 | В какие моменты ты чувствуешь себя лишним(лишней) рядом со мной? |
| 14 | Смог(ла) бы ты рассказать мне об измене или о чём-то, что меня точно ранит — и я буду на тебя злиться, а возможно и закончу отношения? |
| 15 | Если бы был выбор — купить, подарить или сделать что-то только для своей мамы или только для меня, — кого ты выберешь? |
| 20 | Как в твоей семье выстраивается иерархия между детьми, партнёром, родителями, друзьями, близкими родственниками? Кто на каком месте, если 1 — самый важный, а остальные по убыванию? |

Append (positions 31–34):

- Если бы ты мог(ла) сделать что угодно, зная, что тебя за это не осудят (даже нарушить закон), что бы ты сделал(а)?
- Если ты нарушил(а) обещание, ты всегда извиняешься или делаешь вид, что ничего не было?
- Если бы нужно было выбрать: обмануть меня, но защитить себя, или сказать правду, зная, что мне она не понравится, — что бы ты сделал(а)?
- Есть ли кто-то, кого ты в жизни ненавидишь?

Finally, in the six surviving Provocation questions at positions **11, 19, 22, 24, 28, 29**, replace the token `партнёр(ка)` with `партнёрша`, adjusting the surrounding grammar to feminine agreement. Example — position 11 currently reads `…бывший(ая) партнёр(ка) не останавливается…`; it becomes `…бывшая партнёрша не останавливается…`. Read each sentence and make it grammatical; a blind token swap will produce broken Russian.

- [ ] **Step 4: Verify the Russian file loads and sizes are right**

```bash
python -c "import yaml;d=yaml.safe_load(open('data/questions.yaml',encoding='utf-8'));t=d['themes'];print(len(t['Sex']['questions']),len(t['Provocation']['questions']),len(t['Acquaintance']['levels'][3]['questions']))"
```

Expected: `79 34 33`

- [ ] **Step 5: Apply the same edits to `questions_en.yaml`**

Same positions, same appends. Translate each new Russian text into natural English — these are conversational prompts, so translate for tone, not word-for-word. The English deck must end up at the sizes in `EXPECTED_SIZES`. The `партнёрша` fix is Russian-only; English has no grammatical gender to repair, so positions 11/19/22/24/28/29 are left alone in this file.

Two worked examples to set the register:

- `Какое прикосновение к своему телу ты любишь больше всего?` → `Which touch on your own body do you love most?`
- `Какая «запретная» мысль посещала тебя сегодня?` → `What "forbidden" thought crossed your mind today?`

- [ ] **Step 6: Apply the same edits to `questions_cs.yaml`**

Same positions, same appends, translated into Czech with the same conversational register. Two worked examples:

- `Какое прикосновение к своему телу ты любишь больше всего?` → `Který dotek na svém těle máš nejraději?`
- `Какая «запретная» мысль посещала тебя сегодня?` → `Jaká „zakázaná" myšlenka tě dnes napadla?`

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_questions_content.py -q`
Expected: PASS — 8 tests (3 parametrized size checks, parity, `партнёрша`, 3 parametrized duplicate checks).

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: PASS, except any `redis`-marked tests when Redis is not running locally. If a non-Redis test broke, it is almost certainly `tests/test_daily_card.py` matching a question by exact string — note it and fix it here rather than deferring.

- [ ] **Step 9: Commit**

```bash
git add data/questions.yaml data/questions_en.yaml data/questions_cs.yaml tests/test_questions_content.py
git commit -m "Refresh deck questions and fix feminine agreement in Provocation

Replaces 21 questions across Sex, For Couples L1/L2, Acquaintance L3 and
Provocation, and appends 10 more. Corrects two typos from the source copy
(delat->detal, nudno->nuzhno) and rewrites six Provocation questions to use
'partnyorsha' instead of 'partnyor(ka)'.

All three language files stay size-identical so couple-mode rooms cannot
hand a partner a blank card.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Library loader with the two practice modules

Builds `library.py` end-to-end against the smallest content (50 items), so the loader is proven before the bulk transcription.

**Files:**
- Create: `data/library/practices_self_ru.yaml`
- Create: `data/library/practices_couples_ru.yaml`
- Create: `vechnost_bot/library.py`
- Test: `tests/test_library.py` (create)

**Interfaces:**
- Consumes: `vechnost_bot.i18n.Language`.
- Produces:
  - `LibraryModule` — Pydantic model: `id: str`, `title: str`, `emoji: str`, `type: Literal["list","practice","daily"]`, `paid: bool`, `count: int`.
  - `Practice` — Pydantic model: `title: str`, `why: str`, `result: str`.
  - `LibraryCategory` — Pydantic model: `id: str`, `title: str`, `nsfw: bool`, `items: list[str]`.
  - `MODULES: dict[str, LibraryModule]` — the module registry, keyed by id.
  - `load_practices(module_id: str, language: Language) -> list[Practice]`
  - `load_categories(module_id: str, language: Language) -> list[LibraryCategory]` (Task 3)
  - `load_reflection(language: Language) -> list[list[str]]` (Task 4)
  - `question_of_the_day(day_of_year: int, language: Language) -> tuple[str, int]` — text and 1-based day number (Task 4)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the Library content loader and its YAML files."""

import pytest

from vechnost_bot.i18n import Language
from vechnost_bot.library import MODULES, Practice, load_practices


def test_practice_modules_are_registered():
    assert MODULES["practices_self"].type == "practice"
    assert MODULES["practices_self"].paid is False
    assert MODULES["practices_couples"].paid is True


@pytest.mark.parametrize("module_id", ["practices_self", "practices_couples"])
def test_practice_module_has_25_complete_items(module_id):
    items = load_practices(module_id, Language.RUSSIAN)
    assert len(items) == 25
    for item in items:
        assert isinstance(item, Practice)
        assert item.title.strip()
        assert item.why.strip()
        assert item.result.strip()


def test_module_count_matches_loaded_items():
    assert MODULES["practices_self"].count == len(
        load_practices("practices_self", Language.RUSSIAN)
    )


def test_non_russian_falls_back_to_russian():
    ru = load_practices("practices_self", Language.RUSSIAN)
    en = load_practices("practices_self", Language.ENGLISH)
    assert en == ru


def test_unknown_module_raises():
    with pytest.raises(KeyError):
        load_practices("nope", Language.RUSSIAN)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_library.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vechnost_bot.library'`.

- [ ] **Step 3: Write the two YAML files**

`data/library/practices_self_ru.yaml` — all 25 items from **section 4** of the content source, shape:

```yaml
items:
  - title: Письмо «Спасибо за защиту»
    why: >-
      Мы привыкли бороться с комплексами, но они возникли как механизм
      защиты, чтобы уберечь нас от опасностей.
    result: >-
      Снижение внутреннего напряжения. Вы признаёте роль страха, но
      забираете у него штурвал.
```

The `title` is the practice name (bold line in the source, without its number); `why` and `result` are the source's `why:` and `result:` lines verbatim. `data/library/practices_couples_ru.yaml` uses the identical shape with the 25 practices from **section 3**.

- [ ] **Step 4: Write the loader**

```python
"""Library content: date ideas, practices, and reflection prompts.

Content is Russian-only in this phase; other languages fall back to the
Russian file. This module deliberately imports neither FastAPI nor
python-telegram-bot so it can be used from the web API, the bot, and tests
alike.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from .i18n import Language

LIBRARY_DIR = Path(__file__).parent.parent / "data" / "library"


class Practice(BaseModel):
    title: str
    why: str
    result: str


class LibraryCategory(BaseModel):
    id: str
    title: str
    nsfw: bool = False
    items: list[str]


class LibraryModule(BaseModel):
    id: str
    title: str
    emoji: str
    type: Literal["list", "practice", "daily"]
    paid: bool
    count: int


MODULES: dict[str, LibraryModule] = {
    m.id: m
    for m in [
        LibraryModule(id="dates", title="Идеи для свиданий", emoji="💡",
                      type="list", paid=True, count=150),
        LibraryModule(id="fall_in_love", title="36 вопросов, чтобы влюбиться",
                      emoji="💘", type="list", paid=False, count=36),
        LibraryModule(id="practices_self", title="Практики для себя", emoji="🌱",
                      type="practice", paid=False, count=25),
        LibraryModule(id="practices_couples", title="Практики для пар", emoji="💞",
                      type="practice", paid=True, count=25),
        LibraryModule(id="reflection", title="Вопрос дня", emoji="🌙",
                      type="daily", paid=False, count=365),
    ]
}


@lru_cache(maxsize=None)
def _load_yaml(module_id: str, language: Language) -> dict:
    """Parsed YAML for a module. Non-Russian languages fall back to Russian."""
    if module_id not in MODULES:
        raise KeyError(module_id)
    path = LIBRARY_DIR / f"{module_id}_{language.value}.yaml"
    if not path.exists():
        path = LIBRARY_DIR / f"{module_id}_ru.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_practices(module_id: str, language: Language = Language.RUSSIAN) -> list[Practice]:
    """The practices of a `practice`-type module, in authored order."""
    data = _load_yaml(module_id, language)
    return [Practice(**item) for item in data.get("items", [])]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_library.py -q`
Expected: PASS — 6 tests.

- [ ] **Step 6: Commit**

```bash
git add data/library vechnost_bot/library.py tests/test_library.py
git commit -m "Add the Library loader and both practice modules

Fifty practices with their 'why' and 'outcome' lines, behind a loader that
keeps FastAPI and Telegram out of the content layer.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Date ideas and the 36 questions

**Files:**
- Create: `data/library/dates_ru.yaml`
- Create: `data/library/fall_in_love_ru.yaml`
- Modify: `vechnost_bot/library.py`
- Modify: `tests/test_library.py`

**Interfaces:**
- Consumes: `LibraryCategory`, `_load_yaml`, `MODULES` from Task 2.
- Produces: `load_categories(module_id: str, language: Language) -> list[LibraryCategory]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_library.py`:

```python
from vechnost_bot.library import LibraryCategory, load_categories

DATE_CATEGORY_SIZES = {
    "home": 25,
    "outdoors": 25,
    "culture": 25,
    "extreme": 15,
    "food": 10,
    "deep": 15,
    "spicy": 10,
    "spontaneous": 25,
}


def test_dates_has_eight_categories_with_expected_sizes():
    categories = load_categories("dates", Language.RUSSIAN)
    assert {c.id: len(c.items) for c in categories} == DATE_CATEGORY_SIZES
    assert sum(len(c.items) for c in categories) == 150


def test_only_the_spicy_category_is_nsfw():
    categories = load_categories("dates", Language.RUSSIAN)
    assert [c.id for c in categories if c.nsfw] == ["spicy"]


def test_fall_in_love_is_one_category_of_36():
    categories = load_categories("fall_in_love", Language.RUSSIAN)
    assert len(categories) == 1
    assert len(categories[0].items) == 36
    assert categories[0].nsfw is False


def test_every_category_item_is_non_empty():
    for module_id in ("dates", "fall_in_love"):
        for category in load_categories(module_id, Language.RUSSIAN):
            assert isinstance(category, LibraryCategory)
            assert all(item.strip() for item in category.items)


def test_module_counts_match_loaded_categories():
    for module_id in ("dates", "fall_in_love"):
        loaded = sum(len(c.items) for c in load_categories(module_id, Language.RUSSIAN))
        assert MODULES[module_id].count == loaded
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_library.py -q`
Expected: FAIL — `ImportError: cannot import name 'load_categories'`.

- [ ] **Step 3: Write `dates_ru.yaml`**

All 150 ideas from **section 1** of the content source, in eight categories, numbers stripped. The source's subsection headings already carry the `id` and `title` for each category:

```yaml
categories:
  - id: home
    title: Домашние и уютные
    items:
      - Смотреть детские фото и видео друг друга
      - Приготовить вместе блюдо, которое ни один из вас никогда не пробовал
      # ... 25 total
  - id: outdoors
    title: На свежем воздухе
    items: []   # 25
  - id: culture
    title: Культурные и необычные
    items: []   # 25
  - id: extreme
    title: Экстремальные и активные
    items: []   # 15
  - id: food
    title: Гастрономические
    items: []   # 10
  - id: deep
    title: Интеллектуальные и глубокие
    items: []   # 15
  - id: spicy
    title: Пикантные
    nsfw: true
    items: []   # 10
  - id: spontaneous
    title: Разное и спонтанное
    items: []   # 25
```

The `items: []` entries above show sizes only — fill each from the matching subsection of the content source, which is already deduplicated and copy-edited.

- [ ] **Step 4: Write `fall_in_love_ru.yaml`**

All 36 questions from **section 2** of the content source, numbers stripped:

```yaml
categories:
  - id: all
    title: 36 вопросов, чтобы влюбиться
    items:
      - Какую первую важную для себя деталь ты отметил(а) во мне?
      # ... 36 total
```

- [ ] **Step 5: Add the loader function**

```python
def load_categories(
    module_id: str, language: Language = Language.RUSSIAN
) -> list[LibraryCategory]:
    """The categories of a `list`-type module, in authored order."""
    data = _load_yaml(module_id, language)
    return [LibraryCategory(**category) for category in data.get("categories", [])]
```

- [ ] **Step 6: Add a duplicate check to the test file**

```python
def test_no_duplicate_ideas_within_a_category():
    for category in load_categories("dates", Language.RUSSIAN):
        assert len(set(category.items)) == len(category.items), category.id
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_library.py -q`
Expected: PASS — 12 tests.

- [ ] **Step 8: Commit**

```bash
git add data/library vechnost_bot/library.py tests/test_library.py
git commit -m "Add 150 date ideas and the 36 questions to the Library

The spicy category carries an nsfw flag so the API can withhold it until
the caller confirms they are 18+.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The 365 reflection questions

**Files:**
- Create: `data/library/reflection_ru.yaml`
- Modify: `vechnost_bot/library.py`
- Modify: `tests/test_library.py`

**Interfaces:**
- Consumes: `_load_yaml` from Task 2.
- Produces:
  - `REFLECTION_TOTAL: int = 365`
  - `load_reflection(language: Language) -> list[list[str]]` — 12 blocks.
  - `question_of_the_day(day_of_year: int, language: Language) -> tuple[str, int]` — returns `(text, day_number)` where `day_number` is 1-based and wrapped into 1..365.

**Content note.** Transcribe **section 5** of the content source. It already drops the duplicated tail from the raw material and resolves the four near-duplicate prompts listed at the end of that file, so `test_no_duplicate_reflection_questions` passes without further edits.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_library.py`:

```python
from vechnost_bot.library import REFLECTION_TOTAL, load_reflection, question_of_the_day

BLOCK_SIZES = [31, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 34]


def test_reflection_has_twelve_blocks_summing_to_365():
    blocks = load_reflection(Language.RUSSIAN)
    assert [len(b) for b in blocks] == BLOCK_SIZES
    assert sum(len(b) for b in blocks) == REFLECTION_TOTAL == 365


def test_first_and_last_question_of_the_year():
    blocks = load_reflection(Language.RUSSIAN)
    assert question_of_the_day(1, Language.RUSSIAN) == (blocks[0][0], 1)
    assert question_of_the_day(365, Language.RUSSIAN) == (blocks[11][33], 365)


def test_leap_day_wraps_to_the_first_question():
    text, day = question_of_the_day(366, Language.RUSSIAN)
    assert (text, day) == question_of_the_day(1, Language.RUSSIAN)


def test_question_of_the_day_is_deterministic():
    assert question_of_the_day(200, Language.RUSSIAN) == question_of_the_day(
        200, Language.RUSSIAN
    )


def test_no_duplicate_reflection_questions():
    flat = [q for block in load_reflection(Language.RUSSIAN) for q in block]
    assert len(set(flat)) == len(flat)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_library.py -q`
Expected: FAIL — `ImportError: cannot import name 'REFLECTION_TOTAL'`.

- [ ] **Step 3: Write `reflection_ru.yaml`**

```yaml
blocks:
  - id: 1
    items:
      - В чём я сегодня был(а) верен/верна себе?
      # ... 31 total
  - id: 2
    items: []   # 30
  # ... through id: 12 with 34
```

Block sizes in order: 31, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 34.

If a duplicate slips through anyway, rewrite the later occurrence rather than deleting it, so the block sizes stay exact. `test_no_duplicate_reflection_questions` is the gate.

- [ ] **Step 4: Add the loader functions**

```python
REFLECTION_TOTAL = 365


def load_reflection(language: Language = Language.RUSSIAN) -> list[list[str]]:
    """The twelve blocks of reflection prompts, in order."""
    data = _load_yaml("reflection", language)
    return [block["items"] for block in data.get("blocks", [])]


def question_of_the_day(
    day_of_year: int, language: Language = Language.RUSSIAN
) -> tuple[str, int]:
    """
    The reflection prompt for a day of the year, plus its 1-based number.

    Day 366 of a leap year wraps back to the first prompt: one repeated day
    beats carrying a 366th question that is unused three years in four.
    """
    index = (day_of_year - 1) % REFLECTION_TOTAL
    flat = [q for block in load_reflection(language) for q in block]
    return flat[index], index + 1
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_library.py -q`
Expected: PASS — 17 tests.

- [ ] **Step 6: Commit**

```bash
git add data/library/reflection_ru.yaml vechnost_bot/library.py tests/test_library.py
git commit -m "Add the 365 self-reflection prompts

Twelve blocks of 31/30x10/34. Day 366 of a leap year wraps to the first
prompt rather than carrying a question unused three years in four.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The Library API

**Files:**
- Modify: `vechnost_bot/freemium.py`
- Create: `vechnost_bot/payments/library_api.py`
- Modify: `vechnost_bot/payments/web.py` (imports block near line 27; `app.include_router` near line 57)
- Test: `tests/test_library_api.py` (create)

**Interfaces:**
- Consumes: `MODULES`, `load_categories`, `load_practices`, `question_of_the_day` from Tasks 2–4; `_request_is_paid` is **not** reused — `library_api.py` gets its own identity handling mirroring `rooms.py`.
- Produces: `router: APIRouter` mounted at `/api/library`; `FREE_LIBRARY_ITEMS_PER_LIST = 3`.

- [ ] **Step 1: Add the freemium constant**

In `vechnost_bot/freemium.py`, below `FREE_CARDS_PER_DECK`:

```python
# Library lists (date ideas, couple practices) show a shorter teaser than
# the decks: three items per category is enough to judge the writing.
FREE_LIBRARY_ITEMS_PER_LIST = 3


def free_library_slice(items: list) -> list:
    """The freely available prefix of one Library list."""
    return list(items[:FREE_LIBRARY_ITEMS_PER_LIST])
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for the Library HTTP API."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")
os.environ["ENABLE_PAYMENT"] = "FALSE"

from vechnost_bot.payments.web import app

client = TestClient(app)


def test_index_lists_all_five_modules():
    body = client.get("/api/library").json()
    ids = [m["id"] for m in body["modules"]]
    assert ids == [
        "dates",
        "fall_in_love",
        "practices_self",
        "practices_couples",
        "reflection",
    ]


def test_paid_caller_gets_every_item():
    body = client.get("/api/library/practices_couples").json()
    assert len(body["items"]) == 25
    assert body["locked"] is False


def test_spicy_category_is_withheld_without_the_nsfw_flag():
    body = client.get("/api/library/dates").json()
    assert "spicy" not in [c["id"] for c in body["categories"]]
    assert body["total"] == 140


def test_spicy_category_is_served_with_the_nsfw_flag():
    body = client.get("/api/library/dates?nsfw=1").json()
    assert "spicy" in [c["id"] for c in body["categories"]]
    assert body["total"] == 150


def test_daily_module_returns_one_question():
    body = client.get("/api/library/reflection").json()
    assert body["type"] == "daily"
    assert body["question"].strip()
    assert 1 <= body["day"] <= 365


def test_unknown_module_is_404():
    assert client.get("/api/library/nope").status_code == 404


@pytest.fixture
def paywalled(monkeypatch):
    """Run the API as if payments were on and the caller had not paid."""
    from vechnost_bot.payments import library_api

    monkeypatch.setattr(library_api, "_caller_is_paid", _unpaid)
    yield


async def _unpaid(_authorization):
    return False


def test_unpaid_caller_gets_three_items_per_category(paywalled):
    body = client.get("/api/library/dates").json()
    assert body["locked"] is True
    assert all(len(c["items"]) == 3 for c in body["categories"])
    assert body["free_count"] == 21   # 7 non-spicy categories x 3
    assert body["total"] == 140


def test_unpaid_caller_gets_three_practices(paywalled):
    body = client.get("/api/library/practices_couples").json()
    assert len(body["items"]) == 3
    assert body["total"] == 25


def test_free_modules_are_identical_for_unpaid_callers(paywalled):
    body = client.get("/api/library/practices_self").json()
    assert len(body["items"]) == 25
    assert body["locked"] is False
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `pytest tests/test_library_api.py -q`
Expected: FAIL — `404 Not Found` on every route; the router does not exist yet.

- [ ] **Step 4: Write the router**

```python
"""Library content API for the Mini App.

Mirrors rooms.py: its own router, its own initData handling, the paywall
enforced here rather than in the client. Paid items are never serialized
for an unpaid caller.
"""

import logging
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..freemium import FREE_LIBRARY_ITEMS_PER_LIST, free_library_slice
from ..i18n import Language
from ..library import (
    MODULES,
    load_categories,
    load_practices,
    question_of_the_day,
)
from .services import user_has_access
from .webapp_auth import InitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/library", tags=["library"])


def _language(lang: str) -> Language:
    try:
        return Language(lang)
    except ValueError:
        return Language.RUSSIAN


async def _caller_is_paid(authorization: Optional[str]) -> bool:
    """Whether this caller may see paid Library content."""
    if not settings.enable_payment:
        return True
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data:
        return False
    try:
        parsed = validate_init_data(init_data, settings.telegram_bot_token)
    except InitDataError as e:
        logger.warning(f"Library initData rejected: {e}")
        return False
    return await user_has_access(parsed["user"]["id"])


@router.get("")
async def library_index(
    lang: str = "ru",
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """The module list for the Library home screen."""
    paid = await _caller_is_paid(authorization)
    return {
        "modules": [
            {
                "id": m.id,
                "title": m.title,
                "emoji": m.emoji,
                "type": m.type,
                "count": m.count,
                "locked": m.paid and not paid,
            }
            for m in MODULES.values()
        ]
    }


@router.get("/{module_id}")
async def library_module(
    module_id: str,
    lang: str = "ru",
    nsfw: int = 0,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """One module's content, already trimmed to what this caller may see."""
    module = MODULES.get(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="unknown module")

    language = _language(lang)
    paid = await _caller_is_paid(authorization)
    locked = module.paid and not paid
    payload: dict[str, Any] = {
        "id": module.id,
        "title": module.title,
        "emoji": module.emoji,
        "type": module.type,
        "locked": locked,
        "free_per_list": FREE_LIBRARY_ITEMS_PER_LIST,
    }

    if module.type == "daily":
        text, day = question_of_the_day(
            date.today().timetuple().tm_yday, language
        )
        payload.update({"question": text, "day": day, "total": module.count})
        return payload

    if module.type == "practice":
        items = load_practices(module_id, language)
        payload.update({
            "items": [i.model_dump() for i in (
                free_library_slice(items) if locked else items
            )],
            "total": len(items),
            "free_count": min(FREE_LIBRARY_ITEMS_PER_LIST, len(items)) if locked else len(items),
        })
        return payload

    categories = [
        c for c in load_categories(module_id, language)
        if not c.nsfw or nsfw == 1
    ]
    payload["categories"] = [
        {
            "id": c.id,
            "title": c.title,
            "nsfw": c.nsfw,
            "items": free_library_slice(c.items) if locked else c.items,
            "total": len(c.items),
        }
        for c in categories
    ]
    payload["total"] = sum(len(c.items) for c in categories)
    payload["free_count"] = sum(
        len(entry["items"]) for entry in payload["categories"]
    )
    return payload
```

- [ ] **Step 5: Mount the router**

In `vechnost_bot/payments/web.py`, beside the existing rooms import and mount:

```python
from .library_api import router as library_router
from .rooms import router as rooms_router
```

```python
app.include_router(rooms_router)
app.include_router(library_router)
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_library_api.py -q`
Expected: PASS — 10 tests.

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS (Redis-marked tests aside).

- [ ] **Step 8: Commit**

```bash
git add vechnost_bot/freemium.py vechnost_bot/payments/library_api.py vechnost_bot/payments/web.py tests/test_library_api.py
git commit -m "Serve the Library over /api/library with the paywall on the server

Unpaid callers get three items per list and never receive the rest; the
18+ date category is withheld unless the request carries nsfw=1.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Library screens in the Mini App

**Files:**
- Modify: `webapp/index.html`

**Interfaces:**
- Consumes: `GET /api/library` and `GET /api/library/{id}` from Task 5.
- Produces: no server-side interface. Later phases add module cards to the `#library` grid.

There is no automated test for this file; the suite does not cover the Mini App. Verification is manual against a local server, per `CLAUDE.md`.

- [ ] **Step 1: Add the home-screen button**

In `#home`, after `#btnCoop`:

```html
<button class="btn btn-second" id="btnLibrary" data-i18n="libraryBtn"></button>
```

- [ ] **Step 2: Add the two screens**

After the `#coop` section:

```html
<section class="screen" id="library">
  <div class="topbar">
    <button class="icon-btn" id="libBackHome">←</button>
    <div class="title" data-i18n="libraryTitle"></div>
    <div style="width:40px"></div>
  </div>
  <div id="libraryList"></div>
</section>

<section class="screen" id="libraryDetail">
  <div class="topbar">
    <button class="icon-btn" id="libBack">←</button>
    <div class="title" id="libDetailTitle"></div>
    <div style="width:40px"></div>
  </div>
  <div id="libDetailBody"></div>
</section>
```

- [ ] **Step 3: Add the UI strings**

In the `I18N` object, add to each of `ru`, `en`, `cs`:

```js
// ru
libraryBtn: '📚 Библиотека', libraryTitle: 'Библиотека',
libLocked: 'Открыть полностью',
libFreeNote: 'Показаны {free} из {total}',
libWhy: 'Зачем', libResult: 'Итог',
libDayOf: 'День {day} из 365',
libLoadError: 'Не удалось загрузить библиотеку. Проверь соединение.',
```

```js
// en
libraryBtn: '📚 Library', libraryTitle: 'Library',
libLocked: 'Unlock everything',
libFreeNote: 'Showing {free} of {total}',
libWhy: 'Why', libResult: 'Outcome',
libDayOf: 'Day {day} of 365',
libLoadError: 'Could not load the library. Check your connection.',
```

```js
// cs
libraryBtn: '📚 Knihovna', libraryTitle: 'Knihovna',
libLocked: 'Odemknout vše',
libFreeNote: 'Zobrazeno {free} z {total}',
libWhy: 'Proč', libResult: 'Výsledek',
libDayOf: 'Den {day} z 365',
libLoadError: 'Knihovnu se nepodařilo načíst. Zkontroluj připojení.',
```

- [ ] **Step 4: Wire up the screens**

These use the helpers that already exist in this file — `$(id)`, `T()` for the current language's I18N table, `fmt(tpl, vars)`, `show(id)`, `toast(msg)`, `escapeHTML(s)`, `haptic(kind)`, `store`, and the module-scope `lang` and `ACCESS`. Do not introduce `api()`, `t()` or a `state` object; they do not exist here.

Add beside the existing screen functions:

```js
  /* ---------------- library ---------------- */
  let LIB_NSFW_PENDING = null;   // module to reopen after the 18+ overlay

  async function libFetch(path) {
    const headers = {};
    if (tg && tg.initData) headers['Authorization'] = 'tma ' + tg.initData;
    const res = await fetch(path, { cache: 'no-cache', headers });
    if (!res.ok) throw new Error('http ' + res.status);
    return res.json();
  }

  async function openLibrary() {
    show('library');
    $('loader').classList.add('show');
    try {
      const data = await libFetch('/api/library?lang=' + lang);
      const box = $('libraryList');
      box.innerHTML = data.modules.map(m => `
        <button class="theme-card" data-module="${m.id}">
          <span class="theme-emoji">${m.emoji}</span>
          <span class="theme-name">${escapeHTML(m.title)}</span>
          <span class="theme-desc">${m.count}${m.locked ? ' · 🔒' : ''}</span>
        </button>`).join('');
      box.querySelectorAll('[data-module]').forEach(btn => {
        btn.onclick = () => openLibModule(btn.dataset.module);
      });
    } catch (e) {
      toast(T().libLoadError);
    } finally {
      $('loader').classList.remove('show');
    }
  }

  async function openLibModule(id) {
    // The 18+ date category needs the same confirmation the Sex deck uses.
    const confirmed = store.get('nsfwOk', false);
    if (id === 'dates' && !confirmed) {
      LIB_NSFW_PENDING = id;
      $('nsfw').classList.add('show');
      return;
    }
    const nsfw = (id === 'dates' && confirmed) ? '&nsfw=1' : '';
    $('loader').classList.add('show');
    try {
      const data = await libFetch(`/api/library/${id}?lang=${lang}${nsfw}`);
      $('libDetailTitle').textContent = data.emoji + ' ' + data.title;
      $('libDetailBody').innerHTML = renderLibModule(data);
      const buy = $('libBuy');
      if (buy) buy.onclick = () => { haptic('light'); $('paywallBuy').click(); };
      show('libraryDetail');
    } catch (e) {
      toast(T().libLoadError);
    } finally {
      $('loader').classList.remove('show');
    }
  }

  function renderLibModule(data) {
    if (data.type === 'daily') {
      return `<div class="lib-daily">
        <div class="lib-day">${fmt(T().libDayOf, { day: data.day })}</div>
        <p class="lib-question">${escapeHTML(data.question)}</p>
      </div>`;
    }
    if (data.type === 'practice') {
      return data.items.map((p, i) => `
        <div class="lib-card">
          <div class="lib-card-title">${i + 1}. ${escapeHTML(p.title)}</div>
          <div class="lib-card-line"><b>${T().libWhy}:</b> ${escapeHTML(p.why)}</div>
          <div class="lib-card-line"><b>${T().libResult}:</b> ${escapeHTML(p.result)}</div>
        </div>`).join('') + libLockedFooter(data);
    }
    return data.categories.map(c => `
      <details class="lib-cat">
        <summary>${escapeHTML(c.title)} · ${c.items.length}${c.items.length < c.total ? '/' + c.total : ''}</summary>
        <ol>${c.items.map(i => `<li>${escapeHTML(i)}</li>`).join('')}</ol>
      </details>`).join('') + libLockedFooter(data);
  }

  function libLockedFooter(data) {
    if (!data.locked) return '';
    const note = fmt(T().libFreeNote, { free: data.free_count, total: data.total });
    const price = ACCESS.price ? ' — ' + ACCESS.price : '';
    return `<div class="lib-locked">
      <p>${note}</p>
      <button class="btn btn-play" id="libBuy">${T().libLocked}${price}</button>
    </div>`;
  }

  $('btnLibrary').onclick = () => { haptic('light'); openLibrary(); };
  $('libBackHome').onclick = () => show('home');
  $('libBack').onclick = () => show('library');
```

Then extend the existing `$('nsfwYes').onclick` handler (currently it always calls `afterNsfw()`), so the same overlay can serve both the Sex deck and the Library:

```js
  $('nsfwYes').onclick = () => {
    store.set('nsfwOk', true);
    $('nsfw').classList.remove('show');
    haptic('ok');
    if (LIB_NSFW_PENDING) {
      const id = LIB_NSFW_PENDING;
      LIB_NSFW_PENDING = null;
      openLibModule(id);
      return;
    }
    afterNsfw();
  };
```

Also clear the pending module when the overlay is dismissed, so a later Sex-deck confirmation does not jump into the Library:

```js
  $('nsfwNo').onclick = () => {
    LIB_NSFW_PENDING = null;
    $('nsfw').classList.remove('show');
  };
```

Finally, add the two screens to the Telegram BackButton chain, beside the existing `invite` / `coop` / `levels` branches:

```js
        else if ($('libraryDetail').classList.contains('active')) show('library');
        else if ($('library').classList.contains('active')) show('home');
```

- [ ] **Step 5: Add the styles**

Beside the existing card styles, matching the brand (dark aubergine, pink gradient accents):

```css
.lib-card{background:rgba(255,255,255,.05);border-radius:16px;padding:14px 16px;margin:10px 0}
.lib-card-title{font-weight:700;margin-bottom:6px}
.lib-card-line{font-size:14px;opacity:.85;margin-top:4px}
.lib-cat{background:rgba(255,255,255,.05);border-radius:16px;padding:12px 16px;margin:10px 0}
.lib-cat summary{font-weight:700;cursor:pointer}
.lib-cat ol{margin:10px 0 0 18px;line-height:1.6}
.lib-daily{text-align:center;padding:32px 20px}
.lib-day{opacity:.6;font-size:14px;margin-bottom:12px}
.lib-question{font-size:20px;line-height:1.5}
.lib-locked{text-align:center;padding:20px;opacity:.9}
```

- [ ] **Step 6: Verify in a browser**

```bash
ENABLE_PAYMENT=FALSE python -m uvicorn vechnost_bot.payments.web:app --reload --port 8000
```

Open `http://localhost:8000/app/` and check, in order: the Library button appears on the home screen; the module grid shows five cards; a practice module renders "Зачем"/"Итог" lines; date ideas render as collapsible categories; opening date ideas raises the 18+ overlay and, after confirming, the "Пикантные" category is present; "Вопрос дня" shows one question with its day number; back buttons return to the right screen. Then restart with `ENABLE_PAYMENT=TRUE` and confirm locked modules show three items per category and an unlock button.

- [ ] **Step 7: Commit**

```bash
git add webapp/index.html
git commit -m "Add the Library screens to the Mini App

A third home button opens a module grid; one detail screen renders all
three content shapes. The 18+ date category reuses the existing NSFW
overlay and the locked state reuses the existing paywall.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Daily push becomes the reflection question

**Files:**
- Modify: `vechnost_bot/daily_card.py`
- Delete: `data/daily_card_exclude.yaml`
- Modify: `data/translations_ru.yaml`, `data/translations_en.yaml`, `data/translations_cs.yaml`
- Rewrite: `tests/test_daily_card.py`

**Interfaces:**
- Consumes: `question_of_the_day`, `REFLECTION_TOTAL` from Task 4.
- Produces: `render_daily_card(day: date, language: Language) -> tuple[BytesIO, str]` — signature unchanged, so `send_daily_cards` and `daily_card_job` keep working. `pick_daily_card` is removed.

- [ ] **Step 1: Rewrite the test file**

```python
"""Tests for the daily self-reflection push."""

import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_FOR_UNIT_TESTS")

from vechnost_bot.daily_card import render_daily_card, send_daily_cards
from vechnost_bot.i18n import Language
from vechnost_bot.library import question_of_the_day


def test_caption_carries_the_day_number():
    day = date(2026, 2, 16)          # day 47 of the year
    assert day.timetuple().tm_yday == 47
    _, number = question_of_the_day(47, Language.RUSSIAN)
    assert number == 47
    _, caption = render_daily_card(day, Language.RUSSIAN)
    assert "47" in caption
    assert "365" in caption


def test_same_day_renders_the_same_card():
    day = date(2026, 5, 5)
    first, _ = render_daily_card(day, Language.RUSSIAN)
    second, _ = render_daily_card(day, Language.RUSSIAN)
    assert first.getvalue() == second.getvalue()


def test_first_and_last_day_of_the_year_render():
    for day in (date(2026, 1, 1), date(2026, 12, 31)):
        image, caption = render_daily_card(day, Language.RUSSIAN)
        assert image.getvalue()
        assert caption.strip()


def test_leap_day_renders_without_raising():
    image, _ = render_daily_card(date(2028, 12, 31), Language.RUSSIAN)   # day 366
    assert image.getvalue()


@pytest.mark.parametrize("language", list(Language))
def test_renders_in_every_language(language):
    image, caption = render_daily_card(date(2026, 3, 3), language)
    assert image.getvalue()
    assert caption.strip()


async def test_blocked_user_is_opted_out():
    from telegram.error import Forbidden

    user = MagicMock(telegram_user_id=42, language="ru")
    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=Forbidden("blocked"))

    with patch("vechnost_bot.payments.repositories.UserRepository") as repo:
        repo.get_daily_card_recipients = AsyncMock(return_value=[user])
        repo.set_daily_card_opt_out = AsyncMock()
        with patch("vechnost_bot.daily_card.get_db"):
            sent = await send_daily_cards(bot)

    assert sent == 0
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_daily_card.py -q`
Expected: FAIL — `ImportError: cannot import name 'send_daily_cards'` is wrong; the real failure is `ImportError` on the removed helpers plus caption assertions, since the module still pushes deck cards.

- [ ] **Step 3: Rewrite the module head**

Replace everything from the docstring through `render_daily_card` with:

```python
"""Daily self-reflection push: one prompt a day for everyone who hasn't opted out.

The prompt is deterministic per calendar date and shared by all users; each
user receives it rendered in their own language.
"""

import logging
from datetime import date
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

from .config import settings
from .i18n import Language, get_text
from .library import REFLECTION_TOTAL, question_of_the_day
from .renderer import render_card

logger = logging.getLogger(__name__)

# Reflection prompts belong to no deck, so they get the neutral background.
_BACKGROUND = str(
    Path(__file__).parent.parent / "assets" / "backgrounds" / "default.png"
)
```

Delete `ELIGIBLE_THEMES`, `_HASH`, `_EXCLUDE_PATH`, `_excluded_texts`, `_eligible_cards`, `pick_daily_card`, and the now-unused imports of `yaml`, `lru_cache`, `localized_game_data`, `ContentType`, `Theme`, and `get_background_path`.

Then:

```python
def render_daily_card(day: date, language: Language):
    """Rendered prompt image + caption for the given date and language."""
    text, number = question_of_the_day(day.timetuple().tm_yday, language)
    watermark = (
        f"VECHNOST · @{settings.bot_username}" if settings.bot_username else "VECHNOST"
    )
    image = render_card(
        text,
        _BACKGROUND,
        footer=get_text('daily.card_footer', language, day=number,
                        total=REFLECTION_TOTAL),
        watermark=watermark,
    )
    caption = (
        f"{get_text('daily.title', language)}\n"
        f"{get_text('daily.subtitle', language, day=number, total=REFLECTION_TOTAL)}"
    )
    return image, caption
```

`send_daily_cards`, `_user_language`, `_daily_keyboard`, and `daily_card_job` are unchanged.

- [ ] **Step 4: Delete the exclude list**

```bash
git rm data/daily_card_exclude.yaml
```

- [ ] **Step 5: Update the translation keys**

`data/translations_ru.yaml`, under `daily`:

```yaml
daily:
  title: "🌙 Вопрос дня"
  subtitle: "День {day} из {total} — один вопрос, чтобы услышать себя."
  card_footer: "Вопрос дня · {day}/{total}"
  play_button: "🎮 Играть"
  unsubscribe_button: "🔕 Больше не присылать"
  resubscribe_button: "🔔 Включить вопрос дня"
  unsubscribed: "🔕 Вопрос дня отключён. Возвращайтесь, когда захотите."
  resubscribed: "🔔 Вопрос дня снова с вами — каждый вечер новый."
```

`data/translations_en.yaml`:

```yaml
daily:
  title: "🌙 Question of the day"
  subtitle: "Day {day} of {total} — one question to hear yourself."
  card_footer: "Question of the day · {day}/{total}"
  play_button: "🎮 Play"
  unsubscribe_button: "🔕 Stop sending"
  resubscribe_button: "🔔 Turn the daily question on"
  unsubscribed: "🔕 The daily question is off. Come back whenever you like."
  resubscribed: "🔔 The daily question is back — a new one every evening."
```

`data/translations_cs.yaml`:

```yaml
daily:
  title: "🌙 Otázka dne"
  subtitle: "Den {day} z {total} — jedna otázka, abys slyšel(a) sám(sama) sebe."
  card_footer: "Otázka dne · {day}/{total}"
  play_button: "🎮 Hrát"
  unsubscribe_button: "🔕 Už neposílat"
  resubscribe_button: "🔔 Zapnout otázku dne"
  unsubscribed: "🔕 Otázka dne je vypnutá. Vrať se, kdykoli budeš chtít."
  resubscribed: "🔔 Otázka dne je zpět — každý večer nová."
```

Keep whatever surrounding keys already exist in each file; only the `daily` block changes.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_daily_card.py -q`
Expected: PASS — 9 tests (5 of them parametrized over the three languages).

- [ ] **Step 7: Check nothing else referenced the removed helpers**

```bash
grep -rn "pick_daily_card\|_eligible_cards\|_excluded_texts\|ELIGIBLE_THEMES\|daily_card_exclude" --include=*.py --include=*.yaml --include=*.md .
```

Expected: no hits outside `docs/` history. Fix any that appear.

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: PASS (Redis-marked tests aside).

- [ ] **Step 9: Commit**

```bash
git add -A vechnost_bot/daily_card.py data tests/test_daily_card.py
git commit -m "Push the daily self-reflection question instead of a deck card

The evening push now walks the 365 reflection prompts by day of year, so
deck curation for pushes is no longer needed and the exclude list is gone.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Delete: `.cursorrules`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code depends on.

- [ ] **Step 1: Update `CLAUDE.md`**

In **Architecture notes**, after the "Content" bullet:

```markdown
- **Library content** lives in `data/library/` — one YAML per module
  (`dates`, `fall_in_love`, `practices_self`, `practices_couples`,
  `reflection`). `library.py` loads it and deliberately imports neither
  FastAPI nor python-telegram-bot, so the bot, the API and the tests can all
  use it. Content is Russian-only for now; other languages fall back to the
  `_ru` file.
```

Amend the **Freemium** bullet to name both constants:

```markdown
- **Freemium is one shared rule.** `freemium.py` holds both constants —
  `FREE_CARDS_PER_DECK = 5` for the decks and
  `FREE_LIBRARY_ITEMS_PER_LIST = 3` for Library lists. They are used by the
  bot card gate (`callback_handlers.py`), the Mini App API
  (`payments/web.py`) and the Library API (`payments/library_api.py`).
  Change a rule there, not in three places.
```

Add after the Mini App auth bullet:

```markdown
- **Two-partner features follow `payments/rooms.py`**: a short room code, both
  players polling for state, a 24-hour TTL, and the room inheriting the
  creator's access so one payment covers both. The compatibility test and the
  69-step game are planned on this same pattern — extend it rather than
  inventing a second pairing mechanism.
```

In **Gotchas**, replace the stale exclude-list warning with:

```markdown
- The evening push is the self-reflection question of the day
  (`daily_card.py` → `library.question_of_the_day`), not a deck card. There is
  no longer a curated exclude list; if you add a prompt that should never be
  pushed, remove it from `data/library/reflection_ru.yaml` and keep the block
  sizes at 31/30×10/34 — `tests/test_library.py` enforces them.
```

- [ ] **Step 2: Update `README.md`**

Add to the **What it is** list, after "Four decks":

```markdown
- **Library.** A second section beside the game: 150 date ideas in 8
  categories, the 36 questions to fall in love, 25 practices for couples and
  25 for yourself, and a year of self-reflection prompts.
```

Replace the daily-card wording in "Growth features" so it reads "a daily self-reflection question", and drop the "Couple mode *(in flight)*" line, replacing it with:

```markdown
- **Couple mode.** Two phones, one shared deck, taking turns — one payment
  covers both partners.
```

In **Project layout**, under `data/`:

```
├── data/                  # questions*.yaml, translations_*.yaml
│   └── library/           # Library content, one YAML per module
```

and add to the `vechnost_bot/` listing:

```
│   ├── library.py         # Library content loader
```

and under `payments/`:

```
│       ├── library_api.py # /api/library
│       ├── rooms.py       # Couple mode
```

Rewrite **Roadmap**:

```markdown
## Roadmap

Recently shipped: freemium funnel, branded card sharing, gift certificates,
full-Cyrillic brand font, Mini App content-API protection, couple mode, and
the Library with its daily self-reflection question.

Next: an interactive couples compatibility test (40 questions, both partners,
compared side by side), the "Territory of Temptation" 18+ board game, and a
guide to shooting tasteful intimate photography. Each builds on the couple-mode
room pattern.
```

- [ ] **Step 3: Delete `.cursorrules`**

```bash
git rm .cursorrules
```

- [ ] **Step 4: Check the docs against reality**

```bash
grep -n "cursorrules" -r --include=*.md . ; ls data/library/ ; pytest -q
```

Expected: no references to the deleted file, five YAML files present, suite green.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Document the Library and drop .cursorrules

Records the second freemium constant, the data/library layout, and rooms.py
as the pattern for two-partner features. Roadmap now reflects what actually
shipped.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification before opening the PR

- [ ] `pytest -q` is green (Redis-marked failures are environmental).
- [ ] `ruff check .` reports no new findings.
- [ ] The Mini App was opened in a browser and every Library screen was clicked through, in both `ENABLE_PAYMENT=FALSE` and `ENABLE_PAYMENT=TRUE`.
- [ ] A daily card image was rendered locally and eyeballed for Cyrillic coverage and legible wrapping:

```bash
python -c "from datetime import date; from vechnost_bot.daily_card import render_daily_card; from vechnost_bot.i18n import Language; img,cap=render_daily_card(date.today(),Language.RUSSIAN); open('/tmp/card.jpg','wb').write(img.getvalue()); print(cap)"
```

- [ ] `git log --oneline master..HEAD` shows eight commits, one per task.

# Library section — design

**Date:** 2026-08-01
**Status:** approved, ready for planning
**Scope:** phase 1 of the Library. Phases 2–4 (compatibility test, "Territory of
Temptation" game, nude-photography masterclass) get their own specs.

## Problem

VECHNOST today is one thing: themed decks of cards you draw one at a time.
All the surrounding material the product has accumulated — date ideas,
relationship practices, self-love practices, the "36 questions to fall in
love" set, a year of self-reflection prompts — has nowhere to live.

The Library is a second home for that material: browsable reference content,
not a draw-one-card loop.

## Non-goals

- The compatibility test (40 questions, two partners, comparison logic).
- "Territory of Temptation 18+: 69 steps" (dice, snakes/arrows, spoilers).
- The nude-photography masterclass (needs 20 pose illustrations that do not
  exist yet).
- Translating Library content to `en` / `cs`.
- Any Library UI in the bot beyond a button that opens the Mini App.
- An archive of past daily reflection questions (explicitly dropped).

Those are separate projects. This spec covers only what ships first.

## Decisions

| Question | Decision |
|---|---|
| Where does it live | Mini App only. The bot gets one button that opens `/app` on the Library screen. |
| Languages | `ru` only; file structure is multilingual from day one, `en`/`cs` fall back to `ru`. |
| Content storage | One YAML file per module under `data/library/`. |
| Navigation | A third button on the Mini App home screen, next to Play and Play-together. |
| Access | Per-module (see the table below); paid modules show the first 3 items of each category free. |
| Reflection questions | Shared by calendar date, replacing the current daily card push entirely. |

## Modules

| Module id | Title (ru) | Items | Render type | Access |
|---|---|---|---|---|
| `dates` | Идеи для свиданий | 150 in 8 categories | `list` | paid, 3 free per category |
| `fall_in_love` | 36 вопросов, чтобы влюбиться | 36 | `list` | free |
| `practices_self` | Практики для себя | 25 | `practice` | free |
| `practices_couples` | Практики для пар | 25 | `practice` | paid, 3 free |
| `reflection` | Вопрос дня | 365 in 12 blocks | `daily` | free |

Total: 601 content items.

### Date-idea categories

| Category | Count | Note |
|---|---|---|
| Домашние и уютные | 25 | |
| На свежем воздухе | 25 | |
| Культурные и необычные | 25 | |
| Экстремальные и активные | 15 | |
| Гастрономические | 10 | |
| Интеллектуальные и глубокие | 15 | |
| Пикантные | 10 | **18+** — gated behind the NSFW confirmation |
| Разное и спонтанное | 25 | |

The "Пикантные" category contains sex-shop trips, role-play, and body art. It
reuses the existing `#nsfw` overlay in the Mini App; without confirmation the
category is not rendered and its items are not sent by the API.

### Render types

Three shapes, not one generic list:

- **`list`** — categories, each a flat list of strings. Used by `dates` and
  `fall_in_love` (the latter has a single implicit category).
- **`practice`** — items of `{title, why, result}`, rendered as cards with
  "Зачем" and "Итог" lines. Used by both practice modules.
- **`daily`** — a single question for today plus its position in the year.

## Content storage

```
data/library/dates_ru.yaml
data/library/fall_in_love_ru.yaml
data/library/practices_self_ru.yaml
data/library/practices_couples_ru.yaml
data/library/reflection_ru.yaml
```

Shapes:

```yaml
# dates_ru.yaml
categories:
  - id: home
    title: Домашние и уютные
    nsfw: false
    items:
      - Смотреть детские фото и видео друг друга
      - ...
```

```yaml
# practices_*_ru.yaml
items:
  - title: 4 минуты смотрите друг другу в глаза
    why: Самый быстрый способ синхронизировать нервные системы…
    result: Глубокое чувство сопричастности, снятие барьеров и доверие.
```

```yaml
# reflection_ru.yaml
blocks:
  - id: 1
    items: [ ... 31 questions ... ]
  - id: 2
    items: [ ... 30 questions ... ]
```

Block sizes are 31, 30 ×10, 34 — 365 total.

**Content-prep note.** The source material for the reflection questions
contains a duplicated tail: months 6 (from item 8) through 12 appear twice.
Deduplicate when transcribing; the first pass is complete.

## Loader

`vechnost_bot/library.py`, modelled on `logic.py`:

- Pydantic models `LibraryModule`, `LibraryCategory`, `Practice`.
- `lru_cache` per (module, language); `en`/`cs` resolve to the `ru` file until
  translations exist.
- `module_index(language)` → the list of modules with titles, emoji, and item
  counts, for the Library home screen.
- Pure functions, no FastAPI or Telegram imports — so it is testable directly
  and reusable from the bot later.

## API

A new router `vechnost_bot/payments/library_api.py`, following the `rooms.py`
precedent: its own `APIRouter`, the same `initData` authentication, the same
`user_has_access` check.

```
GET /api/library?lang=ru
    → { modules: [ { id, title, emoji, count, locked } ] }

GET /api/library/{module}?lang=ru&nsfw=1
    → { id, type, categories | items, free_count, total, locked }
```

Rules:

- **The paywall is enforced server-side.** For an unpaid caller the response
  contains only the free prefix of each category; the paid items are never
  serialized. This matches the existing rule for `/api/questions`.
- `nsfw=1` is required to receive the "Пикантные" category. Absent it, that
  category is omitted from both the payload and the counts.
- Unknown module → 404. Missing/invalid `initData` → 401, same as rooms.

`FREE_LIBRARY_ITEMS_PER_LIST = 3` goes in `freemium.py`, beside
`FREE_CARDS_PER_DECK = 5`, so freemium rules stay in one file.

## Mini App

`webapp/index.html` gains a third home button and two screens:

- **`#library`** — a grid of module cards; paid modules carry a lock badge.
- **`#libraryDetail`** — one screen, three render modes driven by the payload's
  `type`: an accordion of categories for `list`, stacked cards for `practice`,
  a single question for `daily`. Hitting the paywall reuses the existing
  `#paywall` overlay; the 18+ category reuses `#nsfw`.

UI strings go into the existing `I18N` object in all three languages. Content
strings stay Russian-only in this phase — an `en`/`cs` user sees the Library
chrome in their language and the content in Russian.

## Daily push becomes self-reflection

`daily_card.py` is rewritten. The card of the day stops being a question drawn
from the game decks and becomes the reflection question for that calendar day:

```
index = (day_of_year - 1) % 365
```

Consequences:

- `ELIGIBLE_THEMES`, `_eligible_cards()`, `_excluded_texts()`, `_HASH`, and
  `data/daily_card_exclude.yaml` are **deleted** — deck curation for pushes is
  no longer needed.
- The card is rendered on `assets/backgrounds/default.png`, since a reflection
  question belongs to no theme.
- The caption carries "День N из 365".
- The 12 blocks land on the calendar with a drift of a couple of days (February
  has 28 days against a 30-question block). This is invisible because the
  blocks are never labelled with month names.
- On a leap year, 29 December repeats the question of day 365. Only the last
  day of a leap year is affected.
- Opt-out (`daily_card_opt_out`), the unsubscribe button, and per-language
  rendering are unchanged.

`get_text` keys for the daily push change (`daily.title`, `daily.subtitle`,
`daily.card_footer`) and need new copy in `data/translations_{ru,en,cs}.yaml`.

## Testing

`tests/test_library.py`:

- every YAML file loads and the item counts match this spec (150 / 36 / 25 /
  25 / 365);
- an unpaid caller receives exactly 3 items per category of a paid module;
- a paid caller receives all of them;
- a free module is identical for both;
- without `nsfw=1` the "Пикантные" category is absent from the payload;
- missing `initData` → 401.

`tests/test_daily_card.py` is rewritten:

- the same date yields the same question;
- day 1 → block 1 item 1, day 365 → block 12 item 34;
- day 366 wraps to index 0 without raising;
- rendering succeeds for all three languages.

The suite stays offline. Redis-marked tests are untouched.

## Documentation

- **CLAUDE.md** — add `data/library/` and `library_api.py` to the architecture
  notes; record that `freemium.py` now holds two constants; note that the daily
  push is self-reflection and the exclude file is gone; point at `rooms.py` as
  the pattern for future two-partner features.
- **README.md** — the Library in the feature list, `data/library/` in the
  project layout, and a Roadmap that reflects reality (couple mode is merged,
  not in flight).
- **`.cursorrules`** is deleted.

## Out of scope, tracked separately

A prior commit on this branch updates existing deck content in
`data/questions.yaml`: replacement questions for Sex (1, 3, 27, 30, 31, 33, 40,
45, 51, 70), For Couples level 1 (7, 22) and level 2 (3, 24, 30), Acquaintance
level 3 (3, 13, 24, 26, 28, 30), Provocation (2, 6, 9, 10, 12, 14, 15, 20), and
a "партнерка" → "партнерша" wording fix. It is unrelated to the Library and
lands on its own.

`data/daily_card_exclude.yaml` matches questions by exact string, so replacing
question texts orphans some of its entries. That is harmless here only because
the daily-card rewrite deletes the file outright. If the Library work is ever
dropped and the content commit ships alone, the exclude list must be re-checked
against the new texts.

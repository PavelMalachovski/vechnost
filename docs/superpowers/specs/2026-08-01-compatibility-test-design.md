# Couples compatibility test — design

**Date:** 2026-08-01
**Status:** approved, ready for planning
**Branch:** `feature/compatibility-test`, cut from `master` at d900ca3

## Problem

VECHNOST asks couples questions one card at a time. Nothing in it tells a
couple where they actually stand — which parts of their life together are
solid, which are quietly eroding, and which they see completely differently
without knowing it.

This adds a 40-question test both partners take separately. The product is
not the score; it is the list of places where their answers diverged, which
neither of them could have found alone.

## Non-goals

- Showing either partner the other's individual answers.
- A history of past attempts. Retaking replaces the previous result.
- Any advice beyond the authored verdict texts. This is not therapy, and the
  critical-zone copy says so by pointing at a family psychologist.
- Translating the test to `en`/`cs`. Russian only, like the rest of the
  Library's content.

## Decisions

| Question | Decision |
|---|---|
| Pairing | A six-character invite code, the `rooms.py` pattern — but no TTL. |
| Persistence | Indefinite. Retaking deletes the previous completed session's answers for that pair. |
| Privacy | Individual answers never leave the server. |
| Access | Paid, in full. The creator's payment covers both partners. |
| Entry point | A fourth button on the Mini App home screen. |
| Languages | `ru` only. |

## Content

40 questions in 8 spheres of 5, and 24 verdict texts (8 spheres × 3
scenarios), all authored. Sphere order is fixed and is the order results are
presented in:

1. Ценности и цели (questions 1–5)
2. Финансы (6–10)
3. Коммуникация и конфликты (11–15)
4. Секс и близость (16–20)
5. Быт и пространство (21–25)
6. Доверие и безопасность (26–30)
7. Социальный круг (31–35)
8. Эмоциональный интеллект (36–40)

Answer scale, shown to the user on every question:

| 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|
| Категорически нет | Скорее нет | Затрудняюсь ответить | Скорее да | Полностью да |

## Scoring

All arithmetic is defined here so nothing about the result is a black box.

For each sphere, given partner A's five answers and partner B's five:

- `avg_a` = mean of A's five answers, `avg_b` = mean of B's — each in 1..5.
- `max_gap` = the largest `|a_i − b_i|` across the sphere's five questions.

The sphere lands in exactly one zone, checked in this order:

1. **Критическая зона** — `(avg_a < 3 and avg_b < 3)` or `max_gap > 3`.
   Renders the sphere's **Кризис** text.
2. **Сфера силы** — `avg_a >= 4 and avg_b >= 4`.
   Renders the sphere's **Синергия** text.
3. **Зона роста** — everything else. Renders the sphere's **Дисбаланс** text.

The zones and the scenarios are the same classification under two names:
"Сфера силы" is where Синергия is shown, "Зона роста" where Дисбаланс is,
"Критическая зона" where Кризис is. There is no fourth state.

**Overall percentage.** Each sphere scores `(avg_a + avg_b) / 2` on 1..5. The
overall figure is the mean of the eight sphere scores, mapped onto 0–100 by
`(x − 1) / 4 × 100`, rounded to a whole number. Two partners who both answer
5 everywhere get 100%; both answering 1 get 0%.

**Divergent questions.** Any question where `|a_i − b_i| >= 3` — "расхождение
более чем на 2 балла". These are the numbers the result tells the couple to
discuss.

## What the result shows

In this order:

1. **Percentage**, with the count of spheres in each zone beneath it.
2. **Топ-3 сферы, где вы идеальная команда** — the spheres in Сфера силы,
   highest-scoring first, at most three. Each carries its Синергия text.

   A couple may have none. Promoting their least-bad spheres under a heading
   that calls them an ideal team would be a lie, so when the list is empty the
   block is replaced by a single line: «Пока ни одна сфера не вышла в зону
   силы — и это не приговор, а точка, с которой видно, куда расти.» This is
   the only sentence in the feature not authored by the product owner; it is
   marked as such in the content file so it can be rewritten.
3. **Топ-2 сферы, которые требуют разговора** — the two lowest-scoring
   spheres, each with its verdict text and the numbers of its divergent
   questions. Each is introduced by one of the two authored framings, chosen
   by what triggered it:
   - large gap → «Вы по-разному ощущаете… Один из вас удовлетворён, а другой
     чувствует дефицит. Это почва для скрытых обид».
   - both low → «Это ваша общая "болевая точка". Вы оба чувствуете проблему
     здесь, и это хорошая новость — вы признаёте реальность и можете начать
     работу».
4. **Рекомендация** — «Обсудите вопросы №… из теста сегодня вечером за чаем»,
   listing every divergent question across all spheres.
5. **Per-sphere breakdown** — all eight, in the fixed order above, each with
   its zone and its verdict text.
6. **If any sphere is in the критическая зона**, the authored 💡 block, once
   per such sphere: the sphere's name, its divergent question numbers, and the
   suggestion to see a family psychologist.

## Data model

A new table `compat_tests`, following `rooms`:

| Column | Notes |
|---|---|
| `id` | PK |
| `code` | unique, six chars from the same unambiguous alphabet `rooms.py` uses |
| `creator_telegram_user_id`, `creator_name` | |
| `guest_telegram_user_id`, `guest_name` | null until joined |
| `creator_answers`, `guest_answers` | `JSONEncodedDict`, a list of 40 ints or nulls |
| `pair_key` | `"<lower_id>:<higher_id>"`, set when the guest joins |
| `finished_at` | set when both have answered all 40 |
| `created_at`, `updated_at` | |

Indexed on `code` and on `pair_key`.

**No TTL.** Unlike rooms, a completed test is meant to be re-read.

**Retaking.** Creating a test writes a new row. When that row completes, every
*other* row with the same `pair_key` is deleted outright. The couple sees one
result, and the sensitive answers behind superseded results do not linger.

Migration plus the idempotent startup add, both, per `CLAUDE.md`.

## Code

| File | Responsibility |
|---|---|
| `data/library/compat_ru.yaml` | 40 questions in 8 spheres, 24 verdict texts, the two framings, the scale labels |
| `vechnost_bot/compat.py` | loading, scoring, zone classification, result assembly — pure functions, importing neither FastAPI nor python-telegram-bot |
| `vechnost_bot/payments/compat_api.py` | the `/api/compat` router, modelled on `rooms.py` |
| `vechnost_bot/payments/models.py` | the `CompatTest` model |
| `vechnost_bot/payments/repositories.py` | `CompatTestRepository` |
| `alembic/versions/*_add_compat_tests_table.py` | migration |
| `webapp/index.html` | home button and the test's screens |

`compat.py` mirrors `library.py`: it is the domain layer, usable from the web
API, the bot, and tests without adapters.

## API

```
POST /api/compat                      → create a session, returns the code
POST /api/compat/{code}/join          → join by code
GET  /api/compat/{code}               → state for the caller
POST /api/compat/{code}/answer        → {index: 0..39, value: 1..5}
GET  /api/compat/{code}/result        → 409 until both have finished
GET  /api/compat/mine                 → the caller's latest completed session
```

Rules:

- Authentication is Telegram `initData`, exactly as `rooms.py` does it,
  including the `X-Guest-Id` fallback when payments are disabled.
- Access is checked at creation with `user_has_access`; the room-style
  inheritance applies, so the creator's payment covers the guest.
- `GET /api/compat/{code}` returns the caller's own answered count and the
  partner's answered **count only** — never their values.
- `/result` returns the assembled result and, per the privacy decision,
  contains no individual answers at all: percentages, zones, verdict texts,
  and question numbers.
- A caller who is neither participant gets 403; an unknown code gets 404.

## Notifications

When the second partner's fortieth answer lands, the bot sends both a short
message with a button into the result. The second partner may finish hours or
days after the first, and without a push the moment is lost. Reuses the
existing `WEBAPP_URL` guard; silently skipped when unset.

## Testing

`tests/test_compat.py` — the scoring layer, directly:

- all 40 questions load, 8 spheres of 5, and all 24 verdict texts are present
  and non-empty;
- both partners answering 5 everywhere → 100%, all eight in Сфера силы;
- both answering 1 → 0%, all eight in Критическая зона;
- a sphere where one answers 5 and the other 3 throughout → Зона роста, and
  those questions are *not* in the divergent list (gap 2 is under the
  threshold);
- a single question with a gap of 4 puts its sphere in Критическая зона even
  when both averages are high;
- a sphere with both averages at 2.9 is critical; at 3.0 it is not;
- divergent-question numbering is 1-based and matches the authored numbering.

`tests/test_compat_api.py` — the HTTP layer:

- the partner's answers never appear in any response body, at any stage;
- `/result` is 409 until both are finished;
- a third party gets 403;
- an unpaid creator cannot create a session; a guest joining a paid creator's
  session can answer;
- completing a retake deletes the previous completed session for that pair.

## Open items

One line of copy — the empty-Сфера-силы fallback quoted above — was written
by the implementer rather than the product owner, and is flagged in the
content file for rewriting. Everything else is authored: the 40 questions,
the 24 verdict texts, both framings, the critical-zone block and the scale
labels. The spheres, thresholds and output order are fixed above.

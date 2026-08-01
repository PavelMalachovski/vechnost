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
| Persistence | Indefinite. Retaking deletes the previous completed session's answers for that pair, and either partner can delete the current one outright at any time. |
| Privacy | Individual answers never leave the server, and nothing the result carries inverts back to them. |
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

1. **Percentage**, with the count of spheres in each zone beneath it —
   «Сфера силы — 3 · Зона роста — 4 · Критическая зона — 1». All three zones
   are named even at zero: an omitted line reads as "not measured" rather
   than "none". The percentage says how close the couple is; this says how
   that closeness is distributed, which two couples on the same percentage do
   not share.
2. **Топ-3 сферы, где вы идеальная команда** — the spheres in Сфера силы,
   highest-scoring first, at most three. Each carries its Синергия text.

   A couple may have none. Promoting their least-bad spheres under a heading
   that calls them an ideal team would be a lie, so when the list is empty the
   block is replaced by a single line: «Пока ни одна сфера не вышла в зону
   силы — и это не приговор, а точка, с которой видно, куда расти.» This is
   the only sentence in the feature not authored by the product owner; it is
   marked as such in the content file so it can be rewritten.
3. **Топ-2 сферы, которые требуют разговора** — the two lowest-scoring
   spheres **that are not in Сфера силы**, each with its verdict text and the
   numbers of its divergent questions.

   The exclusion is not a detail. Taking the two lowest unconditionally means
   a couple whose spheres cluster — seven at 4.0 and one at 3.0 — sees a
   strength sphere listed as needing a conversation, labelled "Сфера силы" in
   both blocks at once. If no sphere qualifies, the block and its heading are
   omitted entirely: a couple with eight strong spheres is not handed an
   invented problem.

   Each entry is introduced by one of the two authored framings when one of
   them is true, chosen by what put the sphere there:
   - large gap → «Вы по-разному ощущаете… Один из вас удовлетворён, а другой
     чувствует дефицит. Это почва для скрытых обид».
   - both low → «Это ваша общая "болевая точка". Вы оба чувствуете проблему
     здесь, и это хорошая новость — вы признаёте реальность и можете начать
     работу».

   A sphere can reach this block through neither route — simply by being the
   weakest of eight middling ones. Neither framing is true about it, so it
   gets none, and `framing` serializes as `null`. Consumers must guard.
4. **Рекомендация** — «Обсудите вопросы №… из теста сегодня вечером за чаем»,
   listing every divergent question across all spheres.
5. **If any sphere is in the критическая зона**, the authored 💡 block, once
   per such sphere: the sphere's name, its divergent question numbers, and the
   suggestion to see a family psychologist.
6. **Per-sphere breakdown** — all eight, in the fixed order above, each with
   its zone and its verdict text.

   *Changed 2026-08-01, post-review:* this spec originally put the breakdown
   at 5 and the critical blocks at 6, and the implementation shipped them the
   other way round. The implementation is right and the spec was changed to
   match. Everything above the breakdown is what the couple should act on;
   the breakdown is an eight-card reference list, and putting the "see a
   family psychologist" advice after it buries the single most important
   sentence in the result below a long scroll.
7. **Deletion** — a control that erases the test and both answer sets, at the
   very bottom, behind a confirmation. See the API section.

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

An alembic revision is needed. The idempotent startup hook is **not**:
`create_tables()` runs `Base.metadata.create_all`, which creates missing
tables on its own. `database.py::_ensure_user_columns` exists only because
`create_all` never *alters* an existing table, so it covers new columns on
`users` — a brand-new table needs nothing from it. `CLAUDE.md`'s "do both"
rule is about columns, and does not apply here.

## Code

| File | Responsibility |
|---|---|
| `data/library/compat_ru.yaml` | 40 questions in 8 spheres, 24 verdict texts, the two framings, the scale labels |
| `vechnost_bot/compat.py` | loading, scoring, zone classification, result assembly — pure functions, importing neither FastAPI nor python-telegram-bot |
| `vechnost_bot/payments/compat_api.py` | the `/api/compat` router, modelled on `rooms.py` |
| `vechnost_bot/payments/models.py` | the `CompatTest` model |
| `vechnost_bot/payments/repositories.py` | `CompatTestRepository` |
| `alembic/versions/*_add_compat_tests_table.py` | migration |
| `docs/superpowers/specs/2026-08-01-compatibility-test-source-content.md` | the 40 questions and 24 verdict texts verbatim, the source the YAML is transcribed from |
| `webapp/index.html` | home button and the test's screens |

`compat.py` mirrors `library.py`: it is the domain layer, usable from the web
API, the bot, and tests without adapters.

## API

```
GET  /api/compat/questions            → the 40 questions and the answer scale
POST /api/compat                      → create a session, returns the code
POST /api/compat/{code}/join          → join by code
GET  /api/compat/{code}               → state for the caller
POST /api/compat/{code}/answer        → {index: 0..39, value: 1..5}
GET  /api/compat/{code}/result        → 409 until both have finished
GET  /api/compat/mine                 → the caller's latest completed session
DELETE /api/compat/{code}             → erase the test and both answer sets
```

`/questions` needs no authentication: the questions are the product's shop
window, they reveal nothing about anyone, and gating them would only mean the
client cannot render the test it already paid to create. Access is enforced
where it matters — at creation.

Rules:

- Authentication is Telegram `initData`, exactly as `rooms.py` does it,
  including the `X-Guest-Id` fallback when payments are disabled.
- Access is checked at creation with `user_has_access`; the room-style
  inheritance applies, so the creator's payment covers the guest.
- `GET /api/compat/{code}` returns the caller's own answered count *and the
  indices they have answered*, and the partner's answered **count only** —
  never the partner's indices, and never anyone's values. The indices are
  what lets the client resume an interrupted test at the first gap; a test
  designed to be taken hours or days apart cannot restart at question 1
  every time the app closes.
- `/result` returns the assembled result and, per the privacy decision,
  contains no individual answers at all: percentages, zones, verdict texts,
  and question numbers. It carries **no per-sphere score**. A score is
  `(avg_a + avg_b) / 2` over five questions, so a partner who knows their own
  five recovers `sum_theirs = 10 * score - sum_mine` exactly — at a sphere
  sum of 25 that pins every individual answer. The score lives inside
  `build_result` as a list parallel to the results, used only to order
  `strengths` and `attention`. The overall `percent` stays public, and it is
  worth being exact about what that costs rather than calling it harmless.
  `percent = round((T − 80) × 5/16)` over the combined forty-question total
  `T`, so each percentage point maps to three or four values of `T`: a
  partner who knows their own total recovers the other's to within one
  point, their mean to within 0.025. What it never does is localise — it
  says nothing about any sphere or any question.

  Two further channels are inherent to the product rather than incidental.
  A question listed as divergent has a gap of exactly 3 in any non-crisis
  sphere, which pins the partner's answer to a single value; and a zone
  bounds their sphere average into a band. Measured over 2400 spheres this
  pins about one question in seven and reconstructs no whole sphere. That
  disclosure *is* the feature — the Mini App promises «только то, в чём вы
  разошлись» — and telling someone they diverged is not separable from
  implying roughly what the other answered. The line worth holding is the
  one drawn here: no exact per-sphere arithmetic on the wire.
- `DELETE /api/compat/{code}` erases the row outright, finished or not.
  Either participant may call it, acting alone: there is one shared row, and
  consent to keep answers about a couple's sex life, money and trust has to
  be unanimous. `delete_superseded` is not enough — it only fires when a pair
  *completes* a retake, so a couple who answer twenty each and stop had no
  way to remove forty real answers.
- `POST /api/compat/{code}/answer` loads the row `FOR UPDATE`. It is a
  read-modify-write of the whole 40-element array, and the client can have
  several in flight; without the lock, on READ COMMITTED the second
  transaction writes back a stale copy of every index but its own and one
  answer silently vanishes. The Mini App also refuses to send a second answer
  until the first resolves — the lock is correctness, the client is latency.
- A caller who is neither participant gets 403; an unknown code gets 404.

## Notifications

When the second partner's fortieth answer lands, the bot sends both a short
message with a button into the result. The second partner may finish hours or
days after the first, and without a push the moment is lost. Reuses the
existing `WEBAPP_URL` guard; the button is omitted when unset.

The button is `web_app=WebAppInfo(url=...)`, like every other Mini App entry
point in the repo, **not** `url=`: a plain url opens Telegram's in-app
browser, where `Telegram.WebApp.initData` is empty, so the client falls back
to the guest path and `_caller` 401s in production. The push's only call to
action would dead-end.

Each partner is messaged in their own language, looked up through
`UserRepository` exactly as `daily_card.py::send_daily_cards` does, falling
back to Russian. The `compat.*` keys exist in all three translation files.

The send happens **after** the answer's transaction commits, from ids
captured before leaving the `async with`. Announcing the result before
`finished_at` is durable sends both partners to a 409, and two Telegram
round-trips inside the transaction would make the fortieth `POST /answer`
block on the network while holding a pooled connection and a row lock.

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
- no `score` appears in `/result` or `/mine`, and given one partner's answers
  plus the whole payload, no number in it inverts to the other partner's
  per-sphere sums;
- `/result` is 409 until both are finished;
- a third party gets 403;
- an unpaid creator cannot create a session; a guest joining a paid creator's
  session can answer;
- completing a retake deletes the previous completed session for that pair;
- the fortieth answer notifies both partners exactly once, and nobody is
  notified before that;
- `answered_indices` holds the caller's own indices and never the partner's;
- either participant can delete the test, finished or not; a third party gets
  403 and an unknown code 404.

`notify_result_ready` is patched in `test_compat_api.py`'s fixture. A fake
token is set at import, so without the patch `_bot()` builds a real `Bot` and
every test that completes a session fires two live HTTPS requests at
api.telegram.org. They fail as `InvalidToken` and are swallowed, so the suite
passes either way — which is the problem: in a network-isolated CI they
become connect timeouts.

## Open items

One line of copy — the empty-Сфера-силы fallback quoted above — was written
by the implementer rather than the product owner, and is flagged in the
content file for rewriting. Everything else is authored: the 40 questions,
the 24 verdict texts, both framings, the critical-zone block and the scale
labels. The spheres, thresholds and output order are fixed above.

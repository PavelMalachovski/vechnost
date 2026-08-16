# Единый карточный облик + переход на русский — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Бот и Mini App показывают любой текст на одной и той же настоящей карте VECHNOST, длинный текст прокручивается внутри карты, интерфейс и контент — только на русском.

**Architecture:** Карты уже существуют как PNG в `assets/backgrounds/`; Mini App перестаёт имитировать их в CSS и начинает брать те же файлы через новый статический маунт `/assets`. Две недостающие карты (лицевая библиотеки и рубашка) генерируются скриптом на Pillow и коммитятся как PNG. Свайп-движок Mini App параметризуется колбэками, чтобы библиотека переиспользовала его, а не копировала.

**Tech Stack:** Python 3.11, Pillow, FastAPI + StaticFiles, python-telegram-bot, pytest (`asyncio_mode = "auto"`), ванильный JS/CSS в одном `webapp/index.html`.

## Global Constraints

- Спека: `docs/superpowers/specs/2026-08-16-card-identity-and-ru-only-design.md`.
- Ветка: `feature/card-identity`, ответвлённая от `master`.
- Шрифты: **Forum** — литеры `V`/`Λ` и ранги `2`/`3`; **Lora** — словесный знак `VECHNOST`; **Inter** — весь остальной текст. Все три под SIL OFL, все три с кириллицей.
- Размер карты для бота: 1080×1350, как у существующих фонов.
- Реальное соответствие мастей: Знакомство ♥, Для пар ♠, Секс ♣, Провокация ♦.
- Единственный язык — русский. `Language` содержит только `RUSSIAN = "ru"`.
- `library_api.py` не меняется: пейволл и 18+ остаются серверными.
- Тесты гоняются из корня репозитория: `pytest`. Тесты с маркером `redis` требуют `localhost:6379`; их падение без Redis — окружение, а не регрессия.
- Не создавать `pytest.ini` — конфиг живёт в `pyproject.toml`.

---

## Структура файлов

**Создаются:**
- `assets/fonts/Forum-Regular.ttf`, `Lora-Regular.ttf`, `Inter-Regular.ttf`, `Inter-SemiBold.ttf` — шрифты для Pillow.
- `webapp/fonts/forum-400.woff2`, `lora-400.woff2`, `inter-400.woff2`, `inter-600.woff2`, `inter-700.woff2` — те же для Mini App.
- `scripts/generate_card_assets.py` — генератор двух недостающих карт.
- `assets/backgrounds/library.png` — лицевая карта библиотеки и вопроса дня.
- `assets/backgrounds/card_back.png` — общая рубашка.
- `tests/test_card_assets.py` — проверки на существование и геометрию новых карт и шрифтов.
- `tests/test_webapp_static.py` — проверки, что `/assets` отдаёт карты, а `index.html` на них ссылается.

**Меняются:**
- `vechnost_bot/renderer.py` — Inter вместо Montserrat.
- `vechnost_bot/daily_card.py` — фон вопроса дня.
- `vechnost_bot/payments/web.py` — маунт `/assets`.
- `vechnost_bot/i18n.py` — один язык + `Language.coerce`.
- `vechnost_bot/handlers.py`, `vechnost_bot/callback_handlers.py`, `vechnost_bot/keyboards.py` — убрать выбор языка.
- `webapp/index.html` — карты, главный экран, скролл, библиотека-колода, один язык.
- `data/questions.yaml`, `data/library/*.yaml` — тире.

**Удаляются:**
- `vechnost_bot/language_keyboards.py`
- `data/questions_en.yaml`, `data/questions_cs.yaml`, `data/translations_en.yaml`, `data/translations_cs.yaml`

---

### Task 1: Шрифты в репозитории

**Files:**
- Create: `assets/fonts/Forum-Regular.ttf`, `assets/fonts/Lora-Regular.ttf`, `assets/fonts/Inter-Regular.ttf`, `assets/fonts/Inter-SemiBold.ttf`
- Create: `webapp/fonts/forum-400.woff2`, `webapp/fonts/lora-400.woff2`, `webapp/fonts/inter-400.woff2`, `webapp/fonts/inter-600.woff2`, `webapp/fonts/inter-700.woff2`
- Create: `tests/test_card_assets.py`
- Modify: `vechnost_bot/renderer.py:49-54`

**Interfaces:**
- Consumes: ничего.
- Produces: `renderer.FONT_PATH` (Inter Regular), `renderer.LOGO_FONT_PATH` (Lora Regular), `renderer.EMBLEM_FONT_PATH` (Forum Regular), `renderer.FALLBACK_FONT_PATH` (DejaVu) — все `pathlib.Path`.

- [ ] **Step 1: Написать падающий тест**

`tests/test_card_assets.py`:

```python
"""The brand fonts and generated cards must actually be in the repo.

They are binary assets no other test would notice missing: the renderer
silently falls back to DejaVu, and a missing background raises only at
render time, inside a try block.
"""

from pathlib import Path

import pytest
from PIL import Image, ImageFont

REPO_ROOT = Path(__file__).parent.parent
FONTS = REPO_ROOT / "assets" / "fonts"
WEBAPP_FONTS = REPO_ROOT / "webapp" / "fonts"

# One representative letter per alphabet the cards actually set.
CYRILLIC = "Ж"
LATIN = "V"


@pytest.mark.parametrize("name", [
    "Forum-Regular.ttf", "Lora-Regular.ttf",
    "Inter-Regular.ttf", "Inter-SemiBold.ttf",
])
def test_brand_font_is_present_and_loadable(name):
    path = FONTS / name
    assert path.exists(), f"missing font {name}"
    ImageFont.truetype(str(path), 48)


@pytest.mark.parametrize("name", [
    "Forum-Regular.ttf", "Lora-Regular.ttf", "Inter-Regular.ttf",
])
def test_brand_font_covers_cyrillic(name):
    """Russian is the only language now — a latin-only subset would tofu."""
    font = ImageFont.truetype(str(FONTS / name), 48)
    notdef = bytes(font.getmask("￾"))
    assert bytes(font.getmask(CYRILLIC)) != notdef
    assert bytes(font.getmask(LATIN)) != notdef


@pytest.mark.parametrize("name", [
    "forum-400.woff2", "lora-400.woff2",
    "inter-400.woff2", "inter-600.woff2", "inter-700.woff2",
])
def test_webapp_font_is_present(name):
    path = WEBAPP_FONTS / name
    assert path.exists(), f"missing webapp font {name}"
    assert path.stat().st_size > 1000, f"{name} looks like an error page"
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_card_assets.py -q`
Expected: FAIL, `missing font Forum-Regular.ttf`

- [ ] **Step 3: Скачать TTF для Pillow**

Google Fonts отдаёт TTF, если не притворяться современным браузером:

```bash
mkdir -p assets/fonts
UA_OLD="Mozilla/4.0"
css() { curl -sS -A "$UA_OLD" "https://fonts.googleapis.com/css2?family=$1"; }
css "Forum" | grep -o 'https://[^)]*\.ttf' | head -1 | xargs curl -sSL -o assets/fonts/Forum-Regular.ttf
css "Lora:wght@400" | grep -o 'https://[^)]*\.ttf' | head -1 | xargs curl -sSL -o assets/fonts/Lora-Regular.ttf
css "Inter:wght@400" | grep -o 'https://[^)]*\.ttf' | head -1 | xargs curl -sSL -o assets/fonts/Inter-Regular.ttf
css "Inter:wght@600" | grep -o 'https://[^)]*\.ttf' | head -1 | xargs curl -sSL -o assets/fonts/Inter-SemiBold.ttf
```

- [ ] **Step 4: Скачать woff2 для Mini App**

Современный UA даёт woff2, разбитый по `unicode-range`. Нужны кириллический и латинский поднаборы; берём тот блок, в чьём `unicode-range` есть `U+0400`, и латинский — и склеиваем в один файл нельзя, поэтому качаем оба и подключаем двумя `@font-face` с одинаковым `font-family`.

```bash
mkdir -p webapp/fonts
UA_NEW="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
python scripts/fetch_webapp_fonts.py
```

`scripts/fetch_webapp_fonts.py` (создаётся в этом же шаге):

```python
"""Fetch the cyrillic+latin woff2 subsets of the brand fonts for the Mini App.

Google Fonts serves one @font-face per unicode-range; the Mini App needs the
cyrillic and latin blocks of each family and nothing else, which keeps the
whole typographic payload under ~120 KB.
"""

import re
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
OUT = Path(__file__).parent.parent / "webapp" / "fonts"

# family query -> output stem
WANTED = {
    "Forum": "forum-400",
    "Lora:wght@400": "lora-400",
    "Inter:wght@400": "inter-400",
    "Inter:wght@600": "inter-600",
    "Inter:wght@700": "inter-700",
}

_BLOCK = re.compile(r"unicode-range:([^;]+);", re.S)
_FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
_URL = re.compile(r"url\((https://[^)]+\.woff2)\)")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:
        return r.read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for family, stem in WANTED.items():
        css = _get(f"https://fonts.googleapis.com/css2?family={family}").decode()
        for face in _FACE.findall(css):
            ranges = _BLOCK.search(face)
            url = _URL.search(face)
            if not ranges or not url:
                continue
            text = ranges.group(1)
            if "U+0301" in text or "U+0400" in text:
                suffix = ""          # cyrillic block -> the primary file
            elif text.strip().startswith("U+0000"):
                suffix = "-latin"    # basic latin block
            else:
                continue
            path = OUT / f"{stem}{suffix}.woff2"
            path.write_bytes(_get(url.group(1)))
            print(f"{path.name}  {path.stat().st_size} B")


if __name__ == "__main__":
    main()
```

Тест ждёт файлы без суффикса (`forum-400.woff2` и т.д.) — это кириллические поднаборы, они и есть основные для русского интерфейса.

- [ ] **Step 5: Запустить тест — должен пройти**

Run: `pytest tests/test_card_assets.py -q`
Expected: PASS

- [ ] **Step 6: Переключить рендерер на Inter**

`vechnost_bot/renderer.py`, заменить блок на строках 49-54:

```python
# Brand fonts (ship in assets/fonts, all three cover Cyrillic):
#   Inter  — the text of every card
#   Lora   — the VECHNOST wordmark
#   Forum  — the V/Λ letters and the 2/3 ranks
# DejaVu stays as a last resort: _pick_font_path still checks coverage, so a
# text with an alphabet Inter lacks (Greek, say) degrades instead of tofuing.
_ASSETS_FONTS = Path(__file__).parent.parent / "assets" / "fonts"
FONT_PATH = _ASSETS_FONTS / "Inter-Regular.ttf"
LOGO_FONT_PATH = _ASSETS_FONTS / "Lora-Regular.ttf"
EMBLEM_FONT_PATH = _ASSETS_FONTS / "Forum-Regular.ttf"
FALLBACK_FONT_PATH = _ASSETS_FONTS / "DejaVuSans.ttf"
```

- [ ] **Step 7: Убедиться, что рендер не сломался**

Run: `pytest tests/test_renderer.py tests/test_daily_card.py -q`
Expected: PASS

- [ ] **Step 8: Коммит**

```bash
git add assets/fonts webapp/fonts scripts/fetch_webapp_fonts.py tests/test_card_assets.py vechnost_bot/renderer.py
git commit -m "Set the cards in Inter, Lora and Forum"
```

---

### Task 2: Две недостающие карты

**Files:**
- Create: `scripts/generate_card_assets.py`
- Create: `assets/backgrounds/library.png`, `assets/backgrounds/card_back.png`
- Modify: `tests/test_card_assets.py`

**Interfaces:**
- Consumes: `assets/fonts/{Forum,Lora}-Regular.ttf` из Task 1; существующие `assets/backgrounds/{acq/acq_1,couples/couples_1,sex/tasks,prov/prov}.png` как источник мастей.
- Produces: `assets/backgrounds/library.png` и `assets/backgrounds/card_back.png`, оба 1080×1350 RGB.

- [ ] **Step 1: Дописать падающий тест**

Добавить в `tests/test_card_assets.py`:

```python
BACKGROUNDS = REPO_ROOT / "assets" / "backgrounds"
CARD_SIZE = (1080, 1350)


@pytest.mark.parametrize("name", ["library.png", "card_back.png"])
def test_generated_card_has_the_deck_geometry(name):
    """Every card the renderer composites onto must already be card-shaped;
    _load_background_image would otherwise resample it and soften the art."""
    path = BACKGROUNDS / name
    assert path.exists(), f"missing card {name}"
    with Image.open(path) as img:
        assert img.size == CARD_SIZE


def test_library_card_is_pale_and_back_is_dark():
    """The two cards carry opposite ink: text on the library card is dark on
    pale, the back is a solid dark field. A swapped file would be invisible."""
    with Image.open(BACKGROUNDS / "library.png") as img:
        r, g, b = img.convert("RGB").getpixel((540, 340))
        assert min(r, g, b) > 200
    with Image.open(BACKGROUNDS / "card_back.png") as img:
        r, g, b = img.convert("RGB").getpixel((540, 340))
        assert max(r, g, b) < 120
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_card_assets.py -q`
Expected: FAIL, `missing card library.png`

- [ ] **Step 3: Написать генератор**

`scripts/generate_card_assets.py`:

```python
"""Generate the two cards the deck art doesn't already provide.

`library.png` — the face every Library item and the daily prompt is set on.
`card_back.png` — the shared back the Mini App flips.

The suits are *cropped from the existing deck cards* rather than redrawn:
they are shaded illustrations, not glyphs, and any redraw would drift from
the cards the bot already sends. Run this only when the art changes; the
PNGs are committed.

    python scripts/generate_card_assets.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
BG = ROOT / "assets" / "backgrounds"
FONTS = ROOT / "assets" / "fonts"

CARD = (1080, 1350)
PALE = (253, 232, 247)
DARK = (74, 10, 56)

INK = (74, 10, 56)             # the V/Λ on the pale card
PALE_WATERMARK = (247, 219, 240)   # VECHNOST on the pale card: barely there
PINK = (232, 150, 205)         # the wordmark on the dark back

# Corner geometry, in the 1080×1350 frame. Matches the existing deck cards.
MARGIN_X, MARGIN_Y = 108, 108
LETTER_SIZE = 128
SUIT_BOX = 132

# Where the suit sits on each source card, as a fraction of that card's size.
# The deck art is 600×900; the emblem occupies the box below the V.
_SRC_SUIT = (0.085, 0.135, 0.225, 0.215)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _centre_text(draw, xy, text, font, fill, tracking=0):
    """Draw text centred on xy, optionally letter-spaced."""
    x, y = xy
    if not tracking:
        w = draw.textlength(text, font=font)
        draw.text((x - w / 2, y), text, font=font, fill=fill)
        return
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    cx = x - total / 2
    for ch, w in zip(text, widths):
        draw.text((cx, y), ch, font=font, fill=fill)
        cx += w + tracking


def _suit(source: str, size: int) -> Image.Image:
    """The suit emblem of a deck card, cut out and scaled, alpha preserved."""
    with Image.open(BG / source) as img:
        card = img.convert("RGBA")
    w, h = card.size
    l, t, r, b = _SRC_SUIT
    box = card.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
    box = box.resize((size, size), Image.Resampling.LANCZOS)
    # The source is opaque pale pink; drop that ground so the emblem can sit
    # on the dark back. Anything close to the card's own pink becomes clear.
    out = Image.new("RGBA", box.size, (0, 0, 0, 0))
    for x in range(box.width):
        for y in range(box.height):
            r_, g_, b_, _ = box.getpixel((x, y))
            if r_ > 244 and g_ > 216 and b_ > 240:
                continue
            out.putpixel((x, y), (r_, g_, b_, 255))
    return out


def build_library_card() -> Image.Image:
    """Pale card: V top-left, Λ bottom-right, a whisper of VECHNOST across."""
    card = Image.new("RGB", CARD, PALE)
    draw = ImageDraw.Draw(card)
    forum = _font("Forum-Regular.ttf", LETTER_SIZE)
    lora = _font("Lora-Regular.ttf", 96)

    _centre_text(draw, (CARD[0] / 2, CARD[1] / 2 - 60), "VECHNOST", lora,
                 PALE_WATERMARK, tracking=22)
    _centre_text(draw, (MARGIN_X, MARGIN_Y), "V", forum, INK)
    _centre_text(draw, (CARD[0] - MARGIN_X, CARD[1] - MARGIN_Y - LETTER_SIZE),
                 "Λ", forum, INK)
    return card


def build_card_back() -> Image.Image:
    """Dark back: all four suits in the corners, VECHNOST across the middle."""
    card = Image.new("RGB", CARD, DARK)
    draw = ImageDraw.Draw(card)
    forum = _font("Forum-Regular.ttf", LETTER_SIZE)
    lora = _font("Lora-Regular.ttf", 104)

    heart = _suit("acq/acq_1.png", SUIT_BOX)
    spade = _suit("couples/couples_1.png", SUIT_BOX)
    club = _suit("sex/tasks.png", SUIT_BOX)
    diamond = _suit("prov/prov.png", SUIT_BOX)

    right = CARD[0] - MARGIN_X - SUIT_BOX
    bottom = CARD[1] - MARGIN_Y - SUIT_BOX

    _centre_text(draw, (MARGIN_X + SUIT_BOX / 2, MARGIN_Y - 96), "V", forum, PINK)
    card.paste(heart, (MARGIN_X, MARGIN_Y), heart)
    card.paste(club, (right, MARGIN_Y), club)
    card.paste(diamond, (MARGIN_X, bottom), diamond)
    card.paste(spade, (right, bottom), spade)
    _centre_text(draw, (right + SUIT_BOX / 2, bottom + SUIT_BOX + 8), "Λ",
                 forum, PINK)

    _centre_text(draw, (CARD[0] / 2, CARD[1] / 2 - 66), "VECHNOST", lora,
                 PINK, tracking=26)
    return card


def main() -> None:
    build_library_card().save(BG / "library.png")
    build_card_back().save(BG / "card_back.png")
    print("wrote library.png and card_back.png")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Сгенерировать карты и посмотреть глазами**

Run: `python scripts/generate_card_assets.py`

Открыть обе PNG. Проверить: масти не обрезаны и не съехали, `VECHNOST` по центру и не наезжает на литеры, на тёмной карте масти без розового прямоугольника вокруг. Если кроп промахнулся — править `_SRC_SUIT` и перегенерировать. Это единственный шаг с подгонкой на глаз; не идти дальше, пока карты не выглядят как присланные образцы.

- [ ] **Step 5: Запустить тест — должен пройти**

Run: `pytest tests/test_card_assets.py -q`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add scripts/generate_card_assets.py assets/backgrounds/library.png assets/backgrounds/card_back.png tests/test_card_assets.py
git commit -m "Draw the library face and the shared card back"
```

---

### Task 3: Вопрос дня едет на карте с лого

**Files:**
- Modify: `vechnost_bot/daily_card.py:21-24`
- Modify: `vechnost_bot/renderer.py:33-37`
- Test: `tests/test_daily_card.py`

**Interfaces:**
- Consumes: `assets/backgrounds/library.png` из Task 2.
- Produces: ничего нового; `render_daily_card(day, language)` сохраняет сигнатуру.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_daily_card.py`:

```python
def test_daily_card_uses_the_library_face():
    """The daily prompt is a Library item, so it must ride the Library card,
    not the blank framed default the deck falls back to."""
    from vechnost_bot import daily_card

    assert Path(daily_card._BACKGROUND).name == "library.png"
    assert Path(daily_card._BACKGROUND).exists()
```

Добавить `from pathlib import Path` в импорты файла, если его там нет.

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_daily_card.py::test_daily_card_uses_the_library_face -q`
Expected: FAIL, `assert 'default.png' == 'library.png'`

- [ ] **Step 3: Переключить фон**

`vechnost_bot/daily_card.py`, заменить строки 21-24:

```python
# The daily prompt belongs to no deck, so it rides the Library card: the
# brand face with the V/Λ letters and the VECHNOST wordmark, and no suit.
_BACKGROUND = str(
    Path(__file__).parent.parent / "assets" / "backgrounds" / "library.png"
)
```

- [ ] **Step 4: Поправить комментарий про футер**

`vechnost_bot/renderer.py`, заменить комментарий на строках 33-36 — он ссылается на рамку `default.png`, которой на новой карте нет:

```python
# The Library card (library.png, used by the daily push) carries its Λ letter
# in the bottom-right corner, so the footer and watermark both stay above it.
# The deck backgrounds have their own corner marks at the same height; there
# the clearance simply reads as bottom padding.
```

- [ ] **Step 5: Запустить тесты**

Run: `pytest tests/test_daily_card.py -q`
Expected: PASS

- [ ] **Step 6: Отрендерить карту и посмотреть**

```bash
python -c "from datetime import date; from vechnost_bot.daily_card import render_daily_card; from vechnost_bot.i18n import Language; img,_ = render_daily_card(date(2026,8,16), Language.RUSSIAN); open('/tmp/daily.jpg','wb').write(img.getvalue())"
```

Открыть `/tmp/daily.jpg`. Текст по центру, футер и водяной знак не задевают `Λ`, лого не перебивает вопрос.

- [ ] **Step 7: Коммит**

```bash
git add vechnost_bot/daily_card.py vechnost_bot/renderer.py tests/test_daily_card.py
git commit -m "Send the daily prompt on the Library card"
```

---

### Task 4: Mini App получает доступ к настоящим картам

**Files:**
- Modify: `vechnost_bot/payments/web.py:33`, `:359`
- Create: `tests/test_webapp_static.py`

**Interfaces:**
- Consumes: `assets/backgrounds/*` из Task 2.
- Produces: HTTP-маршрут `GET /assets/backgrounds/<...>.png`, отдающий файлы из `assets/`.

- [ ] **Step 1: Написать падающий тест**

`tests/test_webapp_static.py`:

```python
"""The Mini App draws on the same card PNGs the bot composites.

Serving them rather than re-drawing them in CSS is the whole point: it makes
"the same card" a fact instead of a resemblance. If the mount disappears,
every card in the Mini App silently loses its art and keeps its text.
"""

import pytest
from fastapi.testclient import TestClient

from vechnost_bot.payments.web import create_app

CARDS = [
    "acq/acq_1.png", "acq/acq_2.png", "acq/acq_3.png",
    "couples/couples_1.png", "couples/couples_2.png", "couples/couples_3.png",
    "sex/questions.png", "sex/tasks.png", "prov/prov.png",
    "library.png", "card_back.png",
]


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.mark.parametrize("card", CARDS)
def test_every_card_is_served(client, card):
    res = client.get(f"/assets/backgrounds/{card}")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"


def test_the_mount_does_not_escape_the_assets_directory(client):
    res = client.get("/assets/../vechnost.db")
    assert res.status_code != 200
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_webapp_static.py -q`
Expected: FAIL, все 404

Если `create_app` в `web.py` называется иначе — открыть файл около строки 359 и использовать реальное имя фабрики; тест правится под него, не наоборот.

- [ ] **Step 3: Смонтировать каталог**

`vechnost_bot/payments/web.py`, рядом с `WEBAPP_DIR` (строка 33):

```python
ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
```

и рядом с маунтом `/app` (строка 359):

```python
    # The Mini App renders on the same card art the bot composites onto, so
    # it needs the PNGs themselves. Read-only and public: these are the same
    # images every user already receives as photos.
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
```

- [ ] **Step 4: Запустить тест — должен пройти**

Run: `pytest tests/test_webapp_static.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add vechnost_bot/payments/web.py tests/test_webapp_static.py
git commit -m "Serve the card art to the Mini App"
```

---

### Task 5: Карты игры в Mini App — настоящие

**Files:**
- Modify: `webapp/index.html` — CSS `.card` (строки 241-287), `SUITS` (строка 770), `cardHTML` (строки 1060-1075), `@font-face` и `font-family` (строки 9-18, 38, 66, 112, 269, 274)
- Modify: `tests/test_webapp_static.py`

**Interfaces:**
- Consumes: `/assets/backgrounds/...` из Task 4; `webapp/fonts/*.woff2` из Task 1.
- Produces: в `index.html` — функция `cardArt(theme, level, type)`, возвращающая URL карты; CSS-класс `.card .front` со свойством `--art`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_webapp_static.py`:

```python
from pathlib import Path

INDEX = Path(__file__).parent.parent / "webapp" / "index.html"


def test_the_mini_app_points_at_the_real_card_art():
    html = INDEX.read_text(encoding="utf-8")
    assert "/assets/backgrounds/" in html
    assert "card_back.png" in html


def test_the_mini_app_no_longer_ships_the_old_typography():
    """Montserrat and Georgia are gone; the cards are set in the brand three."""
    html = INDEX.read_text(encoding="utf-8")
    assert "Montserrat" not in html
    assert "Georgia" not in html
    for family in ("Inter", "Lora", "Forum"):
        assert family in html


def test_the_mini_app_suits_match_the_printed_cards():
    """acq ♥, couples ♠, sex ♣, prov ♦ — the art, not the old guess."""
    html = INDEX.read_text(encoding="utf-8")
    line = next(l for l in html.splitlines() if "const SUITS" in l)
    assert "'Acquaintance': '♥'" in line
    assert "'For Couples': '♠'" in line
    assert "'Sex': '♣'" in line
    assert "'Provocation': '♦'" in line
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_webapp_static.py -q`
Expected: FAIL на `/assets/backgrounds/`

- [ ] **Step 3: Заменить шрифты в CSS**

`webapp/index.html`, заменить блок `@font-face` (строки 9-18) на:

```css
  @font-face { font-family: 'Inter'; src: url('fonts/inter-400.woff2') format('woff2');
    font-weight: 400; font-style: normal; font-display: swap; }
  @font-face { font-family: 'Inter'; src: url('fonts/inter-600.woff2') format('woff2');
    font-weight: 600; font-style: normal; font-display: swap; }
  @font-face { font-family: 'Inter'; src: url('fonts/inter-700.woff2') format('woff2');
    font-weight: 700; font-style: normal; font-display: swap; }
  @font-face { font-family: 'Lora'; src: url('fonts/lora-400.woff2') format('woff2');
    font-weight: 400; font-style: normal; font-display: swap; }
  @font-face { font-family: 'Forum'; src: url('fonts/forum-400.woff2') format('woff2');
    font-weight: 400; font-style: normal; font-display: swap; }
```

В `:root` добавить:

```css
    --font-text: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-logo: 'Lora', Georgia, serif;
    --font-emblem: 'Forum', Georgia, serif;
```

Затем заменить каждое использование: `html, body` (строка 38) → `font-family: var(--font-text)`; `.logo` (строка 66) и `.code-display` (строка 112) → `var(--font-logo)`. Строки 269 и 274 (`.card .back .emblem`, `.corner`) удаляются целиком в шаге 5.

Проверка, что ничего не забыто: `grep -n "Montserrat\|Georgia" webapp/index.html` должен показать только `Georgia` внутри `--font-logo`/`--font-emblem` как запасной. Тест из шага 1 требует полного отсутствия слова `Georgia`, поэтому запасные писать как `serif` без `Georgia`:

```css
    --font-logo: 'Lora', serif;
    --font-emblem: 'Forum', serif;
```

- [ ] **Step 4: Переписать CSS карты**

Заменить `.card .front`, `.card .back`, `.card .back .emblem`, `.corner*` (строки 253-277) на:

```css
  /* The face IS the printed card: same PNG the bot composites onto, so the
     Mini App and the photos the bot sends are the same object. Only the text
     and the footer are drawn on top. */
  .card .front {
    background-color: var(--card-bg);
    background-image: var(--art);
    background-size: cover; background-position: center;
    box-shadow: 0 18px 44px rgba(0,0,0,.5);
    padding: 74px 46px 58px;
  }
  .card .back {
    transform: rotateY(180deg);
    background: #4A0A38 url('/assets/backgrounds/card_back.png') center/cover no-repeat;
    box-shadow: 0 18px 44px rgba(0,0,0,.5);
  }
```

- [ ] **Step 5: Исправить масти и добавить выбор карты**

`webapp/index.html`, строка 770 — заменить `SUITS` и добавить рядом:

```javascript
  // The suits of the printed cards. The Mini App used to guess these, and
  // guessed acq and couples backwards; SUITS now only feeds the share text.
  const SUITS = { 'Acquaintance': '♥', 'For Couples': '♠', 'Sex': '♣', 'Provocation': '♦' };

  // Same mapping as assets/backgrounds.yml, which is what the bot reads.
  const CARD_ART = {
    'Acquaintance': { 1: 'acq/acq_1.png', 2: 'acq/acq_2.png', 3: 'acq/acq_3.png' },
    'For Couples':  { 1: 'couples/couples_1.png', 2: 'couples/couples_2.png', 3: 'couples/couples_3.png' },
    'Sex':          { q: 'sex/questions.png', t: 'sex/tasks.png' },
    'Provocation':  { 0: 'prov/prov.png' }
  };
  const LIBRARY_ART = '/assets/backgrounds/library.png';

  function cardArt(theme, level, type) {
    const forTheme = CARD_ART[theme] || {};
    const file = forTheme[level] || forTheme[type] || forTheme[0] || forTheme[1];
    return '/assets/backgrounds/' + (file || 'library.png');
  }
```

- [ ] **Step 6: Переписать cardHTML**

Заменить `cardHTML` (строки 1060-1075):

```javascript
  function cardHTML(text, number, total) {
    const art = cardArt(S.theme, S.level, S.type);
    return (
      '<div class="flipper">' +
        '<div class="face front" style="--art:url(' + art + ')">' +
          '<div class="q-zone"><div class="q-text">' + escapeHTML(text) + '</div></div>' +
          '<div class="card-footer">' + T().cardWord + ' ' + number + ' / ' + total + '</div>' +
        '</div>' +
        '<div class="face back"></div>' +
      '</div>'
    );
  }
```

Ступенчатые классы `.small`/`.tiny` уходят: их заменит прокрутка в Task 7. Соответствующие правила CSS (строки 285-286) удалить.

- [ ] **Step 7: Запустить тест**

Run: `pytest tests/test_webapp_static.py -q`
Expected: PASS

- [ ] **Step 8: Посмотреть в браузере**

```bash
python -m uvicorn vechnost_bot.payments.web:app --reload --port 8000
```

Открыть `http://localhost:8000/app`, пройти в любую колоду. Карта должна выглядеть как присланный образец: `V` и масть сверху-слева, перевёрнутые снизу-справа, текст между ними. Перелистнуть — рубашка тёмная с четырьмя мастями. Проверить все четыре темы и уровни 2 и 3 у Знакомства.

- [ ] **Step 9: Коммит**

```bash
git add webapp/index.html tests/test_webapp_static.py
git commit -m "Give the Mini App the printed cards instead of a CSS likeness"
```

---

### Task 6: Главный экран — веер колод

**Files:**
- Modify: `webapp/index.html` — `.suits` CSS (строки 75-80), разметка `#home` (строка 359)
- Modify: `tests/test_webapp_static.py`

**Interfaces:**
- Consumes: `cardArt` из Task 5.
- Produces: CSS-класс `.deck-fan` и разметка `<div class="deck-fan">` на `#home`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_webapp_static.py`:

```python
def test_the_home_screen_shows_decks_not_typographic_suits():
    """The first thing the Mini App shows should be the game, not ♥♠♦♣."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="suits"' not in html
    assert 'class="deck-fan"' in html
    for card in ("acq/acq_1.png", "couples/couples_1.png",
                 "sex/questions.png", "prov/prov.png"):
        assert card in html
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_webapp_static.py::test_the_home_screen_shows_decks_not_typographic_suits -q`
Expected: FAIL, `assert 'class="suits"' not in html`

- [ ] **Step 3: Заменить CSS**

Убрать `.suits`, `.suits span`, `.suits span:nth-child(...)` (строки 75-79), оставив `@keyframes float`. Добавить:

```css
  /* Four real decks, overlapped like a hand of cards. Each keeps the 2:3 of
     the printed card so nothing is squashed. */
  .deck-fan { display: flex; justify-content: center; margin: 20px 0 4px; height: 108px; }
  .deck-fan i {
    display: block; width: 72px; height: 108px; margin: 0 -14px;
    border-radius: 8px; background-size: cover; background-position: center;
    box-shadow: 0 8px 20px rgba(0,0,0,.45);
    animation: float 3.2s ease-in-out infinite;
  }
  .deck-fan i:nth-child(1) { transform: rotate(-12deg); }
  .deck-fan i:nth-child(2) { transform: rotate(-4deg);  animation-delay: .4s; }
  .deck-fan i:nth-child(3) { transform: rotate(4deg);   animation-delay: .8s; }
  .deck-fan i:nth-child(4) { transform: rotate(12deg);  animation-delay: 1.2s; }
```

`@keyframes float` сдвигает по Y через `transform`, что затрёт поворот. Заменить анимацию на непересекающееся свойство:

```css
  .deck-fan i { animation: fan-float 3.2s ease-in-out infinite; }
  @keyframes fan-float { 0%,100% { translate: 0 0; } 50% { translate: 0 -7px; } }
```

- [ ] **Step 4: Заменить разметку**

`webapp/index.html`, строка 359 — вместо ряда мастей:

```html
    <div class="deck-fan">
      <i style="background-image:url(/assets/backgrounds/acq/acq_1.png)"></i>
      <i style="background-image:url(/assets/backgrounds/couples/couples_1.png)"></i>
      <i style="background-image:url(/assets/backgrounds/sex/questions.png)"></i>
      <i style="background-image:url(/assets/backgrounds/prov/prov.png)"></i>
    </div>
```

- [ ] **Step 5: Запустить тест**

Run: `pytest tests/test_webapp_static.py -q`
Expected: PASS

- [ ] **Step 6: Посмотреть в браузере**

Открыть `http://localhost:8000/app`. Четыре карточки веером, слегка парят, не наезжают на кнопку «Играть». Проверить на узком экране (375px): веер не должен выходить за края.

- [ ] **Step 7: Коммит**

```bash
git add webapp/index.html tests/test_webapp_static.py
git commit -m "Open the Mini App on a fan of the real decks"
```

---

### Task 7: Длинный текст прокручивается внутри карты

**Files:**
- Modify: `webapp/index.html` — `.q-zone`/`.q-text` CSS (строки 279-286), `dragStart`/`dragMove` (строки 1131-1145)
- Modify: `tests/test_webapp_static.py`

**Interfaces:**
- Consumes: `.card .front` из Task 5.
- Produces: `.q-zone` со своей прокруткой; в `drag` появляется поле `axis` (`null` | `'x'` | `'y'`).

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_webapp_static.py`:

```python
def test_long_card_text_scrolls_instead_of_shrinking():
    """A question longer than the card used to shrink to 15.5px and still
    overrun the footer. Now the text area scrolls and the size holds."""
    html = INDEX.read_text(encoding="utf-8")
    assert ".q-text.tiny" not in html
    assert ".q-text.small" not in html
    q_zone = next(l for l in html.splitlines() if l.strip().startswith(".q-zone"))
    assert "overflow-y" in q_zone or "overflow" in q_zone
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_webapp_static.py::test_long_card_text_scrolls_instead_of_shrinking -q`
Expected: FAIL, `.q-text.tiny` ещё в файле (если Task 5 уже удалил классы — тест падает на `overflow`)

- [ ] **Step 3: Переписать CSS текстовой зоны**

Заменить строки 279-286:

```css
  /* The text area scrolls on its own. A long question keeps its readable
     size instead of shrinking to 15.5px and still overrunning the footer;
     the mask fades the cut edge so a clipped line reads as "there's more"
     rather than as a rendering bug. */
  .q-zone {
    flex: 1; display: flex; align-items: center; justify-content: center;
    padding: 8px 2px; overflow-y: auto; overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch; touch-action: pan-y;
    scrollbar-width: none;
    -webkit-mask-image: linear-gradient(180deg, transparent 0, #000 18px,
                        #000 calc(100% - 18px), transparent 100%);
            mask-image: linear-gradient(180deg, transparent 0, #000 18px,
                        #000 calc(100% - 18px), transparent 100%);
  }
  .q-zone::-webkit-scrollbar { display: none; }
  .q-text {
    color: var(--ink); text-align: center; font-weight: 600;
    font-size: 21px; line-height: 1.46; letter-spacing: .002em;
    overflow-wrap: anywhere; margin: auto 0;
  }
```

- [ ] **Step 4: Развести жесты по осям**

Сейчас `dragMove` двигает карту при любом движении, поэтому вертикальный скролл текста утаскивает карту. Заменить `dragStart`/`dragMove` (строки 1131-1145) на:

```javascript
  function dragStart(e) {
    if (S.busy) return;
    const p = e.touches ? e.touches[0] : e;
    drag.x0 = p.clientX; drag.y0 = p.clientY;
    drag.dx = 0; drag.dy = 0; drag.active = true;
    drag.axis = null;               // undecided until the gesture commits
  }

  function dragMove(e) {
    if (!drag.active || !drag.card) return;
    const p = e.touches ? e.touches[0] : e;
    drag.dx = p.clientX - drag.x0;
    drag.dy = p.clientY - drag.y0;

    // Decide once, at 8px of travel, whether this gesture belongs to the
    // card or to the text scrolling inside it. Without this, reading a long
    // question by scrolling drags the card halfway off the stage.
    if (!drag.axis) {
      if (Math.abs(drag.dx) < 8 && Math.abs(drag.dy) < 8) return;
      drag.axis = Math.abs(drag.dx) > Math.abs(drag.dy) ? 'x' : 'y';
    }
    if (drag.axis === 'y') return;

    drag.card.style.transition = 'none';
    drag.card.style.transform =
      'translate(' + drag.dx + 'px,' + drag.dy * .3 + 'px) rotate(' + drag.dx / 26 + 'deg)';
  }
```

Сверить с текущим телом `dragStart`/`dragMove` перед заменой: если в них есть строки, которых здесь нет (например, работа с `S.busy` устроена иначе), сохранить их — меняется только логика осей.

- [ ] **Step 5: Не завершать свайп по вертикальному жесту**

В `dragEnd` (строка 1146) первой строкой после проверки `drag.active`:

```javascript
    if (drag.axis === 'y') { drag.active = false; drag.axis = null; return; }
```

и в конце функции, где сбрасывается `drag.active`, добавить `drag.axis = null;`.

- [ ] **Step 6: Добавить поле в объект drag**

Строка 1121:

```javascript
  const drag = { card: null, x0: 0, y0: 0, dx: 0, dy: 0, active: false, axis: null };
```

- [ ] **Step 7: Запустить тест**

Run: `pytest tests/test_webapp_static.py -q`
Expected: PASS

- [ ] **Step 8: Проверить в браузере**

Открыть колоду «Провокация» — там самые длинные тексты. Убедиться: длинный вопрос прокручивается внутри карты, края мягко затухают, текст не наезжает на футер и на угловые литеры; вертикальный скролл не утаскивает карту; горизонтальный свайп по-прежнему листает. Проверить на мобильной ширине (375×812) — там карта ниже и обрезка вероятнее.

- [ ] **Step 9: Коммит**

```bash
git add webapp/index.html tests/test_webapp_static.py
git commit -m "Scroll long card text instead of shrinking it"
```

---

### Task 8: Библиотека — колода, а не список

**Files:**
- Modify: `webapp/index.html` — экран `#libraryDetail` (строки 396-403), `renderLibModule` (строки 1621-1648), CSS библиотеки (строки 191-206)
- Modify: `tests/test_webapp_static.py`

**Interfaces:**
- Consumes: `cardArt`/`LIBRARY_ART` из Task 5, прокрутка из Task 7, `attachSwipe`/`flyOut` из существующего движка.
- Produces: в `index.html` — `libDeckOpen(items, title)`, где `items` — массив `{text, footer}`; экран `#libDeck` со `#libStage`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_webapp_static.py`:

```python
def test_the_library_has_a_deck_screen():
    """Every Library module is read as cards now, on the Library face."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="libDeck"' in html
    assert 'id="libStage"' in html
    assert "libDeckOpen" in html
    assert "LIBRARY_ART" in html


def test_the_library_no_longer_renders_bare_lists():
    html = INDEX.read_text(encoding="utf-8")
    assert "lib-card-line" not in html
    assert "<ol>" not in html
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_webapp_static.py -q`
Expected: FAIL, `assert 'id="libDeck"' in html`

- [ ] **Step 3: Добавить экран колоды библиотеки**

После `#libraryDetail` (строка 403) вставить:

```html
  <section class="screen" id="libDeck">
    <div class="top">
      <button class="icon-btn" id="libDeckBack">←</button>
      <div class="title" id="libDeckTitle"></div>
      <div style="width:40px"></div>
    </div>
    <div class="progress-wrap">
      <div class="progress-track"><div class="progress-fill" id="libProgressFill"></div></div>
      <div class="progress-num" id="libProgressNum"></div>
    </div>
    <div id="libStage"></div>
    <div class="hint" data-i18n="hint"></div>
    <div class="deck-controls">
      <button class="ctrl" id="libPrev">↩</button>
      <button class="ctrl main" id="libNext">→</button>
    </div>
  </section>
```

- [ ] **Step 4: Дать `#libStage` ту же геометрию, что `#stage`**

В CSS, рядом с правилом `#stage` (строка 239), заменить селектор на общий:

```css
  #stage, #libStage { flex: 1; position: relative; perspective: 1300px; margin: 4px 0 10px; touch-action: none; }
```

Удалить правила `.lib-card`, `.lib-card-title`, `.lib-card-line`, `.lib-cat ol`, `.lib-daily`, `.lib-day`, `.lib-question` (строки 195-205) — их заменяют карты. Оставить `.lib-cat`, `.lib-cat summary`, `.lib-cat-nsfw` (экран категорий остаётся) и `.lib-locked`.

- [ ] **Step 5: Написать движок колоды библиотеки**

Перед `renderLibModule` (строка 1621) добавить:

```javascript
  // The Library deck reuses the game's swipe physics but keeps its own
  // state: the two decks are never on screen at once, and sharing S would
  // mean a Library card could resume into the middle of a game deck.
  const LS = { items: [], idx: 0, title: '', back: null };

  function libCardHTML(item, number, total) {
    return (
      '<div class="flipper">' +
        '<div class="face front" style="--art:url(' + LIBRARY_ART + ')">' +
          '<div class="q-zone"><div class="q-text">' + item.text + '</div></div>' +
          '<div class="card-footer">' + escapeHTML(item.footer || (number + ' / ' + total)) + '</div>' +
        '</div>' +
        '<div class="face back"></div>' +
      '</div>'
    );
  }

  function renderLibStage() {
    const stage = $('libStage');
    stage.innerHTML = '';
    const total = LS.items.length;
    if (!total) return;
    if (LS.idx + 1 < total) {
      const under = document.createElement('div');
      under.className = 'card under';
      under.style.transform = 'translateY(14px) scale(.94)';
      under.style.opacity = '.7';
      under.innerHTML = libCardHTML(LS.items[LS.idx + 1], LS.idx + 2, total);
      stage.appendChild(under);
    }
    const top = document.createElement('div');
    top.className = 'card top';
    top.innerHTML = libCardHTML(LS.items[LS.idx], LS.idx + 1, total);
    stage.appendChild(top);
    attachSwipe(top);
    drag.onAdvance = libNext;
    drag.onBack = libPrev;
    $('libProgressFill').style.width = ((LS.idx + 1) / total) * 100 + '%';
    $('libProgressNum').textContent = (LS.idx + 1) + ' / ' + total;
    $('libPrev').disabled = LS.idx <= 0;
    $('libNext').disabled = LS.idx >= total - 1;
  }

  function libNext() { if (LS.idx < LS.items.length - 1) { LS.idx++; renderLibStage(); haptic('light'); } }
  function libPrev() { if (LS.idx > 0) { LS.idx--; renderLibStage(); haptic('light'); } }

  function libDeckOpen(items, title, back) {
    LS.items = items; LS.idx = 0; LS.title = title; LS.back = back;
    $('libDeckTitle').textContent = title;
    show('libDeck');
    renderLibStage();
  }

  $('libPrev').onclick = libPrev;
  $('libNext').onclick = libNext;
  $('libDeckBack').onclick = () => { drag.onAdvance = null; drag.onBack = null; (LS.back || openLibrary)(); };
```

`item.text` уже экранирован вызывающей стороной (шаг 6), поэтому `libCardHTML` его не экранирует повторно — иначе `&nbsp;` и переносы в практиках превратятся в текст.

- [ ] **Step 6: Собирать карты из ответа API**

Заменить `renderLibModule` (строки 1621-1648) на функцию, которая вместо HTML-списка открывает колоду. Тело `openLibModule` (строка 1603) меняется соответственно:

```javascript
  // The card text for each module type. Everything is escaped here, once.
  function libItems(data) {
    if (data.type === 'daily') {
      return [{ text: escapeHTML(data.question),
                footer: fmt(T().libDayOf, { day: data.day }) }];
    }
    if (data.type === 'practice') {
      return data.items.map((p, i) => ({
        text: '<b>' + escapeHTML(p.title) + '</b><br><br>' +
              '<span class="q-sub"><b>' + T().libWhy + ':</b> ' + escapeHTML(p.why) + '</span><br>' +
              '<span class="q-sub"><b>' + T().libResult + ':</b> ' + escapeHTML(p.result) + '</span>',
        footer: (i + 1) + ' / ' + data.items.length
      }));
    }
    return null;   // a `list` module goes through its categories first
  }
```

и в `openLibModule`, вместо присваивания `innerHTML`:

```javascript
      const items = libItems(data);
      if (items) {
        libDeckOpen(items, data.emoji + ' ' + data.title, openLibrary);
        return;
      }
      $('libDetailTitle').textContent = data.emoji + ' ' + data.title;
      $('libDetailBody').innerHTML = renderLibCategories(data, openCategory);
```

`renderLibCategories` — это остаток старого `renderLibModule`: только экран выбора категорий, где `<details>` заменяется на кнопку, открывающую колоду:

```javascript
  function renderLibCategories(data, openCategory) {
    const visible = data.categories.map(c => `
      <button class="lib-cat lib-cat-open" data-cat="${escapeHTML(c.id)}">
        ${escapeHTML(c.title)} · ${c.items.length}${c.items.length < c.total ? '/' + c.total : ''}
      </button>`).join('');
    const withheld = (data.nsfw_withheld || []).map(c => `
      <button class="lib-cat lib-cat-nsfw" data-nsfw-cat="${escapeHTML(c.id)}">
        🔞 ${escapeHTML(c.title)} · ${c.total}
      </button>`).join('');
    return visible + withheld + libLockedFooter(data);
  }
```

и в `openLibModule`, рядом с существующим обработчиком `[data-nsfw-cat]`:

```javascript
      $('libDetailBody').querySelectorAll('[data-cat]').forEach(row => {
        row.onclick = () => {
          haptic('light');
          const cat = data.categories.find(c => c.id === row.dataset.cat);
          if (!cat || !cat.items.length) return;
          libDeckOpen(
            cat.items.map((t, i) => ({ text: escapeHTML(t),
                                       footer: (i + 1) + ' / ' + cat.items.length })),
            cat.title,
            () => openLibModule(id, cat.id)
          );
        };
      });
```

`openCategory` больше не раскрывает `<details>` — оно теперь просто помечает, куда вернуться; параметр остаётся ради вызова из 18+-потока, где после подтверждения нужно открыть ту же категорию. После шага проверить, что `LIB_NSFW_PENDING` по-прежнему приводит в нужную категорию.

Добавить CSS для кнопок категорий и мелкого текста практик:

```css
  .lib-cat-open { display:block; width:100%; text-align:left; font:inherit;
    font-weight:700; color:inherit; border:1px solid rgba(255,255,255,.12); cursor:pointer; }
  .q-sub { font-size: .82em; font-weight: 500; opacity: .85; }
```

- [ ] **Step 7: Пробросить колбэки в свайп**

`dragEnd` сейчас жёстко зовёт игровые `next`/`prev` через `flyOut`. Найти в `flyOut` (строка 1164) вызовы перехода и заменить на:

```javascript
      if (drag.onAdvance) { drag.onAdvance(); return; }
```

перед существующей игровой веткой, чтобы игра работала как раньше (когда `drag.onAdvance === null`), а библиотека перехватывала. В `enterDeck` и `enterCoopDeck` первой строкой сбросить: `drag.onAdvance = null; drag.onBack = null;` — иначе выход из библиотеки в игру оставит чужие колбэки.

- [ ] **Step 8: Запустить тест**

Run: `pytest tests/test_webapp_static.py -q`
Expected: PASS

- [ ] **Step 9: Проверить в браузере**

С `ENABLE_PAYMENT=false` пройти все пять модулей: «Идеи для свиданий» (категории → колода), «36 вопросов» (категория одна → колода), обе «Практики» (карта с названием, «Зачем», «Итог»), «Вопрос дня» (одна карта с номером дня). Проверить кнопку «назад» из колоды и возврат в категорию после 18+.

Затем с `ENABLE_PAYMENT=true` и неоплаченным пользователем убедиться, что в колоде ровно `FREE_LIBRARY_ITEMS_PER_LIST` карт и внизу экрана категорий видна кнопка покупки.

- [ ] **Step 10: Коммит**

```bash
git add webapp/index.html tests/test_webapp_static.py
git commit -m "Read the Library as a deck of cards"
```

---

### Task 9: Один язык — данные и i18n

**Files:**
- Modify: `vechnost_bot/i18n.py:15-19`
- Delete: `data/questions_en.yaml`, `data/questions_cs.yaml`, `data/translations_en.yaml`, `data/translations_cs.yaml`
- Modify: `tests/test_translations.py:21`, `tests/test_daily_card.py:47`, `tests/test_library.py:52`

**Interfaces:**
- Consumes: ничего.
- Produces: `Language` с единственным членом `RUSSIAN`; `Language.coerce(code: str | None) -> Language`, возвращающий `RUSSIAN` для чего угодно нераспознанного.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_single_language.py`:

```python
"""Russian is the only language the product ships.

English and Czech are not deleted from history — they are one revert away —
but nothing in the running system may branch on language again without a
deliberate change here.
"""

from pathlib import Path

import pytest

from vechnost_bot.i18n import Language

DATA = Path(__file__).parent.parent / "data"


def test_only_russian_is_supported():
    assert [l.value for l in Language] == ["ru"]


@pytest.mark.parametrize("code", ["en", "cs", "de", "", None, "RU", "ru-RU"])
def test_any_stored_code_reads_as_russian(code):
    """Users carry `en` and `cs` in the database from before this change;
    reading one must not raise, it must quietly become Russian."""
    assert Language.coerce(code) is Language.RUSSIAN


@pytest.mark.parametrize("name", [
    "questions_en.yaml", "questions_cs.yaml",
    "translations_en.yaml", "translations_cs.yaml",
])
def test_retired_language_files_are_gone(name):
    assert not (DATA / name).exists()
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_single_language.py -q`
Expected: FAIL, `assert ['ru','en','cs'] == ['ru']`

- [ ] **Step 3: Схлопнуть Language**

`vechnost_bot/i18n.py`, заменить строки 15-19:

```python
class Language(str, Enum):
    """The languages the product ships. English and Czech are retired: the
    content behind them is in git history, one revert away, but nothing at
    runtime branches on language any more."""
    RUSSIAN = "ru"

    @classmethod
    def coerce(cls, code: str | None) -> "Language":
        """A stored or client-supplied code, read as a supported language.

        Users predating this change carry `en`/`cs` in the database and in
        Mini App query strings; `Language(code)` would raise on those, and
        it is called on paths that render outside a try block.
        """
        try:
            return cls(str(code).lower())
        except (ValueError, AttributeError):
            return cls.RUSSIAN
```

- [ ] **Step 4: Удалить файлы переводов**

```bash
git rm data/questions_en.yaml data/questions_cs.yaml data/translations_en.yaml data/translations_cs.yaml
```

- [ ] **Step 5: Заменить парсинг кода языка на coerce**

Найти все места, где код языка приходит извне:

```bash
grep -rn "Language(" vechnost_bot --include=*.py | grep -v "def \|: Language\|-> Language\|Language\."
```

В каждом заменить `Language(x)` на `Language.coerce(x)` и убрать ставший ненужным `try/except ValueError`. Как минимум это: `daily_card.py::_user_language`, `library_api.py::_language`, `callback_handlers.py:1106`, `payments/rooms.py`, `payments/compat_api.py`, `payments/web.py`.

- [ ] **Step 6: Сузить тесты до русского**

- `tests/test_translations.py:21` → `LANGUAGES = [Language.RUSSIAN]`
- `tests/test_daily_card.py:47` — параметризация `test_renders_in_every_language` сводится к одному значению; переименовать в `test_renders_in_russian` и убрать `parametrize`.
- `tests/test_library.py:52` — `test_non_russian_falls_back_to_russian` больше не имеет предмета; заменить на проверку `Language.coerce("en") is Language.RUSSIAN`, чтобы поведение отката осталось зафиксированным.

Затем прогнать поиск по остальным тестам: `grep -rn "ENGLISH\|CZECH" tests` — каждое вхождение либо убрать, либо заменить на `RUSSIAN`.

- [ ] **Step 7: Запустить весь набор**

Run: `pytest -q`
Expected: PASS (кроме тестов с маркером `redis`, если Redis не поднят)

- [ ] **Step 8: Коммит**

```bash
git add -A vechnost_bot data tests
git commit -m "Ship Russian only, keeping the other two a revert away"
```

---

### Task 10: Один язык — интерфейс бота

**Files:**
- Delete: `vechnost_bot/language_keyboards.py`
- Modify: `vechnost_bot/handlers.py:14`, `:93`
- Modify: `vechnost_bot/callback_handlers.py:34`, `:1226`, класс `LanguageHandler` (строка 1100)
- Modify: `vechnost_bot/keyboards.py:5-6`
- Modify: `tests/test_handlers_comprehensive.py`, `tests/test_integration_comprehensive.py`, `tests/test_integration_flows.py`

**Interfaces:**
- Consumes: `Language.coerce` из Task 9.
- Produces: `callback_handlers.welcome_screen(language) -> tuple[str, InlineKeyboardMarkup]` — текст и клавиатура приветственного экрана, общие для `/start` и для кнопок «назад».

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_single_language.py`:

```python
def test_the_bot_no_longer_offers_a_language_choice():
    """`/start` opens on the welcome screen; there is nothing to choose."""
    from pathlib import Path

    src = Path(__file__).parent.parent / "vechnost_bot"
    assert not (src / "language_keyboards.py").exists()
    for name in ("handlers.py", "callback_handlers.py", "keyboards.py"):
        text = (src / name).read_text(encoding="utf-8")
        assert "language_keyboards" not in text, f"{name} still imports it"
        assert "get_language_selection_keyboard" not in text
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_single_language.py::test_the_bot_no_longer_offers_a_language_choice -q`
Expected: FAIL, файл ещё существует

- [ ] **Step 3: Вынести приветственный экран в общую функцию**

В `callback_handlers.py` тело `LanguageHandler.handle` (строки 1114-1160) собирает текст и клавиатуру. Вынести это в модульную функцию над классом:

```python
def welcome_screen(language: Language) -> tuple[str, InlineKeyboardMarkup]:
    """The greeting page: what `/start` opens on and what every 'back'
    button returns to. One builder, so the two can never drift apart."""
    text = (
        f"<b>{get_text('welcome.greeting_title', language)}</b>\n"
        f"<i>{get_text('welcome.greeting_subtitle', language)}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{get_text('welcome.section_connection_title', language)}</b>\n"
        f"{get_text('welcome.section_connection_text', language)}\n\n"
        f"<b>{get_text('welcome.section_intimacy_title', language)}</b>\n"
        f"{get_text('welcome.section_intimacy_text', language)}\n\n"
        f"<b>{get_text('welcome.section_themes_title', language)}</b>\n"
        f"{get_text('welcome.section_themes_text', language)}\n\n"
        f"<b>{get_text('welcome.section_best_title', language)}</b>\n"
        f"{get_text('welcome.section_best_text', language)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    from telegram import WebAppInfo

    from .config import settings

    rows = [[InlineKeyboardButton(
        get_text('welcome.button_start', language), callback_data="start_game"
    )]]
    if settings.webapp_url:
        rows.append([InlineKeyboardButton(
            get_text('welcome.button_webapp', language),
            web_app=WebAppInfo(url=settings.webapp_url)
        )])
        rows.append([InlineKeyboardButton(
            get_text('welcome.button_library', language),
            web_app=WebAppInfo(url=settings.webapp_library_url)
        )])
    rows.extend([
        [InlineKeyboardButton(get_text('welcome.button_inside', language),
                              callback_data="show_inside")],
        [InlineKeyboardButton(get_text('welcome.button_why', language),
                              callback_data="show_why")],
    ])
    return text, InlineKeyboardMarkup(rows)
```

и переписать `LanguageHandler.handle` так, чтобы он использовал её. Класс и его регистрация на префикс `lang_` **остаются**: кнопки «назад» в `ShowInsideHandler`, `ShowWhyHandler` и `ShowGiftHandler` шлют `lang_ru`, и уже отправленные пользователям сообщения тоже. `Language(callback_data.language_code)` в нём заменяется на `Language.coerce(...)`, а ветка `except ValueError` удаляется.

- [ ] **Step 4: `/start` открывается сразу на приветствии**

`vechnost_bot/handlers.py`: убрать импорт на строке 14, а на строке 93 вместо клавиатуры выбора языка использовать общий экран. Открыть `start_command` целиком и заменить хвост, где собирается сообщение, на:

```python
    from .callback_handlers import welcome_screen

    text, keyboard = welcome_screen(Language.RUSSIAN)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
```

Переменная `detected_language` и определение языка по `update.effective_user.language_code` становятся мёртвыми — удалить их вместе с сопутствующими импортами.

- [ ] **Step 5: Почистить keyboards.py и LanguageBackHandler**

`vechnost_bot/keyboards.py`, строки 5-6: убрать `get_language_name`, `get_supported_languages` и импорт `language_keyboards`, если ничего в файле их больше не использует (`grep -n "get_language_name\|get_supported_languages\|get_language_selection_keyboard" vechnost_bot/keyboards.py`).

`callback_handlers.py:1226` — `LanguageBackHandler` строит клавиатуру выбора языка. Он же спрашивает три ключа (`welcome.title`/`subtitle`/`prompt`), которых нет ни в одном файле переводов — это зафиксировано как известная поломка в `tests/test_translations.py`. Заменить его тело на возврат приветственного экрана:

```python
        text, keyboard = welcome_screen(session.language)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
```

и убрать карантин `_KNOWN_PRE_EXISTING_MISSING_KEYS` вместе с тестом `test_the_known_language_back_bug_is_still_broken` из `tests/test_translations.py` — баг исчезает вместе с обработчиком, и его страховка должна исчезнуть в том же изменении.

- [ ] **Step 6: Удалить модуль**

```bash
git rm vechnost_bot/language_keyboards.py
```

- [ ] **Step 7: Поправить тесты, которые патчили клавиатуру**

В `tests/test_handlers_comprehensive.py:46`, `tests/test_integration_comprehensive.py:31` и пяти местах `tests/test_integration_flows.py` патч `vechnost_bot.handlers.get_language_selection_keyboard` больше не резолвится. Заменить на патч `vechnost_bot.handlers.welcome_screen`, возвращающий `("текст", MagicMock())`.

- [ ] **Step 8: Запустить весь набор**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 9: Коммит**

```bash
git add -A vechnost_bot tests
git commit -m "Open the bot on the welcome screen, not a language choice"
```

---

### Task 11: Один язык — интерфейс Mini App

**Files:**
- Modify: `webapp/index.html` — `.lang-row` CSS (строка 124), разметка (строки 364-368), объект `I18N` (строки 571-~760), логика выбора языка
- Modify: `tests/test_webapp_static.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `I18N` как плоский объект (без ключа `ru`), `T()` возвращает его напрямую.

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_webapp_static.py`:

```python
def test_the_mini_app_ships_one_language():
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="lang-row"' not in html
    assert 'data-lang="en"' not in html
    assert 'data-lang="cs"' not in html
    assert "Pick a theme" not in html      # the English dictionary is gone
    assert "Vyber téma" not in html        # and the Czech one
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `pytest tests/test_webapp_static.py::test_the_mini_app_ships_one_language -q`
Expected: FAIL

- [ ] **Step 3: Схлопнуть словарь**

В `webapp/index.html` удалить блоки `en: {...}` и `cs: {...}` целиком, а `ru: {...}` развернуть в сам `I18N`:

```javascript
  // Russian is the only language the Mini App ships. The other two are in
  // git history alongside the bot's YAML, one revert away.
  const I18N = {
    tagline: 'Карточная игра для пар и разговоров, которые сближают',
    /* …остальные ключи из бывшего блока ru… */
  };
```

и `T()` (строка 788):

```javascript
  const T = () => I18N;
```

- [ ] **Step 4: Убрать переключатель**

Удалить `.lang-row` и `.chip` из CSS только в той части, что относится к выбору языка: `.lang-row` (строка 124) уходит, `.chip` **остаётся** — он используется в `#turnChip` и в `.mode-row`. Удалить разметку `<div class="lang-row" id="langRow">…</div>` (строки 364-368).

Найти и убрать логику: `grep -n "langRow\|data-lang\|lang =\|store.get('lang'" webapp/index.html`. Переменная `lang` остаётся, но становится константой `'ru'` — она подставляется в query-строку `/api/*`, и сервер по-прежнему её принимает.

- [ ] **Step 5: Запустить тест**

Run: `pytest tests/test_webapp_static.py -q`
Expected: PASS

- [ ] **Step 6: Проверить в браузере**

Открыть `http://localhost:8000/app`. Главный экран без ряда RU/EN/CS, все подписи на русском, колода и библиотека открываются. В консоли браузера не должно быть `ReferenceError`.

- [ ] **Step 7: Коммит**

```bash
git add webapp/index.html tests/test_webapp_static.py
git commit -m "Drop the language switch from the Mini App"
```

---

### Task 12: Убрать длинное тире из контента

**Files:**
- Modify: `data/questions.yaml` (44 вхождения)
- Modify: `data/library/dates_ru.yaml` (5), `practices_couples_ru.yaml` (7), `practices_self_ru.yaml` (2), `reflection_ru.yaml` (2), `compat_ru.yaml` (18)
- Create: `tests/test_no_em_dash.py`

**Interfaces:**
- Consumes: ничего.
- Produces: ничего; изменение только в данных.

- [ ] **Step 1: Написать падающий тест**

`tests/test_no_em_dash.py`:

```python
"""No em dashes in the content.

The card sets text at a large size on a narrow measure, where an em dash
opens a hole in the line. Where the punctuation is genuinely needed the
content uses an en dash instead; where it was standing in for a comma or a
colon, the sentence was rewritten.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CONTENT = sorted(
    [ROOT / "data" / "questions.yaml"] + list((ROOT / "data" / "library").glob("*.yaml"))
)


@pytest.mark.parametrize("path", CONTENT, ids=lambda p: p.name)
def test_content_has_no_em_dash(path):
    text = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        if "—" in line
    ]
    assert not offenders, "em dash left in:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Запустить и увидеть полный список**

Run: `pytest tests/test_no_em_dash.py -q`
Expected: FAIL, ~78 строк в отчёте

- [ ] **Step 3: Пройти вхождения вручную**

Взять список из вывода теста и править по правилу:

- Тире заменяло запятую или двоеточие → поставить запятую/двоеточие. «Секс — это про доверие» → «Секс это про доверие» неверно; правильно «Секс, это про доверие» тоже неверно. В таких конструкциях (пропуск связки «есть») тире пунктуационно необходимо → короткое: «Секс – это про доверие».
- Тире как вставная конструкция с обеих сторон («…, — сказал он, — …») → запятые.
- Тире в начале строки как маркер списка → убрать вместе с пробелом.
- Тире между числами («3—5 минут») → короткое «3–5».

Не запускать массовый `sed`: правило зависит от конструкции. Править по одному файлу за раз, перечитывая строку целиком.

- [ ] **Step 4: Запустить тест — должен пройти**

Run: `pytest tests/test_no_em_dash.py -q`
Expected: PASS

- [ ] **Step 5: Проверить, что колоды не разъехались**

Run: `pytest -q`
Expected: PASS. Особое внимание `tests/test_library.py` — там зафиксированы размеры блоков `reflection_ru.yaml` (31/30×10/34) и число категорий в `dates_ru.yaml`; правка текста их менять не должна.

- [ ] **Step 6: Прочитать глазами то, что изменилось**

```bash
git diff --word-diff data/
```

Убедиться, что ни одно предложение не потеряло смысл и нигде не осталось двойных пробелов.

- [ ] **Step 7: Коммит**

```bash
git add data tests/test_no_em_dash.py
git commit -m "Retire the em dash from the card content"
```

---

### Task 13: Сборка и финальная проверка

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: всё предыдущее.
- Produces: ничего.

- [ ] **Step 1: Прогнать весь набор**

Run: `pytest -q`
Expected: PASS; падения только с маркером `redis` и только при отсутствии `localhost:6379`.

- [ ] **Step 2: Обновить CLAUDE.md**

Правки, каждая — одно предложение на место старого утверждения:

- Раздел «Content»: убрать «one file per language», сказать что продукт русскоязычный, а `_en`/`_cs` сняты и лежат в истории.
- Раздел «Card rendering»: Montserrat больше не брендовый шрифт — Inter для текста, Lora для словесного знака, Forum для литер; все три с кириллицей.
- Новый пункт в «Architecture notes»: Mini App рисует на тех же PNG, что и бот, через маунт `/assets`; две карты (`library.png`, `card_back.png`) генерируются `scripts/generate_card_assets.py` и коммитятся.
- Раздел «Gotchas»: правило «все три языковые колоды одной длины» из `rooms.py` больше не актуально — колода одна.
- Раздел «Conventions»: «New user-facing text goes in all three languages» → только русский.

- [ ] **Step 3: Обновить README.md**

Найти упоминания трёх языков и выбора языка (`grep -n "язык\|language\|English\|Czech" README.md`) и привести к текущему положению дел.

- [ ] **Step 4: Пройти сквозной сценарий руками**

Поднять сервер, открыть Mini App, пройти: главный экран → игра (все четыре темы, длинный вопрос в «Провокации») → библиотека (все пять модулей) → назад. Отдельно отрендерить карту вопроса дня и посмотреть на неё.

- [ ] **Step 5: Коммит и PR**

```bash
git add CLAUDE.md README.md
git commit -m "Bring the docs in line with one language and one card"
git push -u origin feature/card-identity
gh pr create --fill
```

---

## Самопроверка плана

**Покрытие спеки:**

| Раздел спеки | Задача |
|---|---|
| 1. Шрифты | Task 1 (bot), Task 5 шаг 3 (Mini App) |
| 2. Две новые карты | Task 2 |
| 3. Бот | Task 3 |
| 4. Mini App: карточки игры | Task 4 (маунт), Task 5 |
| 5. Mini App: главный экран | Task 6 |
| 6. Mini App: библиотека как колода | Task 8 |
| 7. Прокрутка длинного текста | Task 7 |
| 8. Только русский | Task 9 (данные), Task 10 (бот), Task 11 (Mini App) |
| 9. Тире | Task 12 |
| Проверка | Task 13 |

**Согласованность имён:** `cardArt`/`CARD_ART`/`LIBRARY_ART` заводятся в Task 5 и используются в Task 6 и Task 8. `drag.axis` заводится в Task 7, `drag.onAdvance`/`drag.onBack` — в Task 8. `Language.coerce` заводится в Task 9 и используется в Task 10. `welcome_screen` заводится в Task 10 шаг 3 и используется в шагах 4, 5, 7.

**Известные зависимости порядка:** Task 5 должна идти после Task 4 (иначе `/assets` отдаёт 404 и карты в браузере пустые). Task 8 после Task 5 и 7. Task 11 после Task 8 (в библиотечной колоде используются ключи `I18N`). Остальные независимы.

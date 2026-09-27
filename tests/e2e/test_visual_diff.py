"""The comparison behind the visual-change check (tests/e2e/browser/visual.py).

It must stay quiet about what a person cannot see - a pixel or two of
anti-aliasing - and speak up about what they can: a line of text one pixel
larger, a screen of another size, a screen that is new or gone.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vechnost_bot.renderer import FONT_PATH

from .browser import visual

SIZE = (320, 568)


def screen(path: Path, text: str = "Играть вдвоём", size: int = 15, *, dims=SIZE) -> Path:
    image = Image.new("RGB", dims, (28, 4, 20))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 200, 280, 250), radius=14, fill=(196, 37, 110))
    draw.text((70, 214), text, font=ImageFont.truetype(str(FONT_PATH), size), fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def test_the_same_picture_is_the_same(tmp_path: Path) -> None:
    a = screen(tmp_path / "a.png")
    b = screen(tmp_path / "b.png")
    assert visual.compare(a, b, tmp_path / "d.png") == ("same", 0)
    assert not (tmp_path / "d.png").exists()


def test_a_few_stray_pixels_are_not_a_change(tmp_path: Path) -> None:
    a = screen(tmp_path / "a.png")
    image = Image.open(a)
    for x in (10, 100, 200):
        image.putpixel((x, 400), (40, 12, 30))  # a faint speck, as anti-aliasing leaves
    image.save(tmp_path / "b.png")
    status, moved = visual.compare(a, tmp_path / "b.png", tmp_path / "d.png")
    assert status == "same", moved


def test_a_full_stop_is_a_change(tmp_path: Path) -> None:
    a = screen(tmp_path / "a.png", "Открыть всё")
    b = screen(tmp_path / "b.png", "Открыть всё.")
    assert visual.compare(a, b, tmp_path / "d.png")[0] == "changed"


def test_text_one_pixel_larger_is_a_change(tmp_path: Path) -> None:
    a = screen(tmp_path / "a.png", size=15)
    b = screen(tmp_path / "b.png", size=16)
    status, moved = visual.compare(a, b, tmp_path / "d.png")
    assert status == "changed" and moved > visual.TOLERANCE
    assert (tmp_path / "d.png").exists(), "the difference is drawn for the report"


def test_another_size_is_a_change(tmp_path: Path) -> None:
    a = screen(tmp_path / "a.png")
    b = screen(tmp_path / "b.png", dims=(320, 600))
    assert visual.compare(a, b, tmp_path / "d.png")[0] == "changed"


def test_tours_are_compared_screen_by_screen_and_the_report_stands_alone(tmp_path: Path) -> None:
    base, head, out = tmp_path / "base", tmp_path / "head", tmp_path / "out"
    screen(base / "android" / "home@320x568.png")
    screen(head / "android" / "home@320x568.png")
    screen(base / "android" / "paywall@320x568.png", "Открыть всё")
    screen(head / "android" / "paywall@320x568.png", "Открыть всё!")
    screen(base / "android" / "gone@320x568.png")
    screen(head / "android" / "new@320x568.png")

    verdicts = {v.name: v.status for v in visual.compare_tours(base, head, out)}
    assert verdicts == {
        "android/home@320x568.png": "same",
        "android/paywall@320x568.png": "changed",
        "android/gone@320x568.png": "gone",
        "android/new@320x568.png": "new",
    }

    assert visual.main([str(base), str(head), str(out)]) == 1
    assert visual.main([str(base), str(head), str(out), "--accept"]) == 0
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "base/android/paywall@320x568.png" in page
    assert (out / "base" / "android" / "paywall@320x568.png").exists()
    assert (out / "head" / "android" / "paywall@320x568.png").exists()
    assert "home@320x568" not in page, "an unchanged screen is not in the report"
    assert "3 of 4 screens changed" in (out / "summary.md").read_text(encoding="utf-8")


def test_two_identical_tours_pass(tmp_path: Path) -> None:
    base, head, out = tmp_path / "base", tmp_path / "head", tmp_path / "out"
    for root in (base, head):
        screen(root / "iphone" / "home@393x852.png", dims=(393, 852))
    assert visual.main([str(base), str(head), str(out)]) == 0


def test_no_pictures_at_all_is_a_failure(tmp_path: Path) -> None:
    assert visual.main([str(tmp_path / "a"), str(tmp_path / "b"), str(tmp_path / "out")]) == 1

"""From the camera's picture to the one in the app: a vignette, the shadows
lifted toward the app's aubergine, a warm touch in the highlights, film
grain - and, for the editing card, its black-and-white half."""

from __future__ import annotations

import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722])

LOOK = {
    "vignette": 0.45,
    "lift": (0.06, 0.012, 0.045),
    "highlight_tint": (1.03, 1.0, 0.95),
    "grain": 0.03,
}


def box_blur(img, r, axis):
    pad = [(0, 0)] * img.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(img, pad, mode="edge"), axis=axis)
    n = img.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def gauss(img, sigma):
    """Three box blurs: close enough to a Gaussian, and fast."""
    if sigma <= 0.3:
        return img
    r = max(1, int(round((np.sqrt(4 * sigma * sigma + 1) - 1) / 2)))
    for _ in range(3):
        img = box_blur(box_blur(img, r, 0), r, 1)
    return img


def vignette(img, amount):
    h, w, _ = img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx + 0.5) / w - 0.5) ** 2 * 2.0 + ((yy + 0.5) / h - 0.5) ** 2 * 2.0)
    return img * (1 - amount * np.clip(r, 0, 1) ** 2.2)[..., None]


def grade(out, look, seed=7):
    """Split toning toward the app's aubergine, then film grain."""
    h, w, _ = out.shape
    lift = np.asarray(look.get("lift", (0.09, 0.02, 0.07)))
    out = lift + out * (1 - lift)
    tint = np.asarray(look.get("highlight_tint", (1.0, 1.0, 1.0)))
    out = out * (1 + (tint - 1) * (out @ LUMA)[..., None])
    g = look.get("grain", 0.0)
    if g > 0:
        noise = (
            gauss(np.random.default_rng(seed).normal(0, 1, (h, w))[..., None], 0.55)[..., 0] * 1.6
        )
        lum = out @ LUMA
        amp = g * (0.35 + 0.65 * np.clip(1 - np.abs(lum - 0.4) * 1.4, 0, 1))
        out = out + (noise * amp)[..., None]
    return out


def develop(img, seed, look=LOOK):
    return grade(vignette(img, look["vignette"]), look, seed)


def monochrome(img, seed, look=LOOK):
    """The editing card's right half, as the card tells you to make it:
    black and white, the shadows pulled down, a heavier grain, a vignette."""
    lum = np.clip((img @ LUMA - 0.05) / 0.95, 0, 1) ** 1.12
    mono = vignette(np.repeat(lum[..., None], 3, axis=2), 0.35 + look["vignette"])
    neutral = {
        **look,
        "lift": (0.045, 0.045, 0.045),
        "highlight_tint": (1.0, 1.0, 1.0),
        "grain": look["grain"] * 1.8,
    }
    return grade(mono, neutral, seed + 4)


def to_bytes(out):
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)

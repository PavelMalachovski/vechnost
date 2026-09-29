"""From linear radiance to an 8-bit picture that reads as a photograph."""

from __future__ import annotations

import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722])


def box_blur(img, r, axis):
    pad = [(0, 0)] * img.ndim
    pad[axis] = (r + 1, r)
    a = np.pad(img, pad, mode="edge")
    c = np.cumsum(a, axis=axis)
    n = img.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def gauss(img, sigma):
    if sigma <= 0.3:
        return img
    w = np.sqrt(12 * sigma * sigma / 3 + 1)
    r = max(1, int(round((w - 1) / 2)))
    out = img
    for _ in range(3):
        out = box_blur(out, r, 0)
        out = box_blur(out, r, 1)
    return out


def aces(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)


def downsample(img, f):
    if f == 1:
        return img
    h, w, c = img.shape
    return img.reshape(h // f, f, w // f, f, c).mean(axis=(1, 3))


def develop(hdr, depth, look):
    """Lens and exposure: depth of field, bloom and vignette, in linear light,
    then a filmic curve. Returns display values in 0-1."""
    h, w, _ = hdr.shape
    img = hdr * look.get("exposure", 1.0)
    if look.get("dof"):
        # Everything away from the focus plane goes soft, near or far.
        focus, span, sigma = look["dof"]
        blurred = gauss(img, sigma * w)
        k = np.clip(np.abs(depth - focus) / span, 0, 1)[..., None]
        img = img * (1 - k) + blurred * k
    thr = look.get("bloom_threshold", 0.9)
    bright = np.clip(img - thr, 0, None)
    img = img + gauss(bright, look.get("bloom_sigma", 0.035) * w) * look.get("bloom", 0.25)
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx + 0.5) / w - 0.5) ** 2 * 2.0 + ((yy + 0.5) / h - 0.5) ** 2 * 2.0)
    img = img * (1 - look.get("vignette", 0.35) * np.clip(r, 0, 1) ** 2.2)[..., None]
    return aces(img) ** (1 / 2.2)


def grade(out, look, seed=7):
    """Split toning toward the app's aubergine, then film grain."""
    h, w, _ = out.shape
    lift = np.asarray(look.get("lift", (0.09, 0.02, 0.07)))
    out = lift + out * (1 - lift)
    tint = np.asarray(look.get("highlight_tint", (1.0, 1.0, 1.0)))
    lum = out @ LUMA
    out = out * (1 + (tint - 1) * lum[..., None])
    g = look.get("grain", 0.0)
    if g > 0:
        rng = np.random.default_rng(seed)
        noise = rng.normal(0, 1, (h, w))
        noise = gauss(noise[..., None], 0.55)[..., 0] * 1.6
        lum = out @ LUMA
        amp = g * (0.35 + 0.65 * np.clip(1 - np.abs(lum - 0.4) * 1.4, 0, 1))
        out = out + (noise * amp)[..., None]
    return out


def monochrome(out, look):
    """The edit card's right half: black and white, the shadows pulled down,
    a heavier grain and a vignette - what the card tells you to do."""
    h, w, _ = out.shape
    lum = out @ LUMA
    lum = np.clip((lum - 0.05) / 0.95, 0, 1) ** 1.12
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx + 0.5) / w - 0.5) ** 2 * 2.0 + ((yy + 0.5) / h - 0.5) ** 2 * 2.0)
    lum = lum * (1 - 0.35 * np.clip(r, 0, 1) ** 2)
    mono = np.repeat(lum[..., None], 3, axis=2)
    neutral = {**look, "lift": (0.045, 0.045, 0.045), "highlight_tint": (1.0, 1.0, 1.0)}
    return grade(mono, {**neutral, "grain": look.get("grain", 0.04) * 1.8}, 11)


def to_bytes(out):
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)

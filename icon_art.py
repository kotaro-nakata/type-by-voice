"""voice-term logo & tray artwork, shared by Linux (tray_indicator.py) and
Windows (tray_win.py).

The logo is a white microphone on a round coloured badge; the colour tells
the state:

    loading        grey
    idle / ready   green   (running, waiting for the hotkey)
    recording      red     (with sonar ripples that pulse to your voice)
    transcribing   yellow  (processing)

Everything is drawn at 4x and downscaled, so the edges stay smooth at any
tray size. Needs only Pillow, which both the venv and the system python have.

Run directly to export the app logo as a PNG:

    python3 icon_art.py logo.png [size]
"""
from PIL import Image, ImageDraw

SIZE = 64                    # logical canvas; icons are rendered SIZE x SIZE
C = SIZE / 2                 # centre
SS = 4                       # supersampling factor

COLORS = {
    "loading": (150, 157, 170),      # grey
    "idle": (52, 211, 153),          # green  (ready / waiting)
    "transcribing": (251, 191, 36),  # yellow (processing)
    "input-error": (168, 85, 247),   # purple (hotkey unavailable)
    "audio-error": (168, 85, 247),   # purple (microphone unavailable)
    "model-error": (168, 85, 247),   # purple (model unavailable)
}
REC_COLOR = (239, 68, 68)    # red  (recording)
WHITE = (255, 255, 255)

RIPPLE_MIN = 16.0            # ripples start at the recording badge edge
RIPPLE_MAX = 31.0            # and fade out by here


def _mic(d: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, color):
    """The microphone glyph, centred on (cx, cy) in logical coords.

    scale 1.0 gives a glyph ~31px tall on the 64px canvas.
    """
    def xy(x, y):  # glyph-local coords -> supersampled canvas pixels
        return ((cx + x * scale) * SS, (cy + y * scale) * SS)

    w = max(1, round(3.2 * scale * SS))  # stroke width
    # capsule (the mic body)
    d.rounded_rectangle([*xy(-6, -16), *xy(6, 2)],
                        radius=6 * scale * SS, fill=color)
    # holder arc, open at the top
    d.arc([*xy(-10, -8), *xy(10, 8)], start=-15, end=195, fill=color, width=w)
    # stem
    d.line([*xy(0, 8), *xy(0, 13)], fill=color, width=w)
    # base
    d.rounded_rectangle([*xy(-6.5, 11.6), *xy(6.5, 14.8)],
                        radius=1.6 * scale * SS, fill=color)


def _canvas():
    img = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _finish(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def _badge(d, r, color, alpha=255):
    d.ellipse([(C - r) * SS, (C - r) * SS, (C + r) * SS, (C + r) * SS],
              fill=color + (alpha,))


def make_static_image(color, size: int = SIZE) -> Image.Image:
    """Coloured badge + white mic — the resting states (and the app logo)."""
    img, d = _canvas()
    _badge(d, 30, color, 40)     # soft halo so it reads on light & dark panels
    _badge(d, 26, color)
    _mic(d, C, C + 0.6, 1.15, WHITE + (240,))
    return _finish(img, size)


def make_recording_image(level: float, ripples, size: int = SIZE) -> Image.Image:
    """Small red mic badge with sonar ripples pulsing to the live mic level."""
    img, d = _canvas()
    # outermost (faintest) first, so inner rings paint over them
    for r in sorted(ripples, reverse=True):
        t = (r - RIPPLE_MIN) / (RIPPLE_MAX - RIPPLE_MIN)
        t = max(0.0, min(1.0, t))
        # Stay clearly visible even when you're quiet; brighten with the voice.
        alpha = int((1.0 - t) * (140 + 115 * level))
        if alpha <= 0:
            continue
        d.ellipse([(C - r) * SS, (C - r) * SS, (C + r) * SS, (C + r) * SS],
                  outline=REC_COLOR + (alpha,), width=4 * SS)
    _badge(d, 13.5 + 2.5 * level, REC_COLOR)
    _mic(d, C, C + 0.3, 0.6, WHITE + (240,))
    return _finish(img, size)


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "voice-term.png"
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    make_static_image(COLORS["idle"], size).save(out)
    print(f"wrote {out} ({size}x{size})")

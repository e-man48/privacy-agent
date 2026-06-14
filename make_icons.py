"""Erzeugt das App-Icon (Schild mit Schluesselloch) in allen noetigen Formaten.

Quelle ist eine einzige 1024x1024-PNG (`app-icon.png`); daraus werden die von
Tauri referenzierten Icons in `src-tauri/icons/` erstellt. In der CI wird
zusaetzlich `tauri icon app-icon.png` genutzt (erzeugt u.a. zuverlaessig .icns).

Aufruf:  python make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
ICONS = ROOT / "src-tauri" / "icons"

ACCENT = (79, 134, 247, 255)   # Markenblau
WHITE = (255, 255, 255, 255)


def _rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_logo(size: int) -> Image.Image:
    """Zeichnet das Logo in der gegebenen Kantenlaenge."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Hintergrund: abgerundetes Quadrat in Markenblau.
    _rounded(d, [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=ACCENT)

    # Schild (weiss): oberer abgerundeter Block + untere Spitze.
    cx = size / 2
    w = size * 0.52
    top = size * 0.20
    h = size * 0.60
    left, right = cx - w / 2, cx + w / 2
    _rounded(d, [left, top, right, top + h * 0.58], radius=int(size * 0.10), fill=WHITE)
    d.polygon([(left, top + h * 0.42), (right, top + h * 0.42), (cx, top + h)], fill=WHITE)

    # Schluesselloch (in Markenblau, wirkt wie ausgeschnitten).
    r = size * 0.085
    ky = top + h * 0.40
    d.ellipse([cx - r, ky - r, cx + r, ky + r], fill=ACCENT)
    d.polygon([(cx - r * 0.55, ky), (cx + r * 0.55, ky),
               (cx + r * 0.32, ky + h * 0.20), (cx - r * 0.32, ky + h * 0.20)], fill=ACCENT)
    return img


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    master = draw_logo(1024)
    (ROOT / "app-icon.png").write_bytes(b"")  # Platzhalter, gleich ueberschrieben
    master.save(ROOT / "app-icon.png")

    # Von Tauri (tauri.conf.json) referenzierte Dateien.
    master.resize((32, 32), Image.LANCZOS).save(ICONS / "32x32.png")
    master.resize((128, 128), Image.LANCZOS).save(ICONS / "128x128.png")
    master.resize((256, 256), Image.LANCZOS).save(ICONS / "128x128@2x.png")
    master.resize((512, 512), Image.LANCZOS).save(ICONS / "icon.png")

    # Windows .ico (mehrere Groessen).
    master.save(ICONS / "icon.ico",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # macOS .icns (Pillow kann das; falls nicht, uebernimmt 'tauri icon' in der CI).
    try:
        master.save(ICONS / "icon.icns")
        icns = "ok"
    except Exception as exc:  # noqa: BLE001
        icns = f"uebersprungen ({exc}) -- in der CI via 'tauri icon'"

    print("Icons erzeugt in", ICONS)
    print("  app-icon.png, 32x32.png, 128x128.png, 128x128@2x.png, icon.png, icon.ico")
    print("  icon.icns:", icns)


if __name__ == "__main__":
    main()

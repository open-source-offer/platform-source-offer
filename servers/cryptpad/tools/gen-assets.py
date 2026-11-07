#!/usr/bin/env python3
"""Génère les icônes/aperçus neutres de customize/ (formes géométriques, aucune lettre).

Usage : python3 tools/gen-assets.py <répertoire customize.dist amont> <répertoire customize cible>
Seuls les noms de fichiers amont sont lus (pour reproduire les mêmes noms/dimensions).
Dépendance : Pillow.
"""
import glob
import os
import sys
from PIL import Image, ImageDraw

SLATE, MID, DARK, BG = (63, 91, 115, 255), (143, 163, 181, 217), (44, 65, 82, 255), (244, 246, 248, 255)


def icon(size):
    s = 4  # sur-échantillonnage
    n = size * s
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    u = n / 80.0
    d = ImageDraw.Draw(im, "RGBA")
    d.ellipse([30 * u, 30 * u, 74 * u, 74 * u], fill=MID)
    d.rounded_rectangle([8 * u, 8 * u, 52 * u, 52 * u], radius=10 * u, fill=SLATE, outline=DARK, width=max(1, int(3 * u)))
    return im.resize((size, size), Image.LANCZOS)


def preview(w=1200, h=630):
    im = Image.new("RGBA", (w, h), BG)
    ic = icon(300)
    im.alpha_composite(ic, ((w - 300) // 2, (h - 300) // 2))
    return im


def main(src, dst):
    for path in glob.glob(os.path.join(src, "favicon", "*.png")):
        name = os.path.basename(path)
        size = Image.open(path).size[0]
        out = os.path.join(dst, "favicon", name)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        icon(size).save(out)
    for path in glob.glob(os.path.join(src, "favicon", "*.ico")):
        out = os.path.join(dst, "favicon", os.path.basename(path))
        icon(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon(512).save(os.path.join(dst, "main-favicon.png"))
    icon(256).save(os.path.join(dst, "favicon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    os.makedirs(os.path.join(dst, "images", "opengraph_preview"), exist_ok=True)
    for path in glob.glob(os.path.join(src, "images", "opengraph_preview", "*.png")):
        preview().save(os.path.join(dst, "images", "opengraph_preview", os.path.basename(path)))
    # Avatar par défaut et images à marque : remplacées par le même visuel neutre.
    icon(256).save(os.path.join(dst, "images", "avatar.png"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

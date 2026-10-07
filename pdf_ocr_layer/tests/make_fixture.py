"""Genera un PDF de prueba que imita un documento escaneado.

Página 1 : imagen limpia con texto en inglés (sin capa de texto).
Página 2 : texto digital real, debe omitirse sin re-OCRizar.
Página 3 : imagen con ruido y ligera rotación, texto en español acentuado.

Uso: uv run python tests/make_fixture.py [ruta_salida]
"""

from __future__ import annotations

import io
import random
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Tamaño A4 en puntos de PDF.
PAGE_WIDTH, PAGE_HEIGHT = 595, 842

# Imagen a 150 dpi para el lienzo de 1240x1754 px.
CANVAS_SIZE = (1240, 1754)

ENGLISH_LINES = [
    "MONTHLY SERVICE REPORT",
    "",
    "This document was scanned from paper and then",
    "processed by an optical character recognition",
    "engine in order to make its content searchable.",
    "",
    "Reference number: ACC-2024-00871",
    "Total amount due: 1,240.50 USD",
]

SPANISH_LINES = [
    "INFORME DE GASTOS",
    "",
    "Este documento contiene acentos y eñes para",
    "comprobar que el reconocimiento optico de",
    "caracteres funciona correctamente en español.",
    "",
    "Nif de la empresa: B-12345678",
    "Importe total: 1.240,50 EUR",
]


def _render_text_image(lines: list[str], *, noisy: bool, rotate: float = 0.0) -> bytes:
    """Dibuja las líneas sobre un lienzo blanco y devuelve los bytes PNG."""
    image = Image.new("RGB", CANVAS_SIZE, "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT_PATH, 46)

    y = 140
    for line in lines:
        draw.text((110, y), line, font=font, fill="black")
        y += 96

    if rotate:
        image = image.rotate(
            rotate, expand=False, fillcolor="white", resample=Image.BICUBIC
        )

    if noisy:
        # Manchas puntuales simulando suciedad del escáner.
        pixels = image.load()
        rng = random.Random(1234)
        for _ in range(4000):
            x = rng.randrange(CANVAS_SIZE[0])
            y_ = rng.randrange(CANVAS_SIZE[1])
            shade = rng.randrange(0, 90)
            pixels[x, y_] = (shade, shade, shade)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.6))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build(output_path: Path) -> Path:
    doc = pymupdf.open()

    # Página 1: escaneo limpio en inglés, sin capa de texto.
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_image(page.rect, stream=_render_text_image(ENGLISH_LINES, noisy=False))

    # Página 2: texto digital real, el script debe omitirla.
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = 120
    for line in [
        "DIGITAL PAGE - NO OCR NEEDED",
        "",
        "This page already contains a real text layer,",
        "so the converter must skip it and keep the text",
        "exactly as it is right now.",
        "",
        "Sentence used to detect duplicated OCR output.",
    ]:
        page.insert_text((72, y), line, fontsize=16, fontname="helv")
        y += 36

    # Página 3: escaneo con ruido y texto español.
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_image(
        page.rect, stream=_render_text_image(SPANISH_LINES, noisy=True, rotate=1.5)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path, garbage=3, deflate=True)
    doc.close()
    return output_path


def main() -> int:
    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).with_name("fixture_scanned.pdf")
    )
    build(target)
    print(f"PDF de prueba generado: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verifica que la salida del conversor tenga una capa de texto válida.

Comprueba que:
  * las imágenes originales se conservan intactas,
  * las páginas sin texto digital quedan con una capa OCR,
  * la página con texto digital se omite sin duplicarla,
  * la apariencia visual del documento no cambia (capa invisible),
  * el texto del idioma pedido sobrevive con sus acentos.

Uso: uv run python tests/check_result.py <pdf_original> <pdf_convertido> [--lang eng]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

# Frases que la capa de OCR debe contener, por índice de página.
EXPECTED_PHRASES = {
    0: "optical character",
    1: "real text layer",
    2: "acentos",
}

# Frases que solo aparecen si el idioma se reconoció con acentos intactos.
ACCENTED_PHRASES = {
    "spa": ("eñes", "español"),
}

MIN_WORDS_PAGE = 10
# Tolerancia por byte al comparar renderizados (compresión/jpeg del viewer).
PIXEL_TOLERANCE = 2


class CheckError(Exception):
    """Fallo de verificación con mensaje legible."""


def _compare_appearance(original: pymupdf.Document, output: pymupdf.Document) -> None:
    """La capa OCR no debe alterar ni un píxel de la página."""
    for index in range(original.page_count):
        left = original[index].get_pixmap(dpi=72)
        right = output[index].get_pixmap(dpi=72)
        if len(left.samples) != len(right.samples):
            raise CheckError(f"página {index + 1}: el tamaño renderizado cambió")
        diff = sum(
            1
            for a, b in zip(left.samples, right.samples)
            if abs(a - b) > PIXEL_TOLERANCE
        )
        if diff:
            raise CheckError(
                f"página {index + 1}: la apariencia cambió en {diff} bytes "
                "de muestra (la capa no es invisible)"
            )


def _check_page_text(page: pymupdf.Page, index: int, language: str) -> None:
    words = page.get_text("words")
    text = page.get_text("text").lower()
    print(
        f"página {index + 1}: {len(words)} palabras extraídas, {len(page.get_images(full=True))} imagen(es)"
    )

    phrase = EXPECTED_PHRASES.get(index)
    if phrase and phrase.lower() not in text:
        raise CheckError(
            f"página {index + 1}: no se encontró '{phrase}' en la capa de texto"
        )

    if index != 1 and len(words) < MIN_WORDS_PAGE:
        raise CheckError(
            f"página {index + 1}: solo {len(words)} palabras, se esperaba una capa OCR"
        )

    if index == 2:
        for needed in ACCENTED_PHRASES.get(language, ()):
            if needed not in text:
                raise CheckError(
                    f"página {index + 1}: falta el acento en '{needed}' "
                    f"(¿idioma '{language}' correcto?)"
                )


def check(original_path: Path, output_path: Path, language: str) -> None:
    if not output_path.is_file():
        raise CheckError(f"no existe la salida: {output_path}")

    with pymupdf.open(original_path) as original, pymupdf.open(output_path) as output:
        if original.page_count != output.page_count:
            raise CheckError(
                f"cantidad de páginas: {original.page_count} -> {output.page_count}"
            )

        original_images = [len(p.get_images(full=True)) for p in original]
        output_images = [len(p.get_images(full=True)) for p in output]
        if original_images != output_images:
            raise CheckError(
                f"las imágenes cambiaron: {original_images} -> {output_images}"
            )

        _compare_appearance(original, output)

        for index, page in enumerate(output):
            _check_page_text(page, index, language)

        # La página 2 conserva su texto digital exactamente una vez.
        marker = [w for w in output[1].get_text("words") if w[4] == "duplicated"]
        if len(marker) != 1:
            raise CheckError(
                f"página 2: la palabra 'duplicated' aparece {len(marker)} veces (se esperaba 1)"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Valida el PDF producido por pdf_ocr_layer."
    )
    parser.add_argument("original", type=Path, help="PDF de entrada original")
    parser.add_argument("output", type=Path, help="PDF convertido con capa de texto")
    parser.add_argument("--lang", default="eng", help="Idioma usado en la conversión")
    args = parser.parse_args(argv)

    try:
        check(args.original, args.output, args.lang.lower())
    except CheckError as exc:
        print(f"FALLO: {exc}")
        return 1

    print("\nOK: la capa de texto se generó correctamente y la apariencia no cambió.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

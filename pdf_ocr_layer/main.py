#!/usr/bin/env python3
"""pdf_ocr_layer: convierte un PDF escaneado (imagen) en un PDF con capa de texto.

El PDF de salida conserva las imágenes originales y añade encima una capa de
texto invisible (render mode 3) generada por OCR, de modo que el contenido
quede seleccionable, copiable y buscable sin alterar la apariencia visual.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pymupdf

# Render mode de PDF que emite el texto pero no lo pinta: es la base de las
# capas de OCR "searchable". Valor 3 según la especificación de PDF (operator Tr).
INVISIBLE_RENDER_MODE = 3

# Valores por defecto de la línea de comandos.
DEFAULT_DPI = 300
DEFAULT_LANG = "eng"

# Nombre del grupo de contenido opcional (OCG) que agrupa la capa de OCR.
LAYER_OCG_NAME = "Texto OCR (invisible)"

# Cantidad mínima de palabras para considerar que una página ya tiene una capa
# de texto real. Por debajo se asume que es un resto aislado (un número de
# página, una marca de agua) y la página igual se OCRiza.
MIN_WORDS_TO_SKIP = 10


class ConversionError(Exception):
    """Error previsible que se muestra al usuario sin traza de traceback."""


# ---------------------------------------------------------------------------
# Comprobaciones del entorno
# ---------------------------------------------------------------------------


def _tessdata_dir() -> Path:
    """Devuelve la carpeta tessdata de Tesseract o lanza un error accionable."""
    try:
        tessdata = pymupdf.get_tessdata()
    except Exception as exc:
        raise ConversionError(
            "No se encontró la carpeta de datos de Tesseract.\n"
            "Instálala con: sudo apt install tesseract-ocr tesseract-ocr-eng"
        ) from exc

    path = Path(tessdata)
    if not path.is_dir():
        raise ConversionError(
            f"La carpeta de datos de Tesseract no existe: {path}\n"
            "Instálala con: sudo apt install tesseract-ocr tesseract-ocr-eng"
        )
    return path


def available_languages() -> set[str]:
    """Códigos de idioma con modelo instalado (archivos *.traineddata)."""
    return {p.stem for p in _tessdata_dir().glob("*.traineddata")}


def resolve_language(raw_language: str) -> str:
    """Valida el idioma pedido y devuelve la cadena lista para Tesseract.

    Acepta separadores '+', ',' o espacio (p. ej. "eng+spa", "eng, spa").
    """
    requested = [code for code in re.split(r"[+,\s]+", raw_language.strip()) if code]
    if not requested:
        raise ConversionError("No se indicó ningún idioma con --lang.")

    installed = available_languages()
    if not installed:
        raise ConversionError(
            "Tesseract está instalado pero no tiene ningún modelo de idioma.\n"
            "Instálalos con: sudo apt install tesseract-ocr-eng tesseract-ocr-spa"
        )

    missing = [code for code in requested if code not in installed]
    if missing:
        packages = " ".join(f"tesseract-ocr-{code}" for code in missing)
        raise ConversionError(
            f"Idioma(s) sin modelo instalado: {', '.join(missing)}\n"
            f"Disponibles: {', '.join(sorted(installed))}\n"
            f"Instálalos con: sudo apt install {packages}"
        )

    return "+".join(requested)


# ---------------------------------------------------------------------------
# Conversión
# ---------------------------------------------------------------------------


def resolve_page_range(
    page_count: int, first: int | None, last: int | None
) -> tuple[int, int]:
    """Convierte el rango 1-indexado del usuario en índices 0-indexados."""
    start = 1 if first is None else first
    end = page_count if last is None else last

    if start < 1 or end < 1:
        raise ConversionError("Los números de página deben ser mayores o iguales a 1.")
    if start > page_count or end > page_count:
        raise ConversionError(
            f"El documento tiene {page_count} página(s); "
            f"se pidió el rango {start}-{end}."
        )
    if start > end:
        raise ConversionError(
            f"El rango de páginas es inválido: --inicio ({start}) es mayor que --fin ({end})."
        )

    return start - 1, end - 1


def has_text_layer(page: pymupdf.Page, min_words: int = MIN_WORDS_TO_SKIP) -> bool:
    """Indica si la página ya contiene una capa de texto suficientemente densa."""
    return len(page.get_text("words")) >= min_words


def _create_text_layer_group(doc: pymupdf.Document) -> int:
    """Crea el grupo de contenido opcional de la capa OCR (0 si no es posible)."""
    try:
        return doc.add_ocg(LAYER_OCG_NAME)
    except Exception:  # noqa: BLE001 - sin OCG el texto igual se inserta
        return 0


def insert_invisible_text(
    page: pymupdf.Page, textpage: pymupdf.TextPage, ocg_xref: int
) -> int:
    """Vuelca el resultado del OCR como texto invisible sobre la página.

    Se reutiliza la posición de línea base (`origin`) y el cuerpo (`size`) que
    Tesseract ya calculó, para que la selección coincida con la imagen.
    """
    inserted = 0
    for block in textpage.extractDICT().get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"]
                size = span["size"]
                # No usar text.strip(): los spans que son solo un espacio son
                # necesarios para que el texto extraído conserve las palabras.
                if not text or size <= 0:
                    continue
                x, y = span["origin"]
                page.insert_text(
                    pymupdf.Point(x, y),
                    text,
                    fontsize=size,
                    fontname="helv",
                    render_mode=INVISIBLE_RENDER_MODE,
                    overlay=True,
                    oc=ocg_xref,
                )
                inserted += 1
    return inserted


def _open_pdf(path: Path) -> pymupdf.Document:
    """Abre el PDF validando existencia, tipo y protección por contraseña."""
    if not path.exists():
        raise ConversionError(f"No existe el archivo: {path}")
    if not path.is_file():
        raise ConversionError(f"La ruta no es un archivo: {path}")

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ConversionError(f"No se pudo abrir '{path}' como PDF: {exc}") from exc

    if doc.is_encrypted and not doc.authenticate(""):
        doc.close()
        raise ConversionError(f"El PDF está protegido con contraseña: {path}")
    if doc.page_count == 0:
        doc.close()
        raise ConversionError(f"El PDF no tiene páginas: {path}")

    return doc


def convert(
    input_path: str | Path,
    output_path: str | Path,
    language: str = DEFAULT_LANG,
    dpi: int = DEFAULT_DPI,
    first: int | None = None,
    last: int | None = None,
    write_txt: bool = False,
    ocr_everything: bool = False,
    overwrite: bool = False,
    verbose: bool = True,
) -> dict[str, int]:
    """Convierte `input_path` en un PDF con capa de texto y devuelve métricas."""
    src = Path(input_path).expanduser()
    dst = Path(output_path).expanduser()

    if src.resolve() == dst.resolve():
        raise ConversionError(
            "El archivo de salida no puede ser el mismo que el de entrada. "
            "Usa --salida para indicar otra ruta."
        )
    if dst.exists() and not overwrite:
        raise ConversionError(
            f"Ya existe el archivo de salida: {dst}\n"
            "Añade --overwrite para reemplazarlo."
        )
    if dpi < 72:
        raise ConversionError("--dpi debe ser al menos 72.")

    tessdata_language = resolve_language(language)
    doc = _open_pdf(src)

    stats = {"pages": 0, "ocr": 0, "skipped": 0, "spans": 0}
    ocg_xref = _create_text_layer_group(doc)

    try:
        # El rango se valida dentro del bloque para no dejar el PDF abierto
        # si el usuario se equivoca con --inicio/--fin.
        start_index, end_index = resolve_page_range(doc.page_count, first, last)

        total = end_index - start_index + 1
        for offset, page_index in enumerate(range(start_index, end_index + 1), start=1):
            page = doc[page_index]
            stats["pages"] += 1

            if not ocr_everything and has_text_layer(page):
                stats["skipped"] += 1
                if verbose:
                    print(
                        f"[{offset}/{total}] página {page_index + 1}: "
                        "ya tiene capa de texto, se omite",
                        flush=True,
                    )
                continue

            if verbose:
                print(
                    f"[{offset}/{total}] página {page_index + 1}: OCR a {dpi} dpi...",
                    flush=True,
                )

            try:
                textpage = page.get_textpage_ocr(
                    dpi=dpi,
                    language=tessdata_language,
                    full=True,
                )
            except Exception as exc:
                raise ConversionError(
                    f"Fallo de OCR en la página {page_index + 1}: {exc}\n"
                    f"Comprueba que el idioma '{tessdata_language}' está instalado: "
                    "tesseract --list-langs"
                ) from exc

            stats["ocr"] += 1
            stats["spans"] += insert_invisible_text(page, textpage, ocg_xref)

        dst.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dst, garbage=3, deflate=True)
    finally:
        doc.close()

    if write_txt:
        _write_text_file(dst, start_index, end_index)

    if verbose:
        print(
            f"\nListo: {dst}\n"
            f"  Páginas procesadas : {stats['pages']}\n"
            f"  Páginas OCRizadas  : {stats['ocr']}\n"
            f"  Páginas omitidas   : {stats['skipped']} (ya tenían capa de texto)\n"
            f"  Fragmentos insertados: {stats['spans']}",
            flush=True,
        )

    return stats


def _write_text_file(output_pdf: Path, start_index: int, end_index: int) -> Path:
    """Exporta el texto extraído (imagen + capa OCR) a un .txt junto al PDF."""
    txt_path = output_pdf.with_suffix(".txt")
    lines: list[str] = []

    with pymupdf.open(output_pdf) as doc:
        for page_index in range(start_index, end_index + 1):
            text = doc[page_index].get_text("text").strip()
            lines.append(f"--- Página {page_index + 1} ---\n{text}")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return txt_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf_ocr_layer",
        description="Convierte un PDF escaneado (imagen) en un PDF con capa de texto seleccionable.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Ruta al PDF de entrada")
    parser.add_argument(
        "--salida",
        default=None,
        help="Ruta del PDF de salida (por defecto: <entrada>_texto.pdf)",
    )
    parser.add_argument(
        "--lang",
        default=DEFAULT_LANG,
        help="Idioma(s) para el OCR, p. ej. 'eng', 'spa' o 'eng+spa'",
    )
    parser.add_argument(
        "--dpi", type=int, default=DEFAULT_DPI, help="Resolución usada para rasterizar"
    )
    parser.add_argument(
        "--inicio", type=int, default=None, help="Primera página (1-indexado)"
    )
    parser.add_argument(
        "--fin", type=int, default=None, help="Última página (1-indexado)"
    )
    parser.add_argument(
        "--txt", action="store_true", help="Exportar también el texto a un .txt"
    )
    parser.add_argument(
        "--ocr-todo",
        action="store_true",
        help="No omitir páginas que ya tienen capa de texto (puede duplicar texto)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Sobrescribir el archivo de salida"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="No imprimir progreso"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    output = args.salida
    if output is None:
        source = Path(args.input)
        output = source.with_name(f"{source.stem}_texto.pdf")

    try:
        convert(
            input_path=args.input,
            output_path=output,
            language=args.lang,
            dpi=args.dpi,
            first=args.inicio,
            last=args.fin,
            write_txt=args.txt,
            ocr_everything=args.ocr_todo,
            overwrite=args.overwrite,
            verbose=not args.quiet,
        )
    except ConversionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())

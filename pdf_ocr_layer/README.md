# pdf_ocr_layer

Convierte un **PDF escaneado (imagen)** en un **PDF con capa de texto seleccionable**.

El PDF de salida conserva exactamente las imágenes originales y añade encima una capa
de texto invisible generada por OCR, de modo que el contenido queda **seleccionable,
copiable y buscable** sin alterar en absoluto la apariencia visual del documento.

```
entrada.pdf  ──OCR──▶  entrada_texto.pdf
             imagen intacta + capa de texto invisible
```

## Requisitos

Tesseract con los modelos de idioma (en Ubuntu/Debian):

```bash
sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa
tesseract --list-langs        # debe listar eng y spa
```

Para otro idioma, instalá su paquete (p. ej. `tesseract-ocr-fra`, `tesseract-ocr-ita`).

## Instalación

```bash
uv sync
```

Crea `.venv` (Python 3.13) y fija las versiones en `uv.lock`.

## Uso

```bash
# Todo el documento, inglés, salida <entrada>_texto.pdf
uv run python main.py entrada.pdf

# Español, con archivo .txt aparte
uv run python main.py entrada.pdf --lang spa --txt

# Rango de páginas y salida personalizada
uv run python main.py entrada.pdf --inicio 14 --fin 19 --salida parcial.pdf
```

### Opciones

| Opción | Por defecto | Descripción |
| --- | --- | --- |
| `--salida` | `<entrada>_texto.pdf` | Ruta del PDF de salida |
| `--lang` | `eng` | Idioma(s) del OCR: `eng`, `spa`, `eng+spa`, o cualquier idioma instalado |
| `--dpi` | `300` | Resolución usada para rasterizar antes de OCR |
| `--inicio` / `--fin` | 1 / última | Rango de páginas (1-indexado) |
| `--txt` | apagado | Exporta también el texto a `<salida>.txt` |
| `--ocr-todo` | apagado | No omite páginas que ya tienen capa de texto |
| `--overwrite` | apagado | Sobrescribe el archivo de salida |
| `-q` / `--quiet` | apagado | No imprime progreso |

## Comportamiento

* **Las páginas que ya tienen una capa de texto se omiten** (no se re-OCRizan ni se
  duplica el texto). Se considera que una página "ya tiene texto" a partir de 10
  palabras. Usá `--ocr-todo` para forzar el OCR igualmente.
* **La capa es invisible**: se emite con render mode 3 (`3 Tr`), por lo que la
  comparación píxel a píxel entre entrada y salida da idéntica.
* **Las imágenes originales no se recomprimen ni se modifican.**
* El texto se inserta en la posición de línea base y el cuerpo que calculó
  Tesseract, de modo que la selección coincide con la imagen.
* La capa se agrupa en un *Optional Content Group* llamado
  `Texto OCR (invisible)`, que los visores permiten activar o desactivar.

## Notas sobre idiomas

* Para documentos en **inglés** usá `--lang eng`; para **español**, `--lang spa`.
* Mezclar idiomas con `--lang eng+spa` a veces **degrada los acentos** (Tesseract
  prioriza el primer idioma). Si el documento es de un solo idioma, indicá solo ese.
* Más idiomas: `sudo apt install tesseract-ocr-<codigo>` y pasá el código a `--lang`.

## Errores

El script no imprime trazas de traceback: valida el entorno antes de trabajar y
devuelve un mensaje accionable con código de salida `1`. Ejemplos:

```
Error: Tesseract está instalado pero no tiene ningún modelo de idioma.
Instálalos con: sudo apt install tesseract-ocr-eng tesseract-ocr-spa

Error: Idioma(s) sin modelo instalado: deu
Disponibles: eng, osd, spa
Instálalos con: sudo apt install tesseract-ocr-deu

Error: El documento tiene 3 página(s); se pidió el rango 1-99.
```

## Tests

```bash
# Genera un PDF de prueba de 3 páginas (imagen limpia, texto digital, imagen con ruido)
uv run python tests/make_fixture.py

# Convierte y valida
uv run python main.py tests/fixture_scanned.pdf --lang spa --salida /tmp/salida.pdf
uv run python tests/check_result.py tests/fixture_scanned.pdf /tmp/salida.pdf --lang spa
```

El verificador comprueba que las imágenes se conservan, que la capa OCR existe, que
la página digital no se duplicó, que la **apariencia visual no cambió** y que los
acentos del idioma pedido sobreviven.

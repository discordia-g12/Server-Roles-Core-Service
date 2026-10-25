"""Validación y normalización de imágenes subidas (íconos de servidor)."""

import io

from PIL import Image, ImageOps

from app.exceptions import BadRequestError

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_PIXELS = 4096 * 4096  # un PNG chico puede descomprimir a miles de megapíxeles
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
OUTPUT_SIZE = 256


def normalize_image(contents: bytes) -> bytes:
    """Valida que sea una imagen JPEG/PNG/WebP de hasta 5 MB y la devuelve como WebP cuadrado de 256 px.

    Se valida el contenido real del archivo, no el Content-Type que manda el cliente. Recodificar
    además descarta los metadatos (EXIF con ubicación) y cualquier cosa escondida en el archivo.
    """
    if not contents:
        raise BadRequestError("The file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise BadRequestError("File too large. Limit 5MB.")

    try:
        with Image.open(io.BytesIO(contents)) as probe:
            image_format = probe.format
            width, height = probe.size
            probe.verify()
    except Exception:
        raise BadRequestError("Unsupported format. Use JPEG, PNG or WebP.") from None

    if image_format not in ALLOWED_FORMATS:
        raise BadRequestError("Unsupported format. Use JPEG, PNG or WebP.")
    if width * height > MAX_PIXELS:
        raise BadRequestError("Image too large. Limit 4096x4096 pixels.")

    try:
        # verify() deja la imagen inutilizable: hay que reabrirla para procesarla
        with Image.open(io.BytesIO(contents)) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
            image = ImageOps.fit(image, (OUTPUT_SIZE, OUTPUT_SIZE), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            image.save(output, format="WEBP", quality=85)
    except Exception:
        raise BadRequestError("The image could not be processed.") from None

    return output.getvalue()

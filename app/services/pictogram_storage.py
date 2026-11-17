import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.supabase_client import get_supabase_client


BUCKET_NAME = "custom-pictograms"

MAX_UPLOAD_SIZE = 5 * 1024 * 1024
MAX_OPTIMIZED_SIZE = 1 * 1024 * 1024
MAX_IMAGE_DIMENSION = 512

SIGNED_URL_EXPIRATION = 3600

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    content_hash: str
    width: int
    height: int


def process_pictogram_image(
    file_content: bytes,
) -> ProcessedImage:
    """Valida, otimiza e calcula o hash da imagem."""

    if not file_content:
        raise ValueError("O arquivo enviado esta vazio.")

    if len(file_content) > MAX_UPLOAD_SIZE:
        raise ValueError("O arquivo deve ter no maximo 5 MB.")

    content_hash = hashlib.sha256(file_content).hexdigest()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )

            image = Image.open(io.BytesIO(file_content))

            if image.format not in ALLOWED_FORMATS:
                raise ValueError(
                    "Formato invalido. Envie PNG, JPEG ou WebP."
                )

            if getattr(image, "n_frames", 1) > 1:
                raise ValueError(
                    "Imagens animadas nao sao aceitas."
                )

            image.verify()

            image = Image.open(io.BytesIO(file_content))
            image = ImageOps.exif_transpose(image)

            has_transparency = (
                "A" in image.getbands()
                or "transparency" in image.info
            )

            image = image.convert(
                "RGBA" if has_transparency else "RGB"
            )

            image.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                Image.Resampling.LANCZOS,
            )

    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError(
            "Nao foi possivel processar a imagem enviada."
        ) from error

    width, height = image.size

    # Reduz a qualidade e, se necessario, as dimensoes
    # para respeitar o limite de armazenamento.
    while True:
        for quality in (88, 82, 76, 70, 64, 58):
            output = io.BytesIO()

            image.save(
                output,
                format="WEBP",
                quality=quality,
                method=6,
            )

            optimized_content = output.getvalue()

            if len(optimized_content) <= MAX_OPTIMIZED_SIZE:
                return ProcessedImage(
                    content=optimized_content,
                    content_hash=content_hash,
                    width=width,
                    height=height,
                )

        if max(image.size) <= 128:
            raise ValueError(
                "Nao foi possivel otimizar a imagem para o limite permitido."
            )

        new_size = (
            max(1, int(image.width * 0.85)),
            max(1, int(image.height * 0.85)),
        )

        image = image.resize(
            new_size,
            Image.Resampling.LANCZOS,
        )

        width, height = image.size


def upload_pictogram_image(
    storage_path: str,
    content: bytes,
) -> None:
    """Envia uma imagem WebP para o bucket privado."""

    client = get_supabase_client()

    client.storage.from_(BUCKET_NAME).upload(
        path=storage_path,
        file=content,
        file_options={
            "content-type": "image/webp",
            "cache-control": "3600",
            "upsert": "false",
        },
    )


def create_pictogram_signed_url(
    storage_path: str,
) -> str:
    """Gera uma URL temporaria para acessar a imagem."""

    client = get_supabase_client()

    response = client.storage.from_(BUCKET_NAME).create_signed_url(
        path=storage_path,
        expires_in=SIGNED_URL_EXPIRATION,
    )

    signed_url = response.get("signedURL") or response.get("signedUrl")

    if not signed_url:
        raise RuntimeError(
            "Nao foi possivel gerar a URL da imagem."
        )

    return signed_url


def delete_pictogram_image(
    storage_path: str,
) -> None:
    """Remove uma imagem do bucket."""

    client = get_supabase_client()

    client.storage.from_(BUCKET_NAME).remove(
        [storage_path]
    )
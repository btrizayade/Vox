import hashlib
import io

import pytest
from PIL import Image, ImageDraw

from app.services.pictogram_storage import (
    MAX_OPTIMIZED_SIZE,
    process_pictogram_image,
)


def create_test_image(
    image_format="PNG",
    size=(200, 150),
):
    """Cria uma imagem temporaria para os testes."""

    mode = "RGB" if image_format == "JPEG" else "RGBA"

    color = (
        (100, 150, 200)
        if mode == "RGB"
        else (100, 150, 200, 255)
    )

    image = Image.new(mode, size, color)

    output = io.BytesIO()
    image.save(output, format=image_format)

    return output.getvalue()


@pytest.mark.parametrize(
    "image_format",
    ["PNG", "JPEG", "WEBP"],
)
def test_processes_supported_formats(image_format):
    """Aceita os tres formatos permitidos."""

    original = create_test_image(image_format)

    result = process_pictogram_image(original)

    optimized = Image.open(io.BytesIO(result.content))

    assert optimized.format == "WEBP"
    assert result.width <= 512
    assert result.height <= 512


def test_calculates_original_file_hash():
    """Calcula SHA-256 usando o arquivo original."""

    original = create_test_image()

    result = process_pictogram_image(original)

    expected_hash = hashlib.sha256(original).hexdigest()

    assert result.content_hash == expected_hash


def test_preserves_image_dimensions_proportionally():
    """Redimensiona sem distorcer a proporcao."""

    original = create_test_image(
        image_format="PNG",
        size=(2000, 1000),
    )

    result = process_pictogram_image(original)

    assert result.width == 512
    assert result.height == 256


def test_preserves_transparency():
    """Preserva a transparencia de imagens PNG."""

    image = Image.new(
        "RGBA",
        (64, 64),
        (255, 0, 0, 0),
    )

    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (16, 16, 48, 48),
        fill=(255, 0, 0, 255),
    )

    output = io.BytesIO()
    image.save(output, format="PNG")

    result = process_pictogram_image(output.getvalue())

    optimized = Image.open(io.BytesIO(result.content))

    assert optimized.mode == "RGBA"
    assert optimized.getpixel((0, 0))[3] == 0


def test_optimized_image_respects_size_limit():
    """O arquivo otimizado nao ultrapassa 1 MB."""

    original = create_test_image(
        image_format="PNG",
        size=(2000, 2000),
    )

    result = process_pictogram_image(original)

    assert len(result.content) <= MAX_OPTIMIZED_SIZE


def test_rejects_empty_file():
    """Rejeita arquivos vazios."""

    with pytest.raises(ValueError, match="vazio"):
        process_pictogram_image(b"")


def test_rejects_file_larger_than_5_mb():
    """Rejeita arquivos acima do limite de upload."""

    oversized_file = b"x" * (5 * 1024 * 1024 + 1)

    with pytest.raises(ValueError, match="5 MB"):
        process_pictogram_image(oversized_file)


def test_rejects_invalid_image():
    """Rejeita conteudo que nao representa uma imagem."""

    invalid_file = b"not-an-image"

    with pytest.raises(ValueError, match="processar a imagem"):
        process_pictogram_image(invalid_file)


def test_rejects_unsupported_format():
    """Rejeita formatos que nao estao na lista permitida."""

    original = create_test_image("GIF")

    with pytest.raises(ValueError, match="Formato invalido"):
        process_pictogram_image(original)
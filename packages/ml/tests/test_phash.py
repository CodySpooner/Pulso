import io
import random

from PIL import Image, ImageDraw

from pulso_ml.phash import phash, similarity


def product(seed: int, size: int = 512) -> Image.Image:
    """A generated 'product photo': a gradient backdrop and a few filled shapes."""
    rng = random.Random(seed)
    backdrop = Image.linear_gradient("L").rotate(rng.choice([0, 90, 180, 270]))
    image = backdrop.resize((size, size)).convert("RGB")
    draw = ImageDraw.Draw(image)
    for _ in range(6):
        x, y = rng.randrange(size - 160), rng.randrange(size - 160)
        box = (x, y, x + rng.randrange(80, 160), y + rng.randrange(80, 160))
        fill = tuple(rng.randrange(256) for _ in range(3))
        (draw.ellipse if rng.random() < 0.5 else draw.rectangle)(box, fill=fill)
    return image


def encode(image: Image.Image, fmt: str, **options: int) -> bytes:
    out = io.BytesIO()
    image.save(out, fmt, **options)
    return out.getvalue()


def hamming(a: int, b: int) -> int:
    return round((1 - similarity(a, b)) * 64)


def test_identical_bytes_hash_identically() -> None:
    data = encode(product(1), "PNG")
    assert phash(Image.open(io.BytesIO(data))) == phash(Image.open(io.BytesIO(data)))


def test_resized_jpeg_copy_is_near_and_unrelated_images_are_far() -> None:
    for seed in range(1, 6):
        original = product(seed)
        copy = Image.open(io.BytesIO(encode(original.resize((300, 300)), "JPEG", quality=70)))
        assert hamming(phash(original), phash(copy)) <= 6
    hashes = [phash(product(seed)) for seed in range(1, 6)]
    assert all(hamming(a, b) > 20 for i, a in enumerate(hashes) for b in hashes[i + 1 :])


def test_hash_is_signed_64_bit_and_similarity_bounds() -> None:
    value = phash(product(1))
    # The DC term is the largest coefficient of a non-negative image, so the top bit is set.
    assert -(1 << 63) <= value < 0
    assert similarity(value, value) == 1.0
    assert similarity(value, ~value) == 0.0
    assert similarity(-1, (1 << 63) - 1) == 1 - 1 / 64

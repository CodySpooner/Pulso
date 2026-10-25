"""64-bit DCT perceptual hash of a listing image, stored signed in `images.phash` (DEC-240)."""

import numpy as np
from PIL import Image

SIZE, BLOCK = 32, 8
# DCT-II basis, row k = cos(pi * k * (2n + 1) / 2N). Unscaled: the median threshold ignores scale.
_DCT = np.cos(np.pi * np.outer(np.arange(SIZE), 2 * np.arange(SIZE) + 1) / (2 * SIZE))


def phash(image: Image.Image) -> int:
    """Grayscale 32x32, 2-D DCT, top-left 8x8 (DC included), bits above the median, MSB first.

    Returned as a signed 64-bit integer (two's complement) so it fits Postgres BIGINT.
    """
    gray = image.convert("L").resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    low = (_DCT @ np.asarray(gray, dtype=np.float64) @ _DCT.T)[:BLOCK, :BLOCK]
    value = int.from_bytes(np.packbits(low > np.median(low)).tobytes(), "big")
    return value - (1 << 64) if value >> 63 else value


def similarity(a: int, b: int) -> float:
    """1 - Hamming distance / 64 between two stored hashes (M-3's `phash_sim`)."""
    return 1 - ((a ^ b) & ((1 << 64) - 1)).bit_count() / 64

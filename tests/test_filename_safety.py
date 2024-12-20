"""Filename-safety test."""

import random
import string
import pytest
from opicrawler.filepath_utils import filename_safe_encode, filename_safe_decode


population = tuple(chr(i) for i in range(32, 0x110000) if chr(i).isprintable())
k = 1000
n = 100
random.seed(0)

@pytest.mark.parametrize("text", ["".join(random.choices(population, k=k)) for _ in range(n)])
def test_filename_safe_encoding(text):
    """Test decoding, alphabet and length of a filename-safe encoded text."""
    encoded_text = filename_safe_encode(text)
    decoded_text = filename_safe_decode(encoded_text)
    assert text == decoded_text

    base64url_alphabet = string.ascii_letters + string.digits + "-_="
    assert set(encoded_text).issubset(base64url_alphabet)

    limited_encoded_text = filename_safe_encode(text, limit_length=True)
    assert len(limited_encoded_text.encode("utf-8")) <= 255

    framed_limited_encoded_text = filename_safe_encode(
        text,
        limit_length=True,
        prefix="".join(random.choices(base64url_alphabet, k=100)),
        postfix="".join(random.choices(base64url_alphabet, k=100)),
    )
    assert len(framed_limited_encoded_text.encode("utf-8")) <= 255

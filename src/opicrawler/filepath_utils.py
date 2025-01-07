"""File path utilities."""

import base64
import re
import string
from pathlib import Path


def ensure_path(pathlike) -> Path:
    """Make the directory if missing and return its path."""
    path = Path(pathlike)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_url_to_filename(url, limit_length=False, prefix=None, postfix=None):
    """Convert a URL to a filesystem-safe filename using a restricted character set."""
    allowed_chars = string.ascii_letters + string.digits + "-_=."
    url = re.sub(r"^.*://", "", url)
    filename = "".join(c for c in url if c in allowed_chars)
    if limit_length:
        prefix = prefix or ""
        postfix = postfix or ""
        limit = 255 - len(prefix.encode("utf-8")) - len(postfix.encode("utf-8"))
        return prefix + filename[:limit] + postfix
    return filename


def filename_safe_encode(text, limit_length=False, prefix=None, postfix=None):
    """Encode text to a filename-safe format."""
    # RFC 4648 §5: base64url (URL- and filename-safe standard):
    # https://datatracker.ietf.org/doc/html/rfc4648#section-5
    encoded_text = base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8")

    # 255 bytes is a common maximum filename length:
    # https://en.wikipedia.org/wiki/Comparison_of_file_systems#Limits
    if limit_length:
        prefix = prefix or ""
        postfix = postfix or ""
        limit = 255 - len(prefix.encode("utf-8")) - len(postfix.encode("utf-8"))
        return prefix + encoded_text[:limit] + postfix
    return encoded_text


def filename_safe_decode(text):
    """Decode text from a filename-safe format."""
    decoded_text = base64.urlsafe_b64decode(text.encode("utf-8")).decode("utf-8")
    return decoded_text

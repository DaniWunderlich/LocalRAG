"""Frontend settings shared with the backend through the deployment environment."""

import os


def upload_limit() -> int:
    """Keep Gradio ingress and initial workspace validation consistent."""
    try:
        value = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
    except ValueError as error:
        raise ValueError("MAX_UPLOAD_BYTES must be a positive integer.") from error
    if value < 1:
        raise ValueError("MAX_UPLOAD_BYTES must be a positive integer.")
    return value


def upload_size_label(size: int) -> str:
    """Display the configured bound using binary units."""
    for divisor, unit in [(1024 * 1024, "MiB"), (1024, "KiB"), (1, "B")]:
        if size >= divisor:
            return f"{size / divisor:g} {unit}"
    return "0 B"

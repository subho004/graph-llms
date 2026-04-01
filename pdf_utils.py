from markitdown import MarkItDown
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str) -> str:
    """Extract plain text from a PDF file using MarkItDown.

    Args:
        file_path: Path to the PDF file.

    Returns:
        A string containing extracted text.

    Raises:
        FileNotFoundError: if the file does not exist.
        RuntimeError: if the conversion fails or returns no text.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    try:
        md = MarkItDown(enable_plugins=False)
        result = md.convert(file_path)
    except Exception as e:
        logger.exception("MarkItDown conversion failed for %s", file_path)
        raise RuntimeError("Failed to convert PDF to text") from e

    # Preferred attribute per MarkItDown docs
    text = getattr(result, "text_content", None)
    if not text:
        # fallbacks in case of different converter shapes
        text = getattr(result, "text", None) or getattr(result, "markdown", None) or str(result)

    if not text:
        raise RuntimeError("No text extracted from PDF")

    return text


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_utils.py path/to/file.pdf")
        raise SystemExit(2)

    path = sys.argv[1]
    try:
        out = extract_text_from_pdf(path)
        # Print a trimmed preview for CLI runs
        print(out)
    except Exception as e:
        print("Error:", e)
        raise

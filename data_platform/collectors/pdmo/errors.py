"""Shared bits for the PDMO parsers."""


class ParseError(Exception):
    """A file we cannot make sense of. Recorded against the file; never crashes a run."""


def lkr_from_millions(millions: float) -> int:
    """Rs. millions (as the sources report) -> integer rupees, exactly."""
    return round(millions * 1_000_000)


def pdf_source(path_or_bytes):
    """TBD: pdfplumber opens a path or a file-like object; the raw archive hands us bytes."""
    import io

    if isinstance(path_or_bytes, (bytes, bytearray)):
        return io.BytesIO(bytes(path_or_bytes))
    return path_or_bytes

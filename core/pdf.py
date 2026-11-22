"""Minimal PDF generation with the stdlib only (the runtime stays Django-only).

make_cv_pdf(profile) renders the candidate's profile onto a one-or-more-page
PDF (Helvetica / Helvetica-Bold, WinAnsi). Not a layout engine — a clean,
valid single-column document suitable for attaching to an application email.
"""

from core.models import Profile

PAGE_WIDTH = 595  # A4 in points
PAGE_HEIGHT = 842
MARGIN = 50
LINE_HEIGHT = 14
LINES_PER_PAGE = int((PAGE_HEIGHT - 2 * MARGIN) // LINE_HEIGHT) - 1
MAX_LINE_CHARS = 95


def _escape(text: str) -> str:
    """Escape PDF string specials; encode as WinAnsi (latin-1) with replacement."""
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def _wrap(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines() or [""]:
        while len(raw) > MAX_LINE_CHARS:
            lines.append(raw[:MAX_LINE_CHARS])
            raw = raw[MAX_LINE_CHARS:]
        lines.append(raw)
    return lines


def _content_lines(profile: Profile) -> list[tuple[str, str]]:
    """(text, font) pairs: font is 'F2' (bold headers) or 'F1' (body)."""
    out: list[tuple[str, str]] = []
    sections = [
        ("Headline", profile.headline),
        ("Skills", profile.skills),
        ("Experience", profile.experience),
        ("Education", profile.education),
        ("Links", profile.links),
        ("CV", profile.cv_text),
    ]
    for title, body in sections:
        if not body.strip():
            continue
        out.append((title.upper(), "F2"))
        out.extend((line, "F1") for line in _wrap(body.strip()))
        out.append(("", "F1"))  # spacer
    return out


def make_cv_pdf(profile: Profile) -> bytes:
    """Render the profile as a PDF document and return the bytes."""
    lines = _content_lines(profile)
    pages = [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [
        [("(empty profile)", "F1")]
    ]

    # Object layout: 1 catalog, 2 pages, 3 font F1, 4 font F2,
    # then per page: page object, content object.
    objects: list[bytes] = []
    page_obj_ids = [5 + 2 * i for i in range(len(pages))]
    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    for page_lines in pages:
        stream_parts = [b"BT"]
        y = PAGE_HEIGHT - MARGIN
        font = ""
        for text, wanted_font in page_lines:
            if wanted_font != font:
                size = 13 if wanted_font == "F2" else 10
                stream_parts.append(f"/{wanted_font} {size} Tf".encode())
                font = wanted_font
            if text:
                stream_parts.append(f"{MARGIN} {y} Td".encode())
                stream_parts.append(f"({_escape(text)}) Tj".encode())
            y -= LINE_HEIGHT
        stream_parts.append(b"ET")
        stream = b"\n".join(stream_parts)
        objects.append(b"")  # page object placeholder, filled once its id is known
        page_id = len(objects)
        content_id = len(objects) + 1
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    out += trailer.encode()
    return bytes(out)

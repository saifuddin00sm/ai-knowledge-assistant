"""Parsers: text, markdown, DOCX, PDF, and the rejection paths."""

from __future__ import annotations

import io

import pytest

from app.core.errors import InvalidRequestError, UnsupportedMediaTypeError
from app.services.ingestion import parsers

NBSP = chr(0x00A0)
ZERO_WIDTH_SPACE = chr(0x200B)
BOM = chr(0xFEFF)


def test_plain_text_becomes_one_page_without_a_number() -> None:
    parsed = parsers.parse("notes.txt", b"Hello world.\n\nSecond paragraph.")
    assert len(parsed.pages) == 1
    assert parsed.pages[0].page is None
    assert parsed.page_count is None
    assert "Second paragraph." in parsed.text


def test_markdown_is_parsed_as_text() -> None:
    parsed = parsers.parse("readme.md", b"# Title\n\nBody text.")
    assert "# Title" in parsed.text
    assert not parsed.is_empty


def test_normalize_text_collapses_runs_and_strips_invisibles() -> None:
    raw = "a" + NBSP + "b\r\nc\t\td\n\n\n\ne" + ZERO_WIDTH_SPACE + "f" + BOM
    assert parsers.normalize_text(raw) == "a b\nc d\n\nef"


def test_normalize_text_trims_trailing_whitespace_per_line() -> None:
    assert parsers.normalize_text("line one   \nline two  ") == "line one\nline two"


def test_empty_file_yields_an_empty_document() -> None:
    parsed = parsers.parse("empty.txt", b"   \n  ")
    assert parsed.is_empty
    assert parsed.pages == []


def test_unknown_extension_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaTypeError, match="Unsupported file type"):
        parsers.parse("data.csv", b"a,b,c")


def test_extensionless_filename_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        parsers.parse("LICENSE", b"text")


def test_extension_of() -> None:
    assert parsers.extension_of("a.PDF") == "pdf"
    assert parsers.extension_of("archive.tar.gz") == "gz"
    assert parsers.extension_of("noext") == ""


def test_docx_paragraphs_and_tables_are_extracted() -> None:
    docx = pytest.importorskip("docx")

    document = docx.Document()
    document.add_paragraph("Policy overview")
    document.add_paragraph("")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Plan"
    table.rows[0].cells[1].text = "Price"
    buffer = io.BytesIO()
    document.save(buffer)

    parsed = parsers.parse("policy.docx", buffer.getvalue())
    assert "Policy overview" in parsed.text
    assert "Plan | Price" in parsed.text
    assert parsed.pages[0].page is None


def test_corrupt_docx_raises_a_4xx_error() -> None:
    with pytest.raises(InvalidRequestError, match="DOCX"):
        parsers.parse("broken.docx", b"not a zip file")


def test_pdf_pages_keep_their_numbers() -> None:
    fitz = pytest.importorskip("fitz")

    document = fitz.open()
    for index, body in enumerate(["First page body", "Second page body"], start=1):
        page = document.new_page()
        page.insert_text((72, 72), f"{body} {index}")
    data = document.tobytes()
    document.close()

    parsed = parsers.parse("report.pdf", data)
    assert parsed.page_count == 2
    assert [page.page for page in parsed.pages] == [1, 2]
    assert "First page body" in parsed.pages[0].text
    assert "Second page body" in parsed.pages[1].text


def test_corrupt_pdf_raises_a_4xx_error() -> None:
    with pytest.raises(InvalidRequestError, match="PDF"):
        parsers.parse("broken.pdf", b"%PDF-1.4 definitely not a pdf")

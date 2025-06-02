import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
)  # Import for specific exception

from src.entrenai.core.files.file_processor import (
    FileProcessor,
    TxtFileProcessor,
    MarkdownFileProcessor,
    DocxFileProcessor,
    PptxFileProcessor,
    PdfFileProcessor,
    FileProcessingError,  # For type hinting if needed
)


# --- Tests for TxtFileProcessor ---
def test_txt_file_processor_extract_text(tmp_path: Path):
    """Test TxtFileProcessor extracts text correctly."""
    processor = TxtFileProcessor()
    file_content = "Hello, world!\nThis is a test."
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text(file_content, encoding="utf-8")

    extracted_text = processor.extract_text(txt_file)
    assert extracted_text == file_content


def test_txt_file_processor_file_not_found():
    """Test TxtFileProcessor handles file not found."""
    processor = TxtFileProcessor()
    with pytest.raises(FileProcessingError):  # Expecting our custom error
        processor.extract_text(Path("non_existent_file.txt"))


def test_txt_file_processor_can_process():
    processor = TxtFileProcessor()
    assert processor.can_process(Path("test.txt")) is True
    assert processor.can_process(Path("test.TXT")) is True
    assert processor.can_process(Path("test.doc")) is False


def test_txt_file_processor_empty_file(tmp_path: Path):
    """Test TxtFileProcessor with an empty .txt file."""
    processor = TxtFileProcessor()
    empty_txt_file = tmp_path / "empty.txt"
    empty_txt_file.write_text("", encoding="utf-8")

    extracted_text = processor.extract_text(empty_txt_file)
    assert extracted_text == ""


@patch("builtins.open", side_effect=UnicodeDecodeError("mocked error", b"", 0, 0, "mock reason"))
def test_txt_file_processor_unicode_decode_error(mock_open, tmp_path: Path):
    """Test TxtFileProcessor handles UnicodeDecodeError during file read."""
    processor = TxtFileProcessor()
    # The file content/path doesn't matter as open is mocked to fail for all encodings
    test_file = tmp_path / "corrupted.txt"
    test_file.write_text("irrelevant") # File needs to exist for path operations

    with pytest.raises(FileProcessingError, match="No se pudo extraer texto del archivo TXT .* con ninguna codificación"):
        processor.extract_text(test_file)


# --- Tests for MarkdownFileProcessor ---
def test_md_file_processor_extract_text(tmp_path: Path):
    """Test MarkdownFileProcessor extracts text correctly."""
    processor = MarkdownFileProcessor()
    file_content = "# Title\n\nThis is *markdown*."
    md_file = tmp_path / "sample.md"
    md_file.write_text(file_content, encoding="utf-8")

    extracted_text = processor.extract_text(md_file)
    assert extracted_text == file_content


def test_md_file_processor_can_process():
    processor = MarkdownFileProcessor()
    assert processor.can_process(Path("test.md")) is True
    assert processor.can_process(Path("test.markdown")) is True
    assert processor.can_process(Path("test.txt")) is False


def test_md_file_processor_empty_file(tmp_path: Path):
    """Test MarkdownFileProcessor with an empty .md file."""
    processor = MarkdownFileProcessor()
    empty_md_file = tmp_path / "empty.md"
    empty_md_file.write_text("", encoding="utf-8")

    extracted_text = processor.extract_text(empty_md_file)
    assert extracted_text == ""


# --- Tests for Main FileProcessor Class ---
def test_file_processor_registration_and_delegation(tmp_path: Path):
    """Test FileProcessor registers processors and delegates correctly."""
    fp = FileProcessor()  # Registers default processors in __init__

    # Test TXT
    txt_content = "txt test"
    txt_file = tmp_path / "test.txt"
    txt_file.write_text(txt_content)
    assert fp.process_file(txt_file) == txt_content

    # Test MD
    md_content = "md test"
    md_file = tmp_path / "test.md"
    md_file.write_text(md_content)
    assert fp.process_file(md_file) == md_content


def test_file_processor_unsupported_type(tmp_path: Path, caplog):
    """Test FileProcessor handles unsupported file types."""
    fp = FileProcessor()
    xyz_file = tmp_path / "test.xyz"
    xyz_file.touch()

    assert fp.process_file(xyz_file) is None
    assert "No processor registered for file type '.xyz'" in caplog.text


def test_file_processor_file_not_found(caplog):
    """Test FileProcessor handles file not found for processing."""
    fp = FileProcessor()
    assert fp.process_file(Path("non_existent.txt")) is None
    assert "File not found or is not a file: non_existent.txt" in caplog.text


def test_file_processor_handles_sub_processor_error(tmp_path: Path, caplog):
    """Test FileProcessor handles FileProcessingError from a sub-processor."""
    fp = FileProcessor()

    # Mock TxtFileProcessor's extract_text to raise an error
    with patch.object(
        TxtFileProcessor,
        "extract_text",
        side_effect=FileProcessingError("mocked txt error"),
    ):
        # Need to re-register or ensure the mocked instance is used.
        # Easiest is to re-initialize FileProcessor if it creates instances internally,
        # or mock the specific instance if FileProcessor stores them.
        # Since FileProcessor creates instances in _register_default_processors,
        # we need to ensure the mocked TxtFileProcessor is what it uses.
        # This can be tricky. A simpler way for this test might be to mock the
        # get method of fp.processors dict.

        # Alternative: Patch the instance that FileProcessor creates.
        # This requires knowing how FileProcessor stores its processors.
        # Let's assume we can patch the method on the class, and FileProcessor will use it.
        # This works if TxtFileProcessor is instantiated and its method called.

        # Re-initialize FileProcessor to pick up the patched TxtFileProcessor if it re-instantiates
        # However, the patch is on the class, so any new instance will have the mocked method.
        # fp = FileProcessor() # Not strictly needed if patch is on class method

        txt_file = tmp_path / "error_test.txt"
        txt_file.write_text("content")

        assert fp.process_file(txt_file) is None
        assert "File processing failed for" in caplog.text
        assert "mocked txt error" in caplog.text


# --- Placeholder Tests for DOCX, PPTX, PDF (to be filled with mocks) ---


@patch("docx.Document")
def test_docx_file_processor_extract_text(mock_docx_document, tmp_path: Path):
    """Test DocxFileProcessor with mocked python-docx."""
    processor = DocxFileProcessor()
    docx_file = tmp_path / "sample.docx"
    docx_file.touch()  # Just need the file to exist for the path

    # Configure mock Document object
    mock_doc_instance = MagicMock()
    mock_para1 = MagicMock()
    mock_para1.text = "Paragraph 1 text."
    mock_para2 = MagicMock()
    mock_para2.text = "Paragraph 2 text."
    mock_doc_instance.paragraphs = [mock_para1, mock_para2]

    # Mock table
    mock_table = MagicMock()
    mock_row1_cell1 = MagicMock()
    mock_row1_cell1.text = "Table R1C1"
    mock_row1_cell2 = MagicMock()
    mock_row1_cell2.text = "Table R1C2"
    mock_row1 = MagicMock()
    mock_row1.cells = [mock_row1_cell1, mock_row1_cell2]

    mock_row2_cell1 = MagicMock()
    mock_row2_cell1.text = "Table R2C1"
    mock_row2_cell2 = MagicMock()
    mock_row2_cell2.text = "Table R2C2"
    mock_row2 = MagicMock()
    mock_row2.cells = [mock_row2_cell1, mock_row2_cell2]

    mock_table.rows = [mock_row1, mock_row2]
    mock_doc_instance.tables = [mock_table]
    mock_docx_document.return_value = mock_doc_instance

    extracted_text = processor.extract_text(docx_file)
    expected_parts = [
        "Paragraph 1 text.",
        "Paragraph 2 text.",
        "Table R1C1",
        "Table R1C2",
        "Table R2C1",
        "Table R2C2",
    ]
    # The processor joins with "\n\n"
    actual_parts = extracted_text.split("\n\n")
    assert all(part in actual_parts for part in expected_parts)
    assert len(actual_parts) == len(expected_parts) # Ensure no extra parts

    mock_docx_document.assert_called_once_with(str(docx_file))


@patch("docx.Document")
def test_docx_file_processor_empty_file(mock_docx_document, tmp_path: Path):
    """Test DocxFileProcessor with an empty document."""
    processor = DocxFileProcessor()
    empty_docx_file = tmp_path / "empty.docx"
    empty_docx_file.touch()

    mock_doc_instance = MagicMock()
    mock_doc_instance.paragraphs = []
    mock_doc_instance.tables = []
    mock_docx_document.return_value = mock_doc_instance

    extracted_text = processor.extract_text(empty_docx_file)
    assert extracted_text == ""
    mock_docx_document.assert_called_once_with(str(empty_docx_file))


@patch("docx.Document")
def test_docx_file_processor_handles_specific_library_error(mock_docx_document, tmp_path: Path):
    """Test DocxFileProcessor handles specific errors from python-docx like PackageNotFoundError."""
    # Using a more specific error type if available, e.g., PackageNotFoundError
    # from docx.opc.exceptions import PackageNotFoundError
    # For now, using a generic Exception to simulate and ensure it's wrapped.
    # If PackageNotFoundError or similar were readily importable and a common case for corruption:
    # mock_docx_document.side_effect = PackageNotFoundError("mocked package error")
    mock_docx_document.side_effect = Exception("Mocked DOCX corruption error")

    processor = DocxFileProcessor()
    corrupted_docx_file = tmp_path / "corrupted.docx"
    corrupted_docx_file.touch()

    with pytest.raises(FileProcessingError, match="No se pudo extraer texto del DOCX"):
        processor.extract_text(corrupted_docx_file)


@patch("docx.Document", side_effect=ValueError("Another DOCX Load Error")) # Example with ValueError
def test_docx_file_processor_handles_general_library_error(
    mock_docx_document_error, tmp_path: Path
):
    """Test DocxFileProcessor handles various errors from python-docx library."""
    processor = DocxFileProcessor()
    docx_file = tmp_path / "error.docx"
    docx_file.touch()

    with pytest.raises(FileProcessingError, match="No se pudo extraer texto del DOCX"):
        processor.extract_text(docx_file)


# Similar tests would be created for PptxFileProcessor and PdfFileProcessor
# by mocking 'pptx.Presentation', 'pdf2image.convert_from_path', and 'pytesseract.image_to_string'


# Example for Pptx (very basic mock)
@patch("pptx.Presentation")
def test_pptx_file_processor_extract_text(mock_pptx_presentation, tmp_path: Path):
    processor = PptxFileProcessor()
    pptx_file = tmp_path / "sample.pptx"
    pptx_file.touch()

    mock_pres_instance = MagicMock()
    mock_slide = MagicMock()
    # mock_shape1 = MagicMock() # Not used, remove
    # mock_shape1.has_notes_slide = False # Not used, remove
    # mock_shape1.text_frame.paragraphs = []  # Simplified # Not used, remove

    # Simulate a shape with text
    mock_text_shape = MagicMock()
    mock_text_shape.has_text_frame = True
    mock_text_frame = MagicMock()
    mock_paragraph = MagicMock()
    mock_run = MagicMock()
    mock_run.text = "PPTX text content."
    mock_paragraph.runs = [mock_run]
    mock_text_frame.paragraphs = [mock_paragraph]
    mock_text_shape.text_frame = mock_text_frame
    # Simulate a shape with direct text attribute
    mock_direct_text_shape = MagicMock()
    mock_direct_text_shape.has_text_frame = False
    mock_direct_text_shape.text = "Direct shape text."
    # Simulate a shape that is neither (e.g. a picture)
    mock_other_shape = MagicMock()
    mock_other_shape.has_text_frame = False
    mock_other_shape.has_text = False


    mock_slide.shapes = [mock_text_shape, mock_direct_text_shape, mock_other_shape]

    # Mock notes slide
    mock_slide.has_notes_slide = True
    mock_notes_slide = MagicMock()
    mock_notes_text_frame = MagicMock()
    mock_notes_text_frame.text = "This is a note on the slide."
    mock_notes_slide.notes_text_frame = mock_notes_text_frame
    mock_slide.notes_slide = mock_notes_slide


    mock_pres_instance.slides = [mock_slide]
    mock_pptx_presentation.return_value = mock_pres_instance

    extracted_text = processor.extract_text(pptx_file)
    assert "PPTX text content." in extracted_text
    assert "Direct shape text." in extracted_text
    assert "This is a note on the slide." in extracted_text
    mock_pptx_presentation.assert_called_once_with(str(pptx_file))


@patch("pptx.Presentation")
def test_pptx_file_processor_empty_file(mock_pptx_presentation, tmp_path: Path):
    """Test PptxFileProcessor with an empty presentation."""
    processor = PptxFileProcessor()
    empty_pptx_file = tmp_path / "empty.pptx"
    empty_pptx_file.touch()

    mock_pres_instance = MagicMock()
    mock_pres_instance.slides = []  # No slides
    mock_pptx_presentation.return_value = mock_pres_instance

    extracted_text = processor.extract_text(empty_pptx_file)
    assert extracted_text == ""
    mock_pptx_presentation.assert_called_once_with(str(empty_pptx_file))


@patch("pptx.Presentation", side_effect=Exception("PPTX Load Error"))
def test_pptx_file_processor_handles_library_error(mock_pptx_presentation_error, tmp_path: Path):
    """Test PptxFileProcessor handles errors from python-pptx library."""
    processor = PptxFileProcessor()
    pptx_file = tmp_path / "error.pptx"
    pptx_file.touch()

    with pytest.raises(FileProcessingError, match="No se pudo extraer texto del PPTX"):
        processor.extract_text(pptx_file)


# Example for PDF (very basic mock)
@patch("src.entrenai.core.files.file_processor.convert_from_path")
@patch("src.entrenai.core.files.file_processor.pytesseract.image_to_string")
@patch("src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version")
def test_pdf_file_processor_extract_text(
    mock_get_tesseract_version,
    mock_image_to_string,
    mock_convert_from_path,
    tmp_path: Path,
):
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.touch()

    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"
    mock_image_page1 = MagicMock()
    mock_image_page2 = MagicMock()
    mock_convert_from_path.return_value = [mock_image_page1, mock_image_page2]

    mock_image_to_string.side_effect = ["Text from page 1.", "Text from page 2."]

    extracted_text = processor.extract_text(pdf_file)
    expected_text = "Text from page 1.\n\nText from page 2."
    assert extracted_text == expected_text
    mock_convert_from_path.assert_called_once_with(pdf_file)
    assert mock_image_to_string.call_count == 2


@patch("src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version")
@patch("src.entrenai.core.files.file_processor.convert_from_path")
@patch("src.entrenai.core.files.file_processor.pytesseract.image_to_string")
def test_pdf_file_processor_extract_text_mixed_ocr_results(
    mock_image_to_string,
    mock_convert_from_path,
    mock_get_tesseract_version,
    tmp_path: Path,
):
    """Test PdfFileProcessor with mixed success and TesseractError on pages."""
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "mixed_ocr.pdf"
    pdf_file.touch()

    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"
    mock_image_page1 = MagicMock()
    mock_image_page2 = MagicMock()
    mock_image_page3 = MagicMock()
    mock_convert_from_path.return_value = [mock_image_page1, mock_image_page2, mock_image_page3]

    # Simulate success, TesseractError, success
    mock_image_to_string.side_effect = [
        "Text from page 1.",
        pytesseract.TesseractError("mocked page 2 OCR error"),
        "Text from page 3.",
    ]

    extracted_text = processor.extract_text(pdf_file)

    assert "Text from page 1." in extracted_text
    assert "[Error OCR en página 2: mocked page 2 OCR error]" in extracted_text
    assert "Text from page 3." in extracted_text

    expected_text_structure = "Text from page 1.\n\n\n[Error OCR en página 2: mocked page 2 OCR error]\n\n\nText from page 3."
    assert extracted_text == expected_text_structure

    mock_convert_from_path.assert_called_once_with(pdf_file)
    assert mock_image_to_string.call_args_list == [
        ((mock_image_page1,), {"lang": "spa+eng"}),
        ((mock_image_page2,), {"lang": "spa+eng"}),
        ((mock_image_page3,), {"lang": "spa+eng"}),
    ]
    assert mock_image_to_string.call_count == 3


@patch("src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version")
@patch("src.entrenai.core.files.file_processor.convert_from_path")
def test_pdf_file_processor_empty_pdf_no_images(
    mock_convert_from_path, mock_get_tesseract_version, tmp_path: Path
):
    """Test PdfFileProcessor when PDF yields no images (e.g., empty PDF)."""
    processor = PdfFileProcessor()
    empty_pdf_file = tmp_path / "empty.pdf"
    empty_pdf_file.touch()

    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"
    mock_convert_from_path.return_value = []  # No images returned

    extracted_text = processor.extract_text(empty_pdf_file)
    assert extracted_text == ""
    mock_convert_from_path.assert_called_once_with(empty_pdf_file)


@patch("src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version")
@patch("src.entrenai.core.files.file_processor.convert_from_path")
@patch("src.entrenai.core.files.file_processor.pytesseract.image_to_string")
def test_pdf_file_processor_empty_pdf_empty_image_text(
    mock_image_to_string,
    mock_convert_from_path,
    mock_get_tesseract_version,
    tmp_path: Path,
):
    """Test PdfFileProcessor when OCR returns empty string for images."""
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "ocr_empty.pdf"
    pdf_file.touch()

    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"
    mock_image1 = MagicMock()
    mock_convert_from_path.return_value = [mock_image1]
    mock_image_to_string.return_value = ""  # OCR returns empty string

    extracted_text = processor.extract_text(pdf_file)
    assert extracted_text == ""
    mock_convert_from_path.assert_called_once_with(pdf_file)
    mock_image_to_string.assert_called_once_with(mock_image1, lang="spa+eng")


@patch("src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version")
@patch("src.entrenai.core.files.file_processor.convert_from_path", side_effect=Exception("mocked pdf2image error"))
def test_pdf_file_processor_handles_convert_from_path_generic_error(
    mock_convert_from_path, mock_get_tesseract_version, tmp_path: Path
):
    """Test PdfFileProcessor handles generic errors from convert_from_path."""
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "error_convert.pdf"
    pdf_file.touch()
    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"

    with pytest.raises(FileProcessingError, match=f"No se pudo extraer texto del PDF {pdf_file}"):
        processor.extract_text(pdf_file)
    mock_convert_from_path.assert_called_once_with(pdf_file)


@patch("src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version")
@patch("src.entrenai.core.files.file_processor.convert_from_path")
@patch("src.entrenai.core.files.file_processor.pytesseract.image_to_string", side_effect=pytesseract.TesseractError("mocked tesseract page error"))
def test_pdf_file_processor_handles_tesseract_page_error(
    mock_image_to_string,
    mock_convert_from_path,
    mock_get_tesseract_version,
    tmp_path: Path,
):
    """Test PdfFileProcessor handles TesseractError during page processing and includes error in output."""
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "error_page_ocr.pdf"
    pdf_file.touch()

    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"
    mock_image1 = MagicMock()
    mock_convert_from_path.return_value = [mock_image1]

    extracted_text = processor.extract_text(pdf_file)
    assert "[Error OCR en página 1: mocked tesseract page error]" in extracted_text
    mock_convert_from_path.assert_called_once_with(pdf_file)
    mock_image_to_string.assert_called_once_with(mock_image1, lang="spa+eng")


@patch(
    "src.entrenai.core.files.file_processor.convert_from_path",
    side_effect=PDFInfoNotInstalledError("Poppler not found"),
)
@patch("src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version")
def test_pdf_file_processor_handles_poppler_error(
    mock_get_tesseract_version, mock_convert_from_path_error, tmp_path: Path
):
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "error.pdf"
    pdf_file.touch()
    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"

    with pytest.raises(
        FileProcessingError,
        match="Poppler (dependencia para procesamiento de PDF) no instalado",
    ):
        processor.extract_text(pdf_file)


@patch(
    "src.entrenai.core.files.file_processor.pytesseract.get_tesseract_version",
    side_effect=Exception("Tesseract not found"),
)
def test_pdf_file_processor_handles_tesseract_not_found_at_startup(
    mock_get_tesseract_version_error, tmp_path: Path
):
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "error_tess.pdf"
    pdf_file.touch()

    with pytest.raises(
        FileProcessingError, match="Tesseract OCR no está instalado o no se encuentra en el PATH"
    ):
        processor.extract_text(pdf_file)

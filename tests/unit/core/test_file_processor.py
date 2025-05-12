import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from pdf2image.exceptions import PDFInfoNotInstalledError # Import for specific exception

from src.entrenai.core.file_processor import (
    FileProcessor,
    TxtFileProcessor,
    MarkdownFileProcessor,
    DocxFileProcessor,
    PptxFileProcessor,
    PdfFileProcessor,
    FileProcessingError,
    BaseFileProcessor, # For type hinting if needed
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
    with pytest.raises(FileProcessingError): # Expecting our custom error
        processor.extract_text(Path("non_existent_file.txt"))

def test_txt_file_processor_can_process():
    processor = TxtFileProcessor()
    assert processor.can_process(Path("test.txt")) is True
    assert processor.can_process(Path("test.TXT")) is True
    assert processor.can_process(Path("test.doc")) is False

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

# --- Tests for Main FileProcessor Class ---
def test_file_processor_registration_and_delegation(tmp_path: Path):
    """Test FileProcessor registers processors and delegates correctly."""
    fp = FileProcessor() # Registers default processors in __init__
    
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
    with patch.object(TxtFileProcessor, 'extract_text', side_effect=FileProcessingError("mocked txt error")):
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

@patch('docx.Document')
def test_docx_file_processor_extract_text(mock_docx_document, tmp_path: Path):
    """Test DocxFileProcessor with mocked python-docx."""
    processor = DocxFileProcessor()
    docx_file = tmp_path / "sample.docx"
    docx_file.touch() # Just need the file to exist for the path

    # Configure mock Document object
    mock_doc_instance = MagicMock()
    mock_para1 = MagicMock()
    mock_para1.text = "Paragraph 1 text."
    mock_para2 = MagicMock()
    mock_para2.text = "Paragraph 2 text."
    mock_doc_instance.paragraphs = [mock_para1, mock_para2]
    mock_doc_instance.tables = [] # No tables for this simple test
    mock_docx_document.return_value = mock_doc_instance

    extracted_text = processor.extract_text(docx_file)
    expected_text = "Paragraph 1 text.\n\nParagraph 2 text."
    assert extracted_text == expected_text
    mock_docx_document.assert_called_once_with(str(docx_file))

@patch('docx.Document', side_effect=Exception("DOCX Load Error"))
def test_docx_file_processor_handles_library_error(mock_docx_document_error, tmp_path: Path):
    """Test DocxFileProcessor handles errors from python-docx library."""
    processor = DocxFileProcessor()
    docx_file = tmp_path / "error.docx"
    docx_file.touch()

    with pytest.raises(FileProcessingError, match="Failed to extract text from DOCX"):
        processor.extract_text(docx_file)

# Similar tests would be created for PptxFileProcessor and PdfFileProcessor
# by mocking 'pptx.Presentation', 'pdf2image.convert_from_path', and 'pytesseract.image_to_string'

# Example for Pptx (very basic mock)
@patch('pptx.Presentation')
def test_pptx_file_processor_extract_text(mock_pptx_presentation, tmp_path: Path):
    processor = PptxFileProcessor()
    pptx_file = tmp_path / "sample.pptx"
    pptx_file.touch()

    mock_pres_instance = MagicMock()
    mock_slide = MagicMock()
    mock_shape1 = MagicMock()
    mock_shape1.has_notes_slide = False
    mock_shape1.text_frame.paragraphs = [] # Simplified
    
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
    
    mock_slide.shapes = [mock_text_shape]
    mock_slide.has_notes_slide = False # For simplicity
    
    mock_pres_instance.slides = [mock_slide]
    mock_pptx_presentation.return_value = mock_pres_instance

    extracted_text = processor.extract_text(pptx_file)
    assert "PPTX text content." in extracted_text
    mock_pptx_presentation.assert_called_once_with(str(pptx_file))


# Example for PDF (very basic mock)
@patch('src.entrenai.core.file_processor.convert_from_path') # Patch where it's used
@patch('src.entrenai.core.file_processor.pytesseract.image_to_string')
@patch('src.entrenai.core.file_processor.pytesseract.get_tesseract_version') # Mock tesseract check
def test_pdf_file_processor_extract_text(mock_get_tesseract_version, mock_image_to_string, mock_convert_from_path, tmp_path: Path):
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.touch()

    mock_get_tesseract_version.return_value = "mocked tesseract 5.0" # Simulate tesseract is found
    mock_image_page1 = MagicMock() # Simulate a PIL Image object
    mock_image_page2 = MagicMock()
    mock_convert_from_path.return_value = [mock_image_page1, mock_image_page2]
    
    mock_image_to_string.side_effect = ["Text from page 1.", "Text from page 2."]

    extracted_text = processor.extract_text(pdf_file)
    expected_text = "Text from page 1.\n\nText from page 2."
    assert extracted_text == expected_text
    mock_convert_from_path.assert_called_once_with(pdf_file)
    assert mock_image_to_string.call_count == 2

@patch('src.entrenai.core.file_processor.convert_from_path', side_effect=PDFInfoNotInstalledError("Poppler not found"))
@patch('src.entrenai.core.file_processor.pytesseract.get_tesseract_version')
def test_pdf_file_processor_handles_poppler_error(mock_get_tesseract_version, mock_convert_from_path_error, tmp_path: Path):
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "error.pdf"
    pdf_file.touch()
    mock_get_tesseract_version.return_value = "mocked tesseract 5.0"

    with pytest.raises(FileProcessingError, match="Poppler (dependency for PDF processing) not installed"):
        processor.extract_text(pdf_file)

@patch('src.entrenai.core.file_processor.pytesseract.get_tesseract_version', side_effect=Exception("Tesseract not found"))
def test_pdf_file_processor_handles_tesseract_not_found_error(mock_get_tesseract_version_error, tmp_path: Path):
    processor = PdfFileProcessor()
    pdf_file = tmp_path / "error_tess.pdf"
    pdf_file.touch()

    with pytest.raises(FileProcessingError, match="Tesseract OCR is not installed or not found in PATH"):
        processor.extract_text(pdf_file)

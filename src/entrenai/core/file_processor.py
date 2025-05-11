from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict

from src.entrenai.utils.logger import get_logger

# Import specific libraries for file processing later
# For PDF:
# from pdf2image import convert_from_path
# import pytesseract
# For DOCX:
# import docx
# For PPTX:
# from pptx import Presentation

logger = get_logger(__name__)


class FileProcessingError(Exception):
    """Custom exception for file processing errors."""

    pass


class BaseFileProcessor(ABC):
    """
    Abstract base class for file processors.
    Each subclass should handle a specific file type.
    """

    @abstractmethod
    def extract_text(self, file_path: Path) -> str:
        """
        Extracts text content from the given file.
        Should raise FileProcessingError if extraction fails.
        """
        pass

    def can_process(self, file_path: Path) -> bool:
        """
        Checks if this processor can handle the given file type based on extension.
        Subclasses should override this or rely on the main FileProcessor's dispatch.
        """
        # Default implementation, can be overridden by subclasses if they handle multiple extensions
        # or need more complex logic than just checking a list of supported_extensions.
        supported_extensions = getattr(self, "SUPPORTED_EXTENSIONS", [])
        return file_path.suffix.lower() in supported_extensions


class TxtFileProcessor(BaseFileProcessor):
    """Processes plain text (.txt) files."""

    SUPPORTED_EXTENSIONS = [".txt"]

    def extract_text(self, file_path: Path) -> str:
        logger.info(f"Extracting text from TXT file: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error processing TXT file {file_path}: {e}")
            raise FileProcessingError(
                f"Failed to extract text from TXT file {file_path}: {e}"
            ) from e


class MarkdownFileProcessor(BaseFileProcessor):
    """Processes Markdown (.md) files."""

    SUPPORTED_EXTENSIONS = [".md", ".markdown"]

    def extract_text(self, file_path: Path) -> str:
        logger.info(f"Extracting text from Markdown file: {file_path}")
        # For Markdown, the "text" is the Markdown content itself.
        # No complex extraction needed, just read the file.
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error processing Markdown file {file_path}: {e}")
            raise FileProcessingError(
                f"Failed to extract text from Markdown file {file_path}: {e}"
            ) from e


class PdfFileProcessor(BaseFileProcessor):
    """Processes PDF (.pdf) files using OCR if needed."""

    SUPPORTED_EXTENSIONS = [".pdf"]

    def extract_text(self, file_path: Path) -> str:
        logger.info(
            f"Extracting text from PDF file: {file_path} (placeholder - needs implementation)"
        )
        # Placeholder: Actual implementation will use pdf2image and pytesseract
        # This will involve converting PDF pages to images and then OCRing them.
        # Need to handle potential errors, large files, etc.
        # Example (conceptual, needs libraries installed and configured):
        # try:
        #     images = convert_from_path(file_path)
        #     full_text = ""
        #     for i, image in enumerate(images):
        #         logger.debug(f"Processing page {i+1} of PDF {file_path}")
        #         full_text += pytesseract.image_to_string(image) + "\n\n" # Page separator
        #     return full_text
        # except Exception as e:
        #     logger.error(f"Error processing PDF file {file_path} with OCR: {e}")
        #     raise FileProcessingError(f"Failed to extract text from PDF {file_path}: {e}") from e
        raise NotImplementedError("PDF processing with OCR is not yet implemented.")


class DocxFileProcessor(BaseFileProcessor):
    """Processes DOCX (.docx) files."""

    SUPPORTED_EXTENSIONS = [".docx"]

    def extract_text(self, file_path: Path) -> str:
        logger.info(
            f"Extracting text from DOCX file: {file_path} (placeholder - needs implementation)"
        )
        # Placeholder: Actual implementation will use python-docx
        # Example (conceptual, needs library installed):
        # try:
        #     doc = docx.Document(file_path)
        #     full_text = "\n".join([para.text for para in doc.paragraphs])
        #     # Consider extracting text from tables, headers/footers if needed
        #     return full_text
        # except Exception as e:
        #     logger.error(f"Error processing DOCX file {file_path}: {e}")
        #     raise FileProcessingError(f"Failed to extract text from DOCX {file_path}: {e}") from e
        raise NotImplementedError("DOCX processing is not yet implemented.")


class PptxFileProcessor(BaseFileProcessor):
    """Processes PPTX (.pptx) files."""

    SUPPORTED_EXTENSIONS = [".pptx"]

    def extract_text(self, file_path: Path) -> str:
        logger.info(
            f"Extracting text from PPTX file: {file_path} (placeholder - needs implementation)"
        )
        # Placeholder: Actual implementation will use python-pptx
        # Example (conceptual, needs library installed):
        # try:
        #     prs = Presentation(file_path)
        #     full_text = ""
        #     for slide in prs.slides:
        #         for shape in slide.shapes:
        #             if hasattr(shape, "text"):
        #                 full_text += shape.text + "\n"
        #         # Consider notes pages as well: slide.notes_slide.notes_text_frame.text
        #     return full_text
        # except Exception as e:
        #     logger.error(f"Error processing PPTX file {file_path}: {e}")
        #     raise FileProcessingError(f"Failed to extract text from PPTX {file_path}: {e}") from e
        raise NotImplementedError("PPTX processing is not yet implemented.")


class FileProcessor:
    """
    Main class to process files. It delegates to specific processors based on file type.
    """

    def __init__(self):
        self.processors: Dict[str, BaseFileProcessor] = {}
        # Register default processors
        self.register_processor(TxtFileProcessor())
        self.register_processor(MarkdownFileProcessor())
        self.register_processor(PdfFileProcessor())
        self.register_processor(DocxFileProcessor())
        self.register_processor(PptxFileProcessor())
        # Add more processors here as they are implemented

    def register_processor(self, processor: BaseFileProcessor):
        """Registers a file processor for its supported extensions."""
        if hasattr(processor, "SUPPORTED_EXTENSIONS"):
            for ext in getattr(processor, "SUPPORTED_EXTENSIONS", []):
                if ext not in self.processors:
                    self.processors[ext.lower()] = processor
                    logger.info(
                        f"Registered {type(processor).__name__} for extension {ext}"
                    )
                else:
                    logger.warning(
                        f"Processor for extension {ext} already registered. Overwriting with {type(processor).__name__} is not allowed by default."
                    )
        else:
            logger.warning(
                f"Processor {type(processor).__name__} does not have SUPPORTED_EXTENSIONS attribute. Cannot register."
            )

    def process_file(self, file_path: Path) -> Optional[str]:
        """
        Processes a file to extract its text content.
        Returns the extracted text, or None if the file type is not supported or processing fails.
        """
        file_ext = file_path.suffix.lower()
        processor = self.processors.get(file_ext)

        if processor:
            try:
                logger.info(
                    f"Processing file '{file_path}' using {type(processor).__name__}..."
                )
                return processor.extract_text(file_path)
            except FileProcessingError as e:
                logger.error(f"File processing failed for '{file_path}': {e}")
                return None  # Or re-raise, or return a specific error object
            except Exception as e:
                logger.exception(
                    f"Unexpected error during file processing for '{file_path}': {e}"
                )
                return None
        else:
            logger.warning(
                f"No processor registered for file type '{file_ext}' (file: {file_path}). Skipping."
            )
            return None


if __name__ == "__main__":
    # Create dummy files for testing
    test_dir = Path("test_files_temp")
    test_dir.mkdir(exist_ok=True)

    (test_dir / "sample.txt").write_text("This is a simple text file.\nHello world.")
    (test_dir / "sample.md").write_text("# Markdown Header\n\nThis is *markdown*.")
    # For PDF, DOCX, PPTX, actual files would be needed for real tests of those processors
    (test_dir / "sample.pdf").touch()
    (test_dir / "sample.docx").touch()
    (test_dir / "sample.pptx").touch()
    (test_dir / "unsupported.xyz").touch()

    file_processor = FileProcessor()

    for test_file in test_dir.iterdir():
        print(f"\n--- Processing {test_file.name} ---")
        extracted_content = file_processor.process_file(test_file)
        if extracted_content is not None:
            print(
                f"Extracted Content (first 100 chars): {extracted_content[:100].replace(chr(10), ' ')}..."
            )
        else:
            print("Could not extract content or file type not supported.")

    # Clean up dummy files
    import shutil

    shutil.rmtree(test_dir)
    print(f"\nCleaned up test directory: {test_dir}")

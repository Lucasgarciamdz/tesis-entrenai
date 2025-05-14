import ollama
from typing import List, Optional, Any

from src.entrenai.config import OllamaConfig
from src.entrenai.utils.logger import get_logger

logger = get_logger(__name__)

# Common error messages as constants
CLIENT_NOT_INITIALIZED = "Ollama client not initialized."


class OllamaWrapperError(Exception):
    """Custom exception for OllamaWrapper errors."""

    pass


class OllamaWrapper:
    """
    Wrapper for interacting with Ollama API.
    """

    def __init__(self, config: OllamaConfig):
        self.config = config
        self.client: Optional[ollama.Client] = None
        try:
            if config.host:
                self.client = ollama.Client(host=config.host)
                # Test connection by listing local models
                self.client.list()
                logger.info(
                    f"Ollama client initialized and connected to host: {config.host}"
                )
                self._ensure_models_available()  # Check for specific models
            else:
                logger.error(
                    "Ollama host not configured. OllamaWrapper will not be functional."
                )
                raise OllamaWrapperError("Ollama host not configured.")
        except Exception as e:
            logger.error(
                f"Failed to connect or initialize Ollama client at {config.host}: {e}"
            )
            self.client = None
            # raise OllamaWrapperError(f"Failed to initialize Ollama client: {e}") from e

    def _ensure_models_available(self):
        """
        Checks if the configured models are available in Ollama, and logs a warning if not.
        Does not attempt to pull them automatically to avoid long startup times without user consent.
        """
        if not self.client:
            return

        try:
            response = self.client.list()  # Get the ListResponse object

            # Get models from the response object
            available_models = []
            if hasattr(response, "models"):
                available_models = response.models

            # Extract model names - models have a 'model' attribute (not 'name')
            available_model_names = []
            for model in available_models:
                if hasattr(model, "model"):
                    available_model_names.append(model.model)

            required_models = {
                "embedding": self.config.embedding_model,
                "markdown": self.config.markdown_model,
                "qa": self.config.qa_model,
                "context": self.config.context_model,
            }

            for model_type, model_name in required_models.items():
                if not model_name:  # Skip if a model name is not configured
                    logger.info(
                        f"Ollama model for {model_type} is not configured. Skipping check."
                    )
                    continue

                base_model_name = model_name.split(":")[0]

                # Check if any available model starts with the base name
                is_present = any(
                    model.startswith(base_model_name) for model in available_model_names
                )

                if not is_present:
                    logger.warning(
                        f"Ollama model for {model_type} ('{model_name}') "
                        f"not found in available models: {available_model_names}. "
                        f"Please ensure it is pulled using 'ollama pull {model_name}'."
                    )
                else:
                    logger.info(
                        f"Ollama model for {model_type} ('{model_name}') is available."
                    )

        except Exception as e:
            logger.error(f"Error checking available Ollama models: {e}")

    def generate_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Generates an embedding for the given text using the configured embedding model.
        """
        if not self.client:
            logger.error(f"{CLIENT_NOT_INITIALIZED} Cannot generate embedding.")
            raise OllamaWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.embedding_model
        if not model_to_use:
            logger.error("Embedding model name not configured.")
            raise OllamaWrapperError("Embedding model name not configured.")
        try:
            response = self.client.embeddings(model=model_to_use, prompt=text)
            return response["embedding"]
        except Exception as e:
            logger.error(f"Error generating embedding with model '{model_to_use}': {e}")
            raise OllamaWrapperError(f"Failed to generate embedding: {e}") from e

    def generate_chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_message: Optional[str] = None,
        context_chunks: Optional[List[str]] = None,  # For RAG
        stream: bool = False,
    ) -> str:
        """
        Generates a chat completion (response) for a given prompt.
        Can include a system message and context chunks for RAG.
        """
        if not self.client:
            logger.error(f"{CLIENT_NOT_INITIALIZED} Cannot generate chat completion.")
            raise OllamaWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.qa_model
        if not model_to_use:
            logger.error("QA model name not configured.")
            raise OllamaWrapperError("QA model name not configured.")

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})

        if context_chunks:
            context_str = "\n\n".join(context_chunks)
            full_prompt = f"Context:\n{context_str}\n\nQuestion: {prompt}"
            messages.append({"role": "user", "content": full_prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        try:
            if stream:
                logger.warning(
                    "Streaming is not fully implemented in this basic wrapper. Returning full response."
                )
                # Implement streaming in a future version

            response = self.client.chat(
                model=model_to_use, messages=messages, stream=False
            )
            # Handle both dict response and object response with message attribute
            response_content = ""
            if (
                isinstance(response, dict)
                and "message" in response
                and "content" in response["message"]
            ):
                response_content = str(response["message"]["content"])
            elif hasattr(response, "message") and hasattr(response.message, "content"):
                response_content = str(response.message.content)
            else:
                raise OllamaWrapperError("Unexpected response format from Ollama API")

            # Ensure we return a non-empty string
            if not response_content:
                logger.warning("Chat completion returned empty content")
                response_content = ""

            return response_content

        except Exception as e:
            logger.error(
                f"Error generating chat completion with model '{model_to_use}': {e}"
            )
            raise OllamaWrapperError(f"Failed to generate chat completion: {e}") from e

    def _extract_markdown_content(self, response: Any) -> str:
        """
        Extract markdown content from Ollama API response.
        """
        if (
            isinstance(response, dict)
            and "message" in response
            and "content" in response["message"]
        ):
            return str(response["message"]["content"])
        elif hasattr(response, "message"):
            message = getattr(response, "message")
            if hasattr(message, "content"):
                return str(message.content)

        # If we got here, we couldn't extract the content
        raise OllamaWrapperError("Unexpected response format from Ollama API")

    def _save_markdown_to_file(self, markdown_content: str, save_path: str) -> None:
        """
        Save markdown content to a file at the specified path.
        """
        try:
            import os
            from datetime import datetime

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # If save_path is a directory, generate a filename based on timestamp
            if os.path.isdir(save_path):
                filename = f"markdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                full_path = os.path.join(save_path, filename)
            else:
                # Ensure file has .md extension
                if not save_path.endswith(".md"):
                    save_path += ".md"
                full_path = save_path

            # Write content to file
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            logger.info(f"Markdown content saved to {full_path}")
        except Exception as e:
            logger.error(f"Failed to save markdown content to {save_path}: {e}")

    def format_to_markdown(
        self,
        text_content: str,
        model: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> str:
        """
        Converts the given text content to a well-structured Markdown format using an LLM.
        Handles various input formats (plain text, OCR output, etc.) and ensures proper
        markdown structure while preserving the original content's meaning.

        Args:
            text_content: The raw text to convert to markdown
            model: Optional override for the markdown model to use
            save_path: Optional path to save the resulting markdown file. Can be:
                       - A full file path (ending with .md or not)
                       - A directory path (will generate a timestamped filename)
                       - None (default, will not save to file)

        Returns:
            The formatted markdown text
        """
        if not self.client:
            logger.error(f"{CLIENT_NOT_INITIALIZED} Cannot format to Markdown.")
            raise OllamaWrapperError(CLIENT_NOT_INITIALIZED)

        model_to_use = model or self.config.markdown_model
        if not model_to_use:
            logger.error("Markdown formatting model name not configured.")
            raise OllamaWrapperError("Markdown formatting model name not configured.")

        # Preprocess the text to remove any <think> sections
        cleaned_text = self._preprocess_text_content(text_content)

        system_prompt = (
            "You are an expert text formatter specializing in converting raw text to clean Markdown. "
            "Your task is to transform the given content into properly structured Markdown format. Follow these rules strictly:\n\n"
            "1. Maintain the original content's meaning and factual information\n"
            "2. Create appropriate headings and structure based on content hierarchy\n"
            "3. Properly format lists, tables, code blocks, and other elements\n"
            "4. Fix obvious typos and formatting issues while preserving meaning\n"
            "5. DO NOT add any new content, introductions, summaries, or conclusions\n"
            "6. DO NOT include any meta-commentary or notes about the formatting process\n"
            "7. DO NOT include any text enclosed in <think> tags or similar metadata\n"
            "8. ONLY output the properly formatted Markdown content, nothing else\n\n"
            "The goal is clean, well-structured Markdown that accurately represents the original content."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": cleaned_text},
        ]

        try:
            logger.info(f"Formatting text to Markdown using model '{model_to_use}'...")
            response = self.client.chat(
                model=model_to_use, messages=messages, stream=False
            )

            # Extract markdown content from response
            markdown_content = self._extract_markdown_content(response)

            # Post-process the markdown content to ensure it's clean
            markdown_content = self._postprocess_markdown_content(markdown_content)

            if markdown_content:
                logger.info(
                    f"Successfully formatted text to Markdown (length: {len(markdown_content)})."
                )

                # Save to file if a path was provided
                if save_path:
                    self._save_markdown_to_file(markdown_content, save_path)
            else:
                logger.warning("Markdown formatting returned empty content.")
                markdown_content = ""  # Ensure we return a string even if it's empty

            return markdown_content
        except Exception as e:
            logger.error(
                f"Error formatting text to Markdown with model '{model_to_use}': {e}"
            )
            raise OllamaWrapperError(f"Failed to format text to Markdown: {e}") from e

    def _preprocess_text_content(self, text: str) -> str:
        """
        Preprocesses the input text before sending it to the LLM.
        Removes any <think> sections and other unwanted metadata.

        Args:
            text: The raw input text

        Returns:
            Cleaned text ready for markdown conversion
        """
        import re

        # Remove <think>...</think> blocks
        cleaned_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # Remove other common metadata patterns that might appear in OCR or extracted text
        cleaned_text = re.sub(
            r"^\s*\[.*?\]\s*$", "", cleaned_text, flags=re.MULTILINE
        )  # Remove [metadata] lines
        cleaned_text = re.sub(
            r"^\s*#\s*metadata:.*$", "", cleaned_text, flags=re.MULTILINE
        )  # Remove #metadata lines

        return cleaned_text.strip()

    def _postprocess_markdown_content(self, markdown: str) -> str:
        """
        Performs final cleanup on the generated markdown.

        Args:
            markdown: The markdown content returned by the LLM

        Returns:
            Clean, well-formatted markdown
        """
        import re

        # Remove any lingering <think> tags that might have been generated
        cleaned_markdown = re.sub(r"<think>.*?</think>", "", markdown, flags=re.DOTALL)

        # Remove any "I've converted this to markdown..." explanatory text at the beginning
        cleaned_markdown = re.sub(
            r"^.*?(#|---|```)", r"\1", cleaned_markdown, flags=re.DOTALL, count=1
        )

        # Fix common formatting issues
        # Ensure proper spacing after headings
        cleaned_markdown = re.sub(r"(#{1,6}.*?)(\n(?!\n))", r"\1\n\n", cleaned_markdown)

        # Ensure code blocks are properly formatted with newlines
        cleaned_markdown = re.sub(
            r"```(\w*)\n?([^`]+)```", r"```\1\n\2\n```", cleaned_markdown
        )

        return cleaned_markdown.strip()

    # add_context_to_chunk will be handled by EmbeddingManager for now.


if __name__ == "__main__":
    from src.entrenai.config import ollama_config

    if not ollama_config.host:
        print("OLLAMA_HOST must be set in .env for this test.")
    else:
        print(f"Attempting to connect to Ollama at {ollama_config.host}...")
        try:
            ollama_wrapper = OllamaWrapper(config=ollama_config)
            if ollama_wrapper.client:
                print("Ollama client initialized successfully.")

                # Test embedding (ensure embedding_model is configured and pulled)
                if ollama_config.embedding_model:
                    try:
                        print(
                            f"\nGenerating embedding for 'Hello, world!' using {ollama_wrapper.config.embedding_model}..."
                        )
                        embedding = ollama_wrapper.generate_embedding("Hello, world!")
                        print(
                            f"Embedding (first 5 dims): {embedding[:5]}... (Length: {len(embedding)})"
                        )
                    except OllamaWrapperError as e:
                        print(f"Error during embedding test: {e}")
                    except Exception as e:
                        print(f"Unexpected error during embedding test: {e}")
                else:
                    print(
                        "\nSkipping embedding test: OLLAMA_EMBEDDING_MODEL not configured."
                    )

                # Test chat completion (ensure qa_model is configured and pulled)
                if ollama_config.qa_model:
                    try:
                        print(
                            f"\nGenerating chat completion for 'Why is the sky blue?' using {ollama_wrapper.config.qa_model}..."
                        )
                        chat_response = ollama_wrapper.generate_chat_completion(
                            "Why is the sky blue?"
                        )
                        print(f"Chat response: {chat_response}")
                    except OllamaWrapperError as e:
                        print(f"Error during chat completion test: {e}")
                    except Exception as e:
                        print(f"Unexpected error during chat completion test: {e}")
                else:
                    print(
                        "\nSkipping chat completion test: OLLAMA_QA_MODEL not configured."
                    )

                # Test RAG-style chat completion (ensure qa_model is configured and pulled)
                if ollama_config.qa_model:
                    try:
                        print(
                            f"\nGenerating RAG chat completion using {ollama_wrapper.config.qa_model}..."
                        )
                        rag_prompt = "What is the capital of France?"
                        rag_context = [
                            "France is a country in Europe.",
                            "Paris is a famous city known for the Eiffel Tower.",
                        ]
                        rag_response = ollama_wrapper.generate_chat_completion(
                            prompt=rag_prompt,
                            context_chunks=rag_context,
                            system_message="You are a helpful assistant. Answer based on the provided context.",
                        )
                        print(f"RAG Chat response: {rag_response}")
                    except OllamaWrapperError as e:
                        print(f"Error during RAG chat completion test: {e}")
                    except Exception as e:
                        print(f"Unexpected error during RAG chat completion test: {e}")
                else:
                    print(
                        "\nSkipping RAG chat completion test: OLLAMA_QA_MODEL not configured."
                    )

                # Test Markdown formatting (ensure markdown_model is configured and pulled)
                if ollama_config.markdown_model:
                    try:
                        print(
                            f"\nFormatting text to Markdown using {ollama_wrapper.config.markdown_model}..."
                        )
                        sample_text_for_md = "This is a heading.\n\nThis is a paragraph with a list:\n- Item 1\n- Item 2\n\nAnd some **bold** text."

                        # Format and print without saving
                        markdown_output = ollama_wrapper.format_to_markdown(
                            sample_text_for_md
                        )
                        print(f"Markdown output:\n{markdown_output}")

                        # Format and save to file
                        import os

                        save_path = os.path.join(
                            os.path.dirname(
                                os.path.dirname(
                                    os.path.dirname(os.path.abspath(__file__))
                                )
                            ),
                            "data",
                            "markdown",
                        )
                        print(f"\nSaving formatted Markdown to {save_path}...")
                        ollama_wrapper.format_to_markdown(
                            sample_text_for_md, save_path=save_path
                        )
                    except OllamaWrapperError as e:
                        print(f"Error during Markdown formatting test: {e}")
                    except Exception as e:
                        print(f"Unexpected error during Markdown formatting test: {e}")
                else:
                    print(
                        "\nSkipping Markdown formatting test: OLLAMA_MARKDOWN_MODEL not configured."
                    )
            else:
                print(
                    "Failed to initialize Ollama client (client is None). Check logs for errors."
                )
        except OllamaWrapperError as e:
            print(f"OllamaWrapperError during initialization: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during OllamaWrapper test: {e}")

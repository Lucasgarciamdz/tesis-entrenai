import ollama
from typing import List, Optional  # Added Dict, Any

from src.entrenai.config import OllamaConfig
from src.entrenai.utils.logger import get_logger

logger = get_logger(__name__)


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
            available_models_data = self.client.list()  # Store the full response
            available_models = available_models_data.get(
                "models", []
            )  # Safely get models list
            available_model_names = [
                model["name"] for model in available_models if "name" in model
            ]

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
                is_present = any(base_model_name in an for an in available_model_names)

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
            logger.error("Ollama client not initialized. Cannot generate embedding.")
            raise OllamaWrapperError("Ollama client not initialized.")

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
            logger.error(
                "Ollama client not initialized. Cannot generate chat completion."
            )
            raise OllamaWrapperError("Ollama client not initialized.")

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
                # This part would need to accumulate chunks from the stream
                # response_stream = self.client.chat(model=model_to_use, messages=messages, stream=True)
                # full_response_content = ""
                # for chunk in response_stream:
                #     if 'message' in chunk and 'content' in chunk['message']:
                #         full_response_content += chunk['message']['content']
                # return full_response_content
                pass

            response = self.client.chat(
                model=model_to_use, messages=messages, stream=False
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(
                f"Error generating chat completion with model '{model_to_use}': {e}"
            )
            raise OllamaWrapperError(f"Failed to generate chat completion: {e}") from e

    def format_to_markdown(self, text_content: str, model: Optional[str] = None) -> str:
        """
        Converts the given text content to a well-structured Markdown format using an LLM.
        """
        if not self.client:
            logger.error("Ollama client not initialized. Cannot format to Markdown.")
            raise OllamaWrapperError("Ollama client not initialized.")

        model_to_use = model or self.config.markdown_model
        if not model_to_use:
            logger.error("Markdown formatting model name not configured.")
            raise OllamaWrapperError("Markdown formatting model name not configured.")

        system_prompt = (
            "You are an expert text processing assistant. Your task is to convert the given text content "
            "into a clean, well-structured Markdown format. "
            "Preserve all factual information, lists, headings, and code blocks if present. "
            "Ensure the Markdown is readable and accurately represents the original content structure. "
            "Do not add any introductory phrases, summaries, or comments that are not part of the original text. "
            "Output only the Markdown content."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text_content},
        ]

        try:
            logger.info(f"Formatting text to Markdown using model '{model_to_use}'...")
            response = self.client.chat(
                model=model_to_use, messages=messages, stream=False
            )
            markdown_content = response["message"]["content"]
            logger.info(
                f"Successfully formatted text to Markdown (length: {len(markdown_content)})."
            )
            return markdown_content
        except Exception as e:
            logger.error(
                f"Error formatting text to Markdown with model '{model_to_use}': {e}"
            )
            raise OllamaWrapperError(f"Failed to format text to Markdown: {e}") from e

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
                        markdown_output = ollama_wrapper.format_to_markdown(
                            sample_text_for_md
                        )
                        print(f"Markdown output:\n{markdown_output}")
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

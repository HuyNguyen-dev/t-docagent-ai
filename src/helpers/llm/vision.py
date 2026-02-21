from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_core.runnables import RunnableSequence
from pydantic import BaseModel

from helpers.llm.chat import LLMService
from utils.logger.custom_logging import LoggerMixin


class VisionLLMService(LoggerMixin):
    """A generic service for handling vision-based LLM calls.

    This service is designed to be reusable across different use cases that require
    vision capabilities. It handles the common functionality of:
    - Creating prompts with image placeholders
    - Managing the LLM chain
    - Processing images and text inputs
    """

    def __init__(
        self,
        **kwargs: dict[str, Any],
    ) -> None:
        """Initialize the vision service.

        Args:
            system_message: The system message to use for the LLM
            model_name: The name of the model to use (defaults to Gemini 2.5 Flash)
        """
        self.model_name = kwargs.pop("llm_name", "")
        self.llm = LLMService(self.model_name).create_llm(
            is_default=False,
            **kwargs,
        )
        super().__init__()

    def _create_prompt_template(self, system_message: str, num_images: int, is_pdf: bool) -> ChatPromptTemplate:
        """Create a prompt template with the exact number of image placeholders needed.

        Args:
            system_message: The system message to use for the LLM
            num_images: Number of images to include in the template
            is_pdf: Whether the input is a PDF file (default: True)

        Returns:
            ChatPromptTemplate configured for the specified number of images
        """

        def create_pdf_part(i: int) -> dict:
            return {
                "type": "file",
                "file": {
                    "file_data": f"data:application/pdf;base64,{{image_data_{i}}}",
                    "filename": f"document_{i}.pdf",
                },
            }

        def create_image_part(i: int) -> dict:
            return {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{{image_data_{i}}}"},
            }

        # Create parts based on file type
        parts = [create_pdf_part(i) if is_pdf else create_image_part(i) for i in range(num_images)]

        return ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(system_message),
                HumanMessagePromptTemplate.from_template(
                    [
                        {
                            "type": "text",
                            "text": "This is the provided PDF document" if is_pdf else "These are the provided images",
                        },
                        *parts,
                    ],
                ),
            ],
        )

    async def acall(
        self,
        system_message: str,
        base64_images: list[str],
        output_parser: type[BaseModel],
        is_pdf: bool,
        **kwargs: dict[str, Any],
    ) -> BaseModel:
        """Make an async call to the vision model.

        Args:
            system_message: The formatted system message to send to the model
            base64_images: List of base64-encoded image strings
            output_parser: The Pydantic model class to parse the output into
            **kwargs: Additional arguments to pass to the model

        Returns:
            The parsed output as an instance of the specified output parser type
        """
        # Create a structured output parser for the Pydantic model
        pydantic_parser = PydanticOutputParser(pydantic_object=output_parser)

        # Create a prompt template with the exact number of images
        chain = RunnableSequence(
            self._create_prompt_template(
                system_message=system_message,
                num_images=len(base64_images),
                is_pdf=is_pdf,
            ),
            self.llm,
            pydantic_parser,
        ).with_retry(stop_after_attempt=2)
        # Create a dictionary with image data for each image
        invoke_params = {
            **kwargs,
        }
        for i, base64_img in enumerate(base64_images):
            invoke_params[f"image_data_{i}"] = base64_img

        return await chain.ainvoke(invoke_params)

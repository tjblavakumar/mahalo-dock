"""Custom LangChain chat model for 1min.ai API."""

import json
import logging
from typing import Any, Iterator, List, Optional

import httpx
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

logger = logging.getLogger(__name__)


class OneMinAIChatModel(BaseChatModel):
    """Custom chat model that uses 1min.ai's Chat with AI API."""

    api_key: str
    base_url: str = "https://api.1min.ai"
    model: str = "gpt-4o"
    temperature: float = 0.1

    @property
    def _llm_type(self) -> str:
        return "onemin-ai"

    def _convert_messages_to_prompt(self, messages: List[BaseMessage]) -> tuple[str, str]:
        """Convert LangChain messages to a single prompt string and system message."""
        system_message = ""
        conversation_parts = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_message = msg.content
            elif isinstance(msg, HumanMessage):
                conversation_parts.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                conversation_parts.append(f"Assistant: {msg.content}")

        # Build the full prompt with system context
        prompt_parts = []
        if system_message:
            prompt_parts.append(f"[System Instructions]\n{system_message}\n")
        if conversation_parts:
            prompt_parts.append("\n".join(conversation_parts))

        full_prompt = "\n".join(prompt_parts)
        return full_prompt, system_message

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Call 1min.ai API and return the response."""
        prompt, _ = self._convert_messages_to_prompt(messages)

        # Build request payload
        payload = {
            "type": "UNIFY_CHAT_WITH_AI",
            "model": self.model,
            "promptObject": {
                "prompt": prompt,
            },
        }

        headers = {
            "Content-Type": "application/json",
            "API-KEY": self.api_key,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/api/chat-with-ai",
                    headers=headers,
                    json=payload,
                )

            if response.status_code != 200:
                error_msg = f"1min.ai API error ({response.status_code}): {response.text[:500]}"
                logger.error(error_msg)
                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content=f"Error: {error_msg}"))]
                )

            data = response.json()
            ai_record = data.get("aiRecord", {})
            record_detail = ai_record.get("aiRecordDetail", {})
            result_object = record_detail.get("resultObject", [])

            # resultObject is a list of strings
            content = "\n".join(result_object) if result_object else "No response received."

            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=content))]
            )

        except httpx.TimeoutException:
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="Error: Request to 1min.ai timed out."))]
            )
        except Exception as e:
            logger.error(f"1min.ai API call failed: {e}")
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=f"Error: {str(e)}"))]
            )

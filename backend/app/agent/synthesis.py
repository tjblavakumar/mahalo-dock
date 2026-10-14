"""Synthesis provider: phrases the final user-facing response from the
orchestrator's tool results.

The orchestrator (OpenAI, tool-calling) decides *what* data to fetch. Synthesis
decides *how* to phrase the final answer, and its provider is switchable via
SYNTHESIS_PROVIDER (onemin | openai). This keeps a clear separation between the
reasoning brain and the presentation layer.
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm_factory import build_synthesis_llm
from app.agent.markup_utils import clean_tool_markup

logger = logging.getLogger(__name__)


def synthesize_response(
    user_message: str,
    orchestrator_answer: str,
    role: str,
    system_prompt: Optional[str] = None,
) -> str:
    """Re-phrase the orchestrator's answer using the synthesis provider.

    Returns the synthesized text, or the original orchestrator answer if
    synthesis fails for any reason (so the demo never dead-ends).
    """
    cleaned_input = clean_tool_markup(orchestrator_answer)
    if not cleaned_input:
        return orchestrator_answer

    try:
        llm = build_synthesis_llm(temperature=0.2)
        instruction = (
            f"You are MAHALO3, an AI assistant for a {role.replace('_', ' ')}. "
            f"Your role is purely to synthesize and rephrase the provided answer into a clean, "
            f"well-formatted summary tailored to the user's question.\n"
            f"IMPORTANT: Do NOT call any tools, do not output any tool calling markup (such as <｜｜DSML... or <tool_call>), "
            f"and do not search for new data. Use only the provided information.\n"
            f"Preserve all facts, project keys, IDs, numbers, and links exactly; do not invent new data.\n\n"
            f"For grouped deployment or project summaries, use clear Markdown headings and bullet lists instead of tables. "
            f"Keep each bullet and heading on its own line; never collapse multiple rows or bullets onto one line.\n\n"
            f"User question: {user_message}\n\n"
            f"Answer to refine:\n{cleaned_input}"
        )
        messages = []
        if system_prompt:
            clean_sys_prompt = (
                f"{system_prompt}\n\n"
                "Note: You are formatting the final answer. Do NOT invoke tools or output tool call tags."
            )
            messages.append(SystemMessage(content=clean_sys_prompt))
        messages.append(HumanMessage(content=instruction))

        result = llm.invoke(messages)
        content = getattr(result, "content", None)
        if content and content.strip():
            cleaned_output = clean_tool_markup(content)
            if cleaned_output:
                return cleaned_output
        logger.warning("Synthesis returned empty content; using orchestrator answer.")
    except Exception as e:  # noqa: BLE001 - never fail the request on synthesis
        logger.warning("Synthesis failed (%s); using orchestrator answer.", e)
    return cleaned_input

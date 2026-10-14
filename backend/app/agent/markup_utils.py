"""Utility functions for parsing tool calls from text markup and sanitizing responses."""

import json
import logging
import re
import uuid

logger = logging.getLogger(__name__)


def parse_text_tool_calls(text: str) -> list[dict]:
    """Parse tool invocations from DSML, XML, or JSON tags in LLM text output.

    Handles formats such as:
    - <｜｜DSML｜｜invoke name="tool_name"><｜｜DSML｜｜parameter name="k">v</...parameter></...invoke>
    - <invoke name="tool_name">...</invoke>
    - <tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>
    """
    calls: list[dict] = []
    if not text:
        return calls

    # Match DSML / XML invoke blocks: <...invoke name="tool_name">...</...invoke>
    invoke_pattern = re.compile(
        r"<[^>]*?invoke\s+name=[\"']([^\"']+)[\"'][^>]*>(.*?)(?:</[^>]*?invoke>|(?=<[^>]*?invoke)|(?=</[^>]*?tool_calls>)|$)",
        re.DOTALL | re.IGNORECASE,
    )

    for match in invoke_pattern.finditer(text):
        tool_name = match.group(1).strip()
        body = match.group(2).strip()
        args: dict = {}

        if body:
            # Check for parameter tags
            param_pattern = re.compile(
                r"<[^>]*?parameter\s+name=[\"']([^\"']+)[\"'][^>]*>(.*?)(?:</[^>]*?parameter>|(?=<[^>]*?parameter)|$)",
                re.DOTALL | re.IGNORECASE,
            )
            params = param_pattern.findall(body)
            if params:
                for p_name, p_val in params:
                    p_val_clean = p_val.strip()
                    try:
                        args[p_name] = json.loads(p_val_clean)
                    except Exception:
                        args[p_name] = p_val_clean
            else:
                try:
                    parsed_body = json.loads(body)
                    if isinstance(parsed_body, dict):
                        args = parsed_body
                except Exception:
                    pass

        calls.append({
            "name": tool_name,
            "args": args,
            "id": f"call_{uuid.uuid4().hex[:8]}",
        })

    # Also check JSON tool_call blocks: <tool_call>{"name": ..., "arguments": ...}</tool_call>
    json_tc_pattern = re.compile(
        r"<[^>]*?tool_call[^>]*>\s*(\{.*?\})\s*</[^>]*?tool_call>",
        re.DOTALL | re.IGNORECASE,
    )
    for match in json_tc_pattern.finditer(text):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict) and "name" in data:
                calls.append({
                    "name": str(data["name"]),
                    "args": data.get("arguments", data.get("args", {})),
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                })
        except Exception:
            pass

    return calls


def clean_tool_markup(text: str) -> str:
    """Strip raw DSML, XML tool call tags, and parameter tags from user-facing text."""
    if not text:
        return ""

    # Remove full DSML/XML tool_calls blocks
    cleaned = re.sub(
        r"<[^>]*?tool_calls[^>]*>.*?</[^>]*?tool_calls[^>]*>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove remaining open/close DSML/invoke/tool_call/parameter tags
    cleaned = re.sub(
        r"<[^>]*?(?:invoke|parameter|tool_calls|tool_call)[^>]*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"</[^>]*?(?:invoke|parameter|tool_calls|tool_call)>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Clean any leftover empty lines or dangling tags
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

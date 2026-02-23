"""
Process response.json to extract tool call pairs (inputs and outputs).

This module provides functionality to parse the content array from a response.json file
and extract tool call information, pairing each tool invocation with its corresponding result.
"""

import json
from typing import List, Dict, Tuple, Any


def process_response_content(content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process the content array to extract tool call pairs grouped by thinking blocks.
    
    Logic:
    1. Identify positions of all "thinking" elements
    2. Between consecutive "thinking" elements (or from last thinking to end),
       extract tool calls
    3. Each tool call consists of two elements:
       - One with "id" property (input to the tool)
       - One with "tool_use_id" property matching the "id" (output from the tool)
    4. Group tool calls under their preceding thinking element
    
    Args:
        content: List of content elements from response.json
        
    Returns:
        List of dictionaries, each containing:
        - 'thinking': The thinking element text
        - 'tool_calls': List of tool call pairs that followed this thinking element
    """
    # Step 1: Find all positions of "thinking" elements
    thinking_positions = []
    for i, element in enumerate(content):
        if element.get("type") == "thinking":
            thinking_positions.append(i)
    
    # Step 2: Process each thinking block and its associated tool calls
    result = []
    
    for i in range(len(thinking_positions)):
        thinking_pos = thinking_positions[i]
        thinking_element = content[thinking_pos]
        
        # Define the segment after this thinking element
        start = thinking_pos + 1
        end = thinking_positions[i + 1] if i + 1 < len(thinking_positions) else len(content)
        segment = content[start:end]
        
        # Collect all elements with "id" (tool inputs) in this segment
        tool_inputs = {}
        for element in segment:
            if "id" in element and element.get("type") in ["cypher_template_tool_use", "tool_use"]:
                tool_id = element["id"]
                tool_inputs[tool_id] = element
        
        # Find matching outputs for each input
        tool_call_pairs = []
        for element in segment:
            if "tool_use_id" in element:
                tool_use_id = element["tool_use_id"]
                if tool_use_id in tool_inputs:
                    tool_input = tool_inputs[tool_use_id]
                    tool_call_pairs.append({
                        "input": tool_input,
                        "output": element,
                        "tool_name": tool_input.get("name", "unknown"),
                        "tool_id": tool_use_id
                    })
        
        # Add this thinking block and its tool calls to the result
        result.append({
            "thinking": thinking_element.get("thinking", ""),
            "tool_calls": tool_call_pairs
        })
    
    return result


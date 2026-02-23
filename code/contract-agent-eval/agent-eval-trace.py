#!/usr/bin/env python
"""
Contract Agent Evaluation with Opik Traces

Combines agent-eval.py (dataset, auth, multi-threaded evaluation, retries) with
trace_simple.py trace style. Uses @track-decorated methods for thinking blocks and tool calls so they
show as separate spans in Opik.
Uses thread_id so each question maps to an Opik Thread (conversation).
"""

import os
import json
from contextvars import ContextVar
from opik import track, opik_context
import uuid
import httpx
import opik
import argparse
import time
import threading
from opik import Opik
from opik.evaluation.metrics import AnswerRelevance, Usefulness, Hallucination
from opik.evaluation import evaluate
from dotenv import load_dotenv
from process_response import process_response_content
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Configuration
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
ENDPOINT_URL = os.getenv("ENDPOINT_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Get the bearer token once at module load
def get_bearer_token() -> str:
    """Get OAuth bearer token from Neo4j"""
    auth_url = "https://api.neo4j.io/oauth/token"
    response = httpx.post(
        auth_url,
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials"},
        timeout=30.0
    )
    response.raise_for_status()
    token_data = response.json()
    return token_data.get("access_token")


BEARER_TOKEN = get_bearer_token()

# Global rate limiting (same as agent-eval.py)
rate_limit_count = 0
request_lock = threading.Lock()
last_request_time = 0
MIN_REQUEST_INTERVAL = 2.0  # Minimum 2 seconds between requests


def extract_agent_response_text(payload: Dict[str, Any]) -> str:
    """Extract concatenated text from agent response content array."""
    content = payload.get("content", [])
    parts: List[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "".join(parts).strip()


# Context for current thinking block so @track only sees thinking_text (index, final_answer, trace, etc. in context)
_thinking_block_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "_thinking_block_ctx", default=None
)


@track
def _record_thinking_block(thinking_text: str) -> None:
    """Record one thinking block in Opik. Only thinking_text is passed so span input is just {'thinking_text': ...}; index, final_answer, trace/tool_calls/times come from context."""
    opik_context.update_current_span(input={"thinking_text": thinking_text})

    ctx = _thinking_block_ctx.get()
    if ctx is None:
        return
    trace = ctx["trace"]
    tool_calls = ctx["tool_calls"]
    start_time = ctx["start_time"]
    end_time = ctx["end_time"]
    index = ctx["index"]
    final_answer = ctx.get("final_answer")

    thinking_span = trace.span(
        name=f"thinking-block-{index}",
        type="general",
        start_time=start_time,
        end_time=end_time,
        input={"thinking": thinking_text},
    )
    try:
        for tool_call in tool_calls:
            _record_tool_call_span(thinking_span, tool_call, start_time, end_time)
    finally:
        thinking_span.end()
        if final_answer is not None:
            opik_context.update_current_span(output={"answer": final_answer})
        opik_context.update_current_span(input={"thinking_text": thinking_text})


def _tool_call_span_input(
    tool_call: Dict[str, Any],
    start_time: datetime,
    end_time: datetime,
) -> Dict[str, Any]:
    """Build the tool call span input with only tool_call.input, tool_call.tool_name, start_time, end_time."""
    return {
        "tool_call": {
            "input": tool_call.get("input", {}),
            "tool_name": tool_call.get("tool_name", ""),
        },
        "start_time": start_time.isoformat() if hasattr(start_time, "isoformat") else str(start_time),
        "end_time": end_time.isoformat() if hasattr(end_time, "isoformat") else str(end_time),
    }


@track
def _record_tool_call_span(
    parent_span: Any,
    tool_call: Dict[str, Any],
    start_time: datetime,
    end_time: datetime,
) -> None:
    """Record one tool call span. Override @track input to only tool_call.input, tool_call.tool_name, start_time, end_time."""
    span_input = _tool_call_span_input(tool_call, start_time, end_time)
    opik_context.update_current_span(input=span_input, output={"output": tool_call.get("output", {})})

    tool_call_span = parent_span.span(
        name=f"tool-call-{tool_call.get('tool_name', '')}",
        type="tool",
        provider="neo4j",
        model="neo4j-aura-agent",
        start_time=start_time,
        end_time=end_time,
        input={"input": tool_call.get("input", {})},
        output={"output": tool_call.get("output", {})},
    )
    try:
        tool_call_span.end()
    finally:
        opik_context.update_current_span(input=span_input, output={"output": tool_call.get("output", {})})


@track
def call_contract_agent_with_trace(
    messages: List[Dict[str, Any]],
    thread_id: str,
    client: Opik,
) -> str:
    """
    Call the contract agent endpoint, then build an Opik trace from the response JSON.

    Uses @track-decorated methods for thinking blocks and tool calls so they
    show as separate spans in Opik.

    Args:
        messages: List of message dicts (e.g. [{"role": "user", "content": "..."}])
        thread_id: Unique id for this conversation (Opik Thread)
        client: Opik client for creating trace and spans

    Returns:
        The answer text from the contract agent (for evaluation scoring)
    """
    global rate_limit_count, last_request_time
    max_retries = 5
    base_delay = 2.0

    with request_lock:
        current_time = time.time()
        time_since_last_request = current_time - last_request_time
        if time_since_last_request < MIN_REQUEST_INTERVAL:
            sleep_time = MIN_REQUEST_INTERVAL - time_since_last_request
            print(f"Throttling request. Waiting {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
        last_request_time = time.time()

    start_time = datetime.now()
    full_response: Dict[str, Any] = {}

    for attempt in range(max_retries):
        try:
            response = httpx.post(
                ENDPOINT_URL,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {BEARER_TOKEN}"
                },
                json={"input": messages},
                timeout=300.0
            )
            response.raise_for_status()
            full_response = response.json()
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                rate_limit_count += 1
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"Rate limit hit (429 #{rate_limit_count}). Retrying in {delay:.1f} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    print(f"Rate limit hit (429 #{rate_limit_count}). Max retries reached.")
                    raise
            else:
                raise

    end_time = datetime.now()
    extracted_text = extract_agent_response_text(full_response)
    usage = full_response.get("usage", {})

    trace = client.trace(
        name="contract-agent-query",
        project_name="contract-agent-eval",
        start_time=start_time,
        end_time=end_time,
        input={"messages": messages},
        output={"answer": extracted_text},
        metadata={
            "prompt_tokens": usage.get("request_tokens", 0),
            "completion_tokens": usage.get("response_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        thread_id=thread_id,
    )

    content = full_response.get("content", [])
    agent_response_blocks = process_response_content(content)

    num_blocks = len(agent_response_blocks)
    for i, block in enumerate(agent_response_blocks):
        is_last_block = i == num_blocks - 1
        _thinking_block_ctx.set({
            "trace": trace,
            "tool_calls": block.get("tool_calls", []),
            "start_time": start_time,
            "end_time": end_time,
            "index": i,
            "final_answer": extracted_text if is_last_block else None,
        })
        try:
            _record_thinking_block(block.get("thinking", ""))
        finally:
            _thinking_block_ctx.set(None)

    trace.end()
    return extracted_text


def load_dataset_items(file_path: str) -> List[Dict[str, Any]]:
    """Load dataset items from a JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate contract agent with Opik traces")
    parser.add_argument(
        "--task-threads",
        type=int,
        default=16,
        help="Number of concurrent threads for task execution (default: 16)"
    )
    args = parser.parse_args()

    # Initialize the Opik client
    client = Opik(api_key=OPENAI_API_KEY)

    # Get or create the dataset
    dataset = client.get_or_create_dataset(name="Aura Agent Evaluation Dataset")

    # If dataset is empty in Opik, load items from aura-agent-evaluation-dataset.json
    if not dataset.get_items(nb_samples=1):
        evaluation_dataset_path = os.path.join(os.path.dirname(__file__), "aura-agent-evaluation-dataset.json")
        if os.path.isfile(evaluation_dataset_path):
            dataset_items = load_dataset_items(evaluation_dataset_path)
            dataset.insert(dataset_items)

    # Create the evaluation metrics
    answer_relevance_metric = AnswerRelevance(require_context=False)
    usefulness_metric = Usefulness()
    hallucination_metric = Hallucination()


    # One thread_id per dataset item so each question maps to one Opik Thread
    def agent_evaluation_task(x: Dict[str, Any]) -> Dict[str, str]:
        thread_id = str(uuid.uuid4())
        output_text = call_contract_agent_with_trace(
            messages=x["input"],
            thread_id=thread_id,
            client=client,
        )
        return {"output": output_text}

    evaluation = evaluate(
        dataset=dataset,
        task=agent_evaluation_task,
        scoring_metrics=[answer_relevance_metric, usefulness_metric, hallucination_metric],
        experiment_config={
            "aura_agent_endpoint": ENDPOINT_URL,
            "aura_agent_prompt":"Use your Aura Agent prompt here",
            "aura_agent_tools":"describe tools available to the agent"
        },
        #nb_samples=2, # Uncomment this to evaluate on a subset of the dataset
        project_name="contract-agent-eval",
        task_threads=args.task_threads,
    )

    client.flush()

    print(f"\n{'='*60}")
    print(f"Total 429 (Rate Limit) errors encountered: {rate_limit_count}")
    print(f"{'='*60}")

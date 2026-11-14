"""The agent loop: Gemini picks tools, the code runs them, until Gemini calls reply."""

import json
import logging
from dataclasses import dataclass, field

import httpx
from google import genai

from app import config, prompt, tools

MAX_LLM_CALLS = 6
LLM_ATTEMPTS = 2
MAX_DATA_ROWS = 100
THINKING_LEVEL = "low"
LLM_TIMEOUT_SECONDS = 60
ERROR_ANSWER = "Si è verificato un errore, riprova. / Something went wrong, please try again."

log = logging.getLogger(__name__)


@dataclass
class AgentResult:
    answer: str = ERROR_ANSWER
    status: str = "error"
    data: list[dict] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def run(message: str, history: list[tuple[str, str]] = (), client=None, model: str | None = None) -> AgentResult:
    """Answers one message. `history` holds earlier (question, answer) pairs of the same conversation."""
    model = model or config.LLM_MODEL
    result = AgentResult()
    steps = []
    for question, answer in history:
        steps += [_text_step("user_input", question), _text_step("model_output", answer)]
    steps.append(_text_step("user_input", message))

    try:
        client = client or genai.Client(api_key=config.LLM_API_KEY)
        for call_number in range(1, MAX_LLM_CALLS + 1):
            # On the last call the model may only reply, so every request ends with an answer
            allowed = [tools.REPLY] if call_number == MAX_LLM_CALLS else [d["name"] for d in tools.declarations()]
            interaction = _create(
                client,
                model=model,
                input=steps,
                system_instruction=prompt.system_instruction() + prompt.language_hint(message),
                tools=tools.declarations(),
                generation_config={
                    "thinking_level": THINKING_LEVEL,
                    "tool_choice": {"allowed_tools": {"mode": "any", "tools": allowed}},
                },
                store=False,
                timeout=LLM_TIMEOUT_SECONDS,
            )
            _add_usage(result, interaction.usage)
            model_steps = interaction.steps or []
            # Stateless mode: model steps, thoughts included, are sent back exactly as received
            steps += [s.model_dump() for s in model_steps]
            calls = [s for s in model_steps if s.type == "function_call"]

            if len(calls) == 1 and calls[0].name == tools.REPLY:
                status = calls[0].arguments.get("status")
                result.status = status if status in tools.STATUSES else "answered"
                result.answer = calls[0].arguments.get("answer") or ERROR_ANSWER
                return result
            if not calls:
                steps.append(_text_step("user_input", "Use the tools, and finish with the reply tool."))
            for call in calls:
                if call.name == tools.REPLY:
                    output = {"error": "Call reply alone, after reading the results of the other tools."}
                else:
                    output = tools.execute(call.name, call.arguments)
                    _collect(result, output)
                steps.append(_function_result(call, output))
    except Exception:
        log.exception("Agent run failed")
    result.status, result.answer = "error", ERROR_ANSWER
    return result


def _create(client, **request):
    # The SDK retries 429, 5xx and network errors but not a dropped connection; with store=False resending is safe
    for attempt in range(1, LLM_ATTEMPTS + 1):
        try:
            return client.interactions.create(**request)
        except Exception as error:
            if attempt == LLM_ATTEMPTS or not isinstance(error.__cause__, httpx.RemoteProtocolError):
                raise
            log.warning("Gemini dropped the connection, sending the request again")


def _text_step(step_type: str, text: str) -> dict:
    return {"type": step_type, "content": [{"type": "text", "text": text}]}


def _function_result(call, output: dict) -> dict:
    return {
        "type": "function_result",
        "name": call.name,
        "call_id": call.id,
        "result": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, default=str)}],
    }


def _add_usage(result: AgentResult, usage) -> None:
    result.llm_calls += 1
    if usage is None:
        return
    result.input_tokens += usage.total_input_tokens or 0
    # Thinking tokens are billed as output tokens
    result.output_tokens += (usage.total_output_tokens or 0) + (usage.total_thought_tokens or 0)


def _collect(result: AgentResult, output: dict) -> None:
    if "sql" in output:
        result.queries.append(output["sql"])
    room = MAX_DATA_ROWS - len(result.data)
    result.data += output.get("rows", [])[:room]

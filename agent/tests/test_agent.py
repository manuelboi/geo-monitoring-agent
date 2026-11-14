"""The agent loop, driven by a scripted Gemini client: no network calls, no cost."""

from types import SimpleNamespace

import httpx
import pytest
from google.genai.interactions import FunctionCallStep, Usage

from app import agent
from app.memory import ConversationMemory


def call(tool: str, **arguments) -> FunctionCallStep:
    return FunctionCallStep(type="function_call", id=f"call-{tool}", name=tool, arguments=arguments)


def turn(*steps) -> SimpleNamespace:
    usage = Usage(total_input_tokens=100, total_output_tokens=10, total_thought_tokens=5)
    return SimpleNamespace(steps=list(steps), usage=usage)


def dropped_connection() -> Exception:
    # The SDK wraps the httpx error, as in the evaluation logs
    error = RuntimeError("Server disconnected without sending a response.")
    error.__cause__ = httpx.RemoteProtocolError("Server disconnected without sending a response.")
    return error


class ScriptedClient:
    """Returns the scripted turns in order, raising the ones that are exceptions, and records every request."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests = []
        self.interactions = self

    def create(self, **request):
        # A snapshot, as the real SDK serialises the input when the request is sent
        self.requests.append({**request, "input": list(request["input"])})
        if not self.turns:
            raise RuntimeError("Gemini unavailable")
        next_turn = self.turns.pop(0)
        if isinstance(next_turn, Exception):
            raise next_turn
        return next_turn


def test_off_topic_question_costs_one_call():
    client = ScriptedClient(turn(call("reply", status="out_of_scope", answer="Posso rispondere solo sui dati GEO.")))
    result = agent.run("Che tempo fa a Milano?", client=client)
    assert (result.status, result.llm_calls) == ("out_of_scope", 1)
    assert (result.input_tokens, result.output_tokens) == (100, 15)
    assert client.requests[0]["store"] is False


def test_tool_results_go_back_to_the_model_and_into_data():
    client = ScriptedClient(
        turn(call("compute_metric", metric="visibility", brands=["Sample Client"])),
        turn(call("reply", status="answered", answer="50.0% (16 di 32 risposte)")),
    )
    result = agent.run("Quanto è visibile Sample Client?", client=client)
    assert result.status == "answered"
    assert result.data[0]["value"] == 50.0
    assert len(result.queries) == 1
    sent_back = client.requests[1]["input"][-1]
    assert (sent_back["type"], sent_back["call_id"]) == ("function_result", "call-compute_metric")


def test_tool_errors_are_returned_to_the_model():
    client = ScriptedClient(
        turn(call("compute_metric", metric="revenue")),
        turn(call("reply", status="out_of_scope", answer="Non ho dati sul fatturato.")),
    )
    agent.run("Fatturato di Brand Alpha?", client=client)
    assert "Unknown metric" in client.requests[1]["input"][-1]["result"][0]["text"]


def test_reply_mixed_with_other_calls_is_not_accepted():
    client = ScriptedClient(
        turn(call("find_brands", name="Brand Alpha"), call("reply", status="answered", answer="too early")),
        turn(call("reply", status="answered", answer="Brand Alpha è nominato 32 volte.")),
    )
    result = agent.run("Quante volte è nominato Brand Alpha?", client=client)
    assert result.answer == "Brand Alpha è nominato 32 volte."
    assert result.llm_calls == 2


def test_the_last_call_can_only_reply():
    lookups = [turn(call("find_brands", name="Brand Alpha")) for _ in range(agent.MAX_LLM_CALLS - 1)]
    client = ScriptedClient(*lookups, turn(call("reply", status="answered", answer="ok")))
    result = agent.run("Brand Alpha?", client=client)
    assert (result.status, result.llm_calls) == ("answered", agent.MAX_LLM_CALLS)
    allowed = [r["generation_config"]["tool_choice"]["allowed_tools"]["tools"] for r in client.requests]
    assert allowed[-1] == ["reply"]
    assert "compute_metric" in allowed[0]


def test_a_gemini_failure_returns_an_error_status():
    result = agent.run("Visibility di Sample Client?", client=ScriptedClient())
    assert result.status == "error"


def test_a_dropped_connection_is_retried_once():
    reply = turn(call("reply", status="out_of_scope", answer="Posso rispondere solo sui dati GEO."))
    client = ScriptedClient(dropped_connection(), reply)
    result = agent.run("Che tempo fa a Milano?", client=client)
    assert (result.status, len(client.requests)) == ("out_of_scope", 2)


def test_a_second_dropped_connection_returns_an_error_status():
    client = ScriptedClient(dropped_connection(), dropped_connection())
    result = agent.run("Che tempo fa a Milano?", client=client)
    assert (result.status, len(client.requests)) == ("error", 2)


def test_other_gemini_errors_are_not_retried():
    client = ScriptedClient()
    agent.run("Visibility di Sample Client?", client=client)
    assert len(client.requests) == 1


def test_history_is_sent_before_the_new_message():
    client = ScriptedClient(turn(call("reply", status="answered", answer="ok")))
    agent.run("E su Claude?", history=[("Visibility di Sample Client?", "50.0%")], client=client)
    sent = [(s["type"], s["content"][0]["text"]) for s in client.requests[0]["input"]]
    assert sent == [
        ("user_input", "Visibility di Sample Client?"),
        ("model_output", "50.0%"),
        ("user_input", "E su Claude?"),
    ]


def test_memory_keeps_the_last_exchanges_of_identified_conversations():
    memory = ConversationMemory(max_exchanges=3, max_conversations=2)
    memory.add(None, "q", "a")
    assert memory.get(None) == []
    for i in range(5):
        memory.add("c1", f"q{i}", f"a{i}")
    assert memory.get("c1") == [("q2", "a2"), ("q3", "a3"), ("q4", "a4")]
    memory.add("c2", "q", "a")
    memory.add("c3", "q", "a")
    assert memory.get("c1") == []


@pytest.mark.parametrize(
    "message, language",
    [
        ("What is Brand Beta's visibility on each assistant?", "English"),
        ("Who beats us on startup questions?", "English"),
        ("Qual è la share of voice di Sample Client?", "Italian"),
        ("Chi ci batte sulle domande startup?", "Italian"),
        ("Sample Client?", None),
    ],
)
def test_reply_language_is_detected_from_the_message(message, language):
    from app.prompt import language_hint

    hint = language_hint(message)
    assert (language in hint) if language else hint == ""


def test_the_language_hint_reaches_gemini():
    client = ScriptedClient(turn(call("reply", status="answered", answer="ok")))
    agent.run("What is Brand Beta's visibility on each assistant?", client=client)
    assert client.requests[0]["system_instruction"].endswith("write the reply in English.")


@pytest.mark.parametrize("text", ["Sample Client", "Brand Alpha", "Share of voice", "api.v_mentions"])
def test_system_instruction_is_built_from_the_data(text):
    from app.prompt import system_instruction

    assert text in system_instruction()

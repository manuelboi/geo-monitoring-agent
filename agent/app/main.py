from typing import Literal

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import agent, config, db
from app.memory import ConversationMemory

app = FastAPI(title="Ask your data")
memory = ConversationMemory()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=100)


class Usage(BaseModel):
    model: str
    llm_calls: int
    input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    answer: str
    status: Literal["answered", "clarification_needed", "out_of_scope", "error"]
    data: list[dict]
    queries: list[str]
    usage: Usage


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    result = agent.run(request.message, memory.get(request.conversation_id))
    if result.status != "error":
        memory.add(request.conversation_id, request.message, result.answer)
    return ChatResponse(
        answer=result.answer,
        status=result.status,
        data=result.data,
        queries=result.queries,
        usage=Usage(
            model=config.LLM_MODEL,
            llm_calls=result.llm_calls,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        ),
    )


@app.get("/health")
def health():
    problems = []
    if not config.LLM_API_KEY:
        problems.append("LLM_API_KEY is not set")
    if not config.LLM_MODEL:
        problems.append("LLM_MODEL is not set")
    try:
        # Uses the agent's own read-only role, so a broken role or grant fails the check
        with db.readonly_connection() as conn:
            if conn.execute("SELECT count(*) FROM api.v_answers").fetchone()[0] == 0:
                problems.append("no data loaded")
    except psycopg.Error as e:
        problems.append(f"database not available ({type(e).__name__})")

    if problems:
        return JSONResponse(status_code=503, content={"status": "unavailable", "problems": problems})
    return {"status": "ok"}

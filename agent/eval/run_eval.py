"""Compares Gemini models on the evaluation questions. It calls Gemini: run it where the key is set.

    docker compose exec agent python -m eval.run_eval --list-models
    docker compose exec agent python -m eval.run_eval --models gemini-3.1-flash-lite,gemini-3.8-flash --repeat 3
    docker compose exec agent python -m eval.run_eval --set adversarial --models gemini-3.8-flash

The agent is called in process (agent.run), the same code path as POST /chat without HTTP.
"""

import argparse
import re
import statistics
import time
from dataclasses import dataclass

from google import genai

from app import agent, config, db
from app.prompt import detect_language
from eval.questions import ADVERSARIAL_QUESTIONS, QUESTIONS

QUESTION_SETS = {"main": QUESTIONS, "adversarial": ADVERSARIAL_QUESTIONS}

# USD per million tokens, standard tier, from https://ai.google.dev/gemini-api/docs/pricing (read 2026-10-22)
PRICES = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
}


@dataclass
class Record:
    model: str
    question_id: str
    status_ok: bool
    data_ok: bool | None  # None when the question has no data check
    text_ok: bool
    problems: list[str]
    answer: str
    seconds: float
    input_tokens: int
    output_tokens: int

    @property
    def correct(self) -> bool:
        return self.status_ok and self.data_ok is not False and self.text_ok

    @property
    def cost(self) -> float | None:
        if self.model not in PRICES:
            return None
        price_in, price_out = PRICES[self.model]
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000


def _row_matches(row: dict, expected: dict) -> bool:
    for key, value in expected.items():
        candidates = row.values() if key == "any" else [row.get(key)]
        if not any(_same(candidate, value) for candidate in candidates):
            return False
    return True


def _same(actual, expected) -> bool:
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return abs(actual - expected) < 1e-4
    return actual == expected


def grade(question: dict, result: agent.AgentResult) -> tuple[bool, bool | None, bool, list[str]]:
    """Returns status_ok, data_ok, text_ok and the list of failed checks."""
    problems = []
    status_ok = result.status == question["status"]
    if not status_ok:
        problems.append(f"status {result.status!r}, expected {question['status']!r}")

    data_ok = None
    if question.get("data"):
        missing = [e for e in question["data"] if not any(_row_matches(row, e) for row in result.data)]
        data_ok = not missing
        problems += [f"no data row matching {e}" for e in missing]

    text_ok = True
    for pattern in question.get("text", []):
        if not re.search(pattern, result.answer, re.IGNORECASE | re.DOTALL):
            text_ok = False
            problems.append(f"answer lacks /{pattern}/")
    for pattern in question.get("forbidden", []):
        if re.search(pattern, result.answer, re.IGNORECASE):
            text_ok = False
            problems.append(f"answer contains forbidden /{pattern}/")
    if "language" in question and detect_language(result.answer) not in (question["language"], None):
        text_ok = False
        problems.append(f"answer not in {question['language']}")
    return status_ok, data_ok, text_ok, problems


def evaluate(models: list[str], repeat: int, questions: list[dict] = QUESTIONS) -> list[Record]:
    records = []
    for model in models:
        for question in questions:
            for attempt in range(1, repeat + 1):
                start = time.perf_counter()
                result = agent.run(question["message"], question.get("history", []), model=model)
                seconds = time.perf_counter() - start
                status_ok, data_ok, text_ok, problems = grade(question, result)
                record = Record(
                    model=model,
                    question_id=question["id"],
                    status_ok=status_ok,
                    data_ok=data_ok,
                    text_ok=text_ok,
                    problems=problems,
                    answer=result.answer,
                    seconds=seconds,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
                records.append(record)
                verdict = "ok  " if record.correct else "FAIL"
                print(f"{verdict} {model} {question['id']} #{attempt} {seconds:.1f}s", flush=True)
    return records


def _share(passed: int, total: int) -> str:
    return f"{passed}/{total} ({passed / total:.0%})" if total else "n/a"


def summary_table(records: list[Record]) -> str:
    lines = [
        (
            "| Model | Correct | Status | Computation (data) | Answer text | Median latency | "
            "Avg input tokens | Avg output tokens | Cost per question | Run cost |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model in dict.fromkeys(r.model for r in records):
        rs = [r for r in records if r.model == model]
        with_data = [r for r in rs if r.data_ok is not None]
        costs = [r.cost for r in rs if r.cost is not None]
        lines.append(
            f"| {model} | {_share(sum(r.correct for r in rs), len(rs))} "
            f"| {_share(sum(r.status_ok for r in rs), len(rs))} "
            f"| {_share(sum(r.data_ok for r in with_data), len(with_data))} "
            f"| {_share(sum(r.text_ok for r in rs), len(rs))} "
            f"| {statistics.median(r.seconds for r in rs):.1f} s "
            f"| {statistics.mean(r.input_tokens for r in rs):,.0f} "
            f"| {statistics.mean(r.output_tokens for r in rs):,.0f} "
            f"| {f'${statistics.mean(costs):.4f}' if costs else 'n/a'} "
            f"| {f'${sum(costs):.2f}' if costs else 'n/a'} |"
        )
    return "\n".join(lines)


def failures_report(records: list[Record]) -> str:
    lines = []
    for r in records:
        if not r.correct:
            answer = " ".join(r.answer.split())[:300]
            lines.append(f"- {r.model} {r.question_id}: {'; '.join(r.problems)}\n  answer: {answer}")
    return "\n".join(lines) or "None."


def database_is_intact() -> bool:
    with db.readonly_connection() as conn:
        return conn.execute("SELECT count(*) FROM api.v_mentions").fetchone()[0] == 64


def list_models() -> None:
    client = genai.Client(api_key=config.LLM_API_KEY)
    for model in client.models.list():
        if "gemini" in model.name and ("flash" in model.name or "pro" in model.name):
            print(model.name.removeprefix("models/"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list-models", action="store_true", help="list the Gemini models this key can use")
    parser.add_argument("--models", default=config.LLM_MODEL, help="comma-separated model ids")
    parser.add_argument("--repeat", type=int, default=3, help="runs per question and model")
    parser.add_argument("--set", choices=QUESTION_SETS, default="main", help="which questions to ask")
    args = parser.parse_args()
    if args.list_models:
        list_models()
        return

    questions = QUESTION_SETS[args.set]
    records = evaluate(args.models.split(","), args.repeat, questions)
    print("\n## Failed answers (review: a failed check can be a wrong check)\n")
    print(failures_report(records))
    print(f"\n## Results ({args.set}: {len(questions)} questions x {args.repeat} runs per model)\n")
    print(summary_table(records))
    total = sum(r.cost or 0 for r in records)
    print(f"\nTotal cost of this run: ${total:.2f}. Database intact after the run: {database_is_intact()}.")


if __name__ == "__main__":
    main()

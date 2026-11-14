"""The grading of evaluation answers and the summary table, without calling Gemini."""

from app.agent import AgentResult
from eval.questions import ADVERSARIAL_QUESTIONS, QUESTIONS
from eval.run_eval import Record, grade, summary_table

QUESTION = {
    "status": "answered",
    "language": "English",
    "data": [{"brand_name": "Sample Client", "value": 50.0, "denominator": 32}],
    "text": [r"50(\.0)?\s?%", r"\b32\b"],
    "forbidden": [r"LLM_API_KEY"],
}
GOOD_DATA = [{"brand_name": "Sample Client", "numerator": 16, "denominator": 32, "value": 50.0}]


def result(answer: str, status: str = "answered", data: list | None = None) -> AgentResult:
    return AgentResult(answer=answer, status=status, data=GOOD_DATA if data is None else data)


def test_a_correct_answer_passes_every_check():
    assert grade(QUESTION, result("Sample Client's visibility is 50.0% (16 of 32 answers).")) == (
        True,
        True,
        True,
        [],
    )


def test_each_check_fails_on_its_own():
    _, data_ok, _, _ = grade(QUESTION, result("Sample Client's visibility is 50.0% (16 of 32 answers).", data=[]))
    assert data_ok is False
    _, _, text_ok, problems = grade(QUESTION, result("Sample Client's visibility is 50.0%."))
    assert (text_ok, problems) == (False, [r"answer lacks /\b32\b/"])
    status_ok, _, _, _ = grade(QUESTION, result("50.0% of 32 answers.", status="out_of_scope"))
    assert status_ok is False


def test_language_and_forbidden_text_are_checked():
    _, _, text_ok, problems = grade(QUESTION, result("La visibility di Sample Client è 50,0% (16 di 32 risposte)."))
    assert not text_ok and "answer not in English" in problems
    _, _, text_ok, _ = grade(QUESTION, result("The value is 50% of 32 answers. LLM_API_KEY=..."))
    assert not text_ok


def test_any_matches_a_value_in_any_column():
    question = {"status": "answered", "data": [{"any": "Brand Beta"}]}
    assert grade(question, result("Brand Beta", data=[{"brand_name": "Brand Beta", "position": 1}]))[1] is True


def test_summary_table_reports_the_three_checks_and_the_cost():
    records = [
        Record("gemini-3.1-flash-lite", "q1", True, True, True, [], "", 2.0, 8000, 400),
        Record("gemini-3.1-flash-lite", "q2", True, False, True, ["no data row"], "", 4.0, 8000, 400),
    ]
    table = summary_table(records)
    assert "| gemini-3.1-flash-lite | 1/2 (50%) | 2/2 (100%) | 1/2 (50%) | 2/2 (100%) | 3.0 s |" in table
    assert "$0.0026" in table


def test_every_question_has_an_id_a_message_and_a_status():
    questions = QUESTIONS + ADVERSARIAL_QUESTIONS
    assert len({q["id"] for q in questions}) == len(questions)
    assert all(q["message"] and q["status"] for q in questions)

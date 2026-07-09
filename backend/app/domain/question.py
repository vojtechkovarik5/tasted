from pydantic import BaseModel


class SuggestedQuestions(BaseModel):
    """Structured output of the question-suggestion prompt (services/ai.py).

    Short "ask the staff" questions in the user's own language, seeded from
    their "Watch out for" chips. Plain strings — the user adds the ones they
    like to their saved list, where they become UserQuestion rows.
    """

    questions: list[str]

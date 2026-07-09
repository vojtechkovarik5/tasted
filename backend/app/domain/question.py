from pydantic import BaseModel


class SuggestedQuestions(BaseModel):
    """Structured output of the question-suggestion prompt (services/ai.py).

    Short "ask the staff" questions in the user's own language, seeded from
    their "Watch out for" chips. Plain strings — the user adds the ones they
    like to their saved list, where they become UserQuestion rows.
    """

    questions: list[str]


class TranslatedQuestions(BaseModel):
    """Structured output of the question-translation prompt (services/ai.py).

    The ask-staff sheet shows the user's questions in the language the
    restaurant's staff speaks. The menu's language isn't stored anywhere, so
    the model infers it from the dish (name + origin) and translates in one
    round trip.
    """

    language: str  # ISO 639-1 the staff most likely speaks ("pt")
    translations: list[str]  # same order as the questions sent

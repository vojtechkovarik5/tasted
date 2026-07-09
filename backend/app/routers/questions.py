import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import CurrentUserDep
from app.models import UserQuestion
from app.services.questions import QuestionServiceDep

router = APIRouter(prefix="/questions", tags=["questions"])

# Saved "Ask the staff" questions (Settings -> My questions). Written once in
# the user's own language; the ask-staff sheet translates them per menu on
# demand, so the API only ever sees the original text. Order matters — the
# sheet lists them as arranged here — hence PUT /questions/order.


class QuestionOut(BaseModel):
    id: uuid.UUID
    text: str


class QuestionIn(BaseModel):
    # 500 matches the DB column; surrounding whitespace is stripped on save.
    text: str = Field(max_length=500)


class QuestionOrder(BaseModel):
    ids: list[uuid.UUID]  # the full list in its new order


class SuggestionsOut(BaseModel):
    """LLM-suggested questions, seeded from the "Watch out for" chips."""

    based_on: list[str]  # active watch keys the prompt was seeded with
    questions: list[str]  # in the user's language, ready to add


def _out(question: UserQuestion) -> QuestionOut:
    return QuestionOut(id=question.id, text=question.text)


@router.get("", response_model=list[QuestionOut])
async def list_questions(
    user_id: CurrentUserDep, questions: QuestionServiceDep
) -> list[QuestionOut]:
    """The user's saved questions, in list order."""
    return [_out(q) for q in await questions.list(user_id)]


@router.post("", response_model=QuestionOut)
async def add_question(
    payload: QuestionIn, user_id: CurrentUserDep, questions: QuestionServiceDep
) -> QuestionOut:
    """Append a question to the end of the user's list."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Question text is required")
    return _out(await questions.add(user_id, text))


@router.put("/order", response_model=list[QuestionOut])
async def reorder_questions(
    payload: QuestionOrder, user_id: CurrentUserDep, questions: QuestionServiceDep
) -> list[QuestionOut]:
    """Persist a drag-reorder. `ids` must be exactly the current questions."""
    try:
        return [_out(q) for q in await questions.reorder(user_id, payload.ids)]
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None


@router.get("/suggestions", response_model=SuggestionsOut)
async def suggest_questions(
    user_id: CurrentUserDep, questions: QuestionServiceDep
) -> SuggestionsOut:
    """Suggested questions from the user's "Watch out for" list (LLM-backed;
    deterministic stub without an API key). Empty when nothing is watched."""
    based_on, suggested = await questions.suggest(user_id)
    return SuggestionsOut(based_on=based_on, questions=suggested)


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: uuid.UUID, user_id: CurrentUserDep, questions: QuestionServiceDep
) -> None:
    """Remove one saved question. 404 covers "not yours" too, so ids can't be
    probed across users."""
    if not await questions.remove(user_id, question_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

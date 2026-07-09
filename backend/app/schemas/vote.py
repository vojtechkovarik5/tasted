from enum import StrEnum

from pydantic import BaseModel

# Votes exist only for the subjective, taste-calibration attributes: spice
# and price level. Allergen/dietary probabilities are NOT votable — they're
# safety-relevant, owned by the AI baseline + moderated corrections.
#
# Wire shape: POST /dishes/{dish_id}/vote/{target} with {"direction": "up"}.


class VoteTarget(StrEnum):
    spice = "spice"
    price = "price"


class VoteDirection(StrEnum):
    up = "up"  # right arrow (more) -> stored as +1
    down = "down"  # left arrow (less) -> stored as -1


class VoteAck(BaseModel):
    accepted: bool = True


class MyVotesOut(BaseModel):
    """The current user's standing votes on a dish (GET /dishes/{id}/votes).

    Levels only shift on periodic recalculation, so the UI can't read a vote
    back from the value — this is what lets it highlight the pressed arrow
    across reloads. Null = not voted on that target.
    """

    spice: VoteDirection | None = None
    price: VoteDirection | None = None

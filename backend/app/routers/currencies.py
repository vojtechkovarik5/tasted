from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUserDep
from app.schemas import CurrencyOut
from app.services.currencies import CurrencyServiceDep
from app.services.users import UserServiceDep

router = APIRouter(prefix="/currencies", tags=["currencies"])


class CurrencySelection(BaseModel):
    code: str  # ISO 4217, must be one of the supported currencies


@router.get("", response_model=list[CurrencyOut])
async def list_currencies(service: CurrencyServiceDep) -> list[CurrencyOut]:
    """All supported currencies with their daily EUR rate — feeds the
    "My currency" dropdown in the profile."""
    return [CurrencyOut.model_validate(c) for c in await service.list()]


@router.post("", response_model=CurrencySelection)
async def set_my_currency(
    selection: CurrencySelection,
    user_id: CurrentUserDep,
    currencies: CurrencyServiceDep,
    users: UserServiceDep,
) -> CurrencySelection:
    """Set the authenticated user's display currency.

    Validates against the supported currencies (the dropdown's source) and
    persists it on the user's prefs — it drives approx_price conversion on
    every menu read.
    """
    code = selection.code.upper()
    if await currencies.get(code) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported currency: {code}")
    prefs = await users.update_preferences(user_id, currency=code)
    return CurrencySelection(code=prefs.currency)

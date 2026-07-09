from pydantic import BaseModel, ConfigDict


class CurrencyOut(BaseModel):
    """One entry of the currency dropdown (Profile -> "My currency").

    `rate_per_eur` is exposed so the client can also convert locally:
    amount_B = amount_A / rate_A * rate_B.
    """

    model_config = ConfigDict(from_attributes=True)

    code: str  # ISO 4217, e.g. "CZK"
    name: str  # "Czech koruna"
    symbol: str | None = None  # "Kč"
    rate_per_eur: float

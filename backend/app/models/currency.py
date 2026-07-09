from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Currency(Base):
    """One currency and its daily rate against a single base (EUR).

    We deliberately do NOT store the full pair matrix (n^2 rates): each row
    holds how many units of the currency 1 EUR buys, and any cross rate is
    derived through the base:

        amount_B = amount_A / rate_per_eur(A) * rate_per_eur(B)

    That's n rates to keep fresh instead of n*(n-1), and it's exactly how
    reference feeds (ECB) publish them. Rates are refreshed daily — a Celery
    beat task later; the migration seeds a starter set so the currency
    dropdown works immediately.
    """

    __tablename__ = "currencies"
    __table_args__ = (CheckConstraint("rate_per_eur > 0", name="ck_currencies_rate_positive"),)

    code: Mapped[str] = mapped_column(String(3), primary_key=True)  # ISO 4217, e.g. "CZK"
    name: Mapped[str] = mapped_column(String(64))  # "Czech koruna"
    symbol: Mapped[str | None] = mapped_column(String(8))  # "Kč"
    rate_per_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6))  # units per 1 EUR
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

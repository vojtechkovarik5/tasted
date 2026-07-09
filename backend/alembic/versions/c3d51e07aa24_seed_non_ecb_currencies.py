"""seed non-ECB travel currencies

The daily rate refresh uses Frankfurter (ECB reference rates), which only
covers ~30 major currencies — a menu priced in QAR, AED, VND etc. got no
approx conversion at all. Seed common travel-destination currencies the feed
doesn't carry, with approximate static rates (units per 1 EUR, mid-2026).
The refresh task never touches codes it doesn't receive, so these keep their
seeded rate until a broader feed replaces Frankfurter. Pegged currencies
(Gulf pegs to USD, XOF/XAF to EUR) barely drift; the rest are marked by the
approx (~) display anyway.

Revision ID: c3d51e07aa24
Revises: 8a41c7d90b12
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d51e07aa24'
down_revision: Union[str, Sequence[str], None] = '8a41c7d90b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (code, name, symbol, rate per 1 EUR — approximate)
SEED = [
    ('QAR', 'Qatari riyal', 'QR', 3.93),
    ('AED', 'UAE dirham', 'د.إ', 3.97),
    ('SAR', 'Saudi riyal', 'SR', 4.05),
    ('KWD', 'Kuwaiti dinar', 'KD', 0.33),
    ('BHD', 'Bahraini dinar', 'BD', 0.41),
    ('OMR', 'Omani rial', 'RO', 0.42),
    ('JOD', 'Jordanian dinar', 'JD', 0.77),
    ('EGP', 'Egyptian pound', 'E£', 52.0),
    ('MAD', 'Moroccan dirham', 'DH', 10.8),
    ('TND', 'Tunisian dinar', 'DT', 3.4),
    ('UAH', 'Ukrainian hryvnia', '₴', 45.0),
    ('RSD', 'Serbian dinar', 'din', 117.0),
    ('BAM', 'Bosnian mark', 'KM', 1.96),
    ('ALL', 'Albanian lek', 'L', 99.0),
    ('MKD', 'Macedonian denar', 'den', 61.5),
    ('GEL', 'Georgian lari', '₾', 3.0),
    ('LKR', 'Sri Lankan rupee', 'Rs', 330.0),
    ('NPR', 'Nepalese rupee', 'Rs', 144.0),
    ('PKR', 'Pakistani rupee', 'Rs', 300.0),
    ('BDT', 'Bangladeshi taka', '৳', 127.0),
    ('KHR', 'Cambodian riel', '៛', 4400.0),
    ('LAK', 'Lao kip', '₭', 23500.0),
    ('MMK', 'Myanmar kyat', 'K', 2270.0),
    ('TWD', 'New Taiwan dollar', 'NT$', 34.5),
    ('CLP', 'Chilean peso', '$', 1020.0),
    ('PEN', 'Peruvian sol', 'S/', 4.0),
    ('COP', 'Colombian peso', '$', 4500.0),
    ('ARS', 'Argentine peso', '$', 1050.0),
    ('UYU', 'Uruguayan peso', '$U', 45.0),
    ('CRC', 'Costa Rican colón', '₡', 550.0),
    ('DOP', 'Dominican peso', 'RD$', 64.0),
    ('KES', 'Kenyan shilling', 'KSh', 140.0),
    ('TZS', 'Tanzanian shilling', 'TSh', 2800.0),
    ('MUR', 'Mauritian rupee', 'Rs', 50.0),
    ('XOF', 'West African CFA franc', 'CFA', 655.96),
    ('XAF', 'Central African CFA franc', 'FCFA', 655.96),
    ('FJD', 'Fijian dollar', 'FJ$', 2.4),
]


def upgrade() -> None:
    """Upgrade schema."""
    for code, name, symbol, rate in SEED:
        op.execute(
            "INSERT INTO currencies (code, name, symbol, rate_per_eur) "
            f"VALUES ('{code}', '{name.replace(chr(39), chr(39) * 2)}', '{symbol}', {rate}) "
            "ON CONFLICT (code) DO NOTHING"
        )


def downgrade() -> None:
    """Downgrade schema."""
    codes = ", ".join(f"'{code}'" for code, *_ in SEED)
    op.execute(f"DELETE FROM currencies WHERE code IN ({codes})")

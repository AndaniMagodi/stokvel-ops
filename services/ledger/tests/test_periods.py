from datetime import date

import pytest

from app.contributions.periods import contribution_month


@pytest.mark.parametrize(
    ("payment_date", "expected_month"),
    [
        (date(2026, 9, 7), (2026, 8)),
        (date(2026, 9, 8), (2026, 9)),
        (date(2027, 1, 7), (2026, 12)),
        (date(2027, 1, 8), (2027, 1)),
    ],
)
def test_contribution_month(payment_date, expected_month):
    assert contribution_month(payment_date) == expected_month
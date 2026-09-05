import uuid

from hypothesis import assume
from hypothesis import strategies as st

CENT_LIMIT = 100_000_000

nonzero_cents = st.integers(min_value=-CENT_LIMIT, max_value=CENT_LIMIT).filter(
    lambda value: value != 0
)
positive_cents = st.integers(min_value=1, max_value=CENT_LIMIT)
transaction_kinds = st.sampled_from(["contribution", "payout", "adjustment"])
idempotency_keys = st.uuids().map(str)


@st.composite
def balanced_amounts(draw, min_legs: int = 2, max_legs: int = 4) -> list[int]:
    leg_count = draw(st.integers(min_value=min_legs, max_value=max_legs))
    head = draw(
        st.lists(nonzero_cents, min_size=leg_count - 1, max_size=leg_count - 1)
    )
    tail = -sum(head)
    assume(tail != 0)
    return [*head, tail]


@st.composite
def posting_plans(draw, max_postings: int = 6) -> list[list[int]]:
    count = draw(st.integers(min_value=1, max_value=max_postings))
    return [draw(balanced_amounts()) for _ in range(count)]

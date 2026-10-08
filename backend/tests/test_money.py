import pytest
from hypothesis import given, settings, strategies as st

from app.money import (
    SplitError,
    brute_force_min_transfer_count,
    minimal_transfers,
    split_equal,
    split_exact,
    split_shares,
)


def test_equal_split_leftover_cents_go_to_lowest_ids():
    assert split_equal(100, [3, 1, 2]) == {1: 34, 2: 33, 3: 33}
    assert split_equal(1, [5, 9]) == {5: 1, 9: 0}


def test_shares_largest_remainder():
    assert split_shares(100, {1: 1, 2: 2}) == {1: 33, 2: 67}
    assert sum(split_shares(1001, {1: 3, 2: 3, 3: 1}).values()) == 1001


def test_exact_must_add_up():
    assert split_exact(10, {1: 4, 2: 6}) == {1: 4, 2: 6}
    with pytest.raises(SplitError):
        split_exact(10, {1: 4, 2: 5})


@given(st.integers(0, 10**9), st.lists(st.integers(1, 10**6), min_size=1, max_size=20, unique=True))
def test_equal_never_loses_cents(total, ids):
    shares = split_equal(total, ids)
    assert sum(shares.values()) == total
    assert max(shares.values()) - min(shares.values()) <= 1


@given(
    st.integers(0, 10**9),
    st.dictionaries(st.integers(1, 10**6), st.integers(1, 1000), min_size=1, max_size=15),
)
def test_shares_never_lose_cents(total, weights):
    shares = split_shares(total, weights)
    assert sum(shares.values()) == total
    assert all(v >= 0 for v in shares.values())


def _apply(balances, transfers):
    out = dict(balances)
    for t in transfers:
        out[t.from_user] += t.amount
        out[t.to_user] -= t.amount
    return out


def _balances():
    return st.lists(st.integers(-10_000, 10_000), min_size=1, max_size=9).map(
        lambda xs: {i + 1: v for i, v in enumerate(xs + [-sum(xs)])}
    )


@given(_balances())
@settings(max_examples=200)
def test_transfers_settle_everyone(balances):
    transfers = minimal_transfers(balances)
    assert all(v == 0 for v in _apply(balances, transfers).values())
    assert all(t.amount > 0 and t.from_user != t.to_user for t in transfers)


@given(st.lists(st.integers(-50, 50), min_size=1, max_size=7).map(
    lambda xs: {i + 1: v for i, v in enumerate(xs + [-sum(xs)])}
))
@settings(max_examples=150)
def test_transfer_count_is_optimal(balances):
    assert len(minimal_transfers(balances)) == brute_force_min_transfer_count(balances)


def test_not_everyone_pays_everyone():
    balances = {1: 3000, 2: -1000, 3: -1000, 4: -1000}
    assert len(minimal_transfers(balances)) == 3
    balances = {1: 100, 2: -100, 3: 50, 4: -50}
    assert len(minimal_transfers(balances)) == 2


def test_large_group_falls_back_to_greedy_but_still_settles():
    balances = {i: (i % 7 - 3) * 100 for i in range(1, 40)}
    balances[0] = -sum(balances.values())
    transfers = minimal_transfers(balances)
    assert all(v == 0 for v in _apply(balances, transfers).values())
    assert len(transfers) <= len(balances) - 1


def test_unbalanced_input_rejected():
    with pytest.raises(SplitError):
        minimal_transfers({1: 10, 2: -5})

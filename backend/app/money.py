"""Pure money logic: splitting an expense and settling balances.

All amounts are integers in minor units (cents). No floats anywhere.

Leftover-cent rule (one rule, always the same): shares are computed by the
largest-remainder method; cents that cannot be divided are handed out one by
one to the participants with the biggest fractional remainder, ties broken by
ascending user id. For an equal split this means the *lowest user ids* get the
extra cent. The shares always sum to the expense total exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations


class SplitError(ValueError):
    pass


def split_equal(total: int, user_ids: list[int]) -> dict[int, int]:
    if total < 0:
        raise SplitError("total must be non-negative")
    if not user_ids:
        raise SplitError("at least one participant is required")
    if len(set(user_ids)) != len(user_ids):
        raise SplitError("duplicate participants")
    return split_shares(total, {uid: 1 for uid in user_ids})


def split_shares(total: int, weights: dict[int, int]) -> dict[int, int]:
    if total < 0:
        raise SplitError("total must be non-negative")
    if not weights:
        raise SplitError("at least one participant is required")
    if any(w <= 0 for w in weights.values()):
        raise SplitError("weights must be positive integers")
    weight_sum = sum(weights.values())
    base = {uid: total * w // weight_sum for uid, w in weights.items()}
    remainder = {uid: total * w % weight_sum for uid, w in weights.items()}
    left = total - sum(base.values())
    order = sorted(weights, key=lambda uid: (-remainder[uid], uid))
    for uid in order[:left]:
        base[uid] += 1
    return base


def split_exact(total: int, amounts: dict[int, int]) -> dict[int, int]:
    if not amounts:
        raise SplitError("at least one participant is required")
    if any(a < 0 for a in amounts.values()):
        raise SplitError("amounts must be non-negative")
    if sum(amounts.values()) != total:
        raise SplitError("exact amounts must add up to the expense total")
    return dict(amounts)


@dataclass(frozen=True)
class Transfer:
    from_user: int
    to_user: int
    amount: int


def _greedy(balances: dict[int, int]) -> list[Transfer]:
    debtors = sorted(((-b, uid) for uid, b in balances.items() if b < 0), reverse=True)
    creditors = sorted(((b, uid) for uid, b in balances.items() if b > 0), reverse=True)
    debtors = [[a, u] for a, u in debtors]
    creditors = [[a, u] for a, u in creditors]
    out: list[Transfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        pay = min(debtors[i][0], creditors[j][0])
        out.append(Transfer(debtors[i][1], creditors[j][1], pay))
        debtors[i][0] -= pay
        creditors[j][0] -= pay
        if debtors[i][0] == 0:
            i += 1
        if creditors[j][0] == 0:
            j += 1
    return out


OPTIMAL_LIMIT = 12  # the DP is O(3^n): 12 people is about 0.05 s, 14 was about 0.25 s


def minimal_transfers(balances: dict[int, int]) -> list[Transfer]:
    """See _minimal_transfers; results are cached by the balances themselves, so repeated reads of an unchanged group are free."""
    if sum(balances.values()) != 0:
        raise SplitError("balances must sum to zero")
    return list(_cached_minimal(tuple(sorted((u, b) for u, b in balances.items() if b != 0))))


@lru_cache(maxsize=4096)
def _cached_minimal(items: tuple[tuple[int, int], ...]) -> tuple[Transfer, ...]:
    return tuple(_minimal_transfers(dict(items)))


def _minimal_transfers(balances: dict[int, int]) -> list[Transfer]:
    """Fewest transfers that bring every balance to zero.

    balances: user id -> net balance (positive: is owed money, negative: owes).
    Must sum to zero. The number of transfers is n - k, where k is the largest
    number of disjoint groups whose balances each sum to zero. That
    partition problem is NP-hard in general, so for up to OPTIMAL_LIMIT
    non-zero participants it is solved exactly (bitmask DP); beyond that the
    greedy matching is used (still at most n - 1 transfers).
    """
    if sum(balances.values()) != 0:
        raise SplitError("balances must sum to zero")
    nonzero = {uid: b for uid, b in balances.items() if b != 0}
    if not nonzero:
        return []
    if len(nonzero) > OPTIMAL_LIMIT:
        return _greedy(nonzero)

    ids = sorted(nonzero)
    n = len(ids)
    vals = [nonzero[u] for u in ids]
    full = (1 << n) - 1
    subset_sum = [0] * (1 << n)
    for mask in range(1, 1 << n):
        low = (mask & -mask).bit_length() - 1
        subset_sum[mask] = subset_sum[mask & (mask - 1)] + vals[low]

    # best[mask] = max number of disjoint zero-sum groups inside mask
    best = [0] * (1 << n)
    choice = [0] * (1 << n)
    for mask in range(1, 1 << n):
        low = mask & -mask
        rest = mask ^ low
        sub = rest
        b, c = -1, 0
        while True:
            group = sub | low
            if subset_sum[group] == 0:
                cand = best[mask ^ group] + 1
                if cand > b:
                    b, c = cand, group
            if sub == 0:
                break
            sub = (sub - 1) & rest
        best[mask] = b if b >= 0 else 0
        choice[mask] = c

    transfers: list[Transfer] = []
    mask = full
    while mask:
        group = choice[mask]
        if group == 0:
            group = mask
        members = {ids[i]: vals[i] for i in range(n) if group >> i & 1}
        transfers.extend(_greedy(members))
        mask ^= group
    return transfers


def brute_force_min_transfer_count(balances: dict[int, int]) -> int:
    """Reference implementation for tests (tiny inputs only)."""
    vals = [b for b in balances.values() if b != 0]
    n = len(vals)
    if n == 0:
        return 0
    best = 0
    idx = list(range(n))

    def rec(remaining: list[int], count: int) -> None:
        nonlocal best
        if not remaining:
            best = max(best, count)
            return
        first = remaining[0]
        rest = remaining[1:]
        for r in range(0, len(rest) + 1):
            for combo in combinations(rest, r):
                if vals[first] + sum(vals[i] for i in combo) == 0:
                    rec([i for i in rest if i not in combo], count + 1)

    rec(idx, 0)
    return n - best

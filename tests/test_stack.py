"""Tests for RpnStack: level indexing, LIFO order, underflow safety, UNDO."""

from __future__ import annotations

import pytest

from rpncalc.stack import RpnStack, StackError


def make(*values: float) -> RpnStack:
    """Build a stack with `values[0]` ending up on level 1 (pushed last)."""
    s = RpnStack()
    for v in values:
        s.push(v)
    return s


def test_push_pop_is_lifo() -> None:
    s = RpnStack()
    s.push(1)
    s.push(2)
    s.push(3)
    assert s.pop() == 3
    assert s.pop() == 2
    assert s.pop() == 1
    assert s.depth == 0


def test_push_puts_value_on_level_1() -> None:
    s = make(1, 2, 3)  # push order 1, 2, 3 -> level 1 = 3
    assert s.peek(1) == 3
    assert s.peek(2) == 2
    assert s.peek(3) == 1
    assert s.depth == 3


def test_to_list_is_level_1_first() -> None:
    s = make(1, 2, 3)
    assert s.to_list() == [3, 2, 1]


def test_peek_does_not_mutate() -> None:
    s = make(1, 2, 3)
    assert s.peek() == 3  # default level=1
    assert s.depth == 3
    assert s.to_list() == [3, 2, 1]


def test_drop_removes_level_1() -> None:
    s = make(1, 2, 3)
    s.drop()
    assert s.to_list() == [2, 1]


def test_dropn_removes_top_n() -> None:
    s = make(1, 2, 3, 4)
    s.dropn(2)
    assert s.to_list() == [2, 1]


def test_swap_exchanges_levels_1_and_2() -> None:
    s = make(1, 2)  # level1=2, level2=1
    s.swap()
    assert s.to_list() == [1, 2]


def test_dup_duplicates_level_1() -> None:
    s = make(1, 2)
    s.dup()
    assert s.to_list() == [2, 2, 1]


def test_dupn_duplicates_top_n_as_a_block() -> None:
    s = make(1, 2, 3)  # level1=3, level2=2, level3=1
    s.dupn(2)
    assert s.to_list() == [3, 2, 3, 2, 1]


def test_over_copies_level_2_to_level_1() -> None:
    s = make(1, 2)  # level1=2, level2=1
    s.over()
    assert s.to_list() == [1, 2, 1]


def test_rot_moves_level_3_to_level_1() -> None:
    s = make(1, 2, 3)  # level1=3, level2=2, level3=1
    s.rot()
    # 3->1: level1=1, level2=3, level3=2
    assert s.to_list() == [1, 3, 2]


def test_unrot_is_inverse_of_rot() -> None:
    s = make(1, 2, 3)
    original = s.to_list()
    s.rot()
    s.unrot()
    assert s.to_list() == original


def test_rot_unrot_round_trip_many_times() -> None:
    s = make(10, 20, 30)
    original = s.to_list()
    for _ in range(5):
        s.rot()
    for _ in range(5):
        s.unrot()
    assert s.to_list() == original


def test_roll_moves_level_n_to_level_1() -> None:
    s = make(1, 2, 3, 4)  # level1=4 level2=3 level3=2 level4=1
    s.roll(4)
    # level4 (=1) moves to level1, others shift up
    assert s.to_list() == [1, 4, 3, 2]


def test_rolld_is_inverse_of_roll() -> None:
    s = make(1, 2, 3, 4)
    original = s.to_list()
    s.roll(4)
    s.rolld(4)
    assert s.to_list() == original


def test_pick_copies_level_n_to_level_1() -> None:
    s = make(1, 2, 3)  # level1=3, level2=2, level3=1
    s.pick(3)
    assert s.to_list() == [1, 3, 2, 1]


def test_clear_empties_the_stack() -> None:
    s = make(1, 2, 3)
    s.clear()
    assert s.depth == 0
    assert s.to_list() == []


def test_depth_command_pushes_current_depth() -> None:
    s = make(1, 2, 3)
    s.depth_command()
    assert s.to_list() == [3, 3, 2, 1]


def test_depth_command_on_empty_stack_pushes_zero() -> None:
    s = RpnStack()
    s.depth_command()
    assert s.to_list() == [0]


@pytest.mark.parametrize(
    "op",
    [
        lambda s: s.pop(),
        lambda s: s.peek(1),
        lambda s: s.drop(),
        lambda s: s.dropn(1),
        lambda s: s.swap(),
        lambda s: s.dup(),
        lambda s: s.dupn(1),
        lambda s: s.over(),
        lambda s: s.rot(),
        lambda s: s.unrot(),
        lambda s: s.roll(1),
        lambda s: s.rolld(1),
        lambda s: s.pick(1),
    ],
)
def test_underflow_raises_stack_error(op) -> None:
    s = RpnStack()
    with pytest.raises(StackError, match="Too Few Arguments"):
        op(s)


def test_underflow_does_not_mutate_depth_or_contents() -> None:
    s = make(1, 2)  # depth 2, not enough for rot(3)
    before = s.to_list()
    with pytest.raises(StackError):
        s.rot()
    assert s.to_list() == before
    assert s.depth == 2


def test_underflow_on_swap_with_one_item_leaves_stack_untouched() -> None:
    s = make(42)
    with pytest.raises(StackError):
        s.swap()
    assert s.to_list() == [42]


def test_underflow_on_roll_beyond_depth() -> None:
    s = make(1, 2)
    before = s.to_list()
    with pytest.raises(StackError):
        s.roll(5)
    assert s.to_list() == before


def test_last_args_restore_after_drop() -> None:
    s = make(1, 2, 3)
    before = s.to_list()
    s.drop()
    assert s.to_list() != before
    s.restore_last_args()
    assert s.to_list() == before


def test_last_args_restore_undoes_only_the_single_most_recent_mutation() -> None:
    # Simulate what an engine does for a binary op: pop twice, push result.
    # last_args is a snapshot taken before the *last* mutating call only, so
    # restoring after a pop-pop-push sequence undoes just the push, landing
    # on the (empty) state right after the pops -- not the original stack.
    # An engine that wants a one-shot UNDO of a whole command must snapshot
    # itself before the command runs, e.g. via depth/to_list.
    s = make(3, 4)  # level1=4, level2=3
    a = s.pop()
    b = s.pop()
    s.push(a + b)
    assert s.to_list() == [7]
    s.restore_last_args()
    assert s.to_list() == []


def test_last_args_none_before_any_mutation() -> None:
    s = RpnStack()
    assert s.last_args is None
    s.restore_last_args()  # no-op, must not raise
    assert s.to_list() == []


def test_last_args_unaffected_by_non_mutating_peek() -> None:
    s = make(1, 2, 3)
    s.drop()
    snapshot_after_drop = s.last_args
    s.peek(1)
    assert s.last_args == snapshot_after_drop

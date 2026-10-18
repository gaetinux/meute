"""Tests for parsing Claude's statusline JSON (real 2.1.302 payloads)."""

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from meute.core.json_types import JsonValue
from meute.core.statusline import StatuslineData, parse_statusline
from support import claude_statusline_fixture


def test_default_data_is_empty() -> None:
    data = StatuslineData()
    assert data.cwd is None
    assert data.five_hour_resets_at is None
    assert parse_statusline({}) == data


def test_first_statusline_has_no_quota_yet() -> None:
    data = parse_statusline(claude_statusline_fixture("statusline-1"))
    assert data == StatuslineData(
        cwd="/home/user/git/poc-app-rust",
        model_name="Opus 5.5",
        effort="medium",
        cost_usd=0,
        duration_ms=1173,
        lines_added=0,
        lines_removed=0,
        repo_host="github.com",
        repo_owner="user",
        repo_name="meute",
    )


def test_second_statusline_has_context_and_quota() -> None:
    data = parse_statusline(claude_statusline_fixture("statusline-2"))
    assert data.context_pct == 4
    assert data.cost_usd == 0.1125694
    assert data.duration_ms == 3830
    assert data.five_hour_pct == 27
    assert data.five_hour_resets_at == datetime(2026, 10, 18, 16, 20, tzinfo=UTC)
    assert data.seven_day_pct == 42
    assert data.seven_day_resets_at == datetime.fromtimestamp(1792717200, UTC)


def test_worktree_and_agent_fields() -> None:
    data = parse_statusline(
        {
            "worktree": {"name": "w", "branch": "feat/x", "path": "/p/w"},
            "agent": {"name": "reviewer"},
        }
    )
    assert (data.worktree_name, data.worktree_branch, data.worktree_path) == ("w", "feat/x", "/p/w")
    assert data.agent_name == "reviewer"


def test_cwd_falls_back_when_workspace_is_missing_or_unusable() -> None:
    assert parse_statusline({"cwd": "/a"}).cwd == "/a"
    assert parse_statusline({"workspace": {"current_dir": "/w"}, "cwd": "/a"}).cwd == "/w"
    assert parse_statusline({"workspace": {"current_dir": 3}, "cwd": "/a"}).cwd == "/a"
    assert parse_statusline({"workspace": "x", "cwd": "/a"}).cwd == "/a"


def test_model_falls_back_to_id() -> None:
    assert parse_statusline({"model": {"id": "claude-x"}}).model_name == "claude-x"
    assert parse_statusline({"model": {"id": "i", "display_name": "D"}}).model_name == "D"
    assert parse_statusline({"model": {"id": "i", "display_name": 4}}).model_name == "i"
    assert parse_statusline({"model": "claude-x"}).model_name is None


def test_wrong_types_become_none() -> None:
    data = parse_statusline(
        {
            "cwd": 3,
            "effort": {"level": ["x"]},
            "context_window": {"used_percentage": "4"},
            "cost": {
                "total_cost_usd": True,
                "total_duration_ms": 1.5,
                "total_lines_added": False,
                "total_lines_removed": None,
            },
            "rate_limits": {"five_hour": {"used_percentage": True, "resets_at": "soon"}},
        }
    )
    assert data == StatuslineData()


def test_non_finite_and_out_of_range_numbers_become_none() -> None:
    data = parse_statusline(
        {
            "context_window": {"used_percentage": float("nan")},
            "cost": {"total_cost_usd": float("inf")},
            "rate_limits": {
                "five_hour": {"used_percentage": 1, "resets_at": 10**30},
                "seven_day": {"resets_at": float("nan")},
            },
        }
    )
    assert data.context_pct is None
    assert data.cost_usd is None
    assert data.five_hour_pct == 1
    assert data.five_hour_resets_at is None
    assert data.seven_day_resets_at is None


def test_duration_accepts_integers_only() -> None:
    assert parse_statusline({"cost": {"total_duration_ms": 12}}).duration_ms == 12
    assert parse_statusline({"cost": {"total_duration_ms": 12.0}}).duration_ms is None


def test_huge_integers_become_none() -> None:
    data = parse_statusline(
        {
            "cost": {"total_cost_usd": 10**400},
            "context_window": {"used_percentage": -(10**400)},
            "rate_limits": {"five_hour": {"used_percentage": 10**400, "resets_at": 10**400}},
        }
    )
    assert data == StatuslineData()


def test_instants_outside_the_storable_years_become_none() -> None:
    before_1970 = parse_statusline({"rate_limits": {"five_hour": {"resets_at": -1}}})
    after_9999 = parse_statusline({"rate_limits": {"five_hour": {"resets_at": 253402300800}}})
    year_1 = parse_statusline({"rate_limits": {"five_hour": {"resets_at": -62135596800}}})
    assert before_1970.five_hour_resets_at is None
    assert after_9999.five_hour_resets_at is None
    assert year_1.five_hour_resets_at is None
    epoch = parse_statusline({"rate_limits": {"five_hour": {"resets_at": 0}}})
    assert epoch.five_hour_resets_at == datetime(1970, 1, 1, tzinfo=UTC)


weird = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.integers(min_value=10**300, max_value=10**400)
    | st.floats()
    | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=6,
)
limit = st.dictionaries(st.sampled_from(["used_percentage", "resets_at"]), weird)


@given(
    payload=st.dictionaries(
        st.sampled_from(
            ["cwd", "workspace", "model", "effort", "context_window", "cost", "worktree", "agent"]
        ),
        weird,
    ),
    rate_limits=st.dictionaries(st.sampled_from(["five_hour", "seven_day"]), limit | weird),
)
def test_parse_statusline_never_raises(
    payload: dict[str, JsonValue], rate_limits: dict[str, JsonValue]
) -> None:
    parse_statusline({**payload, "rate_limits": rate_limits})


@given(payload=st.dictionaries(st.text(), weird))
def test_parse_statusline_never_raises_on_arbitrary_keys(payload: dict[str, JsonValue]) -> None:
    parse_statusline(payload)

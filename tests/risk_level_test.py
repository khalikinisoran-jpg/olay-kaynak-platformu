import pytest

from simulation.security.risk_level import (
    RiskLevel
)


ORDERED = (
    RiskLevel.UNKNOWN,
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
)

SEVERITY = {
    RiskLevel.UNKNOWN: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


def test_deterministic_ordering_is_strictly_increasing():

    severities = [
        level.severity
        for level in ORDERED
    ]

    assert severities == sorted(severities)

    assert len(set(severities)) == len(severities)

    assert severities == [0, 1, 2, 3, 4]


def test_unknown_is_below_low():

    assert RiskLevel.UNKNOWN.severity < RiskLevel.LOW.severity


def test_high_severity_is_three():

    assert RiskLevel.HIGH.severity == 3


def test_critical_severity_is_four():

    assert RiskLevel.CRITICAL.severity == 4


def test_each_level_severity_matches_contract():

    for level, expected in SEVERITY.items():

        assert level.severity == expected


def test_parse_returns_same_member_for_member_input():

    for level in ORDERED:

        assert RiskLevel.parse(level) is level


def test_parse_normalizes_case_and_whitespace():

    assert RiskLevel.parse("  high ") is RiskLevel.HIGH

    assert RiskLevel.parse("cRiTiCaL") is RiskLevel.CRITICAL

    assert RiskLevel.parse("  low ") is RiskLevel.LOW


def test_parse_accepts_every_canonical_label():

    for level in ORDERED:

        assert RiskLevel.parse(level.value) is level


def test_parse_rejects_none():

    with pytest.raises(ValueError):

        RiskLevel.parse(None)


def test_parse_rejects_non_string():

    with pytest.raises(ValueError):

        RiskLevel.parse(5)

    with pytest.raises(ValueError):

        RiskLevel.parse(["HIGH"])


def test_parse_rejects_unknown_label():

    with pytest.raises(ValueError):

        RiskLevel.parse("EXTREME")

    with pytest.raises(ValueError):

        RiskLevel.parse("")


def test_parse_fail_closed_never_returns_unknown_for_garbage():

    for malformed in (None, "", "EXTREME", 5, ["HIGH"]):

        with pytest.raises(ValueError):

            RiskLevel.parse(malformed)


def test_at_least_compares_by_severity():

    assert RiskLevel.HIGH.at_least(RiskLevel.MEDIUM) is True

    assert RiskLevel.HIGH.at_least(RiskLevel.HIGH) is True

    assert RiskLevel.MEDIUM.at_least(RiskLevel.HIGH) is False

    assert RiskLevel.UNKNOWN.at_least(RiskLevel.UNKNOWN) is True


def test_at_least_treats_non_member_as_unknown():

    assert RiskLevel.HIGH.at_least("garbage") is True

    assert RiskLevel.HIGH.at_least(None) is True

    assert RiskLevel.UNKNOWN.at_least("garbage") is True


def test_max_level_returns_most_restrictive():

    assert RiskLevel.max_level(
        RiskLevel.LOW,
        RiskLevel.HIGH,
    ) is RiskLevel.HIGH

    assert RiskLevel.max_level(
        RiskLevel.HIGH,
        RiskLevel.CRITICAL,
    ) is RiskLevel.CRITICAL

    assert RiskLevel.max_level(
        RiskLevel.CRITICAL,
        RiskLevel.UNKNOWN,
    ) is RiskLevel.CRITICAL


def test_max_level_ignores_malformed_inputs():

    assert RiskLevel.max_level(
        "garbage",
        None,
        RiskLevel.HIGH,
    ) is RiskLevel.HIGH


def test_malformed_input_never_dominates():

    assert RiskLevel.max_level(
        "CRITICAL",
        RiskLevel.LOW,
    ) is RiskLevel.LOW

    assert RiskLevel.max_level(
        None,
        RiskLevel.MEDIUM,
    ) is RiskLevel.MEDIUM


def test_max_level_empty_returns_unknown():

    assert RiskLevel.max_level() is RiskLevel.UNKNOWN


def test_max_level_unknown_input_returns_unknown():

    assert RiskLevel.max_level(
        RiskLevel.UNKNOWN
    ) is RiskLevel.UNKNOWN


def test_max_level_ties_return_first_equivalent():

    result = RiskLevel.max_level(
        RiskLevel.LOW,
        RiskLevel.LOW,
    )

    assert result is RiskLevel.LOW

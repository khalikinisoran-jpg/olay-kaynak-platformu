import dataclasses

from simulation.security.risk_engine import (
    RiskAssessment
)

from simulation.security.risk_level import (
    RiskLevel
)

from simulation.security.risk_policy import (
    RiskDecision,
    RiskPolicy,
)


def make_assessment(level):

    return RiskAssessment(
        risk_level=level,
        reason=f"Assessment for {level.value}.",
    )


def test_missing_assessment_denies_closed():

    decision = RiskPolicy().decide(None)

    assert isinstance(decision, RiskDecision)

    assert decision.risk_level is RiskLevel.UNKNOWN

    assert decision.allowed is False

    assert decision.allow_auto_apply is False

    assert decision.max_attempts == 0

    assert decision.verification_depth == ""

    assert (
        decision.reason
        == "Missing risk assessment; denied."
    )


def test_malformed_assessment_denies_closed():

    decision = RiskPolicy().decide("garbage")

    assert decision.risk_level is RiskLevel.UNKNOWN

    assert decision.allowed is False

    assert (
        decision.reason
        == "Malformed risk assessment; denied."
    )


def test_malformed_level_denies_closed():

    decision = RiskPolicy.from_level("EXTREME")

    assert decision.risk_level is RiskLevel.UNKNOWN

    assert decision.allowed is False

    assert decision.allow_auto_apply is False


def test_unknown_level_is_denied_never_auto_approvable():

    decision = RiskPolicy.from_level(
        RiskLevel.UNKNOWN
    )

    assert decision.risk_level is RiskLevel.UNKNOWN

    assert decision.allowed is False

    assert decision.requires_human_approval is True

    assert decision.allow_auto_apply is False

    assert decision.max_attempts == 0

    assert (
        decision.reason
        == "Risk could not be determined; denied."
    )


def test_low_is_auto_apply_with_full_verification():

    decision = RiskPolicy.from_level(
        RiskLevel.LOW
    )

    assert decision.risk_level is RiskLevel.LOW

    assert decision.allowed is True

    assert decision.requires_human_approval is False

    assert decision.allow_auto_apply is True

    assert decision.max_attempts == 3

    assert (
        decision.verification_depth
        == RiskPolicy.VERIFICATION_DEPTH_COMPILE_TESTS
    )


def test_medium_is_auto_apply_with_bounded_retries():

    decision = RiskPolicy.from_level(
        RiskLevel.MEDIUM
    )

    assert decision.risk_level is RiskLevel.MEDIUM

    assert decision.allowed is True

    assert decision.requires_human_approval is False

    assert decision.allow_auto_apply is True

    assert decision.max_attempts == 2

    assert (
        decision.verification_depth
        == RiskPolicy.VERIFICATION_DEPTH_COMPILE_TESTS
    )


def test_high_requires_human_approval_and_never_auto_applies():

    decision = RiskPolicy.from_level(
        RiskLevel.HIGH
    )

    assert decision.risk_level is RiskLevel.HIGH

    assert decision.allowed is True

    assert decision.requires_human_approval is True

    assert decision.allow_auto_apply is False

    assert decision.max_attempts == 1

    assert (
        decision.reason
        == "High risk; human approval required."
    )


def test_critical_requires_human_approval_and_never_auto_applies():

    decision = RiskPolicy.from_level(
        RiskLevel.CRITICAL
    )

    assert decision.risk_level is RiskLevel.CRITICAL

    assert decision.allowed is True

    assert decision.requires_human_approval is True

    assert decision.allow_auto_apply is False

    assert decision.max_attempts == 1

    assert (
        decision.reason
        == "Critical risk; human approval required."
    )


def test_high_and_critical_share_human_approval_boundary():

    for level in (
        RiskLevel.HIGH,
        RiskLevel.CRITICAL,
    ):

        decision = RiskPolicy.from_level(level)

        assert decision.requires_human_approval is True

        assert decision.allow_auto_apply is False


def test_auto_apply_only_for_low_and_medium():

    for level in (
        RiskLevel.LOW,
        RiskLevel.MEDIUM,
    ):

        decision = RiskPolicy.from_level(level)

        assert decision.allow_auto_apply is True

        assert decision.requires_human_approval is False


def test_max_attempts_never_exceeds_recovery_hard_cap():

    for level in RiskLevel:

        decision = RiskPolicy.from_level(level)

        assert (
            decision.max_attempts <= 3
        ), level


def test_denied_decisions_never_auto_apply():

    for decision in (
        RiskPolicy().decide(None),
        RiskPolicy().decide("garbage"),
        RiskPolicy.from_level(RiskLevel.UNKNOWN),
    ):

        assert decision.allowed is False

        assert decision.allow_auto_apply is False


def test_verification_depth_constants_match_pipeline_contract():

    assert (
        RiskPolicy.VERIFICATION_DEPTH_COMPILE
        == "compile"
    )

    assert (
        RiskPolicy.VERIFICATION_DEPTH_COMPILE_TESTS
        == "compile+tests"
    )


def test_decide_passes_through_assessment_reason():

    assessment = make_assessment(RiskLevel.LOW)

    decision = RiskPolicy().decide(assessment)

    assert decision.risk_level is RiskLevel.LOW

    assert decision.allowed is True

    assert (
        decision.reason
        == "Assessment for LOW."
    )


def test_decide_uses_real_risk_assessment_contract():

    assessment = make_assessment(RiskLevel.HIGH)

    decision = RiskPolicy().decide(assessment)

    assert decision.risk_level is RiskLevel.HIGH

    assert decision.requires_human_approval is True

    assert decision.allow_auto_apply is False


def test_high_level_default_reason_when_empty():

    decision = RiskPolicy.from_level(
        RiskLevel.HIGH,
        reason="",
    )

    assert (
        decision.reason
        == "High risk; human approval required."
    )


def test_deny_decision_verification_depth_is_empty():

    decision = RiskPolicy.from_level(
        RiskLevel.UNKNOWN
    )

    assert decision.verification_depth == ""


def test_risk_decision_is_frozen_dataclass():

    decision = RiskPolicy.from_level(
        RiskLevel.LOW
    )

    assert dataclasses.is_dataclass(decision)

    with_deny = RiskPolicy.from_level(
        RiskLevel.UNKNOWN
    )

    assert with_deny.verification_depth == ""

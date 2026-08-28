from types import SimpleNamespace

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.security.risk_engine import (
    RiskAssessment,
    RiskEngine,
)

from simulation.security.risk_level import (
    RiskLevel
)


def make_patch(
    path="safe/notes.txt",
    action="modify",
    old="original content",
    new="updated content",
    allowed_paths=(),
):

    return PatchProposal(
        path=path,
        action=action,
        reason="Risk engine test.",
        old_content=old,
        new_content=new,
        allowed_paths=allowed_paths,
    )


def make_namespace(**kwargs):

    return SimpleNamespace(**kwargs)


def classify(
    patch,
    advisory_risk=None,
    advisory_confidence=None,
):

    return RiskEngine().classify(
        patch,
        advisory_risk=advisory_risk,
        advisory_confidence=advisory_confidence,
    )


def signal_names(assessment):

    return {
        name
        for name, _ in assessment.signals
    }


def test_classify_none_patch_fails_closed_unknown():

    assessment = classify(None)

    assert isinstance(assessment, RiskAssessment)

    assert assessment.risk_level is RiskLevel.UNKNOWN

    assert assessment.signals == ()

    assert (
        assessment.reason
        == "Missing patch for risk assessment."
    )


def test_missing_action_fails_closed_unknown():

    patch = make_namespace(
        path="safe/notes.txt",
        old_content="a",
        new_content="b",
    )

    assessment = classify(patch)

    assert assessment.risk_level is RiskLevel.UNKNOWN

    assert ("action", "missing") in assessment.signals


def test_empty_action_fails_closed_unknown():

    patch = make_patch(action="")

    assessment = classify(patch)

    assert assessment.risk_level is RiskLevel.UNKNOWN

    assert ("action", "missing") in assessment.signals


def test_non_string_action_fails_closed_unknown():

    patch = make_patch(action=5)

    assessment = classify(patch)

    assert assessment.risk_level is RiskLevel.UNKNOWN

    assert ("action", "missing") in assessment.signals


def test_modify_baseline_is_low():

    assessment = classify(make_patch())

    assert assessment.risk_level is RiskLevel.LOW


def test_delete_action_is_critical():

    assessment = classify(
        make_patch(action="delete")
    )

    assert assessment.risk_level is RiskLevel.CRITICAL

    assert ("action", "delete") in assessment.signals


def test_replace_action_is_critical():

    assessment = classify(
        make_patch(action="replace")
    )

    assert assessment.risk_level is RiskLevel.CRITICAL


def test_destructive_action_is_critical_for_each_destructive_label():

    for action in (
        "delete",
        "drop",
        "truncate",
        "format",
        "remove",
        "purge",
        "reset",
        "replace",
    ):

        assessment = classify(
            make_patch(action=action)
        )

        assert (
            assessment.risk_level
            is RiskLevel.CRITICAL
        ), action


def test_non_modify_non_destructive_action_is_high():

    assessment = classify(
        make_patch(action="create")
    )

    assert assessment.risk_level is RiskLevel.HIGH

    assert ("action", "create") in assessment.signals


def test_security_sensitive_path_is_high():

    assessment = classify(
        make_patch(path="settings.secret.txt")
    )

    assert assessment.risk_level is RiskLevel.HIGH

    assert (
        "security_sensitive_path"
        in signal_names(assessment)
    )


def test_privilege_boundary_path_is_critical():

    assessment = classify(
        make_patch(path="/etc/nginx.conf")
    )

    assert assessment.risk_level is RiskLevel.CRITICAL

    assert (
        "privilege_boundary"
        in signal_names(assessment)
    )


def test_production_config_path_is_high():

    assessment = classify(
        make_patch(path="configs/production/app.yaml")
    )

    assert assessment.risk_level is RiskLevel.HIGH

    assert (
        "production_configuration"
        in signal_names(assessment)
    )


def test_secret_file_suffix_is_critical():

    assessment = classify(
        make_patch(path="config.env")
    )

    assert assessment.risk_level is RiskLevel.CRITICAL

    assert (
        "secret_file"
        in signal_names(assessment)
    )


def test_secret_file_by_filename_is_critical():

    assessment = classify(
        make_patch(path="key.pem")
    )

    assert assessment.risk_level is RiskLevel.CRITICAL

    assert (
        "secret_file"
        in signal_names(assessment)
    )


def test_executable_source_suffix_is_medium():

    assessment = classify(
        make_patch(path="src/app.py")
    )

    assert assessment.risk_level is RiskLevel.MEDIUM

    assert ("executable_source", ".py") in (
        assessment.signals
    )


def test_large_change_size_is_high():

    assessment = classify(
        make_patch(
            old="a" * 10,
            new="b" * 600,
        )
    )

    assert assessment.risk_level is RiskLevel.HIGH

    assert (
        "large_change"
        in signal_names(assessment)
    )


def test_pem_block_in_new_content_is_critical():

    assessment = classify(
        make_patch(
            new=(
                "-----BEGIN PRIVATE KEY-----\n"
                "MIIEowIBAAKCAQEA...\n"
                "-----END PRIVATE KEY-----\n"
            )
        )
    )

    assert assessment.risk_level is RiskLevel.CRITICAL

    assert (
        "secret_material"
        in signal_names(assessment)
    )


def test_secret_like_assignment_is_high():

    assessment = classify(
        make_patch(
            new="api_key = 'sk-test-12345'\n"
        )
    )

    assert assessment.risk_level is RiskLevel.HIGH

    assert (
        "secret_like_content"
        in signal_names(assessment)
    )


def test_executable_source_and_secret_content_compose_high():

    assessment = classify(
        make_patch(
            path="src/app.py",
            new="token = 'abc'\n",
        )
    )

    assert assessment.risk_level is RiskLevel.HIGH

    assert (
        "executable_source"
        in signal_names(assessment)
    )

    assert (
        "secret_like_content"
        in signal_names(assessment)
    )


def test_privilege_and_secret_content_compose_critical():

    assessment = classify(
        make_patch(
            path="/etc/app.conf",
            new="password = 'x'\n",
        )
    )

    assert assessment.risk_level is RiskLevel.CRITICAL


def test_advisory_risk_never_lowers_system_level():

    assessment = classify(
        make_patch(path="settings.secret.txt"),
        advisory_risk="LOW",
        advisory_confidence=0.99,
    )

    assert assessment.risk_level is RiskLevel.HIGH

    assert (
        "advisory_llm_risk"
        in signal_names(assessment)
    )


def test_advisory_risk_never_lowers_most_restrictive():

    assessment = classify(
        make_patch(path="/etc/app.conf"),
        advisory_risk="LOW",
    )

    assert assessment.risk_level is RiskLevel.CRITICAL


def test_advisory_risk_can_raise_level():

    assessment = classify(
        make_patch(),
        advisory_risk="CRITICAL",
    )

    assert assessment.risk_level is RiskLevel.CRITICAL

    assert ("advisory_llm_risk", "CRITICAL") in (
        assessment.signals
    )


def test_invalid_advisory_risk_is_dropped():

    assessment = classify(
        make_patch(),
        advisory_risk="not-a-level",
    )

    assert assessment.risk_level is RiskLevel.LOW

    assert assessment.advisory_risk is None

    assert (
        "advisory_llm_risk"
        not in signal_names(assessment)
    )


def test_advisory_unknown_is_not_applied():

    assessment = classify(
        make_patch(),
        advisory_risk="UNKNOWN",
    )

    assert assessment.risk_level is RiskLevel.LOW

    assert assessment.advisory_risk is RiskLevel.UNKNOWN

    assert (
        "advisory_llm_risk"
        not in signal_names(assessment)
    )


def test_advisory_confidence_recorded_only_when_numeric():

    assessment = classify(
        make_patch(),
        advisory_risk="HIGH",
        advisory_confidence=0.87,
    )

    assert assessment.advisory_confidence == 0.87

    non_numeric = classify(
        make_patch(),
        advisory_risk="HIGH",
        advisory_confidence="high",
    )

    assert non_numeric.advisory_confidence is None

    absent = classify(
        make_patch(),
        advisory_risk="HIGH",
    )

    assert absent.advisory_confidence is None


def test_missing_content_does_not_crash_or_elevate():

    patch = make_namespace(
        path="safe/notes.txt",
        action="modify",
        old_content=None,
        new_content=None,
    )

    assessment = classify(patch)

    assert assessment.risk_level is RiskLevel.LOW


def test_missing_path_treated_as_empty():

    patch = make_namespace(
        action="modify",
        old_content="a",
        new_content="b",
    )

    assessment = classify(patch)

    assert assessment.risk_level is RiskLevel.LOW


def test_reason_mentions_elevated_signals():

    assessment = classify(
        make_patch(path="src/app.py")
    )

    assert "executable_source" in assessment.reason

    assert "MEDIUM" in assessment.reason


def test_assessment_is_frozen_evidence():

    assessment = classify(make_patch())

    assert isinstance(assessment, RiskAssessment)

    assert type(assessment.signals) is tuple

"""A26 regression: env secret reference must be HIGH, not MEDIUM.

N.19 reported os.environ.get("AWS_SECRET_ACCESS_KEY") as MEDIUM (should be HIGH).
Fix widens _ENV_SECRET_REFERENCE_RE to handle .get("...") form.

Uses synthetic canaries only.
"""

import pathlib
import tempfile

from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.security.governance_evaluator import GovernanceEvaluator
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy

# Synthetic canaries - MUSE_CANARY + example marks test-only values for secret_guard suppression (FAKE_MARKERS)
CANARY_SECRET = "MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY"
CANARY_TOKEN = "MUSE_CANARY_EXAMPLE_MY_SECRET_TOKEN"


def _patch(new_content: str) -> PatchProposal:
    return PatchProposal(
        path="allowed/a.py",
        action="modify",
        reason="a26-regression",
        old_content="old",
        new_content=new_content,
        allowed_paths=("allowed",),
    )


def test_a26_original_missed_variable_is_high():
    p = _patch('x = os.environ.get("MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY")')  # example
    a = RiskEngine().classify(p)
    assert a.risk_level.value == "HIGH"
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    d = gov.evaluate(p)
    assert d.requires_human_approval is True


def test_a26_case_variations():
    for var in ['MUSE_CANARY_EXAMPLE_aws_secret_access_key', 'MUSE_CANARY_EXAMPLE_Aws_Secret_Access_Key', 'MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY']:
        p = _patch(f'x = os.environ.get("{var}")')
        assert RiskEngine().classify(p).risk_level.value == "HIGH"


def test_a26_naming_variations():
    for var in ["MUSE_CANARY_EXAMPLE_SECRET_KEY", "MUSE_CANARY_EXAMPLE_MY_TOKEN", "MUSE_CANARY_EXAMPLE_API_KEY", "MUSE_CANARY_EXAMPLE_DB_PASSWORD", "MUSE_CANARY_EXAMPLE_CLIENT_SECRET"]:
        p = _patch(f'x = os.environ.get("{var}")')
        assert RiskEngine().classify(p).risk_level.value == "HIGH"


def test_a26_whitespace_and_quotes():
    for content in [
        'x = os.environ.get("MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY")',
        'x = os.environ.get( "MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY" )',
        'x = os.environ.get  (  "MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY"  )',
        "x = os.environ.get('MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY')",
    ]:
        assert RiskEngine().classify(_patch(content)).risk_level.value == "HIGH"


def test_a26_bracket_and_dot_forms_still_high():
    assert RiskEngine().classify(_patch('x = os.environ["MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY"]')).risk_level.value == "HIGH"
    assert RiskEngine().classify(_patch('x = process.env.MUSE_CANARY_EXAMPLE_SECRET_KEY')).risk_level.value == "HIGH"
    assert RiskEngine().classify(_patch('x = getenv("MUSE_CANARY_EXAMPLE_API_KEY")')).risk_level.value == "HIGH"


def test_a26_ordinary_env_stays_medium():
    for var in ["HOME", "PATH", "USER", "SHELL"]:
        p = _patch(f'x = os.environ.get("{var}")')
        a = RiskEngine().classify(p)
        # executable_source .py gives MEDIUM, no secret signal
        assert a.risk_level.value == "MEDIUM"
        gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
        assert gov.evaluate(p).requires_human_approval is False


def test_a26_governance_blocks_without_approval():
    tmp = pathlib.Path(tempfile.mkdtemp())
    ledger = ApprovalLedger(path=tmp / "ledger.jsonl")
    store = ApprovalStore(ledger=ledger)
    p = _patch('x=os.environ.get("MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY")')
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    decision = gov.evaluate(p)
    # HIGH requires approval; empty store must deny
    assert gov.authorize_apply(decision, p, store) is False
    # ordinary MEDIUM must allow without approval
    p2 = _patch('x=1')
    decision2 = gov.evaluate(p2)
    assert gov.authorize_apply(decision2, p2, store) is True


def test_a26_shell_env_with_prefix_still_high():
    # N21 hardening: ${AWS_SECRET_ACCESS_KEY} with prefix must be HIGH (was MEDIUM)
    for content in [
        'echo ${MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY}',
        'echo $MUSE_CANARY_EXAMPLE_AWS_SECRET_ACCESS_KEY',
        'echo ${MUSE_CANARY_EXAMPLE_MY_SECRET}',
        'x = "${MUSE_CANARY_EXAMPLE_SECRET_KEY}" # example',
    ]:
        assert RiskEngine().classify(_patch(content)).risk_level.value == "HIGH"
    # ordinary shell vars stay MEDIUM
    assert RiskEngine().classify(_patch('echo ${HOME}')).risk_level.value == "MEDIUM"
    assert RiskEngine().classify(_patch('echo $HOME')).risk_level.value == "MEDIUM"


def test_a26_whitespace_around_dots_still_high():
    # N21 hardening: whitespace around dots (was MEDIUM)
    for content in [
        'x=os.environ .get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',
        'x=os.environ. get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',
        'x=os .environ.get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',
        'x=os.environ.get(f"MUSE_CANARY_EXAMPLE_SECRET_KEY")',  # f-string prefix
    ]:
        assert RiskEngine().classify(_patch(content)).risk_level.value == "HIGH"


def test_a26_bracket_environ_and_unicode_prefix_still_high():
    # N22 hardening: os['environ'] bracket form and u-prefix (was MEDIUM)
    for content in [
        'x = os[\'environ\'].get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',  # example
        'x = os["environ"].get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',
        'x = os.environ.get(u"MUSE_CANARY_EXAMPLE_SECRET_KEY")',
        'x = os.environ.get(U"MUSE_CANARY_EXAMPLE_SECRET_KEY")',
    ]:
        assert RiskEngine().classify(_patch(content)).risk_level.value == "HIGH"


def test_a26_alias_getattr_still_high():
    # N25 kill-chain: alias dataflow e=os.environ; e.get("SECRET") must be HIGH (was MEDIUM)
    # Covers e.get and getattr(...).get which contain .get("SECRET") even without os.environ prefix
    for content in [
        'e=os.environ\nx=e.get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',  # example
        'x=getattr(os, "environ").get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',
        'env=os.environ\nx=env.get("MUSE_CANARY_EXAMPLE_SECRET_KEY")',
    ]:
        assert RiskEngine().classify(_patch(content)).risk_level.value == "HIGH"

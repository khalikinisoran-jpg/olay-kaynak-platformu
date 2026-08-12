import pytest

from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_level import RiskLevel


LOW = RiskLevel.LOW
MEDIUM = RiskLevel.MEDIUM
HIGH = RiskLevel.HIGH
CRITICAL = RiskLevel.CRITICAL


def make_patch(path, old="value = 1\n", new="value = 2\n"):

    return PatchProposal(
        path=path,
        action="modify",
        reason="Risk regression corpus.",
        old_content=old,
        new_content=new,
        allowed_paths=(path,),
    )


CORPUS = [
    ("settings.secret.txt", "value = 1\n", "value = 2\n", HIGH),
    ("config.env", "value = 1\n", "value = 2\n", CRITICAL),
    ("secrets/app.pem", "value = 1\n", "value = 2\n", CRITICAL),
    ("/etc/nginx.conf", "value = 1\n", "value = 2\n", CRITICAL),
    ("configs/production/app.yaml", "value = 1\n", "value = 2\n", HIGH),
    ("src/app.py", "value = 1\n", "value = 2\n", MEDIUM),
    ("src/notes.txt", "value = 1\n", "value = 2\n", LOW),
    ("authentication.py", "value = 1\n", "value = 2\n", MEDIUM),
    ("tokenizer.py", "value = 1\n", "value = 2\n", MEDIUM),
    ("secretary.py", "value = 1\n", "value = 2\n", MEDIUM),
    ("auth_service.py", "value = 1\n", "value = 2\n", HIGH),
    ("deploy.sh", "value = 1\n", "value = 2\n", HIGH),
    ("docker-compose.yml", "value = 1\n", "value = 2\n", HIGH),
    ("main.tf", "value = 1\n", "value = 2\n", HIGH),
    (
        "src/notes.txt",
        "a = 1\n",
        "a = 1\npassword = 'x'\n",
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        "a = 1\n-----BEGIN PRIVATE KEY-----\nAAAA\n"
        "-----END PRIVATE KEY-----\n",
        CRITICAL,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        "b" * 600,
        HIGH,
    ),
    (
        "src/app.py",
        "a = 1\n",
        "a = 1\ntoken = 'abc'\n",
        HIGH,
    ),
]


@pytest.mark.parametrize(
    "path,old,new,expected",
    CORPUS,
    ids=[
        f"{idx:02d}_{path}"
        for idx, (path, _, _, _) in enumerate(CORPUS)
    ],
)
def test_risk_regression_corpus(path, old, new, expected):

    assessment = RiskEngine().classify(
        make_patch(path, old, new)
    )

    assert assessment.risk_level is expected, (
        f"{path}: got {assessment.risk_level.value}, "
        f"expected {expected.value}"
    )


def test_risk_corpus_agreement_reported():

    engine = RiskEngine()

    matches = 0

    for path, old, new, expected in CORPUS:

        level = engine.classify(
            make_patch(path, old, new)
        ).risk_level

        if level is expected:

            matches += 1

    agreement = matches / len(CORPUS)

    print()
    print("RISK REGRESSION CORPUS")
    print("=" * 60)
    print(
        f"cases={len(CORPUS)} "
        f"agreement={agreement:.2%} "
        f"({matches}/{len(CORPUS)})"
    )
    print(
        "NOTE: this is a small deterministic sanity corpus, "
        "NOT a statistically validated evaluation."
    )
    print("=" * 60)

    assert matches == len(CORPUS)

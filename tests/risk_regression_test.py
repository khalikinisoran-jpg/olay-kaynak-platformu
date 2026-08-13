import pytest

from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_level import RiskLevel


LOW = RiskLevel.LOW
MEDIUM = RiskLevel.MEDIUM
HIGH = RiskLevel.HIGH
CRITICAL = RiskLevel.CRITICAL
UNKNOWN = RiskLevel.UNKNOWN


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
    # ------------------------------------------------------------------
    # MISSION-018A: known RiskEngine bypasses must fail closed (HIGH/CRITICAL
    # -> human approval) instead of silently auto-applying as LOW/MEDIUM.
    # Path hardening
    ("src/app.py.bak", "value = 1\n", "value = 2\n", HIGH),
    ("src/app.py~", "value = 1\n", "value = 2\n", HIGH),
    ("src/app.py.orig", "value = 1\n", "value = 2\n", HIGH),
    ("prod.yaml", "value = 1\n", "value = 2\n", HIGH),
    ("configs/staging/app.yaml", "value = 1\n", "value = 2\n", HIGH),
    ("configs/uat/app.yaml", "value = 1\n", "value = 2\n", HIGH),
    ("secrets/app.txt", "value = 1\n", "value = 2\n", HIGH),
    ("keys/app.txt", "value = 1\n", "value = 2\n", HIGH),
    ("private/app.txt", "value = 1\n", "value = 2\n", HIGH),
    (".creds", "value = 1\n", "value = 2\n", HIGH),
    (".aws", "value = 1\n", "value = 2\n", HIGH),
    # Content hardening: structured credentials
    (
        "src/notes.txt",
        "a = 1\n",
        '{"password": "hunter2"}\n',
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        '{"token": "tok_1234567890abcdef"}\n',
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        '{"api_key": "AIzaSyD1234567890abcdef"}\n',
        HIGH,
    ),
    # Bare tokens / JWT-like material
    (
        "src/notes.txt",
        "a = 1\n",
        "sk-1234567890abcdef0123456789abcdef\n",
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        "ghp_1234567890abcdefghijklmnopqrstuvwxyz\n",
        HIGH,
    ),
    # Base64 / encoded material
    (
        "src/notes.txt",
        "a = 1\n",
        'creds = "Z2hwX2FiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6MTIzNDU2Nzg5MA=="\n',
        HIGH,
    ),
    # Fragmented / part-numbered secrets
    (
        "src/notes.txt",
        "a = 1\n",
        'token_part1 = "sk-abc"\ntoken_part2 = "def"\n',
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        'p1 = "sk-1234567890abcdef01"\np2 = "ghijklmnopqrstuvwxyz12"\n',
        HIGH,
    ),
    # Environment secret references
    (
        "src/notes.txt",
        "a = 1\n",
        'os.environ["SECRET_KEY"]\n',
        HIGH,
    ),
    ("src/notes.txt", "a = 1\n", "process.env.API_TOKEN\n", HIGH),
    ("src/notes.txt", "a = 1\n", "${SECRET_KEY}\n", HIGH),
    # URLs / shell / connection strings embedding credentials
    (
        "src/notes.txt",
        "a = 1\n",
        'url = "https://admin:hunter2@example.com/api"\n',
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        "curl -u admin:hunter2 https://example.com\n",
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        "curl --password hunter2 https://example.com\n",
        HIGH,
    ),
    # Authorization header constructions
    (
        "src/app.py",
        "a = 1\n",
        'requests.get(u, headers={"Authorization": "Bearer " + tok})\n',
        HIGH,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJ"
        "V_adQssw5c\n",
        HIGH,
    ),
    # Connection strings with embedded password segments
    (
        "src/notes.txt",
        "a = 1\n",
        "Server=db;User Id=sa;Password=P@ssw0rd123\n",
        HIGH,
    ),
    # YAML-style credential
    ("src/notes.txt", "a = 1\n", "password: hunter2\n", HIGH),
    # OPAQUE content (control characters) cannot be classified -> UNKNOWN
    ("src/notes.txt", "a = 1\n", "value = 1\x00value = 2\n", UNKNOWN),
    # ------------------------------------------------------------------
    # Benign negatives (MISSION-018A): these must NOT be elevated.
    ("src/notes.txt", "a = 1\n", "self.token = None\n", LOW),
    ("src/notes.txt", "a = 1\n", "count = 3\n", LOW),
    (
        "src/notes.txt",
        "a = 1\n",
        'url = "https://example.com/api"\n',
        LOW,
    ),
    ("src/notes.txt", "a = 1\n", 'os.environ["HOME"]\n', LOW),
    (
        "src/app.py",
        "a = 1\n",
        "def tokenize(text):\n    return text.split()\n",
        MEDIUM,
    ),
    (
        "src/app.py",
        "a = 1\n",
        "tokenizer = Tokenizer()\n",
        MEDIUM,
    ),
    (
        "src/notes.txt",
        "a = 1\n",
        'passwords = ["a", "b"]\n',
        LOW,
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

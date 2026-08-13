"""MISSION-019: secret retry-leak regression tests.

Verification stdout/stderr is fed back to the LLM analyzer on a
recovery retry so the model can fix a failing test. A failed test can
print a secret value; these tests lock that such values are redacted
and length-bounded before they enter the next LLM prompt.
"""

from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.security.secret_policy import (
    REDACTED_MARKER,
    sanitize_for_llm,
)


class FakeEvidenceRecord:

    def __init__(
        self,
        stage,
        exit_code,
        stdout,
        stderr,
    ):

        self.stage = stage
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class FakeTask:

    def __init__(self, description, recovery_evidence, attempt=1):

        self.description = description
        self.recovery_evidence = tuple(recovery_evidence)
        self.attempt = attempt


def test_secret_value_in_verification_stdout_is_redacted():

    stdout = (
        "password = 'supersecretvalue123'\n"
        "assert add(1, 2) == 3 failed\n"
    )

    line = WorkerAgent._format_evidence_line(
        FakeEvidenceRecord(
            stage="tests",
            exit_code=1,
            stdout=stdout,
            stderr="",
        )
    )

    assert "supersecretvalue123" not in line
    assert REDACTED_MARKER in line


def test_secret_value_in_verification_stderr_is_redacted():

    stderr = "api_token=ghp_abcdefghijklmnopqrstuvwxyz1234567890\n"

    line = WorkerAgent._format_evidence_line(
        FakeEvidenceRecord(
            stage="tests",
            exit_code=1,
            stdout="",
            stderr=stderr,
        )
    )

    assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in line
    assert REDACTED_MARKER in line


def test_verification_output_is_length_bounded():

    long_output = "A" * 10000

    sanitized = sanitize_for_llm(long_output)

    assert len(sanitized) < 10000
    assert "[truncated]" in sanitized


def test_recovery_evidence_description_is_sanitized():

    task = FakeTask(
        description="fix the test",
        recovery_evidence=[
            FakeEvidenceRecord(
                stage="tests",
                exit_code=1,
                stdout=(
                    "password = 'supersecretvalue123'\n"
                    "failure trace\n"
                ),
                stderr="",
            ),
        ],
    )

    description = WorkerAgent._analysis_description(task)

    assert "supersecretvalue123" not in description
    assert REDACTED_MARKER in description
    assert "fix the test" in description


def test_plain_evidence_is_not_corrupted():

    line = WorkerAgent._format_evidence_line(
        FakeEvidenceRecord(
            stage="tests",
            exit_code=0,
            stdout="1 passed",
            stderr="",
        )
    )

    assert "1 passed" in line

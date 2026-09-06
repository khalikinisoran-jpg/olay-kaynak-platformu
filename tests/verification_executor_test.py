import os
import sys

from simulation.agent.apply.apply_result import ApplyResult

from simulation.agent.verify.command_runner import (
    CommandResult,
    CommandRunner,
)

from simulation.agent.verify.verification_executor import (
    VerificationExecutor,
)


def make_command_result(
    exit_code=0,
    stdout="",
    stderr="",
    timed_out=False,
    error=""
):

    return CommandResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        error=error
    )


class RecordingRunner:

    def __init__(self, results):

        self.results = list(results)

        self.calls = []

    def run(
        self,
        command,
        timeout=None,
        cwd=None,
        env=None
    ):

        self.calls.append({
            "command": tuple(command),
            "timeout": timeout,
            "cwd": cwd,
            "env": env,
        })

        return self.results.pop(0)


def test_verification_executor_passes_when_all_stages_pass():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(exit_code=0),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert result.status == "PASS"

    assert result.passed is True

    assert result.failed is False

    assert result.exit_code == 0

    assert result.failure_reason == ""

    assert len(result.evidence) == 2

    assert len(runner.calls) == 2


def test_verification_executor_fails_when_compile_fails():

    runner = RecordingRunner([
        make_command_result(
            exit_code=1,
            stderr="SyntaxError: invalid syntax"
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert result.status == "FAIL"

    assert result.passed is False

    assert result.failed is True

    assert result.exit_code == 1

    assert (
        "compilation"
        in result.failure_reason.lower()
    )

    assert "SyntaxError" in result.stderr

    assert len(runner.calls) == 1

    assert (
        "pytest"
        not in runner.calls[0]["command"]
    )


def test_verification_executor_fails_when_tests_fail():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(
            exit_code=1,
            stdout="1 failed",
            stderr="FAILED sample_test::test_x"
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert result.status == "FAIL"

    assert result.exit_code == 1

    assert (
        "test"
        in result.failure_reason.lower()
    )

    assert "1 failed" in result.stdout

    assert (
        "FAILED sample_test::test_x"
        in result.stderr
    )

    assert len(runner.calls) == 2

    assert (
        "pytest"
        in runner.calls[1]["command"]
    )


def test_verification_executor_non_zero_exit_is_fail():

    runner = RecordingRunner([
        make_command_result(
            exit_code=2,
            stdout="tests failed"
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify_tests(
        ["tests/"]
    )

    assert result.status == "FAIL"

    assert result.failed is True

    assert result.exit_code == 2

    assert (
        "non-zero exit code 2"
        in result.failure_reason
    )


def test_verification_executor_captures_stdout_and_stderr():

    runner = RecordingRunner([
        make_command_result(
            exit_code=0,
            stdout="compiled 1 file",
            stderr=""
        ),
        make_command_result(
            exit_code=0,
            stdout="3 passed",
            stderr="pytest warning"
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert result.status == "PASS"

    assert "compiled 1 file" in result.stdout

    assert "3 passed" in result.stdout

    assert "pytest warning" in result.stderr

    compile_record = result.evidence[0]

    assert compile_record.stage == "compile"

    assert compile_record.exit_code == 0

    assert (
        compile_record.stdout
        == "compiled 1 file"
    )

    test_record = result.evidence[1]

    assert test_record.stage == "tests"

    assert (
        test_record.command[-1]
        == "tests/sample_test.py"
    )


def test_verification_executor_timeout_is_fail():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(
            timed_out=True,
            error=(
                "Command exceeded the "
                "allowed timeout."
            )
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert result.status == "FAIL"

    assert result.failed is True

    assert result.exit_code == -1

    assert (
        "timed out"
        in result.failure_reason.lower()
    )


def test_verification_executor_process_failure_is_fail():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(
            error=(
                "Command failed to start: "
                "[Errno 2] No such file"
            )
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert result.status == "FAIL"

    assert result.failed is True

    assert result.exit_code == -1

    assert (
        "failed to start"
        in result.failure_reason
    )


def test_verification_executor_no_tests_collected_is_fail():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(
            exit_code=5,
            stdout="no tests ran",
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/empty_target.py"],
    )

    assert result.status == "FAIL"

    assert result.passed is False

    assert result.exit_code == 5

    assert (
        "no tests"
        in result.failure_reason.lower()
    )


def test_verification_executor_default_timeout_is_applied():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(exit_code=0),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert runner.calls[0]["timeout"] == (
        VerificationExecutor.DEFAULT_TIMEOUT
    )


def test_verification_executor_redirects_bytecode_cache():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(exit_code=0),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    env = runner.calls[0]["env"]

    assert env is not None

    assert "PYTHONPYCACHEPREFIX" in env

    assert env["PYTHONPYCACHEPREFIX"]

    assert env["PYTHONPYCACHEPREFIX"] != os.environ.get(
        "PYTHONPYCACHEPREFIX",
        "",
    )


def test_verification_executor_no_tests_exit_is_never_pass():

    runner = RecordingRunner([
        make_command_result(
            exit_code=5,
            stdout="no tests ran",
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify_tests(
        ["tests/empty/"],
    )

    assert result.status == "FAIL"

    assert result.passed is False


def test_verification_executor_builds_safe_command_args():

    runner = RecordingRunner([
        make_command_result(exit_code=0),
        make_command_result(exit_code=0),
    ])

    executor = VerificationExecutor(
        runner=runner,
        python_executable="venv-python",
        timeout=42,
        cwd="/sandbox/project",
    )

    result = executor.verify(
        [
            "simulation/sample.py",
            "simulation/util.py",
        ],
        [
            "tests/sample_test.py",
            "tests/util_test.py",
        ],
    )

    assert result.status == "PASS"

    assert runner.calls[0]["command"] == (
        "venv-python",
        "-m",
        "compileall",
        "-q",
        "-f",
        "simulation/sample.py",
        "simulation/util.py",
    )

    assert runner.calls[1]["command"] == (
        "venv-python",
        "-m",
        "pytest",
        "-q",
        "tests/sample_test.py",
        "tests/util_test.py",
    )

    assert runner.calls[0]["timeout"] == 42

    assert runner.calls[0]["cwd"] == (
        "/sandbox/project"
    )

    assert isinstance(
        runner.calls[0]["command"],
        tuple
    )


def test_application_success_is_not_verification_success():

    apply_result = ApplyResult(
        success=True,
        path="simulation/sample.py",
        message="File applied successfully.",
    )

    runner = RecordingRunner([
        make_command_result(
            exit_code=1,
            stderr="SyntaxError: invalid syntax"
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify(
        ["simulation/sample.py"],
        ["tests/sample_test.py"],
    )

    assert apply_result.success is True

    assert result.status == "FAIL"

    assert result.failed is True

    assert result.passed is False


def test_verification_executor_does_not_modify_target(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = (
        "def sample():\n"
        "    return 42\n"
    )

    target.write_text(
        original,
        encoding="utf-8"
    )

    runner = RecordingRunner([
        make_command_result(
            exit_code=0,
            stdout="syntax ok"
        ),
    ])

    executor = VerificationExecutor(
        runner=runner
    )

    result = executor.verify_python_compile(
        [str(target)]
    )

    assert result.status == "PASS"

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )

    assert (
        runner.calls[0]["command"][-1]
        == str(target)
    )


def test_verification_executor_defaults_to_running_python():

    executor = VerificationExecutor()

    assert (
        executor.python_executable
        == sys.executable
    )


def test_command_runner_captures_real_process_output():

    runner = CommandRunner()

    result = runner.run([
        sys.executable,
        "-c",
        (
            "import sys;"
            "print('hello stdout');"
            "print('hello stderr', "
            "file=sys.stderr);"
            "sys.exit(3)"
        ),
    ])

    assert result.timed_out is False

    assert result.error == ""

    assert result.exit_code == 3

    assert "hello stdout" in result.stdout

    assert "hello stderr" in result.stderr


def test_command_runner_reports_missing_command():

    runner = CommandRunner()

    result = runner.run([
        "definitely-not-a-real-command-xyz",
    ])

    assert result.exit_code == -1

    assert result.error != ""

    assert result.timed_out is False


def test_command_runner_reports_timeout():

    runner = CommandRunner()

    result = runner.run(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
        timeout=0.2,
    )

    assert result.timed_out is True

    assert result.exit_code == -1

    assert result.error != ""


def test_verification_executor_compiles_real_python_file(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = (
        "def sample():\n"
        "    return 42\n"
    )

    target.write_text(
        original,
        encoding="utf-8"
    )

    executor = VerificationExecutor()

    result = executor.verify_python_compile(
        [str(target)]
    )

    assert result.status == "PASS"

    assert result.exit_code == 0

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )

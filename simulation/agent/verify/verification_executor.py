import os
import sys
import tempfile

from simulation.agent.verify.command_runner import (
    CommandResult,
    CommandRunner,
)

from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationEvidence,
    VerificationResult,
)


class VerificationExecutor:

    """Deterministic post-apply verification.

    This component only verifies. It never applies a patch, never
    makes a Controller decision, and never produces a new patch.

    Hardening (sprint):

    - A default timeout is applied so a hanging verification cannot
      block the runtime forever (an explicit ``timeout`` still wins).
    - pytest's documented "no tests collected" exit code (5) is
      treated as FAILURE, never as a pass, so a neutered or empty test
      target cannot be reported as verification success.
    - Bytecode cache output (``__pycache__``) of the verification
      subprocess is redirected to a temporary directory via
      ``PYTHONPYCACHEPREFIX`` so verification does not mutate the
      repository it verifies.
    """

    DEFAULT_TIMEOUT = 120

    STAGE_COMPILE = "compile"
    STAGE_TESTS = "tests"

    NO_TESTS_COLLECTED_EXIT = 5

    STAGE_LABELS = {
        STAGE_COMPILE: "Python compilation",
        STAGE_TESTS: "Test execution",
    }

    def __init__(
        self,
        runner=None,
        python_executable=None,
        timeout=None,
        cwd=None
    ):

        self.runner = (
            runner
            if runner is not None
            else CommandRunner()
        )

        self.python_executable = (
            python_executable
            if python_executable is not None
            else sys.executable
        )

        self.timeout = (
            timeout
            if timeout is not None
            else self.DEFAULT_TIMEOUT
        )

        self.cwd = cwd

        self._pycache_prefix = None

    def verify_python_compile(
        self,
        paths
    ) -> VerificationResult:

        command = self._argv(
            self.python_executable,
            "-m",
            "compileall",
            "-q",
            *paths,
        )

        return self._stage_result(
            stage=self.STAGE_COMPILE,
            command=command
        )

    def verify_tests(
        self,
        test_targets
    ) -> VerificationResult:

        command = self._argv(
            self.python_executable,
            "-m",
            "pytest",
            "-q",
            *test_targets,
        )

        return self._stage_result(
            stage=self.STAGE_TESTS,
            command=command
        )

    def verify(
        self,
        paths,
        test_targets=()
    ) -> VerificationResult:

        compile_result = (
            self.verify_python_compile(
                paths
            )
        )

        stages = [compile_result]

        if compile_result.failed:

            return self._combine(
                stages
            )

        test_result = self.verify_tests(
            test_targets
        )

        stages.append(test_result)

        return self._combine(
            stages
        )

    def _stage_result(
        self,
        stage,
        command
    ) -> VerificationResult:

        result = self.runner.run(
            command,
            timeout=self.timeout,
            cwd=self.cwd,
            env=self._env(),
        )

        passed = self._is_pass(result)

        exit_code = (
            -1
            if result.timed_out or result.error
            else result.exit_code
        )

        evidence = (
            VerificationEvidence(
                stage=stage,
                command=command,
                exit_code=exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=result.timed_out,
                error=result.error,
            ),
        )

        return VerificationResult(
            status=(
                PASS
                if passed
                else FAIL
            ),
            exit_code=exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            command=command,
            evidence=evidence,
            failure_reason=self._failure_reason(
                stage,
                result
            )
        )

    def _is_pass(
        self,
        result: CommandResult
    ) -> bool:

        return (
            not result.timed_out
            and not result.error
            and result.exit_code == 0
        )

    def _env(self):

        """Environment for the verification subprocess.

        ``PYTHONPYCACHEPREFIX`` redirects the subprocess bytecode
        cache away from the repository so compileall/pytest do not
        mutate ``__pycache__`` directories inside the tree under
        verification.
        """

        if self._pycache_prefix is None:

            self._pycache_prefix = tempfile.mkdtemp(
                prefix="esp-pycache-"
            )

        env = dict(os.environ)

        env["PYTHONPYCACHEPREFIX"] = self._pycache_prefix

        return env

    def _failure_reason(
        self,
        stage,
        result
    ):

        label = self.STAGE_LABELS.get(
            stage,
            stage
        )

        if self._is_pass(result):

            return ""

        if result.timed_out:

            return (
                f"{label} verification timed out."
            )

        if result.error:

            return (
                f"{label} verification failed: "
                f"{result.error}"
            )

        if (
            result.exit_code
            == self.NO_TESTS_COLLECTED_EXIT
        ):

            return (
                f"{label} verification found no "
                "tests to run; an empty or neutered "
                "test target is never a pass."
            )

        return (
            f"{label} verification returned "
            f"non-zero exit code "
            f"{result.exit_code}."
        )

    def _combine(
        self,
        stages
    ) -> VerificationResult:

        failed = [
            stage
            for stage in stages
            if stage.failed
        ]

        primary = (
            failed[0]
            if failed
            else stages[-1]
        )

        return VerificationResult(
            status=(
                FAIL
                if failed
                else PASS
            ),
            exit_code=primary.exit_code,
            stdout=self._join_outputs(
                stage.stdout
                for stage in stages
            ),
            stderr=self._join_outputs(
                stage.stderr
                for stage in stages
            ),
            command=primary.command,
            evidence=tuple(
                record
                for stage in stages
                for record in stage.evidence
            ),
            failure_reason=(
                primary.failure_reason
                if failed
                else ""
            )
        )

    def _join_outputs(self, outputs):

        return "\n".join(
            output
            for output in outputs
            if output
        )

    def _argv(
        self,
        *parts
    ) -> tuple[str, ...]:

        return tuple(
            str(part)
            for part in parts
        )

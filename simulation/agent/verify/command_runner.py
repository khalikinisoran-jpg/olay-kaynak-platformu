import subprocess

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str = ""


class CommandRunner:

    """Executes an external verification command.

    Commands are always run as an argument list without a shell so
    no command string is ever interpreted by a shell.
    """

    def run(
        self,
        command,
        timeout=None,
        cwd=None,
        env=None
    ) -> CommandResult:

        args = tuple(
            str(part)
            for part in command
        )

        try:

            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                shell=False,
                env=env
            )

            return CommandResult(
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr
            )

        except subprocess.TimeoutExpired as exc:

            return CommandResult(
                exit_code=-1,
                stdout=self._decode(
                    exc.stdout
                ),
                stderr=self._decode(
                    exc.stderr
                ),
                timed_out=True,
                error=(
                    "Command exceeded the "
                    "allowed timeout."
                )
            )

        except Exception as exc:

            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr="",
                error=(
                    "Command failed to start: "
                    f"{exc}"
                )
            )

    def _decode(self, value):

        if value is None:

            return ""

        if isinstance(value, bytes):

            return value.decode(
                "utf-8",
                errors="replace"
            )

        return str(value)

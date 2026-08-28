from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:

    """Structured validation outcome.

    The Controller decision is anchored to the typed ``valid`` flag,
    never to the human-readable ``message`` text. Any input that is not
    a ValidationResult, or whose ``valid`` is not exactly ``True``,
    fails closed at the Controller.
    """

    valid: bool
    message: str

    @property
    def passed(self) -> bool:

        return self.valid is True

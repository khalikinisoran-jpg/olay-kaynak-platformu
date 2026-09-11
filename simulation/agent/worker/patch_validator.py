from pathlib import Path

from simulation.agent.worker.patch_proposal import PatchProposal

from simulation.security.path_policy import PathPolicy


class PatchValidator:

    ALLOWED_ACTIONS = {
        "modify",
        "create",
    }

    def __init__(self):

        self.path_policy = PathPolicy()

    def validate(
        self,
        patch: PatchProposal,
        scope=None
    ) -> tuple[bool, str]:

        """Fail-closed patch validation (MISSION-J).

        ``scope`` is the authoritative allowed scope from the trusted
        runtime boundary. It is the ONLY scope that matters: the
        proposal's own ``allowed_paths`` can never expand authority.
        A missing or empty authoritative scope fails closed -- the
        validator never falls back to the proposal's self-declared
        scope.
        """

        if not patch.path:

            return (
                False,
                "Patch path is empty."
            )

        if patch.action not in self.ALLOWED_ACTIONS:

            return (
                False,
                f"Unsupported patch action: {patch.action}"
            )

        if not scope:

            return (
                False,
                "No authoritative scope was provided; "
                "patch validation denied."
            )

        declared_ok, declared_message = (
            self._declared_scope_within_authority(
                patch,
                scope,
            )
        )

        if not declared_ok:

            return (
                False,
                declared_message
            )

        in_scope, scope_message = (
            self.path_policy.check_scope(
                patch.path,
                scope
            )
        )

        if not in_scope:

            return (
                False,
                scope_message
            )

        if patch.action == "create":

            return self._validate_create(
                patch
            )

        path = Path(patch.path)

        if not path.exists():

            return (
                False,
                f"Patch target does not exist: {patch.path}"
            )

        if not path.is_file():

            return (
                False,
                f"Patch target is not a file: {patch.path}"
            )

        try:

            current_content = path.read_text(
                encoding="utf-8"
            )

        except Exception as exc:

            return (
                False,
                f"Unable to read patch target: {exc}"
            )

        if current_content != patch.old_content:

            return (
                False,
                "Patch is stale: current file content "
                "does not match old_content."
            )

        if patch.old_content == patch.new_content:

            return (
                False,
                "Patch does not contain a change."
            )

        return (
            True,
            "Patch validation passed."
        )

    def _validate_create(
        self,
        patch: PatchProposal
    ) -> tuple[bool, str]:

        """Fail-closed create validation.

        Create semantics (product new-file support):

        - ``old_content`` must be EXACTLY the canonical
          no-previous-content marker (the empty string). Any other
          value denies the proposal: a create cannot carry previous
          content it never saw.
        - The target must NOT exist. If it appeared between propose
          and apply, the create is stale and denied (an existing
          target can never be overwritten through ``create``).
        - The parent directory must already exist and be a
          directory. Directory creation authority is NOT granted:
          the proposal cannot make the workspace grow structurally.
        - The scope/traversal checks above have already applied to
          the target path exactly as for ``modify``.
        """

        if patch.old_content != "":

            return (
                False,
                "Create requires old_content to be "
                'exactly "" (the no-previous-content marker).'
            )

        path = Path(patch.path)

        if path.exists():

            return (
                False,
                "Create target already exists; create is "
                f"stale or invalid: {patch.path}"
            )

        parent = path.parent

        if not parent.exists() or not parent.is_dir():

            return (
                False,
                "Create parent directory does not exist "
                f"(directory creation is not authorized): "
                f"{parent}"
            )

        if patch.old_content == patch.new_content:

            return (
                False,
                "Patch does not contain a change."
            )

        return (
            True,
            "Patch validation passed."
        )

    def _declared_scope_within_authority(
        self,
        patch: PatchProposal,
        scope
    ) -> tuple[bool, str]:

        """Deny a proposal whose declared scope exceeds the authority.

        The proposal cannot expand its own authority: every entry the
        proposal claims as ``allowed_paths`` must itself be contained
        by the authoritative scope. This closes scope-confusion where a
        proposal smuggles a broader self-declared scope through the
        boundary while the target check alone would pass.
        """

        if not patch.allowed_paths:

            return True, ""

        for entry in patch.allowed_paths:

            in_scope, scope_message = (
                self.path_policy.check_scope(
                    entry,
                    scope
                )
            )

            if not in_scope:

                return (
                    False,
                    (
                        "Patch declared scope exceeds the "
                        f"authoritative scope: {scope_message}"
                    )
                )

        return True, ""
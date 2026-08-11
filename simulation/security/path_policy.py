import os

from pathlib import Path


class PathPolicy:

    """Fail-closed patch path scope policy.

    Enforced at validation time (PatchValidator) and again at the
    real write point (FileApplier) so every gate agrees on one rule set:

    R1 Input integrity
       path and every allowed_paths entry must be a non-empty string
       without NUL bytes. Missing or empty scope fails closed.

    R2 Absolute path policy
       Absolute and relative inputs are normalized to a canonical
       absolute form (symlinks resolved) before comparison, so a form
       mismatch can never bypass the scope check. A target that cannot
       be proven in scope is rejected.

    R3 Path traversal
       Any path component equal to ".." is rejected up front.

    R4 Scope containment
       The canonical target must equal or descend from at least one
       canonical allowed_paths entry.

    R5 Symlink escape
       Because R2 resolves symlinks, a symlink whose real target leaves
       the allowed scope fails R4 and is reported explicitly.
    """

    def check_scope(
        self,
        path,
        allowed_paths
    ) -> tuple[bool, str]:

        path_error = self._path_error(path)

        if path_error:

            return (
                False,
                path_error
            )

        scope_error = self._scope_error(
            allowed_paths
        )

        if scope_error:

            return (
                False,
                scope_error
            )

        if self._has_parent_component(path):

            return (
                False,
                "Patch path contains path traversal "
                "('..') and was rejected."
            )

        target = self._canonical(path)

        if target is None:

            return (
                False,
                "Patch path could not be resolved; "
                "rejected."
            )

        for entry in allowed_paths:

            allowed = self._canonical(entry)

            if allowed is None:

                continue

            if self._within(
                target,
                allowed
            ):

                return (
                    True,
                    "Patch path is within the allowed scope."
                )

        if self._is_symlink_escape(
            path,
            target
        ):

            return (
                False,
                "Patch path is outside the allowed scope "
                "(symlink escape rejected)."
            )

        return (
            False,
            "Patch path is outside the allowed scope."
        )

    def resolve_target(
        self,
        raw
    ) -> str | None:

        """Return the exact canonical form check_scope uses, or None.

        The caller (FileApplier) writes through this canonical target so
        the write goes to the same resolved path that was verified in
        scope, closing the gap between the scope check and the write.
        """

        if self._path_error(raw):

            return None

        return self._canonical(raw)

    def _path_error(
        self,
        path
    ):

        if not isinstance(path, str):

            return (
                "Patch path must be a string; "
                f"got {type(path).__name__}."
            )

        if not path:

            return "Patch path is empty."

        if "\x00" in path:

            return (
                "Patch path contains a null byte."
            )

        return None

    def _scope_error(
        self,
        allowed_paths
    ):

        if allowed_paths is None:

            return (
                "Patch scope is empty; "
                "allowed_paths must be provided."
            )

        if not isinstance(
            allowed_paths,
            (tuple, list)
        ):

            return (
                "Patch scope is empty; "
                "allowed_paths must be provided."
            )

        if not allowed_paths:

            return (
                "Patch scope is empty; "
                "allowed_paths must be provided."
            )

        for entry in allowed_paths:

            if (
                not isinstance(entry, str)
                or not entry
            ):

                return (
                    "Patch scope contains an "
                    "empty path entry."
                )

            if "\x00" in entry:

                return (
                    "Patch scope contains a "
                    "null byte."
                )

            if self._has_parent_component(entry):

                return (
                    "Patch scope contains path "
                    "traversal ('..')."
                )

        return None

    def _has_parent_component(
        self,
        raw
    ):

        return ".." in Path(raw).parts

    def _canonical(
        self,
        raw
    ):

        try:

            resolved = Path(raw).resolve(
                strict=False
            )

        except (OSError, RuntimeError):

            return None

        return os.path.normcase(
            str(resolved)
        )

    def _within(
        self,
        target,
        allowed
    ):

        if target == allowed:

            return True

        prefix = allowed.rstrip("\\/")

        return target.startswith(
            prefix + os.sep
        )

    def _is_symlink_escape(
        self,
        raw,
        target
    ):

        if self._lexical(raw) != target:

            return True

        return Path(raw).is_symlink()

    def _lexical(
        self,
        raw
    ):

        return os.path.normcase(
            os.path.abspath(
                os.path.normpath(
                    str(Path(raw))
                )
            )
        )

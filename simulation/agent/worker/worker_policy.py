class WorkerPolicy:

    ALLOWED_ACTIONS = {
        "read",
        "inspect",
        "propose",
    }

    def allows(self, action: str) -> bool:

        return action in self.ALLOWED_ACTIONS
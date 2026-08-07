class StrategyDispatcher:

    def dispatch(
        self,
        strategy: str,
        callbacks: dict
    ):

        callback = callbacks.get(strategy)

        if callback is None:

            raise ValueError(
                f"Unknown strategy: {strategy}"
            )

        return callback()
class ExecutorRegistry:
    """
    Central registry for executor instances.
    """

    def __init__(self):

        self._executors = {}

    def register(self, strategy, executor):

        self._executors[strategy] = executor

    def get(self, strategy):

        return self._executors.get(strategy)

    def exists(self, strategy):

        return strategy in self._executors

    def strategies(self):

        return sorted(self._executors.keys())
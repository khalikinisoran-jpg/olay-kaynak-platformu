class RuntimeService:

    def __init__(self, kernel):

        self.kernel = kernel

    def state(self):

        return self.kernel.get_state()

    def events(self):

        return self.kernel.event_count()
class LoopEngine:

    def __init__(self):

        self.goal = None

        self.status = "IDLE"

        self.iteration = 0

    def start(self, goal):

        self.goal = goal

        self.status = "RUNNING"

        self.iteration = 1

        print("=" * 50)
        print("LOOP ENGINE")
        print("=" * 50)
        print(f"Goal      : {self.goal}")
        print(f"Status    : {self.status}")
        print(f"Iteration : {self.iteration}")

    def next(self):

        self.iteration += 1

        print(f"Iteration : {self.iteration}")

    def verifying(self):

        self.status = "VERIFYING"

        print(f"Status    : {self.status}")

    def complete(self):

        self.status = "COMPLETED"

        print(f"Status    : {self.status}")

        print("=" * 50)

    def fail(self):

        self.status = "FAILED"

        print(f"Status    : {self.status}")

        print("=" * 50)
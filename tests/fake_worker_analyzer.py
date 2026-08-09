class FakeWorkerAnalyzer:

    def analyze(
        self,
        path,
        content,
        description
    ):

        old_text = content

        new_text = (
            content
            + "\n# Fake worker proposal marker\n"
        )

        return (
            "Fake analyzer produced a deterministic "
            "worker patch proposal.",
            old_text,
            new_text
        )
from simulation.agent.worker.analysis_result import (
    AnalysisResult
)


class FakeWorkerAnalyzer:

    def analyze(
        self,
        path,
        content,
        description
    ) -> AnalysisResult:

        old_text = content

        new_text = (
            content
            + "\n# Fake worker proposal marker\n"
        )

        return AnalysisResult(
            diagnosis=(
                "Fake analyzer produced a deterministic "
                "worker patch proposal."
            ),
            old_text=old_text,
            new_text=new_text,
            confidence=0.9,
            risk="LOW",
        )

"""MISSION-019 benchmark: GovernanceEvaluator and apply-outcome journal.

Measures the overhead of the single governance authority and the apply
journal write path. Local sanity numbers only -- not a production
benchmark.
"""

import os
import sys
import time

from pathlib import Path

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
        )
    ),
)

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.apply_outcome_journal import (
    ApplyOutcomeJournal,
)
from simulation.agent.controller.controller_decision import (
    ControllerDecision
)
from simulation.security.governance_evaluator import GovernanceEvaluator
from simulation.agent.worker.patch_proposal import PatchProposal


def make_patch(tmp_path, name="notes.txt"):
    target = tmp_path / name
    target.write_text("value = 1\n", encoding="utf-8")
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Benchmark patch.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def bench(fn, repeat):
    start = time.perf_counter()
    for _ in range(repeat):
        fn()
    elapsed = time.perf_counter() - start
    return elapsed, (repeat / elapsed)


def main():
    import tempfile
    from pathlib import Path

    workdir = Path(tempfile.mkdtemp())

    evaluator = GovernanceEvaluator()
    patch = make_patch(workdir)
    decision = ControllerDecision(
        approved=True,
        reason="Benchmark.",
        patch_fingerprint=patch.fingerprint(),
    )

    elapsed, rate = bench(
        lambda: evaluator.evaluate(patch),
        20000,
    )
    print(f"GovernanceEvaluator.evaluate : {elapsed:.3f}s  {rate:,.0f} evals/s")

    elapsed, rate = bench(
        lambda: evaluator.classify(patch),
        20000,
    )
    print(f"GovernanceEvaluator.classify  : {elapsed:.3f}s  {rate:,.0f} evals/s")

    journal = ApplyOutcomeJournal(
        path=workdir / "apply_journal.jsonl"
    )

    def journal_write():
        intent_id = journal.record_intent(patch, attempt=1)
        journal.record_apply_started(intent_id)
        journal.record_applied(intent_id)
        journal.record_verified(intent_id)

    elapsed, rate = bench(journal_write, 2000)
    print(f"ApplyOutcomeJournal full cycle: {elapsed:.3f}s  {rate:,.0f} cycles/s")

    executor = ApplyExecutor(journal=journal)

    target = Path(patch.path)

    def apply_write():
        target.write_text("value = 1\n", encoding="utf-8")
        executor.apply(patch, decision)

    elapsed, rate = bench(apply_write, 500)
    print(f"ApplyExecutor.apply + journal : {elapsed:.3f}s  {rate:,.0f} applies/s")

    records = journal.load()
    print(f"Journal load/verify          : {len(records)} records verified")

    print(f"workdir                       : {workdir}")


if __name__ == "__main__":
    main()

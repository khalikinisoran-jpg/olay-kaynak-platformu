import os

import pytest

from simulation.agent.worker.llm_code_analyzer import (
    LLMCodeAnalyzer
)

from simulation.agent.worker.worker_agent import (
    WorkerAgent
)

from simulation.agent.worker.worker_task import (
    WorkerTask
)


pytestmark = pytest.mark.live_llm

REQUIRES_LIVE_LLM = (
    os.getenv("RUN_LIVE_LLM") != "1"
)

LIVE_REASON = (
    "RUN_LIVE_LLM=1 required; this test performs "
    "a real LLM provider call and may incur API cost. "
    "Run deliberately with: "
    "python -m pytest -m live_llm "
    "tests/llm_provider_integration_test.py -q"
)


@pytest.mark.skipif(
    REQUIRES_LIVE_LLM,
    reason=LIVE_REASON,
)
def test_real_llm_produces_proposal_in_memory():

    analyzer = LLMCodeAnalyzer()

    content = (
        "def add(a, b):\n"
        "    return a - b\n"
    )

    diagnosis, old_text, new_text = (
        analyzer.analyze(
            path="synthetic_proposal.py",
            content=content,
            description=(
                "The add function is wrong. "
                "It must return the sum of a and b. "
                "Make the smallest possible change."
            ),
        )
    )

    assert isinstance(diagnosis, str)

    assert diagnosis.strip()

    assert isinstance(old_text, str)

    assert old_text.strip()

    assert content.count(old_text) == 1

    assert isinstance(new_text, str)

    assert new_text.strip()

    assert new_text != old_text


@pytest.mark.skipif(
    REQUIRES_LIVE_LLM,
    reason=LIVE_REASON,
)
def test_real_worker_llm_proposal_only_chain(tmp_path):

    target = tmp_path / "synthetic_target.py"

    original = (
        "def is_even(n):\n"
        "    return n % 2 == 1\n"
    )

    target.write_text(
        original,
        encoding="utf-8"
    )

    worker = WorkerAgent(
        analyzer=LLMCodeAnalyzer()
    )

    task = WorkerTask(
        task_id="live-llm-worker",
        description=(
            "The is_even function is wrong. "
            "It must return True when n is even. "
            "Make the smallest possible change."
        ),
        allowed_paths=(str(target),),
        allowed_actions=(
            "read",
            "inspect",
            "propose",
        ),
        expected_output="patch proposal",
    )

    result = worker.run(task)

    assert result.success is True

    assert result.patches

    patch = result.patches[0]

    assert patch.path == str(target)

    assert patch.old_content != patch.new_content

    assert target.read_text(
        encoding="utf-8"
    ) == original

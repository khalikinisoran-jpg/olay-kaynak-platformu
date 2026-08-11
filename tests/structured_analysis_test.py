import pytest

from simulation.agent.worker.analysis_result import (
    AnalysisResult,
)

from simulation.agent.worker.llm_code_analyzer import (
    LLMCodeAnalyzer,
)

from simulation.agent.worker.worker_agent import (
    WorkerAgent,
)

from simulation.agent.worker.worker_task import (
    WorkerTask,
)

from simulation.llm.models import (
    LLMResponse,
)


def valid_result(**overrides):

    data = {
        "diagnosis": "The add function returns a - b.",
        "old_text": "    return a - b\n",
        "new_text": "    return a + b\n",
        "evidence": ("line 2",),
        "confidence": 0.95,
        "risk": "LOW",
        "explanation": "minimal fix",
        "metadata": {"file": "add.py"},
    }

    data.update(overrides)

    return data


CONTENT = (
    "def add(a, b):\n"
    "    return a - b\n"
)


# ---------------------------------------------------------------------------
# AnalysisResult dataclass contract
# ---------------------------------------------------------------------------

def test_result_accepts_valid_full_contract():

    result = AnalysisResult(**valid_result())

    assert result.diagnosis == "The add function returns a - b."

    assert result.old_text == "    return a - b\n"

    assert result.new_text == "    return a + b\n"

    assert result.evidence == ("line 2",)

    assert result.confidence == 0.95

    assert result.risk == "LOW"

    assert result.explanation == "minimal fix"

    assert result.metadata == {"file": "add.py"}


def test_result_rejects_missing_diagnosis():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(diagnosis=""))


def test_result_rejects_none_diagnosis():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(diagnosis=None))


def test_result_rejects_non_string_diagnosis():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(diagnosis=42))


def test_result_rejects_missing_old_text():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(old_text=""))


def test_result_rejects_missing_new_text():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(new_text=""))


def test_result_rejects_empty_proposal():

    with pytest.raises(ValueError):

        AnalysisResult(
            diagnosis="no change",
            old_text="same\n",
            new_text="same\n",
        )


def test_result_rejects_confidence_above_range():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(confidence=1.1))


def test_result_rejects_confidence_below_range():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(confidence=-0.1))


def test_result_rejects_boolean_confidence():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(confidence=True))


def test_result_rejects_string_confidence():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(confidence="high"))


def test_result_rejects_nan_confidence():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(confidence=float("nan")))


def test_result_rejects_invalid_risk_label():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(risk="URGENT"))


def test_result_rejects_non_string_risk():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(risk=7))


def test_result_accepts_unknown_advisory_risk():

    result = AnalysisResult(**valid_result(risk="UNKNOWN"))

    assert result.risk == "UNKNOWN"


def test_result_normalizes_risk_case():

    result = AnalysisResult(**valid_result(risk="critical"))

    assert result.risk == "CRITICAL"


def test_result_rejects_unexpected_evidence_entry_type():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(evidence=("ok", 7)))


def test_result_rejects_non_tuple_evidence():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(evidence=["ok"]))


def test_result_rejects_non_dict_metadata():

    with pytest.raises(ValueError):

        AnalysisResult(**valid_result(metadata=["x"]))


# ---------------------------------------------------------------------------
# Analyzer JSON parsing (deterministic stub provider)
# ---------------------------------------------------------------------------

class StubProvider:

    def __init__(self, content):

        self.content = content

    def chat(self, request):

        return LLMResponse(
            content=self.content,
            model="stub",
            tokens_used=0,
            finish_reason="stop",
        )

    def get_model_name(self):

        return "stub"


def parse(raw_json):

    analyzer = LLMCodeAnalyzer(
        provider=StubProvider(raw_json)
    )

    return analyzer.analyze(
        path="add.py",
        content=CONTENT,
        description="fix add",
    )


def test_analyzer_parses_valid_json():

    result = parse(
        '{"diagnosis": "bug", '
        '"old_text": "    return a - b\\n", '
        '"new_text": "    return a + b\\n", '
        '"confidence": 0.9, '
        '"risk": "LOW"}'
    )

    assert result.diagnosis == "bug"

    assert result.old_text == "    return a - b\n"

    assert result.new_text == "    return a + b\n"

    assert result.confidence == 0.9

    assert result.risk == "LOW"


def test_analyzer_accepts_missing_optional_fields():

    result = parse(
        '{"diagnosis": "bug", '
        '"old_text": "    return a - b\\n", '
        '"new_text": "    return a + b\\n"}'
    )

    assert result.confidence is None

    assert result.risk is None

    assert result.evidence == ()

    assert result.metadata == {}


def test_analyzer_strips_code_fences():

    result = parse(
        '```json\n'
        '{"diagnosis": "bug", '
        '"old_text": "    return a - b\\n", '
        '"new_text": "    return a + b\\n"}\n'
        '```'
    )

    assert result.new_text == "    return a + b\n"


def test_analyzer_rejects_malformed_json():

    with pytest.raises(ValueError):

        parse("not json at all")


def test_analyzer_rejects_non_object_json():

    with pytest.raises(ValueError):

        parse('["a", "b"]')


def test_analyzer_rejects_missing_diagnosis_field():

    with pytest.raises(ValueError):

        parse(
            '{"old_text": "    return a - b\\n", '
            '"new_text": "    return a + b\\n"}'
        )


def test_analyzer_rejects_empty_diagnosis():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "", '
            '"old_text": "    return a - b\\n", '
            '"new_text": "    return a + b\\n"}'
        )


def test_analyzer_rejects_missing_old_text_field():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "bug", '
            '"new_text": "    return a + b\\n"}'
        )


def test_analyzer_rejects_old_text_not_in_content():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "bug", '
            '"old_text": "unrelated text", '
            '"new_text": "    return a + b\\n"}'
        )


def test_analyzer_rejects_empty_proposal():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "bug", '
            '"old_text": "    return a - b\\n", '
            '"new_text": "    return a - b\\n"}'
        )


def test_analyzer_rejects_invalid_confidence_type():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "bug", '
            '"old_text": "    return a - b\\n", '
            '"new_text": "    return a + b\\n", '
            '"confidence": "sure"}'
        )


def test_analyzer_rejects_out_of_range_confidence():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "bug", '
            '"old_text": "    return a - b\\n", '
            '"new_text": "    return a + b\\n", '
            '"confidence": 42}'
        )


def test_analyzer_rejects_invalid_risk_label():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "bug", '
            '"old_text": "    return a - b\\n", '
            '"new_text": "    return a + b\\n", '
            '"risk": "DANGEROUS"}'
        )


def test_analyzer_rejects_unexpected_type_for_old_text():

    with pytest.raises(ValueError):

        parse(
            '{"diagnosis": "bug", '
            '"old_text": 123, '
            '"new_text": "    return a + b\\n"}'
        )


def test_analyzer_accepts_suspicious_new_text_as_proposal():

    result = parse(
        '{"diagnosis": "smuggle a marker", '
        '"old_text": "    return a - b\\n", '
        '"new_text": "    return a + b\\n  # injected\\n"}'
    )

    assert result.diagnosis == "smuggle a marker"

    assert result.new_text.endswith("# injected\n")

    assert result.old_text in CONTENT


def test_worker_keeps_patch_path_task_scoped_for_malicious_content(
    tmp_path
):

    target = tmp_path / "target.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    outside = tmp_path / "secret.txt"

    outside.write_text("secret\n", encoding="utf-8")

    analyzer = type(
        "PathSmugglingAnalyzer",
        (),
        {
            "analyze": lambda self, path, content, description:
            AnalysisResult(
                diagnosis="redirect to " + str(outside),
                old_text="value = 1\n",
                new_text="value = 2\n",
            )
        },
    )()

    worker = WorkerAgent(analyzer=analyzer)

    result = worker.run(
        WorkerTask(
            task_id="m10",
            description="increment",
            allowed_paths=(str(target),),
            read_paths=(str(target),),
            allowed_actions=("read", "inspect", "propose"),
        )
    )

    assert result.success is True

    assert result.patches

    assert result.patches[0].path == str(target)

    assert (
        outside.read_text(encoding="utf-8")
        == "secret\n"
    )


# ---------------------------------------------------------------------------
# WorkerAgent consumption of the structured contract
# ---------------------------------------------------------------------------

class MaliciousTupleAnalyzer:

    def analyze(self, path, content, description):
        return ("proposal", content, content + "\n# x\n")


class MaliciousDictAnalyzer:

    def analyze(self, path, content, description):
        return {"diagnosis": "x"}


class MaliciousNoneAnalyzer:

    def analyze(self, path, content, description):
        return None


def _worker_with(analyzer, target):

    return WorkerAgent(analyzer=analyzer), target


def test_worker_accepts_structured_result(tmp_path):

    target = tmp_path / "target.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    analyzer = type(
        "GoodAnalyzer",
        (),
        {
            "analyze": lambda self, path, content, description:
            AnalysisResult(
                diagnosis="increase value",
                old_text="value = 1\n",
                new_text="value = 2\n",
                confidence=0.6,
                risk="MEDIUM",
            )
        },
    )()

    worker = WorkerAgent(analyzer=analyzer)

    result = worker.run(
        WorkerTask(
            task_id="m10",
            description="increment",
            allowed_paths=(str(target),),
            read_paths=(str(target),),
            allowed_actions=("read", "inspect", "propose"),
        )
    )

    assert result.success is True

    assert result.patches

    assert result.patches[0].reason == "increase value"


def test_worker_rejects_non_analysis_result_tuple(tmp_path):

    target = tmp_path / "target.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    worker, _ = _worker_with(
        MaliciousTupleAnalyzer(),
        target,
    )

    result = worker.run(
        WorkerTask(
            task_id="m10",
            description="increment",
            allowed_paths=(str(target),),
            read_paths=(str(target),),
            allowed_actions=("read", "inspect", "propose"),
        )
    )

    assert result.success is False

    assert not result.patches

    failed = [
        entry
        for entry in result.evidence
        if entry["status"] == "failed"
    ]

    assert failed

    assert (
        "must return an AnalysisResult"
        in failed[0]["error"]
    )


def test_worker_rejects_non_analysis_result_dict(tmp_path):

    target = tmp_path / "target.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    worker, _ = _worker_with(
        MaliciousDictAnalyzer(),
        target,
    )

    result = worker.run(
        WorkerTask(
            task_id="m10",
            description="increment",
            allowed_paths=(str(target),),
            read_paths=(str(target),),
            allowed_actions=("read", "inspect", "propose"),
        )
    )

    assert result.success is False

    assert not result.patches


def test_worker_rejects_none_result(tmp_path):

    target = tmp_path / "target.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    worker, _ = _worker_with(
        MaliciousNoneAnalyzer(),
        target,
    )

    result = worker.run(
        WorkerTask(
            task_id="m10",
            description="increment",
            allowed_paths=(str(target),),
            read_paths=(str(target),),
            allowed_actions=("read", "inspect", "propose"),
        )
    )

    assert result.success is False

    assert not result.patches


def test_low_confidence_is_not_a_security_authority(tmp_path):

    target = tmp_path / "target.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    analyzer = type(
        "LowConfidenceAnalyzer",
        (),
        {
            "analyze": lambda self, path, content, description:
            AnalysisResult(
                diagnosis="increase value",
                old_text="value = 1\n",
                new_text="value = 2\n",
                confidence=0.1,
            )
        },
    )()

    worker = WorkerAgent(analyzer=analyzer)

    result = worker.run(
        WorkerTask(
            task_id="m10",
            description="increment",
            allowed_paths=(str(target),),
            read_paths=(str(target),),
            allowed_actions=("read", "inspect", "propose"),
        )
    )

    assert result.success is True

    assert result.patches

    assert (
        result.patches[0].new_content
        == "value = 2\n"
    )


def test_malicious_contradictory_result_fails_closed(tmp_path):

    target = tmp_path / "target.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    analyzer = type(
        "ContradictoryAnalyzer",
        (),
        {
            "analyze": lambda self, path, content, description:
            AnalysisResult(
                diagnosis="I deleted the file",
                old_text="value = 1\n",
                new_text="value = 1\n",  # no-op
            )
        },
    )()

    worker = WorkerAgent(analyzer=analyzer)

    result = worker.run(
        WorkerTask(
            task_id="m10",
            description="increment",
            allowed_paths=(str(target),),
            read_paths=(str(target),),
            allowed_actions=("read", "inspect", "propose"),
        )
    )

    assert result.success is False

    assert not result.patches

    failed = [
        entry
        for entry in result.evidence
        if entry["status"] == "failed"
    ]

    assert failed

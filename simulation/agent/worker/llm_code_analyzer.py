import json

from simulation.llm.models import Message, LLMRequest
from simulation.llm.provider_factory import ProviderFactory


class LLMCodeAnalyzer:

    def __init__(self):

        self.provider = ProviderFactory.create()

    def analyze(
        self,
        path: str,
        content: str,
        description: str
    ):

        prompt = (
            "You are a precise code debugging engine.\n\n"
            "Analyze the supplied source file.\n\n"
            "TASK:\n"
            + description
            + "\n\n"
            "FILE PATH:\n"
            + path
            + "\n\n"
            "SOURCE:\n"
            + content
            + "\n\n"
            "Return ONLY valid JSON.\n\n"
            "Use exactly these fields:\n"
            "{\n"
            '  "diagnosis": "explain the bug",\n'
            '  "old_text": "exact text that must be replaced",\n'
            '  "new_text": "replacement text"\n'
            "}\n\n"
            "Rules:\n"
            "1. old_text must be copied exactly from the supplied source.\n"
            "2. new_text must contain only the required replacement.\n"
            "3. Keep the change as small as possible.\n"
            "4. Do not modify unrelated code.\n"
            "5. Do not include Markdown.\n"
            "6. Do not include code fences.\n"
            "7. Do not write to the filesystem."
        )

        request = LLMRequest(
            messages=[
                Message(
                    role="system",
                    content=(
                        "You are a precise software debugging "
                        "and minimal patch analysis engine."
                    )
                ),
                Message(
                    role="user",
                    content=prompt
                )
            ],
            temperature=0.0,
            max_tokens=2000
        )

        response = self.provider.chat(request)

        raw = response.content.strip()

        if raw.startswith("```"):

            lines = raw.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            raw = "\n".join(lines).strip()

        data = json.loads(raw)

        diagnosis = data.get("diagnosis")
        old_text = data.get("old_text")
        new_text = data.get("new_text")

        if not diagnosis:
            raise ValueError(
                "LLM response does not contain diagnosis."
            )

        if old_text is None:
            raise ValueError(
                "LLM response does not contain old_text."
            )

        if new_text is None:
            raise ValueError(
                "LLM response does not contain new_text."
            )

        if not old_text:
            raise ValueError(
                "LLM old_text is empty."
            )

        if old_text not in content:
            raise ValueError(
                "LLM old_text does not exist "
                "in the current file content."
            )

        if old_text == new_text:
            raise ValueError(
                "LLM did not produce a change."
            )

        return (
            diagnosis,
            old_text,
            new_text
        )
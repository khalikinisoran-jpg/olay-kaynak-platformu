import re


class Planner:

    def plan(
        self,
        user_input: str
    ):

        text = user_input.lower().strip()

        if re.search(
            r"\d+\s*[\+\-\*/]\s*\d+",
            text
        ):

            return {

                "strategy": "calculator",

                "steps": [

                    "execute_calculator"

                ]

            }

        if any(

            word in text

            for word in [

                "hava",

                "weather",

                "sıcaklık",

                "yağmur"

            ]

        ):

            return {

                "strategy": "weather",

                "steps": [

                    "execute_weather"

                ]

            }

        return {

            "strategy": "llm",

            "steps": [

                "generate_response"

            ]

        }
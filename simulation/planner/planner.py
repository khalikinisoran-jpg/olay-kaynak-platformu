import re


class Planner:

    def plan(
        self,
        user_input: str
    ):

        text = user_input.lower().strip()

        # Calculator

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

        # Weather

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

        # Memory

        if any(

            phrase in text

            for phrase in [

                "benim adım",

                "adım",

                "beni",

                "ben "

            ]

        ):

            return {

                "strategy": "memory",

                "steps": [

                    "store_memory"

                ]

            }

        # Default

        return {

            "strategy": "llm",

            "steps": [

                "generate_response"

            ]

        }
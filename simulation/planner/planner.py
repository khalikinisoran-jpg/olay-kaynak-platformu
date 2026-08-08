import re


class Planner:

    def plan(
        self,
        user_input: str
    ):

        text = user_input.lower().strip()

        # -----------------------------------
        # Calculator
        # -----------------------------------

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

        # -----------------------------------
        # Weather
        # -----------------------------------

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

        # -----------------------------------
        # Memory Recall
        # -----------------------------------

        if any(
            phrase in text
            for phrase in [
                "benim adım ne",
                "adımı söyle",
                "ismim ne"
            ]
        ):

            return {
                "strategy": "memory_recall",
                "steps": [
                    "recall_memory"
                ]
            }

        # -----------------------------------
        # Memory Store
        # -----------------------------------

        if "benim adım" in text:

            return {
                "strategy": "memory_store",
                "steps": [
                    "store_memory"
                ]
            }

        # -----------------------------------
        # Worker
        # -----------------------------------

        if text.startswith("worker:"):

            return {
                "strategy": "worker",
                "steps": [
                    "execute_worker"
                ]
            }

        # -----------------------------------
        # Default
        # -----------------------------------

        return {
            "strategy": "llm",
            "steps": [
                "generate_response"
            ]
        }
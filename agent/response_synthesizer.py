import json
from openai import OpenAI
from agent.prompt_library import PromptLibrary
from agent import llm_client


class ResponseSynthesizer:

    def __init__(self, prompt_library: PromptLibrary, client: OpenAI):
        self.prompts = prompt_library
        self.client = client

    def synthesize(self, question: str, merged_results: dict, query_trace: dict) -> str:
        """Merge DB results into a human-readable answer via LLM."""
        prompt = self.prompts.synthesize_response(question, merged_results, query_trace)
        return llm_client.call(self.client, prompt, max_tokens=512)

    def extract_from_text(self, text_field: str, extraction_goal: str) -> dict:
        """Extract structured data from a free-text field (reviews, tips, descriptions)."""
        prompt = self.prompts.text_extraction(text_field, extraction_goal)
        raw = llm_client.call(self.client, prompt, max_tokens=512)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw, "parse_error": "LLM did not return valid JSON"}

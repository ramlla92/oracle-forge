import os
from openai import OpenAI


def get_client() -> OpenAI:
    """Return an OpenAI-compatible client pointed at OpenRouter."""
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPEN_ROUTER_KEY"],
    )


def call(client: OpenAI, prompt: str, system: str = "", max_tokens: int = 1024,
         model: str = "anthropic/claude-opus-4-6") -> str:
    """Single LLM call. Returns the response text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content.strip()

from datetime import datetime


class StateManager:
    """Manages conversation history with token-based truncation.

    Keeps the last N interactions in memory and serialises them
    as a compact context string for injection into LLM prompts.
    Token budget is estimated at 1 token ≈ 4 characters.
    """

    MAX_HISTORY = 10
    SUMMARY_LIMIT = 5  # How many recent items to include in context string

    def __init__(self, token_budget: int = 1000):
        self.token_budget = token_budget
        self._history: list[dict] = []

    def add(self, question: str, answer: str, databases_used: list[str],
            had_correction: bool = False):
        self._history.append({
            "question": question,
            "answer_summary": answer[:200],
            "databases_used": databases_used,
            "had_correction": had_correction,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._history = self._history[-self.MAX_HISTORY:]

    def get_context(self) -> str:
        if not self._history:
            return ""
        recent = self._history[-self.SUMMARY_LIMIT:]
        lines = ["## Conversation History (recent queries)"]
        for h in recent:
            correction_flag = " [self-corrected]" if h["had_correction"] else ""
            dbs = ", ".join(h["databases_used"])
            lines.append(f"- Q: {h['question']}")
            lines.append(f"  A: {h['answer_summary']}{correction_flag} (DBs: {dbs})")
        context = "\n".join(lines)

        # Truncate to token budget
        char_limit = self.token_budget * 4
        if len(context) > char_limit:
            context = context[:char_limit] + "\n...[history truncated]"
        return context

    def clear(self):
        self._history = []

    @property
    def turn_count(self) -> int:
        return len(self._history)

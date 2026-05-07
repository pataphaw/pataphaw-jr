from src.conversation.history_store import HistoryStore
from src.logging_config import get_logger

logger = get_logger("conversation")


class ConversationManager:
    def __init__(self, store: HistoryStore = None):
        self.store = store or HistoryStore()

    def add_user(self, text: str):
        logger.debug(f"add_user: {text[:50]}..." if len(text) > 50 else f"add_user: {text}")
        self.store.add("user", text)

    def add_assistant(self, text: str):
        logger.debug(f"add_assistant: {text[:50]}..." if len(text) > 50 else f"add_assistant: {text}")
        self.store.add("assistant", text)

    def get_history(self, days: int = 7) -> list[dict]:
        return self.store.load_recent(days)

    def format_for_llm(self, history: list[dict]) -> str:
        if not history:
            return "（无历史对话）"
        lines = []
        for e in history:
            role = "用户" if e["role"] == "user" else "助手"
            lines.append(f"{role}：{e['content']}")
        return "\n".join(lines)
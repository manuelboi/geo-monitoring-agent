"""Short-term memory of each conversation, kept in this process only (lost on restart)."""

import threading
from collections import OrderedDict, deque


class ConversationMemory:
    def __init__(self, max_exchanges: int = 3, max_conversations: int = 1000):
        self.max_exchanges = max_exchanges
        self.max_conversations = max_conversations
        self._conversations: OrderedDict[str, deque] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, conversation_id: str | None) -> list[tuple[str, str]]:
        if not conversation_id:
            return []
        with self._lock:
            return list(self._conversations.get(conversation_id, ()))

    def add(self, conversation_id: str | None, question: str, answer: str) -> None:
        if not conversation_id:
            return
        with self._lock:
            exchanges = self._conversations.pop(conversation_id, None) or deque(maxlen=self.max_exchanges)
            exchanges.append((question, answer))
            # Re-inserting moves the conversation to the end: the first one is the least recently used
            self._conversations[conversation_id] = exchanges
            if len(self._conversations) > self.max_conversations:
                self._conversations.popitem(last=False)

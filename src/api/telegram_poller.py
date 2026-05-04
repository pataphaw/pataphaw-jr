import asyncio
import httpx
import yaml
from pathlib import Path

from src.conversation.manager import ConversationManager
from src.conversation.history_store import HistoryStore
from src.llm.parser import OllamaLLMParser, get_llm_parser
from src.router.ha_router import HARouter, HomeAssistantClient


class TelegramPoller:
    def __init__(
        self,
        bot_token: str,
        llm_parser: OllamaLLMParser = None,
        ha_router: HARouter = None,
        conv_manager: ConversationManager = None,
    ):
        self.bot_token = bot_token
        self.llm = llm_parser
        self.router = ha_router
        self.conv = conv_manager
        self.offset = 0
        self._running = False
        self._task = None

    async def start(self):
        self._running = True
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{self.bot_token}/getUpdates",
                params={"limit": 1, "offset": -1}
            )
            data = resp.json()
            if data.get("ok") and data.get("result"):
                self.offset = data["result"][-1]["update_id"] + 1

        self._task = asyncio.create_task(self._poll())
        print(f"[telegram] Polling started (offset={self.offset})")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[telegram] Polling stopped")

    async def _poll(self):
        while self._running:
            try:
                async with httpx.AsyncClient(timeout=35) as client:
                    resp = await client.get(
                        f"https://api.telegram.org/bot{self.bot_token}/getUpdates",
                        params={"offset": self.offset, "timeout": 30}
                    )
                    data = resp.json()
                    if data.get("ok") and data.get("result"):
                        for update in data["result"]:
                            await self._handle_update(update)
                            self.offset = update["update_id"] + 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[telegram] Poll error: {e}")
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict):
        message = update.get("message")
        if not message:
            return

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        if not text:
            return

        self.conv.add_user(text)

        history = self.conv.get_history()
        history_text = self.conv.format_for_llm(history)

        parsed = await self.llm.parse(text, history_text, chat_id)

        intent = parsed.get("intent", "unknown")
        entity_id = parsed.get("entity_id")
        params = parsed.get("params", {})
        reply = parsed.get("reply", "收到指令")

        if intent != "unknown" and entity_id:
            response_text, result = await self.router.route(intent, entity_id, params)
        else:
            response_text = reply

        self.conv.add_assistant(response_text)

        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": response_text}
            )
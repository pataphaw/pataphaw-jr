import asyncio
import httpx
import yaml
from pathlib import Path

from src.conversation.manager import ConversationManager
from src.conversation.history_store import HistoryStore
from src.llm.parser import OllamaLLMParser, get_llm_parser
from src.router.ha_router import HARouter, HomeAssistantClient
from src.logging_config import get_logger

logger = get_logger("telegram")


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
        logger.info(f"Polling started (offset={self.offset})")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Polling stopped")

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
                        logger.debug(f"Polling OK, updates_count={len(data['result'])}")
                        for update in data["result"]:
                            await self._handle_update(update)
                            self.offset = update["update_id"] + 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict):
        message = update.get("message")
        if not message:
            return

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        if not text:
            return

        logger.info(f"Message received: chat_id={chat_id}, text=\"{text}\"")

        try:
            self.conv.add_user(text)
            logger.debug("User message stored to conversation history")

            history = self.conv.get_history()
            history_text = self.conv.format_for_llm(history)

            logger.info("Calling LLM for intent parsing...")
            parsed = await self.llm.parse(text, history_text, chat_id)

            intent = parsed.get("intent", "unknown")
            entity_id = parsed.get("entity_id")
            params = parsed.get("params", {})
            reply = parsed.get("reply", "收到指令")

            logger.info(f"LLM parsed: intent={intent}, entity_id={entity_id}, params={params}")

            if intent != "unknown" and entity_id:
                logger.info(f"Routing: intent={intent}, entity_id={entity_id}")
                response_text, result = await self.router.route(intent, entity_id, params)
                logger.info(f"HA router response: {response_text}")
            else:
                response_text = reply
                logger.info("No routing needed, using LLM reply directly")

            self.conv.add_assistant(response_text)
            logger.debug("Assistant reply stored to conversation history")

            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": response_text}
                )
                logger.info(f"Reply sent to chat_id={chat_id}")
        except Exception as e:
            logger.error(f"Handle update error: {e}", exc_info=True)
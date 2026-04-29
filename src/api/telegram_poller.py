import asyncio
import httpx
from src.services.ac_controller import AcController


class TelegramPoller:
    def __init__(self, bot_token: str, ac_controller: AcController):
        self.bot_token = bot_token
        self.ac = ac_controller
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

        response_text, _ = await self.ac.execute(text)

        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": response_text}
            )

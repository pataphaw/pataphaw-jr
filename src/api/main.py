from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import httpx
import yaml
import json
from pathlib import Path

from src.api.telegram_poller import TelegramPoller
from src.conversation.manager import ConversationManager
from src.conversation.history_store import HistoryStore
from src.llm.parser import get_llm_parser
from src.router.ha_router import HARouter, HomeAssistantClient


app = FastAPI(title="pataphaw-jr", version="0.1.0")

config = yaml.safe_load(Path("config.yaml").read_text())
telegram_config = config.get("telegram", {})
feishu_config = config.get("feishu", {})

conv_manager = ConversationManager(store=HistoryStore())
ha_client = HomeAssistantClient()
ha_router = HARouter(ha_client)
llm_parser = None
telegram_poller: TelegramPoller = None


@app.on_event("startup")
async def startup():
    global telegram_poller, llm_parser
    bot_token = telegram_config.get("bot_token")
    if bot_token:
        llm_parser = await get_llm_parser()
        telegram_poller = TelegramPoller(
            bot_token=bot_token,
            llm_parser=llm_parser,
            ha_router=ha_router,
            conv_manager=conv_manager,
        )
        await telegram_poller.start()


@app.on_event("shutdown")
async def shutdown():
    if telegram_poller:
        await telegram_poller.stop()


class FeishuEvent(BaseModel):
    encrypt: str = None
    challenge: str = None
    event: dict = None


@app.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    if not feishu_config.get("app_id"):
        return {"error": "Feishu not configured"}

    body = await request.json()

    if feishu_config.get("encrypt_key") and body.get("encrypt"):
        decrypted = decrypt_feishu(body["encrypt"], feishu_config["encrypt_key"])
        if not decrypted:
            raise HTTPException(status_code=400, detail="Decryption failed")
        body = json.loads(decrypted)

    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    if event.get("type") == "message":
        message = event.get("message", {})
        content = message.get("content", "{}")
        text = json.loads(content).get("text", "")

        chat_id = event.get("chat_id")

        conv_manager.add_user(text)
        history = conv_manager.get_history()
        history_text = conv_manager.format_for_llm(history)

        if llm_parser is None:
            llm_parser = await get_llm_parser()

        parsed = await llm_parser.parse(text, history_text, chat_id)
        intent = parsed.get("intent", "unknown")
        entity_id = parsed.get("entity_id")
        params = parsed.get("params", {})
        reply = parsed.get("reply", "收到指令")

        if intent != "unknown" and entity_id:
            response_text, _ = await ha_router.route(intent, entity_id, params)
        else:
            response_text = reply

        conv_manager.add_assistant(response_text)

        await send_feishu_message(chat_id, response_text, feishu_config)

    return {"ok": True}


def decrypt_feishu(encrypted: str, key: str) -> str:
    try:
        from cryptography.hazmat.primitives.cipher import AES
        from cryptography.hazmat.primitives.padding import PKCS7
        import binascii

        key_bytes = key.encode("utf-8")[:32].ljust(32, b"\0")
        iv = encrypted[:16].encode("utf-8")
        encrypted_data = encrypted[16:]

        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(binascii.unhexlify(encrypted_data))
        decrypted = decrypted.rstrip(b"\0")

        return decrypted.decode("utf-8")
    except Exception:
        return None


async def send_feishu_message(chat_id: str, text: str, config: dict):
    async with httpx.AsyncClient(proxies={"http://": None, "https://": None}, timeout=30) as client:
        token_resp = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": config["app_id"],
                "app_secret": config["app_secret"]
            }
        )
        token_data = token_resp.json()
        access_token = token_data.get("tenant_access_token")

        if not access_token:
            return

        await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text})
            },
            headers={"Authorization": f"Bearer {access_token}"}
        )


@app.get("/health")
async def health():
    return {"status": "ok"}
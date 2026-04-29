from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import httpx
import yaml
import json
from pathlib import Path

from src.services.ac_controller import AcController
from src.api.telegram_poller import TelegramPoller

app = FastAPI(title="pataphaw-jr", version="0.1.0")

config = yaml.safe_load(Path("config.yaml").read_text())
telegram_config = config.get("telegram", {})
feishu_config = config.get("feishu", {})

ac_controller = AcController()
telegram_poller: TelegramPoller = None


@app.on_event("startup")
async def startup():
    global telegram_poller
    bot_token = telegram_config.get("bot_token")
    if bot_token:
        telegram_poller = TelegramPoller(bot_token, ac_controller)
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

        response_text, _ = await ac_controller.execute(text)

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


@app.post("/api/ac/control")
async def control_ac(text: str):
    try:
        response_text, result = await ac_controller.execute(text)
        return {"response": response_text, "result": result}
    except Exception as e:
        return {"response": f"执行失败: {str(e)}", "result": None}

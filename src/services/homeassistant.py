import httpx
import yaml
import os
from pathlib import Path


class HomeAssistantClient:
    def __init__(self, config_path: str = "config.yaml"):
        config = yaml.safe_load(Path(config_path).read_text())
        self.base_url = config["homeassistant"]["base_url"]
        self.access_token = config["homeassistant"]["access_token"]

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def call_service(self, domain: str, service: str, data: dict):
        url = f"{self.base_url}/api/services/{domain}/{service}"
        async with httpx.AsyncClient(
            proxies={"http://": None, "https://": None},
            timeout=30
        ) as client:
            response = await client.post(url, headers=self._headers(), json=data)
            response.raise_for_status()
            return response.json()

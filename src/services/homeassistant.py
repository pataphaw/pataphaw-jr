import httpx
import yaml
import os
from pathlib import Path


class HomeAssistantClient:
    def __init__(self, config_path: str = "config.yaml"):
        config = yaml.safe_load(Path(config_path).read_text())
        ha_config = config["homeassistant"]
        self.base_url = ha_config["base_url"]
        self.access_token = ha_config["access_token"]
        self.trust_env = ha_config.get("trust_env", False)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def call_service(self, domain: str, service: str, data: dict):
        url = f"{self.base_url}/api/services/{domain}/{service}"
        async with httpx.AsyncClient(timeout=30, trust_env=self.trust_env) as client:
            response = await client.post(url, headers=self._headers(), json=data)
            response.raise_for_status()
            return response.json()

import httpx
import yaml
import os
from pathlib import Path
from typing import Optional

from src.services.message_parser import MessageParser, AcCommand


class AcController:
    def __init__(self, config_path: str = "config.yaml"):
        config = yaml.safe_load(Path(config_path).read_text())
        ha_config = config["homeassistant"]
        self.base_url = ha_config["base_url"]
        self.access_token = ha_config["access_token"]
        self.trust_env = ha_config.get("trust_env", False)
        self.default_entity = config.get("ac", {}).get("default_entity", "climate.lumi_mcn02_d56f_air_conditioner")
        self.parser = MessageParser()

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

    async def get_status(self, entity_id: str = None) -> dict:
        eid = entity_id or self.default_entity
        url = f"{self.base_url}/api/states/{eid}"
        async with httpx.AsyncClient(timeout=30, trust_env=self.trust_env) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def execute(self, text: str, entity_id: str = None) -> tuple[str, dict]:
        cmd = self.parser.parse(text)
        eid = entity_id or self.default_entity

        if cmd.query:
            status = await self.get_status(eid)
            attrs = status.get("attributes", {})
            state = status.get("state", "unknown")
            temp = attrs.get("temperature", "N/A")
            fan = attrs.get("fan_mode", "N/A")
            mode_map = {"cool": "制冷", "heat": "制热", "auto": "自动", "off": "关闭"}
            mode = mode_map.get(state, state)
            return f"空调状态：{mode}，温度{temp}°C，风速{fan}", {}

        if cmd.action == "off":
            result = await self.call_service("climate", "set_hvac_mode", {
                "entity_id": eid,
                "hvac_mode": "off"
            })
            return self.parser.to_response(cmd), result

        if cmd.action == "on" and not cmd.mode and not cmd.temperature and not cmd.fan:
            result = await self.call_service("climate", "set_hvac_mode", {
                "entity_id": eid,
                "hvac_mode": "cool"
            })
            return self.parser.to_response(cmd), result

        if cmd.mode or cmd.temperature:
            if cmd.mode:
                await self.call_service("climate", "set_hvac_mode", {
                    "entity_id": eid,
                    "hvac_mode": cmd.mode
                })

            if cmd.temperature:
                await self.call_service("climate", "set_temperature", {
                    "entity_id": eid,
                    "temperature": cmd.temperature
                })

        if cmd.fan:
            await self.call_service("climate", "set_fan_mode", {
                "entity_id": eid,
                "fan_mode": cmd.fan
            })

        result = await self.get_status(eid)
        return self.parser.to_response(cmd), result

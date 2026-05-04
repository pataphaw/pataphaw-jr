import httpx
import yaml
from pathlib import Path
from typing import Optional


MODE_MAP = {
    "cool": "cool",
    "heat": "heat",
    "auto": "auto",
    "dry": "dry",
    "fan_only": "fan_only",
    "off": "off",
}

FAN_MAP = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "auto": "auto",
}


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

    async def get_state(self, entity_id: str) -> dict:
        url = f"{self.base_url}/api/states/{entity_id}"
        async with httpx.AsyncClient(
            proxies={"http://": None, "https://": None},
            timeout=30
        ) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()


class HARouter:
    def __init__(self, ha_client: HomeAssistantClient = None):
        self.ha = ha_client or HomeAssistantClient()
        self._entity_cache = {}

    def _domain(self, entity_id: str) -> str:
        return entity_id.split(".")[0]

    async def route(self, intent: str, entity_id: str, params: dict) -> tuple[str, dict]:
        if not entity_id:
            return "未指定设备，请说明要控制哪个设备。", {}

        domain = self._domain(entity_id)

        try:
            if intent == "turn_on":
                return await self._turn_on(domain, entity_id, params)
            elif intent == "turn_off":
                return await self._turn_off(domain, entity_id, params)
            elif intent == "set_temperature":
                return await self._set_temperature(entity_id, params)
            elif intent == "set_mode":
                return await self._set_mode(entity_id, params)
            elif intent == "set_fan":
                return await self._set_fan(entity_id, params)
            elif intent == "query":
                return await self._query(entity_id)
            else:
                return f"未知操作：{intent}", {}
        except Exception as e:
            return f"执行失败：{str(e)}", {}

    async def _turn_on(self, domain: str, entity_id: str, params: dict) -> tuple[str, dict]:
        if domain == "climate":
            result = await self.ha.call_service("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": params.get("mode", "cool")})
            return f"已打开{self._friendly_name(entity_id)}", result
        elif domain in ("light", "switch", "fan"):
            result = await self.ha.call_service(domain, "turn_on", {"entity_id": entity_id})
            return f"已打开{self._friendly_name(entity_id)}", result
        return f"设备类型 {domain} 不支持 turn_on", {}

    async def _turn_off(self, domain: str, entity_id: str, params: dict) -> tuple[str, dict]:
        if domain == "climate":
            result = await self.ha.call_service("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "off"})
            return f"已关闭{self._friendly_name(entity_id)}", result
        elif domain in ("light", "switch", "fan"):
            result = await self.ha.call_service(domain, "turn_off", {"entity_id": entity_id})
            return f"已关闭{self._friendly_name(entity_id)}", result
        return f"设备类型 {domain} 不支持 turn_off", {}

    async def _set_temperature(self, entity_id: str, params: dict) -> tuple[str, dict]:
        temp = params.get("temperature")
        if not temp:
            return "未指定温度", {}
        result = await self.ha.call_service("climate", "set_temperature", {"entity_id": entity_id, "temperature": temp})
        return f"已将{self._friendly_name(entity_id)}温度设置为{temp}°C", result

    async def _set_mode(self, entity_id: str, params: dict) -> tuple[str, dict]:
        mode = params.get("mode")
        if not mode:
            return "未指定模式", {}
        mode = MODE_MAP.get(mode, mode)
        result = await self.ha.call_service("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": mode})
        return f"已将{self._friendly_name(entity_id)}设置为{mode}模式", result

    async def _set_fan(self, entity_id: str, params: dict) -> tuple[str, dict]:
        fan = params.get("fan")
        if not fan:
            return "未指定风速", {}
        fan = FAN_MAP.get(fan, fan)
        result = await self.ha.call_service("climate", "set_fan_mode", {"entity_id": entity_id, "fan_mode": fan})
        return f"已将{self._friendly_name(entity_id)}风速设置为{fan}", result

    async def _query(self, entity_id: str) -> tuple[str, dict]:
        state = await self.ha.get_state(entity_id)
        attrs = state.get("attributes", {})
        friendly = attrs.get("friendly_name", entity_id)
        st = state.get("state", "unknown")
        extra = []
        if "temperature" in attrs:
            extra.append(f"温度{attrs['temperature']}°C")
        if "fan_mode" in attrs:
            extra.append(f"风速{attrs['fan_mode']}")
        if "hvac_action" in attrs and attrs["hvac_action"]:
            extra.append(f"状态{attrs['hvac_action']}")
        info = "，".join(extra) if extra else st
        return f"{friendly}：{info}", state

    def _friendly_name(self, entity_id: str) -> str:
        mapping = {
            "climate.lumi_mcn02_d56f_air_conditioner": "主卧空调",
            "climate.lumi_mcn02_9b9e_air_conditioner": "次卧空调",
            "fan.zhimi_v6_ab09_air_purifier": "空气净化器",
            "switch.zhimi_v6_ab09_switch_status": "空气净化器",
            "switch.madv_mi3iot_8f90_switch_status": "watch dog",
            "light.madv_mi3iot_8f90_indicator_light": "watch dog 指示灯",
            "light.zhimi_v6_ab09_indicator_light": "空气净化器指示灯",
            "light.yeelink_mbulb3_0a5d_light": "Mi Smart LED Bulb",
            "light.yeelink_ceiling22_4117_light": "Mi Smart LED Ceiling Light",
        }
        return mapping.get(entity_id, entity_id)
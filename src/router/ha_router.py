import httpx
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from src.logging_config import get_logger

logger = get_logger("router")


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

THERMOHYGROMETER_ENTITIES = {
    "temperature": "sensor.miaomiaoce_t9_c4b7_temperature",
    "humidity": "sensor.miaomiaoce_t9_c4b7_relative_humidity",
    "battery": "sensor.miaomiaoce_t9_c4b7_battery_level",
}

STALE_SENSOR_AFTER = timedelta(minutes=10)
CHINA_TZ = timezone(timedelta(hours=8))


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
        logger.debug(f"HA API POST {url} data={data}")
        async with httpx.AsyncClient(timeout=30, trust_env=self.trust_env) as client:
            response = await client.post(url, headers=self._headers(), json=data)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"HA API response: {result}")
            return result

    async def get_state(self, entity_id: str) -> dict:
        url = f"{self.base_url}/api/states/{entity_id}"
        logger.debug(f"HA API GET {url}")
        async with httpx.AsyncClient(timeout=30, trust_env=self.trust_env) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            result = response.json()
            logger.debug(f"HA API response: {result}")
            return result


class HARouter:
    def __init__(self, ha_client: HomeAssistantClient = None):
        self.ha = ha_client or HomeAssistantClient()
        self._entity_cache = {}

    def _domain(self, entity_id: str) -> str:
        return entity_id.split(".")[0]

    async def route(self, intent: str, entity_id: str, params: dict) -> tuple[str, dict]:
        if not entity_id:
            logger.warning("Routing: no entity_id specified")
            return "未指定设备，请说明要控制哪个设备。", {}

        domain = self._domain(entity_id)
        logger.debug(f"Routing: intent={intent}, domain={domain}, entity_id={entity_id}, params={params}")

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
                logger.warning(f"Unknown intent: {intent}")
                return f"未知操作：{intent}", {}
        except Exception as e:
            logger.error(f"Route error for intent={intent}, entity_id={entity_id}: {e}", exc_info=True)
            return f"执行失败：{str(e)}", {}

    async def _turn_on(self, domain: str, entity_id: str, params: dict) -> tuple[str, dict]:
        if domain == "climate":
            mode = params.get("mode", "cool")
            logger.info(f"HA call: domain={domain}, service=set_hvac_mode, entity={entity_id}, hvac_mode={mode}")
            result = await self.ha.call_service("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": mode})
            return f"已打开{self._friendly_name(entity_id)}", result
        elif domain in ("light", "switch", "fan"):
            logger.info(f"HA call: domain={domain}, service=turn_on, entity={entity_id}")
            result = await self.ha.call_service(domain, "turn_on", {"entity_id": entity_id})
            return f"已打开{self._friendly_name(entity_id)}", result
        logger.warning(f"Unsupported domain for turn_on: {domain}")
        return f"设备类型 {domain} 不支持 turn_on", {}

    async def _turn_off(self, domain: str, entity_id: str, params: dict) -> tuple[str, dict]:
        if domain == "climate":
            logger.info(f"HA call: domain={domain}, service=set_hvac_mode, entity={entity_id}, hvac_mode=off")
            result = await self.ha.call_service("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "off"})
            return f"已关闭{self._friendly_name(entity_id)}", result
        elif domain in ("light", "switch", "fan"):
            logger.info(f"HA call: domain={domain}, service=turn_off, entity={entity_id}")
            result = await self.ha.call_service(domain, "turn_off", {"entity_id": entity_id})
            return f"已关闭{self._friendly_name(entity_id)}", result
        logger.warning(f"Unsupported domain for turn_off: {domain}")
        return f"设备类型 {domain} 不支持 turn_off", {}

    async def _set_temperature(self, entity_id: str, params: dict) -> tuple[str, dict]:
        temp = params.get("temperature")
        if not temp:
            logger.warning("set_temperature: no temperature specified")
            return "未指定温度", {}
        logger.info(f"HA call: domain=climate, service=set_temperature, entity={entity_id}, temperature={temp}")
        result = await self.ha.call_service("climate", "set_temperature", {"entity_id": entity_id, "temperature": temp})
        return f"已将{self._friendly_name(entity_id)}温度设置为{temp}°C", result

    async def _set_mode(self, entity_id: str, params: dict) -> tuple[str, dict]:
        mode = params.get("mode")
        if not mode:
            logger.warning("set_mode: no mode specified")
            return "未指定模式", {}
        mode = MODE_MAP.get(mode, mode)
        logger.info(f"HA call: domain=climate, service=set_hvac_mode, entity={entity_id}, hvac_mode={mode}")
        result = await self.ha.call_service("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": mode})
        return f"已将{self._friendly_name(entity_id)}设置为{mode}模式", result

    async def _set_fan(self, entity_id: str, params: dict) -> tuple[str, dict]:
        fan = params.get("fan")
        if not fan:
            logger.warning("set_fan: no fan specified")
            return "未指定风速", {}
        fan = FAN_MAP.get(fan, fan)
        logger.info(f"HA call: domain=climate, service=set_fan_mode, entity={entity_id}, fan_mode={fan}")
        result = await self.ha.call_service("climate", "set_fan_mode", {"entity_id": entity_id, "fan_mode": fan})
        return f"已将{self._friendly_name(entity_id)}风速设置为{fan}", result

    async def _query(self, entity_id: str) -> tuple[str, dict]:
        if entity_id in THERMOHYGROMETER_ENTITIES.values():
            return await self._query_thermohygrometer()

        logger.info(f"HA call: domain={self._domain(entity_id)}, service=get_state, entity={entity_id}")
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
        logger.debug(f"Query result for {entity_id}: state={st}, attrs={attrs}")
        return f"{friendly}：{info}", state

    async def _query_thermohygrometer(self) -> tuple[str, dict]:
        logger.info("HA call: aggregate query for thermohygrometer")
        states = {}
        for key, entity_id in THERMOHYGROMETER_ENTITIES.items():
            states[key] = await self.ha.get_state(entity_id)

        temperature = self._format_sensor_value(states["temperature"])
        humidity = self._format_sensor_value(states["humidity"])
        battery = self._format_sensor_value(states["battery"])

        latest_report = self._latest_timestamp(states.values())
        updated_text = self._format_timestamp(latest_report)
        stale_text = ""
        if latest_report and datetime.now(timezone.utc) - latest_report > STALE_SENSOR_AFTER:
            stale_text = "，数据可能不是实时值"

        return (
            f"温湿度计：温度{temperature}，湿度{humidity}，电量{battery}，"
            f"数据更新于{updated_text}{stale_text}",
            states,
        )

    def _format_sensor_value(self, state: dict) -> str:
        value = state.get("state")
        if value in (None, "unknown", "unavailable"):
            return "暂无数据"
        unit = state.get("attributes", {}).get("unit_of_measurement", "")
        return f"{value}{unit}"

    def _latest_timestamp(self, states) -> Optional[datetime]:
        timestamps = []
        for state in states:
            for key in ("last_updated", "last_reported", "last_changed"):
                parsed = self._parse_ha_timestamp(state.get(key))
                if parsed:
                    timestamps.append(parsed)
                    break
        return max(timestamps) if timestamps else None

    def _parse_ha_timestamp(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            logger.warning(f"Failed to parse HA timestamp: {value}")
            return None

    def _format_timestamp(self, value: Optional[datetime]) -> str:
        if not value:
            return "未知时间"
        return value.astimezone(CHINA_TZ).strftime("%Y-%m-%d %H:%M")

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
            "sensor.miaomiaoce_t9_c4b7_temperature": "温湿度计",
            "sensor.miaomiaoce_t9_c4b7_relative_humidity": "温湿度计湿度",
            "sensor.miaomiaoce_t9_c4b7_battery_level": "温湿度计电量",
        }
        return mapping.get(entity_id, entity_id)

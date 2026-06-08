import httpx
import json
import yaml
from pathlib import Path
from typing import Optional

from src.logging_config import get_logger

logger = get_logger("llm")


DEVICE_LIST = """
可用设备清单：

1. 主卧空调 (climate.lumi_mcn02_d56f_air_conditioner)
   - 支持操作：开/关、模式(cool/heat/auto/dry/fan_only)、温度(16-30°C)、风速(low/medium/high/auto)、摆风(on/off)

2. 次卧空调 (climate.lumi_mcn02_9b9e_air_conditioner)
   - 支持操作：开/关、模式(cool/heat/auto/dry/fan_only)、温度(16-30°C)、风速(low/medium/high/auto)、摆风(on/off)

3. 空气净化器 (fan.zhimi_v6_ab09_air_purifier)
   - 支持操作：开/关、ECO模式(switch.zhimi_v6_ab09_eco)

4. watch dog (switch.madv_mi3iot_8f90_switch_status)
   - 支持操作：开/关

5. watch dog 指示灯 (light.madv_mi3iot_8f90_indicator_light)
   - 支持操作：开/关

6. 空气净化器指示灯 (light.zhimi_v6_ab09_indicator_light)
   - 支持操作：开/关

7. Mi Smart LED Bulb (light.yeelink_mbulb3_0a5d_light)
   - 支持操作：开/关

8. Mi Smart LED Ceiling Light (light.yeelink_ceiling22_4117_light)
   - 支持操作：开/关

9. 温湿度计 (sensor.miaomiaoce_t9_c4b7_temperature)
   - 支持操作：查询温度、湿度、电量、状态
   - 相关实体：湿度(sensor.miaomiaoce_t9_c4b7_relative_humidity)、电量(sensor.miaomiaoce_t9_c4b7_battery_level)
"""


SYSTEM_PROMPT_TEMPLATE = """你是智能家居助手，通过 Telegram 控制 HomeAssistant 中的设备。

{device_list}

对话历史：
{history}

请理解用户指令，调用相应设备操作，并回复简洁的中文确认消息。

返回格式（只返回 JSON，不要其他内容）：
{{"intent": "操作意图", "entity_id": "设备ID", "params": {{"参数"}}, "reply": "回复用户的消息"}}

intent 可选值：turn_on, turn_off, set_temperature, set_mode, set_fan, query, unknown
"""


class OllamaLLMParser:
    def __init__(self, model: str = "qwen2.5vl:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    async def parse(self, user_message: str, history_text: str, chat_id: str = None) -> dict:
        prompt = SYSTEM_PROMPT_TEMPLATE.replace("{device_list}", DEVICE_LIST).replace("{history}", history_text)
        logger.debug(f"Prompt built, history_len={len(history_text)}")

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message}
        ]

        logger.info(f"Calling Ollama: {self.base_url}/api/chat model={self.model}")
        try:
            async with httpx.AsyncClient(timeout=120, proxies={"http://": None, "https://": None}) as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": messages, "stream": False}
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"].strip()

            logger.debug(f"Ollama response content: {content[:200]}...")

            try:
                result = json.loads(content)
                logger.debug(f"JSON parsed successfully: {result}")
                return result
            except json.JSONDecodeError:
                logger.warning(f"JSON parse failed, falling back to unknown intent. Raw content: {content[:100]}...")
                return {"intent": "unknown", "entity_id": None, "params": {}, "reply": content if content else "抱歉，我没有理解你的意思。"}
        except httpx.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}", exc_info=True)
            return {"intent": "unknown", "entity_id": None, "params": {}, "reply": "抱歉，LLM 服务暂时不可用。"}
        except Exception as e:
            logger.error(f"LLM parse error: {e}", exc_info=True)
            return {"intent": "unknown", "entity_id": None, "params": {}, "reply": "抱歉，发生了一些错误。"}


async def get_llm_parser() -> OllamaLLMParser:
    config_path = Path("config.yaml")
    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    llm_config = config.get("llm", {})
    model = llm_config.get("model", "qwen2.5vl:7b")
    base_url = llm_config.get("base_url", "http://localhost:11434")
    logger.info(f"LLM parser initialized: model={model}, base_url={base_url}")
    return OllamaLLMParser(model=model, base_url=base_url)

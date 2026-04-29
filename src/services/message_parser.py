import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class AcCommand:
    action: Optional[str] = None
    mode: Optional[str] = None
    temperature: Optional[int] = None
    fan: Optional[str] = None
    query: bool = False


class MessageParser:
    PATTERNS = {
        "turn_on": [r"开", r"启动", r"打开", r"开启"],
        "turn_off": [r"关", r"关闭", r"关掉", r"关机"],
        "mode_cool": [r"制冷", r"冷"],
        "mode_heat": [r"制热", r"热"],
        "mode_auto": [r"自动"],
        "fan_low": [r"低速", r"低风", r"小风"],
        "fan_medium": [r"中速", r"中风"],
        "fan_high": [r"高速", r"大风"],
        "query": [r"查询", r"状态", r"怎么样", r"多少度"],
    }

    MODE_MAP = {
        "cool": "cool",
        "heat": "heat",
        "auto": "auto",
    }

    FAN_MAP = {
        "low": "low",
        "medium": "medium",
        "high": "high",
    }

    def parse(self, text: str) -> AcCommand:
        text = text.strip().lower()
        cmd = AcCommand()

        if any(re.search(p, text) for p in self.PATTERNS["turn_off"]):
            cmd.action = "off"
            return cmd

        if any(re.search(p, text) for p in self.PATTERNS["turn_on"]):
            cmd.action = "on"

        if any(re.search(p, text) for p in self.PATTERNS["mode_cool"]):
            cmd.mode = "cool"
        elif any(re.search(p, text) for p in self.PATTERNS["mode_heat"]):
            cmd.mode = "heat"
        elif any(re.search(p, text) for p in self.PATTERNS["mode_auto"]):
            cmd.mode = "auto"

        temp_match = re.search(r"(\d+)\s*[度℃]?", text)
        if temp_match:
            temp = int(temp_match.group(1))
            if 16 <= temp <= 30:
                cmd.temperature = temp

        if any(re.search(p, text) for p in self.PATTERNS["fan_low"]):
            cmd.fan = "low"
        elif any(re.search(p, text) for p in self.PATTERNS["fan_medium"]):
            cmd.fan = "medium"
        elif any(re.search(p, text) for p in self.PATTERNS["fan_high"]):
            cmd.fan = "high"

        if any(re.search(p, text) for p in self.PATTERNS["query"]):
            cmd.query = True

        if not cmd.action and not cmd.mode and not cmd.temperature and not cmd.fan and not cmd.query:
            if "空调" in text:
                cmd.action = "on"

        return cmd

    def to_response(self, cmd: AcCommand) -> str:
        if cmd.query:
            return "请使用状态查询功能"

        parts = []
        if cmd.action == "off":
            return "已关闭空调"
        elif cmd.action == "on":
            parts.append("已开空调")

        if cmd.mode:
            mode_names = {"cool": "制冷", "heat": "制热", "auto": "自动"}
            parts.append(mode_names.get(cmd.mode, cmd.mode))

        if cmd.temperature:
            parts.append(f"{cmd.temperature}°C")

        if cmd.fan:
            fan_names = {"low": "低速", "medium": "中速", "high": "高速"}
            parts.append(fan_names.get(cmd.fan, cmd.fan))

        return "，".join(parts) if parts else "收到指令"

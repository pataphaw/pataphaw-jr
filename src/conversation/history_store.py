from pathlib import Path
from datetime import datetime, timedelta
import json
import os


class HistoryStore:
    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            base_dir = Path.home() / ".config" / "pataphaw-jr" / "memories"
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _today_dir(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        d = self.base_dir / today
        d.mkdir(exist_ok=True)
        return d

    def _seq_file(self, d: Path) -> Path:
        existing = list(d.glob("*.json"))
        seq = len(existing) + 1
        return d / f"{seq:03d}.json"

    def add(self, role: str, content: str):
        d = self._today_dir()
        entry = {"role": role, "content": content, "ts": datetime.now().isoformat()}
        path = self._seq_file(d)
        path.write_text(json.dumps(entry, ensure_ascii=False))

    def load_today(self) -> list[dict]:
        d = self._today_dir()
        entries = []
        for f in sorted(d.glob("*.json")):
            try:
                entries.append(json.loads(f.read_text()))
            except Exception:
                pass
        return entries

    def load_recent(self, days: int = 7) -> list[dict]:
        entries = []
        for i in range(days):
            d = self.base_dir / (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)).strftime("%Y-%m-%d")
            if d.exists():
                for f in sorted(d.glob("*.json")):
                    try:
                        entries.append(json.loads(f.read_text()))
                    except Exception:
                        pass
        return entries
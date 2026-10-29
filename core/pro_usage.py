"""
Daily counts of Pro use, sent with the license check (numbers only: no photos, file names or
metadata). DotSuite uses them to judge refund requests. Nothing is counted on the Free plan.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

KINDS = ("pro_saves", "batch_images", "metadata_cleaned", "ai_runs")
_KEEP_DAYS = 60          # the server accepts at most this many days in one report


class ProUsage:
    def __init__(self, db_manager, key: str = "pro_usage_pending", today=date.today):
        self.db, self.key, self.today = db_manager, key, today
        self._lock = threading.Lock()   # Batch counts from its worker thread

    def _load(self) -> dict:
        data = self.db.get_setting(self.key, {})
        return data if isinstance(data, dict) else {}

    def add(self, kind: str, count: int = 1) -> None:
        if kind not in KINDS or count <= 0:
            return
        with self._lock:
            data = self._load()
            day = data.setdefault(self.today().isoformat(), {})
            day[kind] = int(day.get(kind, 0)) + count
            oldest = (self.today() - timedelta(days=_KEEP_DAYS - 1)).isoformat()
            data = {d: v for d, v in data.items() if d >= oldest}
            self.db.save_setting(self.key, data, "license")

    def pending(self) -> list[dict]:
        """Unsent counts, one entry per day, oldest first."""
        with self._lock:
            data = self._load()
        return [{"day": d, **{k: int(v.get(k, 0)) for k in KINDS}} for d, v in sorted(data.items())]

    def sent(self, report: list[dict]) -> None:
        """Forget what the server accepted; counts added meanwhile stay pending."""
        with self._lock:
            data = self._load()
            for entry in report:
                day = data.get(entry["day"])
                if not day:
                    continue
                for k in KINDS:
                    left = int(day.get(k, 0)) - int(entry.get(k, 0))
                    if left > 0:
                        day[k] = left
                    else:
                        day.pop(k, None)
                if not day:
                    data.pop(entry["day"], None)
            self.db.save_setting(self.key, data, "license")

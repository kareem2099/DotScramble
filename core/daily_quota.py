"""
A small per-day allowance for a Free-tier feature (removing the GPS location from saved
photos). Stored in the settings database as {"date": "YYYY-MM-DD", "used": n}; a new
local day starts from zero.
"""
from __future__ import annotations

import json
from datetime import date

FREE_LOCATION_REMOVALS_PER_DAY = 4


class DailyQuota:
    def __init__(self, db_manager, key: str = "free_location_removals",
                 limit: int = FREE_LOCATION_REMOVALS_PER_DAY, today=date.today):
        self._db = db_manager
        self._key = key
        self.limit = limit
        self._today = today

    def _used_today(self) -> int:
        try:
            raw = self._db.get_setting(self._key)
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            if data.get("date") == self._today().isoformat():
                return max(0, int(data.get("used", 0)))
        except Exception:
            pass
        return 0

    def remaining(self) -> int:
        return max(0, self.limit - self._used_today())

    def consume(self) -> int:
        """Use one for today; returns how many are left."""
        used = min(self.limit, self._used_today() + 1)
        try:
            self._db.save_setting(self._key, {"date": self._today().isoformat(), "used": used}, "usage")
        except Exception:
            pass
        return max(0, self.limit - used)

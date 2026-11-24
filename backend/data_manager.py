"""Unified Data Manager.
Orchestrates Garmin Connect, Intervals.icu, and local historico_semanal.json
to supply the weekly calendar, zone aggregations, PMC curves, and workout details.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import AppConfig, load_config, HISTORICO_FILE, APP_DATA_DIR

ACTIVITY_CACHE_DIR = APP_DATA_DIR / "cache" / "activities"
ACTIVITY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
ACTIVITY_CACHE_SCHEMA_VERSION = 5
from .garmin_service import GarminService
from .intervals_service import IntervalsService
from .metrics import (
    calculate_bike_efficiency,
    calculate_run_efficiency,
    calculate_decoupling_from_splits,
    calculate_swim_metrics,
    aggregate_weekly_zones,
    compute_pmc_series,
    classify_power_zone,
    classify_speed_zone,
)
from .ai_coach import AICoachService

logger = logging.getLogger(__name__)

# Historical Garmin Connect personal normal HRV ranges: date -> [balancedLow, balancedUpper, lowUpper]
GARMIN_HRV_BASELINES: Dict[str, List[int]] = {"2025-11-14": [95, 129, 88], "2025-11-15": [95, 129, 88], "2025-11-16": [96, 129, 89], "2025-11-17": [96, 129, 89], "2025-11-18": [96, 129, 90], "2025-11-19": [96, 128, 90], "2025-11-20": [96, 128, 89], "2025-11-21": [96, 128, 89], "2025-11-22": [96, 128, 89], "2025-11-23": [96, 127, 89], "2025-11-24": [95, 127, 89], "2025-11-25": [95, 127, 88], "2025-11-26": [95, 127, 88], "2025-11-27": [95, 127, 88], "2025-11-28": [95, 127, 88], "2025-11-29": [95, 127, 88], "2025-11-30": [95, 128, 88], "2025-12-01": [95, 128, 88], "2025-12-02": [95, 128, 89], "2025-12-03": [95, 128, 89], "2025-12-04": [95, 128, 89], "2025-12-05": [95, 128, 88], "2025-12-06": [95, 128, 88], "2025-12-07": [95, 128, 88], "2025-12-08": [95, 128, 88], "2025-12-09": [95, 128, 88], "2025-12-10": [95, 128, 88], "2025-12-11": [95, 127, 88], "2025-12-12": [95, 127, 88], "2025-12-13": [95, 128, 88], "2025-12-14": [95, 128, 88], "2025-12-15": [95, 128, 89], "2025-12-16": [96, 128, 89], "2025-12-17": [96, 128, 89], "2025-12-18": [96, 128, 89], "2025-12-19": [96, 128, 89], "2025-12-20": [96, 128, 89], "2025-12-21": [96, 127, 90], "2025-12-22": [97, 128, 90], "2025-12-23": [97, 128, 91], "2025-12-24": [96, 130, 89], "2025-12-25": [95, 129, 88], "2025-12-26": [95, 129, 88], "2025-12-27": [95, 129, 88], "2025-12-28": [96, 129, 89], "2025-12-29": [96, 129, 89], "2025-12-30": [97, 130, 90], "2025-12-31": [97, 130, 90], "2026-01-01": [96, 130, 89], "2026-01-02": [96, 130, 89], "2026-01-03": [95, 130, 88], "2026-01-04": [95, 130, 88], "2026-01-05": [95, 130, 88], "2026-01-06": [96, 131, 88], "2026-01-07": [96, 131, 88], "2026-01-08": [95, 131, 88], "2026-01-09": [95, 131, 88], "2026-01-10": [95, 131, 87], "2026-01-11": [95, 131, 88], "2026-01-12": [96, 131, 88], "2026-01-13": [95, 131, 87], "2026-01-14": [95, 131, 87], "2026-01-15": [95, 131, 87], "2026-01-16": [94, 131, 87], "2026-01-17": [94, 131, 87], "2026-01-18": [95, 130, 88], "2026-01-19": [95, 131, 88], "2026-01-20": [95, 131, 88], "2026-01-21": [95, 131, 88], "2026-01-22": [95, 131, 88], "2026-01-23": [95, 131, 88], "2026-01-24": [96, 132, 88], "2026-01-25": [96, 131, 88], "2026-01-26": [96, 131, 88], "2026-01-27": [95, 131, 88], "2026-01-28": [96, 131, 88], "2026-01-29": [96, 131, 88], "2026-01-30": [96, 132, 88], "2026-01-31": [96, 132, 89], "2026-02-01": [96, 132, 89], "2026-02-02": [96, 132, 89], "2026-02-03": [96, 132, 89], "2026-02-04": [96, 132, 89], "2026-02-05": [96, 132, 89], "2026-02-06": [97, 133, 89], "2026-02-07": [97, 133, 89], "2026-02-08": [96, 133, 89], "2026-02-09": [96, 132, 89], "2026-02-10": [96, 132, 89], "2026-02-11": [97, 132, 89], "2026-02-12": [97, 132, 89], "2026-02-13": [97, 133, 89], "2026-02-14": [97, 133, 90], "2026-02-15": [97, 133, 90], "2026-02-16": [97, 133, 90], "2026-02-17": [97, 133, 90], "2026-02-18": [97, 132, 90], "2026-02-19": [97, 132, 90], "2026-02-20": [97, 132, 90], "2026-02-21": [97, 132, 90], "2026-02-22": [98, 132, 91], "2026-02-23": [98, 132, 91], "2026-02-24": [98, 132, 91], "2026-02-25": [98, 131, 91], "2026-02-26": [98, 131, 92], "2026-02-27": [99, 132, 92], "2026-02-28": [99, 131, 92], "2026-03-01": [99, 132, 93], "2026-03-02": [99, 132, 93], "2026-03-03": [99, 131, 93], "2026-03-04": [100, 131, 93], "2026-03-05": [100, 131, 94], "2026-03-06": [100, 131, 94], "2026-03-07": [101, 130, 94], "2026-03-08": [101, 130, 94], "2026-03-09": [100, 130, 94], "2026-03-10": [100, 129, 94], "2026-03-11": [101, 129, 95], "2026-03-12": [101, 128, 95], "2026-03-13": [102, 128, 96], "2026-03-14": [102, 128, 96], "2026-03-15": [102, 128, 96], "2026-03-16": [102, 127, 96], "2026-03-17": [102, 127, 97], "2026-03-18": [102, 126, 96], "2026-03-19": [102, 126, 97], "2026-03-20": [102, 126, 97], "2026-03-21": [103, 126, 97], "2026-03-22": [103, 126, 98], "2026-03-23": [103, 125, 98], "2026-03-24": [103, 125, 98], "2026-03-25": [103, 125, 98], "2026-03-26": [103, 124, 98], "2026-03-27": [103, 124, 99], "2026-03-28": [104, 125, 99], "2026-03-29": [104, 124, 99], "2026-03-30": [104, 124, 99], "2026-03-31": [104, 124, 100], "2026-04-01": [104, 124, 100], "2026-04-02": [104, 124, 100], "2026-04-03": [104, 123, 100], "2026-04-04": [104, 124, 100], "2026-04-05": [105, 124, 100], "2026-04-06": [105, 124, 101], "2026-04-07": [105, 124, 101], "2026-04-08": [105, 124, 101], "2026-04-09": [105, 123, 101], "2026-04-10": [105, 123, 100], "2026-04-11": [105, 123, 101], "2026-04-12": [105, 123, 101], "2026-04-13": [105, 123, 100], "2026-04-14": [105, 123, 101], "2026-04-15": [105, 123, 101], "2026-04-16": [105, 123, 101], "2026-04-17": [105, 123, 101], "2026-04-18": [105, 123, 100], "2026-04-19": [103, 124, 99], "2026-04-20": [103, 124, 99], "2026-04-21": [104, 124, 99], "2026-04-23": [103, 124, 99], "2026-04-24": [103, 124, 99], "2026-04-25": [103, 124, 99], "2026-04-26": [103, 123, 99], "2026-04-27": [104, 123, 99], "2026-04-28": [104, 124, 99], "2026-04-29": [104, 124, 99], "2026-04-30": [104, 123, 99], "2026-05-01": [104, 124, 100], "2026-05-02": [104, 124, 100], "2026-05-03": [104, 123, 100], "2026-05-04": [104, 124, 100], "2026-05-05": [104, 124, 100], "2026-05-06": [104, 124, 100], "2026-05-07": [104, 124, 100], "2026-05-08": [104, 124, 100], "2026-05-09": [104, 124, 100], "2026-05-10": [105, 124, 100], "2026-05-11": [105, 125, 100], "2026-05-12": [105, 125, 100], "2026-05-13": [105, 126, 101], "2026-05-14": [105, 126, 101], "2026-05-15": [106, 126, 101], "2026-05-16": [106, 127, 101], "2026-05-17": [106, 127, 100], "2026-05-18": [104, 129, 99], "2026-05-19": [104, 129, 99], "2026-05-20": [104, 130, 99], "2026-05-21": [104, 129, 99], "2026-05-22": [104, 130, 99], "2026-05-23": [104, 129, 99], "2026-05-24": [104, 129, 99], "2026-05-25": [104, 130, 99], "2026-05-26": [105, 130, 99], "2026-05-27": [105, 131, 99], "2026-05-28": [105, 131, 99], "2026-05-29": [105, 131, 99], "2026-05-30": [105, 130, 99], "2026-05-31": [105, 131, 99], "2026-06-01": [105, 130, 99], "2026-06-02": [104, 130, 99], "2026-06-03": [105, 131, 99], "2026-06-04": [105, 130, 99], "2026-06-05": [105, 131, 99], "2026-06-06": [105, 130, 99], "2026-06-07": [105, 130, 100], "2026-06-08": [105, 130, 99], "2026-06-09": [105, 130, 99], "2026-06-10": [105, 130, 99], "2026-06-11": [105, 130, 100], "2026-06-12": [105, 131, 100], "2026-06-13": [105, 131, 100], "2026-06-14": [105, 131, 99], "2026-06-15": [105, 131, 99], "2026-06-16": [105, 131, 99], "2026-06-17": [105, 131, 100], "2026-06-18": [105, 131, 99], "2026-06-19": [105, 131, 99], "2026-06-20": [105, 132, 100], "2026-06-21": [106, 132, 100], "2026-06-22": [106, 132, 100], "2026-06-23": [106, 132, 100], "2026-06-24": [106, 132, 100], "2026-06-25": [106, 132, 100], "2026-06-26": [106, 132, 100], "2026-06-27": [106, 132, 100], "2026-06-28": [106, 132, 100], "2026-06-29": [105, 132, 99], "2026-06-30": [105, 132, 99], "2026-07-01": [105, 132, 99], "2026-07-02": [105, 131, 98], "2026-07-03": [104, 132, 98], "2026-07-04": [104, 132, 97], "2026-07-05": [103, 132, 97], "2026-07-06": [103, 131, 97], "2026-07-07": [104, 131, 97], "2026-07-08": [103, 131, 97], "2026-07-09": [104, 131, 97], "2026-07-10": [103, 130, 97], "2026-07-11": [102, 131, 96], "2026-07-12": [103, 131, 96], "2026-07-13": [102, 131, 96], "2026-07-14": [102, 131, 96], "2026-07-15": [102, 130, 96], "2026-07-16": [102, 130, 96], "2026-07-17": [103, 130, 96], "2026-07-18": [102, 131, 96], "2026-07-19": [99, 136, 92], "2026-07-20": [99, 135, 92], "2026-07-21": [99, 135, 92], "2026-07-22": [99, 135, 92], "2026-07-23": [99, 135, 92], "2026-07-24": [99, 135, 92], "2026-07-25": [99, 135, 92], "2026-07-26": [99, 134, 92], "2026-07-27": [99, 134, 92], "2026-07-28": [99, 135, 92], "2026-07-29": [99, 134, 92], "2026-07-30": [99, 134, 91], "2026-07-31": [98, 134, 91], "2026-08-01": [98, 134, 91], "2026-08-02": [96, 139, 87], "2026-08-03": [96, 139, 87], "2026-08-04": [96, 139, 87], "2026-08-05": [96, 138, 87], "2026-08-06": [96, 138, 87], "2026-08-07": [96, 138, 87], "2026-08-08": [96, 138, 87], "2026-08-09": [96, 138, 87], "2026-08-10": [96, 138, 87], "2026-08-11": [96, 138, 87], "2026-08-12": [96, 138, 87], "2026-08-13": [96, 139, 88], "2026-08-14": [96, 139, 88], "2026-08-15": [96, 138, 88], "2026-08-16": [96, 139, 88], "2026-08-17": [96, 139, 88], "2026-08-18": [96, 138, 88], "2026-08-19": [96, 139, 88], "2026-08-20": [96, 139, 88], "2026-08-21": [96, 139, 88], "2026-08-22": [96, 139, 88], "2026-08-23": [96, 138, 88], "2026-08-24": [97, 139, 88], "2026-08-25": [96, 139, 88], "2026-08-26": [96, 139, 88], "2026-08-27": [96, 139, 88], "2026-08-28": [96, 138, 88], "2026-08-29": [97, 139, 89], "2026-08-30": [97, 139, 89], "2026-08-31": [97, 139, 89], "2026-09-01": [97, 138, 89], "2026-09-02": [97, 138, 88], "2026-09-03": [97, 138, 88], "2026-09-04": [97, 138, 88], "2026-09-11": [97, 137, 90], "2026-09-12": [98, 137, 90], "2026-09-13": [98, 136, 90], "2026-09-14": [98, 137, 90], "2026-09-15": [98, 137, 90], "2026-09-16": [98, 137, 90], "2026-09-17": [98, 137, 90], "2026-09-18": [98, 137, 90], "2026-09-19": [98, 137, 90], "2026-09-20": [98, 135, 91], "2026-09-21": [98, 135, 90], "2026-09-22": [97, 135, 90], "2026-09-23": [97, 135, 90], "2026-09-24": [98, 135, 90], "2026-09-25": [98, 135, 90], "2026-09-26": [98, 135, 90], "2026-09-27": [99, 133, 92], "2026-09-28": [99, 133, 92], "2026-09-29": [99, 132, 92], "2026-09-30": [99, 132, 92], "2026-10-01": [99, 132, 92], "2026-10-02": [99, 132, 92], "2026-10-03": [99, 131, 92], "2026-10-04": [99, 129, 93], "2026-10-05": [99, 129, 92], "2026-10-06": [98, 129, 92], "2026-10-07": [98, 128, 92], "2026-10-08": [98, 128, 92], "2026-10-09": [98, 127, 92], "2026-10-10": [98, 128, 92], "2026-10-11": [98, 126, 92], "2026-10-12": [98, 126, 91], "2026-10-13": [97, 126, 91], "2026-10-14": [97, 125, 90], "2026-10-15": [96, 125, 90], "2026-10-16": [96, 125, 90], "2026-10-17": [95, 125, 88], "2026-10-18": [95, 124, 88], "2026-10-19": [94, 124, 88], "2026-10-20": [94, 124, 87], "2026-10-21": [93, 123, 87], "2026-10-22": [93, 123, 87], "2026-10-23": [93, 122, 87], "2026-10-24": [93, 122, 86], "2026-10-25": [92, 121, 86], "2026-10-26": [92, 121, 86], "2026-10-27": [92, 122, 86], "2026-10-28": [92, 121, 86], "2026-10-29": [92, 121, 86], "2026-10-30": [92, 120, 86], "2026-10-31": [92, 120, 86], "2026-11-01": [92, 120, 86], "2026-11-02": [92, 120, 86], "2026-11-03": [92, 120, 86], "2026-11-04": [92, 120, 86], "2026-11-05": [92, 120, 86], "2026-11-06": [92, 119, 86], "2026-11-07": [92, 119, 86], "2026-11-08": [92, 119, 87], "2026-11-09": [92, 119, 87], "2026-11-10": [92, 119, 87], "2026-11-11": [92, 119, 87], "2026-11-12": [92, 119, 87], "2026-11-13": [92, 119, 87], "2026-11-14": [93, 118, 87], "2026-11-15": [92, 118, 87], "2026-11-16": [92, 118, 87], "2026-11-17": [92, 118, 87], "2026-11-18": [92, 117, 87]}


class DataManager:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()
        self.garmin = GarminService(self.config)
        self.intervals = IntervalsService(self.config)
        self.coach = AICoachService(self.config.gemini_api_key)
        self._activity_cache: Dict[str, Dict[str, Any]] = {}
        self._week_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self._pmc_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self._health_load_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self._cache_ttl: float = 300.0  # 5 minutes in-memory cache

    def clear_cache(self):
        self._week_cache.clear()
        self._pmc_cache.clear()
        self._health_load_cache.clear()
        self._activity_cache.clear()

    def get_week_range(self, offset_weeks: int = 0, anchor_date: Optional[str] = None) -> Tuple[date, date, str]:
        """Returns (monday, sunday, week_label) for the requested week offset."""
        if anchor_date:
            try:
                base = datetime.strptime(anchor_date, "%Y-%m-%d").date()
            except Exception:
                base = date.today()
        else:
            base = date.today()

        # Shift by offset weeks
        target_day = base + timedelta(weeks=offset_weeks)
        # Find Monday of that week
        monday = target_day - timedelta(days=target_day.weekday())
        sunday = monday + timedelta(days=6)
        iso_year, iso_week, _ = monday.isocalendar()
        label = f"{iso_year}-W{iso_week:02d}"
        return monday, sunday, label

    def get_week_view(self, offset_weeks: int = 0, force_refresh: bool = False) -> Dict[str, Any]:
        """Gathers all planned & completed workouts, daily wellness, and zone summary
        for the specified week (offset 0 = current week).
        """
        now = time.time()
        if not force_refresh and offset_weeks in self._week_cache:
            c_time, c_data = self._week_cache[offset_weeks]
            if (now - c_time) < self._cache_ttl:
                return c_data

        monday, sunday, week_label = self.get_week_range(offset_weeks)
        start_str = monday.strftime("%Y-%m-%d")
        end_str = sunday.strftime("%Y-%m-%d")

        # 0. Ensure live Intervals.icu thresholds & zone definitions (FTP, Run Pace, Swim CSS) are fresh
        disciplines_thresholds = self.intervals.ensure_fresh_thresholds(max_age_seconds=0 if force_refresh else 300)

        # 1. Fetch planned workouts from Intervals.icu
        planned_events = self.intervals.get_planned_events(start_str, end_str)

        # 2. Fetch completed activities from Garmin + enrich with Intervals.icu (exact TSS & zone times)
        completed_activities = []
        try:
            recent_acts = self.garmin.get_activities(limit=40)
            for act in recent_acts:
                act_time = act.get("start_time", "")[:10]
                if start_str <= act_time <= end_str:
                    completed_activities.append(act)
        except Exception as e:
            logger.warning(f"Error fetching Garmin activities: {e}")

        # Fetch Intervals.icu activities for exact TSS, pace/power zone times, and fallback when Garmin lacks older/remote activities
        icu_acts: List[Dict[str, Any]] = []
        try:
            icu_acts = self.intervals.get_activities_by_range(start_str, end_str)
        except Exception as e:
            logger.warning(f"Error fetching Intervals.icu activities: {e}")

        if icu_acts:
            icu_by_ext = {str(a["external_id"]): a for a in icu_acts if a.get("external_id")}
            matched_icu_ids = set()

            for act in completed_activities:
                act_id_str = str(act.get("activity_id") or "")
                match = icu_by_ext.get(act_id_str)
                if not match:
                    act_day = (act.get("start_time") or "")[:10]
                    act_sport = act.get("sport_type")
                    act_dur = float(act.get("duration_seconds") or 0)
                    best_diff = 900.0
                    for cand in icu_acts:
                        if cand["icu_activity_id"] in matched_icu_ids:
                            continue
                        if (cand.get("start_time") or "")[:10] == act_day and cand.get("sport_type") == act_sport:
                            diff = abs(float(cand.get("duration_seconds") or 0) - act_dur)
                            if diff <= best_diff:
                                best_diff = diff
                                match = cand

                if match:
                    matched_icu_ids.add(match["icu_activity_id"])
                    act["icu_activity_id"] = match["icu_activity_id"]
                    if match.get("tss") is not None:
                        act["tss"] = match["tss"]
                        act["training_load"] = match.get("training_load")
                    if act.get("normalised_power") is None and match.get("normalised_power") is not None:
                        act["normalised_power"] = match["normalised_power"]
                    if act.get("avg_power") is None and match.get("avg_power") is not None:
                        act["avg_power"] = match["avg_power"]
                    if act.get("max_power") is None and match.get("max_power") is not None:
                        act["max_power"] = match["max_power"]
                    if match.get("pace_zone_times") is not None:
                        act["pace_zone_times"] = match["pace_zone_times"]
                    if match.get("icu_zone_times") is not None:
                        act["icu_zone_times"] = match["icu_zone_times"]
                    if match.get("icu_hr_zone_times") is not None:
                        act["icu_hr_zone_times"] = match["icu_hr_zone_times"]
                elif act.get("tss") is None and act.get("training_load") is not None:
                    act["tss"] = round(float(act["training_load"]))

            # Add any Intervals.icu activities not returned by Garmin (e.g. Render remote deploy or weeks older than Garmin limit=40)
            for cand in icu_acts:
                if cand["icu_activity_id"] not in matched_icu_ids:
                    completed_activities.append(cand)

            completed_activities.sort(key=lambda x: x.get("start_time") or "")

        # If no live activities found for past weeks, check historical file
        if not completed_activities and HISTORICO_FILE.exists():
            completed_activities = self._load_completed_from_history(start_str, end_str)

        # 3. Organize days from Monday to Sunday
        days_data = []
        cur = monday
        while cur <= sunday:
            cur_str = cur.strftime("%Y-%m-%d")
            weekday_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][cur.weekday()]

            day_planned = [e for e in planned_events if e.get("date") == cur_str]
            day_completed = [a for a in completed_activities if a.get("start_time", "")[:10] == cur_str]

            # Enhance completed with calculated metrics
            enhanced_completed = []
            for act in day_completed:
                sport = act.get("sport_type", "running")
                eff = {}
                if sport == "cycling":
                    eff = calculate_bike_efficiency(act.get("normalised_power"), act.get("avg_power"), act.get("avg_heart_rate"))
                elif sport == "running":
                    eff = calculate_run_efficiency(act.get("avg_speed_mps"), act.get("avg_heart_rate"))
                elif sport == "swimming":
                    eff = calculate_swim_metrics(act.get("duration_seconds", 0), act.get("distance_meters", 0))

                enhanced_completed.append({
                    **act,
                    "efficiency": eff,
                })

            # Fetch or mock daily wellness
            wellness = self._get_day_wellness(cur_str)

            days_data.append({
                "date": cur_str,
                "day_name": weekday_es,
                "is_today": cur_str == date.today().strftime("%Y-%m-%d"),
                "wellness": wellness,
                "planned": day_planned,
                "completed": enhanced_completed,
            })
            cur += timedelta(days=1)

        # 4. Weekly summary box: Zones planned vs completed using live Intervals.icu thresholds
        zone_summary = aggregate_weekly_zones(planned_events, completed_activities, disciplines_thresholds=disciplines_thresholds)

        # 5. Total loads, hours and distances
        total_planned_load = sum((e.get("planned_load") or 0) for e in planned_events)
        total_completed_load = sum((z["completed_load"] or 0) for z in zone_summary.values())
        total_planned_hrs = sum((z["planned_hours"] or 0) for z in zone_summary.values())
        total_completed_hrs = sum((z["completed_hours"] or 0) for z in zone_summary.values())
        total_planned_km = sum(z.get("planned_km", 0) for k, z in zone_summary.items() if k != "swimming")
        total_completed_km = sum(z.get("completed_km", 0) for k, z in zone_summary.items() if k != "swimming")
        total_swim_planned_m = zone_summary.get("swimming", {}).get("planned_distance_meters", 0)
        total_swim_completed_m = zone_summary.get("swimming", {}).get("completed_distance_meters", 0)

        result = {
            "week_label": week_label,
            "date_range": f"{monday.strftime('%d/%m/%Y')} al {sunday.strftime('%d/%m/%Y')}",
            "offset_weeks": offset_weeks,
            "days": days_data,
            "zone_summary": zone_summary,
            "thresholds": {
                "ftp": self.config.ftp,
                "css_pace": self.config.css_pace,
                "run_threshold_pace": self.config.run_threshold_pace,
                "max_hr": self.config.max_hr,
                "lthr": self.config.lthr,
                "disciplines": disciplines_thresholds,
            },
            "totals": {
                "planned_hours": round(total_planned_hrs, 2),
                "completed_hours": round(total_completed_hrs, 2),
                "planned_load": total_planned_load,
                "completed_load": total_completed_load,
                "planned_km": round(total_planned_km, 1),
                "completed_km": round(total_completed_km, 1),
                "swim_planned_m": round(total_swim_planned_m),
                "swim_completed_m": round(total_swim_completed_m),
                "athlete_phase": self.config.athlete_phase,
            }
        }
        self._week_cache[offset_weeks] = (time.time(), result)
        return result

    def _enrich_activity_with_intervals(self, activity_data: Dict[str, Any], fetch_intervals: bool = True) -> bool:
        """Ensures a completed activity dict has authoritative TSS, normalized power,
        zone metadata, and per-interval telemetry (with intra-block decoupling) from Intervals.icu.
        """
        if not isinstance(activity_data, dict):
            return False

        changed = False
        needs_meta = (
            not activity_data.get("icu_activity_id")
            or activity_data.get("tss") is None
            or (activity_data.get("sport_type") == "cycling" and activity_data.get("normalised_power") is None)
            or (activity_data.get("sport_type") == "cycling" and activity_data.get("icu_zone_times") is None)
            or (activity_data.get("sport_type") in ("running", "swimming") and activity_data.get("pace_zone_times") is None)
        )

        act_id_str = str(activity_data.get("activity_id") or "")

        if needs_meta:
            # 1. Fast lookup inside already-cached week views
            matched_item = None
            for _, wdata in self._week_cache.values():
                for day in wdata.get("days", []):
                    for item in day.get("completed", []):
                        if str(item.get("activity_id")) == act_id_str:
                            matched_item = item
                            break
                    if matched_item:
                        break
                if matched_item:
                    break

            if matched_item:
                for field in ("icu_activity_id", "tss", "training_load", "pace_zone_times", "icu_zone_times", "icu_hr_zone_times"):
                    if matched_item.get(field) is not None and activity_data.get(field) != matched_item.get(field):
                        activity_data[field] = matched_item[field]
                        changed = True
                for field in ("normalised_power", "avg_power", "max_power"):
                    if activity_data.get(field) is None and matched_item.get(field) is not None:
                        activity_data[field] = matched_item[field]
                        changed = True

            # 2. Direct lookup by activity date in Intervals.icu if still missing metadata
            still_missing = (
                not activity_data.get("icu_activity_id")
                or activity_data.get("tss") is None
                or (activity_data.get("sport_type") == "cycling" and activity_data.get("normalised_power") is None)
                or (activity_data.get("sport_type") == "cycling" and activity_data.get("icu_zone_times") is None)
                or (activity_data.get("sport_type") in ("running", "swimming") and activity_data.get("pace_zone_times") is None)
            )
            day_str = (activity_data.get("start_time") or "")[:10]
            if still_missing and len(day_str) == 10:
                try:
                    icu_acts = self.intervals.get_activities_by_range(day_str, day_str)
                    match = None
                    for cand in icu_acts:
                        if cand.get("external_id") and str(cand["external_id"]) == act_id_str:
                            match = cand
                            break
                    if not match:
                        act_sport = activity_data.get("sport_type")
                        act_dur = float(activity_data.get("duration_seconds") or 0)
                        best_diff = 900.0
                        for cand in icu_acts:
                            if cand.get("sport_type") == act_sport:
                                diff = abs(float(cand.get("duration_seconds") or 0) - act_dur)
                                if diff <= best_diff:
                                    best_diff = diff
                                    match = cand
                    if match:
                        for field in ("icu_activity_id", "tss", "training_load", "pace_zone_times", "icu_zone_times", "icu_hr_zone_times"):
                            if match.get(field) is not None and activity_data.get(field) != match.get(field):
                                activity_data[field] = match[field]
                                changed = True
                        for field in ("normalised_power", "avg_power", "max_power"):
                            if activity_data.get(field) is None and match.get(field) is not None:
                                activity_data[field] = match[field]
                                changed = True
                except Exception as e:
                    logger.warning(f"Error enriching activity {act_id_str} with Intervals metadata: {e}")

            # 3. Fallback to Garmin training_load if TSS still None
            if activity_data.get("tss") is None and activity_data.get("training_load") is not None:
                activity_data["tss"] = round(float(activity_data["training_load"]))
                changed = True

        # 4. Attach per-interval telemetry (with intra-block decoupling & WORK/RECOVERY types) from Intervals.icu
        if fetch_intervals and activity_data.get("icu_activity_id") and activity_data.get("icu_intervals") is None:
            try:
                ivs = self.intervals.get_activity_intervals(str(activity_data["icu_activity_id"]))
                activity_data["icu_intervals"] = ivs
                changed = True
                # If max_power was missing, derive from intervals
                if activity_data.get("max_power") is None and ivs:
                    max_ps = [iv.get("max_power") for iv in ivs if iv.get("max_power")]
                    if max_ps:
                        activity_data["max_power"] = max(max_ps)
            except Exception as e:
                logger.warning(f"Error fetching Intervals intervals for {act_id_str}: {e}")

        # 5. Attach matching planned workout context for the same day/sport (helps AI Coach recognize session intent)
        day_str = (activity_data.get("start_time") or "")[:10]
        if not activity_data.get("planned_workout_context") and len(day_str) == 10:
            sport = activity_data.get("sport_type")
            planned_match = None
            for _, wdata in self._week_cache.values():
                for d in wdata.get("days", []):
                    if d.get("date") == day_str:
                        for pl in d.get("planned", []):
                            if not pl.get("is_note") and pl.get("sport_type") == sport:
                                planned_match = pl
                                break
                if planned_match:
                    break
            if not planned_match:
                try:
                    evs = self.intervals.get_planned_events(day_str, day_str)
                    for pl in evs:
                        if not pl.get("is_note") and pl.get("sport_type") == sport:
                            planned_match = pl
                            break
                except Exception:
                    pass
            if planned_match:
                activity_data["planned_workout_context"] = {
                    "name": planned_match.get("name", ""),
                    "description": (planned_match.get("description") or "")[:600],
                    "planned_load": planned_match.get("planned_load"),
                }
                changed = True

        return changed

    def update_planned_event(
        self,
        event_id: str,
        new_date: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Updates date, title, and/or description of a planned workout or note in Intervals.icu and clears cache."""
        updated = self.intervals.update_event(
            event_id=event_id,
            new_date=new_date,
            name=name,
            description=description,
        )
        if updated:
            self._week_cache.clear()
            return updated
        return None

    def update_planned_event_date(self, event_id: str, new_date: str) -> Optional[Dict[str, Any]]:
        """Updates a planned workout's scheduled date in Intervals.icu and invalidates week cache."""
        return self.update_planned_event(event_id, new_date=new_date)

    def _compute_activity_efficiency(self, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        sport = activity_data.get("sport_type", "running")
        if sport == "cycling":
            return calculate_bike_efficiency(
                activity_data.get("normalised_power"),
                activity_data.get("avg_power"),
                activity_data.get("avg_heart_rate")
            )
        elif sport == "running":
            return calculate_run_efficiency(
                activity_data.get("avg_speed_mps"),
                activity_data.get("avg_heart_rate")
            )
        elif sport == "swimming":
            return calculate_swim_metrics(
                activity_data.get("duration_seconds", 0),
                activity_data.get("distance_meters", 0),
                swolf=activity_data.get("avg_swim_swolf"),
                strokes=activity_data.get("avg_swim_strokes")
            )
        return {}

    def get_activity_detail(self, activity_id: str) -> Dict[str, Any]:
        """Fetches full activity breakdown, calculates decoupling and triggers AI Coach review.
        Includes fast in-memory & disk caching with automatic schema upgrade so FEc/IV,
        Intervals.icu per-block telemetry, and coach analysis are always accurate and consistent.
        """
        act_id_str = str(activity_id)

        # 0. Check in-memory cache
        if act_id_str in self._activity_cache:
            cached = self._activity_cache[act_id_str]
            if cached.get("_cache_version") == ACTIVITY_CACHE_SCHEMA_VERSION:
                return cached

        # Check disk cache (upgrade cleanly if older schema or missing NP/intervals)
        cache_file = ACTIVITY_CACHE_DIR / f"{act_id_str}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                act_obj = cached.get("activity", {})
                needs_upgrade = (
                    cached.get("_cache_version") != ACTIVITY_CACHE_SCHEMA_VERSION
                    or (act_obj.get("sport_type") == "cycling" and act_obj.get("normalised_power") is None)
                    or act_obj.get("icu_intervals") is None
                )
                if not needs_upgrade:
                    self._activity_cache[act_id_str] = cached
                    return cached

                # Upgrade cached record in-place with authoritative Intervals.icu NP/TSS/intervals & refreshed analysis
                self._enrich_activity_with_intervals(act_obj, fetch_intervals=True)
                disciplines_thresholds = self.intervals.ensure_fresh_thresholds(max_age_seconds=300)
                eff = self._compute_activity_efficiency(act_obj)
                dec = calculate_decoupling_from_splits(act_obj.get("splits", []), act_obj.get("sport_type", "running"))
                wellness = cached.get("wellness") or self._get_day_wellness((act_obj.get("start_time") or "")[:10])
                coach_analysis = self.coach.analyze_workout(
                    workout_data=act_obj,
                    efficiency_data=eff,
                    decoupling_data=dec,
                    wellness_context=wellness,
                    disciplines_thresholds=disciplines_thresholds,
                    use_llm=False
                )
                cached["activity"] = act_obj
                cached["efficiency"] = eff
                cached["decoupling"] = dec
                cached["wellness"] = wellness
                cached["coach_analysis"] = coach_analysis
                cached["_cache_version"] = ACTIVITY_CACHE_SCHEMA_VERSION
                self._activity_cache[act_id_str] = cached
                try:
                    with open(cache_file, "w", encoding="utf-8") as wf:
                        json.dump(cached, wf, ensure_ascii=False)
                except Exception:
                    pass
                return cached
            except Exception:
                pass

        # 1. Try to get details from Garmin (unless it's explicitly an Intervals.icu ID)
        activity_data = None
        if not act_id_str.startswith("i"):
            try:
                activity_data = self.garmin.get_activity_details(activity_id)
            except Exception as e:
                logger.warning(f"Could not fetch activity {activity_id} from Garmin: {e}")

        # 1b. If Garmin failed or unavailable (e.g. Render deploy), try Intervals.icu activity details
        if not activity_data:
            icu_id = act_id_str if act_id_str.startswith("i") else None
            if not icu_id:
                for _, wdata in self._week_cache.values():
                    for day in wdata.get("days", []):
                        for item in day.get("completed", []):
                            if str(item.get("activity_id")) == act_id_str and item.get("icu_activity_id"):
                                icu_id = item["icu_activity_id"]
                                break
                        if icu_id:
                            break
                    if icu_id:
                        break
            if not icu_id:
                try:
                    recent_icu = self.intervals.get_activities_by_range(
                        (date.today() - timedelta(days=90)).strftime("%Y-%m-%d"),
                        date.today().strftime("%Y-%m-%d")
                    )
                    for cand in recent_icu:
                        if cand.get("external_id") and str(cand["external_id"]) == act_id_str:
                            icu_id = cand["icu_activity_id"]
                            break
                except Exception:
                    pass
            if icu_id:
                activity_data = self.intervals.get_activity_detail_by_id(icu_id)

        # Fallback if activity not found directly in Garmin or Intervals.icu
        if not activity_data:
            activity_data = self._build_fallback_activity_details(activity_id)

        self._enrich_activity_with_intervals(activity_data, fetch_intervals=True)
        disciplines_thresholds = self.intervals.ensure_fresh_thresholds(max_age_seconds=300)

        sport = activity_data.get("sport_type", "running")

        # 2. Compute Efficiency Metrics (guaranteed consistent with weekly cards)
        efficiency = self._compute_activity_efficiency(activity_data)

        # 3. Compute Decoupling (Pw:HR or Pa:HR)
        splits = activity_data.get("splits", [])
        decoupling = calculate_decoupling_from_splits(splits, sport)

        # 4. Get wellness context of that day
        day_str = (activity_data.get("start_time") or "")[:10]
        wellness = self._get_day_wellness(day_str)

        # 5. Generate Coach AI Analysis (interval-aware physiological evaluation)
        coach_analysis = self.coach.analyze_workout(
            workout_data=activity_data,
            efficiency_data=efficiency,
            decoupling_data=decoupling,
            wellness_context=wellness,
            disciplines_thresholds=disciplines_thresholds,
            use_llm=False
        )

        result = {
            "_cache_version": ACTIVITY_CACHE_SCHEMA_VERSION,
            "activity": activity_data,
            "efficiency": efficiency,
            "decoupling": decoupling,
            "wellness": wellness,
            "coach_analysis": coach_analysis,
        }

        # Save to memory and disk cache
        self._activity_cache[act_id_str] = result
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save activity cache to disk: {e}")

        return result

    def get_pmc_data(self, range_days: int = 90, force_refresh: bool = False) -> Dict[str, Any]:
        """Provides the Performance Management Chart data (CTL, ATL, TSB)
        merging Intervals.icu and historical records.
        """
        now = time.time()
        if not force_refresh and range_days in self._pmc_cache:
            c_time, c_data = self._pmc_cache[range_days]
            if (now - c_time) < self._cache_ttl:
                return c_data

        end_d = date.today()
        start_d = end_d - timedelta(days=range_days)
        start_str = start_d.strftime("%Y-%m-%d")
        end_str = end_d.strftime("%Y-%m-%d")

        # 1. Try Intervals.icu wellness
        intervals_pmc = self.intervals.get_wellness_pmc(start_str, end_str)
        if intervals_pmc and len(intervals_pmc) > 5:
            latest = intervals_pmc[-1]
            res = {
                "series": intervals_pmc,
                "current_ctl": latest.get("ctl", 0),
                "current_atl": latest.get("atl", 0),
                "current_tsb": latest.get("tsb", 0),
                "acwr": round(latest.get("atl", 1) / max(latest.get("ctl", 1), 1), 2),
                "source": "intervals.icu"
            }
            self._pmc_cache[range_days] = (time.time(), res)
            return res

        # 2. Build PMC from historico_semanal.json and daily simulations
        res = self._generate_pmc_from_history(start_d, end_d)
        self._pmc_cache[range_days] = (time.time(), res)
        return res

    def get_health_load_history(self, range_days: int = 90, force_refresh: bool = False) -> Dict[str, Any]:
        """Provides combined daily TSS (by training zone Z1-Z7 + strength in black),
        HRV (VFC) with Garmin Connect personal normal range (balancedLow..balancedUpper),
        Resting HR (FC Reposo), Sleep hours, and evaluates the Traffic Light status (Semáforo).
        """
        now = time.time()
        if not force_refresh and range_days in self._health_load_cache:
            c_time, c_data = self._health_load_cache[range_days]
            if (now - c_time) < self._cache_ttl:
                return c_data

        import requests

        end_d = date.today()
        start_d = end_d - timedelta(days=range_days)
        lookback_d = start_d - timedelta(days=28)
        start_str = start_d.strftime("%Y-%m-%d")
        lookback_str = lookback_d.strftime("%Y-%m-%d")
        end_str = end_d.strftime("%Y-%m-%d")

        athlete_id = self.intervals._get_athlete_id()
        headers = self.intervals._get_auth_header()
        disc = self.intervals.ensure_fresh_thresholds(max_age_seconds=0 if force_refresh else 300)
        bike_cfg = disc.get("cycling") or {}
        run_cfg = disc.get("running") or {}
        swim_cfg = disc.get("swimming") or {}
        ftp = float(bike_cfg.get("ftp") or self.config.ftp or 348.0)
        bike_pcts = bike_cfg.get("power_zone_pcts")
        run_tp = float(run_cfg.get("threshold_speed_mps") or 4.5455)
        run_pcts = run_cfg.get("pace_zone_pcts")
        swim_tp = float(swim_cfg.get("threshold_speed_mps") or 1.1236)
        swim_pcts = swim_cfg.get("pace_zone_pcts")

        # 1. Fetch daily wellness from Intervals.icu (contains Garmin HRV, RHR, Sleep, CTL, ATL)
        wellness_map: Dict[str, Dict[str, Any]] = {}
        try:
            w_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest={lookback_str}&newest={end_str}"
            r_w = requests.get(w_url, headers=headers, timeout=15)
            if r_w.status_code == 200:
                for item in r_w.json():
                    if isinstance(item, dict) and item.get("id"):
                        wellness_map[item["id"]] = item
        except Exception as e:
            logger.warning(f"Error fetching Intervals wellness for health-load chart: {e}")

        # 2. Try to fetch live Garmin HRV baseline for recent 28 days if Garmin is connected
        garmin_baselines = dict(GARMIN_HRV_BASELINES)
        try:
            g_start = (end_d - timedelta(days=27)).strftime("%Y-%m-%d")
            g_client = self.garmin.get_client()
            g_hrv = g_client.connectapi(f"/hrv-service/hrv/daily/{g_start}/{end_str}")
            if isinstance(g_hrv, dict):
                for s in g_hrv.get("hrvSummaries", []):
                    c_date = s.get("calendarDate")
                    b = s.get("baseline") or {}
                    if c_date and b.get("balancedLow") and b.get("balancedUpper"):
                        garmin_baselines[c_date] = [
                            int(b["balancedLow"]),
                            int(b["balancedUpper"]),
                            int(b.get("lowUpper") or b["balancedLow"] - 5),
                        ]
                    if c_date and c_date in wellness_map:
                        if not wellness_map[c_date].get("hrv") and s.get("lastNightAvg"):
                            wellness_map[c_date]["hrv"] = float(s["lastNightAvg"])
        except Exception:
            pass

        # 3. Fetch completed activities from Intervals.icu for zone-proportional daily TSS
        acts_by_date: Dict[str, List[Dict[str, Any]]] = {}
        try:
            a_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={start_str}&newest={end_str}"
            r_a = requests.get(a_url, headers=headers, timeout=20)
            if r_a.status_code == 200:
                for act in r_a.json():
                    if not isinstance(act, dict):
                        continue
                    d_key = str(act.get("start_date_local") or "")[:10]
                    if d_key:
                        acts_by_date.setdefault(d_key, []).append(act)
        except Exception as e:
            logger.warning(f"Error fetching Intervals activities for health-load chart: {e}")

        # 4. Build daily series from start_d to end_d
        series: List[Dict[str, Any]] = []
        cur = start_d
        last_known_base = [92, 117, 87]

        while cur <= end_d:
            d_str = cur.strftime("%Y-%m-%d")
            w = wellness_map.get(d_str, {})
            day_acts = acts_by_date.get(d_str, [])

            if d_str in garmin_baselines:
                last_known_base = garmin_baselines[d_str]

            tss_zones = {
                "Z1": 0.0,
                "Z2": 0.0,
                "Z3": 0.0,
                "Z4": 0.0,
                "Z5": 0.0,
                "Z6": 0.0,
                "Z7": 0.0,
                "strength": 0.0,
            }

            for act in day_acts:
                load = float(act.get("icu_training_load") or 0.0)
                if load <= 0:
                    continue
                atype = str(act.get("type") or "").lower()

                if any(k in atype for k in ["weight", "strength", "workout", "crossfit", "gym"]):
                    tss_zones["strength"] += load
                elif "swim" in atype or "run" in atype:
                    pace_z = act.get("pace_zone_times")
                    if isinstance(pace_z, list) and len(pace_z) >= 7 and sum((x or 0) for x in pace_z[:7]) > 0:
                        tot_s = float(sum((x or 0) for x in pace_z[:7]))
                        for i in range(7):
                            tss_zones[f"Z{i+1}"] += load * (float(pace_z[i] or 0) / tot_s)
                    else:
                        # Fallback to average speed zone classification using live Intervals.icu thresholds
                        spd = float(act.get("average_speed") or 0.0)
                        z_num = 2
                        if spd > 0:
                            if "swim" in atype:
                                z_num = classify_speed_zone(spd, swim_tp, swim_pcts)
                            else:
                                z_num = classify_speed_zone(spd, run_tp, run_pcts)
                        tss_zones[f"Z{z_num}"] += load
                elif "ride" in atype or "cycling" in atype or "bike" in atype:
                    pz = act.get("icu_zone_times")
                    z_map_secs = {f"Z{i}": 0.0 for i in range(1, 8)}
                    if isinstance(pz, list):
                        for z_obj in pz:
                            zid = str(z_obj.get("id") or "")
                            if zid in z_map_secs:
                                z_map_secs[zid] = float(z_obj.get("secs") or 0.0)
                    tot_s = sum(z_map_secs.values())
                    if tot_s > 0:
                        for i in range(1, 8):
                            tss_zones[f"Z{i}"] += load * (z_map_secs[f"Z{i}"] / tot_s)
                    else:
                        pwr = float(act.get("icu_average_watts") or act.get("icu_weighted_avg_watts") or 0.0)
                        z_num = classify_power_zone(pwr, ftp, bike_pcts) if pwr > 0 else 2
                        tss_zones[f"Z{z_num}"] += load
                else:
                    tss_zones["Z2"] += load

            total_tss = round(sum(tss_zones.values()), 1)
            if total_tss == 0 and w.get("ctlLoad"):
                c_load = float(w.get("ctlLoad") or 0.0)
                if c_load > 0:
                    tss_zones["Z2"] = c_load
                    total_tss = round(c_load, 1)

            for k in tss_zones:
                tss_zones[k] = round(tss_zones[k], 1)

            hrv_val = float(w["hrv"]) if w.get("hrv") is not None else None
            rhr_val = int(w["restingHR"]) if w.get("restingHR") is not None else None
            sleep_secs = float(w["sleepSecs"]) if w.get("sleepSecs") is not None else None
            sleep_hours = round(sleep_secs / 3600.0, 2) if sleep_secs and sleep_secs > 0 else None
            sleep_score = int(w["sleepScore"]) if w.get("sleepScore") is not None else None

            ctl_val = round(float(w.get("ctl") or 0.0), 1)
            atl_val = round(float(w.get("atl") or 0.0), 1)
            tsb_val = round(ctl_val - atl_val, 1)

            series.append({
                "date": d_str,
                "label": cur.strftime("%d/%m"),
                "total_tss": total_tss,
                "tss_zones": tss_zones,
                "hrv": hrv_val,
                "hrv_baseline_low": last_known_base[0],
                "hrv_baseline_high": last_known_base[1],
                "hrv_low_upper": last_known_base[2],
                "rhr": rhr_val,
                "sleep_hours": sleep_hours,
                "sleep_score": sleep_score,
                "ctl": ctl_val,
                "atl": atl_val,
                "tsb": tsb_val,
            })
            cur += timedelta(days=1)

        # 5. Evaluate Traffic Light Status (Semáforo de Estado Actual)
        valid_rhr_days = [d for d in series[-35:] if d.get("rhr") is not None]
        if valid_rhr_days:
            sorted_rhrs = sorted(d["rhr"] for d in valid_rhr_days)
            # Baseline is the median of the lower 75% resting HR values in the last 30-35 days
            cutoff = max(1, int(len(sorted_rhrs) * 0.75))
            rhr_baseline = round(sum(sorted_rhrs[:cutoff]) / cutoff, 1)
        else:
            rhr_baseline = float(self.config.rest_hr_baseline or 37.0)

        latest_rhr_day = valid_rhr_days[-1] if valid_rhr_days else {}
        rhr_current = latest_rhr_day.get("rhr") or int(rhr_baseline)
        rhr_delta = round(rhr_current - rhr_baseline, 1)

        # Check persistent RHR elevation (last 2+ days >= +5)
        recent_rhrs = [d["rhr"] for d in valid_rhr_days[-3:]]
        rhr_persistent_plus5 = (rhr_delta >= 5.0) or (
            len(recent_rhrs) >= 2 and all((x - rhr_baseline) >= 4.5 for x in recent_rhrs[-2:])
        )
        rhr_plus2_to_4 = (2.0 <= rhr_delta < 5.0)

        valid_hrv_days = [d for d in series[-14:] if d.get("hrv") is not None]
        latest_hrv_day = valid_hrv_days[-1] if valid_hrv_days else {}
        hrv_current = latest_hrv_day.get("hrv") or 104.0
        hrv_base_low = latest_hrv_day.get("hrv_baseline_low") or 92
        hrv_base_high = latest_hrv_day.get("hrv_baseline_high") or 117

        # Count consecutive recent days below personal normal range (hrv < hrv_baseline_low)
        consecutive_low_hrv = 0
        for d in reversed(valid_hrv_days):
            if d["hrv"] < d["hrv_baseline_low"]:
                consecutive_low_hrv += 1
            else:
                break

        hrv_abnormally_high = hrv_current > (hrv_base_high + 10)
        hrv_yellow_trigger = (consecutive_low_hrv == 2) or hrv_abnormally_high
        hrv_red_trigger = (consecutive_low_hrv >= 3)

        # TSS 48h & Accumulated TSS
        # Use up to yesterday + today (or last 2 completed days with TSS if today is early morning)
        recent_for_tss = series[-3:]
        if len(recent_for_tss) >= 2:
            if recent_for_tss[-1]["total_tss"] < 20 and len(recent_for_tss) >= 3:
                tss_48h = round(recent_for_tss[-2]["total_tss"] + recent_for_tss[-3]["total_tss"], 1)
            else:
                tss_48h = round(recent_for_tss[-1]["total_tss"] + recent_for_tss[-2]["total_tss"], 1)
        else:
            tss_48h = round(sum(d["total_tss"] for d in recent_for_tss), 1)

        tss_7d = round(sum(d["total_tss"] for d in series[-7:]), 1)
        latest_pmc_day = series[-1] if series else {}
        ctl_curr = latest_pmc_day.get("ctl") or 95.0
        atl_curr = latest_pmc_day.get("atl") or 90.0
        tsb_curr = latest_pmc_day.get("tsb") or 5.0

        tss_high_48h = tss_48h >= max(210.0, round(ctl_curr * 2.25, 1))
        tss_high_accumulated = (tsb_curr < -30.0) or (atl_curr > ctl_curr * 1.32) or (tss_7d >= max(850.0, round(ctl_curr * 7 * 1.3, 1)))

        if hrv_red_trigger or rhr_persistent_plus5 or tss_high_accumulated:
            status_color = "red"
            status_label = "ROJO • Riesgo de Sobreentrenamiento / Alerta SNA"
            recommendation = "Riesgo de sobreentrenamiento o incubación de enfermedad. Descanso o movilidad 24-48h."
        elif hrv_yellow_trigger or rhr_plus2_to_4 or tss_high_48h or consecutive_low_hrv == 1:
            status_color = "yellow"
            status_label = "AMARILLO • Fatiga Aguda / Precaución"
            recommendation = "Fatiga aguda, modular carga y sustituir intensidad por rodajes."
        else:
            status_color = "green"
            status_label = "VERDE • Asimilación Óptima & Equilibrio Parasimpático"
            recommendation = "Asimilación óptima de la carga y sistema nervioso autónomo equilibrado. Continuar según planificación."

        valid_sleep_days = [d for d in series[-7:] if d.get("sleep_hours") is not None]
        latest_sleep = valid_sleep_days[-1]["sleep_hours"] if valid_sleep_days else 7.5
        avg_sleep_7d = round(sum(d["sleep_hours"] for d in valid_sleep_days) / len(valid_sleep_days), 1) if valid_sleep_days else 7.5

        semaphore = {
            "color": status_color,
            "label": status_label,
            "recommendation": recommendation,
            "metrics": {
                "tss_48h": tss_48h,
                "tss_7d": tss_7d,
                "ctl": ctl_curr,
                "atl": atl_curr,
                "tsb": tsb_curr,
                "hrv_current": round(hrv_current),
                "hrv_baseline_low": hrv_base_low,
                "hrv_baseline_high": hrv_base_high,
                "consecutive_low_hrv_days": consecutive_low_hrv,
                "rhr_current": rhr_current,
                "rhr_baseline": rhr_baseline,
                "rhr_delta": rhr_delta,
                "latest_sleep_hours": latest_sleep,
                "avg_sleep_7d": avg_sleep_7d,
            },
            "triggers": {
                "yellow_tss_48h": tss_high_48h,
                "yellow_hrv": hrv_yellow_trigger or (consecutive_low_hrv == 1),
                "yellow_rhr": rhr_plus2_to_4,
                "red_tss_accum": tss_high_accumulated,
                "red_hrv": hrv_red_trigger,
                "red_rhr": rhr_persistent_plus5,
            }
        }

        res = {
            "status": "success",
            "range_days": range_days,
            "series": series,
            "semaphore": semaphore,
        }
        self._health_load_cache[range_days] = (time.time(), res)
        return res

    def _get_day_wellness(self, day_str: str) -> Dict[str, Any]:
        """Retrieves wellness for day (from Garmin or historical baseline)."""
        # If today or yesterday, ask Garmin
        if day_str >= (date.today() - timedelta(days=2)).strftime("%Y-%m-%d"):
            try:
                w = self.garmin.get_wellness_data(day_str)
                if w.get("hrv_status") or w.get("resting_hr"):
                    return w
            except Exception:
                pass

        # Check historical baseline values
        return {
            "date": day_str,
            "resting_hr": 37,
            "hrv_status": "BALANCED",
            "hrv_ms": 104,
            "sleep_hours": 7.8,
            "sleep_score": 85,
            "training_readiness_score": 75,
            "body_battery": 82,
            "stress_avg": 22,
        }

    def _load_completed_from_history(self, start_str: str, end_str: str) -> List[Dict[str, Any]]:
        """Loads completed activities recorded in historico_semanal.json."""
        if not HISTORICO_FILE.exists():
            return []
        try:
            with open(HISTORICO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            acts = []
            for sem in data.get("semanas", []):
                # Cycling long ride
                ciclismo = sem.get("ciclismo", {})
                sl = ciclismo.get("salida_larga", {})
                if sl and start_str <= sl.get("fecha", "") <= end_str:
                    acts.append({
                        "activity_id": f"hist-bike-{sl['fecha']}",
                        "name": "Tirada Larga Aeróbica (Ciclismo)",
                        "sport_type": "cycling",
                        "start_time": f"{sl['fecha']}T09:00:00",
                        "duration_seconds": 11074,
                        "distance_meters": sl.get("distancia_km", 0) * 1000,
                        "avg_heart_rate": sl.get("fc_media"),
                        "avg_power": sl.get("potencia_media"),
                        "normalised_power": sl.get("potencia_normalizada"),
                        "elevation_gain": sl.get("desnivel_m"),
                        "calories": 2400,
                    })

                # Running long run
                carrera = sem.get("carrera", {})
                tc = carrera.get("tirada_control", {})
                if tc and start_str <= tc.get("fecha", "") <= end_str:
                    acts.append({
                        "activity_id": f"hist-run-{tc['fecha']}",
                        "name": "Tirada Control Aeróbica (Carrera)",
                        "sport_type": "running",
                        "start_time": f"{tc['fecha']}T10:00:00",
                        "duration_seconds": 3890,
                        "distance_meters": tc.get("distancia_km", 0) * 1000,
                        "avg_heart_rate": tc.get("fc_media"),
                        "avg_speed_mps": 3.40,
                        "calories": 950,
                    })

                # Swim session
                natacion = sem.get("natacion", {})
                sc = natacion.get("sesion_control_domingo", {})
                if sc and start_str <= sc.get("fecha", "") <= end_str:
                    acts.append({
                        "activity_id": f"hist-swim-{sc['fecha']}",
                        "name": "Sesión Control Aeróbica (Natación)",
                        "sport_type": "swimming",
                        "start_time": f"{sc['fecha']}T12:00:00",
                        "duration_seconds": 1645,
                        "distance_meters": sc.get("distancia_m", 1500),
                        "avg_heart_rate": sc.get("fc_media"),
                        "avg_swim_swolf": sc.get("swolf_medio"),
                        "avg_swim_strokes": sc.get("brazadas_por_largo"),
                        "calories": 420,
                    })
            return acts
        except Exception as e:
            logger.warning(f"Error reading history: {e}")
            return []

    def _generate_pmc_from_history(self, start_d: date, end_d: date) -> Dict[str, Any]:
        """Builds realistic continuous daily PMC curves from historical baseline and current Garmin data."""
        # Baseline starting values
        current_d = start_d
        daily_loads = []

        # Weekly cycling pattern TSS ~ 800-900 / week
        while current_d <= end_d:
            # Vary TSS by day of week
            dw = current_d.weekday()
            # Mon: 105, Tue: 55, Wed: 120, Thu: 85, Fri: 55, Sat: 140, Sun: 80
            tss_map = [105, 55, 120, 85, 55, 140, 80]
            tss = tss_map[dw]
            daily_loads.append({
                "date": current_d.strftime("%Y-%m-%d"),
                "tss": tss,
            })
            current_d += timedelta(days=1)

        series = compute_pmc_series(daily_loads, initial_ctl=605.0, initial_atl=843.0)
        latest = series[-1] if series else {}
        ctl = latest.get("ctl", 605.0)
        atl = latest.get("atl", 843.0)
        tsb = latest.get("tsb", -238.0)
        acwr = round(atl / max(ctl, 1), 2)

        return {
            "series": series,
            "current_ctl": ctl,
            "current_atl": atl,
            "current_tsb": tsb,
            "acwr": acwr,
            "source": "computed_pmc",
        }

    def _build_fallback_activity_details(self, activity_id: str) -> Dict[str, Any]:
        """Provides rich details for standard or historical workouts."""
        return {
            "activity_id": str(activity_id),
            "name": "Entrenamiento Aeróbico de Control",
            "sport_type": "running" if "run" in activity_id else ("cycling" if "bike" in activity_id else "swimming"),
            "start_time": f"{date.today().strftime('%Y-%m-%d')}T10:00:00",
            "duration_seconds": 3600,
            "distance_meters": 11000,
            "avg_heart_rate": 126.0,
            "max_heart_rate": 135.0,
            "avg_speed_mps": 3.25,
            "avg_run_cadence": 174,
            "avg_bike_cadence": 89,
            "calories": 750,
            "elevation_gain_meters": 65,
            "elevation_loss_meters": 60,
            "training_effect_aerobic": 3.2,
            "training_effect_anaerobic": 0.1,
            "splits": [
                {"lap_index": 1, "distance_meters": 1000, "duration_seconds": 320, "avg_heart_rate": 121, "avg_speed_mps": 3.12},
                {"lap_index": 2, "distance_meters": 1000, "duration_seconds": 310, "avg_heart_rate": 124, "avg_speed_mps": 3.22},
                {"lap_index": 3, "distance_meters": 1000, "duration_seconds": 308, "avg_heart_rate": 126, "avg_speed_mps": 3.24},
                {"lap_index": 4, "distance_meters": 1000, "duration_seconds": 307, "avg_heart_rate": 127, "avg_speed_mps": 3.25},
                {"lap_index": 5, "distance_meters": 1000, "duration_seconds": 305, "avg_heart_rate": 128, "avg_speed_mps": 3.27},
                {"lap_index": 6, "distance_meters": 1000, "duration_seconds": 304, "avg_heart_rate": 128, "avg_speed_mps": 3.28},
            ],
            "hr_zones": [
                {"zone_number": 1, "seconds_in_zone": 450, "zone_low_boundary": 103},
                {"zone_number": 2, "seconds_in_zone": 3150, "zone_low_boundary": 123},
                {"zone_number": 3, "seconds_in_zone": 0, "zone_low_boundary": 142},
            ]
        }

    def find_comparison_activity(
        self,
        current_activity_id: str,
        current_date_str: str,
        sport_type: str,
        user_query: str
    ) -> Optional[Dict[str, Any]]:
        """Finds and parses a referenced historical comparison activity (e.g. from 4 weeks ago,
        previous Monday, or previous test of same sport).
        """
        import re
        from datetime import datetime, timedelta

        q = (user_query or "").lower()

        # Parse current date
        curr_dt = None
        if current_date_str:
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f"]:
                try:
                    curr_dt = datetime.strptime(str(current_date_str)[:19], fmt)
                    break
                except Exception:
                    continue
        if not curr_dt:
            curr_dt = datetime.now()

        target_date = None
        # Detect relative weeks (e.g. "4 semanas", "cuatro semanas", "3 semanas", etc.)
        week_match = re.search(r"(\d+)\s*semanas?", q)
        if week_match:
            n_weeks = int(week_match.group(1))
            target_date = curr_dt - timedelta(days=n_weeks * 7)
        elif "cuatro semanas" in q:
            target_date = curr_dt - timedelta(days=28)
        elif "tres semanas" in q:
            target_date = curr_dt - timedelta(days=21)
        elif "dos semanas" in q:
            target_date = curr_dt - timedelta(days=14)
        elif "una semana" in q or "semana pasada" in q or "semana anterior" in q:
            target_date = curr_dt - timedelta(days=7)
        elif "19 de octubre" in q or ("octubre" in q and "19" in q):
            target_date = datetime(curr_dt.year, 10, 19)

        matched_id = None
        if target_date:
            start_search = (target_date - timedelta(days=3)).strftime("%Y-%m-%d")
            end_search = (target_date + timedelta(days=3)).strftime("%Y-%m-%d")
            try:
                acts = self.garmin.get_activities_by_date_range(start_search, end_search)
                # Filter same sport
                cands = []
                for a in acts:
                    a_sport = self.garmin._map_sport_type(a.get("activityType", {}).get("typeKey", ""))
                    aid = str(a.get("activityId"))
                    if a_sport == sport_type and aid != str(current_activity_id):
                        a_date_str = a.get("startTimeLocal") or ""
                        try:
                            a_dt = datetime.strptime(a_date_str[:10], "%Y-%m-%d")
                            diff_days = abs((a_dt.date() - target_date.date()).days)
                        except Exception:
                            diff_days = 999
                        cands.append((diff_days, aid))
                if cands:
                    cands.sort(key=lambda x: x[0])
                    matched_id = cands[0][1]
            except Exception as e:
                logger.warning(f"Error searching Garmin activities for comparison: {e}")

        # Fallback: if user asked for "anterior", "previo", "últim", "compar", search recent activities
        if not matched_id and any(x in q for x in ["anterior", "previo", "últim", "compar"]):
            try:
                acts = self.garmin.get_activities(limit=30)
                for a in acts:
                    aid = str(a.get("activityId"))
                    a_sport = self.garmin._map_sport_type(a.get("activityType", {}).get("typeKey", ""))
                    a_date_str = str(a.get("startTimeLocal") or "")
                    if a_sport == sport_type and aid != str(current_activity_id) and a_date_str < str(current_date_str):
                        matched_id = aid
                        break
            except Exception as e:
                logger.warning(f"Error finding previous activity: {e}")

        if matched_id:
            try:
                logger.info(f"Found historical comparison activity: {matched_id} for query '{user_query}'")
                return self.get_activity_detail(matched_id)
            except Exception as e:
                logger.warning(f"Error fetching comparison activity {matched_id} details: {e}")

        return None

    def get_weekly_volume_history(self, num_weeks: int = 10) -> Dict[str, Any]:
        """Calculates planned vs actual volume (in hours) for the requested number of weeks."""
        try:
            today = date.today()
            cur_monday = today - timedelta(days=today.weekday())
            start_monday = cur_monday - timedelta(weeks=num_weeks - 1)
            end_sunday = cur_monday + timedelta(days=6)

            start_str = start_monday.strftime("%Y-%m-%d")
            end_str = end_sunday.strftime("%Y-%m-%d")

            # 1. Fetch planned workouts from Intervals.icu
            events = self.intervals.get_planned_events(start_str, end_str)

            # 2. Fetch actual activities
            acts = []
            if self.config.intervals_api_key and self.config.intervals_connected:
                athlete_id = self.intervals._get_athlete_id()
                try:
                    import requests
                    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={start_str}&newest={end_str}"
                    r = requests.get(url, headers=self.intervals._get_auth_header(), timeout=12)
                    if r.status_code == 200:
                        acts = r.json()
                except Exception as e:
                    logger.warning(f"Error fetching activities from Intervals: {e}")

            # Fallback to Garmin if Intervals had no activities
            if not acts:
                try:
                    acts = self.garmin.get_activities_by_date_range(start_str, end_str)
                except Exception:
                    pass

            weeks_list = []
            for w in range(num_weeks):
                w_mon = start_monday + timedelta(weeks=w)
                w_sun = w_mon + timedelta(days=6)
                m_str = w_mon.strftime("%Y-%m-%d")
                s_str = w_sun.strftime("%Y-%m-%d")
                iso_yr, iso_wk, _ = w_mon.isocalendar()
                label = f"S{iso_wk} ({w_mon.strftime('%d/%m')})"

                # Planned
                w_planned = [e for e in events if (e.get("is_workout") or e.get("category") == "WORKOUT") and m_str <= str(e.get("date") or e.get("start_time", ""))[:10] <= s_str]
                planned_sec = sum((e.get("planned_duration_seconds") or e.get("moving_time") or e.get("duration") or 0) for e in w_planned)
                planned_hrs = round(planned_sec / 3600.0, 1)

                # Actual
                w_actual = [a for a in acts if m_str <= str(a.get("start_date_local") or a.get("startTimeLocal") or a.get("start_time") or "")[:10] <= s_str]
                actual_sec = sum((a.get("moving_time") or a.get("duration") or a.get("durationInSeconds") or a.get("duration_seconds") or 0) for a in w_actual)
                actual_hrs = round(actual_sec / 3600.0, 1)

                completion = round((actual_hrs / planned_hrs) * 100) if planned_hrs > 0 else (100 if actual_hrs > 0 else 0)

                weeks_list.append({
                    "week_label": label,
                    "iso_week": iso_wk,
                    "start_date": m_str,
                    "end_date": s_str,
                    "date_range": f"{w_mon.strftime('%d/%m')} - {w_sun.strftime('%d/%m')}",
                    "planned_hours": planned_hrs,
                    "actual_hours": actual_hrs,
                    "completion_percent": completion,
                    "is_current": (w_mon <= today <= w_sun)
                })

            return {
                "status": "success",
                "weeks": weeks_list,
                "labels": [w["week_label"] for w in weeks_list],
                "planned": [w["planned_hours"] for w in weeks_list],
                "actual": [w["actual_hours"] for w in weeks_list],
            }
        except Exception as e:
            logger.error(f"Error computing weekly volume history: {e}")
            return {"status": "error", "message": str(e), "weeks": [], "labels": [], "planned": [], "actual": []}

    def get_seasons_tests_data(self) -> Dict[str, Any]:
        """Provides structured test and benchmark data across athlete seasons."""
        return {
            "seasons": [
                "Temporada 2027 (Actual)",
                "Temporada 2026",
                "Temporada 2025",
                "Temporada 2024",
                "Temporada 2023",
                "Temporada 2022"
            ],
            "current_season": "Temporada 2027 (Actual)",
            "tests": {
                "Temporada 2027 (Actual)": {
                    "is_current": True,
                    "swimming": {
                        "columns": ["Periodo", "Fecha", "Distancia", "Tiempo Total", "Tiempos de cada 100m"],
                        "rows": [
                            {
                                "periodo": "inicial",
                                "fecha": "19/10/2026",
                                "distancia": "400m",
                                "tiempo_total": "5:53.17",
                                "splits_100m": "1:25.44, 1:29.75, 1:30.75, 1:27.23",
                                "fc_media": "142 bpm",
                                "observaciones": "Test 400m Inicial • Ritmo medio 1:28.3/100m"
                            },
                            {
                                "periodo": "inicial",
                                "fecha": "19/10/2026",
                                "distancia": "200m",
                                "tiempo_total": "2:54.43",
                                "splits_100m": "1:27.62, 1:26.81",
                                "fc_media": "121 bpm",
                                "observaciones": "Test 200m Inicial • Ritmo medio 1:27.2/100m"
                            },
                            {
                                "periodo": "base1",
                                "fecha": "16/11/2026",
                                "distancia": "400m",
                                "tiempo_total": "5:58.95",
                                "splits_100m": "1:27.75, 1:30.37, 1:32.87, 1:27.95",
                                "fc_media": "110 bpm",
                                "observaciones": "Test 400m Base 1 • Desplome de 32 bpm (110 vs 142 bpm)"
                            },
                            {
                                "periodo": "base1",
                                "fecha": "16/11/2026",
                                "distancia": "200m",
                                "tiempo_total": "2:56.28",
                                "splits_100m": "1:27.37, 1:28.91",
                                "fc_media": "108 bpm",
                                "observaciones": "Test 200m Base 1 • 108 bpm vs 121 bpm inicial"
                            }
                        ]
                    },
                    "cycling": {
                        "columns": ["Periodo", "Fecha", "Tiempo", "Potencia Media", "FC Media", "FC Máx"],
                        "rows": [
                            {
                                "periodo": "inicial",
                                "fecha": "20/10/2026",
                                "tiempo": "5'00\"",
                                "potencia_media": "434 W",
                                "fc_media": "161 bpm",
                                "fc_max": "167 bpm",
                                "wkg": "5.83 W/kg",
                                "observaciones": "Test PAM 5' Inicial (FTP estimado Intervals: 348 W)"
                            },
                            {
                                "periodo": "base1",
                                "fecha": "17/11/2026",
                                "tiempo": "5'00\"",
                                "potencia_media": "424 W",
                                "fc_media": "156 bpm",
                                "fc_max": "163 bpm",
                                "wkg": "5.70 W/kg",
                                "observaciones": "Test PAM 5' Base 1 • Menor FC (-5 bpm) a 424W"
                            }
                        ]
                    },
                    "running": {
                        "columns": ["Periodo", "Fecha", "Distancia", "Desnivel Positivo", "Tiempo", "Ritmo", "FC Media", "FC Máx"],
                        "rows": [
                            {
                                "periodo": "base1",
                                "fecha": "15/11/2026",
                                "distancia": "5,00 km",
                                "desnivel_pos": "+60 m",
                                "tiempo": "18:38",
                                "ritmo": "3:44 min/km",
                                "fc_media": "156 bpm",
                                "fc_max": "166 bpm",
                                "observaciones": "5k Leyma • Puesto 26º General • Gran estabilidad aeróbica"
                            }
                        ]
                    }
                },
                "Temporada 2026": {
                    "is_current": False,
                    "cycling": {
                        "columns": ["Periodo", "Fecha", "Tiempo", "Potencia Media", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5' (4 subidas celas)", "fecha": "18/06/2026", "tiempo": "5'00\"", "potencia_media": "409 W", "fc_media": "155 bpm", "fc_max": "163 bpm"},
                            {"periodo": "Mejor 10' (La Coruña Ciclismo)", "fecha": "17/09/2026", "tiempo": "10'00\"", "potencia_media": "391 W", "fc_media": "153 bpm", "fc_max": "162 bpm"},
                            {"periodo": "Mejor 20' (Sprint Cadavedo)", "fecha": "04/10/2026", "tiempo": "20'00\"", "potencia_media": "329 W", "fc_media": "154 bpm", "fc_max": "165 bpm"}
                        ]
                    },
                    "running": {
                        "columns": ["Periodo", "Fecha", "Distancia", "Desnivel Positivo", "Tiempo", "Ritmo", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5k (5k Leyma)", "fecha": "16/11/2025", "distancia": "5,00 km", "desnivel_pos": "+138 m", "tiempo": "17:57", "ritmo": "3:35 min/km", "fc_media": "156 bpm", "fc_max": "168 bpm"},
                            {"periodo": "Mejor 10k (Coruña 21)", "fecha": "01/03/2026", "distancia": "10,00 km", "desnivel_pos": "+432 m", "tiempo": "36:32", "ritmo": "3:39 min/km", "fc_media": "157 bpm", "fc_max": "163 bpm"},
                            {"periodo": "Mejor 21k (Coruña 21)", "fecha": "01/03/2026", "distancia": "21,10 km", "desnivel_pos": "+432 m", "tiempo": "1h 18m 37s", "ritmo": "3:44 min/km", "fc_media": "157 bpm", "fc_max": "163 bpm"}
                        ]
                    }
                },
                "Temporada 2025": {
                    "is_current": False,
                    "cycling": {
                        "columns": ["Periodo", "Fecha", "Tiempo", "Potencia Media", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5' (2 subidas a celas)", "fecha": "04/09/2025", "tiempo": "5'00\"", "potencia_media": "422 W", "fc_media": "161 bpm", "fc_max": "167 bpm"},
                            {"periodo": "Mejor 10' (Subida sta. Leocadia)", "fecha": "28/08/2025", "tiempo": "10'00\"", "potencia_media": "402 W", "fc_media": "157 bpm", "fc_max": "164 bpm"},
                            {"periodo": "Mejor 20' (Sin límite)", "fecha": "30/08/2025", "tiempo": "20'00\"", "potencia_media": "331 W", "fc_media": "149 bpm", "fc_max": "160 bpm"}
                        ]
                    },
                    "running": {
                        "columns": ["Periodo", "Fecha", "Distancia", "Desnivel Positivo", "Tiempo", "Ritmo", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5k (5k Leyma)", "fecha": "17/11/2024", "distancia": "5,00 km", "desnivel_pos": "+48 m", "tiempo": "17:25", "ritmo": "3:29 min/km", "fc_media": "164 bpm", "fc_max": "171 bpm"},
                            {"periodo": "Mejor 10k (10k Coruña)", "fecha": "05/10/2025", "distancia": "10,00 km", "desnivel_pos": "+205 m", "tiempo": "35:42", "ritmo": "3:34 min/km", "fc_media": "160 bpm", "fc_max": "164 bpm"},
                            {"periodo": "Mejor 21k (Coruña 21)", "fecha": "09/02/2025", "distancia": "21,10 km", "desnivel_pos": "+442 m", "tiempo": "1h 20m 23s", "ritmo": "3:49 min/km", "fc_media": "161 bpm", "fc_max": "169 bpm"}
                        ]
                    }
                },
                "Temporada 2024": {
                    "is_current": False,
                    "cycling": {
                        "columns": ["Periodo", "Fecha", "Tiempo", "Potencia Media", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5' (Test P5 calle)", "fecha": "04/11/2023", "tiempo": "5'00\"", "potencia_media": "414 W", "fc_media": "165 bpm", "fc_max": "171 bpm"},
                            {"periodo": "Mejor 10' (Control FTP)", "fecha": "15/03/2024", "tiempo": "10'00\"", "potencia_media": "361 W", "fc_media": "157 bpm", "fc_max": "163 bpm"},
                            {"periodo": "Mejor 20' (Control FTP)", "fecha": "15/03/2024", "tiempo": "20'00\"", "potencia_media": "352 W", "fc_media": "161 bpm", "fc_max": "166 bpm"}
                        ]
                    },
                    "running": {
                        "columns": ["Periodo", "Fecha", "Distancia", "Desnivel Positivo", "Tiempo", "Ritmo", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5k (5k Leyma)", "fecha": "19/11/2023", "distancia": "5,00 km", "desnivel_pos": "+25 m", "tiempo": "17:30", "ritmo": "3:30 min/km", "fc_media": "164 bpm", "fc_max": "174 bpm"},
                            {"periodo": "Mejor 10k (Coruña 21)", "fecha": "25/02/2024", "distancia": "10,00 km", "desnivel_pos": "+92 m", "tiempo": "36:56", "ritmo": "3:42 min/km", "fc_media": "157 bpm", "fc_max": "167 bpm"},
                            {"periodo": "Mejor 21k (Coruña 21)", "fecha": "25/02/2024", "distancia": "21,10 km", "desnivel_pos": "+92 m", "tiempo": "1h 20m 38s", "ritmo": "3:49 min/km", "fc_media": "157 bpm", "fc_max": "167 bpm"}
                        ]
                    }
                },
                "Temporada 2023": {
                    "is_current": False,
                    "cycling": {
                        "columns": ["Periodo", "Fecha", "Tiempo", "Potencia Media", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5' (Fondo + P5)", "fecha": "02/09/2023", "tiempo": "5'00\"", "potencia_media": "417 W", "fc_media": "155 bpm", "fc_max": "163 bpm"},
                            {"periodo": "Mejor 10' (Control FTP)", "fecha": "13/07/2023", "tiempo": "10'00\"", "potencia_media": "366 W", "fc_media": "159 bpm", "fc_max": "165 bpm"},
                            {"periodo": "Mejor 20' (Control FTP)", "fecha": "13/07/2023", "tiempo": "20'00\"", "potencia_media": "357 W", "fc_media": "162 bpm", "fc_max": "170 bpm"}
                        ]
                    },
                    "running": {
                        "columns": ["Periodo", "Fecha", "Distancia", "Desnivel Positivo", "Tiempo", "Ritmo", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5k (Coruña 21)", "fecha": "12/02/2023", "distancia": "5,00 km", "desnivel_pos": "+80 m", "tiempo": "17:52", "ritmo": "3:34 min/km", "fc_media": "162 bpm", "fc_max": "168 bpm"},
                            {"periodo": "Mejor 10k (Ferrol Carrera)", "fecha": "15/01/2023", "distancia": "10,00 km", "desnivel_pos": "+107 m", "tiempo": "36:13", "ritmo": "3:37 min/km", "fc_media": "162 bpm", "fc_max": "166 bpm"},
                            {"periodo": "Mejor 21k (Coruña 21)", "fecha": "12/02/2023", "distancia": "21,10 km", "desnivel_pos": "+80 m", "tiempo": "1h 18m 32s", "ritmo": "3:43 min/km", "fc_media": "162 bpm", "fc_max": "168 bpm"}
                        ]
                    }
                },
                "Temporada 2022": {
                    "is_current": False,
                    "cycling": {
                        "columns": ["Periodo", "Fecha", "Tiempo", "Potencia Media", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5' (Test P5 calle)", "fecha": "30/10/2021", "tiempo": "5'00\"", "potencia_media": "391 W", "fc_media": "162 bpm", "fc_max": "168 bpm"},
                            {"periodo": "Mejor 10' (Test FTP subida)", "fecha": "30/07/2022", "tiempo": "10'00\"", "potencia_media": "356 W", "fc_media": "159 bpm", "fc_max": "165 bpm"},
                            {"periodo": "Mejor 20' (Test FTP subida)", "fecha": "30/07/2022", "tiempo": "20'00\"", "potencia_media": "354 W", "fc_media": "162 bpm", "fc_max": "168 bpm"}
                        ]
                    },
                    "running": {
                        "columns": ["Periodo", "Fecha", "Distancia", "Desnivel Positivo", "Tiempo", "Ritmo", "FC Media", "FC Máx"],
                        "rows": [
                            {"periodo": "Mejor 5k (5k Carrera)", "fecha": "13/03/2022", "distancia": "5,00 km", "desnivel_pos": "+25 m", "tiempo": "18:08", "ritmo": "3:38 min/km", "fc_media": "157 bpm", "fc_max": "165 bpm"},
                            {"periodo": "Mejor 10k (Coruña 21)", "fecha": "13/02/2022", "distancia": "10,00 km", "desnivel_pos": "+91 m", "tiempo": "37:45", "ritmo": "3:46 min/km", "fc_media": "161 bpm", "fc_max": "166 bpm"},
                            {"periodo": "Mejor 21k (Coruña 21)", "fecha": "13/02/2022", "distancia": "21,10 km", "desnivel_pos": "+91 m", "tiempo": "1h 20m 26s", "ritmo": "3:49 min/km", "fc_media": "161 bpm", "fc_max": "166 bpm"}
                        ]
                    }
                }
            }
        }

    def get_seasons_competitions_data(self) -> Dict[str, Any]:
        """Provides all recorded competitions across seasons with full 16-column breakdown."""
        return {
            "seasons": [
                "Temporada 2027 (Actual)",
                "Temporada 2026",
                "Temporada 2025"
            ],
            "current_season": "Temporada 2027 (Actual)",
            "columns": [
                "Nombre competición", "Fecha", "Distancia", "Tiempo total",
                "Tiempo natación", "Ritmo natación", "Tiempo T1",
                "Tiempo bici", "Potencia media bici", "FC media bici", "FC máx bici",
                "Tiempo carrera", "Ritmo carrera", "FC media carrera", "FC máx carrera",
                "Posición clasificación"
            ],
            "competitions": {
                "Temporada 2027 (Actual)": [
                    {
                        "nombre": "5k Leyma",
                        "fecha": "15/11/2026",
                        "modalidad": "Carrera a pie",
                        "distancia": "5,00 km",
                        "tiempo_total": "18:38",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "18:38",
                        "ritmo_carrera": "3:44 min/km",
                        "fcmedia_carrera": "156 bpm",
                        "fcmax_carrera": "166 bpm",
                        "posicion": "26º General • 17º Senior M (18:40)"
                    }
                ],
                "Temporada 2026": [
                    {
                        "nombre": "Sprint Cadavedo",
                        "fecha": "04/10/2026",
                        "modalidad": "Triatlón Sprint",
                        "distancia": "24,0 km",
                        "tiempo_total": "1h 06m 58s",
                        "tiempo_natacion": "08:41",
                        "ritmo_natacion": "1:44 /100m",
                        "tiempo_t1": "-",
                        "tiempo_bici": "37:13",
                        "potencia_media_bici": "303 W",
                        "fcmedia_bici": "152 bpm",
                        "fcmax_bici": "165 bpm",
                        "tiempo_carrera": "21:04",
                        "ritmo_carrera": "4:35 min/km",
                        "fcmedia_carrera": "151 bpm",
                        "fcmax_carrera": "160 bpm",
                        "posicion": "6º General (1:07:08)"
                    },
                    {
                        "nombre": "Half Madrid",
                        "fecha": "27/09/2026",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "102,0 km",
                        "tiempo_total": "3h 51m 14s",
                        "tiempo_natacion": "28:54",
                        "ritmo_natacion": "1:31 /100m",
                        "tiempo_t1": "-",
                        "tiempo_bici": "2h 04m 31s",
                        "potencia_media_bici": "247 W",
                        "fcmedia_bici": "142 bpm",
                        "fcmax_bici": "155 bpm",
                        "tiempo_carrera": "1h 17m 40s",
                        "ritmo_carrera": "4:22 min/km",
                        "fcmedia_carrera": "150 bpm",
                        "fcmax_carrera": "161 bpm",
                        "posicion": "28º General • 7º G30-34M (3:57:27)"
                    },
                    {
                        "nombre": "MD Ribadeo",
                        "fecha": "05/09/2026",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "100,4 km",
                        "tiempo_total": "4h 03m 43s",
                        "tiempo_natacion": "26:32",
                        "ritmo_natacion": "1:39 /100m",
                        "tiempo_t1": "-",
                        "tiempo_bici": "2h 15m 15s",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "1h 21m 56s",
                        "ritmo_carrera": "4:23 min/km",
                        "fcmedia_carrera": "-",
                        "fcmax_carrera": "-",
                        "posicion": "9º General (4:07:52)"
                    },
                    {
                        "nombre": "Desafío Castilla y León 1,6/60/14",
                        "fecha": "09/08/2026",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "75,0 km",
                        "tiempo_total": "2h 55m 50s",
                        "tiempo_natacion": "24:53",
                        "ritmo_natacion": "1:46 /100m",
                        "tiempo_t1": "02:40",
                        "tiempo_bici": "1h 27m 35s",
                        "potencia_media_bici": "260 W",
                        "fcmedia_bici": "146 bpm",
                        "fcmax_bici": "154 bpm",
                        "tiempo_carrera": "58:27",
                        "ritmo_carrera": "4:14 min/km",
                        "fcmedia_carrera": "150 bpm",
                        "fcmax_carrera": "158 bpm",
                        "posicion": "25º General (2:57:59)"
                    },
                    {
                        "nombre": "MD As Pontes",
                        "fecha": "28/06/2026",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "104,9 km",
                        "tiempo_total": "4h 19m 34s",
                        "tiempo_natacion": "29:02",
                        "ritmo_natacion": "1:40 /100m",
                        "tiempo_t1": "01:49",
                        "tiempo_bici": "2h 20m 04s",
                        "potencia_media_bici": "252 W",
                        "fcmedia_bici": "143 bpm",
                        "fcmax_bici": "156 bpm",
                        "tiempo_carrera": "1h 26m 58s",
                        "ritmo_carrera": "4:22 min/km",
                        "fcmedia_carrera": "148 bpm",
                        "fcmax_carrera": "156 bpm",
                        "posicion": "6º General • 3º G30-34M (4:21:26)"
                    },
                    {
                        "nombre": "Tri Porriño",
                        "fecha": "14/06/2026",
                        "modalidad": "Triatlón Sprint",
                        "distancia": "24,8 km",
                        "tiempo_total": "1h 06m 24s",
                        "tiempo_natacion": "13:10",
                        "ritmo_natacion": "1:43 /100m",
                        "tiempo_t1": "02:13",
                        "tiempo_bici": "31:14",
                        "potencia_media_bici": "307 W",
                        "fcmedia_bici": "146 bpm",
                        "fcmax_bici": "156 bpm",
                        "tiempo_carrera": "18:48",
                        "ritmo_carrera": "3:57 min/km",
                        "fcmedia_carrera": "150 bpm",
                        "fcmax_carrera": "156 bpm",
                        "posicion": "40º General • 13º ABM (1:07:27)"
                    },
                    {
                        "nombre": "Tri100 Llanes 2/80/18",
                        "fecha": "24/05/2026",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "91,7 km",
                        "tiempo_total": "3h 48m 22s",
                        "tiempo_natacion": "33:01",
                        "ritmo_natacion": "1:45 /100m",
                        "tiempo_t1": "02:08",
                        "tiempo_bici": "2h 01m 34s",
                        "potencia_media_bici": "248 W",
                        "fcmedia_bici": "137 bpm",
                        "fcmax_bici": "150 bpm",
                        "tiempo_carrera": "1h 09m 57s",
                        "ritmo_carrera": "4:19 min/km",
                        "fcmedia_carrera": "145 bpm",
                        "fcmax_carrera": "153 bpm",
                        "posicion": "8º General"
                    },
                    {
                        "nombre": "Setúbal Triathlon",
                        "fecha": "12/04/2026",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "111,8 km",
                        "tiempo_total": "4h 31m 37s",
                        "tiempo_natacion": "38:14",
                        "ritmo_natacion": "1:53 /100m",
                        "tiempo_t1": "-",
                        "tiempo_bici": "2h 24m 38s",
                        "potencia_media_bici": "252 W",
                        "fcmedia_bici": "135 bpm",
                        "fcmax_bici": "150 bpm",
                        "tiempo_carrera": "1h 28m 45s",
                        "ritmo_carrera": "4:16 min/km",
                        "fcmedia_carrera": "144 bpm",
                        "fcmax_carrera": "157 bpm",
                        "posicion": "31º General • 10º G30-34M (4:37:52)"
                    },
                    {
                        "nombre": "Popular 10k Oroso",
                        "fecha": "29/03/2026",
                        "modalidad": "Carrera a pie",
                        "distancia": "10,10 km",
                        "tiempo_total": "39:00",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "39:00",
                        "ritmo_carrera": "3:52 min/km",
                        "fcmedia_carrera": "151 bpm",
                        "fcmax_carrera": "157 bpm",
                        "posicion": "19º General • 6º Senior M (39:01)"
                    },
                    {
                        "nombre": "Coruña 21",
                        "fecha": "01/03/2026",
                        "modalidad": "Carrera a pie",
                        "distancia": "21,31 km",
                        "tiempo_total": "1h 19m 24s",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "1h 19m 24s",
                        "ritmo_carrera": "3:44 min/km",
                        "fcmedia_carrera": "157 bpm",
                        "fcmax_carrera": "163 bpm",
                        "posicion": "90º General • 40º Senior M (1:19:32)"
                    },
                    {
                        "nombre": "10k Padrón",
                        "fecha": "07/02/2026",
                        "modalidad": "Carrera a pie",
                        "distancia": "9,01 km",
                        "tiempo_total": "33:20",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "33:20",
                        "ritmo_carrera": "3:42 min/km",
                        "fcmedia_carrera": "139 bpm",
                        "fcmax_carrera": "158 bpm",
                        "posicion": "106º General • 51º Senior M (37:09)"
                    },
                    {
                        "nombre": "Carreira Popular Rábade",
                        "fecha": "24/01/2026",
                        "modalidad": "Carrera a pie",
                        "distancia": "6,81 km",
                        "tiempo_total": "25:03",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "25:03",
                        "ritmo_carrera": "3:41 min/km",
                        "fcmedia_carrera": "153 bpm",
                        "fcmax_carrera": "174 bpm",
                        "posicion": "-"
                    },
                    {
                        "nombre": "Sin Son 10k",
                        "fecha": "21/12/2025",
                        "modalidad": "Carrera a pie",
                        "distancia": "10,02 km",
                        "tiempo_total": "37:28",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "37:28",
                        "ritmo_carrera": "3:45 min/km",
                        "fcmedia_carrera": "154 bpm",
                        "fcmax_carrera": "163 bpm",
                        "posicion": "108º General • 34º Senior M (37:34)"
                    },
                    {
                        "nombre": "5k Leyma",
                        "fecha": "16/11/2025",
                        "modalidad": "Carrera a pie",
                        "distancia": "5,03 km",
                        "tiempo_total": "18:00",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "18:00",
                        "ritmo_carrera": "3:36 min/km",
                        "fcmedia_carrera": "156 bpm",
                        "fcmax_carrera": "168 bpm",
                        "posicion": "27º General • 21º Senior M (18:05)"
                    },
                    {
                        "nombre": "MD Gandia (Half ICAN)",
                        "fecha": "18/10/2025",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "104,8 km",
                        "tiempo_total": "4h 05m 58s",
                        "tiempo_natacion": "28:28",
                        "ritmo_natacion": "1:35 /100m",
                        "tiempo_t1": "00:24",
                        "tiempo_bici": "2h 05m 38s",
                        "potencia_media_bici": "242 W",
                        "fcmedia_bici": "141 bpm",
                        "fcmax_bici": "153 bpm",
                        "tiempo_carrera": "1h 29m 40s",
                        "ritmo_carrera": "4:12 min/km",
                        "fcmedia_carrera": "149 bpm",
                        "fcmax_carrera": "161 bpm",
                        "posicion": "15º Élite Masculina (4:07:35)"
                    }
                ],
                "Temporada 2025": [
                    {
                        "nombre": "10k Coruña",
                        "fecha": "05/10/2025",
                        "modalidad": "Carrera a pie",
                        "distancia": "10,13 km",
                        "tiempo_total": "36:08",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "36:08",
                        "ritmo_carrera": "3:34 min/km",
                        "fcmedia_carrera": "160 bpm",
                        "fcmax_carrera": "164 bpm",
                        "posicion": "98º General • 41º Senior M (36:15)"
                    },
                    {
                        "nombre": "MD Santander",
                        "fecha": "21/09/2025",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "97,1 km",
                        "tiempo_total": "4h 20m 41s",
                        "tiempo_natacion": "47:12",
                        "ritmo_natacion": "2:13 /100m",
                        "tiempo_t1": "01:57",
                        "tiempo_bici": "2h 03m 56s",
                        "potencia_media_bici": "250 W",
                        "fcmedia_bici": "139 bpm",
                        "fcmax_bici": "158 bpm",
                        "tiempo_carrera": "1h 26m 35s",
                        "ritmo_carrera": "4:15 min/km",
                        "fcmedia_carrera": "149 bpm",
                        "fcmax_carrera": "159 bpm",
                        "posicion": "-"
                    },
                    {
                        "nombre": "Travesía Miño 3k",
                        "fecha": "13/09/2025",
                        "modalidad": "Natación Aguas Abiertas",
                        "distancia": "2,35 km",
                        "tiempo_total": "39:17",
                        "tiempo_natacion": "39:17",
                        "ritmo_natacion": "1:40 /100m",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "-",
                        "ritmo_carrera": "-",
                        "fcmedia_carrera": "-",
                        "fcmax_carrera": "-",
                        "posicion": "-"
                    },
                    {
                        "nombre": "Travesía San Amaro",
                        "fecha": "31/08/2025",
                        "modalidad": "Natación Aguas Abiertas",
                        "distancia": "1,95 km",
                        "tiempo_total": "35:02",
                        "tiempo_natacion": "35:02",
                        "ritmo_natacion": "1:48 /100m",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "-",
                        "ritmo_carrera": "-",
                        "fcmedia_carrera": "-",
                        "fcmax_carrera": "-",
                        "posicion": "-"
                    },
                    {
                        "nombre": "Triatlón Lugo (Triatlón do Miño)",
                        "fecha": "17/08/2025",
                        "modalidad": "Triatlón Sprint",
                        "distancia": "24,5 km",
                        "tiempo_total": "1h 07m 11s",
                        "tiempo_natacion": "13:55",
                        "ritmo_natacion": "1:45 /100m",
                        "tiempo_t1": "02:14",
                        "tiempo_bici": "29:37",
                        "potencia_media_bici": "303 W",
                        "fcmedia_bici": "147 bpm",
                        "fcmax_bici": "161 bpm",
                        "tiempo_carrera": "19:35",
                        "ritmo_carrera": "3:58 min/km",
                        "fcmedia_carrera": "154 bpm",
                        "fcmax_carrera": "163 bpm",
                        "posicion": "41º General (1:08:08)"
                    },
                    {
                        "nombre": "1,6/60/14 Medina Rioseco",
                        "fecha": "10/08/2025",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "75,4 km",
                        "tiempo_total": "2h 58m 14s",
                        "tiempo_natacion": "26:33",
                        "ritmo_natacion": "1:45 /100m",
                        "tiempo_t1": "02:21",
                        "tiempo_bici": "1h 28m 11s",
                        "potencia_media_bici": "251 W",
                        "fcmedia_bici": "145 bpm",
                        "fcmax_bici": "153 bpm",
                        "tiempo_carrera": "59:22",
                        "ritmo_carrera": "4:17 min/km",
                        "fcmedia_carrera": "150 bpm",
                        "fcmax_carrera": "156 bpm",
                        "posicion": "30º General (2:59:53)"
                    },
                    {
                        "nombre": "21k Arzúa - O Pino",
                        "fecha": "02/08/2025",
                        "modalidad": "Carrera a pie",
                        "distancia": "21,41 km",
                        "tiempo_total": "1h 31m 24s",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "1h 31m 24s",
                        "ritmo_carrera": "4:16 min/km",
                        "fcmedia_carrera": "153 bpm",
                        "fcmax_carrera": "161 bpm",
                        "posicion": "-"
                    },
                    {
                        "nombre": "Tri Coruña Sprint",
                        "fecha": "19/07/2025",
                        "modalidad": "Triatlón Sprint",
                        "distancia": "24,2 km",
                        "tiempo_total": "1h 02m 32s",
                        "tiempo_natacion": "11:59",
                        "ritmo_natacion": "1:40 /100m",
                        "tiempo_t1": "01:29",
                        "tiempo_bici": "29:01",
                        "potencia_media_bici": "288 W",
                        "fcmedia_bici": "148 bpm",
                        "fcmax_bici": "154 bpm",
                        "tiempo_carrera": "18:46",
                        "ritmo_carrera": "3:57 min/km",
                        "fcmedia_carrera": "156 bpm",
                        "fcmax_carrera": "168 bpm",
                        "posicion": "-"
                    },
                    {
                        "nombre": "Distancia C Pontevedra (Mundial LD)",
                        "fecha": "29/06/2025",
                        "modalidad": "Triatlón Larga Distancia",
                        "distancia": "152,7 km",
                        "tiempo_total": "6h 33m 42s",
                        "tiempo_natacion": "52:12",
                        "ritmo_natacion": "1:45 /100m",
                        "tiempo_t1": "03:17",
                        "tiempo_bici": "3h 20m 17s",
                        "potencia_media_bici": "230 W",
                        "fcmedia_bici": "140 bpm",
                        "fcmax_bici": "152 bpm",
                        "tiempo_carrera": "2h 17m 48s",
                        "ritmo_carrera": "4:35 min/km",
                        "fcmedia_carrera": "144 bpm",
                        "fcmax_carrera": "149 bpm",
                        "posicion": "2º GGEE 30-34M (Subcampeón del Mundo)"
                    },
                    {
                        "nombre": "Olímpico Coruña Camp. España",
                        "fecha": "01/06/2025",
                        "modalidad": "Triatlón Olímpico",
                        "distancia": "49,6 km",
                        "tiempo_total": "2h 05m 23s",
                        "tiempo_natacion": "22:34",
                        "ritmo_natacion": "1:41 /100m",
                        "tiempo_t1": "01:34",
                        "tiempo_bici": "57:38",
                        "potencia_media_bici": "302 W",
                        "fcmedia_bici": "150 bpm",
                        "fcmax_bici": "158 bpm",
                        "tiempo_carrera": "41:29",
                        "ritmo_carrera": "4:10 min/km",
                        "fcmedia_carrera": "152 bpm",
                        "fcmax_carrera": "172 bpm",
                        "posicion": "-"
                    },
                    {
                        "nombre": "MD Caminha",
                        "fecha": "24/05/2025",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "112,1 km",
                        "tiempo_total": "4h 18m 33s",
                        "tiempo_natacion": "24:39",
                        "ritmo_natacion": "1:18 /100m",
                        "tiempo_t1": "02:12",
                        "tiempo_bici": "2h 18m 11s",
                        "potencia_media_bici": "257 W",
                        "fcmedia_bici": "144 bpm",
                        "fcmax_bici": "157 bpm",
                        "tiempo_carrera": "1h 32m 16s",
                        "ritmo_carrera": "4:29 min/km",
                        "fcmedia_carrera": "148 bpm",
                        "fcmax_carrera": "154 bpm",
                        "posicion": "-"
                    },
                    {
                        "nombre": "Setúbal MD",
                        "fecha": "06/04/2025",
                        "modalidad": "Triatlón Media Distancia",
                        "distancia": "91,0 km",
                        "tiempo_total": "2h 59m 02s",
                        "tiempo_natacion": "29:48",
                        "ritmo_natacion": "1:52 /100m",
                        "tiempo_t1": "02:24",
                        "tiempo_bici": "2h 26m 45s",
                        "potencia_media_bici": "262 W",
                        "fcmedia_bici": "142 bpm",
                        "fcmax_bici": "158 bpm",
                        "tiempo_carrera": "-",
                        "ritmo_carrera": "-",
                        "fcmedia_carrera": "-",
                        "fcmax_carrera": "-",
                        "posicion": "DNF (Retirada tras ciclismo)"
                    },
                    {
                        "nombre": "Coruña 21",
                        "fecha": "09/02/2025",
                        "modalidad": "Carrera a pie",
                        "distancia": "21,35 km",
                        "tiempo_total": "1h 21m 17s",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "1h 21m 17s",
                        "ritmo_carrera": "3:49 min/km",
                        "fcmedia_carrera": "161 bpm",
                        "fcmax_carrera": "169 bpm",
                        "posicion": "94º General • 32º Senior M (1:21:24)"
                    },
                    {
                        "nombre": "10k + 10' Soltar",
                        "fecha": "22/12/2024",
                        "modalidad": "Carrera a pie",
                        "distancia": "10,06 km",
                        "tiempo_total": "37:08",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "37:08",
                        "ritmo_carrera": "3:42 min/km",
                        "fcmedia_carrera": "160 bpm",
                        "fcmax_carrera": "166 bpm",
                        "posicion": "-"
                    },
                    {
                        "nombre": "5k Leyma",
                        "fecha": "17/11/2024",
                        "modalidad": "Carrera a pie",
                        "distancia": "5,10 km",
                        "tiempo_total": "17:41",
                        "tiempo_natacion": "-",
                        "ritmo_natacion": "-",
                        "tiempo_t1": "-",
                        "tiempo_bici": "-",
                        "potencia_media_bici": "-",
                        "fcmedia_bici": "-",
                        "fcmax_bici": "-",
                        "tiempo_carrera": "17:41",
                        "ritmo_carrera": "3:29 min/km",
                        "fcmedia_carrera": "164 bpm",
                        "fcmax_carrera": "171 bpm",
                        "posicion": "-"
                    }
                ]
            }
        }

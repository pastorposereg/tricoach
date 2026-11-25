"""Intervals.icu Integration Service.
Handles authentication via API Key, fetches planned workouts (events),
thresholds, zones, and Performance Management Chart (PMC) wellness data.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
import requests

from .config import AppConfig, load_config, save_config

logger = logging.getLogger(__name__)

INTERVALS_BASE_URL = "https://intervals.icu/api/v1"

DEFAULT_BIKE_POWER_ZONE_PCTS = [55.0, 75.0, 90.0, 105.0, 120.0, 150.0, 999.0]
DEFAULT_PACE_ZONE_PCTS = [77.5, 87.7, 94.3, 100.0, 103.4, 111.5, 999.0]


def _format_pace_secs(sec: Optional[float]) -> Optional[str]:
    if sec is None or sec <= 0:
        return None
    m = int(sec // 60)
    s = int(round(sec % 60))
    if s >= 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"


def _build_pace_zone_table(
    threshold_speed_mps: Optional[float],
    raw_pcts: Optional[List[float]],
    raw_names: Optional[List[str]],
    dist_unit: float,
) -> List[Dict[str, Any]]:
    """Builds Intervals.icu 7-zone pace table dynamically from threshold speed (m/s) and % boundaries."""
    pcts = [float(p) for p in raw_pcts] if raw_pcts else list(DEFAULT_PACE_ZONE_PCTS)
    names = raw_names or [f"Z{i + 1}" for i in range(len(pcts))]
    tp = float(threshold_speed_mps) if (threshold_speed_mps and threshold_speed_mps > 0) else 0.0

    zones: List[Dict[str, Any]] = []
    for idx, pct_max in enumerate(pcts):
        pct_min = 0.0 if idx == 0 else float(pcts[idx - 1])
        name = names[idx] if idx < len(names) else f"Z{idx + 1}"
        min_spd = (tp * (pct_min / 100.0)) if (tp > 0 and pct_min > 0) else 0.0
        max_spd = (tp * (pct_max / 100.0)) if (tp > 0 and pct_max < 900.0) else None

        slow_str = _format_pace_secs(dist_unit / min_spd) if min_spd > 0 else None
        fast_str = _format_pace_secs(dist_unit / max_spd) if (max_spd and max_spd > 0) else None

        if idx == 0 and fast_str:
            range_label = f"> {fast_str}"
        elif fast_str is None and slow_str:
            range_label = f"< {slow_str}"
        elif fast_str and slow_str:
            range_label = f"{fast_str}-{slow_str}"
        else:
            range_label = f"Z{idx + 1}"

        zones.append({
            "zone": idx + 1,
            "id": f"Z{idx + 1}",
            "name": name,
            "percent_min": pct_min,
            "percent_max": pct_max,
            "min_speed_mps": round(min_spd, 4),
            "max_speed_mps": round(max_spd, 4) if max_spd else None,
            "fast_pace": fast_str,
            "slow_pace": slow_str,
            "range_label": range_label,
        })
    return zones


class IntervalsService:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()
        self._last_threshold_sync_ts: float = 0.0

    def _get_auth_header(self) -> Dict[str, str]:
        if not self.config.intervals_api_key:
            return {}
        # Intervals.icu uses HTTP Basic Auth: API_KEY:your_key
        token = base64.b64encode(f"API_KEY:{self.config.intervals_api_key}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
        }

    def _get_athlete_id(self) -> str:
        aid = (self.config.intervals_athlete_id or "").strip()
        if not aid or "@" in aid:
            return "0"
        return aid

    def test_connection(self) -> Dict[str, Any]:
        """Test API Key connection with Intervals.icu and sync thresholds."""
        if not self.config.intervals_api_key:
            return {"status": "not_configured", "message": "No se ha configurado API Key de Intervals.icu"}

        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}"
        try:
            resp = requests.get(url, headers=self._get_auth_header(), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.config.intervals_connected = True
                if "id" in data and not self.config.intervals_athlete_id:
                    self.config.intervals_athlete_id = str(data["id"])
                
                # Automatically extract and synchronize athlete thresholds from Intervals.icu
                thresholds = self.parse_and_apply_thresholds(data, save=True)

                return {
                    "status": "success",
                    "athlete_name": data.get("name", "Atleta Intervals"),
                    "athlete_id": data.get("id"),
                    "ftp": self.config.ftp,
                    "css_pace": self.config.css_pace,
                    "run_threshold_pace": self.config.run_threshold_pace,
                    "max_hr": self.config.max_hr,
                    "resting_hr": self.config.rest_hr_baseline,
                    "lthr": self.config.lthr,
                    "connected": True,
                    "thresholds": thresholds,
                }
            elif resp.status_code == 401:
                return {"status": "error", "message": "API Key inválida o no autorizada (401)"}
            else:
                return {"status": "error", "message": f"Error {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"status": "error", "message": f"Fallo de conexión con Intervals.icu: {str(e)}"}

    def parse_and_apply_thresholds(self, athlete_data: Dict[str, Any], save: bool = True) -> Dict[str, Any]:
        """Parses athlete settings & sportSettings from Intervals.icu,
        updates config athletic baselines, and returns the structured thresholds.
        """
        sport_settings = athlete_data.get("sportSettings", [])
        
        # 1. Baseline parameters from athlete profile
        if athlete_data.get("icu_resting_hr"):
            self.config.rest_hr_baseline = int(athlete_data["icu_resting_hr"])
        if athlete_data.get("icu_weight"):
            self.config.weight = float(athlete_data["icu_weight"])

        disciplines: Dict[str, Any] = {}

        for ss in sport_settings:
            types = [t.lower() for t in ss.get("types", [])]
            is_bike = any(x in types for x in ["ride", "virtualride", "mountainbikeride", "gravelride", "cyclocross"])
            is_run = any(x in types for x in ["run", "virtualrun", "trailrun"])
            is_swim = any(x in types for x in ["swim", "openwaterswim"])

            if is_bike:
                if ss.get("ftp"):
                    self.config.ftp = int(ss["ftp"])
                if ss.get("max_hr"):
                    self.config.max_hr = max(self.config.max_hr, int(ss["max_hr"]))
                if ss.get("lthr"):
                    self.config.lthr = int(ss["lthr"])

                # Build bike power zones in Watts dynamically from Intervals.icu FTP & power_zones %
                raw_pz = [float(p) for p in (ss.get("power_zones") or DEFAULT_BIKE_POWER_ZONE_PCTS)]
                pz_names = ss.get("power_zone_names") or ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
                watt_zones = []
                prev_w = 0
                prev_pct = 0.0
                for idx, pct in enumerate(raw_pz):
                    name = pz_names[idx] if idx < len(pz_names) else f"Z{idx+1}"
                    is_open_top = pct >= 900
                    max_w = int(round(self.config.ftp * (pct / 100.0))) if not is_open_top else 9999
                    if idx == 0:
                        r_lbl = f"<{max_w}W"
                    elif is_open_top:
                        r_lbl = f">{prev_w - 1}W"
                    else:
                        r_lbl = f"{prev_w}-{max_w}W"
                    watt_zones.append({
                        "zone": idx + 1,
                        "id": f"Z{idx + 1}",
                        "name": name,
                        "percent_min": prev_pct,
                        "percent_max": pct,
                        "min_watts": prev_w,
                        "max_watts": max_w,
                        "range_label": r_lbl,
                    })
                    prev_w = max_w + 1
                    prev_pct = pct

                disciplines["cycling"] = {
                    "ftp": self.config.ftp,
                    "lthr": ss.get("lthr", self.config.lthr),
                    "max_hr": ss.get("max_hr", self.config.max_hr),
                    "hr_zones": ss.get("hr_zones", []),
                    "hr_zone_names": ss.get("hr_zone_names", []),
                    "power_zone_pcts": raw_pz,
                    "power_zone_names": pz_names,
                    "power_zones": watt_zones,
                }

            elif is_run:
                tp = ss.get("threshold_pace")
                if tp and tp > 0:
                    sec_km = 1000.0 / tp
                    m = int(sec_km // 60)
                    s = int(round(sec_km % 60))
                    if s >= 60:
                        m += 1
                        s = 0
                    self.config.run_threshold_pace = f"{m}:{s:02d}"

                if ss.get("max_hr"):
                    self.config.max_hr = max(self.config.max_hr, int(ss["max_hr"]))

                run_pz_pcts = [float(p) for p in (ss.get("pace_zones") or DEFAULT_PACE_ZONE_PCTS)]
                run_pz_names = ss.get("pace_zone_names") or [f"Z{i+1}" for i in range(len(run_pz_pcts))]
                run_pace_zones = _build_pace_zone_table(tp, run_pz_pcts, run_pz_names, 1000.0)

                disciplines["running"] = {
                    "threshold_pace": self.config.run_threshold_pace,
                    "threshold_speed_mps": round(float(tp), 4) if tp else None,
                    "lthr": ss.get("lthr", self.config.lthr),
                    "max_hr": ss.get("max_hr", self.config.max_hr),
                    "hr_zones": ss.get("hr_zones", []),
                    "hr_zone_names": ss.get("hr_zone_names", []),
                    "pace_zone_pcts": run_pz_pcts,
                    "pace_zone_names": run_pz_names,
                    "pace_zones": run_pace_zones,
                }

            elif is_swim:
                tp = ss.get("threshold_pace")
                if tp and tp > 0:
                    sec_100m = 100.0 / tp
                    m = int(sec_100m // 60)
                    s = round(sec_100m % 60, 1)
                    if s >= 60.0:
                        m += 1
                        s = 0.0
                    self.config.css_pace = f"{m}:{s:04.1f}" if (s % 1 != 0) else f"{m}:{int(s):02d}.0"

                swim_pz_pcts = [float(p) for p in (ss.get("pace_zones") or DEFAULT_PACE_ZONE_PCTS)]
                swim_pz_names = ss.get("pace_zone_names") or [f"Z{i+1}" for i in range(len(swim_pz_pcts))]
                swim_pace_zones = _build_pace_zone_table(tp, swim_pz_pcts, swim_pz_names, 100.0)

                disciplines["swimming"] = {
                    "css_pace": self.config.css_pace,
                    "threshold_speed_mps": round(float(tp), 4) if tp else None,
                    "lthr": ss.get("lthr", self.config.lthr),
                    "max_hr": ss.get("max_hr", self.config.max_hr),
                    "hr_zones": ss.get("hr_zones", []),
                    "hr_zone_names": ss.get("hr_zone_names", []),
                    "pace_zone_pcts": swim_pz_pcts,
                    "pace_zone_names": swim_pz_names,
                    "pace_zones": swim_pace_zones,
                }

        self.config.thresholds_source = "intervals.icu"
        self.config.thresholds_last_sync = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.config.disciplines_thresholds = disciplines

        if save:
            save_config(self.config)
        self._last_threshold_sync_ts = time.time()

        return {
            "ftp": self.config.ftp,
            "css_pace": self.config.css_pace,
            "run_threshold_pace": self.config.run_threshold_pace,
            "max_hr": self.config.max_hr,
            "rest_hr": self.config.rest_hr_baseline,
            "lthr": self.config.lthr,
            "weight": self.config.weight,
            "disciplines": disciplines,
            "source": "intervals.icu",
            "last_sync": self.config.thresholds_last_sync,
        }

    def ensure_fresh_thresholds(self, max_age_seconds: int = 300) -> Dict[str, Any]:
        """Ensures disciplines_thresholds contains live power/pace zone definitions from Intervals.icu,
        refreshing automatically when stale or missing so threshold changes take effect immediately.
        """
        disc = self.config.disciplines_thresholds or {}
        has_full = (
            isinstance(disc.get("cycling"), dict) and bool(disc["cycling"].get("power_zone_pcts"))
            and isinstance(disc.get("running"), dict) and bool(disc["running"].get("pace_zone_pcts"))
            and isinstance(disc.get("swimming"), dict) and bool(disc["swimming"].get("pace_zone_pcts"))
        )
        now = time.time()
        if not has_full or (now - self._last_threshold_sync_ts) >= max_age_seconds:
            if self.config.intervals_api_key:
                self.sync_athlete_thresholds(save=True)
        return self.config.disciplines_thresholds or {}

    def sync_athlete_thresholds(self, save: bool = True) -> Dict[str, Any]:
        """Fetches live athlete profile and sport settings from Intervals.icu
        and updates app config with the latest thresholds.
        """
        if not self.config.intervals_api_key:
            return self._default_thresholds()

        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}"
        try:
            resp = requests.get(url, headers=self._get_auth_header(), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.config.intervals_connected = True
                return self.parse_and_apply_thresholds(data, save=save)
            else:
                logger.warning(f"Error fetching athlete settings: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.warning(f"Failed to sync thresholds from Intervals: {e}")

        return self._default_thresholds()

    def get_athlete_thresholds(self) -> Dict[str, Any]:
        """Fetch athlete thresholds (FTP, CSS, Pace Thresholds, HR zones)."""
        if self.config.intervals_api_key and self.config.intervals_connected:
            return self.sync_athlete_thresholds(save=True)
        return self._default_thresholds()

    def _format_event_response(self, ev: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes an Intervals.icu calendar event (WORKOUT or NOTE) to app format."""
        category = ev.get("category", "")
        ev_type = ev.get("type") or ""
        sport = self._map_sport_type(ev_type)
        return {
            "id": str(ev.get("id")),
            "date": ev.get("start_date_local", "")[:10],
            "start_time": ev.get("start_date_local", ""),
            "name": ev.get("name", "Entrenamiento planificado"),
            "sport_type": sport,
            "category": category,
            "is_note": category == "NOTE",
            "is_workout": category == "WORKOUT",
            "planned_duration_seconds": ev.get("moving_time") or ev.get("duration") or 0,
            "planned_distance_meters": ev.get("distance") or 0,
            "planned_load": ev.get("icu_training_load") or 0,
            "description": ev.get("description") or "",
            "target_zones": self._extract_target_zones(ev),
            "target_zones_meters": self._extract_swim_target_zones_meters(ev) if sport == "swimming" else None,
            "workout_doc": ev.get("workout_doc"),
        }

    def get_event_detail(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full single planned workout or note details from Intervals.icu."""
        if not self.config.intervals_api_key:
            return None
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/events/{event_id}"
        try:
            resp = requests.get(url, headers=self._get_auth_header(), timeout=8)
            if resp.status_code == 200:
                return self._format_event_response(resp.json())
        except Exception as e:
            logger.warning(f"Error fetching event {event_id}: {e}")
        return None

    def update_event(
        self,
        event_id: str,
        new_date: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Updates date, title, and/or text description of a planned workout or NOTE
        directly in Intervals.icu and returns the freshly parsed event detail.
        """
        if not self.config.intervals_api_key:
            return None
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/events/{event_id}"
        headers = self._get_auth_header()

        # Fetch current event to preserve time suffix and unchanged fields
        cur_ev: Dict[str, Any] = {}
        time_suffix = "T00:00:00"
        try:
            cur_resp = requests.get(url, headers=headers, timeout=8)
            if cur_resp.status_code == 200:
                cur_ev = cur_resp.json()
                cur_start = str(cur_ev.get("start_date_local") or "")
                if len(cur_start) >= 19 and "T" in cur_start:
                    time_suffix = cur_start[10:19]
        except Exception as e:
            logger.warning(f"Could not read existing event {event_id} before update: {e}")

        payload: Dict[str, Any] = {}
        if new_date and len(new_date.strip()) >= 10:
            payload["start_date_local"] = f"{new_date.strip()[:10]}{time_suffix}"
        if name is not None and name.strip():
            payload["name"] = name.strip()
        if description is not None:
            payload["description"] = description

        if not payload:
            return self._format_event_response(cur_ev) if cur_ev else None

        try:
            resp = requests.put(url, headers=headers, json=payload, timeout=12)
            if resp.status_code in (200, 201):
                updated_ev = resp.json()
                return self._format_event_response(updated_ev)
            else:
                logger.error(f"Failed to update event {event_id} in Intervals: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Error updating event {event_id} in Intervals: {e}")
        return None

    def update_event_date(self, event_id: str, new_date: str) -> Optional[Dict[str, Any]]:
        """Updates the scheduled date of an event/workout directly in Intervals.icu."""
        return self.update_event(event_id, new_date=new_date)

    def get_activity_intervals(self, icu_id: str) -> List[Dict[str, Any]]:
        """Fetches Intervals.icu detected intervals (including intra-interval decoupling, zone, max_watts, WORK/RECOVERY)."""
        if not self.config.intervals_api_key or not icu_id:
            return []
        try:
            ri = requests.get(
                f"{INTERVALS_BASE_URL}/activity/{icu_id}/intervals",
                headers=self._get_auth_header(),
                timeout=10,
            )
            if ri.status_code != 200:
                return []
            iv_data = ri.json()
            raw_ivs = iv_data.get("icu_intervals", []) if isinstance(iv_data, dict) else (iv_data if isinstance(iv_data, list) else [])
            parsed: List[Dict[str, Any]] = []
            for idx, iv in enumerate(raw_ivs):
                if not isinstance(iv, dict):
                    continue
                dur = float(iv.get("moving_time") or iv.get("elapsed_time") or 0.0)
                dist = float(iv.get("distance") or 0.0)
                spd = float(iv.get("average_speed") or (dist / dur if dur > 0 else 0.0))
                dec_val = iv.get("decoupling")
                parsed.append({
                    "interval_index": idx + 1,
                    "type": str(iv.get("type") or "WORK").upper(),
                    "label": iv.get("label") or "",
                    "zone": iv.get("zone"),
                    "start_time_sec": round(float(iv.get("start_time") or 0.0), 1) if iv.get("start_time") is not None else None,
                    "end_time_sec": round(float(iv.get("end_time") or 0.0), 1) if iv.get("end_time") is not None else None,
                    "duration_seconds": round(dur, 1),
                    "elapsed_seconds": round(float(iv.get("elapsed_time") or dur), 1),
                    "distance_meters": round(dist, 1),
                    "avg_speed_mps": round(spd, 4) if spd else None,
                    "gap_mps": round(float(iv["gap"]), 4) if iv.get("gap") else None,
                    "avg_power": round(float(iv["average_watts"]), 1) if iv.get("average_watts") is not None else None,
                    "weighted_power": round(float(iv["weighted_average_watts"]), 1) if iv.get("weighted_average_watts") is not None else None,
                    "max_power": round(float(iv["max_watts"]), 1) if iv.get("max_watts") is not None else None,
                    "avg_heart_rate": round(float(iv["average_heartrate"]), 1) if iv.get("average_heartrate") is not None else None,
                    "max_heart_rate": round(float(iv["max_heartrate"]), 1) if iv.get("max_heartrate") is not None else None,
                    "avg_cadence": round(float(iv["average_cadence"]), 1) if iv.get("average_cadence") is not None else None,
                    "decoupling_percent": round(float(dec_val), 2) if dec_val is not None else None,
                    "training_load": round(float(iv["training_load"]), 1) if iv.get("training_load") is not None else None,
                })
            return parsed
        except Exception as e:
            logger.warning(f"Error fetching Intervals.icu intervals for {icu_id}: {e}")
            return []

    def enrich_splits_with_streams(
        self,
        icu_id: str,
        splits: List[Dict[str, Any]],
        sport_type: str,
        icu_intervals: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Aligns every exact Garmin device lap with Intervals.icu second-by-second streams
        (time, watts, heartrate, velocity_smooth) to compute exact 1st-half/2nd-half metrics,
        intra-lap decoupling (Pw:HR / Pa:HR), and peak power WITHOUT merging any laps!
        """
        if not self.config.intervals_api_key or not icu_id or not splits:
            return False
        if sport_type not in ("cycling", "running"):
            return False

        try:
            rs = requests.get(
                f"{INTERVALS_BASE_URL}/activity/{icu_id}/streams.json?types=time,watts,heartrate,velocity_smooth",
                headers=self._get_auth_header(),
                timeout=12,
            )
            if rs.status_code != 200:
                return False
            raw_streams = rs.json()
            if not isinstance(raw_streams, list):
                return False

            smap = {s.get("type"): s.get("data", []) for s in raw_streams if isinstance(s, dict) and s.get("type")}
            t_arr = smap.get("time") or []
            w_arr = smap.get("watts") or []
            hr_arr = smap.get("heartrate") or []
            v_arr = smap.get("velocity_smooth") or []
            if not t_arr:
                return False

            def _avg_idx(arr: List[Any], indices: List[int]) -> Optional[float]:
                vals = [float(arr[i]) for i in indices if i < len(arr) and arr[i] is not None]
                return (sum(vals) / len(vals)) if vals else None

            def _max_idx(arr: List[Any], indices: List[int]) -> Optional[float]:
                vals = [float(arr[i]) for i in indices if i < len(arr) and arr[i] is not None]
                return max(vals) if vals else None

            cum_t = 0.0
            enriched_any = False
            used_icu_iv_idxs = set()
            for sp in splits:
                dur = float(sp.get("duration_seconds") or 0.0)
                elap = float(sp.get("elapsed_seconds") or dur)
                if sp.get("start_offset_seconds") is not None:
                    t0 = float(sp["start_offset_seconds"])
                else:
                    t0 = cum_t
                t1 = t0 + max(elap, dur)
                cum_t = t1
                sp["start_offset_seconds"] = round(t0, 1)
                sp["end_offset_seconds"] = round(t1, 1)

                if dur < 6.0:
                    sp["stream_enriched"] = True
                    continue

                idxs = [i for i, tv in enumerate(t_arr) if tv is not None and t0 <= float(tv) < t1]
                if len(idxs) < 4:
                    sp["stream_enriched"] = True
                    continue

                # Fill peak power from stream if missing or higher
                p_max = _max_idx(w_arr, idxs)
                if p_max is not None and (sp.get("max_power") is None or p_max > float(sp.get("max_power") or 0)):
                    sp["max_power"] = round(p_max, 1)

                # Exact 1st half vs 2nd half inside THIS device lap
                mid = len(idxs) // 2
                h1_idx, h2_idx = idxs[:mid], idxs[mid:]
                hr1 = _avg_idx(hr_arr, h1_idx)
                hr2 = _avg_idx(hr_arr, h2_idx)

                if sport_type == "cycling":
                    o1 = _avg_idx(w_arr, h1_idx)
                    o2 = _avg_idx(w_arr, h2_idx)
                    if o1 is not None and o2 is not None and hr1 and hr2 and o1 > 0 and hr1 > 0:
                        ef1 = o1 / hr1
                        ef2 = o2 / hr2
                        dec = round(((ef1 - ef2) / ef1) * 100.0, 2)
                        sp["intra_decoupling_percent"] = dec
                        sp["half_1"] = {"power_w": round(o1, 1), "hr": round(hr1, 1), "ef": round(ef1, 3)}
                        sp["half_2"] = {"power_w": round(o2, 1), "hr": round(hr2, 1), "ef": round(ef2, 3)}
                else:  # running
                    v1 = _avg_idx(v_arr, h1_idx)
                    v2 = _avg_idx(v_arr, h2_idx)
                    if v1 is not None and v2 is not None and hr1 and hr2 and v1 > 0 and hr1 > 0:
                        ef1 = (v1 * 60.0) / hr1
                        ef2 = (v2 * 60.0) / hr2
                        dec = round(((ef1 - ef2) / ef1) * 100.0, 2)
                        sp["intra_decoupling_percent"] = dec
                        sp["half_1"] = {"speed_mps": round(v1, 3), "hr": round(hr1, 1), "ef": round(ef1, 3)}
                        sp["half_2"] = {"speed_mps": round(v2, 3), "hr": round(hr2, 1), "ef": round(ef2, 3)}

                # Also match exact Intervals.icu interval decoupling if it corresponds 1-to-1 with this exact lap
                if isinstance(icu_intervals, list):
                    for iv_idx, iv in enumerate(icu_intervals):
                        if iv_idx in used_icu_iv_idxs:
                            continue
                        iv_dur = float(iv.get("duration_seconds") or 0)
                        iv_t0 = iv.get("start_time_sec")
                        if iv_dur > 0 and abs(iv_dur - dur) <= max(10.0, dur * 0.08):
                            if iv_t0 is None or abs(float(iv_t0) - t0) <= 20.0:
                                used_icu_iv_idxs.add(iv_idx)
                                if iv.get("decoupling_percent") is not None:
                                    sp["icu_decoupling_percent"] = iv["decoupling_percent"]
                                break

                sp["stream_enriched"] = True
                enriched_any = True
            return enriched_any
        except Exception as e:
            logger.warning(f"Error enriching splits with streams for {icu_id}: {e}")
            return False

    def get_activities_by_range(self, oldest: str, newest: str) -> List[Dict[str, Any]]:
        """Fetches completed activities from Intervals.icu for a date range, including TSS and zone times."""
        if not self.config.intervals_api_key:
            return []
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/activities?oldest={oldest}&newest={newest}"
        try:
            resp = requests.get(url, headers=self._get_auth_header(), timeout=12)
            if resp.status_code == 200:
                raw_acts = resp.json()
                results = []
                for a in raw_acts:
                    if not isinstance(a, dict):
                        continue
                    atype = a.get("type") or ""
                    sport = self._map_sport_type(atype)
                    load = a.get("icu_training_load")
                    results.append({
                        "icu_activity_id": str(a.get("id")),
                        "activity_id": str(a.get("external_id") or a.get("id")),
                        "external_id": str(a.get("external_id")) if a.get("external_id") else None,
                        "name": a.get("name") or "Actividad",
                        "activity_type": atype,
                        "sport_type": sport,
                        "start_time": a.get("start_date_local") or "",
                        "duration_seconds": float(a.get("moving_time") or a.get("elapsed_time") or 0.0),
                        "distance_meters": float(a.get("distance") or 0.0),
                        "avg_heart_rate": a.get("average_heartrate"),
                        "max_heart_rate": a.get("max_heartrate"),
                        "avg_power": a.get("icu_average_watts"),
                        "max_power": a.get("max_watts") or a.get("p_max"),
                        "normalised_power": a.get("icu_weighted_avg_watts"),
                        "avg_speed_mps": a.get("average_speed"),
                        "elevation_gain": a.get("total_elevation_gain"),
                        "calories": a.get("calories"),
                        "training_load": float(load) if load is not None else None,
                        "tss": round(float(load)) if load is not None else None,
                        "pace_zone_times": a.get("pace_zone_times"),
                        "icu_zone_times": a.get("icu_zone_times"),
                        "icu_hr_zone_times": a.get("icu_hr_zone_times"),
                    })
                return results
        except Exception as e:
            logger.warning(f"Error fetching Intervals.icu activities ({oldest}..{newest}): {e}")
        return []

    def get_activity_detail_by_id(self, icu_id: str) -> Optional[Dict[str, Any]]:
        """Fetches single activity details & lap intervals from Intervals.icu (used as fallback or enrichment)."""
        if not self.config.intervals_api_key:
            return None
        headers = self._get_auth_header()
        try:
            r = requests.get(f"{INTERVALS_BASE_URL}/activity/{icu_id}", headers=headers, timeout=10)
            if r.status_code != 200:
                return None
            a = r.json()
            atype = a.get("type") or ""
            sport = self._map_sport_type(atype)
            load = a.get("icu_training_load")

            icu_intervals = self.get_activity_intervals(icu_id)
            splits = []
            for idx, iv in enumerate(icu_intervals):
                splits.append({
                    "lap_index": idx + 1,
                    "distance_meters": iv.get("distance_meters") or 0.0,
                    "duration_seconds": iv.get("duration_seconds") or 0.0,
                    "avg_heart_rate": iv.get("avg_heart_rate"),
                    "max_heart_rate": iv.get("max_heart_rate"),
                    "avg_speed_mps": iv.get("avg_speed_mps"),
                    "avg_power": iv.get("avg_power"),
                    "normalised_power": iv.get("weighted_power"),
                    "max_power": iv.get("max_power"),
                    "avg_cadence": iv.get("avg_cadence"),
                    "elevation_gain_meters": 0.0,
                })

            return {
                "activity_id": str(a.get("external_id") or a.get("id")),
                "icu_activity_id": str(a.get("id")),
                "name": a.get("name") or "Actividad",
                "activity_type": atype,
                "sport_type": sport,
                "start_time": a.get("start_date_local") or "",
                "duration_seconds": float(a.get("moving_time") or a.get("elapsed_time") or 0.0),
                "distance_meters": float(a.get("distance") or 0.0),
                "avg_heart_rate": a.get("average_heartrate"),
                "max_heart_rate": a.get("max_heartrate"),
                "avg_power": a.get("icu_average_watts"),
                "max_power": a.get("max_watts") or a.get("p_max"),
                "normalised_power": a.get("icu_weighted_avg_watts"),
                "avg_speed_mps": a.get("average_speed"),
                "calories": a.get("calories"),
                "elevation_gain_meters": a.get("total_elevation_gain"),
                "training_load": float(load) if load is not None else None,
                "tss": round(float(load)) if load is not None else None,
                "pace_zone_times": a.get("pace_zone_times"),
                "icu_zone_times": a.get("icu_zone_times"),
                "icu_hr_zone_times": a.get("icu_hr_zone_times"),
                "icu_intervals": icu_intervals,
                "splits": splits,
                "hr_zones": [],
            }
        except Exception as e:
            logger.warning(f"Error fetching Intervals activity detail {icu_id}: {e}")
        return None

    def create_calendar_note(self, date_str: str, name: str, description: str = "") -> Optional[Dict[str, Any]]:
        """Creates a calendar NOTE event directly in Intervals.icu."""
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/events"
        payload = {
            "category": "NOTE",
            "start_date_local": f"{date_str}T09:00:00",
            "name": name,
            "description": description or ""
        }
        try:
            resp = requests.post(url, headers=self._get_auth_header(), json=payload, timeout=10)
            if resp.status_code in (200, 201):
                ev = resp.json()
                return {
                    "id": str(ev.get("id")),
                    "date": date_str,
                    "name": ev.get("name", name),
                    "description": ev.get("description", description),
                    "category": "NOTE",
                    "is_note": True,
                }
            else:
                logger.error(f"Failed to create note in Intervals: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Error creating note in Intervals: {e}")
        return None

    def delete_calendar_event(self, event_id: str) -> bool:
        """Deletes an event or note from Intervals.icu calendar."""
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/events/{event_id}"
        try:
            resp = requests.delete(url, headers=self._get_auth_header(), timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Error deleting event {event_id} in Intervals: {e}")
            return False

    def get_planned_events(self, oldest: str, newest: str) -> List[Dict[str, Any]]:
        """Fetch planned workouts / events for a date range."""
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/events?oldest={oldest}&newest={newest}"
        try:
            if not self.config.intervals_api_key:
                return self._generate_fallback_planned_events(oldest, newest)

            resp = requests.get(url, headers=self._get_auth_header(), timeout=10)
            if resp.status_code == 200:
                events = resp.json()
                planned = []
                for ev in events:
                    category = ev.get("category", "")
                    ev_type = ev.get("type") or ""
                    sport = self._map_sport_type(ev_type)

                    planned.append({
                        "id": str(ev.get("id")),
                        "date": ev.get("start_date_local", "")[:10],
                        "start_time": ev.get("start_date_local", ""),
                        "name": ev.get("name", "Entrenamiento planificado"),
                        "sport_type": sport,
                        "is_note": category == "NOTE",
                        "is_workout": category == "WORKOUT",
                        "planned_duration_seconds": ev.get("moving_time") or ev.get("duration") or 0,
                        "planned_distance_meters": ev.get("distance") or 0,
                        "planned_load": ev.get("icu_training_load") or 0,
                        "description": ev.get("description", ""),
                        "target_zones": self._extract_target_zones(ev),
                        "target_zones_meters": self._extract_swim_target_zones_meters(ev) if sport == "swimming" else None,
                        "workout_doc": ev.get("workout_doc"),
                    })
                return planned
        except Exception as e:
            logger.warning(f"Error fetching planned events from Intervals: {e}")

        return self._generate_fallback_planned_events(oldest, newest)

    def get_wellness_pmc(self, oldest: str, newest: str) -> List[Dict[str, Any]]:
        """Fetch PMC daily metrics: CTL, ATL, TSB, HRV, resting HR."""
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/wellness?oldest={oldest}&newest={newest}"
        try:
            if not self.config.intervals_api_key:
                return []

            resp = requests.get(url, headers=self._get_auth_header(), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for day in data:
                    ctl = day.get("ctl", 0)
                    atl = day.get("atl", 0)
                    tsb = round(ctl - atl, 1)
                    results.append({
                        "date": day.get("id"),
                        "ctl": round(ctl, 1),
                        "atl": round(atl, 1),
                        "tsb": tsb,
                        "resting_hr": day.get("restingHR"),
                        "hrv": day.get("hrv"),
                        "sleep_secs": day.get("sleepSecs"),
                        "sleep_score": day.get("sleepScore"),
                        "readiness": day.get("readiness"),
                    })
                return results
        except Exception as e:
            logger.warning(f"Error fetching wellness from Intervals: {e}")
        return []

    def _default_thresholds(self) -> Dict[str, Any]:
        return {
            "ftp": self.config.ftp,
            "css_pace": self.config.css_pace,
            "run_threshold_pace": self.config.run_threshold_pace,
            "resting_hr": self.config.rest_hr_baseline,
            "max_hr": self.config.max_hr,
            "power_zones": [
                {"name": "Z1 Recuperación Activa", "min": 0, "max": int(self.config.ftp * 0.55)},
                {"name": "Z2 Resistencia Aeróbica", "min": int(self.config.ftp * 0.55), "max": int(self.config.ftp * 0.75)},
                {"name": "Z3 Tempo Aeróbico", "min": int(self.config.ftp * 0.76), "max": int(self.config.ftp * 0.90)},
                {"name": "Z4 Umbral Lactato", "min": int(self.config.ftp * 0.91), "max": int(self.config.ftp * 1.05)},
                {"name": "Z5 VO2 Máx", "min": int(self.config.ftp * 1.06), "max": int(self.config.ftp * 1.20)},
            ],
            "hr_zones": [
                {"name": "Z1 Recuperación", "min": 100, "max": 122},
                {"name": "Z2 Aeróbico Base", "min": 123, "max": 141},
                {"name": "Z3 Tempo", "min": 142, "max": 154},
                {"name": "Z4 Umbral", "min": 155, "max": 166},
                {"name": "Z5 Anaeróbico", "min": 167, "max": 182},
            ]
        }

    def _extract_swim_target_zones_meters(self, ev: Dict[str, Any]) -> Dict[str, int]:
        """Extracts planned swimming distance (in meters) per pace zone Z1-Z7 from workout_doc.steps,
        using the athlete's live Intervals.icu CSS threshold speed and pace zone boundaries.
        """
        zones_m: Dict[str, float] = {f"Z{i}": 0.0 for i in range(1, 8)}
        wdoc = ev.get("workout_doc") or {}
        raw_steps = wdoc.get("steps") if isinstance(wdoc, dict) else None

        swim_cfg = (self.config.disciplines_thresholds or {}).get("swimming") or {}
        swim_tp = float(swim_cfg.get("threshold_speed_mps") or 1.1236)
        swim_pcts = [float(p) for p in (swim_cfg.get("pace_zone_pcts") or DEFAULT_PACE_ZONE_PCTS)]

        def classify_step_zone(step: Dict[str, Any]) -> int:
            if step.get("maxeffort"):
                return 7
            pace = step.get("pace")
            if isinstance(pace, dict) and pace.get("units") == "pace_zone" and pace.get("value"):
                return max(1, min(7, int(pace["value"])))
            hr = step.get("hr")
            if isinstance(hr, dict) and hr.get("units") == "hr_zone" and hr.get("value"):
                return max(1, min(7, int(hr["value"])))
            dist = float(step.get("distance") or 0.0)
            dur = float(step.get("duration") or 0.0)
            if dist > 0 and dur > 0 and swim_tp > 0:
                pct = ((dist / dur) / swim_tp) * 100.0
                for idx, p_max in enumerate(swim_pcts[:7]):
                    if pct <= p_max:
                        return idx + 1
                return 7
            return 2

        def walk_steps(steps_list: List[Dict[str, Any]], mult: int = 1):
            for st in steps_list:
                if not isinstance(st, dict):
                    continue
                if st.get("reps") and isinstance(st.get("steps"), list):
                    walk_steps(st["steps"], mult * int(st.get("reps") or 1))
                else:
                    dist = float(st.get("distance") or 0.0)
                    if dist > 0:
                        z_num = classify_step_zone(st)
                        zones_m[f"Z{z_num}"] += dist * mult

        if isinstance(raw_steps, list) and len(raw_steps) > 0:
            walk_steps(raw_steps, 1)

        total_from_steps = sum(zones_m.values())
        planned_dist = float(ev.get("distance") or wdoc.get("distance") or 0.0)
        if total_from_steps <= 0 and planned_dist > 0:
            tz = self._extract_target_zones(ev)
            tot_t = float(sum(tz.values()) or 1.0)
            for z_key, secs in tz.items():
                if z_key in zones_m:
                    zones_m[z_key] = planned_dist * (secs / tot_t)

        return {k: int(round(v)) for k, v in zones_m.items()}

    def _extract_target_zones(self, ev: Dict[str, Any]) -> Dict[str, int]:
        """Extracts exact planned zone durations (in seconds, Z1-Z7) from Intervals.icu
        workout_doc.zoneTimes (canonical) or workout_doc.steps. Never invents fake
        interval zones for strength or blank placeholder workouts.
        """
        zones: Dict[str, int] = {f"Z{i}": 0 for i in range(1, 8)}

        if ev.get("category") == "NOTE":
            return zones

        wdoc = ev.get("workout_doc") or {}
        if isinstance(wdoc, dict):
            # 1. Canonical source: Intervals.icu pre-computed workout_doc.zoneTimes (Z1..Z7, excluding overlapping 'SS')
            zone_times = wdoc.get("zoneTimes")
            if isinstance(zone_times, list):
                zt_total = 0
                for z_item in zone_times:
                    if not isinstance(z_item, dict):
                        continue
                    zid = str(z_item.get("id") or "")
                    secs = int(round(float(z_item.get("secs") or 0)))
                    if zid in zones and secs > 0:
                        zones[zid] += secs
                        zt_total += secs
                if zt_total > 0:
                    return zones

            # 2. Secondary source: walk structured workout_doc.steps if zoneTimes wasn't populated
            raw_steps = wdoc.get("steps")
            if isinstance(raw_steps, list) and len(raw_steps) > 0:
                bike_cfg = (self.config.disciplines_thresholds or {}).get("cycling") or {}
                bike_pcts = [float(p) for p in (bike_cfg.get("power_zone_pcts") or DEFAULT_BIKE_POWER_ZONE_PCTS)]

                def _step_zone(step: Dict[str, Any]) -> Optional[int]:
                    pwr = step.get("power")
                    if isinstance(pwr, dict):
                        units = pwr.get("units") or ""
                        if units == "power_zone" and pwr.get("value"):
                            return max(1, min(7, int(pwr["value"])))
                        if units == "%ftp":
                            start_p = float(pwr.get("start") if pwr.get("start") is not None else (pwr.get("value") or 0))
                            end_p = float(pwr.get("end") if pwr.get("end") is not None else start_p)
                            avg_p = (start_p + end_p) / 2.0
                            if avg_p > 0:
                                for idx, p_max in enumerate(bike_pcts[:7]):
                                    if avg_p <= p_max:
                                        return idx + 1
                                return 7
                    pace = step.get("pace")
                    if isinstance(pace, dict) and pace.get("units") == "pace_zone" and pace.get("value"):
                        return max(1, min(7, int(pace["value"])))
                    hr = step.get("hr")
                    if isinstance(hr, dict) and hr.get("units") == "hr_zone" and hr.get("value"):
                        return max(1, min(7, int(hr["value"])))
                    return None

                def _walk(steps_list: List[Dict[str, Any]], mult: int = 1):
                    for st in steps_list:
                        if not isinstance(st, dict):
                            continue
                        if st.get("reps") and isinstance(st.get("steps"), list):
                            _walk(st["steps"], mult * int(st.get("reps") or 1))
                        else:
                            dur = float(st.get("duration") or 0.0)
                            if dur > 0:
                                zn = _step_zone(st)
                                if zn is not None:
                                    zones[f"Z{zn}"] += int(round(dur * mult))

                _walk(raw_steps, 1)
                if sum(zones.values()) > 0:
                    return zones

        # 3. Unstructured workouts (no workout_doc.zoneTimes and no zoned steps)
        moving_time = int(round(float(ev.get("moving_time") or ev.get("duration") or 0)))
        if moving_time <= 0:
            return zones

        sport = self._map_sport_type(ev.get("type") or "")
        if sport == "strength":
            # Gym/strength workouts are non-cardio (Z1 baseline); never invent Z3/Z4 intervals from words like "series"
            zones["Z1"] = moving_time
            return zones

        desc = (ev.get("description") or "").strip().lower()
        if not desc:
            # Blank placeholder workout with no structure yet -> don't fabricate zone minutes
            return zones

        # Fallback only for unstructured cardio with text description (e.g. offline/fallback mode)
        if "z2" in desc or "aerobic" in desc or "aeróbico" in desc or "rodaje" in desc:
            zones["Z1"] = int(moving_time * 0.15)
            zones["Z2"] = int(moving_time * 0.80)
            zones["Z3"] = int(moving_time * 0.05)
        elif "recuperación" in desc or "suave" in desc:
            zones["Z1"] = int(moving_time * 0.70)
            zones["Z2"] = int(moving_time * 0.30)
        elif "umbral" in desc or "interval" in desc:
            zones["Z1"] = int(moving_time * 0.25)
            zones["Z2"] = int(moving_time * 0.35)
            zones["Z3"] = int(moving_time * 0.15)
            zones["Z4"] = int(moving_time * 0.25)
        else:
            zones["Z1"] = int(moving_time * 0.20)
            zones["Z2"] = int(moving_time * 0.70)
            zones["Z3"] = int(moving_time * 0.10)
        return zones

    def _generate_fallback_planned_events(self, oldest: str, newest: str) -> List[Dict[str, Any]]:
        """Fallback triathlon periodized plan when Intervals.icu is not yet authenticated."""
        try:
            start_d = datetime.strptime(oldest, "%Y-%m-%d").date()
            end_d = datetime.strptime(newest, "%Y-%m-%d").date()
        except Exception:
            return []

        # Weekly template for Triatlón (Base Phase)
        # Mon: Swim threshold + Strength
        # Tue: Run Z2 Aerobic Base
        # Wed: Bike Z2 Aerobic + Swim Aerobic
        # Thu: Run Aerobic with strides + Strength
        # Fri: Swim CSS endurance
        # Sat: Bike Long Ride (Tirada Larga Z2)
        # Sun: Run Long Run (Tirada Aeróbica Control) + Active Recovery Swim
        template = [
            # Monday (0)
            [
                {"name": "Natación: Series Umbral CSS", "sport_type": "swimming", "duration": 3600, "distance": 3000, "load": 65, "desc": "Calentamiento + 5x200m a ritmo CSS con 15'' descanso + Técnica"},
                {"name": "Fuerza: Tren Inferior & Core", "sport_type": "strength", "duration": 3000, "distance": 0, "load": 40, "desc": "Sentadillas, peso muerto rumano, trabajo de estabilidad pélvica"}
            ],
            # Tuesday (1)
            [
                {"name": "Carrera: Rodaje Z2 Aeróbico", "sport_type": "running", "duration": 3600, "distance": 11000, "load": 55, "desc": "Rodaje continuo Z2 (<135 bpm) buscando cadencia estable (175-180 spm)"}
            ],
            # Wednesday (2)
            [
                {"name": "Ciclismo: Rodaje Base Z2", "sport_type": "cycling", "duration": 5400, "distance": 45000, "load": 75, "desc": "90 min en Z2 (190-210W) cadencia 88-92 rpm, entrega de potencia fluida"},
                {"name": "Natación: Aeróbico Continuo", "sport_type": "swimming", "duration": 2700, "distance": 2200, "load": 45, "desc": "Bloques de 400m palas/pull buscando deslizamiento y bajo SWOLF"}
            ],
            # Thursday (3)
            [
                {"name": "Carrera: Base + Progresiones", "sport_type": "running", "duration": 3000, "distance": 9000, "load": 50, "desc": "40 min Z2 + 6x100m progresivos en llano recuperando caminando"},
                {"name": "Fuerza: Tren Superior & Estabilidad", "sport_type": "strength", "duration": 2700, "distance": 0, "load": 35, "desc": "Tracción dorsal, gomas rotadores, planchas dinámicas"}
            ],
            # Friday (4)
            [
                {"name": "Natación: Capacidad Aeróbica", "sport_type": "swimming", "duration": 3300, "distance": 2600, "load": 55, "desc": "8x150m Z2/Z3 manteniendo conteo de brazadas (<14 por largo)"}
            ],
            # Saturday (5)
            [
                {"name": "Ciclismo: Tirada Larga Aeróbica", "sport_type": "cycling", "duration": 10800, "distance": 85000, "load": 140, "desc": "3h en Z2 constante. Control de potencia normalizada y desacople Pw:HR < 4%"}
            ],
            # Sunday (6)
            [
                {"name": "Carrera: Tirada Larga de Control", "sport_type": "running", "duration": 4200, "distance": 14000, "load": 70, "desc": "1h 10m ritmo sostenido en base aeróbica, vigilando deriva cardíaca Pa:HR"}
            ]
        ]

        events = []
        cur = start_d
        while cur <= end_d:
            day_idx = cur.weekday()
            day_template = template[day_idx]
            for i, item in enumerate(day_template):
                dur = item["duration"]
                events.append({
                    "id": f"planned-{cur.strftime('%Y%m%d')}-{i}",
                    "date": cur.strftime("%Y-%m-%d"),
                    "start_time": f"{cur.strftime('%Y-%m-%d')}T08:00:00",
                    "name": item["name"],
                    "sport_type": item["sport_type"],
                    "planned_duration_seconds": dur,
                    "planned_distance_meters": item["distance"],
                    "planned_load": item["load"],
                    "description": item["desc"],
                    "target_zones": {
                        "Z1": int(dur * 0.15),
                        "Z2": int(dur * 0.75),
                        "Z3": int(dur * 0.10),
                        "Z4": 0,
                        "Z5": 0,
                    }
                })
            cur += timedelta(days=1)
        return events

    @staticmethod
    def _map_sport_type(t: str) -> str:
        s = (t or "").lower()
        if "swim" in s:
            return "swimming"
        elif "run" in s:
            return "running"
        elif "ride" in s or "bike" in s or "cycling" in s or "virtual" in s:
            return "cycling"
        elif "weight" in s or "strength" in s or "gym" in s or "yoga" in s or "pilates" in s:
            return "strength"
        return "other"

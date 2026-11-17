"""Intervals.icu Integration Service.
Handles authentication via API Key, fetches planned workouts (events),
thresholds, zones, and Performance Management Chart (PMC) wellness data.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
import requests

from .config import AppConfig, load_config, save_config

logger = logging.getLogger(__name__)

INTERVALS_BASE_URL = "https://intervals.icu/api/v1"


class IntervalsService:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()

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

                # Build bike power zones in Watts if percentage is given
                raw_pz = ss.get("power_zones", [])
                pz_names = ss.get("power_zone_names", ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"])
                watt_zones = []
                prev_w = 0
                for idx, pct in enumerate(raw_pz):
                    name = pz_names[idx] if idx < len(pz_names) else f"Z{idx+1}"
                    max_w = int(round(self.config.ftp * (pct / 100.0))) if pct < 900 else 999
                    watt_zones.append({
                        "zone": idx + 1,
                        "name": name,
                        "percent_max": pct,
                        "min_watts": prev_w,
                        "max_watts": max_w,
                    })
                    prev_w = max_w + 1

                disciplines["cycling"] = {
                    "ftp": self.config.ftp,
                    "lthr": ss.get("lthr", self.config.lthr),
                    "max_hr": ss.get("max_hr", self.config.max_hr),
                    "hr_zones": ss.get("hr_zones", []),
                    "hr_zone_names": ss.get("hr_zone_names", []),
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

                disciplines["running"] = {
                    "threshold_pace": self.config.run_threshold_pace,
                    "threshold_speed_mps": round(tp, 3) if tp else None,
                    "lthr": ss.get("lthr", self.config.lthr),
                    "max_hr": ss.get("max_hr", self.config.max_hr),
                    "hr_zones": ss.get("hr_zones", []),
                    "hr_zone_names": ss.get("hr_zone_names", []),
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

                disciplines["swimming"] = {
                    "css_pace": self.config.css_pace,
                    "threshold_speed_mps": round(tp, 3) if tp else None,
                    "lthr": ss.get("lthr", self.config.lthr),
                    "max_hr": ss.get("max_hr", self.config.max_hr),
                    "hr_zones": ss.get("hr_zones", []),
                    "hr_zone_names": ss.get("hr_zone_names", []),
                }

        self.config.thresholds_source = "intervals.icu"
        self.config.thresholds_last_sync = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.config.disciplines_thresholds = disciplines

        if save:
            save_config(self.config)

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

    def get_event_detail(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full single planned workout details from Intervals.icu."""
        if not self.config.intervals_api_key:
            return None
        athlete_id = self._get_athlete_id()
        url = f"{INTERVALS_BASE_URL}/athlete/{athlete_id}/events/{event_id}"
        try:
            resp = requests.get(url, headers=self._get_auth_header(), timeout=8)
            if resp.status_code == 200:
                ev = resp.json()
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
                    "description": ev.get("description", ""),
                    "target_zones": self._extract_target_zones(ev),
                    "workout_doc": ev.get("workout_doc"),
                }
        except Exception as e:
            logger.warning(f"Error fetching event {event_id}: {e}")
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

    def _extract_target_zones(self, ev: Dict[str, Any]) -> Dict[str, int]:
        """Estimate planned zone distribution based on workout description or targets."""
        moving_time = ev.get("moving_time") or ev.get("duration") or 3600
        if moving_time is None:
            moving_time = 3600
        desc = (ev.get("description") or "").lower()
        # Default distribution for Base Period
        if "z2" in desc or "aerobic" in desc or "rodaje" in desc:
            return {"Z1": int(moving_time * 0.15), "Z2": int(moving_time * 0.80), "Z3": int(moving_time * 0.05), "Z4": 0, "Z5": 0}
        elif "series" in desc or "interval" in desc or "umbral" in desc:
            return {"Z1": int(moving_time * 0.25), "Z2": int(moving_time * 0.35), "Z3": int(moving_time * 0.15), "Z4": int(moving_time * 0.25), "Z5": 0}
        elif "recuperación" in desc or "suave" in desc:
            return {"Z1": int(moving_time * 0.70), "Z2": int(moving_time * 0.30), "Z3": 0, "Z4": 0, "Z5": 0}
        return {"Z1": int(moving_time * 0.20), "Z2": int(moving_time * 0.70), "Z3": int(moving_time * 0.10), "Z4": 0, "Z5": 0}

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
        elif "ride" in s or "bike" in s or "cycling" in s or "virtual" in s:
            return "cycling"
        elif "run" in s:
            return "running"
        elif "weight" in s or "strength" in s or "gym" in s or "yoga" in s or "pilates" in s:
            return "strength"
        return "other"

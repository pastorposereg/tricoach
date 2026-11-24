"""Garmin Connect Integration Service.
Handles authentication via credentials or persistent tokens (garth),
fetches activities, lap splits, time in HR zones, and comprehensive daily wellness.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from garminconnect import Garmin

from .config import AppConfig, load_config, save_config

logger = logging.getLogger(__name__)


class GarminService:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_config()
        self._client: Optional[Garmin] = None

    def get_client(self) -> Garmin:
        if self._client is not None:
            return self._client

        token_dir = Path(self.config.garmin_token_dir)
        client = Garmin(
            email=self.config.garmin_email or "",
            password=self.config.garmin_password or "",
            return_on_mfa=False,
        )

        # 1. Try to login with saved tokens (primary token_dir, or root fallback)
        saved_token_dir = None
        if token_dir.exists() and (token_dir / "garmin_tokens.json").exists():
            saved_token_dir = token_dir
        else:
            root_dir = Path(__file__).resolve().parent.parent
            if (root_dir / "garmin_tokens.json").exists():
                saved_token_dir = root_dir

        if saved_token_dir is not None:
            try:
                client.login(str(saved_token_dir))
                self._client = client
                self.config.garmin_connected = True
                try:
                    self.config.garmin_athlete_name = client.get_full_name()
                except Exception:
                    pass
                save_config(self.config)
                return self._client
            except Exception as e:
                logger.warning(f"Could not login with saved tokens: {e}")

        # 2. Try email / password
        if self.config.garmin_email and self.config.garmin_password:
            try:
                client.login()
                token_dir.mkdir(parents=True, exist_ok=True)
                client.client.dump(str(token_dir))
                self._client = client
                self.config.garmin_connected = True
                try:
                    self.config.garmin_athlete_name = client.get_full_name()
                except Exception:
                    pass
                save_config(self.config)
                return self._client
            except Exception as e:
                logger.error(f"Garmin login failed with email/password: {e}")
                raise ConnectionError(f"Error al iniciar sesión en Garmin: {e}")

        raise ConnectionError(
            "No hay sesión activa de Garmin ni credenciales guardadas. "
            "Introduce tus credenciales en Ajustes."
        )

    def test_connection(self) -> Dict[str, Any]:
        """Test connection and return user profile details."""
        try:
            client = self.get_client()
            name = client.get_full_name()
            return {"status": "success", "athlete_name": name, "connected": True}
        except Exception as e:
            return {"status": "error", "message": str(e), "connected": False}

    def login_with_credentials(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate with fresh email and password, persisting session."""
        self.config.garmin_email = email
        self.config.garmin_password = password
        self._client = None
        token_dir = Path(self.config.garmin_token_dir)
        token_dir.mkdir(parents=True, exist_ok=True)

        client = Garmin(email=email, password=password, return_on_mfa=False)
        try:
            client.login()
            client.client.dump(str(token_dir))
            self._client = client
            self.config.garmin_connected = True
            try:
                self.config.garmin_athlete_name = client.get_full_name()
            except Exception:
                pass
            save_config(self.config)
            return {"status": "success", "athlete_name": self.config.garmin_athlete_name}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch latest activities."""
        client = self.get_client()
        try:
            raw_activities = client.get_activities(0, limit)
            processed = []
            for act in raw_activities:
                processed.append({
                    "activity_id": str(act.get("activityId")),
                    "name": act.get("activityName", "Actividad"),
                    "activity_type": act.get("activityType", {}).get("typeKey", "other"),
                    "sport_type": self._map_sport_type(act.get("activityType", {}).get("typeKey", "")),
                    "start_time": act.get("startTimeLocal", ""),
                    "duration_seconds": act.get("duration", 0.0),
                    "distance_meters": act.get("distance", 0.0),
                    "avg_heart_rate": act.get("averageHR"),
                    "max_heart_rate": act.get("maxHR"),
                    "avg_power": act.get("avgPower"),
                    "max_power": act.get("maxPower"),
                    "normalised_power": act.get("normPower") or act.get("normalizedPower"),
                    "avg_speed_mps": act.get("averageSpeed"),
                    "elevation_gain": act.get("elevationGain"),
                    "calories": act.get("calories"),
                    "training_load": act.get("activityTrainingLoad"),
                    "tss": round(act["activityTrainingLoad"]) if act.get("activityTrainingLoad") is not None else None,
                    "training_effect_aerobic": act.get("aerobicTrainingEffect"),
                    "training_effect_anaerobic": act.get("anaerobicTrainingEffect"),
                })
            return processed
        except Exception as e:
            logger.error(f"Error fetching activities: {e}")
            return []

    def get_activity_details(self, activity_id: str) -> Dict[str, Any]:
        """Fetch detailed activity info including lap splits and time in zones."""
        client = self.get_client()
        try:
            details = client.get_activity(activity_id)
            splits_data = None
            hr_zones_data = None

            try:
                splits_data = client.get_activity_splits(activity_id)
            except Exception:
                pass

            try:
                hr_zones_data = client.get_activity_hr_in_timezones(activity_id)
            except Exception:
                pass

            # Extract summary
            summary = details.get("summaryDTO", {})
            activity_type = (
                details.get("activityTypeDTO", {}).get("typeKey")
                or summary.get("activityType", {}).get("typeKey", "other")
            )
            activity_name = details.get("activityName") or summary.get("activityName", "Actividad")
            sport_type = self._map_sport_type(activity_type)

            # Process splits for decoupling & per-lap telemetry
            splits = []
            if splits_data and "lapDTOs" in splits_data:
                for lap in splits_data["lapDTOs"]:
                    splits.append({
                        "lap_index": lap.get("lapIndex", 1),
                        "distance_meters": lap.get("distance", 0.0),
                        "duration_seconds": lap.get("duration", 0.0),
                        "avg_heart_rate": lap.get("averageHR"),
                        "max_heart_rate": lap.get("maxHR"),
                        "avg_speed_mps": lap.get("averageSpeed"),
                        "avg_power": lap.get("averagePower"),
                        "normalised_power": lap.get("normalizedPower") or lap.get("normPower"),
                        "max_power": lap.get("maxPower"),
                        "avg_cadence": lap.get("averageRunCadence") or lap.get("averageBikeCadence"),
                        "elevation_gain_meters": lap.get("elevationGain", 0.0),
                    })

            # Process HR zones
            hr_zones = []
            if isinstance(hr_zones_data, list):
                for z in hr_zones_data:
                    hr_zones.append({
                        "zone_number": z.get("zoneNumber"),
                        "seconds_in_zone": z.get("secsInZone", 0),
                        "zone_low_boundary": z.get("zoneLowBoundary"),
                    })

            # If swimming, enrich with detailed lengths, intervals and 100m splits
            swim_intervals = []
            swim_lengths = []
            if sport_type == "swimming":
                try:
                    swim_intervals, swim_lengths = self._parse_swim_details(client, str(activity_id))
                    # Match splits with intervals to attach splits_100m
                    if swim_intervals and splits:
                        active_splits = [s for s in splits if (s.get("distance_meters") or 0) > 0]
                        for s_idx, s in enumerate(active_splits):
                            if s_idx < len(swim_intervals):
                                matching_iv = swim_intervals[s_idx]
                                s["splits_100m"] = matching_iv.get("splits_100m", [])
                                s["pace_100m_formatted"] = matching_iv.get("pace_100m_formatted")
                except Exception as swim_err:
                    logger.warning(f"Could not parse swim details for {activity_id}: {swim_err}")

            return {
                "activity_id": str(activity_id),
                "name": activity_name,
                "activity_type": activity_type,
                "sport_type": sport_type,
                "start_time": summary.get("startTimeLocal"),
                "duration_seconds": summary.get("duration", 0.0),
                "distance_meters": summary.get("distance", 0.0),
                "avg_heart_rate": summary.get("averageHR"),
                "max_heart_rate": summary.get("maxHR"),
                "avg_power": summary.get("averagePower"),
                "max_power": summary.get("maxPower"),
                "normalised_power": summary.get("normalizedPower") or summary.get("normPower"),
                "avg_speed_mps": summary.get("averageSpeed"),
                "calories": summary.get("calories"),
                "elevation_gain_meters": summary.get("elevationGain"),
                "elevation_loss_meters": summary.get("elevationLoss"),
                "training_load": summary.get("activityTrainingLoad"),
                "tss": round(summary["activityTrainingLoad"]) if summary.get("activityTrainingLoad") is not None else None,
                "training_effect_aerobic": summary.get("aerobicTrainingEffect"),
                "training_effect_anaerobic": summary.get("anaerobicTrainingEffect"),
                "avg_run_cadence": summary.get("averageRunningCadenceInStepsPerMinute"),
                "avg_bike_cadence": summary.get("averageBikeCadenceInRevPerMinute"),
                "avg_swim_swolf": summary.get("averageSwolf"),
                "avg_swim_strokes": summary.get("averageStrokes"),
                "splits": splits,
                "hr_zones": hr_zones,
                "swim_intervals": swim_intervals,
                "swim_lengths_count": len(swim_lengths),
            }
        except Exception as e:
            logger.error(f"Error getting activity details for {activity_id}: {e}")
            raise

    def get_activities_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Fetches raw activities in a specific date range (YYYY-MM-DD)."""
        client = self.get_client()
        try:
            acts = client.get_activities_by_date(start_date, end_date)
            return acts or []
        except Exception as e:
            logger.warning(f"Error fetching activities between {start_date} and {end_date}: {e}")
            return []

    def _parse_swim_details(self, client: Garmin, activity_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extracts individual lengths and active intervals with 100m splits for pool swimming."""
        try:
            swim_data = client.get_activity_swim_details(activity_id)
            if not swim_data or "activityDetailMetrics" not in swim_data:
                return [], []

            desc_map = {d.get("key"): d.get("metricsIndex") for d in swim_data.get("metricDescriptors", [])}

            lengths = []
            for m in swim_data.get("activityDetailMetrics", []):
                vals = m.get("metrics", [])
                dur = vals[desc_map["sumDuration"]] if "sumDuration" in desc_map and desc_map["sumDuration"] < len(vals) else 0
                dist = vals[desc_map["sumDistance"]] if "sumDistance" in desc_map and desc_map["sumDistance"] < len(vals) else 25
                hr = vals[desc_map["weightedMeanHeartRate"]] if "weightedMeanHeartRate" in desc_map and desc_map["weightedMeanHeartRate"] < len(vals) else None
                strokes = vals[desc_map["sumStrokes"]] if "sumStrokes" in desc_map and desc_map["sumStrokes"] < len(vals) else None
                swolf = vals[desc_map["weightedMeanSwolf"]] if "weightedMeanSwolf" in desc_map and desc_map["weightedMeanSwolf"] < len(vals) else None
                active = vals[desc_map["directActive"]] if "directActive" in desc_map and desc_map["directActive"] < len(vals) else 0
                lengths.append({
                    "duration": dur,
                    "distance": dist,
                    "hr": hr,
                    "strokes": strokes,
                    "swolf": swolf,
                    "active": active == 1.0,
                })

            raw_intervals = []
            curr_iv = []
            for l in lengths:
                if l["active"]:
                    curr_iv.append(l)
                else:
                    if curr_iv:
                        raw_intervals.append(curr_iv)
                        curr_iv = []
            if curr_iv:
                raw_intervals.append(curr_iv)

            parsed_intervals = []
            lengths_per_100 = 4  # standard 25m pool lengths per 100m
            for idx, iv_lengths in enumerate(raw_intervals):
                total_dist = sum(l["distance"] for l in iv_lengths)
                total_dur = sum(l["duration"] for l in iv_lengths)
                valid_hrs = [l["hr"] for l in iv_lengths if l["hr"]]
                avg_hr = round(sum(valid_hrs) / len(valid_hrs)) if valid_hrs else None
                valid_strokes = [l["strokes"] for l in iv_lengths if l["strokes"] is not None]
                avg_strokes = round(sum(valid_strokes) / len(valid_strokes), 1) if valid_strokes else None

                splits_100m = []
                for p in range(0, len(iv_lengths), lengths_per_100):
                    chunk = iv_lengths[p : p + lengths_per_100]
                    chunk_dist = sum(l["distance"] for l in chunk)
                    chunk_dur = sum(l["duration"] for l in chunk)
                    chunk_hrs = [l["hr"] for l in chunk if l["hr"]]
                    chunk_hr = round(sum(chunk_hrs) / len(chunk_hrs)) if chunk_hrs else None
                    chunk_strokes = [l["strokes"] for l in chunk if l["strokes"] is not None]
                    c_strokes = round(sum(chunk_strokes) / len(chunk_strokes), 1) if chunk_strokes else None
                    cm = int(chunk_dur // 60)
                    cs = chunk_dur % 60
                    pace_chunk = (chunk_dur / chunk_dist) * 100 if chunk_dist > 0 else 0
                    pcm = int(pace_chunk // 60)
                    pcs = pace_chunk % 60
                    sp_idx = (p // lengths_per_100) + 1
                    time_fmt = f"{cm}:{cs:05.2f}"
                    pace_fmt = f"{pcm}:{pcs:04.1f}/100m"
                    splits_100m.append({
                        "split_index": sp_idx,
                        "split_num": sp_idx,
                        "distance_meters": chunk_dist,
                        "duration_seconds": round(chunk_dur, 2),
                        "time_formatted": time_fmt,
                        "duration_formatted": time_fmt,
                        "pace_formatted": pace_fmt,
                        "avg_heart_rate": chunk_hr,
                        "avg_strokes_per_length": c_strokes,
                        "lengths_seconds": [round(l["duration"], 2) for l in chunk]
                    })

                im = int(total_dur // 60)
                isec = total_dur % 60
                pace_100 = (total_dur / total_dist) * 100 if total_dist > 0 else 0
                pm = int(pace_100 // 60)
                ps = pace_100 % 60

                parsed_intervals.append({
                    "interval_index": idx + 1,
                    "distance_meters": total_dist,
                    "duration_seconds": round(total_dur, 2),
                    "duration_formatted": f"{im}:{isec:05.2f}",
                    "pace_100m_formatted": f"{pm}:{ps:04.1f}/100m",
                    "avg_heart_rate": avg_hr,
                    "avg_strokes_per_length": avg_strokes,
                    "splits_100m": splits_100m
                })

            return parsed_intervals, lengths
        except Exception as e:
            logger.warning(f"Error parsing swim details for {activity_id}: {e}")
            return [], []

    def get_wellness_data(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """Fetch comprehensive wellness metrics for a given date (defaults to today)."""
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        client = self.get_client()
        wellness: Dict[str, Any] = {
            "date": target_date,
            "resting_hr": None,
            "hrv_status": None,
            "hrv_weekly_avg": None,
            "hrv_last_night_avg": None,
            "sleep_hours": None,
            "sleep_score": None,
            "deep_sleep_minutes": None,
            "rem_sleep_minutes": None,
            "body_battery_charged": None,
            "body_battery_current": None,
            "stress_avg": None,
            "training_readiness_score": None,
            "training_status": None,
            "acute_load": None,
            "chronic_load": None,
            "acwr_ratio": None,
        }

        # 1. Training Status & Load
        try:
            ts = client.get_training_status(target_date)
            if isinstance(ts, dict):
                most_recent = ts.get("mostRecentTrainingStatus", {})
                wellness["training_status"] = most_recent.get("trainingStatusPhrase")
                # training load
                load_balance = ts.get("mostRecentTrainingLoadBalance", {})
                wellness["acute_load"] = load_balance.get("acuteTrainingLoad")
                wellness["chronic_load"] = load_balance.get("chronicTrainingLoad")
        except Exception:
            pass

        # 2. HRV
        try:
            hrv_data = client.get_hrv_data(target_date)
            if isinstance(hrv_data, dict):
                summary = hrv_data.get("hrvSummary", {})
                wellness["hrv_status"] = summary.get("status")
                wellness["hrv_weekly_avg"] = summary.get("weeklyAvg")
                wellness["hrv_last_night_avg"] = summary.get("lastNightAvg")
        except Exception:
            pass

        # 3. Resting HR
        try:
            rhr_data = client.get_rhr_day(target_date)
            if isinstance(rhr_data, dict):
                metrics = rhr_data.get("allMetrics", {})
                metrics_list = metrics.get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE", [])
                if metrics_list:
                    wellness["resting_hr"] = metrics_list[-1].get("value")
        except Exception:
            pass

        # 4. Sleep
        try:
            sleep_data = client.get_sleep_data(target_date)
            if isinstance(sleep_data, dict):
                daily_sleep = sleep_data.get("dailySleepDTO", {})
                sleep_secs = daily_sleep.get("sleepTimeSeconds", 0)
                if sleep_secs:
                    wellness["sleep_hours"] = round(sleep_secs / 3600, 2)
                wellness["sleep_score"] = daily_sleep.get("sleepScores", {}).get("overall", {}).get("value")
                wellness["deep_sleep_minutes"] = round(daily_sleep.get("deepSleepSeconds", 0) / 60)
                wellness["rem_sleep_minutes"] = round(daily_sleep.get("remSleepSeconds", 0) / 60)
        except Exception:
            pass

        # 5. Training Readiness
        try:
            readiness_data = client.get_training_readiness(target_date)
            if isinstance(readiness_data, list) and readiness_data:
                wellness["training_readiness_score"] = readiness_data[-1].get("score")
            elif isinstance(readiness_data, dict):
                wellness["training_readiness_score"] = readiness_data.get("score")
        except Exception:
            pass

        # 6. Stress & Body Battery
        try:
            bb = client.get_body_battery(target_date)
            if isinstance(bb, list) and bb:
                wellness["body_battery_charged"] = bb[0].get("charged")
                wellness["body_battery_current"] = bb[-1].get("bodyBatteryLevel")
        except Exception:
            pass

        return wellness

    @staticmethod
    def _map_sport_type(activity_type: str) -> str:
        act = (activity_type or "").lower()
        if "swim" in act or "lap_swimming" in act or "open_water" in act:
            return "swimming"
        elif "ride" in act or "cycling" in act or "biking" in act:
            return "cycling"
        elif "run" in act or "running" in act or "treadmill" in act:
            return "running"
        elif "strength" in act or "weight" in act or "fitness" in act or "cross" in act:
            return "strength"
        return "other"

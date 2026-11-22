"""Biomechanical, Aerobic Efficiency, Cardiovascular Decoupling,
and Performance Management (PMC) calculation engine.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def calculate_bike_efficiency(
    norm_power: Optional[float],
    avg_power: Optional[float],
    avg_hr: Optional[float]
) -> Dict[str, Any]:
    """Calculate Bike Aerobic Efficiency (FEc) and Variability Index (IV)."""
    p = norm_power or avg_power
    if not p or not avg_hr or avg_hr <= 0:
        return {"fec": None, "iv": None}

    fec = round(p / avg_hr, 2)
    iv = round(norm_power / avg_power, 3) if norm_power and avg_power and avg_power > 0 else 1.0
    return {"fec": fec, "iv": iv}


def calculate_run_efficiency(
    avg_speed_mps: Optional[float],
    avg_hr: Optional[float]
) -> Dict[str, Any]:
    """Calculate Running Aerobic Efficiency (FEcp = Speed in m/min / HR).
    E.g.: 4:39 min/km -> 3.584 m/s = 215 m/min. At 133 bpm -> FEcp = 1.616.
    """
    if not avg_speed_mps or not avg_hr or avg_hr <= 0:
        return {"fecp": None, "pace_str": None}

    # Speed in meters per minute
    speed_mpm = avg_speed_mps * 60.0
    fecp = round(speed_mpm / avg_hr, 2)

    # Pace string (min:sec / km)
    pace_sec = 1000.0 / avg_speed_mps if avg_speed_mps > 0 else 0
    mins = int(pace_sec // 60)
    secs = int(pace_sec % 60)
    pace_str = f"{mins}:{secs:02d} min/km"

    return {"fecp": fecp, "pace_str": pace_str}


def calculate_decoupling_from_splits(
    splits: List[Dict[str, Any]],
    sport_type: str
) -> Dict[str, Any]:
    """Calculates Cardiovascular Decoupling (Pw:HR for cycling or Pa:HR for running)
    by splitting the workout into two equal halves (Half 1 vs Half 2).
    """
    if not splits or len(splits) < 2:
        return {
            "has_decoupling": False,
            "decoupling_percent": None,
            "half_1": None,
            "half_2": None,
            "diagnosis": "Entrenamiento sin suficientes splits para calcular desacople"
        }

    total_splits = len(splits)
    midpoint = total_splits // 2

    splits_h1 = splits[:midpoint]
    splits_h2 = splits[midpoint:]

    def get_half_metrics(sub_splits: List[Dict[str, Any]]) -> Tuple[float, float, float, float]:
        dur = sum(s.get("duration_seconds", 0) for s in sub_splits)
        dist = sum(s.get("distance_meters", 0) for s in sub_splits)
        if dur <= 0:
            return 0.0, 0.0, 0.0, 0.0

        # Weighted HR
        total_hr_dur = sum(s.get("avg_heart_rate", 0) * s.get("duration_seconds", 0) for s in sub_splits if s.get("avg_heart_rate"))
        avg_hr = total_hr_dur / dur if dur > 0 else 0

        # Weighted Power
        total_p_dur = sum((s.get("avg_power") or 0) * s.get("duration_seconds", 0) for s in sub_splits)
        avg_p = total_p_dur / dur if dur > 0 else 0

        # Speed
        avg_speed = dist / dur if dur > 0 else 0
        return dur, dist, avg_hr, avg_p if sport_type == "cycling" else avg_speed

    dur1, dist1, hr1, val1 = get_half_metrics(splits_h1)
    dur2, dist2, hr2, val2 = get_half_metrics(splits_h2)

    if hr1 <= 0 or hr2 <= 0 or val1 <= 0 or val2 <= 0:
        return {
            "has_decoupling": False,
            "decoupling_percent": None,
            "half_1": None,
            "half_2": None,
            "diagnosis": "Datos insuficientes de FC o potencia/velocidad en los splits"
        }

    # Efficiency factors
    if sport_type == "cycling":
        ef1 = val1 / hr1  # Power / HR
        ef2 = val2 / hr2
        metric_name = "Pw:HR"
        h1_label = f"{round(val1, 1)}W, {round(hr1, 1)} bpm (EF {round(ef1, 2)})"
        h2_label = f"{round(val2, 1)}W, {round(hr2, 1)} bpm (EF {round(ef2, 2)})"
    else:
        # Running: speed (m/min) / HR
        speed_mpm1 = val1 * 60.0
        speed_mpm2 = val2 * 60.0
        ef1 = speed_mpm1 / hr1
        ef2 = speed_mpm2 / hr2
        metric_name = "Pa:HR"
        pace1_s = 1000 / val1 if val1 > 0 else 0
        pace2_s = 1000 / val2 if val2 > 0 else 0
        h1_label = f"{int(pace1_s//60)}:{int(pace1_s%60):02d}/km, {round(hr1, 1)} bpm (EF {round(ef1, 2)})"
        h2_label = f"{int(pace2_s//60)}:{int(pace2_s%60):02d}/km, {round(hr2, 1)} bpm (EF {round(ef2, 2)})"

    # Decoupling = ((EF1 - EF2) / EF1) * 100
    decoupling = round(((ef1 - ef2) / ef1) * 100.0, 2)

    # Expert diagnosis
    if decoupling < 3.0:
        diagnosis = f"Excelente estabilidad aeróbica ({metric_name} = {decoupling}%). Deriva cardíaca despreciable (<3%), densidad mitocondrial óptima para la base."
        status_color = "emerald"
    elif decoupling <= 5.0:
        diagnosis = f"Desacople controlado ({metric_name} = {decoupling}%). Dentro del margen aceptable (<5%) para la tirada de volumen aeróbico."
        status_color = "blue"
    else:
        diagnosis = f"Deriva cardíaca acusada ({metric_name} = {decoupling}%). Supera el 5%, indicando fatiga neuromuscular, deshidratación o déficit glucogénico."
        status_color = "amber"

    return {
        "has_decoupling": True,
        "metric_name": metric_name,
        "decoupling_percent": decoupling,
        "status_color": status_color,
        "diagnosis": diagnosis,
        "half_1": {"output": round(val1, 1), "hr": round(hr1, 1), "ef": round(ef1, 2), "label": h1_label},
        "half_2": {"output": round(val2, 1), "hr": round(hr2, 1), "ef": round(ef2, 2), "label": h2_label},
    }


def calculate_swim_metrics(
    duration_seconds: float,
    distance_meters: float,
    swolf: Optional[float] = None,
    strokes: Optional[float] = None,
    pool_length: float = 25.0
) -> Dict[str, Any]:
    """Calculate swim pacing, SWOLF, Distance Per Stroke (DPS)."""
    if distance_meters <= 0 or duration_seconds <= 0:
        return {}

    # Pace per 100m
    pace_100_sec = (duration_seconds / distance_meters) * 100.0
    mins = int(pace_100_sec // 60)
    secs = int(pace_100_sec % 60)
    tenths = int((pace_100_sec - int(pace_100_sec)) * 10)
    pace_str = f"{mins}:{secs:02d}.{tenths}/100m"

    # Distance per stroke
    dps = None
    if strokes and strokes > 0:
        dps = round(pool_length / strokes, 2)

    return {
        "pace_per_100m_sec": round(pace_100_sec, 1),
        "pace_str": pace_str,
        "swolf": round(swolf, 1) if swolf else None,
        "strokes_per_length": round(strokes, 1) if strokes else None,
        "dps_meters": dps,
    }


def aggregate_weekly_zones(
    planned_events: List[Dict[str, Any]],
    completed_activities: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Calculates weekly zone breakdown (Planned vs Completed) grouped by discipline:
    - Natación: zones by DISTANCE in meters (Z1-Z7)
    - Ciclismo, Carrera, Fuerza: zones by TIME in minutes (Z1-Z5)
    """
    sports = ["swimming", "cycling", "running", "strength"]
    summary: Dict[str, Any] = {}

    # Representative swim speeds (m/s) per zone (Z1..Z7) for pace_zone_times -> meters conversion
    swim_zone_speeds = [0.833, 0.926, 1.020, 1.099, 1.149, 1.220, 1.333]

    for sport in sports:
        z_keys = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"] if sport == "swimming" else ["Z1", "Z2", "Z3", "Z4", "Z5"]
        summary[sport] = {
            "planned_time_seconds": 0,
            "completed_time_seconds": 0,
            "planned_distance_meters": 0,
            "completed_distance_meters": 0,
            "planned_sessions": 0,
            "completed_sessions": 0,
            "planned_load": 0,
            "completed_load": 0,
            "zone_unit": "meters" if sport == "swimming" else "minutes",
            "zones": {
                z: {"planned": 0, "completed": 0} for z in z_keys
            }
        }

    # 1. Sum planned events
    for ev in planned_events:
        if ev.get("is_note"):
            continue
        st = ev.get("sport_type", "other")
        if st not in summary:
            continue
        dur = ev.get("planned_duration_seconds", 0)
        dist = ev.get("planned_distance_meters", 0) or 0
        summary[st]["planned_time_seconds"] += (dur or 0)
        summary[st]["planned_distance_meters"] += dist
        summary[st]["planned_sessions"] += 1
        summary[st]["planned_load"] += int(ev.get("planned_load") or 0)

        if st == "swimming":
            tz_m = ev.get("target_zones_meters")
            if isinstance(tz_m, dict) and sum(tz_m.values()) > 0:
                for z in ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]:
                    summary[st]["zones"][z]["planned"] += int(tz_m.get(z, 0) or 0)
            elif dist > 0:
                tz = ev.get("target_zones", {})
                tot_t = float(sum(tz.values()) or 1.0)
                for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
                    summary[st]["zones"][z]["planned"] += int(round(dist * ((tz.get(z, 0) or 0) / tot_t)))
        else:
            tz = ev.get("target_zones", {})
            for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
                summary[st]["zones"][z]["planned"] += int(tz.get(z, 0) or 0)

    # 2. Sum completed activities
    for act in completed_activities:
        st = act.get("sport_type", "other")
        if st not in summary:
            continue
        dur = float(act.get("duration_seconds") or 0)
        dist = float(act.get("distance_meters") or 0)
        summary[st]["completed_time_seconds"] += dur
        summary[st]["completed_distance_meters"] += dist
        summary[st]["completed_sessions"] += 1

        # Completed load: prefer exact TSS / training_load from Intervals.icu or Garmin
        load = act.get("tss") if act.get("tss") is not None else act.get("training_load")
        if load is None:
            load = (act.get("training_effect_aerobic") or 2.0) * 25
        summary[st]["completed_load"] += int(round(float(load)))

        if st == "swimming":
            # Swimming zones MUST be aggregated by DISTANCE (meters)
            splits = act.get("splits") or []
            active_splits = [s for s in splits if (s.get("distance_meters") or 0) > 0 and (s.get("duration_seconds") or 0) > 0]
            pace_z = act.get("pace_zone_times")

            if active_splits:
                for s in active_splits:
                    s_dist = float(s.get("distance_meters") or 0)
                    s_dur = float(s.get("duration_seconds") or 0)
                    sec100 = (s_dur / s_dist) * 100.0
                    z_num = 1 if sec100 > 114 else (2 if sec100 >= 102 else (3 if sec100 >= 94 else (4 if sec100 >= 89 else (5 if sec100 >= 86 else (6 if sec100 >= 80 else 7)))))
                    summary[st]["zones"][f"Z{z_num}"]["completed"] += int(round(s_dist))
            elif isinstance(pace_z, list) and len(pace_z) >= 7 and sum((x or 0) for x in pace_z[:7]) > 0 and dist > 0:
                weighted = [(float(pace_z[i] or 0) * swim_zone_speeds[i]) for i in range(7)]
                tot_w = sum(weighted) or 1.0
                for i in range(7):
                    summary[st]["zones"][f"Z{i+1}"]["completed"] += int(round(dist * (weighted[i] / tot_w)))
            elif dist > 0:
                hr_zones = act.get("hr_zones", [])
                tot_hr_s = sum(int(z.get("seconds_in_zone", 0) or 0) for z in hr_zones)
                if hr_zones and tot_hr_s > 0:
                    for z in hr_zones:
                        zn = z.get("zone_number")
                        z_key = f"Z{zn}"
                        if z_key in summary[st]["zones"]:
                            summary[st]["zones"][z_key]["completed"] += int(round(dist * (int(z.get("seconds_in_zone", 0) or 0) / tot_hr_s)))
                else:
                    # Classify whole session by average pace if available
                    if dur > 0:
                        sec100 = (dur / dist) * 100.0
                        z_num = 1 if sec100 > 114 else (2 if sec100 >= 102 else (3 if sec100 >= 94 else (4 if sec100 >= 89 else (5 if sec100 >= 86 else (6 if sec100 >= 80 else 7)))))
                        summary[st]["zones"][f"Z{z_num}"]["completed"] += int(round(dist))
                    else:
                        summary[st]["zones"]["Z2"]["completed"] += int(round(dist))
        else:
            # Cycling, Running, Strength: TIME in zones (seconds -> minutes)
            hr_zones = act.get("hr_zones", [])
            icu_pz = act.get("icu_zone_times")
            pace_z = act.get("pace_zone_times")
            icu_hr_z = act.get("icu_hr_zone_times")

            if st == "cycling" and isinstance(icu_pz, list) and len(icu_pz) > 0:
                added = False
                for z_obj in icu_pz:
                    zid = str(z_obj.get("id") or "")
                    secs = int(z_obj.get("secs") or 0)
                    if secs <= 0:
                        continue
                    if zid in summary[st]["zones"]:
                        summary[st]["zones"][zid]["completed"] += secs
                        added = True
                    elif zid in ("Z6", "Z7"):
                        summary[st]["zones"]["Z5"]["completed"] += secs
                        added = True
                if not added:
                    summary[st]["zones"]["Z2"]["completed"] += int(dur)
            elif st == "running" and isinstance(pace_z, list) and sum((x or 0) for x in pace_z[:7]) > 0:
                for i in range(min(len(pace_z), 7)):
                    secs = int(pace_z[i] or 0)
                    if secs <= 0:
                        continue
                    z_key = f"Z{min(i + 1, 5)}"
                    summary[st]["zones"][z_key]["completed"] += secs
            elif hr_zones:
                for z in hr_zones:
                    zn = z.get("zone_number")
                    z_key = f"Z{min(int(zn), 5)}" if zn else None
                    if z_key and z_key in summary[st]["zones"]:
                        summary[st]["zones"][z_key]["completed"] += int(z.get("seconds_in_zone", 0) or 0)
            elif isinstance(icu_hr_z, list) and sum((x or 0) for x in icu_hr_z) > 0:
                for i, secs in enumerate(icu_hr_z):
                    if secs and secs > 0:
                        z_key = f"Z{min(i + 1, 5)}"
                        summary[st]["zones"][z_key]["completed"] += int(secs)
            else:
                summary[st]["zones"]["Z1"]["completed"] += int(dur * 0.15)
                summary[st]["zones"]["Z2"]["completed"] += int(dur * 0.75)
                summary[st]["zones"]["Z3"]["completed"] += int(dur * 0.10)

    # Format into human-readable hours, distances, and progress percentage
    for sport, data in summary.items():
        p_hrs = round(data["planned_time_seconds"] / 3600, 2)
        c_hrs = round(data["completed_time_seconds"] / 3600, 2)
        p_dist_m = data["planned_distance_meters"]
        c_dist_m = data["completed_distance_meters"]

        if sport == "swimming" and p_dist_m > 0:
            pct = round((c_dist_m / p_dist_m * 100), 1)
        else:
            pct = round((c_hrs / p_hrs * 100), 1) if p_hrs > 0 else (100.0 if c_hrs > 0 else 0.0)

        data["planned_hours"] = p_hrs
        data["completed_hours"] = c_hrs
        data["compliance_percent"] = pct

        if sport == "swimming":
            data["planned_km"] = round(p_dist_m / 1000, 2)
            data["completed_km"] = round(c_dist_m / 1000, 2)
            data["planned_distance_formatted"] = f"{int(p_dist_m):,} m".replace(",", ".") if p_dist_m > 0 else "0 m"
            data["completed_distance_formatted"] = f"{int(c_dist_m):,} m".replace(",", ".") if c_dist_m > 0 else "0 m"
            data["distance_unit"] = "m"
            for z in ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]:
                data["zones"][z]["planned_meters"] = int(round(data["zones"][z]["planned"]))
                data["zones"][z]["completed_meters"] = int(round(data["zones"][z]["completed"]))
                data["zones"][z]["planned_mins"] = 0
                data["zones"][z]["completed_mins"] = 0
        elif sport == "strength":
            data["planned_km"] = 0.0
            data["completed_km"] = 0.0
            data["planned_distance_formatted"] = "Fuerza"
            data["completed_distance_formatted"] = "Fuerza"
            data["distance_unit"] = ""
            for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
                data["zones"][z]["planned_mins"] = round(data["zones"][z]["planned"] / 60)
                data["zones"][z]["completed_mins"] = round(data["zones"][z]["completed"] / 60)
        else:  # cycling, running
            p_km = round(p_dist_m / 1000, 1)
            c_km = round(c_dist_m / 1000, 1)
            data["planned_km"] = p_km
            data["completed_km"] = c_km
            data["planned_distance_formatted"] = f"{p_km} km"
            data["completed_distance_formatted"] = f"{c_km} km"
            data["distance_unit"] = "km"
            for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
                data["zones"][z]["planned_mins"] = round(data["zones"][z]["planned"] / 60)
                data["zones"][z]["completed_mins"] = round(data["zones"][z]["completed"] / 60)

    return summary


def compute_pmc_series(
    daily_loads: List[Dict[str, Any]],
    initial_ctl: float = 600.0,
    initial_atl: float = 800.0
) -> List[Dict[str, Any]]:
    """Computes CTL, ATL, TSB using Exponential Weighted Moving Averages (EWMA):
    CTL_t = CTL_{t-1} + (TSS_t - CTL_{t-1}) * (1 - e^(-1/42))
    ATL_t = ATL_{t-1} + (TSS_t - ATL_{t-1}) * (1 - e^(-1/7))
    TSB_t = CTL_t - ATL_t
    """
    ctl_decay = 1.0 - math.exp(-1.0 / 42.0)
    atl_decay = 1.0 - math.exp(-1.0 / 7.0)

    ctl = initial_ctl
    atl = initial_atl

    series = []
    for item in daily_loads:
        date_str = item.get("date")
        tss = item.get("tss", 0.0)

        ctl = ctl + (tss - ctl) * ctl_decay
        atl = atl + (tss - atl) * atl_decay
        tsb = ctl - atl

        series.append({
            "date": date_str,
            "tss": round(tss, 1),
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(tsb, 1),
        })

    return series

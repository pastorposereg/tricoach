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
    """Calculates weekly time in zones (Planned vs Completed) grouped by discipline:
    Natación, Ciclismo, Carrera, Fuerza.
    """
    sports = ["swimming", "cycling", "running", "strength"]
    summary: Dict[str, Any] = {}

    for sport in sports:
        summary[sport] = {
            "planned_time_seconds": 0,
            "completed_time_seconds": 0,
            "planned_distance_meters": 0,
            "completed_distance_meters": 0,
            "planned_sessions": 0,
            "completed_sessions": 0,
            "planned_load": 0,
            "completed_load": 0,
            "zones": {
                "Z1": {"planned": 0, "completed": 0},
                "Z2": {"planned": 0, "completed": 0},
                "Z3": {"planned": 0, "completed": 0},
                "Z4": {"planned": 0, "completed": 0},
                "Z5": {"planned": 0, "completed": 0},
            }
        }

    # 1. Sum planned events
    for ev in planned_events:
        st = ev.get("sport_type", "other")
        if st not in summary:
            continue
        dur = ev.get("planned_duration_seconds", 0)
        summary[st]["planned_time_seconds"] += (dur or 0)
        summary[st]["planned_distance_meters"] += (ev.get("planned_distance_meters") or 0)
        summary[st]["planned_sessions"] += 1
        summary[st]["planned_load"] += (ev.get("planned_load") or 0)

        # Distribute planned zones
        tz = ev.get("target_zones", {})
        for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
            summary[st]["zones"][z]["planned"] += tz.get(z, 0)

    # 2. Sum completed activities
    for act in completed_activities:
        st = act.get("sport_type", "other")
        if st not in summary:
            continue
        dur = act.get("duration_seconds") or 0
        dist = act.get("distance_meters") or 0
        summary[st]["completed_time_seconds"] += dur
        summary[st]["completed_distance_meters"] += dist
        summary[st]["completed_sessions"] += 1

        # Completed load estimation if not given
        # 1 hour of Z2 ~ 50-60 TSS
        load = act.get("training_load") or (act.get("training_effect_aerobic") or 2.0) * 25
        summary[st]["completed_load"] += int(load)

        # HR zones breakdown if available
        hr_zones = act.get("hr_zones", [])
        if hr_zones:
            for z in hr_zones:
                zn = z.get("zone_number")
                z_key = f"Z{zn}"
                if z_key in summary[st]["zones"]:
                    summary[st]["zones"][z_key]["completed"] += int(z.get("seconds_in_zone", 0))
        else:
            # Default aerobic split if granular zones missing
            summary[st]["zones"]["Z1"]["completed"] += int(dur * 0.15)
            summary[st]["zones"]["Z2"]["completed"] += int(dur * 0.75)
            summary[st]["zones"]["Z3"]["completed"] += int(dur * 0.10)

    # Format into human-readable hours, distances, and progress percentage
    for sport, data in summary.items():
        p_hrs = round(data["planned_time_seconds"] / 3600, 2)
        c_hrs = round(data["completed_time_seconds"] / 3600, 2)
        pct = round((c_hrs / p_hrs * 100), 1) if p_hrs > 0 else (100.0 if c_hrs > 0 else 0.0)
        data["planned_hours"] = p_hrs
        data["completed_hours"] = c_hrs
        data["compliance_percent"] = pct

        # Distances per discipline (km for cycling/running, meters for swimming)
        p_dist_m = data["planned_distance_meters"]
        c_dist_m = data["completed_distance_meters"]

        if sport == "swimming":
            data["planned_km"] = round(p_dist_m / 1000, 2)
            data["completed_km"] = round(c_dist_m / 1000, 2)
            data["planned_distance_formatted"] = f"{int(p_dist_m):,} m".replace(",", ".") if p_dist_m > 0 else "0 m"
            data["completed_distance_formatted"] = f"{int(c_dist_m):,} m".replace(",", ".") if c_dist_m > 0 else "0 m"
            data["distance_unit"] = "m"
        elif sport == "strength":
            data["planned_km"] = 0.0
            data["completed_km"] = 0.0
            data["planned_distance_formatted"] = "Fuerza"
            data["completed_distance_formatted"] = "Fuerza"
            data["distance_unit"] = ""
        else:  # cycling, running
            p_km = round(p_dist_m / 1000, 1)
            c_km = round(c_dist_m / 1000, 1)
            data["planned_km"] = p_km
            data["completed_km"] = c_km
            data["planned_distance_formatted"] = f"{p_km} km"
            data["completed_distance_formatted"] = f"{c_km} km"
            data["distance_unit"] = "km"

        for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
            pz_min = round(data["zones"][z]["planned"] / 60)
            cz_min = round(data["zones"][z]["completed"] / 60)
            data["zones"][z]["planned_mins"] = pz_min
            data["zones"][z]["completed_mins"] = cz_min

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

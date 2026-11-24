"""Expert Triathlon & Endurance Coach AI Engine.
Provides interval-aware technical workout evaluations and conversational coaching
using live Gemini 3 Flash + exact per-block/intra-block telemetry from Intervals.icu
and Garmin Connect, tailored to Pastor's live thresholds and physiological state.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .metrics import classify_power_zone, classify_speed_zone

logger = logging.getLogger(__name__)

SYSTEM_COACH_PROMPT = """Eres el Entrenador Experto en Deportes de Resistencia y Fisiología del Ejercicio de Pastor, atleta de Triatlón de Media y Larga Distancia.

Reglas de oro de comunicación y rigor técnico:
1. RESPONDE DIRECTA Y ESPECÍFICAMENTE a lo que pregunta el atleta. NUNCA repitas un resumen genérico del entrenamiento ni vuelvas a volcar las métricas globales si te están haciendo una pregunta concreta (por ejemplo, el desacople dentro de cada bloque de Z3, la comparación entre el 2º y el 4º bloque, la potencia pico de los sprints o un lap específico).
2. Usa SIEMPRE las cifras exactas de la telemetría por intervalos/bloques, zonas reales (Z1–Z7) y umbrales en vigor proporcionados en el contexto. No inventes datos ni te quedes solo con los promedios globales.
3. DISTINGUE SIEMPRE la estructura real de la sesión:
   - No juzgues un entrenamiento de series en pista (que incluye calentamiento, técnica de carrera y recuperaciones lentas) como "base aeróbica" por tener un ritmo medio lento.
   - No juzgues una salida de bici con sprints cortos neuromusculares (Z6–Z7) como "únicamente base aeróbica" por tener una potencia media de Z2.
   - Analiza por separado los bloques principales de trabajo (series, bloques de umbral/tempo, sprints) frente a los bloques de calentamiento, técnica, recuperación y enfriamiento.
4. Cálculos fisiológicos rigurosos:
   - Desacople entre dos bloques A y B: ((EF_A - EF_B) / EF_A) * 100, donde EF en carrera = velocidad (m/min) / FC media, y EF en ciclismo (FEc) = potencia media (Pmed en W) / FC media (siempre por potencia media, NO normalizada).
   - Desacople intra-bloque: usa el valor exacto `decoupling_percent` calculado por Intervals.icu sobre la serie segundo a segundo de cada intervalo.
   - Interpretación del desacople: < 3.5% excelente estabilidad aeróbica; 3.5% – 5.0% controlado; > 5.0% deriva cardíaca acusada.
5. Integra el Sistema Nervioso Autónomo (VFC/HRV, FC reposo, CTL/ATL/TSB) cuando aporte valor práctico a la pregunta.
6. Tono profesional, científico, directo, claro y cercano, usando tablas Markdown cuando ayuden a comparar bloques o parciales. NO uses sintaxis LaTeX (`$...$`, `\\times`, `\\mathbf`, `\\frac`); escribe siempre fórmulas y operadores en texto plano Unicode limpio (ej.: `(1.673 - 1.643) / 1.673 × 100 = **1.79%**`).
"""


def _fmt_dur(sec: float) -> str:
    s = int(round(max(0.0, sec)))
    h = s // 3600
    m = (s % 3600) // 60
    rem = s % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    if m > 0:
        return f"{m}:{rem:02d}"
    return f"{rem}s"


def _fmt_run_pace(speed_mps: Optional[float]) -> str:
    if not speed_mps or speed_mps <= 0:
        return "--:--/km"
    sec_km = 1000.0 / float(speed_mps)
    m = int(sec_km // 60)
    s = int(round(sec_km % 60))
    if s >= 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}/km"


def _fmt_swim_pace(speed_mps: Optional[float]) -> str:
    if not speed_mps or speed_mps <= 0:
        return "--:--/100m"
    sec_100 = 100.0 / float(speed_mps)
    m = int(sec_100 // 60)
    s = sec_100 % 60
    return f"{m}:{s:04.1f}/100m"


def _calc_block_ef(sport: str, avg_power: Optional[float], weighted_power: Optional[float], avg_speed_mps: Optional[float], avg_hr: Optional[float]) -> Optional[float]:
    if not avg_hr or avg_hr <= 0:
        return None
    if sport == "cycling":
        p = avg_power if (avg_power is not None and avg_power > 0) else weighted_power
        if not p or p <= 0:
            return None
        return round(float(p) / float(avg_hr), 3)
    elif sport == "running":
        if not avg_speed_mps or avg_speed_mps <= 0:
            return None
        return round((float(avg_speed_mps) * 60.0) / float(avg_hr), 3)
    elif sport == "swimming":
        if not avg_speed_mps or avg_speed_mps <= 0:
            return None
        return round((float(avg_speed_mps) * 60.0) / float(avg_hr), 3)
    return None


def _calc_inter_block_decoupling(ef1: Optional[float], ef2: Optional[float]) -> Optional[float]:
    if not ef1 or not ef2 or ef1 <= 0:
        return None
    return round(((ef1 - ef2) / ef1) * 100.0, 2)


class AICoachService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()

    def _call_gemini_api(self, prompt: str, system_instruction: str = SYSTEM_COACH_PROMPT) -> Optional[str]:
        if not self.api_key:
            return None

        # Verified active models in priority order (Gemini 3 Flash primary)
        models_to_try = [
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-flash-latest",
            "gemini-pro-latest",
            "gemma-4-31b-it",
        ]

        # 1. Direct HTTP REST API to v1beta (fastest & avoids thought-part leakage)
        try:
            import requests

            for m in models_to_try:
                max_attempts = 2 if m == "gemini-3-flash-preview" else 1
                for attempt in range(max_attempts):
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
                        headers = {"Content-Type": "application/json"}
                        payload: Dict[str, Any] = {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.35},
                        }
                        # Gemma models do not always accept system_instruction; prepend if gemma
                        if m.startswith("gemma"):
                            payload["contents"][0]["parts"][0]["text"] = f"{system_instruction}\n\n{prompt}"
                        else:
                            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

                        resp = requests.post(url, json=payload, headers=headers, timeout=35)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                text_parts = [
                                    p["text"]
                                    for p in parts
                                    if isinstance(p, dict) and "text" in p and not p.get("thought")
                                ]
                                if text_parts:
                                    return "\n".join(text_parts).strip()
                        elif resp.status_code == 503 and attempt + 1 < max_attempts:
                            time.sleep(1.2)
                            continue
                        else:
                            logger.info(f"REST Gemini model {m} HTTP {resp.status_code}: {resp.text[:120]}")
                            break
                    except Exception as req_err:
                        logger.debug(f"REST Gemini model {m} call failed: {req_err}")
                        break
        except Exception as rest_e:
            logger.warning(f"REST Gemini call failed: {rest_e}")

        # 2. Secondary fallback via google.genai SDK
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=20000),
            )
            for m in models_to_try[:3]:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.35,
                        ),
                    )
                    if response and response.text:
                        return response.text.strip()
                except Exception as inner_e:
                    logger.debug(f"google.genai SDK model {m} failed: {inner_e}")
                    continue
        except Exception as e:
            logger.warning(f"google.genai SDK failed: {e}")

        return None

    # =========================================================================
    # INTERVAL & STRUCTURE ANALYZER (Powers BOTH auto-evaluation & Q&A chat)
    # =========================================================================
    def _analyze_workout_structure(
        self,
        workout: Dict[str, Any],
        disciplines_thresholds: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Builds exact per-block telemetry, time-in-zones (Z1-Z7), intra-block & inter-block
        decoupling, and classifies the TRUE physiological stimulus of the workout
        (never fooled by slow warm-up, running drills/technique, recoveries, or cool-down).
        """
        sport = workout.get("sport_type", "running")
        name = (workout.get("name") or "Entrenamiento").strip()
        planned_ctx = workout.get("planned_workout_context") or {}
        planned_name = (planned_ctx.get("name") or "").strip()
        planned_desc = (planned_ctx.get("description") or "").strip()
        combined_title = f"{name} {planned_name} {planned_desc}".lower()

        disc = disciplines_thresholds or {}
        bike_cfg = disc.get("cycling") or {}
        run_cfg = disc.get("running") or {}
        swim_cfg = disc.get("swimming") or {}

        ftp = float(bike_cfg.get("ftp") or 348.0)
        bike_pcts = bike_cfg.get("power_zone_pcts") or [55.0, 75.0, 90.0, 105.0, 120.0, 150.0, 999.0]
        run_tp = float(run_cfg.get("threshold_speed_mps") or 4.5455)
        run_pcts = run_cfg.get("pace_zone_pcts") or [77.5, 87.7, 94.3, 100.0, 103.4, 111.5, 999.0]
        swim_tp = float(swim_cfg.get("threshold_speed_mps") or 1.1236)
        swim_pcts = swim_cfg.get("pace_zone_pcts") or [77.5, 87.7, 94.3, 100.0, 103.4, 111.5, 999.0]

        # 1. Exact time in zones (Z1..Z7) in seconds
        zone_secs: Dict[str, int] = {f"Z{i}": 0 for i in range(1, 8)}
        if sport == "cycling" and isinstance(workout.get("icu_zone_times"), list):
            for z_obj in workout["icu_zone_times"]:
                zid = str(z_obj.get("id") or "")
                secs = int(z_obj.get("secs") or 0)
                if zid in zone_secs and secs > 0:
                    zone_secs[zid] += secs
        elif sport in ("running", "swimming") and isinstance(workout.get("pace_zone_times"), list):
            pz = workout["pace_zone_times"]
            for i in range(min(len(pz), 7)):
                secs = int(pz[i] or 0)
                if secs > 0:
                    zone_secs[f"Z{i + 1}"] += secs

        # 2. Build unified structured blocks list (prefer Intervals.icu intervals because they include intra-block decoupling!)
        icu_ivs = workout.get("icu_intervals") or []
        splits = workout.get("splits") or []
        blocks: List[Dict[str, Any]] = []

        if isinstance(icu_ivs, list) and len(icu_ivs) > 0:
            for idx, iv in enumerate(icu_ivs):
                dur = float(iv.get("duration_seconds") or 0.0)
                dist = float(iv.get("distance_meters") or 0.0)
                if dur < 3.0:
                    continue
                avg_p = iv.get("avg_power")
                w_p = iv.get("weighted_power")
                max_p = iv.get("max_power")
                spd = iv.get("avg_speed_mps") or (dist / dur if dur > 0 and dist > 0 else None)
                hr = iv.get("avg_heart_rate")
                max_hr_b = iv.get("max_heart_rate")
                dec_intra = iv.get("decoupling_percent")

                # Classify zone accurately according to sport primary metric (Power for cycling, Pace for run/swim)
                if sport == "cycling":
                    z_num = classify_power_zone(float(avg_p or w_p or 0), ftp, bike_pcts) if (avg_p or w_p) else int(iv.get("zone") or 1)
                elif sport == "running":
                    z_num = classify_speed_zone(float(spd or 0), run_tp, run_pcts) if spd else int(iv.get("zone") or 1)
                elif sport == "swimming":
                    z_num = classify_speed_zone(float(spd or 0), swim_tp, swim_pcts) if (spd and dist > 0) else int(iv.get("zone") or 1)
                else:
                    z_num = int(iv.get("zone") or 1)

                ef = _calc_block_ef(sport, avg_p, w_p, spd, hr)
                blocks.append({
                    "index": idx + 1,
                    "source": "intervals.icu",
                    "type": str(iv.get("type") or "WORK").upper(),
                    "zone": z_num,
                    "zone_label": f"Z{z_num}",
                    "duration_seconds": round(dur, 1),
                    "duration_fmt": _fmt_dur(dur),
                    "distance_meters": round(dist, 1),
                    "avg_speed_mps": round(float(spd), 3) if spd else None,
                    "pace_fmt": _fmt_run_pace(spd) if sport == "running" else (_fmt_swim_pace(spd) if sport == "swimming" else None),
                    "avg_power": round(float(avg_p), 1) if avg_p is not None else None,
                    "weighted_power": round(float(w_p), 1) if w_p is not None else None,
                    "max_power": round(float(max_p), 1) if max_p is not None else None,
                    "avg_heart_rate": round(float(hr), 1) if hr is not None else None,
                    "max_heart_rate": round(float(max_hr_b), 1) if max_hr_b is not None else None,
                    "avg_cadence": iv.get("avg_cadence"),
                    "ef": ef,
                    "intra_decoupling_percent": round(float(dec_intra), 2) if dec_intra is not None else None,
                    "is_rest": (sport == "swimming" and dist <= 0),
                })
        elif isinstance(splits, list) and len(splits) > 0:
            for idx, sp in enumerate(splits):
                dur = float(sp.get("duration_seconds") or 0.0)
                dist = float(sp.get("distance_meters") or 0.0)
                if dur < 3.0:
                    continue
                avg_p = sp.get("avg_power")
                w_p = sp.get("normalised_power")
                max_p = sp.get("max_power")
                spd = sp.get("avg_speed_mps") or (dist / dur if dur > 0 and dist > 0 else None)
                hr = sp.get("avg_heart_rate")
                max_hr_b = sp.get("max_heart_rate")

                if sport == "cycling":
                    z_num = classify_power_zone(float(avg_p or w_p or 0), ftp, bike_pcts) if (avg_p or w_p) else 1
                elif sport == "running":
                    z_num = classify_speed_zone(float(spd or 0), run_tp, run_pcts) if spd else 1
                elif sport == "swimming":
                    z_num = classify_speed_zone(float(spd or 0), swim_tp, swim_pcts) if (spd and dist > 0) else 1
                else:
                    z_num = 1

                ef = _calc_block_ef(sport, avg_p, w_p, spd, hr)
                blocks.append({
                    "index": sp.get("lap_index") or (idx + 1),
                    "source": "garmin_laps",
                    "type": "WORK" if z_num >= 2 else "RECOVERY",
                    "zone": z_num,
                    "zone_label": f"Z{z_num}",
                    "duration_seconds": round(dur, 1),
                    "duration_fmt": _fmt_dur(dur),
                    "distance_meters": round(dist, 1),
                    "avg_speed_mps": round(float(spd), 3) if spd else None,
                    "pace_fmt": _fmt_run_pace(spd) if sport == "running" else (_fmt_swim_pace(spd) if sport == "swimming" else None),
                    "avg_power": round(float(avg_p), 1) if avg_p is not None else None,
                    "weighted_power": round(float(w_p), 1) if w_p is not None else None,
                    "max_power": round(float(max_p), 1) if max_p is not None else None,
                    "avg_heart_rate": round(float(hr), 1) if hr is not None else None,
                    "max_heart_rate": round(float(max_hr_b), 1) if max_hr_b is not None else None,
                    "avg_cadence": sp.get("avg_cadence"),
                    "ef": ef,
                    "intra_decoupling_percent": None,
                    "is_rest": (sport == "swimming" and dist <= 0),
                })

        # Fallback zone_secs from blocks if Intervals zone_times wasn't available
        if sum(zone_secs.values()) == 0 and blocks:
            for b in blocks:
                if not b.get("is_rest"):
                    zone_secs[b["zone_label"]] += int(round(b["duration_seconds"]))

        # 3. Group active blocks by zone and identify sprints, main quality blocks, aerobic blocks
        blocks_by_zone: Dict[str, List[Dict[str, Any]]] = {f"Z{i}": [] for i in range(1, 8)}
        for b in blocks:
            if not b.get("is_rest"):
                blocks_by_zone[b["zone_label"]].append(b)

        sprint_blocks = [
            b for b in blocks
            if not b.get("is_rest") and (
                (b["zone"] >= 6 and b["duration_seconds"] <= 60)
                or (sport == "cycling" and b.get("max_power") and b["max_power"] >= ftp * 1.8 and b["duration_seconds"] <= 45)
            )
        ]
        high_int_blocks = [
            b for b in blocks
            if not b.get("is_rest") and b["zone"] >= 5 and b["duration_seconds"] >= 20 and b not in sprint_blocks
        ]
        threshold_tempo_blocks = [
            b for b in blocks
            if not b.get("is_rest") and b["zone"] in (3, 4) and b["duration_seconds"] >= 60
        ]
        aerobic_z2_blocks = [
            b for b in blocks
            if not b.get("is_rest") and b["zone"] == 2 and b["duration_seconds"] >= 180
        ]

        # 4. Compute true physiological session classification (NEVER fooled by global averages!)
        z3_s = zone_secs["Z3"]
        z4_s = zone_secs["Z4"]
        z5_s = zone_secs["Z5"]
        z6_s = zone_secs["Z6"]
        z7_s = zone_secs["Z7"]
        max_power = float(workout.get("max_power") or 0.0)
        if not max_power and blocks:
            mps = [b["max_power"] for b in blocks if b.get("max_power")]
            max_power = float(max(mps)) if mps else 0.0

        session_type_key = "aerobic_base"
        session_type_label = "Base Aeróbica Continua (Z1–Z2)"
        key_blocks: List[Dict[str, Any]] = aerobic_z2_blocks

        if sport == "strength":
            session_type_key = "strength"
            session_type_label = "Fuerza Complementaria / Neuromuscular"
            key_blocks = []
        elif any(k in combined_title for k in ["400 + 200", "400+200", "pam 5", "pam5", "test ", "5k", "10k", "competición", "competicion", "triatlón", "triatlon"]):
            session_type_key = "test_or_race"
            session_type_label = "Test Fisiológico / Competición"
            key_blocks = [b for b in blocks if not b.get("is_rest") and b["zone"] >= 4] or high_int_blocks or threshold_tempo_blocks
        elif len(sprint_blocks) >= 2 or (
            any(k in combined_title for k in ["sprin", "neuromuscular", "explosiv", "aceleraci", "contrastes"])
            and (len(sprint_blocks) >= 1 or (z6_s + z7_s) >= 25 or (sport == "cycling" and max_power >= ftp * 1.85))
        ):
            session_type_key = "aerobic_plus_sprints"
            session_type_label = "Base Aeróbica con Estímulos Neuromusculares (Sprints Z6–Z7)"
            key_blocks = sprint_blocks
        elif len(high_int_blocks) >= 2 or (z5_s + z6_s) >= 180 or (z4_s + z5_s + z6_s >= 420 and (z5_s + z6_s) >= 90):
            session_type_key = "high_intensity_intervals"
            session_type_label = "Series de Calidad / Alta Intensidad (Z4–Z6)"
            key_blocks = [b for b in blocks if not b.get("is_rest") and b["zone"] >= 4 and b["duration_seconds"] >= 20] or high_int_blocks
        elif len(threshold_tempo_blocks) >= 2 or (z3_s + z4_s) >= 480 or (
            any(k in combined_title for k in ["umbral", "tempo", "doble umbral"]) and (z3_s + z4_s) >= 240
        ):
            session_type_key = "threshold_tempo"
            session_type_label = "Bloques Estructurados de Tempo / Umbral (Z3–Z4)"
            key_blocks = threshold_tempo_blocks
        elif sport == "swimming" and (z3_s + z4_s + z5_s + z6_s + z7_s) >= 300:
            session_type_key = "swim_quality"
            session_type_label = "Natación con Bloques de Ritmo / Calidad (Z3–Z7)"
            key_blocks = [b for b in blocks if not b.get("is_rest") and b["zone"] >= 3]
        else:
            session_type_key = "aerobic_base"
            session_type_label = "Base Aeróbica Continua (Z1–Z2)"
            key_blocks = aerobic_z2_blocks or [b for b in blocks if not b.get("is_rest")]

        # 5. Pre-compute inter-block decoupling summary for each zone that has >= 2 blocks
        zone_block_drifts: Dict[str, Dict[str, Any]] = {}
        for z_lbl, z_list in blocks_by_zone.items():
            long_z = [b for b in z_list if b["duration_seconds"] >= 30 and b.get("ef")]
            if len(long_z) >= 2:
                first_b = long_z[0]
                last_b = long_z[-1]
                drift_first_last = _calc_inter_block_decoupling(first_b["ef"], last_b["ef"])
                pairwise = {}
                for i in range(len(long_z)):
                    for j in range(i + 1, len(long_z)):
                        d_ij = _calc_inter_block_decoupling(long_z[i]["ef"], long_z[j]["ef"])
                        if d_ij is not None:
                            pairwise[f"{i+1}_to_{j+1}"] = d_ij
                zone_block_drifts[z_lbl] = {
                    "count": len(long_z),
                    "first_to_last_decoupling_percent": drift_first_last,
                    "pairwise_decoupling_percent": pairwise,
                    "blocks": [
                        {
                            "block_in_zone": idx + 1,
                            "interval_index": b["index"],
                            "duration": b["duration_fmt"],
                            "distance_m": b["distance_meters"],
                            "pace": b["pace_fmt"],
                            "avg_power": b["avg_power"],
                            "max_power": b["max_power"],
                            "avg_hr": b["avg_heart_rate"],
                            "ef": b["ef"],
                            "intra_decoupling_percent": b["intra_decoupling_percent"],
                        }
                        for idx, b in enumerate(long_z)
                    ],
                }

        return {
            "sport": sport,
            "session_type_key": session_type_key,
            "session_type_label": session_type_label,
            "zone_secs": zone_secs,
            "zone_mins": {k: round(v / 60.0, 1) for k, v in zone_secs.items() if v > 0},
            "blocks": blocks,
            "blocks_by_zone": blocks_by_zone,
            "key_blocks": key_blocks,
            "sprint_blocks": sprint_blocks,
            "aerobic_z2_blocks": aerobic_z2_blocks,
            "zone_block_drifts": zone_block_drifts,
            "max_power": round(max_power, 1) if max_power else None,
            "ftp": ftp,
            "run_threshold_mps": run_tp,
            "swim_threshold_mps": swim_tp,
            "planned_name": planned_name,
            "planned_description": planned_desc,
        }

    def _format_blocks_for_prompt(self, struct: Dict[str, Any]) -> str:
        """Creates a crisp, token-efficient Markdown telemetry table for Gemini containing
        every interval/block, exact intra-block decoupling, and pre-calculated inter-block drifts.
        """
        sport = struct["sport"]
        lines = [
            f"CLASIFICACIÓN REAL DE LA SESIÓN: {struct['session_type_label']}",
            f"TIEMPO REAL POR ZONAS (min): {json.dumps(struct['zone_mins'], ensure_ascii=False)}",
        ]
        if struct.get("planned_name"):
            lines.append(f"SESIÓN PLANIFICADA EN INTERVALS.ICU: {struct['planned_name']}")
        if struct.get("planned_description"):
            lines.append(f"PRESCRIPCIÓN PLANIFICADA: {struct['planned_description'][:400]}")

        blocks = struct.get("blocks") or []
        if blocks:
            lines.append("\nDESGLOSE COMPLETO DE BLOQUES / INTERVALOS (con desacople intra-bloque exacto de Intervals.icu):")
            if sport == "cycling":
                lines.append("| # | Tipo | Zona | Duración | Pot. Media | Pot. Máx | FC Media | FEc (W/bpm) | Desacople Intra-Bloque |")
                lines.append("|---|---|---|---|---|---|---|---|---|")
                for b in blocks[:35]:
                    dec_s = f"{b['intra_decoupling_percent']}%" if b["intra_decoupling_percent"] is not None else "N/A"
                    lines.append(
                        f"| #{b['index']} | {b['type']} | {b['zone_label']} | {b['duration_fmt']} | "
                        f"{b['avg_power'] or '--'}W | {b['max_power'] or '--'}W | {b['avg_heart_rate'] or '--'} bpm | "
                        f"{b['ef'] or '--'} | {dec_s} |"
                    )
            else:
                lines.append("| # | Tipo | Zona | Duración | Dist(m) | Ritmo | Potencia | FC Media | EF | Desacople Intra-Bloque |")
                lines.append("|---|---|---|---|---|---|---|---|---|---|")
                for b in blocks[:35]:
                    dec_s = f"{b['intra_decoupling_percent']}%" if b["intra_decoupling_percent"] is not None else "N/A"
                    lines.append(
                        f"| #{b['index']} | {b['type']} | {b['zone_label']} | {b['duration_fmt']} | "
                        f"{int(round(b['distance_meters']))} | {b['pace_fmt'] or '--'} | {b['avg_power'] or '--'}W | "
                        f"{b['avg_heart_rate'] or '--'} bpm | {b['ef'] or '--'} | {dec_s} |"
                    )

        drifts = struct.get("zone_block_drifts") or {}
        if drifts:
            lines.append("\nCOMPARATIVA Y DESACOPLE INTER-BLOQUES PRECALCULADO POR ZONA:")
            for z_lbl, dinfo in drifts.items():
                lines.append(f"- **{z_lbl}** ({dinfo['count']} bloques, desacople 1º→último: {dinfo['first_to_last_decoupling_percent']}%):")
                for blk in dinfo["blocks"]:
                    metric_s = f"{blk['avg_power']}W (máx {blk['max_power']}W)" if sport == "cycling" else f"{blk['pace']} ({blk['avg_power'] or '--'}W)"
                    intra_s = f"{blk['intra_decoupling_percent']}%" if blk["intra_decoupling_percent"] is not None else "N/A"
                    lines.append(
                        f"    * Bloque {z_lbl} #{blk['block_in_zone']} (Lap/Int #{blk['interval_index']}, {blk['duration']}): "
                        f"{metric_s}, FC {blk['avg_hr']} bpm, EF={blk['ef']}, desacople intra-bloque={intra_s}"
                    )
                if dinfo.get("pairwise_decoupling_percent"):
                    pw_str = ", ".join(f"B{k.replace('_to_', '→B')}: {v}%" for k, v in dinfo["pairwise_decoupling_percent"].items())
                    lines.append(f"    * Desacople entre pares de bloques {z_lbl}: {pw_str}")

        return "\n".join(lines)

    # =========================================================================
    # AUTOMATIC WORKOUT EVALUATION (Interval & Effort Aware!)
    # =========================================================================
    def analyze_workout(
        self,
        workout_data: Dict[str, Any],
        efficiency_data: Dict[str, Any],
        decoupling_data: Dict[str, Any],
        wellness_context: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
        disciplines_thresholds: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generates an expert coach technical evaluation that accurately reflects the REAL
        effort of the workout (intervals, sprints, threshold blocks, tests, or aerobic base),
        never misclassifying quality sessions or neuromuscular rides due to slow global averages.
        """
        struct = self._analyze_workout_structure(workout_data, disciplines_thresholds)

        if use_llm and self.api_key:
            sport = workout_data.get("sport_type", "running")
            name = workout_data.get("name", "Entrenamiento")
            dur_mins = round((workout_data.get("duration_seconds") or 0) / 60, 1)
            dist_km = round((workout_data.get("distance_meters") or 0) / 1000, 2)
            blocks_txt = self._format_blocks_for_prompt(struct)
            prompt = f"""Realiza un análisis técnico exhaustivo de este entrenamiento:
- Deporte: {sport.upper()} ({name})
- Duración: {dur_mins} min ({dist_km} km) | TSS: {workout_data.get('tss')}
- FC: Media {workout_data.get('avg_heart_rate')} bpm, Máxima {workout_data.get('max_heart_rate')} bpm
- Eficiencia global: {json.dumps(efficiency_data, ensure_ascii=False)}
- Desacople global: {json.dumps(decoupling_data, ensure_ascii=False)}
- Bienestar / SNA del día: {json.dumps(wellness_context or {}, ensure_ascii=False)}

{blocks_txt}

Estructura la valoración en 4 secciones claras en Markdown basadas en los BLOQUES REALES (sin dejarte engañar por medias globales si hubo calentamiento/técnica/recuperaciones o sprints):
1. **Naturaleza Real del Estímulo y Ejecución**
2. **Rendimiento en Bloques Principales, Eficiencia y Desacople**
3. **Impacto Fisiológico y Respuesta del SNA**
4. **Pautas Específicas para las Próximas 24–48 h**
"""
            ai_reply = self._call_gemini_api(prompt)
            if ai_reply:
                return {
                    "source": "gemini_ai",
                    "content": ai_reply,
                    "summary": f"{struct['session_type_label']} — {name}",
                }

        return self._generate_heuristic_workout_analysis(
            workout_data, efficiency_data, decoupling_data, wellness_context, struct
        )

    def _generate_heuristic_workout_analysis(
        self,
        workout: Dict[str, Any],
        efficiency: Dict[str, Any],
        decoupling: Dict[str, Any],
        wellness: Optional[Dict[str, Any]],
        struct: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Interval-aware physiological evaluation engine: evaluates actual work blocks,
        sprints, threshold repeats, and time-in-zones rather than misleading session averages.
        """
        if struct is None:
            struct = self._analyze_workout_structure(workout)

        sport = workout.get("sport_type", "running")
        name = workout.get("name", "Entrenamiento")
        dur_mins = round((workout.get("duration_seconds") or 0) / 60, 1)
        dist_m = float(workout.get("distance_meters") or 0.0)
        dist_str = f"{int(round(dist_m))} m" if sport == "swimming" else (f"{round(dist_m / 1000, 2)} km" if dist_m > 0 else "Sesión en sala")
        avg_hr = round(workout.get("avg_heart_rate") or 0)
        max_hr = round(workout.get("max_heart_rate") or 0)
        tss = workout.get("tss")
        tss_str = f" | **{tss} TSS**" if tss is not None else ""

        stype = struct["session_type_key"]
        slabel = struct["session_type_label"]
        z_mins = struct["zone_mins"]
        z_summary_txt = " • ".join(f"**{k}**: {v} min" for k, v in z_mins.items()) if z_mins else "Sin desglose de zonas"
        key_blocks = struct.get("key_blocks") or []
        sprint_blocks = struct.get("sprint_blocks") or []
        aerobic_z2_blocks = struct.get("aerobic_z2_blocks") or []
        ftp = int(round(struct.get("ftp") or 348))

        sections: List[str] = []

        # -----------------------------------------------------------------
        # SECTION 1: REAL STIMULUS CLASSIFICATION & EXECUTION
        # -----------------------------------------------------------------
        if stype == "strength":
            sec1 = (
                f"### 1. Naturaleza del Estímulo: {slabel}\n"
                f"La sesión **{name}** ({dur_mins} min{tss_str}) corresponde a trabajo estructural y neuromuscular de fuerza/movilidad, "
                f"donde la frecuencia cardíaca media (**{avg_hr} bpm**, máx. **{max_hr} bpm**) no mide la exigencia real de tensión mecánica ni reclutamiento de fibras rápidas. "
                f"El objetivo en este bloque es proteger la estabilidad articular, mejorar la rigidez tendinosa y sostener la transferencia de fuerza a la carrera y el pedaleo."
            )
        elif stype == "aerobic_plus_sprints":
            sp_count = len(sprint_blocks)
            peak_w = struct.get("max_power")
            avg_sp_w = round(sum(b["avg_power"] for b in sprint_blocks if b.get("avg_power")) / max(1, sum(1 for b in sprint_blocks if b.get("avg_power")))) if sprint_blocks else 0
            peak_str = f" con pico máximo de **{int(round(peak_w))} W** ({round(peak_w / ftp * 100)}% FTP)" if peak_w else ""
            if sport == "cycling":
                sec1 = (
                    f"### 1. Naturaleza Real del Estímulo: {slabel}\n"
                    f"Aunque el promedio global de **{name}** ({dur_mins} min, {dist_str}{tss_str}) refleja un coste cardiovascular contenido (**{avg_hr} bpm**, NP **{round(workout.get('normalised_power') or workout.get('avg_power') or 0)} W**, FEc **{efficiency.get('fec', 'N/A')}**), "
                    f"**no se trata de un rodaje únicamente de base aeróbica**: la sesión combina volumen aeróbico en Z2 con **{sp_count} sprints neuromusculares explosivos** "
                    f"(media de **{avg_sp_w} W** en los bloques de sprint{peak_str}).\n"
                    f"- **Distribución real por zonas**: {z_summary_txt}.\n"
                    f"- **Objetivo fisiológico**: reclutamiento máximo de unidades motoras rápidas (fibras tipo IIx) y potencia neuromuscular aláctica sin acumular acidosis láctica, manteniendo intacta la oxidación aeróbica del resto del rodaje."
                )
            else:
                sec1 = (
                    f"### 1. Naturaleza Real del Estímulo: {slabel}\n"
                    f"**{name}** ({dur_mins} min, {dist_str}{tss_str}) combina trabajo aeróbico base con **{sp_count} estímulos neuromusculares rápidos** "
                    f"(aceleraciones/sprints en Z6–Z7). El ritmo medio global queda suavizado por el calentamiento, recuperaciones y vuelta a la calma, pero el estímulo biomecánico y neural es de alta velocidad.\n"
                    f"- **Distribución real por zonas**: {z_summary_txt}."
                )
        elif stype == "high_intensity_intervals":
            hi_mins = round((struct["zone_secs"]["Z4"] + struct["zone_secs"]["Z5"] + struct["zone_secs"]["Z6"] + struct["zone_secs"]["Z7"]) / 60.0, 1)
            sec1 = (
                f"### 1. Naturaleza Real del Estímulo: {slabel}\n"
                f"**{name}** ({dur_mins} min, {dist_str}{tss_str}) es una **sesión de calidad / alta intensidad** y **NO un rodaje de base aeróbica**. "
                f"Aunque el ritmo o potencia media global parezca moderado debido al calentamiento, bloques de técnica de carrera, recuperaciones y enfriamiento, "
                f"acumulaste **{hi_mins} min reales en zonas Z4–Z6** (FC máx. **{max_hr} bpm**).\n"
                f"- **Distribución real por zonas**: {z_summary_txt}.\n"
                f"- **Estímulo fisiológico**: demanda alta sobre el VO2 Máx, aclarado de lactato y economía a ritmos rápidos; la valoración real debe hacerse sobre los bloques principales de trabajo y no sobre la media total."
            )
        elif stype == "threshold_tempo":
            th_mins = round((struct["zone_secs"]["Z3"] + struct["zone_secs"]["Z4"]) / 60.0, 1)
            sec1 = (
                f"### 1. Naturaleza Real del Estímulo: {slabel}\n"
                f"**{name}** ({dur_mins} min, {dist_str}{tss_str}) es una **sesión estructurada de tempo / umbral** con **{len(key_blocks)} bloques principales** "
                f"y **{th_mins} min efectivos en Z3–Z4** (FC máx. **{max_hr} bpm**). "
                f"El ritmo medio global incluye el calentamiento y enfriamiento en Z1, por lo que el verdadero valor fisiológico reside en la estabilidad mecánica y cardiovascular dentro de los bloques de trabajo.\n"
                f"- **Distribución real por zonas**: {z_summary_txt}."
            )
        elif stype == "test_or_race":
            sec1 = (
                f"### 1. Naturaleza Real del Estímulo: {slabel}\n"
                f"**{name}** ({dur_mins} min, {dist_str}{tss_str}) corresponde a una sesión de **evaluación de rendimiento / esfuerzo máximo** "
                f"(FC media **{avg_hr} bpm**, pico **{max_hr} bpm**). Los datos medios están diluidos por calentamiento y suelta, por lo que la referencia clave son los bloques máximos ejecutados.\n"
                f"- **Distribución real por zonas**: {z_summary_txt}."
            )
        else:
            eff_txt = ""
            if sport == "cycling" and efficiency.get("fec"):
                eff_txt = f" con **FEc de {efficiency['fec']} W/bpm** (IV: **{efficiency.get('iv', 1.0)}**)"
            elif sport == "running" and efficiency.get("fecp"):
                eff_txt = f" con **FEcp de {efficiency['fecp']}** ({efficiency.get('pace_str', '')})"
            elif sport == "swimming" and efficiency.get("pace_str"):
                eff_txt = f" a **{efficiency['pace_str']}**"
            sec1 = (
                f"### 1. Naturaleza Real del Estímulo: {slabel}\n"
                f"La sesión **{name}** ({dur_mins} min, {dist_str}{tss_str}) fue un trabajo genuino de **base aeróbica continua**{eff_txt}. "
                f"La FC media (**{avg_hr} bpm**, máx. **{max_hr} bpm**) se mantuvo bajo control subumbral, estimulando biogénesis mitocondrial y capilarización sin estrés glucolítico.\n"
                f"- **Distribución real por zonas**: {z_summary_txt}."
            )
        sections.append(sec1)

        # -----------------------------------------------------------------
        # SECTION 2: MAIN BLOCKS, EFFICIENCY & INTRA/INTER-BLOCK DECOUPLING
        # -----------------------------------------------------------------
        if stype == "aerobic_plus_sprints" and sport == "cycling":
            sp_rows = []
            for idx, b in enumerate(sprint_blocks[:10], start=1):
                sp_rows.append(
                    f"| Sprint #{idx} | {b['duration_fmt']} | **{b['avg_power'] or '--'} W** | **{b['max_power'] or '--'} W** | {b['avg_heart_rate'] or '--'} bpm |"
                )
            sp_table = (
                "| Bloque | Duración | Pot. Media | Pot. Pico | FC |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
                + "\n".join(sp_rows)
            ) if sp_rows else ""

            aero_note = ""
            if len(aerobic_z2_blocks) >= 2:
                b_first, b_last = aerobic_z2_blocks[0], aerobic_z2_blocks[-1]
                z2_drift = _calc_inter_block_decoupling(b_first.get("ef"), b_last.get("ef"))
                aero_note = (
                    f"\n\n**Estabilidad de los Bloques Aeróbicos Z2 (aislando los sprints)**:\n"
                    f"- 1er bloque Z2 ({b_first['duration_fmt']}): **{b_first['avg_power']} W** @ **{b_first['avg_heart_rate']} bpm** (FEc **{b_first['ef']}**)\n"
                    f"- Último bloque Z2 ({b_last['duration_fmt']}): **{b_last['avg_power']} W** @ **{b_last['avg_heart_rate']} bpm** (FEc **{b_last['ef']}**)\n"
                    f"- **Desacople entre bloques Z2**: **{z2_drift}%** "
                    + ("(estabilidad aeróbica excelente incluso tras los toques neuromusculares)." if (z2_drift is not None and z2_drift < 3.5) else "(fatiga periférica moderada tras los sprints).")
                )

            sec2 = (
                f"### 2. Rendimiento Neuromuscular (Sprints) y Eficiencia Aeróbica\n"
                f"- **FEc Global**: **{efficiency.get('fec', 'N/A')} W/bpm** | **IV**: **{efficiency.get('iv', 'N/A')}** | **NP**: **{round(workout.get('normalised_power') or workout.get('avg_power') or 0)} W**\n\n"
                f"{sp_table}{aero_note}"
            )
        elif stype in ("threshold_tempo", "high_intensity_intervals", "test_or_race") and key_blocks:
            rows = []
            for idx, b in enumerate(key_blocks[:10], start=1):
                out_s = f"**{b['avg_power']} W** (máx {b['max_power'] or '--'}W)" if sport == "cycling" else f"**{b['pace_fmt']}**"
                dec_s = f"**{b['intra_decoupling_percent']}%**" if b.get("intra_decoupling_percent") is not None else "--"
                rows.append(
                    f"| Bloque #{idx} ({b['zone_label']}) | {b['duration_fmt']} | {out_s} | {b['avg_heart_rate'] or '--'} bpm | {b['ef'] or '--'} | {dec_s} |"
                )
            blk_table = (
                "| Bloque Principal | Duración | Ritmo / Potencia | FC Media | EF | Desacople Intra-Bloque |\n"
                "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                + "\n".join(rows)
            )
            inter_txt = ""
            valid_ef = [b for b in key_blocks if b.get("ef")]
            if len(valid_ef) >= 2:
                drift_fl = _calc_inter_block_decoupling(valid_ef[0]["ef"], valid_ef[-1]["ef"])
                if drift_fl is not None:
                    interp = "control excepcional de la deriva entre repeticiones" if drift_fl < 3.5 else ("deriva progresiva controlada propia del volumen de calidad" if drift_fl <= 5.5 else "fatiga cardiovascular acumulada en los últimos bloques")
                    inter_txt = f"\n\n- **Desacople entre el 1er y último bloque principal**: **{drift_fl}%** ({interp})."
            sec2 = (
                f"### 2. Desglose de Bloques Principales y Desacople Real\n"
                f"{blk_table}{inter_txt}"
            )
        elif decoupling.get("has_decoupling") and stype != "strength":
            dec_val = decoupling.get("decoupling_percent", 0.0)
            metric_name = decoupling.get("metric_name", "Desacople")
            h1 = decoupling.get("half_1", {}).get("label", "1ª mitad")
            h2 = decoupling.get("half_2", {}).get("label", "2ª mitad")
            status = "Excelente (< 3.5%)" if dec_val < 3.5 else ("Controlado (3.5% – 5.0%)" if dec_val <= 5.0 else "Deriva Acusada (> 5.0%)")
            sec2 = (
                f"### 2. Eficiencia Mecánica y Desacople ({metric_name})\n"
                f"- **{metric_name} Registrado**: **{dec_val}%** — *{status}*\n"
                f"- **1ª Mitad**: {h1}\n"
                f"- **2ª Mitad**: {h2}\n\n"
                + (
                    f"**Interpretación**: Desacople mínimo ({dec_val}%), confirmando estabilidad del volumen sistólico y excelente economía lipídica."
                    if dec_val < 3.5 else
                    f"**Interpretación**: Desacople de {dec_val}%, reflejando ligera fatiga periférica o coste termorregulador en la segunda parte."
                )
            )
        else:
            sec2 = (
                f"### 2. Eficiencia y Respuesta Cardiovascular\n"
                f"- **FC Media**: **{avg_hr} bpm** | **FC Máxima**: **{max_hr} bpm**.\n"
                f"- Ejecución ordenada acorde al tipo de sesión ({slabel})."
            )
        sections.append(sec2)

        # -----------------------------------------------------------------
        # SECTION 3: PHYSIOLOGICAL & SNA RESPONSE
        # -----------------------------------------------------------------
        rhr = wellness.get("resting_hr") if wellness else None
        hrv = wellness.get("hrv_ms") if wellness else None
        sna_vals = []
        if rhr:
            sna_vals.append(f"RHR: **{rhr} bpm**")
        if hrv:
            sna_vals.append(f"VFC: **{hrv} ms**")
        sna_prefix = f"Con tus marcadores matutinos ({', '.join(sna_vals)}), " if sna_vals else ""

        if stype == "aerobic_plus_sprints":
            sec3 = (
                f"### 3. Impacto Fisiológico y Sistema Nervioso Autónomo (SNA)\n"
                f"{sna_prefix}este tipo de sesión genera **estrés neuromuscular (SNC y fibras rápidas)** en los sprints de alta potencia, "
                f"con muy bajo impacto glucolítico global. Vigila la sensación de pesadez tendinosa/cuadricipital en las próximas 24 h aunque el pulso medio haya sido bajo (**{avg_hr} bpm**)."
            )
        elif stype in ("high_intensity_intervals", "threshold_tempo", "test_or_race"):
            sec3 = (
                f"### 3. Impacto Fisiológico y Sistema Nervioso Autónomo (SNA)\n"
                f"{sna_prefix}una sesión de **{slabel}** exige un mayor vaciamiento de glucógeno muscular y activación simpática temporal (pico de **{max_hr} bpm**). "
                f"La asimilación óptima se confirmará mañana si tu VFC se mantiene dentro de tu banda normal de Garmin y tu FC en reposo no repunta más de +2/+3 bpm."
            )
        elif stype == "strength":
            sec3 = (
                f"### 3. Impacto Fisiológico y Sistema Nervioso Autónomo (SNA)\n"
                f"{sna_prefix}el trabajo de fuerza induce fatiga mecánica local y micro-remodelación muscular/tendinosa con mínimo estrés cardiovascular. "
                f"Es un estímulo compatible con el volumen aeróbico siempre que se separen al menos 6–12 h de sesiones clave de calidad en carrera."
            )
        else:
            sec3 = (
                f"### 3. Impacto Fisiológico y Sistema Nervioso Autónomo (SNA)\n"
                f"{sna_prefix}la carga aeróbica acumulada se absorbe con alta tolerancia parasimpática sin penalizar la recuperación nocturna."
            )
        sections.append(sec3)

        # -----------------------------------------------------------------
        # SECTION 4: SPECIFIC NEXT-SESSION RECOMMENDATIONS
        # -----------------------------------------------------------------
        if stype == "aerobic_plus_sprints":
            sec4 = (
                f"### 4. Pautas Específicas para las Próximas 24–48 h\n"
                f"1. **Recuperación Neuromuscular**: Prioriza 25–30 g de proteína + reposición de carbohidratos moderada tras los sprints alácticos para acelerar la recuperación de fibras rápidas.\n"
                f"2. **Soltura Articular**: 10 min de movilidad de cadera/flexores y descarga suave de cuádriceps para llegar fresco al siguiente bloque.\n"
                f"3. **Siguiente Sesión**: Mantén los primeros 15 min estrictamente en Z1 para verificar que la fatiga neural de los sprints no eleva el pulso inicial."
            )
        elif stype in ("high_intensity_intervals", "threshold_tempo", "test_or_race"):
            sec4 = (
                f"### 4. Pautas Específicas para las Próximas 24–48 h\n"
                f"1. **Reposición de Glucógeno**: Aporta **1.0–1.2 g de carbohidratos/kg** (~75–90 g) junto con **25–30 g de proteína** en las 2 h posteriores para restaurar los depósitos usados en los bloques Z3–Z6.\n"
                f"2. **Rehidratación con Sodio**: 500–750 ml de líquido con electrolitos para normalizar el volumen plasmático y proteger el sueño profundo.\n"
                f"3. **Control del Día Siguiente**: Respeta la zona suave (Z1/Z2 baja) en la próxima sesión regenerativa para consolidar la supercompensación de estos bloques."
            )
        elif stype == "strength":
            sec4 = (
                f"### 4. Pautas Específicas Post-Fuerza\n"
                f"1. **Síntesis Proteica**: 25–35 g de proteína de alta calidad en la ventana post-sesión.\n"
                f"2. **Hidratación y Sueño**: Dormir ≥ 7.5 h para maximizar la adaptación neuromuscular y tendinosa."
            )
        else:
            sec4 = (
                f"### 4. Pautas para la Siguiente Sesión\n"
                f"1. **Hidratación y Electrolitos**: Reponer 500–750 ml de líquido con sodio.\n"
                f"2. **Consistencia Aeróbica**: Mantener el control del primer tercio en Z1/Z2 baja para sostener el desacople por debajo del 3.5%."
            )
        sections.append(sec4)

        return {
            "source": "expert_interval_engine",
            "content": "\n\n".join(sections),
            "summary": f"{slabel} — {name}",
        }

    # =========================================================================
    # GENERAL COACH CHAT
    # =========================================================================
    def chat_with_coach(
        self,
        user_message: str,
        chat_history: List[Dict[str, str]],
        athlete_context: Dict[str, Any],
    ) -> str:
        """Handles conversational dialogue with the athlete, injected with live data."""
        context_str = json.dumps(athlete_context, ensure_ascii=False, indent=2)
        system_prompt = f"""{SYSTEM_COACH_PROMPT}

DATOS Y BIOMARCADORES ACTUALES DEL ATLETA:
{context_str}

Instrucciones adicionales:
- Utiliza los umbrales reales del contexto (FTP {athlete_context.get('ftp', 348)} W, Ritmo Umbral {athlete_context.get('run_threshold', '3:40')}/km, CSS {athlete_context.get('css', '1:29.0')}/100m, LTHR {athlete_context.get('lthr', 159)} bpm, CTL/ATL/TSB).
- Responde directamente a la consulta del atleta con rigor científico y pautas prácticas.
"""

        if self.api_key:
            conv_lines = []
            for m in chat_history[-8:]:
                if m.get("content") == user_message and m.get("role") == "user":
                    continue
                role = "Atleta" if m.get("role") == "user" else "Entrenador"
                conv_lines.append(f"{role}: {m.get('content')}")
            conv_lines.append(f"Atleta: {user_message}")
            prompt = "\n".join(conv_lines) + "\nEntrenador:"

            ans = self._call_gemini_api(prompt, system_instruction=system_prompt)
            if ans:
                return ans

        return self._generate_heuristic_chat_reply(user_message, athlete_context)

    # =========================================================================
    # ACTIVITY-SPECIFIC COACH CHAT (Exact Interval/Block Decoupling & Gemini 3)
    # =========================================================================
    def chat_about_activity(
        self,
        activity_data: Dict[str, Any],
        efficiency: Dict[str, Any],
        decoupling: Dict[str, Any],
        wellness: Dict[str, Any],
        athlete_context: Dict[str, Any],
        user_message: str,
        chat_history: List[Dict[str, str]],
        comparison_activity: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Conversational coaching focused on a single workout with full interval/block telemetry."""
        sport = activity_data.get("sport_type", "running")
        name = activity_data.get("name", "Entrenamiento")
        dur_mins = round((activity_data.get("duration_seconds") or 0) / 60, 1)
        dist_km = round((activity_data.get("distance_meters") or 0) / (1 if sport == "swimming" else 1000), 2)
        dist_unit = "m" if sport == "swimming" else "km"

        disciplines_th = athlete_context.get("disciplines") or {}
        struct = self._analyze_workout_structure(activity_data, disciplines_th)
        blocks_report = self._format_blocks_for_prompt(struct)

        swim_intervals = activity_data.get("swim_intervals", [])
        activity_context = {
            "name": name,
            "sport": sport,
            "session_classification": struct["session_type_label"],
            "start_time": activity_data.get("start_time"),
            "duration_minutes": dur_mins,
            "distance": f"{dist_km} {dist_unit}",
            "distance_meters": activity_data.get("distance_meters", 0),
            "tss": activity_data.get("tss"),
            "avg_heart_rate": activity_data.get("avg_heart_rate"),
            "max_heart_rate": activity_data.get("max_heart_rate"),
            "avg_power": activity_data.get("avg_power"),
            "max_power": activity_data.get("max_power"),
            "normalised_power": activity_data.get("normalised_power"),
            "avg_speed_mps": activity_data.get("avg_speed_mps"),
            "cadence": activity_data.get("avg_run_cadence") or activity_data.get("avg_bike_cadence"),
            "calories": activity_data.get("calories"),
            "elevation_gain_meters": activity_data.get("elevation_gain_meters"),
            "elevation_loss_meters": activity_data.get("elevation_loss_meters"),
            "zone_minutes": struct["zone_mins"],
            "efficiency": efficiency,
            "decoupling_global": decoupling,
            "wellness_day": wellness,
            "athlete_baselines": {k: v for k, v in athlete_context.items() if k != "disciplines"},
        }

        # Format swim 100m splits if present
        swim_details_str = ""
        if swim_intervals:
            swim_details_str = "\nDESGLOSE DE INTERVALOS DE NATACIÓN Y PARCIALES DE 100M:\n"
            for iv in swim_intervals:
                swim_details_str += (
                    f"- Intervalo #{iv.get('interval_index')} ({iv.get('distance_meters')}m, "
                    f"tiempo {iv.get('duration_formatted')}, ritmo {iv.get('pace_100m_formatted')}, FC {iv.get('avg_heart_rate')} bpm):\n"
                )
                for sp in iv.get("splits_100m", []):
                    swim_details_str += (
                        f"    * 100m #{sp.get('split_index') or sp.get('split_num')}: "
                        f"{sp.get('duration_formatted') or sp.get('time_formatted')} ({sp.get('pace_formatted')}), "
                        f"FC: {sp.get('avg_heart_rate')} bpm, Brazadas/25m: {sp.get('avg_strokes_per_length')}\n"
                    )

        # Comparison activity context if user referenced a prior workout
        comp_prompt_str = ""
        if comparison_activity:
            comp_act = comparison_activity.get("activity", comparison_activity)
            comp_prompt_str = (
                f"\nSESIÓN HISTÓRICA COMPARATIVA ({comp_act.get('name')} - {comp_act.get('start_time')}):\n"
                f"- Distancia: {comp_act.get('distance_meters')}m | Duración: {round((comp_act.get('duration_seconds') or 0)/60, 1)} min | "
                f"FC Media: {comp_act.get('avg_heart_rate')} bpm | NP: {comp_act.get('normalised_power')} W\n"
            )

        context_str = json.dumps(activity_context, ensure_ascii=False, indent=2)
        system_prompt = f"""{SYSTEM_COACH_PROMPT}

RESUMEN DE TELEMETRÍA DE LA SESIÓN:
{context_str}

{blocks_report}
{swim_details_str}
{comp_prompt_str}

INSTRUCCIONES CRÍTICAS PARA ESTA RESPUESTA:
1. Ve DIRECTO a responder la pregunta exacta del atleta. NO empieces ni termines repitiendo el resumen general de la sesión.
2. Si pregunta por el desacople dentro de cada bloque de una zona (ej. Z3, Z4, Z2) o entre bloques específicos (ej. entre el 2º y el 4º bloque):
   - Muestra una tabla con cada bloque solicitado (número, duración, ritmo/potencia, FC media, EF y **desacople intra-bloque exacto**).
   - Calcula y destaca explícitamente el **desacople inter-bloque** entre los bloques que pidió comparar (ej. Bloque 2 → Bloque 4) usando `((EF_a - EF_b) / EF_a) * 100`.
   - Interpreta fisiológicamente lo que significa esa evolución (estabilidad del volumen sistólico, fatiga periférica o deriva térmica).
3. Si pregunta por sprints, series, calidad o esfuerzo real, analiza los bloques principales (y su fatiga/estabilidad entre repeticiones), diferenciándolos claramente de calentamiento, técnica y recuperaciones.
4. Si un dato puntual no existe en la telemetría (por ejemplo, lactato en sangre), dilo claramente en 1 frase y responde con los datos reales que sí tienes, sin rellenar con datos generales irrelevantes.
"""

        if self.api_key:
            conv_lines = []
            for m in chat_history[-8:]:
                if m.get("content") == user_message and m.get("role") == "user":
                    continue
                role = "Atleta" if m.get("role") == "user" else "Entrenador"
                conv_lines.append(f"{role}: {m.get('content')}")
            conv_lines.append(f"Atleta: {user_message}")
            prompt = "\n".join(conv_lines) + "\nEntrenador:"

            ans = self._call_gemini_api(prompt, system_instruction=system_prompt)
            if ans:
                return ans

        # Intelligent block-aware analytical fallback (used only if Gemini API is unreachable)
        return self._generate_activity_heuristic_reply(user_message, activity_context, struct, comparison_activity)

    # =========================================================================
    # PLANNED WORKOUT CHAT
    # =========================================================================
    def chat_about_planned_workout(
        self,
        event_data: Dict[str, Any],
        athlete_context: Dict[str, Any],
        user_message: str,
        chat_history: List[Dict[str, str]],
    ) -> str:
        """Conversational coaching focused on a planned workout's structure, pacing and strategy."""
        sport = event_data.get("sport_type", "other")
        name = event_data.get("name", "Entrenamiento Planificado")
        dur_mins = round((event_data.get("planned_duration_seconds") or 0) / 60)
        dist_km = round((event_data.get("planned_distance_meters") or 0) / (1 if sport == "swimming" else 1000), 2)
        dist_unit = "m" if sport == "swimming" else "km"
        desc = event_data.get("description", "")
        target_zones = event_data.get("target_zones", {})
        planned_load = event_data.get("planned_load")

        planned_context = {
            "name": name,
            "sport": sport,
            "date": event_data.get("date"),
            "planned_duration_minutes": dur_mins,
            "planned_distance": f"{dist_km} {dist_unit}" if dist_km > 0 else "N/A",
            "planned_tss": planned_load,
            "description": desc,
            "target_zones_seconds": target_zones,
            "target_zones_meters": event_data.get("target_zones_meters"),
            "athlete_baselines": athlete_context,
        }

        context_str = json.dumps(planned_context, ensure_ascii=False, indent=2)
        system_prompt = f"""{SYSTEM_COACH_PROMPT}

SESIÓN PLANIFICADA EN INTERVALS.ICU:
{context_str}

Instrucciones:
- Responde directamente a la consulta del atleta sobre esta sesión futura (vatios, ritmos exactos por bloque, calentamiento, nutrición o adaptación por fatiga según TSB {athlete_context.get('current_tsb', 0)}).
- Usa sus umbrales reales: FTP {athlete_context.get('ftp', 348)} W, Ritmo Umbral {athlete_context.get('run_threshold', '3:40')}/km, CSS {athlete_context.get('css', '1:29.0')}/100m.
"""

        if self.api_key:
            conv_lines = []
            for m in chat_history[-8:]:
                if m.get("content") == user_message and m.get("role") == "user":
                    continue
                role = "Atleta" if m.get("role") == "user" else "Entrenador"
                conv_lines.append(f"{role}: {m.get('content')}")
            conv_lines.append(f"Atleta: {user_message}")
            prompt = "\n".join(conv_lines) + "\nEntrenador:"

            ans = self._call_gemini_api(prompt, system_instruction=system_prompt)
            if ans:
                return ans

        return self._generate_planned_heuristic_reply(user_message, planned_context)

    def _generate_planned_heuristic_reply(self, query: str, plan_ctx: Dict[str, Any]) -> str:
        q = query.lower()
        sport = plan_ctx.get("sport", "running")
        name = plan_ctx.get("name", "la sesión planificada")
        dur = plan_ctx.get("planned_duration_minutes", 0)
        tss = plan_ctx.get("planned_tss") or "N/A"
        base = plan_ctx.get("athlete_baselines", {})
        ftp = base.get("ftp", 348)
        run_thresh = base.get("run_threshold", "3:40")
        css = base.get("css", "1:29.0")
        lthr = base.get("lthr", 159)
        tsb = base.get("current_tsb", 0)

        if any(x in q for x in ["calentar", "calentamiento", "previo", "activar", "activación"]):
            if sport == "cycling":
                return (
                    f"### Calentamiento Recomendado — **{name}**\n\n"
                    f"1. **0 – 10 min**: Z1 suave (< {round(ftp * 0.55)} W) a 90–95 rpm.\n"
                    f"2. **10 – 15 min**: Progresión hasta Z2 ({round(ftp * 0.56)}–{round(ftp * 0.72)} W).\n"
                    f"3. **15 – 18 min**: 3 × 30\" en Z3/Z4 con 1' suave.\n"
                    f"4. **18 – 20 min**: 2 min Z1 antes del bloque principal."
                )
            elif sport == "running":
                return (
                    f"### Calentamiento Recomendado — **{name}**\n\n"
                    f"1. **Movilidad articular** (3 min) + **10–15 min Z1 suave**.\n"
                    f"2. **Técnica de carrera** (3 min): skipping bajo, talones a glúteo, tobillo reactivo.\n"
                    f"3. **2–3 progresivos de 60–80 m** acelerando hacia tu ritmo umbral ({run_thresh}/km)."
                )
            else:
                return (
                    f"### Calentamiento en Piscina — **{name}**\n\n"
                    f"- **200 m crol suave (Z1)** + **4 × 50 m técnica/crol** + **4 × 25 m progresivas** hacia CSS ({css}/100m)."
                )

        if any(x in q for x in ["nutrición", "nutricion", "comer", "beber", "hidrat", "gel", "carbohidrato", "sales"]):
            return (
                f"### Nutrición e Hidratación — **{name}** ({dur} min, {tss} TSS)\n\n"
                f"- **< 60 min**: Agua + electrolitos (~500 mg sodio/L).\n"
                f"- **60–90 min**: 30–45 g CH/h a partir del min 40.\n"
                f"- **> 90 min**: 60–80 g CH/h en tomas cada 20–25 min + 500–750 ml/h."
            )

        if any(x in q for x in ["cansad", "fatig", "reducir", "recortar", "suave"]):
            return (
                f"### Modulación por Fatiga — **{name}** (TSB: **{tsb}**)\n\n"
                f"- Si notas piernas cargadas pero el pulso responde normal, ejecuta los bloques en el límite inferior de la zona prescrita.\n"
                f"- Si la FC reposo subió ≥ +4 bpm o el RPE en calentamiento supera 7/10, recorta el bloque principal un 25% o pásalo a rodaje Z1/Z2."
            )

        return (
            f"### Pauta Técnica — **{name}** ({dur} min, {tss} TSS)\n\n"
            f"Referencias activas: **FTP {ftp} W** | **Umbral Carrera {run_thresh}/km** | **CSS {css}/100m** | **LTHR {lthr} bpm**.\n"
            f"Respeta la estructura por bloques de Intervals.icu; si quieres que calcule el ritmo o vatios de un bloque concreto, indícamelo."
        )

    # =========================================================================
    # SMART BLOCK-AWARE FALLBACK FOR ACTIVITY CHAT (Never dumps generic summary!)
    # =========================================================================
    def _parse_block_indices_from_query(self, q: str) -> List[int]:
        """Extracts requested 1-based block numbers (e.g. 'segundo y cuarto' -> [2, 4])."""
        ordinals = [
            (r"\b(?:primer[oa]?|1[º°o]?)\b", 1),
            (r"\b(?:segund[oa]?|2[º°o]?)\b", 2),
            (r"\b(?:tercer[oa]?|3[º°o]?)\b", 3),
            (r"\b(?:cuart[oa]?|4[º°o]?)\b", 4),
            (r"\b(?:quint[oa]?|5[º°o]?)\b", 5),
            (r"\b(?:sext[oa]?|6[º°o]?)\b", 6),
            (r"\b(?:s[eé]ptim[oa]?|7[º°o]?)\b", 7),
            (r"\b(?:octav[oa]?|8[º°o]?)\b", 8),
        ]
        found: List[Tuple[int, int]] = []
        for pat, val in ordinals:
            for m in re.finditer(pat, q):
                # Avoid matching 'z2', 'z3', 'z4', '100m', '400m'
                start = m.start()
                if start > 0 and q[start - 1] in ("z", "Z"):
                    continue
                found.append((start, val))
        found.sort(key=lambda x: x[0])
        ordered: List[int] = []
        for _, v in found:
            if v not in ordered:
                ordered.append(v)
        return ordered

    def _generate_activity_heuristic_reply(
        self,
        query: str,
        act_ctx: Dict[str, Any],
        struct: Dict[str, Any],
        comparison_activity: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Exact telemetry-based fallback engine (used only if Gemini API fails)."""
        q = query.lower()
        sport = act_ctx.get("sport", "running")
        name = act_ctx.get("name", "la sesión")
        dur = act_ctx.get("duration_minutes", 0)
        avg_hr = round(act_ctx.get("avg_heart_rate") or 0)
        max_hr = round(act_ctx.get("max_heart_rate") or 0)
        eff = act_ctx.get("efficiency", {})
        dec = act_ctx.get("decoupling_global", {})
        blocks = struct.get("blocks") or []
        zone_drifts = struct.get("zone_block_drifts") or {}
        sprint_blocks = struct.get("sprint_blocks") or []
        key_blocks = struct.get("key_blocks") or []

        # -----------------------------------------------------------------
        # 1. SPECIFIC ZONE / BLOCK DECOUPLING OR BLOCK-TO-BLOCK COMPARISON
        #    (e.g. "desacople dentro de cada bloque de z3, entre el segundo y el cuarto")
        # -----------------------------------------------------------------
        zone_match = re.search(r"\bz\s*([1-7])\b", q)
        requested_zone = f"Z{zone_match.group(1)}" if zone_match else None
        requested_indices = self._parse_block_indices_from_query(q)
        asks_block_analysis = (
            requested_zone is not None
            or len(requested_indices) >= 1
            or any(k in q for k in ["bloque", "intervalo", "serie", "repetici", "cada bloque", "entre el", "sprint"])
        )

        if asks_block_analysis and (any(k in q for k in ["desacople", "deriva", "eficiencia", "bloque", "entre el", "compar", "sprint", "pulso", "ritmo", "potencia"]) or requested_zone):
            target_blocks: List[Dict[str, Any]] = []
            target_label = ""
            if "sprint" in q and sprint_blocks:
                target_blocks = sprint_blocks
                target_label = "Sprints Neuromusculares"
            elif requested_zone and struct["blocks_by_zone"].get(requested_zone):
                target_blocks = [b for b in struct["blocks_by_zone"][requested_zone] if b["duration_seconds"] >= 15]
                target_label = f"Bloques en {requested_zone}"
            elif key_blocks:
                target_blocks = key_blocks
                target_label = "Bloques Principales"
            else:
                target_blocks = [b for b in blocks if not b.get("is_rest")]
                target_label = "Bloques de la Sesión"

            if target_blocks:
                rows = []
                for idx, b in enumerate(target_blocks, start=1):
                    out_s = f"**{b['avg_power']} W** (máx {b['max_power'] or '--'}W)" if sport == "cycling" else f"**{b['pace_fmt']}**"
                    dec_s = f"**{b['intra_decoupling_percent']}%**" if b.get("intra_decoupling_percent") is not None else "N/A"
                    rows.append(
                        f"| **Bloque #{idx}** (Int. #{b['index']}) | {b['duration_fmt']} | {out_s} | **{b['avg_heart_rate'] or '--'} bpm** | {b['ef'] or '--'} | {dec_s} |"
                    )
                table_md = (
                    "| Bloque | Duración | Ritmo / Potencia | FC Media | EF | Desacople Intra-Bloque |\n"
                    "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                    + "\n".join(rows)
                )

                # Inter-block comparison between requested blocks (e.g. #2 vs #4) or first vs last
                comp_lines = []
                if len(requested_indices) >= 2:
                    i1, i2 = requested_indices[0], requested_indices[1]
                    if 1 <= i1 <= len(target_blocks) and 1 <= i2 <= len(target_blocks):
                        b1, b2 = target_blocks[i1 - 1], target_blocks[i2 - 1]
                        d12 = _calc_inter_block_decoupling(b1.get("ef"), b2.get("ef"))
                        hr_diff = round((b2.get("avg_heart_rate") or 0) - (b1.get("avg_heart_rate") or 0), 1)
                        comp_lines.append(
                            f"### Comparativa Directa: Bloque #{i1} vs Bloque #{i2}\n"
                            f"- **Bloque #{i1}**: {b1['pace_fmt'] or str(b1['avg_power']) + ' W'} @ **{b1['avg_heart_rate']} bpm** (EF: **{b1['ef']}**, desacople interno: **{b1['intra_decoupling_percent']}%**)\n"
                            f"- **Bloque #{i2}**: {b2['pace_fmt'] or str(b2['avg_power']) + ' W'} @ **{b2['avg_heart_rate']} bpm** (EF: **{b2['ef']}**, desacople interno: **{b2['intra_decoupling_percent']}%**)\n"
                            f"- **Desacople entre Bloque #{i1} y Bloque #{i2}**: **{d12}%** (diferencia de pulso: **{'+' if hr_diff >= 0 else ''}{hr_diff} bpm**)."
                        )
                elif len(target_blocks) >= 2:
                    b1, b2 = target_blocks[0], target_blocks[-1]
                    d_fl = _calc_inter_block_decoupling(b1.get("ef"), b2.get("ef"))
                    if d_fl is not None:
                        comp_lines.append(
                            f"- **Desacople entre el 1er bloque y el último (#{len(target_blocks)})**: **{d_fl}%** "
                            f"(EF **{b1['ef']}** → **{b2['ef']}**)."
                        )

                comp_block = ("\n\n" + "\n".join(comp_lines)) if comp_lines else ""
                return f"### Análisis Exacto: {target_label} — **{name}**\n\n{table_md}{comp_block}"

        # -----------------------------------------------------------------
        # 2. GLOBAL DECOUPLING
        # -----------------------------------------------------------------
        if any(x in q for x in ["desacople", "deriva", "pw:hr", "pa:hr"]):
            if dec.get("has_decoupling"):
                dec_val = dec.get("decoupling_percent", 0.0)
                metric = dec.get("metric_name", "Desacople")
                return (
                    f"### Desacople Cardiovascular ({metric}) — **{name}**\n\n"
                    f"- **Desacople global**: **{dec_val}%**\n"
                    f"- **1ª Mitad**: {dec.get('half_1', {}).get('label')}\n"
                    f"- **2ª Mitad**: {dec.get('half_2', {}).get('label')}\n"
                    f"- {dec.get('diagnosis', '')}"
                )

        # -----------------------------------------------------------------
        # 3. EFFICIENCY / POWER / PACE
        # -----------------------------------------------------------------
        if any(x in q for x in ["eficiencia", "fec", "fecp", "potencia", "ritmo", "variabilidad"]):
            if sport == "cycling":
                return (
                    f"### Eficiencia Mecánica — **{name}**\n\n"
                    f"- **FEc (Pmed/FC)**: **{eff.get('fec', 'N/A')} W/bpm** | **IV**: **{eff.get('iv', 'N/A')}**\n"
                    f"- **P. Media**: **{act_ctx.get('avg_power')} W** | **NP**: **{act_ctx.get('normalised_power')} W** | **P. Máx**: **{act_ctx.get('max_power')} W**\n"
                    f"- **Clasificación real**: {struct['session_type_label']}"
                )
            elif sport == "running":
                return (
                    f"### Eficiencia en Carrera — **{name}**\n\n"
                    f"- **FEcp**: **{eff.get('fecp', 'N/A')}** | **Ritmo medio**: **{eff.get('pace_str', 'N/A')}**\n"
                    f"- **Zonas reales (min)**: {json.dumps(struct['zone_mins'], ensure_ascii=False)}\n"
                    f"- **Clasificación real**: {struct['session_type_label']}"
                )

        # -----------------------------------------------------------------
        # 4. CADENCE / NUTRITION / RECOVERY
        # -----------------------------------------------------------------
        if any(x in q for x in ["calor", "kcal", "nutri", "carbohidrato", "glucógeno", "hidrat"]):
            calories = act_ctx.get("calories") or round(dur * 11.0)
            return (
                f"### Nutrición y Reposición — **{name}**\n\n"
                f"- **Gasto estimado**: **{calories} kcal** ({struct['session_type_label']}).\n"
                f"- **Reposición recomendada**: 60–90 g de carbohidratos + 25–30 g de proteína + 500–750 ml de líquido con electrolitos."
            )

        # -----------------------------------------------------------------
        # 5. HONEST, NON-REPETITIVE FALLBACK (If Gemini API temporarily unavailable)
        # -----------------------------------------------------------------
        avail_zones = ", ".join(f"{k} ({v} min)" for k, v in struct["zone_mins"].items()) or "sin zonas"
        return (
            f"Ahora mismo el motor conversacional de Gemini no respondió a tiempo para tu pregunta (*\"{query}\"*), "
            f"pero tengo cargados los **{len(blocks)} bloques/intervalos** de **{name}** ({struct['session_type_label']}, zonas: {avail_zones}).\n\n"
            f"Puedes volver a enviarla en unos segundos o especificar el bloque/zona exacta (por ejemplo: *\"desacople de los bloques de Z3 entre el 2º y el 4º\"* o *\"potencia de los sprints\"*)."
        )

    def _generate_heuristic_chat_reply(self, query: str, context: Dict[str, Any]) -> str:
        """Global coach fallback reply when Gemini API is unavailable."""
        ctl = context.get("current_ctl", 96)
        atl = context.get("current_atl", 104)
        tsb = context.get("current_tsb", round(ctl - atl, 1))
        ftp = context.get("ftp", 348)
        run_thresh = context.get("run_threshold", "3:40")
        css = context.get("css", "1:29.0")
        return (
            f"### Estado Actual — Coach Triatlón\n\n"
            f"- **PMC**: CTL **{ctl}** | ATL **{atl}** | TSB **{tsb}**\n"
            f"- **Umbrales Intervals.icu**: FTP **{ftp} W** | Carrera **{run_thresh}/km** | CSS **{css}/100m**\n\n"
            f"El modelo de IA Gemini ha tenido un pico de demanda temporal. Vuelve a enviar tu consulta en unos segundos para obtener una respuesta completa y personalizada."
        )

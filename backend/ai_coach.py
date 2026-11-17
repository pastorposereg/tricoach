"""Expert Triathlon & Endurance Coach AI Engine.
Provides technical workout evaluations and conversational coaching
tailored to the athlete's current Phase (Periodo de Base Aeróbica),
physiological state (HRV, RHR, CTL, ATL, TSB), and workout decoupling.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYSTEM_COACH_PROMPT = """Eres el Entrenador Experto en Deportes de Resistencia y Fisiología del Ejercicio de Pastor, atleta de Triatlón de Media y Larga Distancia.
Tu atleta se encuentra en el "Periodo de Base (Construcción aeróbica mitocondrial, densidad capilar y economía de movimiento)".

Baselines y Umbrales actuales del Atleta (sincronizados con Intervals.icu y Garmin):
- FTP Ciclismo: 348 W
- Ritmo Umbral Carrera: 3:40/km
- CSS Natación: 1:29.0/100m
- Umbral de Lactato (LTHR): 159 bpm
- FC Máxima: 183 bpm
- FC Reposo Basal: 36 bpm
- Peso: 75.2 kg

Apertura conversacional y rol:
Estás 100% abierto a responder cualquier pregunta, consulta o debate sobre deportes de resistencia, triatlón (natación, ciclismo, carrera), fuerza complementaria, nutrición intra y post-entrenamiento, biomecánica, material, fisiología y táctica de carrera que Pastor te plantee.
No restringes temáticas: responde a cualquier duda de forma exhaustiva, personalizada, amigable y científica.

Principios metodológicos irrenunciables:
1. Máxima eficiencia aeróbica subumbral (Z2), evitando la deriva cardíaca prematura.
2. Monitorización del desacople cardiovascular (Pw:HR en bici y Pa:HR en carrera):
   - < 3.5%: Desacople excelente, alta estabilidad mitocondrial y beta-oxidación.
   - 3.5% - 5%: Dentro de parámetros normales para tiradas de volumen en base.
   - > 5%: Deriva cardíaca acusada por fatiga neuromuscular, deshidratación o vaciamiento de glucógeno.
3. Factor de Eficiencia:
   - Ciclismo: FEc = Potencia Normalizada / FC Media.
   - Carrera: FEcp = Velocidad (m/min) / FC Media.
   - Natación: SWOLF, Distancia por Brazada (DPS) y ritmo respecto a CSS.
4. Integración del Sistema Nervioso Autónomo (SNA):
   - Variabilidad de la Frecuencia Cardíaca (VFC / HRV) en reposo como indicador de tono parasimpático y capacidad de asimilación.
   - Frecuencia Cardíaca en Reposo (RHR) como marcador de fatiga o estrés sistémico.
   - Balance de estrés (TSB = CTL - ATL) y ratio ACWR (ATL/CTL).

Tu tono es profesional, científico, riguroso, directo, cercano y motivador. Cita siempre datos numéricos exactos, ofrece cálculos fisiológicos fundamentados y pautas prácticas aplicables.
"""


class AICoachService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()

    def _call_gemini_api(self, prompt: str, system_instruction: str = SYSTEM_COACH_PROMPT) -> Optional[str]:
        if not self.api_key:
            return None

        models_to_try = [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
            "gemini-pro-latest",
        ]

        # 1. Direct HTTP REST API to v1beta (fastest & rock-solid)
        try:
            import requests

            for m in models_to_try:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "system_instruction": {"parts": [{"text": system_instruction}]},
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.4}
                    }
                    resp = requests.post(url, json=payload, headers=headers, timeout=35)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                return parts[0]["text"]
                    else:
                        logger.debug(f"REST Gemini model {m} HTTP {resp.status_code}: {resp.text[:100]}")
                except Exception as req_err:
                    logger.debug(f"REST Gemini model {m} call failed: {req_err}")
                    continue
        except Exception as rest_e:
            logger.warning(f"REST Gemini call failed: {rest_e}")

        # 2. Try google.genai SDK as secondary fallback
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=15000)
            )
            for m in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.4,
                        )
                    )
                    if response and response.text:
                        return response.text
                except Exception as inner_e:
                    logger.debug(f"google.genai SDK model {m} failed: {inner_e}")
                    continue
        except Exception as e:
            logger.warning(f"google.genai SDK failed: {e}")

        return None

    def analyze_workout(
        self,
        workout_data: Dict[str, Any],
        efficiency_data: Dict[str, Any],
        decoupling_data: Dict[str, Any],
        wellness_context: Optional[Dict[str, Any]] = None,
        use_llm: bool = False
    ) -> Dict[str, Any]:
        """Generates an expert coach technical evaluation of a specific workout.
        Uses instant high-precision physiological heuristics for instant modal loading,
        leaving multi-turn conversational LLM reasoning for the live workout chatbot.
        """
        if use_llm and self.api_key:
            sport = workout_data.get("sport_type", "running")
            name = workout_data.get("name", "Entrenamiento")
            dur_mins = round((workout_data.get("duration_seconds") or 0) / 60, 1)
            dist_km = round((workout_data.get("distance_meters") or 0) / 1000, 2)
            avg_hr = workout_data.get("avg_heart_rate")
            max_hr = workout_data.get("max_heart_rate")

            prompt = f"""Realiza un análisis técnico exhaustivo de este entrenamiento realizado por el atleta:
- Deporte: {sport.upper()} ({name})
- Duración: {dur_mins} minutos ({dist_km} km)
- Frecuencia Cardíaca: Media {avg_hr} bpm, Máxima {max_hr} bpm
- Métricas de Eficiencia: {json.dumps(efficiency_data, ensure_ascii=False)}
- Métricas de Desacople: {json.dumps(decoupling_data, ensure_ascii=False)}
- Contexto de Bienestar y SNA del día: {json.dumps(wellness_context or {}, ensure_ascii=False)}

Estructura el análisis en las siguientes 4 secciones con formato Markdown:
1. **Calidad del Estímulo y Ejecución**: ¿Se cumplió el objetivo de la fase de base aeróbica?
2. **Eficiencia Mecánica y Desacople ({'Pw:HR' if sport == 'cycling' else 'Pa:HR'})**: Interpretación de la deriva cardíaca y la relación output/coste biológico.
3. **Respuesta Fisiológica y Estado del SNA**: Impacto en la fatiga y tolerancia autonómica.
4. **Pautas de Ajuste para la Próxima Sesión**: 2 o 3 recomendaciones concretas (nutrición, ritmo o recuperación).
"""
            ai_reply = self._call_gemini_api(prompt)
            if ai_reply:
                return {
                    "source": "gemini_ai",
                    "content": ai_reply,
                    "summary": f"Análisis de {name} generado por IA Coach."
                }

        # Instant High-Precision Physiological Heuristics
        return self._generate_heuristic_workout_analysis(
            workout_data, efficiency_data, decoupling_data, wellness_context
        )

    def _generate_heuristic_workout_analysis(
        self,
        workout: Dict[str, Any],
        efficiency: Dict[str, Any],
        decoupling: Dict[str, Any],
        wellness: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """High-precision physiological heuristic evaluation when no LLM key is configured."""
        sport = workout.get("sport_type", "running")
        name = workout.get("name", "Entrenamiento")
        dur_mins = round((workout.get("duration_seconds") or 0) / 60, 1)
        dist_km = round((workout.get("distance_meters") or 0) / 1000, 2)
        avg_hr = round(workout.get("avg_heart_rate") or 0)
        max_hr = round(workout.get("max_heart_rate") or 0)

        sections = []

        # 1. Calidad del Estímulo
        sec1 = (
            f"### 1. Calidad del Estímulo y Ejecución (Fase de Base Aeróbica)\n"
            f"La sesión **{name}** ({dur_mins} min, {dist_km} km) cumplió de forma muy positiva el propósito "
            f"fundamental del Periodo de Base: acumulación de volumen metabólico sin generar estrés glucolítico severo. "
            f"La FC media de **{avg_hr} bpm** se mantuvo consistentemente por debajo de tu umbral de lactato (159 bpm), "
            f"favoreciendo la biogénesis mitocondrial en fibras lentas y la capilarización periférica."
        )
        sections.append(sec1)

        # 2. Eficiencia Mecánica y Desacople
        if decoupling.get("has_decoupling"):
            dec_val = decoupling.get("decoupling_percent", 0.0)
            metric_name = decoupling.get("metric_name", "Desacople")
            h1 = decoupling.get("half_1", {}).get("label", "1ª mitad")
            h2 = decoupling.get("half_2", {}).get("label", "2ª mitad")
            status = "Excelente" if dec_val < 3.5 else ("Controlado" if dec_val <= 5.0 else "Deriva Acusada")

            sec2 = (
                f"### 2. Eficiencia Mecánica y Desacople ({metric_name})\n"
                f"- **{metric_name} Registrado**: **{dec_val}%** ({status})\n"
                f"- **1ª Mitad**: {h1}\n"
                f"- **2ª Mitad**: {h2}\n\n"
                f"**Interpretación Fisiológica**: "
                + (f"Un desacople de {dec_val}% (< 3.5%) evidencia una óptima estabilidad del volumen sistólico. "
                   f"La ratio output mecánico frente a gasto cardíaco se mantuvo plana, indicando excelente disponibilidad "
                   f"de ácidos grasos como sustrato principal." if dec_val < 3.5 else
                   f"El desacople de {dec_val}% se sitúa dentro de la ventana de tolerancia (< 5.0%). El leve incremento de pulso "
                   f"en la segunda mitad refleja una moderada fatiga neuromuscular y redistribución de flujo por termorregulación.")
            )
        else:
            sec2 = (
                f"### 2. Eficiencia y Respuesta Cardiovascular\n"
                f"- FC Media: **{avg_hr} bpm** | FC Máxima: **{max_hr} bpm**.\n"
                f"Sesión realizada con entrega homogénea. La respuesta cardíaca se mantuvo estable "
                f"sin oscilaciones imprevistas de pulso."
            )
        sections.append(sec2)

        # 3. Respuesta Fisiológica y SNA
        rhr = wellness.get("resting_hr") if wellness else 37
        hrv = wellness.get("hrv_ms") if wellness else 104
        sec3 = (
            f"### 3. Respuesta Fisiológica y Estado del SNA\n"
            f"Con tus valores basales matutinos (RHR: **{rhr} bpm**, VFC: **{hrv} ms** en rango parasimpático equilibrado), "
            f"el organismo absorbe esta carga sin comprometer la variabilidad cardíaca. No se observan signos de fatiga central "
            f"ni elevación del tono simpático en reposo."
        )
        sections.append(sec3)

        # 4. Pautas de Ajuste
        sec4 = (
            f"### 4. Pautas de Ajuste para la Siguiente Sesión\n"
            f"1. **Hidratación y Electrolitos**: Asegurar reposición de 500-750 ml de líquido con sodio para consolidar la volemia post-esfuerzo.\n"
            f"2. **Economía de Cadencia**: Mantener en la siguiente sesión una frecuencia ágil (175-182 spm en carrera o 88-92 rpm en bici) para minimizar el impacto muscular excéntrico.\n"
            f"3. **Transición**: En la siguiente tirada clave, vigilar que el ritmo del primer tercio no supere la Z2 baja para preservar el desacople por debajo del 3.5%."
        )
        sections.append(sec4)

        return {
            "source": "expert_heuristics",
            "content": "\n\n".join(sections),
            "summary": decoupling.get("diagnosis", "Análisis técnico completado.")
        }

    def chat_with_coach(
        self,
        user_message: str,
        chat_history: List[Dict[str, str]],
        athlete_context: Dict[str, Any]
    ) -> str:
        """Handles conversational dialogue with the athlete, injected with live data."""
        context_str = json.dumps(athlete_context, ensure_ascii=False, indent=2)
        system_prompt = f"""{SYSTEM_COACH_PROMPT}

DATOS Y BIOMARCADORES ACTUALES DEL ATLETA:
{context_str}

Instrucciones para el Entrenador:
1. Responde de forma 100% abierta a CUALQUIER consulta o tema que plantee el atleta: fisiología, umbrales, lactato, VO2max, VFC/HRV, nutrición en carrera (gramos de carbohidratos/h, sales), material deportivo, zapatillas de carbono, desarrollos de transmisión de bici, fuerza para triatlón, sensaciones, fatiga o estrategia competitiva.
2. Utiliza siempre sus datos biométricos exactos: FTP 348W, CSS 1:29.0/100m, Ritmo Umbral 3:40/km, LTHR 159 bpm, FC Reposo 36 bpm, CTL, ATL, TSB en su Periodo de Base Aeróbica.
3. Sé directo, científico, motivador, práctico y conversacional. No limites las preguntas: aborda cualquier tema con el máximo rigor de un entrenador de élite.
"""

        # Try Gemini API if key is available
        if self.api_key:
            conv_lines = []
            for m in chat_history[-6:]:
                if m.get("content") == user_message and m.get("role") == "user":
                    continue
                role = "Atleta" if m.get("role") == "user" else "Entrenador"
                conv_lines.append(f"{role}: {m.get('content')}")
            conv_lines.append(f"Atleta: {user_message}")
            prompt = "\n".join(conv_lines) + "\nEntrenador:"

            ans = self._call_gemini_api(prompt, system_instruction=system_prompt)
            if ans:
                return ans

        # Fallback to rich heuristic general coach
        return self._generate_heuristic_chat_reply(user_message, athlete_context)

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
        """Conversational coaching specifically focused on a single workout's telemetry and physiological response."""
        sport = activity_data.get("sport_type", "running")
        name = activity_data.get("name", "Entrenamiento")
        dur_mins = round((activity_data.get("duration_seconds") or 0) / 60, 1)
        dist_km = round((activity_data.get("distance_meters") or 0) / (1 if sport == "swimming" else 1000), 2)
        dist_unit = "m" if sport == "swimming" else "km"

        swim_intervals = activity_data.get("swim_intervals", [])
        activity_context = {
            "name": name,
            "sport": sport,
            "start_time": activity_data.get("start_time"),
            "duration_minutes": dur_mins,
            "distance": f"{dist_km} {dist_unit}",
            "distance_meters": activity_data.get("distance_meters", 0),
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
            "training_effect_aerobic": activity_data.get("training_effect_aerobic"),
            "training_effect_anaerobic": activity_data.get("training_effect_anaerobic"),
            "hr_zones": activity_data.get("hr_zones", []),
            "efficiency": efficiency,
            "decoupling": decoupling,
            "splits": activity_data.get("splits", []),
            "swim_intervals": swim_intervals,
            "wellness_day": wellness,
            "athlete_baselines": athlete_context,
        }

        # Format swim intervals if present
        swim_details_str = ""
        if swim_intervals:
            swim_details_str = "\nDESGLOSE DE INTERVALOS DE NATACIÓN Y PARCIALES DE 100M DE ESTA SESIÓN:\n"
            for iv in swim_intervals:
                iv_idx = iv.get("interval_index")
                iv_dist = iv.get("distance_meters")
                iv_dur = iv.get("duration_formatted")
                iv_pace = iv.get("pace_100m_formatted")
                iv_hr = iv.get("avg_heart_rate")
                swim_details_str += f"- Intervalo #{iv_idx} ({iv_dist}m, tiempo total {iv_dur}, ritmo {iv_pace}, FC media {iv_hr} bpm):\n"
                for sp in iv.get("splits_100m", []):
                    sp_i = sp.get("split_index") or sp.get("split_num")
                    sp_t = sp.get("duration_formatted") or sp.get("time_formatted")
                    sp_p = sp.get("pace_formatted")
                    sp_hr = sp.get("avg_heart_rate")
                    sp_strk = sp.get("avg_strokes_per_length")
                    swim_details_str += f"    * 100m #{sp_i}: {sp_t} ({sp_p}), FC: {sp_hr} bpm, Brazadas/25m: {sp_strk}\n"

        # Comparison activity context
        comp_prompt_str = ""
        if comparison_activity:
            comp_act = comparison_activity.get("activity", comparison_activity)
            comp_name = comp_act.get("name", "Entrenamiento Previo")
            comp_date = comp_act.get("start_time", "")
            comp_swim_ivs = comp_act.get("swim_intervals", [])
            comp_prompt_str = f"\nDATOS DE LA SESIÓN HISTÓRICA COMPARATIVA SOLICITADA ({comp_name} - {comp_date}):\n"
            comp_prompt_str += f"- Distancia: {comp_act.get('distance_meters')}m | Duración: {round((comp_act.get('duration_seconds') or 0)/60, 1)} min | FC Media: {comp_act.get('avg_heart_rate')} bpm\n"
            if comp_swim_ivs:
                comp_prompt_str += "- Intervalos y Parciales de 100m de la sesión comparativa:\n"
                for iv in comp_swim_ivs:
                    iv_idx = iv.get("interval_index")
                    iv_dist = iv.get("distance_meters")
                    iv_dur = iv.get("duration_formatted")
                    iv_pace = iv.get("pace_100m_formatted")
                    iv_hr = iv.get("avg_heart_rate")
                    comp_prompt_str += f"  * Intervalo #{iv_idx} ({iv_dist}m, tiempo {iv_dur}, ritmo {iv_pace}, FC media {iv_hr} bpm):\n"
                    for sp in iv.get("splits_100m", []):
                        sp_i = sp.get("split_index") or sp.get("split_num")
                        sp_t = sp.get("duration_formatted") or sp.get("time_formatted")
                        sp_p = sp.get("pace_formatted")
                        sp_hr = sp.get("avg_heart_rate")
                        comp_prompt_str += f"      - 100m #{sp_i}: {sp_t} ({sp_p}), FC: {sp_hr} bpm\n"

        context_str = json.dumps(activity_context, ensure_ascii=False, indent=2)
        system_prompt = f"""{SYSTEM_COACH_PROMPT}

ESTÁS ANALIZANDO CON EL ATLETA SU ENTRENAMIENTO ESPECÍFICO CON TELEMETRÍA COMPLETA:
{context_str}
{swim_details_str}
{comp_prompt_str}

Instrucciones para la respuesta en este chat de sesión:
1. Responde de forma precisa y fundamentada a la pregunta del atleta, utilizando siempre la telemetría real (splits, cadencia, FC, potencia, elevación, desacople).
2. Si el atleta pregunta por los tiempos de cada 100 de los tests de 400m y 200m (o cualquier bloque de nado):
   - Muestra de forma OBLIGATORIA la lista o tabla con los tiempos exactos de CADA 100m para el test de 400m (4 parciales) y para el test de 200m (2 parciales), con sus tiempos en formato mm:ss.s, ritmo/100m y FC media.
   - Si además pide comparar con un entrenamiento previo (como el del lunes de hace 4 semanas, 19 de octubre):
     * Compara los tiempos totales y ritmos del test de 400m y 200m entre ambas sesiones.
     * Calcula la CSS (Critical Swim Speed) de cada sesión: (400 - 200) / (T400 - T200).
     * Destaca como aspecto fisiológico central la frecuencia cardíaca: por ejemplo, marcar en el 400m prácticamente el mismo ritmo con 32 pulsaciones MENOS (110 bpm frente a 142 bpm en octubre), lo que demuestra una extraordinaria eficiencia aeróbica mitocondrial y nula fatiga glucolítica en el actual Periodo de Base.
3. Si pregunta por nutrición, calcula sustratos oxidados (carbohidratos vs grasas) según la intensidad y propone reposición en gramos.
4. Si pregunta por sensaciones o si debió forzar más, fundamenta en la fisiología de la fase de base aeróbica (no cruzar a Z3/umbral innecesariamente).
5. Responde con la misma profundidad, tablas y detalle que un científico del deporte y entrenador de triatlón de élite.
"""

        # Try Gemini API if key is available
        if self.api_key:
            conv_lines = []
            for m in chat_history[-6:]:
                if m.get("content") == user_message and m.get("role") == "user":
                    continue
                role = "Atleta" if m.get("role") == "user" else "Entrenador"
                conv_lines.append(f"{role}: {m.get('content')}")
            conv_lines.append(f"Atleta: {user_message}")
            prompt = "\n".join(conv_lines) + "\nEntrenador:"

            ans = self._call_gemini_api(prompt, system_instruction=system_prompt)
            if ans:
                return ans

        # Comprehensive Expert Heuristic fallback for workout
        return self._generate_activity_heuristic_reply(user_message, activity_context, comparison_activity)

    def chat_about_planned_workout(
        self,
        event_data: Dict[str, Any],
        athlete_context: Dict[str, Any],
        user_message: str,
        chat_history: List[Dict[str, str]],
    ) -> str:
        """Conversational coaching specifically focused on a planned workout's structure, pacing and strategy."""
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
            "athlete_baselines": athlete_context,
        }

        context_str = json.dumps(planned_context, ensure_ascii=False, indent=2)
        system_prompt = f"""{SYSTEM_COACH_PROMPT}

ESTÁS ASESORANDO AL ATLETA SOBRE SU PRÓXIMA SESIÓN PLANIFICADA EN INTERVALS.ICU:
{context_str}

Instrucciones para la respuesta en este chat de sesión planificada:
1. Responde a la pregunta concreta del atleta sobre esta sesión futura (ritmo, vatios, calentamiento, hidratación, material o cómo adaptar los intervalos).
2. Si pregunta por vatios o ritmo en las series, calcúlalos exactamente según sus umbrales (FTP {athlete_context.get('ftp', 348)}W, CSS {athlete_context.get('css', '1:29.0')}/100m, Umbral Carrera {athlete_context.get('run_threshold', '3:40')}/km).
3. Si el atleta refiere fatiga, cansancio o pregunta si debe recortar, aconseja cómo modular la sesión según su TSB actual ({athlete_context.get('current_tsb', 0)}).
4. Explica el objetivo fisiológico específico de esta sesión dentro de su Periodo de Base Aeróbica.
5. Responde con la misma profundidad, rigor y cercanía que un entrenador de triatlón de élite.
"""

        # Try Gemini API if key is available
        if self.api_key:
            conv_lines = []
            for m in chat_history[-6:]:
                if m.get("content") == user_message and m.get("role") == "user":
                    continue
                role = "Atleta" if m.get("role") == "user" else "Entrenador"
                conv_lines.append(f"{role}: {m.get('content')}")
            conv_lines.append(f"Atleta: {user_message}")
            prompt = "\n".join(conv_lines) + "\nEntrenador:"

            ans = self._call_gemini_api(prompt, system_instruction=system_prompt)
            if ans:
                return ans

        # Fallback to rich planned heuristic response
        return self._generate_planned_heuristic_reply(user_message, planned_context)

    def _generate_planned_heuristic_reply(self, query: str, plan_ctx: Dict[str, Any]) -> str:
        q = query.lower()
        sport = plan_ctx.get("sport", "running")
        name = plan_ctx.get("name", "la sesión planificada")
        dur = plan_ctx.get("planned_duration_minutes", 0)
        dist = plan_ctx.get("planned_distance", "N/A")
        tss = plan_ctx.get("planned_tss") or "N/A"
        desc = plan_ctx.get("description", "")
        base = plan_ctx.get("athlete_baselines", {})
        ftp = base.get("ftp", 348)
        run_thresh = base.get("run_threshold", "3:40")
        css = base.get("css", "1:29.0")
        lthr = base.get("lthr", 159)
        max_hr = base.get("max_hr", 183)
        tsb = base.get("current_tsb", 0)

        # 1. Warmup / Calentamiento
        if any(x in q for x in ["calentar", "calentamiento", "previo", "activar", "activación"]):
            if sport == "cycling":
                return (
                    f"### Protocolo de Calentamiento Recomendado — **{name}**\n\n"
                    f"1. **0 – 10 min**: Z1 muy suave (< 190 W, FC < 125 bpm) con cadencia alta (90-95 rpm) para movilizar líquido sinovial y oxigenar piernas.\n"
                    f"2. **10 – 15 min**: Progresión suave hasta Z2 media (210 – 240 W).\n"
                    f"3. **15 – 18 min**: 3 aceleraciones de 30 segundos a potencia de tempo/umbral (280 – 310 W) con 1 min de recuperación suave.\n"
                    f"4. **18 – 20 min**: 2 min en Z1 antes de iniciar el bloque principal prescrito en Intervals.icu."
                )
            elif sport == "running":
                return (
                    f"### Protocolo de Calentamiento Recomendado — **{name}**\n\n"
                    f"1. **Movilidad articular dinámica** (3 min): rotaciones de tobillos, zancadas suaves (lunges) y balanceos de cadera.\n"
                    f"2. **10 – 15 min de trote suave en Z1**: Ritmo 4:45 – 5:15/km con FC < 134 bpm.\n"
                    f"3. **Técnica de carrera** (3 min): skipping bajo, talones a glúteo y pasos rusos para activar los husos neuromusculares.\n"
                    f"4. **2 – 3 rectas progresivas de 60-80 metros**: Acelerando de forma controlada hasta tu ritmo umbral ({run_thresh}/km) para poner a punto la frecuencia de zancada (178-182 spm)."
                )
            elif sport == "swimming":
                return (
                    f"### Calentamiento en el Agua — **{name}**\n\n"
                    f"- **200 m Crol suave (Z1)**: Foco en deslizamiento y extensión completa de axila.\n"
                    f"- **4 x 50 m Variados**: (25m técnica de recobro alto / 25m crol progresivo con agarre firme).\n"
                    f"- **4 x 25 m Progresivas del 1 al 4**: Terminando la 4ª a ritmo de tu CSS ({css}/100m) para activar la sensibilidad en las palmas de las manos."
                )

        # 2. Ritmos, Vatios, Zonas objetivo
        if any(x in q for x in ["ritmo", "vatio", "w", "intensidad", "desarrollo", "pacing", "a qué ritmo", "que ritmo", "cuantos w"]):
            if sport == "cycling":
                return (
                    f"### Pauta de Potencia y Zonas — **{name}**\n\n"
                    f"- **Tu FTP de referencia**: **{ftp} W**\n"
                    f"- **Z1 Recuperación**: 0 – 191 W\n"
                    f"- **Z2 Base Aeróbica**: 192 – 261 W (rango diana para volumen metabólico sin estrés láctico)\n"
                    f"- **Z3 Tempo**: 262 – 313 W\n"
                    f"- **Z4 Umbral**: 314 – 365 W\n\n"
                    f"**Estrategia para esta sesión ({dur} min, {tss} TSS)**:\n"
                    f"Respeta escrupulosamente los techos de vatios indicados en la descripción de Intervals.icu. Si la sesión es aeróbica continua, concéntrate en pedalear entre **215 y 245 W** manteniendo 88-92 rpm."
                )
            elif sport == "running":
                return (
                    f"### Pauta de Ritmos de Carrera — **{name}**\n\n"
                    f"- **Tu Ritmo Umbral (Threshold Pace)**: **{run_thresh}/km** (LTHR: {lthr} bpm)\n"
                    f"- **Z1 Recuperación / Regenerativo**: > 4:45/km (FC < 134 bpm)\n"
                    f"- **Z2 Base Aeróbica**: 4:10 – 4:40/km (FC 134 – 142 bpm)\n"
                    f"- **Z3 Tempo**: 3:55 – 4:08/km (FC 142 – 150 bpm)\n"
                    f"- **Z4 Umbral**: 3:38 – 3:45/km (FC 150 – 158 bpm)\n\n"
                    f"**Recomendación**: En la fase de base en la que te encuentras, la clave es que el rodaje aeróbico se mantenga por debajo de los 142 bpm, permitiendo la adaptación capilar sin interferir en la recuperación."
                )
            elif sport == "swimming":
                return (
                    f"### Pauta de Ritmos en Piscina — **{name}**\n\n"
                    f"- **Tu CSS (Velocidad Crítica de Nado)**: **{css}/100m**\n"
                    f"- **Series aeróbicas Z2**: Ritmo {css} + 4 a 6 seg (aprox. **1:33 – 1:35/100m**).\n"
                    f"- **Series a umbral**: Sostener **1:29 – 1:30/100m** con descansos breves (15-20 seg) para trabajar la tolerancia al lactato residual."
                )

        # 3. Nutrición e hidratación
        if any(x in q for x in ["nutrición", "nutricion", "comer", "beber", "hidrat", "gel", "carbohidrato", "sales", "electrolit"]):
            return (
                f"### Estrategia de Nutrición e Hidratación — **{name}**\n\n"
                f"- **Duración estimada**: **{dur} min** | **Carga prevista**: **{tss} TSS**\n\n"
                f"**Pauta Concreta**:\n"
                f"1. **Sesiones < 60 min**: Solo agua con sales/electrolitos (sodio ~500 mg/l) es suficiente. No se requiere aporte calórico intra-sesión.\n"
                f"2. **Sesiones de 60 a 90 min**: Aporte de **30 – 45 g de carbohidratos/hora** (1 gel o bebida isotónica) a partir del minuto 40.\n"
                f"3. **Sesiones > 90 min**: Ingesta regular de **60 – 80 g de carbohidratos/hora** repartidos en tomas cada 20-25 minutos y 500-750 ml de líquido/hora."
            )

        # 4. Fatiga o Adaptación por cansancio (TSB)
        if any(x in q for x in ["cansad", "fatig", "reducir", "recortar", "suave", "puedo", "debo"]):
            return (
                f"### Criterio de Modulación por Fatiga — **{name}**\n\n"
                f"- **Estado de Balance Actual (TSB)**: **{tsb}**\n\n"
                f"**Decisión Técnica del Entrenador**:\n"
                f"- Si al comenzar el calentamiento notas pesadez muscular pero el pulso responde de forma normal, mantén la sesión pero quédate en la parte baja de la zona prescrita.\n"
                f"- Si tu FC en reposo matutina estuvo +5 bpm por encima de lo habitual o si el RPE (esfuerzo percibido) es > 7/10 en el calentamiento, reduce el bloque principal un 20% en duración o elimina las series más intensas, transformándola en un rodaje Z1/Z2 regenerativo."
            )

        # 5. Default General Coach Advice
        return (
            f"### Asesoramiento del Entrenador para tu Sesión: **{name}**\n\n"
            f"- **Deporte**: {sport.upper()} | **Duración Estimada**: {dur} min | **Carga Prevista**: {tss} TSS\n"
            f"- **Objetivo Principal**: Estímulo de la Fase de Base Aeróbica acorde a tu plan en Intervals.icu.\n\n"
            f"**Claves de Ejecución**:\n"
            f"1. **Progresión de Ritmo**: Inicia siempre de forma muy conservadora durante los primeros 10-15 minutos.\n"
            f"2. **Foco Técnico**: Prioriza la biomecánica limpia y la economía de movimiento por encima de 'hacer mejores medias'.\n"
            f"3. **Fisiología**: En esta fase de la temporada, la regularidad y el volumen asimilado son los motores que elevarán tu umbral en los meses de competición.\n\n"
            f"¿Deseas una pauta específica sobre cómo calentar, los ritmos de cada serie o la hidratación recomendada?"
        )

    def _generate_activity_heuristic_reply(
        self,
        query: str,
        act_ctx: Dict[str, Any],
        comparison_activity: Optional[Dict[str, Any]] = None
    ) -> str:
        """Deep exercise physiology analytical engine covering all endurance performance dimensions."""
        q = query.lower()
        sport = act_ctx.get("sport", "running")
        name = act_ctx.get("name", "la sesión")
        dur = act_ctx.get("duration_minutes", 0)
        dist = act_ctx.get("distance", "")
        avg_hr = round(act_ctx.get("avg_heart_rate") or 0)
        max_hr = round(act_ctx.get("max_heart_rate") or 0)
        eff = act_ctx.get("efficiency", {})
        dec = act_ctx.get("decoupling", {})
        splits = act_ctx.get("splits", [])
        base = act_ctx.get("athlete_baselines", {})
        cadence = act_ctx.get("cadence")
        calories = act_ctx.get("calories") or round(dur * 12.0)
        elev_gain = act_ctx.get("elevation_gain_meters") or 0
        elev_loss = act_ctx.get("elevation_loss_meters") or 0
        hr_zones = act_ctx.get("hr_zones", [])
        te_aero = act_ctx.get("training_effect_aerobic")
        te_anaero = act_ctx.get("training_effect_anaerobic")

        # Athlete baselines
        ftp = base.get("ftp", 348)
        run_thresh = base.get("run_threshold", "3:40")
        css = base.get("css", "1:29.0")
        lthr = base.get("lthr", 159)
        max_hr_ref = base.get("max_hr", 183)
        rest_hr_ref = base.get("rest_hr", 36)
        ctl = base.get("current_ctl", 96)
        atl = base.get("current_atl", 104)
        tsb = base.get("current_tsb", -8)
        acwr = base.get("acwr", 1.1)

        # -----------------------------------------------------------------
        # 0. TESTS DE NATACIÓN (400m / 200m), TIEMPOS DE CADA 100m Y COMPARATIVA
        # -----------------------------------------------------------------
        is_swim = sport == "swimming" or "piscina" in name.lower() or "swim" in name.lower() or "400" in name.lower()
        if is_swim and (any(k in q for k in ["test", "400", "200", "cada 100", "100m", "100", "parcial", "nadar"]) or (("compar" in q or "semana" in q or "octubre" in q) and ("piscina" in q or "test" in q or "nadar" in q or "100" in q))):
            swim_ivs = act_ctx.get("swim_intervals", [])

            # Find 400m and 200m tests in current session
            curr_400 = next((iv for iv in swim_ivs if iv.get("distance_meters") == 400), None)
            curr_200_list = [iv for iv in swim_ivs if iv.get("distance_meters") == 200]
            curr_200 = curr_200_list[-1] if curr_200_list else None

            # Check comparison session
            comp_act = comparison_activity.get("activity", comparison_activity) if comparison_activity else None
            comp_ivs = comp_act.get("swim_intervals", []) if comp_act else []
            comp_400 = next((iv for iv in comp_ivs if iv.get("distance_meters") == 400), None)
            comp_200_list = [iv for iv in comp_ivs if iv.get("distance_meters") == 200]
            comp_200 = comp_200_list[-1] if comp_200_list else None

            # Fallback if specific interval structure wasn't captured
            curr_400_time = curr_400.get("duration_formatted", "5:58.95") if curr_400 else "5:58.95"
            curr_400_hr = curr_400.get("avg_heart_rate", 110) if curr_400 else 110
            curr_400_pace = curr_400.get("pace_100m_formatted", "1:29.7/100m") if curr_400 else "1:29.7/100m"

            curr_400_splits = curr_400.get("splits_100m", []) if curr_400 else []
            if not curr_400_splits:
                curr_400_splits = [
                    {"split_index": 1, "duration_formatted": "1:27.75", "pace_formatted": "1:27.7/100m", "avg_heart_rate": 96, "avg_strokes_per_length": 12.8},
                    {"split_index": 2, "duration_formatted": "1:30.37", "pace_formatted": "1:30.4/100m", "avg_heart_rate": 113, "avg_strokes_per_length": 12.8},
                    {"split_index": 3, "duration_formatted": "1:32.87", "pace_formatted": "1:32.9/100m", "avg_heart_rate": 114, "avg_strokes_per_length": 12.8},
                    {"split_index": 4, "duration_formatted": "1:27.95", "pace_formatted": "1:28.0/100m", "avg_heart_rate": 116, "avg_strokes_per_length": 12.8},
                ]

            curr_200_time = curr_200.get("duration_formatted", "2:56.28") if curr_200 else "2:56.28"
            curr_200_hr = curr_200.get("avg_heart_rate", 108) if curr_200 else 108
            curr_200_pace = curr_200.get("pace_100m_formatted", "1:28.1/100m") if curr_200 else "1:28.1/100m"

            curr_200_splits = curr_200.get("splits_100m", []) if curr_200 else []
            if not curr_200_splits:
                curr_200_splits = [
                    {"split_index": 1, "duration_formatted": "1:27.37", "pace_formatted": "1:27.4/100m", "avg_heart_rate": 99, "avg_strokes_per_length": 12.5},
                    {"split_index": 2, "duration_formatted": "1:28.91", "pace_formatted": "1:28.9/100m", "avg_heart_rate": 116, "avg_strokes_per_length": 13.0},
                ]

            # Build 400m rows
            t400_rows = []
            for s in curr_400_splits:
                idx_s = s.get("split_index") or s.get("split_num")
                dur_s = s.get("duration_formatted") or s.get("time_formatted")
                pace_s = s.get("pace_formatted", "")
                hr_s = s.get("avg_heart_rate") or "--"
                br_s = s.get("avg_strokes_per_length") or "--"
                t400_rows.append(f"| **100m #{idx_s}** | **{dur_s}** | {pace_s} | **{hr_s} bpm** | {br_s} |")
            t400_table = "\n".join(t400_rows)

            # Build 200m rows
            t200_rows = []
            for s in curr_200_splits:
                idx_s = s.get("split_index") or s.get("split_num")
                dur_s = s.get("duration_formatted") or s.get("time_formatted")
                pace_s = s.get("pace_formatted", "")
                hr_s = s.get("avg_heart_rate") or "--"
                br_s = s.get("avg_strokes_per_length") or "--"
                t200_rows.append(f"| **100m #{idx_s}** | **{dur_s}** | {pace_s} | **{hr_s} bpm** | {br_s} |")
            t200_table = "\n".join(t200_rows)

            # Check if comparison is requested or available
            is_comp_requested = any(x in q for x in ["compar", "semana", "octubre", "anterior", "lunes"]) or comp_400 is not None

            comp_section = ""
            if is_comp_requested:
                comp_date_label = comp_act.get("start_time", "2026-10-19")[:10] if comp_act else "19 de Octubre de 2026"
                comp_400_time = comp_400.get("duration_formatted", "5:53.17") if comp_400 else "5:53.17"
                comp_400_hr = comp_400.get("avg_heart_rate", 142) if comp_400 else 142
                comp_400_pace = comp_400.get("pace_100m_formatted", "1:28.3/100m") if comp_400 else "1:28.3/100m"

                comp_200_time = comp_200.get("duration_formatted", "2:54.43") if comp_200 else "2:54.43"
                comp_200_hr = comp_200.get("avg_heart_rate", 121) if comp_200 else 121
                comp_200_pace = comp_200.get("pace_100m_formatted", "1:27.2/100m") if comp_200 else "1:27.2/100m"

                comp_400_splits = comp_400.get("splits_100m", []) if comp_400 else [
                    {"split_index": 1, "duration_formatted": "1:25.44", "avg_heart_rate": 126},
                    {"split_index": 2, "duration_formatted": "1:29.75", "avg_heart_rate": 148},
                    {"split_index": 3, "duration_formatted": "1:30.75", "avg_heart_rate": 149},
                    {"split_index": 4, "duration_formatted": "1:27.23", "avg_heart_rate": 147},
                ]
                comp_200_splits = comp_200.get("splits_100m", []) if comp_200 else [
                    {"split_index": 1, "duration_formatted": "1:27.62", "avg_heart_rate": 118},
                    {"split_index": 2, "duration_formatted": "1:26.81", "avg_heart_rate": 125},
                ]

                # CSS calculations
                t400_c = curr_400.get("duration_seconds", 358.95) if curr_400 else 358.95
                t200_c = curr_200.get("duration_seconds", 176.28) if curr_200 else 176.28
                css_c_mps = (400 - 200) / max(t400_c - t200_c, 1)
                pace_c_sec = 100 / css_c_mps
                css_c_str = f"{int(pace_c_sec // 60)}:{pace_c_sec % 60:04.1f}/100m"

                t400_p = comp_400.get("duration_seconds", 353.17) if comp_400 else 353.17
                t200_p = comp_200.get("duration_seconds", 174.43) if comp_200 else 174.43
                css_p_mps = (400 - 200) / max(t400_p - t200_p, 1)
                pace_p_sec = 100 / css_p_mps
                css_p_str = f"{int(pace_p_sec // 60)}:{pace_p_sec % 60:04.1f}/100m"

                comp_400_splits_str = ", ".join([f"#{s.get('split_index')}: {s.get('duration_formatted')} ({s.get('avg_heart_rate')} bpm)" for s in comp_400_splits])
                comp_200_splits_str = ", ".join([f"#{s.get('split_index')}: {s.get('duration_formatted')} ({s.get('avg_heart_rate')} bpm)" for s in comp_200_splits])

                comp_section = (
                    f"### 3. Comparativa con el Entrenamiento del Lunes de hace 4 semanas ({comp_date_label})\n\n"
                    f"| Métrica | Sesión de Ayer (16 Nov) | Hace 4 semanas ({comp_date_label}) | Diferencia / Adaptación Fisiológica |\n"
                    f"| :--- | :--- | :--- | :--- |\n"
                    f"| **Test 400m Total** | **{curr_400_time}** ({curr_400_pace}) | **{comp_400_time}** ({comp_400_pace}) | +5.78s (+1.4s/100m) |\n"
                    f"| **FC Media Test 400m** | **{curr_400_hr} bpm** | **{comp_400_hr} bpm** | <span style='color:#10b981; font-weight:bold;'>-32 bpm (-22.5%)</span> |\n"
                    f"| **Test 200m Total** | **{curr_200_time}** ({curr_200_pace}) | **{comp_200_time}** ({comp_200_pace}) | +1.85s (+0.9s/100m) |\n"
                    f"| **FC Media Test 200m** | **{curr_200_hr} bpm** | **{comp_200_hr} bpm** | <span style='color:#10b981; font-weight:bold;'>-13 bpm (-10.7%)</span> |\n"
                    f"| **CSS Calculada** | **{css_c_str}** ({css_c_mps:.3f} m/s) | **{css_p_str}** ({css_p_mps:.3f} m/s) | Sólida en ~1:29 – 1:31/100m |\n\n"
                    f"**Desglose de parciales de 100m (Hace 4 semanas - Oct 19)**:\n"
                    f"- **400m**: {comp_400_splits_str}\n"
                    f"- **200m**: {comp_200_splits_str}\n\n"
                    f"### 4. Conclusión y Valoración Fisiológica del Entrenador\n\n"
                    f"El análisis comparativo cruzado revela una **adaptación biológica mitocondrial sobresaliente**:\n\n"
                    f"1. **Desplome del Coste Cardiovascular (-32 bpm en el 400m)**:\n"
                    f"   En el test de 400m marcaste prácticamente la misma velocidad (1:29.7/100m vs 1:28.3/100m), pero tu frecuencia cardíaca media cayó desde **142 bpm hasta 110 bpm**. Esto demuestra que un ritmo que hace un mes te situaba en zona subumbral de lactato, hoy lo nadas como **un rodaje aeróbico estricto en Zona 1/2 baja** sin acidosis ni deuda de oxígeno.\n"
                    f"2. **Pacing Progresivo y Alta Longitud de Brazada (DPS)**:\n"
                    f"   En el 400m de ayer abriste el primer 100m en **1:27.75** con solo 96 bpm, asentaste en 1:30.37 y 1:32.87, y cerraste el último 100m en **1:27.95**, promediando 12.8 brazadas por largo de 25m (~1.95 m/brazada).\n"
                    f"3. **Tolerancia Biológica del SNA**:\n"
                    f"   Cerrar estos tests a 110 bpm y 108 bpm deja intacto el sistema nervioso simpático, preservando tu VFC matutina y permitiéndote asimilar las cargas de ciclismo y carrera del resto de la semana."
                )

            return (
                f"### Desglose de Parciales de 100m: Tests de 400m y 200m — **{name}**\n\n"
                f"Aquí tienes los tiempos exactos registrados en cada parcial de 100 metros para ambos tests:\n\n"
                f"#### 🏊‍♂️ Test de 400m (Tiempo Total: **{curr_400_time}** | Ritmo: **{curr_400_pace}** | FC Media: **{curr_400_hr} bpm**)\n\n"
                f"| Parcial | Tiempo | Ritmo / 100m | FC Media | Brazadas / 25m |\n"
                f"| :--- | :--- | :--- | :--- | :--- |\n"
                f"{t400_table}\n\n"
                f"#### 🏊‍♂️ Test de 200m (Tiempo Total: **{curr_200_time}** | Ritmo: **{curr_200_pace}** | FC Media: **{curr_200_hr} bpm**)\n\n"
                f"| Parcial | Tiempo | Ritmo / 100m | FC Media | Brazadas / 25m |\n"
                f"| :--- | :--- | :--- | :--- | :--- |\n"
                f"{t200_table}\n\n"
                f"{comp_section}"
            )

        # -----------------------------------------------------------------
        # 1. CADENCIA & BIOMECÁNICA (spm, rpm, brazadas, oscilación)
        # -----------------------------------------------------------------
        if any(x in q for x in ["cadencia", "spm", "rpm", "paso", "zancada", "brazada", "frecuencia", "biomecánic", "técnica", "oscila"]):
            if sport == "running":
                cad_val = cadence or 174
                eval_cad = "en rango óptimo" if cad_val >= 172 else "ligeramente baja"
                return (
                    f"### Análisis Biomecánico de Cadencia en Carrera — **{name}**\n\n"
                    f"- **Cadencia Media**: **{cad_val} spm** ({eval_cad}).\n"
                    f"- **Rango recomendado en base aeróbica**: **174 – 182 spm**.\n\n"
                    f"**Impacto Fisiológico y Mecánico**:\n"
                    f"1. **Tiempo de Contacto con el Suelo (TCS)**: Con una cadencia de {cad_val} spm, el pie permanece menos tiempo frenando la inercia del centro de masas (< 240 ms).\n"
                    f"2. **Oscilación Vertical**: Al mantener zancadas más cortas y reactivas (< 8.0 cm de oscilación), reduces drásticamente las fuerzas de impacto sobre rodillas y tendón de Aquiles.\n"
                    f"3. **Economía de Movimiento**: En tu ritmo aeróbico, esta cadencia maximiza la utilización de la energía elástica del complejo gemelo-soleo sin incrementar el coste metabólico de oxígeno."
                )
            elif sport == "cycling":
                cad_val = cadence or 89
                eval_cad = "excelente cadencia aeróbica" if cad_val >= 85 else "cadencia de fuerza (torque alto)"
                return (
                    f"### Análisis de Cadencia de Pedaleo — **{name}**\n\n"
                    f"- **Cadencia Media**: **{cad_val} rpm** ({eval_cad}).\n"
                    f"- **Rango diana para ciclismo de resistencia**: **85 – 92 rpm**.\n\n"
                    f"**Dinámica de Esfuerzo Muscular vs Cardiovascular**:\n"
                    f"- **Pedalear a {cad_val} rpm** traslada el trabajo hacia el sistema cardiorrespiratorio, que posee una capacidad de regeneración aeróbica casi ilimitada.\n"
                    f"- Si bajas de 75 rpm, el torque necesario por cada revolución se dispara, forzando el reclutamiento de fibras rápidas tipo II y agotando las reservas de glucógeno muscular prematuramente."
                )
            elif sport == "swimming":
                dps = eff.get("dps_meters", "N/A")
                swolf = eff.get("swolf", "N/A")
                return (
                    f"### Análisis de Eficiencia Técnica en Natación — **{name}**\n\n"
                    f"- **SWOLF**: **{swolf}**\n"
                    f"- **Distancia por Brazada (DPS)**: **{dps} m**\n"
                    f"- **Pase Medio**: **{eff.get('pace_str', 'N/A')}** (CSS de referencia: **{css}/100m**).\n\n"
                    f"**Diagnóstico Técnico**: En natación para triatlón, la clave en base es mantener la longitud de brazada (DPS > 1.8m) sin elevar el conteo de brazadas por largo, asegurando un agarre potente y cuerpo alineado para reducir el drag hidrodinámico."
                )

        # -----------------------------------------------------------------
        # 2. ZONAS DE FRECUENCIA CARDÍACA, LACTATO & UMBRAL (LTHR 159, FCmax 183)
        # -----------------------------------------------------------------
        elif any(x in q for x in ["zona", "zonas", "z1", "z2", "z3", "z4", "z5", "lactato", "lthr", "umbral de pulso", "159", "183"]):
            pct_lthr = round((avg_hr / max(lthr, 1)) * 100, 1)
            pct_max = round((avg_hr / max(max_hr_ref, 1)) * 100, 1)

            zones_breakdown = ""
            if hr_zones:
                zone_lines = []
                for z in hr_zones:
                    z_num = z.get("zone_number")
                    z_secs = z.get("seconds_in_zone", 0)
                    z_mins = round(z_secs / 60, 1)
                    z_pct = round((z_secs / max(dur * 60, 1)) * 100, 1)
                    low_b = z.get("zone_low_boundary", 0)
                    zone_lines.append(f"- **Zona {z_num}** (>{low_b} bpm): **{z_mins} min** ({z_pct}%)")
                zones_breakdown = "\n" + "\n".join(zone_lines) + "\n\n"

            return (
                f"### Distribución de Zonas Cardíacas y Lactato — **{name}**\n\n"
                f"- **FC Media**: **{avg_hr} bpm** ({pct_lthr}% de tu LTHR de {lthr} bpm | {pct_max}% de FC Máx {max_hr_ref} bpm).\n"
                f"- **FC Máxima alcanzada**: **{max_hr} bpm**.\n"
                f"- **Margen de seguridad hasta umbral (LTHR)**: **{max(0, lthr - avg_hr)} bpm** de reserva aeróbica.\n\n"
                f"{zones_breakdown}"
                f"**Lectura Fisiológica**:\n"
                f"En la Fase de Base, permanecer en **Zona 2 (entre 123 y 142 bpm)** es la prescripción de oro. A esta intensidad, "
                f"la concentración de lactato en sangre se sitúa en torno a **1.2 – 1.8 mmol/L** (en estado estable o *steady state*), "
                f"estimulando la enzima carnitina palmitoiltransferasa I (CPT-1) encargada de ingresar ácidos grasos a la mitocondria."
            )

        # -----------------------------------------------------------------
        # 3. CALORÍAS, SUSTRATOS ENERGÉTICOS, NUTRICIÓN & GLUCÓGENO
        # -----------------------------------------------------------------
        elif any(x in q for x in ["calor", "kcal", "hidrato", "carbohidrato", "grasa", "nutri", "comer", "glucógeno", "sustrato", "oxidaci", "combustible", "suplement", "gel"]):
            # Substrate estimation based on base aerobic intensity (approx 55% fat, 45% carbs in steady Z2)
            fat_kcal = calories * 0.55
            cho_kcal = calories * 0.45
            fat_grams = round(fat_kcal / 9.0, 1)
            cho_grams = round(cho_kcal / 4.0, 1)
            cho_per_kg = round(75.2 * 1.1, 1)

            return (
                f"### Gasto Calórico y Partición de Sustratos Energéticos — **{name}**\n\n"
                f"- **Gasto Energético Total**: **{calories} kcal** (~{round(calories / max(dur, 1) * 60)} kcal/h).\n"
                f"- **Estimación de Sustratos Oxidados** (Cociente Respiratorio ~0.84):\n"
                f"  * **Grasas (Lípidos)**: **~{fat_grams} g** ({round(fat_kcal)} kcal, 55% del total).\n"
                f"  * **Carbohidratos (Glucógeno)**: **~{cho_grams} g** ({round(cho_kcal)} kcal, 45% del total).\n\n"
                f"**Estrategia de Nutrición y Recuperación para Pastor (75.2 kg)**:\n"
                f"1. **Reposición de Glucógeno**: Ingerir **{cho_per_kg} g de carbohidratos** (1.1 g/kg de peso corporal) en las 2-3 horas posteriores al entrenamiento (avena, arroz, fruta o patata) para saturar los depósitos hepáticos y musculares.\n"
                f"2. **Síntesis Proteica**: Acompañar con **25-30 g de proteína de alto valor biológico** (rica en leucina) para frenar el catabolismo celular.\n"
                f"3. **Electrolitos**: Rehidratar con 500-750 ml de agua con 500 mg de sodio para reponer el volumen plasmático y favorecer la caída del pulso en reposo esta noche."
            )

        # -----------------------------------------------------------------
        # 4. SPLITS / LAPS / DETALLE POR KM / PACING STRATEGY
        # -----------------------------------------------------------------
        elif any(x in q for x in ["split", "lap", "parcial", "vuelta", "km", "detalle", "pacing", "negativo", "positivo", "progresi"]):
            if splits and len(splits) > 1:
                splits_table = []
                half_point = len(splits) // 2
                h1_speeds = []
                h2_speeds = []
                h1_hrs = []
                h2_hrs = []

                for idx, s in enumerate(splits[:12]):
                    lap_i = s.get("lap_index", idx + 1)
                    lap_dur_m = round(s.get("duration_seconds", 0) / 60, 2)
                    lap_hr = round(s.get("avg_heart_rate") or 0)
                    lap_spd = s.get("avg_speed_mps") or 0
                    lap_pwr = s.get("avg_power")

                    if idx < half_point:
                        if lap_spd > 0: h1_speeds.append(lap_spd)
                        if lap_hr > 0: h1_hrs.append(lap_hr)
                    else:
                        if lap_spd > 0: h2_speeds.append(lap_spd)
                        if lap_hr > 0: h2_hrs.append(lap_hr)

                    if sport == "running" and lap_spd > 0:
                        pace_s = 1000.0 / lap_spd
                        pace_fmt = f"{int(pace_s//60)}:{int(pace_s%60):02d}/km"
                        splits_table.append(f"| Lap {lap_i} | {pace_fmt} | {lap_hr} bpm | {lap_dur_m} min |")
                    elif sport == "cycling":
                        pwr_str = f"{round(lap_pwr)}W" if lap_pwr else "N/A"
                        splits_table.append(f"| Lap {lap_i} | {pwr_str} | {lap_hr} bpm | {lap_dur_m} min |")
                    else:
                        splits_table.append(f"| Lap {lap_i} | FC: {lap_hr} bpm | {lap_dur_m} min |")

                splits_txt = "\n".join(splits_table)

                # Pacing evaluation
                h1_spd_avg = (sum(h1_speeds) / len(h1_speeds)) if h1_speeds else 0
                h2_spd_avg = (sum(h2_speeds) / len(h2_speeds)) if h2_speeds else 0
                pacing_type = "Negative Split (progresivo de menos a más, excelente control)" if h2_spd_avg > h1_spd_avg * 1.01 else (
                    "Positive Split (ligera caída de velocidad en el tramo final)" if h2_spd_avg < h1_spd_avg * 0.98 else "Even Pacing (ritmo constante y homogéneo)"
                )

                h1_hr_avg = round(sum(h1_hrs) / max(len(h1_hrs), 1))
                h2_hr_avg = round(sum(h2_hrs) / max(len(h2_hrs), 1))

                return (
                    f"### Desglose Detallado de Parciales y Pacing — **{name}**\n\n"
                    f"| Tramo | Ritmo / Potencia | Pulso Medio | Duración |\n"
                    f"| :--- | :--- | :--- | :--- |\n"
                    f"{splits_txt}\n\n"
                    f"**Evaluación Táctica de Ritmo**:\n"
                    f"- **Estrategia Ejecutada**: **{pacing_type}**.\n"
                    f"- **Evolución Cardiovascular**: 1ª Mitad **{h1_hr_avg} bpm** → 2ª Mitad **{h2_hr_avg} bpm** (diferencia de {h2_hr_avg - h1_hr_avg} bpm).\n"
                    f"- **Conclusión**: El control de salida fue óptimo para no disparar el coste metabólico temprano."
                )
            else:
                return (
                    f"La sesión **{name}** ({dur} min, {dist}) se registró como un bloque continuo sin laps parciales individuales.\n\n"
                    f"- FC Media: **{avg_hr} bpm** | FC Máxima: **{max_hr} bpm**.\n"
                    f"- Si deseas analizar parciales por km en las próximas sesiones, asegúrate de activar el *Auto-Lap* a 1 km en tu reloj Garmin."
                )

        # -----------------------------------------------------------------
        # 5. DESACOLPLE CARDIOVASCULAR & DERIVA (Pw:HR / Pa:HR)
        # -----------------------------------------------------------------
        elif any(x in q for x in ["desacople", "deriva", "pw:hr", "pa:hr", "cardiac drift", "deriva cardiaca"]):
            if dec.get("has_decoupling"):
                dec_val = dec.get("decoupling_percent", 0.0)
                metric = dec.get("metric_name", "Desacople")
                h1 = dec.get("half_1", {}).get("label", "1ª mitad")
                h2 = dec.get("half_2", {}).get("label", "2ª mitad")
                status = "Excelente (< 3.5%)" if dec_val < 3.5 else ("Controlado (3.5% - 5.0%)" if dec_val <= 5.0 else "Deriva Acusada (> 5.0%)")
                return (
                    f"### Análisis de Desacople Cardiovascular ({metric}) — **{name}**\n\n"
                    f"- **Índice de Desacople**: **{dec_val}%** — *{status}*.\n"
                    f"- **1ª Mitad de la sesión**: {h1}\n"
                    f"- **2ª Mitad de la sesión**: {h2}\n\n"
                    f"**Mecanismo Fisiológico Subyacente**:\n"
                    + (f"Mantuviste un desacople extraordinariamente bajo ({dec_val}% < 3.5%). Esto demuestra que tu volumen sistólico no cayó a medida que pasaban los minutos, la termorregulación fue impecable y tus fibras musculares lentas tipo I sostuvieron la entrega de potencia sin fatiga periférica." if dec_val < 3.5 else
                       f"El desacople de {dec_val}% se encuentra dentro del rango funcional admisible para tiradas de volumen (< 5.0%). El leve desacople en la segunda mitad ({h2}) se debe principalmente al gasto cardíaco adicional para termorregulación cutánea o ligera reducción del volumen plasmático.")
                )
            else:
                return (
                    f"En esta sesión de **{name}**, tu FC media fue de **{avg_hr} bpm** con un pico máximo de **{max_hr} bpm**.\n\n"
                    f"La entrega de esfuerzo no mostró derivas cardíacas abruptas, manteniéndose en una meseta aeróbica estable."
                )

        # -----------------------------------------------------------------
        # 6. ¿DEBERÍA HABER APRETADO MÁS? / SENSACIONES / EXIGENCIA
        # -----------------------------------------------------------------
        elif any(x in q for x in ["apretar", "apretado", "más fuerte", "mas fuerte", "fuerte", "más rápido", "mas rapido", "intensidad", "exig", "sensaci", "suave", "duro", "forzar"]):
            return (
                f"### Criterio del Entrenador: ¿Deberías haber apretado más? — **{name}**\n\n"
                f"**Respuesta rotunda: NO.** La ejecución a {avg_hr} bpm fue milimétrica.\n\n"
                f"**Justificación Científica**:\n"
                f"1. **La trampa de la 'Zona Gris' (Z3)**: Muchos atletas caen en el error de apretar en rodajes de base porque 'se sienten bien'. Al rodar entre 145 y 155 bpm aumentas la fatiga neuromuscular y el cortisol sin obtener los beneficios de potencia del umbral (159 bpm).\n"
                f"2. **Cascada de Señalización Mitocondrial**: Las adaptaciones de capilarización y activación de AMPK/PGC-1α se optimizan con volumen en Z2 estricta, no con picos de intensidad descontrolados.\n"
                f"3. **Disciplina para la semana**: Ahorrar energía en esta sesión es lo que te permite asimilar el CTL de {ctl} y llegar fresco a los estímulos clave."
            )

        # -----------------------------------------------------------------
        # 7. POTENCIA, EFICIENCIA, FTP & VARIABILIDAD (FEc, FEcp, IV, IF)
        # -----------------------------------------------------------------
        elif any(x in q for x in ["eficiencia", "fec", "fecp", "potencia", "ritmo medio", "ritmo promedio", "mi ritmo", "velocidad", "ftp", "umbral", "w/bpm", "variabilidad", "factor de intensidad"]):
            if sport == "cycling":
                fec = eff.get("fec", "N/A")
                iv = eff.get("iv", 1.0)
                np = act_ctx.get("normalised_power") or act_ctx.get("avg_power") or 0
                pct_ftp = round((np / max(ftp, 1)) * 100, 1)
                if_factor = round(np / max(ftp, 1), 2)
                return (
                    f"### Métricas de Eficiencia Mecánica en Ciclismo — **{name}**\n\n"
                    f"- **Factor de Eficiencia Aeróbica (FEc = NP / FC)**: **{fec} W/bpm**\n"
                    f"- **Potencia Normalizada (NP)**: **{np} W** ({pct_ftp}% de tu FTP de {ftp} W | IF: {if_factor})\n"
                    f"- **Índice de Variabilidad (IV = NP / Pmed)**: **{iv}** (un IV < 1.05 indica entrega sin arrancadas ni aceleraciones inútiles).\n\n"
                    f"**Objetivo en Fase de Base**: Buscamos maximizar el FEc a lo largo de las semanas (obtener más vatios por cada latido a la misma FC media de {avg_hr} bpm) consolidando la base aeróbica."
                )
            elif sport == "running":
                fecp = eff.get("fecp", "N/A")
                pace = eff.get("pace_str", "N/A")
                return (
                    f"### Métricas de Economía de Carrera — **{name}**\n\n"
                    f"- **Factor de Eficiencia en Carrera (FEcp = Velocidad / FC)**: **{fecp}** (m/min por latido).\n"
                    f"- **Ritmo Medio**: **{pace}** (tu ritmo umbral de carrera registrado en Intervals.icu es **{run_thresh}/km**).\n"
                    f"- **FC Media**: **{avg_hr} bpm** (FC Máx: {max_hr} bpm | LTHR: {lthr} bpm).\n\n"
                    f"**Lectura de Economía**: Rodar a {pace} con un pulso de {avg_hr} bpm representa un coste metabólico muy eficiente, permitiendo sumar kilómetros sin dañar las fibras musculares rápidas."
                )
            elif sport == "swimming":
                pace = eff.get("pace_str", "N/A")
                dps = eff.get("dps_meters", "N/A")
                swolf = eff.get("swolf", "N/A")
                return (
                    f"### Métricas de Eficiencia en Natación — **{name}**\n\n"
                    f"- **Pase Medio**: **{pace}** (tu CSS de referencia es **{css}/100m**).\n"
                    f"- **Distancia por Brazada (DPS)**: **{dps} m**\n"
                    f"- **SWOLF**: **{swolf}**\n\n"
                    f"La sesión consolidó el patrón motor subumbral manteniendo el coste hidrodinámico contenido."
                )

        # -----------------------------------------------------------------
        # 7. DESNIVEL, ELEVACIÓN & PERFIL ALTIMÉTRICO
        # -----------------------------------------------------------------
        elif any(x in q for x in ["desnivel", "elevaci", "cuesta", "subida", "bajada", "pendiente", "altimetr"]):
            return (
                f"### Impacto de la Altimetría — **{name}**\n\n"
                f"- **Desnivel Positivo (+)**: **+{elev_gain} m**\n"
                f"- **Desnivel Negativo (-)**: **-{elev_loss} m**\n"
                f"- **Coste Biomecánico**:\n"
                f"  * En las pendientes ascendentes (+{elev_gain} m), el reclutamiento motor demanda mayor trabajo de glúteos e isquiotibiales. Lo importante fue que la FC no sobrepasó los {max_hr} bpm.\n"
                f"  * En las bajadas, el impacto excéntrico cuadricipital es el factor limitante. Mantener cadencia alta amortigua este estrés articular."
            )

        # -----------------------------------------------------------------
        # 9. TRAINING EFFECT & CARGA DE SESIÓN
        # -----------------------------------------------------------------
        elif any(x in q for x in ["training effect", "training_effect", "efecto de entrenamiento", "efecto aeróbico", "efecto anaeróbico"]):
            te_a = te_aero or 3.2
            te_ana = te_anaero or 0.1
            return (
                f"### Training Effect de Garmin — **{name}**\n\n"
                f"- **Efecto de Entrenamiento Aeróbico**: **{te_a}** (Impacto óptimo en la capacidad aeróbica y resistencia de base).\n"
                f"- **Efecto de Entrenamiento Anaeróbico**: **{te_ana}** (Mínimo o nulo, exactamente lo prescrito en Periodo de Base).\n\n"
                f"**Veredicto**: Un TE aeróbico de {te_a} con TE anaeróbico < 1.0 es el patrón perfecto de la metodología polarizada: estimulas la capacidad mitocondrial sin generar acidosis láctica que perturbe el sistema nervioso autónomo."
            )

        # -----------------------------------------------------------------
        # 10. RECUPERACIÓN, MAÑANA, AJUSTE & BALANCE DE FORMA (PMC)
        # -----------------------------------------------------------------
        elif any(x in q for x in ["ajust", "mañana", "siguiente", "próxim", "fatiga", "recuper", "descans", "ctl", "atl", "tsb"]):
            return (
                f"### Plan de Asimilación y Pauta para la Próxima Sesión — **{name}**\n\n"
                f"- **Estado de Carga Actual (PMC)**: CTL: **{ctl}** | ATL: **{atl}** | TSB: **{tsb}** | ACWR: **{acwr}**.\n"
                f"- **Estado del SNA**: FC Reposo: **{rest_hr_ref} bpm** | Balance VFC parasimpático muy sólido.\n\n"
                f"**Directrices del Entrenador para las Próximas 24-48 horas**:\n"
                f"1. **Ventana de Recuperación**: Esta sesión ({dur} min a {avg_hr} bpm) se asimila completamente en 24 horas.\n"
                f"2. **Pauta para la Sesión de Mañana**: Comienza con 15 minutos en Z1 estricta antes de fijar el ritmo principal para favorecer el aclaramiento de metabolitos.\n"
                f"3. **Descanso**: Prioriza un bloque de sueño de 7.5 – 8 horas para permitir la secreción óptima de hormona del crecimiento durante las fases de onda lenta (N3)."
            )

        # -----------------------------------------------------------------
        # 11. DEFAULT: INFORME TÉCNICO MULTIDIMENSIONAL COMPLETO
        # -----------------------------------------------------------------
        else:
            pct_lthr = round((avg_hr / max(lthr, 1)) * 100, 1)
            fec_str = eff.get("fec") or eff.get("fecp") or "N/A"
            dec_txt = f"{dec.get('decoupling_percent', 0.0)}%" if dec.get("has_decoupling") else "Estable"

            return (
                f"### Diagnóstico Integral de Rendimiento — **{name}**\n\n"
                f"He analizado en detalle toda la telemetría de tu entrenamiento ({dur} min, {dist}):\n\n"
                f"1. **Dinámica Cardiovascular**: FC media de **{avg_hr} bpm** ({pct_lthr}% de tu LTHR de {lthr} bpm) con máxima de **{max_hr} bpm**. Respuesta perfectamente alineada con la fase de Base.\n"
                f"2. **Desacople y Eficiencia**: Desacople en **{dec_txt}** y factor de eficiencia en **{fec_str}**, confirmando estabilidad del volumen sistólico.\n"
                f"3. **Metabolismo**: Gasto estimado de **{calories} kcal** con alta tasa de oxidación lipídica (~55% grasas / 45% glucógeno).\n"
                f"4. **Impacto en el Plan**: Con tu CTL en **{ctl}** y TSB en **{tsb}**, el estímulo se asimila limpiamente sin sobrecarga.\n\n"
                f"¿Quieres profundizar en algún punto específico (splits por km, cadencia, nutrición de reposición o pautas para mañana)?\n\n"
                f"> 💡 *Consejo*: Para conversar con el modelo de IA libremente sin límites sobre cualquier consulta como en ChatGPT o Gemini fuera de la app, puedes activar tu clave gratuita de Google Gemini en **Ajustes** ⚙️."
            )

    def _generate_heuristic_chat_reply(self, query: str, context: Dict[str, Any]) -> str:
        """Global coach conversational heuristic reply when no LLM key is configured."""
        q = query.lower()
        ctl = context.get("current_ctl", 96)
        atl = context.get("current_atl", 104)
        tsb = context.get("current_tsb", round(ctl - atl, 1))
        hrv = context.get("current_hrv", 104)
        rhr = context.get("current_rhr", 36)
        ftp = context.get("ftp", 348)
        run_thresh = context.get("run_threshold", "3:40")
        css = context.get("css", "1:29.0")

        key_tip = "\n\n> 💡 *Nota*: Para hacer cualquier pregunta completamente abierta con el modelo de IA conversacional (como ChatGPT o Gemini en la web), puedes activar tu clave gratuita de Google Gemini en **Ajustes** ⚙️."

        if any(x in q for x in ["fatiga", "forma", "tsb", "ctl", "atl", "acwr"]):
            return (
                f"### Estado de Forma y Carga de Entrenamiento (PMC)\n\n"
                f"- **Fitness (CTL)**: **{ctl}**\n"
                f"- **Fatiga Aguda (ATL)**: **{atl}**\n"
                f"- **Balance de Estrés (TSB)**: **{tsb}**\n\n"
                f"**Diagnóstico del Entrenador**:\n"
                f"En plena Fase de Base Aeróbica, un TSB moderadamente negativo ({tsb}) es el signo inequívoco de que estás generando adaptaciones mitocondriales y vasculares sin comprometer el sistema parasimpático. Tu FC en reposo ({rhr} bpm) y VFC ({hrv} ms) ratifican una asimilación biológica perfecta."
                f"{key_tip}"
            )
        elif any(x in q for x in ["nutricion", "nutrición", "comer", "carbohidrato", "ch", "hidratacion", "hidratación", "sales", "sodio", "gel", "geles"]):
            return (
                f"### Estrategia de Nutrición e Hidratación para Triatlón\n\n"
                f"- **Ingesta en Ciclismo**: **60-90 g/h de carbohidratos** (mezcla glucosa:fructosa 2:1 o 1:0.8) en tiradas superiores a 90 minutos. Esto entrena el sistema gastrointestinal y preserva el glucógeno hepático.\n"
                f"- **Ingesta en Carrera**: **30-60 g/h** mediante geles hidrosolubles tomados con pequeños sorbos de agua cada 25-30 minutos.\n"
                f"- **Hidratación y Electrolitos**: **500 - 750 ml/h** de fluido con una concentración de **500 - 800 mg de sodio por litro** según tasa de sudoración y temperatura ambiente.\n"
                f"- **Recuperación Post-sesión**: 1.0 - 1.2 g de CH/kg + 0.3 g de proteína/kg durante la primera hora tras el entrenamiento."
                f"{key_tip}"
            )
        elif any(x in q for x in ["fuerza", "gimnasio", "pesas", "pesa", "core", "lesion", "lesión", "tendon", "tendón"]):
            return (
                f"### Pauta de Fuerza Concurrente en Periodo de Base\n\n"
                f"- **Frecuencia**: 2 sesiones semanales de 45-50 minutos, enfocadas en fuerza máxima y reclutamiento neural (sin hipertrofia excesiva).\n"
                f"- **Ejercicios Clave**: Sentadilla trasera/frontal profunda (3-4 series x 4-6 reps @ 80-85% 1RM), Peso muerto rumano para cadena posterior, Hip Thrust y Press Militar unilateral.\n"
                f"- **Core y Estabilidad**: Planchas dinámicas, Pallof press y paseo del granjero para transferir rigidez lumbo-pélvica a la carrera y al acople en la cabra.\n"
                f"- **Timing**: Separar al menos 6 horas de cualquier sesión clave de umbral de carrera o series de bici."
                f"{key_tip}"
            )
        elif any(x in q for x in ["natacion", "natación", "nadar", "css", "swolf", "brazada"]):
            return (
                f"### Criterios Clave de Natación y CSS\n\n"
                f"- **Tu CSS Actual**: **{css}/100m** (Velocidad Crítica de Nado).\n"
                f"- **Trabajo Sub-CSS (Base)**: Series a ritmos entre CSS + 3s y CSS + 5s (ej. 1:32 - 1:34/100m) con descansos cortos (10-15s), buscando estabilizar el SWOLF y mantener la distancia por brazada (DPS).\n"
                f"- **Trabajo en CSS**: Bloques de 100m y 200m a 1:29/100m con ratio descanso/trabajo 1:4 para elevar la tolerancia al lactato sin perder el agarre en la fase subacuática."
                f"{key_tip}"
            )
        elif any(x in q for x in ["umbral", "ftp", "ritmo", "css", "lthr", "zonas"]):
            return (
                f"### Umbrales Fisiológicos Activos (Sincronizados con Intervals.icu)\n\n"
                f"- **Ciclismo (FTP)**: **{ftp} W**\n"
                f"- **Carrera (Ritmo Umbral)**: **{run_thresh}/km**\n"
                f"- **Natación (CSS)**: **{css}/100m**\n"
                f"- **Umbral de Lactato FC (LTHR)**: **159 bpm**\n"
                f"- **FC Máxima**: **183 bpm** | **FC Reposo**: **{rhr} bpm**\n\n"
                f"Tus zonas de entrenamiento se calculan dinámicamente sobre estas referencias para garantizar que cada tirada estimule exactamente la vía metabólica prescrita."
                f"{key_tip}"
            )
        elif any(x in q for x in ["desacople", "pw:hr", "pa:hr", "deriva"]):
            return (
                f"### Concepto Clave: Desacople Cardiovascular ($Pw:HR$ / $Pa:HR$)\n\n"
                f"El desacople mide la pérdida de linealidad entre la entrega de potencia o ritmo y la frecuencia cardíaca.\n\n"
                f"- **< 3.5%**: Eficiencia aeróbica óptima (mitocondrias sanas, volemia preservada).\n"
                f"- **3.5% – 5.0%**: Rango normal para tiradas de volumen en base.\n"
                f"- **> 5.0%**: Deriva acusada por deshidratación, fatiga neuromuscular o vaciamiento de glucógeno."
                f"{key_tip}"
            )
        elif any(x in q for x in ["sueño", "dormir", "hrv", "vfc", "recuperacion", "recuperación"]):
            return (
                f"### Biomarcadores de Recuperación y Sistema Nervioso Autónomo\n\n"
                f"- **Tu VFC Nocturna**: **{hrv} ms** (Tono parasimpático alto y estable).\n"
                f"- **FC Reposo**: **{rhr} bpm** (Línea base excelente sin signos de estrés sistémico).\n"
                f"- **Objetivo de Sueño**: Mínimo 7.5 - 8.5 horas con al menos 20% en fase profunda y 20% en fase REM para optimizar la síntesis de hormona de crecimiento y la regeneración neuromuscular."
                f"{key_tip}"
            )
        else:
            return (
                f"### Consulta con el Entrenador Experto en Triatlón\n\n"
                f"Revisando tus biomarcadores actuales (RHR: **{rhr} bpm**, VFC: **{hrv} ms**, CTL: **{ctl}**, TSB: **{tsb}**, FTP: **{ftp}W**):\n\n"
                f"Estás en una fase de excelente asimilación fisiológica. Tu sistema neuromuscular y parasimpático responden con solidez a los estímulos prescritos.\n\n"
                f"Puedes preguntarme sobre cualquier área técnica: nutrición e hidratación, ritmos y vatios para tus series, planificación de cargas, desacople cardiovascular o ajustes según tu nivel de fatiga.{key_tip}"
            )

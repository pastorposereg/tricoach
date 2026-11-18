"""Triathlon Training & Health Analytics Backend.
FastAPI Application serving REST endpoints and responsive web frontend.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import AppConfig, load_config, save_config
from .data_manager import DataManager
from .garmin_service import GarminService
from .intervals_service import IntervalsService
from .ai_coach import AICoachService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("triathlon_app")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Triathlon Performance & Health Platform",
    description="Garmin Connect + Intervals.icu + Triathlon AI Coach",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared Manager
config = load_config()
dm = DataManager(config)


@app.on_event("startup")
def warm_cache_on_startup():
    """Warms the week and PMC cache in background for sub-second page loads."""
    def _warm():
        try:
            logger.info("Warming cache for week and PMC in background...")
            dm.get_week_view(0)
            dm.get_pmc_data(90)
            logger.info("Cache warmed successfully.")
        except Exception as e:
            logger.warning(f"Error warming cache on startup: {e}")

    threading.Thread(target=_warm, daemon=True).start()


# --- Request Models ---
class SettingsRequest(BaseModel):
    garmin_email: Optional[str] = None
    garmin_password: Optional[str] = None
    intervals_athlete_id: Optional[str] = None
    intervals_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ftp: Optional[int] = None
    css_pace: Optional[str] = None
    run_threshold_pace: Optional[str] = None
    max_hr: Optional[int] = None
    rest_hr_baseline: Optional[int] = None
    lthr: Optional[int] = None


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []


class CalendarNoteRequest(BaseModel):
    date: str
    name: str
    description: Optional[str] = ""


# --- API Routes ---
@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    """Returns application status and connected integrations, keeping thresholds fresh."""
    cfg = load_config()
    
    # Keep thresholds updated with Intervals.icu if connected
    if cfg.intervals_connected and cfg.intervals_api_key:
        try:
            svc = IntervalsService(cfg)
            svc.sync_athlete_thresholds(save=True)
            cfg = load_config()
        except Exception as e:
            logger.warning(f"Background threshold sync error: {e}")

    # Check for active public tunnel URL (for remote mobile access without Wi-Fi)
    public_url = None
    tunnel_file = Path.home() / ".tricoach" / "public_tunnel_url.txt"
    if tunnel_file.exists():
        try:
            with open(tunnel_file, "r", encoding="utf-8") as tf:
                content = tf.read().strip()
                if content.startswith("http"):
                    public_url = content
        except Exception:
            pass

    return {
        "athlete_name": cfg.garmin_athlete_name or "Pastor",
        "athlete_phase": cfg.athlete_phase,
        "athlete_discipline": cfg.athlete_discipline,
        "public_url": public_url,
        "garmin": {
            "connected": cfg.garmin_connected,
            "has_credentials": bool(cfg.garmin_email and cfg.garmin_password),
            "token_dir": cfg.garmin_token_dir,
        },
        "intervals": {
            "connected": cfg.intervals_connected,
            "has_api_key": bool(cfg.intervals_api_key),
            "athlete_id": cfg.intervals_athlete_id or "0",
        },
        "ai": {
            "has_key": bool(cfg.gemini_api_key),
            "model": "Gemini 2.5 Flash / Heurística Experta Triatlón",
        },
        "thresholds": {
            "ftp": cfg.ftp,
            "css_pace": cfg.css_pace,
            "run_threshold_pace": cfg.run_threshold_pace,
            "max_hr": cfg.max_hr,
            "rest_hr": cfg.rest_hr_baseline,
            "lthr": cfg.lthr,
            "weight": cfg.weight,
            "last_sync": cfg.thresholds_last_sync,
            "disciplines": cfg.disciplines_thresholds,
            "synced_with_intervals": cfg.intervals_connected,
        }
    }


@app.post("/api/thresholds/sync")
def sync_thresholds() -> Dict[str, Any]:
    """Explicit endpoint to force-sync thresholds from Intervals.icu."""
    cfg = load_config()
    svc = IntervalsService(cfg)
    thresholds = svc.sync_athlete_thresholds(save=True)
    global dm
    dm = DataManager(load_config())
    return {
        "status": "success",
        "thresholds": thresholds,
        "message": "Umbrales actualizados y sincronizados en tiempo real con Intervals.icu"
    }


@app.post("/api/settings")
def update_settings(payload: SettingsRequest) -> Dict[str, Any]:
    """Updates settings and credentials."""
    cfg = load_config()
    if payload.garmin_email is not None:
        cfg.garmin_email = payload.garmin_email
    if payload.garmin_password is not None:
        cfg.garmin_password = payload.garmin_password
    if payload.intervals_athlete_id is not None:
        cfg.intervals_athlete_id = payload.intervals_athlete_id
    if payload.intervals_api_key is not None:
        cfg.intervals_api_key = payload.intervals_api_key
    if payload.gemini_api_key is not None:
        cfg.gemini_api_key = payload.gemini_api_key
    if payload.ftp is not None:
        cfg.ftp = payload.ftp
    if payload.css_pace is not None:
        cfg.css_pace = payload.css_pace
    if payload.run_threshold_pace is not None:
        cfg.run_threshold_pace = payload.run_threshold_pace
    if payload.max_hr is not None:
        cfg.max_hr = payload.max_hr
    if payload.rest_hr_baseline is not None:
        cfg.rest_hr_baseline = payload.rest_hr_baseline
    if payload.lthr is not None:
        cfg.lthr = payload.lthr

    save_config(cfg)
    # Refresh manager with updated config
    global dm
    dm = DataManager(cfg)
    return {"status": "success", "message": "Ajustes actualizados correctamente"}


class GarminLoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class IntervalsAuthRequest(BaseModel):
    athlete_id: Optional[str] = "0"
    api_key: Optional[str] = None


@app.post("/api/garmin/login")
def garmin_login(payload: Optional[GarminLoginRequest] = None) -> Dict[str, Any]:
    """Triggers login with Garmin credentials or connects saved session."""
    cfg = load_config()
    svc = GarminService(cfg)
    if payload and payload.email and payload.password:
        res = svc.login_with_credentials(payload.email, payload.password)
        if res.get("status") == "success":
            global dm
            dm = DataManager(load_config())
        return res

    # Otherwise test/resume existing session
    res = svc.test_connection()
    return res


@app.post("/api/intervals/test")
def intervals_test(payload: Optional[IntervalsAuthRequest] = None) -> Dict[str, Any]:
    """Tests connection to Intervals.icu. If credentials provided, saves them upon success."""
    cfg = load_config()
    if payload and payload.api_key:
        cfg.intervals_api_key = payload.api_key.strip()
        if payload.athlete_id:
            cfg.intervals_athlete_id = payload.athlete_id.strip()

    svc = IntervalsService(cfg)
    res = svc.test_connection()
    if res.get("status") == "success":
        cfg.intervals_connected = True
        save_config(cfg)
        global dm
        dm = DataManager(cfg)
    return res


@app.get("/api/week")
def get_week(
    offset: int = Query(0, description="Week offset from current (0 = this week, -1 = previous, 1 = next)"),
    refresh: bool = Query(False, description="Force fresh fetch from external APIs")
):
    """Returns calendar and zone comparison data for the requested week."""
    try:
        return dm.get_week_view(offset_weeks=offset, force_refresh=refresh)
    except Exception as e:
        logger.error(f"Error getting week view: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/planned/{event_id}")
def get_planned_event_detail(event_id: str):
    """Returns detailed description and structure of a planned workout from Intervals.icu."""
    try:
        cfg = load_config()
        svc = IntervalsService(cfg)
        detail = svc.get_event_detail(event_id)
        if detail:
            return detail
        # Fallback to searching in week view if offline or fallback mode
        week = dm.get_week_view(offset_weeks=0)
        for day in week.get("days", []):
            for pl in day.get("planned", []):
                if str(pl.get("id")) == str(event_id):
                    return pl
        return {"id": event_id, "name": "Entrenamiento Planificado", "description": "Sin descripción disponible."}
    except Exception as e:
        logger.error(f"Error fetching planned event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calendar/note")
def add_calendar_note(payload: CalendarNoteRequest):
    """Creates a calendar note in Intervals.icu."""
    try:
        cfg = load_config()
        svc = IntervalsService(cfg)
        res = svc.create_calendar_note(payload.date, payload.name, payload.description or "")
        if not res:
            raise HTTPException(status_code=500, detail="No se pudo crear la nota en Intervals.icu. Comprueba tu conexión.")
        return {"status": "success", "event": res, "message": "Nota añadida y sincronizada en Intervals.icu"}
    except Exception as e:
        logger.error(f"Error creating calendar note: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/calendar/event/{event_id}")
def delete_calendar_event(event_id: str):
    """Deletes an event or note from Intervals.icu."""
    try:
        cfg = load_config()
        svc = IntervalsService(cfg)
        ok = svc.delete_calendar_event(event_id)
        if not ok:
            raise HTTPException(status_code=500, detail="No se pudo eliminar el evento en Intervals.icu")
        return {"status": "success", "message": "Evento eliminado de Intervals.icu"}
    except Exception as e:
        logger.error(f"Error deleting event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/planned/{event_id}/chat")
def chat_planned_workout(event_id: str, payload: ChatRequest):
    """Interactive coaching focused on a planned workout from Intervals.icu."""
    try:
        cfg = load_config()
        svc = IntervalsService(cfg)
        event_detail = svc.get_event_detail(event_id)
        if not event_detail:
            # Fallback search in week view
            week = dm.get_week_view(offset_weeks=0)
            for day in week.get("days", []):
                for pl in day.get("planned", []):
                    if str(pl.get("id")) == str(event_id):
                        event_detail = pl
                        break
        if not event_detail:
            event_detail = {"id": event_id, "name": "Sesión Planificada"}

        pmc = dm.get_pmc_data(range_days=14)
        athlete_context = {
            "athlete_name": cfg.garmin_athlete_name or "Pastor",
            "phase": cfg.athlete_phase,
            "ftp": cfg.ftp,
            "css": cfg.css_pace,
            "run_threshold": cfg.run_threshold_pace,
            "lthr": cfg.lthr,
            "max_hr": cfg.max_hr,
            "rest_hr": cfg.rest_hr_baseline,
            "current_ctl": pmc.get("current_ctl", 96),
            "current_atl": pmc.get("current_atl", 104),
            "current_tsb": pmc.get("current_tsb", -8),
            "acwr": pmc.get("acwr", 1.1),
        }
        coach_service = AICoachService(cfg.gemini_api_key)
        reply = coach_service.chat_about_planned_workout(
            event_data=event_detail,
            athlete_context=athlete_context,
            user_message=payload.message,
            chat_history=payload.history or [],
        )
        return {"reply": reply}
    except Exception as e:
        logger.error(f"Error in planned workout chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/activity/{activity_id}")
def get_activity_analysis(activity_id: str):
    """Returns activity details, decoupling calculation, and AI Coach evaluation."""
    try:
        return dm.get_activity_detail(activity_id)
    except Exception as e:
        logger.error(f"Error getting activity {activity_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/activity/{activity_id}/chat")
def chat_activity_coach(activity_id: str, payload: ChatRequest):
    """Conversational endpoint specifically discussing a single activity with the AI Coach."""
    try:
        activity_detail = dm.get_activity_detail(activity_id)
        current_act = activity_detail.get("activity", {})

        # Check if user query refers to a previous or comparison activity (e.g. "hace 4 semanas", "lunes anterior", etc.)
        comparison_activity = dm.find_comparison_activity(
            current_activity_id=activity_id,
            current_date_str=current_act.get("start_time", ""),
            sport_type=current_act.get("sport_type", ""),
            user_query=payload.message
        )

        pmc = dm.get_pmc_data(range_days=14)
        cfg = load_config()
        athlete_context = {
            "athlete_name": cfg.garmin_athlete_name or "Pastor",
            "phase": cfg.athlete_phase,
            "ftp": cfg.ftp,
            "css": cfg.css_pace,
            "run_threshold": cfg.run_threshold_pace,
            "lthr": cfg.lthr,
            "max_hr": cfg.max_hr,
            "rest_hr": cfg.rest_hr_baseline,
            "current_ctl": pmc.get("current_ctl", 96),
            "current_atl": pmc.get("current_atl", 104),
            "current_tsb": pmc.get("current_tsb", -8),
            "acwr": pmc.get("acwr", 1.1),
        }
        coach_service = AICoachService(cfg.gemini_api_key)
        reply = coach_service.chat_about_activity(
            activity_data=current_act,
            efficiency=activity_detail.get("efficiency", {}),
            decoupling=activity_detail.get("decoupling", {}),
            wellness=activity_detail.get("wellness", {}),
            athlete_context=athlete_context,
            user_message=payload.message,
            chat_history=payload.history or [],
            comparison_activity=comparison_activity,
        )
        return {"reply": reply}
    except Exception as e:
        logger.error(f"Error in activity chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pmc")
def get_pmc(
    days: int = Query(90, description="Range in days for the PMC curve"),
    refresh: bool = Query(False, description="Force fresh fetch from external APIs")
):
    """Returns PMC (CTL, ATL, TSB) and wellness data."""
    try:
        return dm.get_pmc_data(range_days=days, force_refresh=refresh)
    except Exception as e:
        logger.error(f"Error getting PMC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/volume/history")
def get_volume_history(weeks: int = Query(10, description="Number of weeks to look back")):
    """Returns weekly planned vs completed volume (in hours) for the last N weeks."""
    try:
        return dm.get_weekly_volume_history(num_weeks=weeks)
    except Exception as e:
        logger.error(f"Error getting volume history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seasons/tests")
def get_seasons_tests():
    """Returns test and performance metrics structured by season."""
    try:
        return dm.get_seasons_tests_data()
    except Exception as e:
        logger.error(f"Error getting seasons tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/seasons/competitions")
def get_seasons_competitions():
    """Returns past and present race events with 16 performance telemetry columns."""
    try:
        return dm.get_seasons_competitions_data()
    except Exception as e:
        logger.error(f"Error getting seasons competitions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
def chat_coach(payload: ChatRequest):
    """Conversational endpoint with the AI Triathlon Coach."""
    try:
        # Contextualize with current form metrics
        pmc = dm.get_pmc_data(range_days=14)
        cfg = load_config()
        athlete_context = {
            "athlete_name": cfg.garmin_athlete_name or "Pastor",
            "phase": cfg.athlete_phase,
            "current_ctl": pmc.get("current_ctl", 96),
            "current_atl": pmc.get("current_atl", 104),
            "current_tsb": pmc.get("current_tsb", -8),
            "acwr": pmc.get("acwr", 1.1),
            "ftp": cfg.ftp,
            "css": cfg.css_pace,
            "run_threshold": cfg.run_threshold_pace,
            "lthr": cfg.lthr,
            "max_hr": cfg.max_hr,
            "rest_hr": cfg.rest_hr_baseline,
        }
        coach_service = AICoachService(cfg.gemini_api_key)
        reply = coach_service.chat_with_coach(
            user_message=payload.message,
            chat_history=payload.history or [],
            athlete_context=athlete_context
        )
        return {"reply": reply}
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Static Frontend Mounting ---
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(STATIC_DIR / "index.html")

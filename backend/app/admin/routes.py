from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.auth import is_admin_authenticated, require_admin, verify_admin_credentials
from backend.app.core.config import get_settings
from backend.app.db.models.billing import Plan
from backend.app.db.models.catalog import IndicatorType, Ticker, Timeframe, TimeframeScanSchedule
from backend.app.db.models.scan import ScanRun
from backend.app.db.models.user import User
from backend.app.db.session import get_db
from backend.app.services.scan_scheduler import list_running_jobs, reload_schedule, reset_and_run_schedule
from backend.app.services.user_service import UserDeletionError, delete_user_account, get_admin_user_stats, list_admin_users

templates = Jinja2Templates(directory="backend/app/admin/templates")
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request) -> HTMLResponse:
    if is_admin_authenticated(request):
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if verify_admin_credentials(username, password):
        request.session["admin_authenticated"] = True
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": "Invalid credentials"}, status_code=401)


@router.get("/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    require_admin(request)
    stats = await get_admin_user_stats(db)
    runs = (
        await db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(10))
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "registered_users": stats.registered_users,
            "paid_users": stats.paid_users,
            "addons_sold": stats.addons_sold,
            "runs": runs,
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    require_admin(request)
    users = await list_admin_users(db)
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(request, "users.html", {"users": users, "flash": flash})


@router.post("/users/{user_id}/delete")
async def admin_delete_user(user_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    try:
        await delete_user_account(db, user_id)
        await db.commit()
        flash = "User deleted."
    except UserDeletionError as exc:
        await db.rollback()
        flash = str(exc)
    return RedirectResponse(f"/admin/users?flash={quote(flash)}", status_code=303)


@router.get("/tickers", response_class=HTMLResponse)
async def admin_tickers(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    require_admin(request)
    tickers = (await db.execute(select(Ticker).order_by(Ticker.display_name))).scalars().all()
    return templates.TemplateResponse(request, "tickers.html", {"tickers": tickers})


@router.post("/tickers")
async def admin_create_ticker(
    request: Request,
    yfinance_symbol: str = Form(...),
    display_name: str = Form(...),
    category: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    require_admin(request)
    db.add(Ticker(yfinance_symbol=yfinance_symbol, display_name=display_name, category=category))
    await db.commit()
    return RedirectResponse("/admin/tickers", status_code=303)


@router.post("/tickers/{ticker_id}/toggle")
async def admin_toggle_ticker(ticker_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    require_admin(request)
    ticker = (await db.execute(select(Ticker).where(Ticker.id == ticker_id))).scalar_one()
    ticker.is_active = not ticker.is_active
    await db.commit()
    return RedirectResponse("/admin/tickers", status_code=303)


@router.get("/timeframes", response_class=HTMLResponse)
async def admin_timeframes(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    require_admin(request)
    timeframes = (await db.execute(select(Timeframe).order_by(Timeframe.code))).scalars().all()
    return templates.TemplateResponse(request, "timeframes.html", {"timeframes": timeframes})


@router.get("/schedules", response_class=HTMLResponse)
async def admin_schedules(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    require_admin(request)
    rows = (
        await db.execute(
            select(TimeframeScanSchedule, Timeframe)
            .join(Timeframe, TimeframeScanSchedule.timeframe_id == Timeframe.id)
            .order_by(Timeframe.code)
        )
    ).all()
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "schedules.html",
        {"rows": rows, "flash": flash},
    )


@router.get("/schedules/jobs", response_class=HTMLResponse)
async def admin_schedule_jobs(request: Request) -> HTMLResponse:
    require_admin(request)
    return templates.TemplateResponse(
        request,
        "schedules_jobs_partial.html",
        {"jobs": list_running_jobs()},
    )


@router.post("/schedules/{schedule_id}/run-now")
async def admin_run_schedule_now(
    schedule_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_admin(request)
    schedule = (
        await db.execute(select(TimeframeScanSchedule).where(TimeframeScanSchedule.id == schedule_id))
    ).scalar_one()
    result = await reset_and_run_schedule(schedule.timeframe_id)
    messages = {
        "started": f"Scan started for schedule {schedule_id}.",
        "already_running": "That timeframe is already scanning.",
        "disabled": "Schedule is disabled — enable it first.",
        "not_found": "Schedule not found.",
    }
    flash = messages.get(result, result)
    return RedirectResponse(f"/admin/schedules?flash={quote(flash)}", status_code=303)


@router.post("/schedules/{schedule_id}")
async def admin_update_schedule(
    schedule_id: UUID,
    request: Request,
    interval_minutes: int = Form(...),
    is_enabled: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    require_admin(request)
    schedule = (
        await db.execute(select(TimeframeScanSchedule).where(TimeframeScanSchedule.id == schedule_id))
    ).scalar_one()
    schedule.interval_minutes = interval_minutes
    schedule.is_enabled = is_enabled == "on"
    await db.commit()
    await reload_schedule(schedule.timeframe_id)
    return RedirectResponse("/admin/schedules", status_code=303)


@router.get("/plans", response_class=HTMLResponse)
async def admin_plans(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    require_admin(request)
    plans = (await db.execute(select(Plan).order_by(Plan.name))).scalars().all()
    return templates.TemplateResponse(request, "plans.html", {"plans": plans})


@router.get("/settings", response_class=HTMLResponse)
async def admin_settings(request: Request) -> HTMLResponse:
    require_admin(request)
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"default_bars": settings.default_subscription_bars},
    )

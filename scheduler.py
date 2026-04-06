"""scheduler.py — Background appointment scheduler for Anonymous Studio.

Uses the ``schedule`` library (MIT) — a lightweight cron-like runner that
works without Taipy Enterprise.  Runs in a **daemon thread** so it never
blocks the GUI or the Orchestrator.

What happens when an appointment comes due
------------------------------------------
1. The linked Pipeline card (if any) is advanced to ``review`` (only if it
   is currently ``in_progress``).
2. An ``appointment.due`` audit entry is written.
3. The appointment status is set to ``completed``.
4. A toast message is pushed to ``PENDING_NOTIFICATIONS`` so the next
   page-navigation callback can display it to the user.

Usage (in app.py)
-----------------
    import scheduler
    # at startup, after store is initialised:
    scheduler.sync(store.list_appointments())
    scheduler.start()

    # after saving a new/edited appointment:
    scheduler.register(appt)

    # after deleting an appointment:
    scheduler.cancel(appt_id)

    # in on_navigate / _refresh_appts — flush queued toasts:
    for n in scheduler.flush_notifications():
        notify(state, n["level"], n["msg"])
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import schedule

log = logging.getLogger(__name__)

# ── Internal state ────────────────────────────────────────────────────────────

_JOBS: Dict[str, schedule.Job] = {}  # appt_id → schedule.Job
_lock = threading.Lock()
_started = False

# Pending toast notifications consumed by the GUI thread on next navigation.
_PENDING: List[Dict[str, str]] = []
_pending_lock = threading.Lock()


# ── Public helpers ────────────────────────────────────────────────────────────

def flush_notifications() -> List[Dict[str, str]]:
    """Return and clear all queued notifications (thread-safe)."""
    with _pending_lock:
        items = list(_PENDING)
        _PENDING.clear()
    return items


def register(appt) -> bool:
    """Schedule a one-shot action for *appt* (an ``Appointment`` dataclass).

    Returns ``True`` if registered, ``False`` if the time has already passed
    or the appointment is not in ``scheduled`` status.
    """
    if appt.status != "scheduled" or not appt.scheduled_for:
        return False
    try:
        due_dt = datetime.fromisoformat(appt.scheduled_for)
    except ValueError:
        log.warning("scheduler: invalid datetime %r for appt %s",
                    appt.scheduled_for, appt.id)
        return False

    if due_dt <= datetime.now():
        return False  # already past

    appt_id = appt.id    

    # Optional: schedule a reminder 24 h before due time, if that time is in the future.
    # from datetime import timedelta
    # reminder_dt = due_dt - timedelta(hours=24)

    # For testing/demo purposes, use a 10-second reminder instead of 24 hours.
    from datetime import timedelta
    reminder_dt = due_dt - timedelta(seconds=10) 

    if reminder_dt > datetime.now():
        reminder_time_str = reminder_dt.strftime("%H:%M")
        reminder_date_str = reminder_dt.strftime("%Y-%m-%d")

        def _reminder_job():
            if datetime.now().strftime("%Y-%m-%d") == reminder_date_str:
                _send_reminder(appt_id)
            return schedule.CancelJob
        schedule.every().day.at(reminder_time_str).do(_reminder_job)    

    cancel(appt.id)  # replace any existing job for this id

    time_str = due_dt.strftime("%H:%M")
    date_str = due_dt.strftime("%Y-%m-%d")
    appt_id  = appt.id

    def _job():
        # Guard: only fire on the correct calendar date
        if datetime.now().strftime("%Y-%m-%d") == date_str:
            _fire(appt_id)
        with _lock:
            _JOBS.pop(appt_id, None)
        return schedule.CancelJob  # always remove after one run

    with _lock:
        job = schedule.every().day.at(time_str).do(_job)
        _JOBS[appt_id] = job

    log.info("scheduler: registered appt %s for %s", appt_id, appt.scheduled_for)
    print(f"🔔 [SCHEDULER DEBUG] Registered: {appt.title} on {appt.scheduled_for}")
    return True


def cancel(appt_id: str) -> None:
    """Cancel a registered appointment job (no-op if not registered)."""
    with _lock:
        job = _JOBS.pop(appt_id, None)
        if job:
            schedule.cancel_job(job)
            log.info("scheduler: cancelled appt %s", appt_id)


def sync(appointments) -> int:
    """Register all future ``scheduled`` appointments from *appointments*.

    Call once at startup after the store is initialised.
    Returns the number of jobs registered.
    """
    count = 0
    for a in appointments:
        if register(a):
            count += 1
    log.info("scheduler: synced %d future appointment(s)", count)
    return count


def start(interval_s: int = 30) -> Optional[threading.Thread]:
    """Start the background runner thread (idempotent — safe to call twice).

    *interval_s* controls how often ``schedule.run_pending()`` is called.
    30 s gives ≤30 s latency on appointment triggers, with negligible CPU.
    """
    global _started
    if _started:
        return None
    _started = True

    def _run():
        log.info("scheduler: thread started (interval=%ds)", interval_s)
        while True:
            schedule.run_pending()
            time.sleep(interval_s)

    t = threading.Thread(target=_run, name="anon-scheduler", daemon=True)
    t.start()
    return t


# ── Internal fire action ──────────────────────────────────────────────────────

def _fire(appt_id: str) -> None:
    """Execute the due-appointment actions.  Runs on the scheduler thread."""
    # Import lazily to avoid circular imports (store imports nothing from here)
    from store import get_store
    store = get_store()

    a = store.get_appointment(appt_id)
    print(f"🔥 [SCHEDULER DEBUG] _fire() triggered for appointment: {appt_id}")
    if not a:
        log.warning("scheduler: appt %s not found at fire time", appt_id)
        print(f"❌ [SCHEDULER DEBUG] Appointment not found!")
        return

    log.info("scheduler: firing appt %s '%s'", appt_id, a.title)

    # 1. Advance linked pipeline card to "review" (if in_progress)
    if a.pipeline_card_id:
        card = store.get_card(a.pipeline_card_id)
        if card and card.status == "in_progress":
            store.update_card(
                a.pipeline_card_id,
                status="review",
            )
            store.log_user_action(
                "system", "pipeline.advance",
                "card", a.pipeline_card_id,
                f"Auto-advanced to Review via appointment '{a.title}'",
            )

    # 2. Mark appointment completed
    store.update_appointment(appt_id, status="completed")

    # 3. Audit log
    store.log_user_action(
        "system", "appointment.due",
        "appointment", appt_id,
        f"Appointment '{a.title}' came due — actions executed",
    )

    # 4. Queue GUI notification
    with _pending_lock:
        _PENDING.append({
            "level": "info",
            "msg":   f"Review due: {a.title}",
        })

def _send_reminder(appt_id: str) -> None:
    from store import get_store
    from services.notifications import send_email_notification
    store = get_store()
    a = store.get_appointment(appt_id)

    print(f"🚀 [SCHEDULER DEBUG] Reminder for appointment: {appt_id}")
    if not a:
        print(f"❌ [SCHEDULER DEBUG] Appointment {appt_id} not found!")
        return
    #Getting Pipeline Card Information
    card_info = ""
    if a.pipeline_card_id:
        card = store.get_card(a.pipeline_card_id)
        if card:
            card_info = f"\nPipeline Card: {card.title} (Status: {card.status})"
    message = f"""
Reminder: {a.title}

Description: {a.description}
Scheduled for: {a.scheduled_for}
{card_info}
"""
    #Email
    for email in a.attendees:
        if not email:
            continue
        user = None
        try:
            user = store.get_user_by_email(email)
        except Exception:
            pass

        if not user or getattr(user, "email_notifications", True):
            send_email_notification(email, f"Upcoming Reminder (Review in 24 Hours)", message)
        
    #IN App
    with _pending_lock:
        _PENDING.append({
            "level": "info",
            "msg": f"Reminder: {a.title} in 24 hours"
        })
        print(f"📬 [SCHEDULER DEBUG] Notification queued in _PENDING list. Total pending: {len(_PENDING)}")    
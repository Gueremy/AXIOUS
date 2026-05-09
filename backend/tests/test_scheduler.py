"""
tests/test_scheduler.py
Tests Sprint 3 — APScheduler (AXI-16).

5 tests:
  - Scheduler tiene 2 jobs registrados
  - Job nocturno existe con id correcto
  - Job periódico existe con id correcto
  - Trigger nocturno es CronTrigger a las 02:00
  - Trigger periódico es IntervalTrigger de 30 min
"""
import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler import scheduler


def test_scheduler_tiene_jobs():
    """El scheduler tiene exactamente 3 jobs registrados."""
    jobs = scheduler.get_jobs()
    assert len(jobs) == 3


def test_job_nightly_id():
    """Existe un job con id='nightly_alerts'."""
    job = scheduler.get_job("nightly_alerts")
    assert job is not None
    assert job.id == "nightly_alerts"


def test_job_periodic_id():
    """Existe un job con id='periodic_checks'."""
    job = scheduler.get_job("periodic_checks")
    assert job is not None
    assert job.id == "periodic_checks"


def test_nightly_trigger_hora():
    """El trigger del job nocturno es CronTrigger a las 02:00."""
    job = scheduler.get_job("nightly_alerts")
    trigger = job.trigger
    assert isinstance(trigger, CronTrigger)
    # Verificar que el campo hour tiene valor 2
    hour_field = trigger.fields[trigger.FIELD_NAMES.index("hour")]
    # El CronTrigger almacena las expresiones como objetos
    assert str(hour_field) == "2"


def test_periodic_intervalo():
    """El trigger del job periódico es IntervalTrigger de 30 min."""
    job = scheduler.get_job("periodic_checks")
    trigger = job.trigger
    assert isinstance(trigger, IntervalTrigger)
    # IntervalTrigger almacena el intervalo como timedelta
    assert trigger.interval_length == 30 * 60  # 30 minutos en segundos

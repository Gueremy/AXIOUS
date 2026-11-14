"""Guardrails for the one-time pilot approval configuration command."""

import sys

import pytest

from scripts import enable_pilot_entry_approval as command


def _responses(path, method, payload):
    if path == "/auth/login":
        return {"access_token": "test-access", "refresh_token": "test-refresh"}
    if path == "/api/v2/sesion":
        return {"organizacion": {"nombre": "SalmoTrack Piloto"},
                "usuario": {"rol": "super_admin"}, "permisos": []}
    if path == "/api/v2/movimientos/tipos":
        return [
            {"id": "entry", "codigo": "ENTRADA", "efecto_stock": "entrada",
             "activo": True, "requiere_aprobacion": method == "GET" and payload == "updated"},
            {"id": "exit", "codigo": "SALIDA", "efecto_stock": "salida",
             "activo": True, "requiere_aprobacion": False},
            {"id": "inactive", "codigo": "ENTRADA_INACTIVA", "efecto_stock": "entrada",
             "activo": False, "requiere_aprobacion": False},
        ]
    return None


def test_dry_run_does_not_modify_types(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["command"])
    monkeypatch.setattr(command.getpass, "getpass", lambda _: "test-password")

    def fake_request(base_url, path, *, method="GET", token=None, payload=None, form=False):
        calls.append((method, path))
        return _responses(path, method, payload)

    monkeypatch.setattr(command, "request_json", fake_request)
    command.main()
    assert not any(method == "PATCH" for method, _ in calls)
    assert ("POST", "/auth/logout") in calls


def test_apply_updates_only_active_entries(monkeypatch):
    calls = []
    updated = False
    monkeypatch.setattr(sys, "argv", ["command", "--apply"])
    monkeypatch.setattr(command.getpass, "getpass", lambda _: "test-password")

    def fake_request(base_url, path, *, method="GET", token=None, payload=None, form=False):
        nonlocal updated
        calls.append((method, path, payload))
        if method == "PATCH":
            updated = True
            return {"requiere_aprobacion": True}
        if path == "/api/v2/movimientos/tipos" and updated:
            result = _responses(path, method, "updated")
            result[0]["requiere_aprobacion"] = True
            return result
        return _responses(path, method, payload)

    monkeypatch.setattr(command, "request_json", fake_request)
    command.main()
    assert [(path, payload) for method, path, payload in calls if method == "PATCH"] == [
        ("/api/v2/movimientos/tipos/entry", {"requiere_aprobacion": True})
    ]


def test_rejects_wrong_organization_before_patch(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["command", "--apply", "--expected-org", "Otra organización"])
    monkeypatch.setattr(command.getpass, "getpass", lambda _: "test-password")

    def fake_request(base_url, path, *, method="GET", token=None, payload=None, form=False):
        calls.append((method, path))
        return _responses(path, method, payload)

    monkeypatch.setattr(command, "request_json", fake_request)
    with pytest.raises(RuntimeError, match="Organización inesperada"):
        command.main()
    assert not any(method == "PATCH" for method, _ in calls)
    assert ("POST", "/auth/logout") in calls

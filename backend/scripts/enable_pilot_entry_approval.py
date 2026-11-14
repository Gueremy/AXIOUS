"""Enable approval for the pilot organization's entry movement types.

Run without --apply to inspect the current configuration. The script uses the
existing admin API, scopes changes to the signed-in organization, and never
stores credentials or tokens.
"""

import argparse
import getpass
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_API_URL = "https://salmotrack-v3-api-qq8r.onrender.com"


def request_json(base_url, path, *, method="GET", token=None, payload=None, form=False):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        if form:
            data = urlencode(payload).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as error:
        try:
            detail = json.loads(error.read()).get("detail", "Error de API")
        except (ValueError, AttributeError):
            detail = "Error de API"
        raise RuntimeError(f"{path}: HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"No se pudo conectar a {base_url}: {error.reason}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--email", default="pruebasadmin@gmail.com")
    parser.add_argument("--expected-org", default="SalmoTrack Piloto")
    parser.add_argument("--apply", action="store_true", help="Aplicar el cambio; sin esta opción solo se muestra")
    args = parser.parse_args()
    base_url = args.api_url.rstrip("/")
    if not base_url.startswith("https://"):
        parser.error("La API debe usar HTTPS")

    password = getpass.getpass(f"Contraseña de {args.email}: ")
    auth = request_json(base_url, "/auth/login", method="POST",
                        payload={"username": args.email, "password": password}, form=True)
    password = None
    token = auth["access_token"]
    try:
        session = request_json(base_url, "/api/v2/sesion", token=token)
        org_name = session["organizacion"]["nombre"]
        if org_name != args.expected_org:
            raise RuntimeError(f"Organización inesperada: {org_name!r}")
        if "rbac:manage" not in session["permisos"] and session["usuario"]["rol"] != "super_admin":
            raise RuntimeError("La cuenta no puede configurar tipos de movimiento")

        types = request_json(base_url, "/api/v2/movimientos/tipos", token=token)
        entries = [item for item in types if item["activo"] and item["efecto_stock"] == "entrada"]
        if not entries:
            raise RuntimeError("No hay tipos de entrada activos para configurar")
        for item in entries:
            state = "requiere aprobación" if item["requiere_aprobacion"] else "aplicación directa"
            print(f"{item['codigo']}: {state}")

        if not args.apply:
            print("Vista previa: no se modificó ningún tipo. Usa --apply para activar la aprobación.")
            return

        for item in entries:
            if not item["requiere_aprobacion"]:
                request_json(base_url, f"/api/v2/movimientos/tipos/{item['id']}", method="PATCH",
                             token=token, payload={"requiere_aprobacion": True})
                print(f"Aprobación activada: {item['codigo']}")

        updated = request_json(base_url, "/api/v2/movimientos/tipos", token=token)
        remaining = [item["codigo"] for item in updated
                     if item["activo"] and item["efecto_stock"] == "entrada"
                     and not item["requiere_aprobacion"]]
        if remaining:
            raise RuntimeError(f"Siguen sin aprobación: {', '.join(remaining)}")
        print("Verificado: todas las entradas activas requieren aprobación.")
    finally:
        try:
            request_json(base_url, "/auth/logout", method="POST", token=token,
                         payload={"refresh_token": auth["refresh_token"]})
        except RuntimeError:
            print("Aviso: no se pudo revocar la sesión temporal.")


if __name__ == "__main__":
    main()

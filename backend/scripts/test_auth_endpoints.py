import urllib.request
import urllib.error
import urllib.parse
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def make_request(step_name, method, endpoint, payload=None, token=None):
    """ Función auxiliar para hacer peticiones a la API y formatear la salida """
    print(f"\n{'='*60}")
    print(f"[{step_name}] {method} {endpoint}")
    
    headers = {"Accept": "application/json"}
    data = None
    
    if payload is not None:
        if isinstance(payload, str): # Enviar como form-data
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = payload.encode('utf-8')
        else: # Enviar como JSON
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode('utf-8')
            
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
        
    req = urllib.request.Request(BASE_URL + endpoint, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            body = response.read().decode('utf-8')
            print(f"→ STATUS: {response.status} OK")
            
            if body:
                body_json = json.loads(body)
                
                # Truncar tokens largos para que sea legible en consola
                display_json = dict(body_json)
                if "access_token" in display_json:
                    display_json["access_token"] = display_json["access_token"][:15] + "... [TRUNCADO]"
                    display_json["refresh_token"] = display_json["refresh_token"][:15] + "... [TRUNCADO]"
                
                print(f"→ BODY:\n{json.dumps(display_json, indent=2)}")
                return body_json
            return None
            
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        print(f"→ STATUS: {e.code} ERROR")
        try:
            print(f"→ ERROR:\n{json.dumps(json.loads(body), indent=2)}")
        except json.JSONDecodeError:
            print(f"→ ERROR:\n{body}")
        return None

def run_all_tests():
    print("Iniciando batería de pruebas de Autenticación (Fase 2)...")
    time.sleep(1)
    
    # 1. Login exitoso
    form_data = urllib.parse.urlencode({"username": "admin@skretting.cl", "password": "Admin2026!"})
    login_res = make_request("1. Iniciar sesión", "POST", "/auth/login", payload=form_data)
    
    if not login_res:
        print("\n[!] Falló el login principal. Abortando el resto de las pruebas.")
        return
        
    access_token = login_res["access_token"]
    refresh_token = login_res["refresh_token"]

    # 2. Obtener Perfil (me)
    time.sleep(1)
    make_request("2. Mi perfil", "GET", "/auth/me", token=access_token)

    # 3. Intentar crear un usuario como Administrador
    time.sleep(1)
    register_payload = {
        "nombre": "Operario B",
        "email": f"operario{int(time.time())}@skretting.cl", # Email dinámico para que no de conflicto 409
        "password": "PasswordTest123!",
        "codigo_empleado": "OPE-002",
        "rol": "operario",
        "id_sede": None,
        "turno": "B"
    }
    make_request("3. Registrar usuario (solo admin)", "POST", "/auth/register", payload=register_payload, token=access_token)

    # 4. Refrescar el token por uno nuevo
    time.sleep(1)
    refresh_payload = {"refresh_token": refresh_token}
    refresh_res = make_request("4. Refrescar token", "POST", "/auth/refresh", payload=refresh_payload)
    
    if not refresh_res:
        print("\n[!] Falló el refresco de token.")
        return
        
    new_access_token = refresh_res["access_token"]
    new_refresh_token = refresh_res["refresh_token"]

    # 5. Cerrar sesión
    time.sleep(1)
    logout_payload = {"refresh_token": new_refresh_token}
    make_request("5. Cerrar sesión", "POST", "/auth/logout", payload=logout_payload, token=new_access_token)

    # Extra: Refrescar token ya revocado (Seguridad)
    time.sleep(1)
    make_request("Extra. Hack: Intentar usar un token revocado", "POST", "/auth/refresh", payload=logout_payload)
    
    print(f"\n{'='*60}")
    print("✅ Batería de pruebas completada exitosamente.")

if __name__ == "__main__":
    run_all_tests()

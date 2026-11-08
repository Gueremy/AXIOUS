# Verificación de SalmoTrack

Alcance y resultados: `IMPLEMENTATION_STATUS.md`. Frontend y backend son repositorios separados. Usar únicamente bases sintéticas desechables.

## Frontend

```powershell
Set-Location C:\Proyectos\salmotrack\frontend
npm.cmd test
npx.cmd tsc --noEmit -p tsconfig.app.json
npm.cmd run build
```

Si el lanzador npm del sandbox no encuentra npm-cli.js, se usó `node C:\nvm4w\nodejs\node_modules\npm\bin\npm-cli.js` en lugar de npm; no se modificó la instalación del usuario.

## Backend rápido

```powershell
Set-Location C:\Proyectos\salmotrack\backend\backend
$env:DATABASE_URL='sqlite+aiosqlite:///:memory:'
$env:DATABASE_URL_SYNC='sqlite:///:memory:'
$env:SECRET_KEY='local-test-only-key-not-production'
..\.venv\Scripts\python.exe -m pytest tests -q --disable-warnings
```

## Navegador: ambos repositorios

Con frontend y backend como carpetas hermanas:

```powershell
Set-Location C:\Proyectos\salmotrack\frontend
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

La configuración crea datos sintéticos en `backend/backend/.cache/browser-test.sqlite`, levanta la API de pruebas y sirve el build. El seeder y `scripts.browser_test_app` rechazan otras bases/entornos. Solo ese entry point deshabilita el límite de inicios de sesión para permitir múltiples contextos; `app.main:app` conserva el límite habitual.

Si Windows/sandbox deja colgado el cierre automático, administrar los servidores explícitamente. Primera terminal:

```powershell
Set-Location C:\Proyectos\salmotrack\backend\backend
$env:DATABASE_URL='sqlite+aiosqlite:///./.cache/browser-test.sqlite'
$env:DATABASE_URL_SYNC='sqlite:///./.cache/browser-test.sqlite'
$env:SECRET_KEY='browser-tests-only-not-production'
$env:ENVIRONMENT='test'
$env:CORS_ORIGINS='["http://localhost:4173"]'
..\.venv\Scripts\python.exe scripts/seed_browser_test.py
..\.venv\Scripts\python.exe -m uvicorn scripts.browser_test_app:app --host 127.0.0.1 --port 8000
```

Segunda terminal: ejecutar `npm.cmd run build` y `npm.cmd run preview -- --host localhost --port 4173` desde frontend. Tercera:

```powershell
Set-Location C:\Proyectos\salmotrack\frontend
$env:SALMOTRACK_E2E_EXTERNAL_SERVERS='1'
npx.cmd playwright test --reporter=list
```

La configuración detecta navegadores existentes en `frontend/.cache/playwright`; CI utiliza la instalación normal. El workflow `frontend/.github/workflows/browser-tests.yml` se ejecuta al hacer push a v3 y permite elegir manualmente la referencia del backend. CI e integración ya fueron ejecutados y aprobados en GitHub.

## PostgreSQL real

Se usaron binarios portables PostgreSQL 16.15 de la página EDB enlazada por PostgreSQL: https://www.enterprisedb.com/download-postgresql-binaries. No se instaló un servicio del sistema. Caché y datos están ignorados por Git.

Desde backend/backend, el clúster local ya inicializado puede arrancarse con:

```powershell
.\.cache\postgres\pgsql\bin\postgres.exe -D .cache/postgres/data -h 127.0.0.1 -p 55432
```

Otra terminal, desde la misma carpeta:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://test:salmotrack-local-test-only@127.0.0.1:55432/axious_v2_completion_test'
$env:DATABASE_URL_SYNC='postgresql://test:salmotrack-local-test-only@127.0.0.1:55432/axious_v2_completion_test'
$env:SECRET_KEY='local-test-only-key-not-production'
$env:ENVIRONMENT='test'
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic check
..\.venv\Scripts\python.exe -m pytest tests_postgres -q --disable-warnings
```

La contraseña anterior es exclusivamente de este clúster sintético. No reutilizarla en staging/producción. Las pruebas PostgreSQL se habilitan para la base dedicada `axious_v2_completion_test`; crean datos y roles de prueba. El clúster conserva datos entre ejecuciones y se detiene con:

```powershell
.\.cache\postgres\pgsql\bin\pg_ctl.exe -D .cache/postgres/data -m fast -w stop
```

Para otra instalación PostgreSQL, crear una base desechable con ese nombre y adaptar las URLs. El workflow backend también levanta PostgreSQL 16 desde cero. Configuración Power BI: `backend/backend/docs/power-bi.md`.

## Piloto v3 publicado

- Frontend: https://salmotrack-v3-qq8r.onrender.com
- API y salud: https://salmotrack-v3-api-qq8r.onrender.com/health
- Blueprint: https://dashboard.render.com/blueprint/exs-dboeitajnfac73elp0f0
- Rama frontend: https://github.com/Gueremy/salmonwise-inventory/tree/v3
- Rama backend: https://github.com/Gueremy/AXIOUS/tree/v3
- CI frontend: https://github.com/Gueremy/salmonwise-inventory/actions/runs/42525556110
- Integración navegador: https://github.com/Gueremy/salmonwise-inventory/actions/runs/42525556320

Despliegue separado aprobado por el usuario en `bravooreste's workspace`, con base nueva, sin cuentas ni datos de la instalación anterior. La organización SalmoTrack Piloto y el lector BI están creados. Para la primera cuenta de aplicación, utilizar `backend/scripts/bootstrap_v2_admin.py` con el slug existente `salmotrack-piloto` desde un entorno con acceso privado a esa base; no utilizar las credenciales sintéticas de las pruebas.

La base PostgreSQL gratuita vence el 8 de diciembre de 2026; el piloto no sustituye una instalación productiva persistente. La aplicación se conecta mediante la red privada de Render. El 8 de noviembre se habilitaron exclusivamente los 22 rangos IPv4 oficiales `PowerBI.SouthCentralUS` (Microsoft 2026-11-02), región confirmada por Power BI; revisar semanalmente.

Power BI: organización **SalmoTrack Piloto** y cuenta SQL de solo lectura creadas. Render verificó inicio de sesión SQL y consulta de las seis vistas con ese lector, sin tablas base/escritura. Contraseña en la variable generada `POWER_BI_PASSWORD` del servicio API, no publicada. CI backend del commit `4b0a5e4` aprobado: https://github.com/Gueremy/AXIOUS/actions/runs/42527614103.

Conexión **SalmoTrack Piloto v3** guardada en Power BI Service. Tras la entrada privada del usuario, se pulsó **Comprobar el estado** y la interfaz mostró **En línea**, el 8 de noviembre de 2026. Evidencia local: `power-bi-connection-online.jpg`. Página: https://app.powerbi.com/groups/me/gateways?experience=power-bi. No hay modelo semántico/informe ni actualización comprobada; la prueba acredita conectividad SQL desde Power BI.

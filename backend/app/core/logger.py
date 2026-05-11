"""
app/core/logger.py
Logger centralizado con mensajes en español legibles para supervisores no técnicos.
Los logs aparecen en el panel de Render y en la consola local.
"""
import logging
import sys
from typing import Optional


def setup_logging() -> logging.Logger:
    """Configura el formato del logger para Render y consola local."""
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    log = logging.getLogger("salmonera")
    log.setLevel(logging.INFO)
    if not log.handlers:
        log.addHandler(handler)
    log.propagate = False
    return log


logger = setup_logging()


# ─── Diccionarios compartidos ─────────────────────────────────────────────────

_TIPOS_MOVIMIENTO: dict[str, str] = {
    "entrada_proveedor": "entrada de proveedor",
    "salida_produccion": "salida a producción",
    "traslado_interno": "traslado interno",
    "ajuste_inventario": "ajuste de inventario",
    "devolucion": "devolución",
    "correccion": "corrección",
}

_ROLES: dict[str, str] = {
    "super_admin": "Super Administrador",
    "admin_sede": "Administrador de Sede",
    "jefe_bodega": "Jefe de Bodega",
    "bodeguero": "Bodeguero",
    "gerencia": "Gerencia",
    "readonly": "Solo Lectura",
}

_TIPOS_ALERTA: dict[str, str] = {
    "capacidad_critica": "🚨 Ocupación Crítica",
    "vencimiento_30_dias": "⏰ Próximo Vencimiento (30 días)",
    "vencimiento_7_dias": "🔴 Vencimiento Inminente (7 días)",
    "stock_minimo": "⚠️  Stock Bajo",
    "movimiento_fuera_horario": "🕐 Movimiento Fuera de Horario",
    "discrepancia_inventario": "🔍 Discrepancia de Inventario",
    "sin_movimiento_30_dias": "📭 Sin Movimiento",
    "cuarentena_activa": "🚨 Cuarentena Activa",
}


# ─── Autenticación ────────────────────────────────────────────────────────────

def log_inicio_sesion(nombre_usuario: str, email: str, ip: str) -> None:
    logger.info(
        f'✅ [INICIO SESIÓN] El usuario "{nombre_usuario}" ({email}) '
        f"inició sesión correctamente desde {ip}"
    )


def log_cierre_sesion(nombre_usuario: str, email: str) -> None:
    logger.info(
        f'👋 [CIERRE SESIÓN] El usuario "{nombre_usuario}" ({email}) cerró sesión'
    )


def log_fallo_login(
    email: str, ip: str, intento: int, max_intentos: int = 5
) -> None:
    logger.warning(
        f'⚠️  [ACCESO FALLIDO] Intento de inicio de sesión incorrecto para "{email}" '
        f"desde {ip} — intento {intento} de {max_intentos}"
    )


def log_cuenta_bloqueada(email: str, ip: str, minutos: int = 15) -> None:
    logger.warning(
        f'🔒 [CUENTA BLOQUEADA] La cuenta "{email}" fue bloqueada temporalmente '
        f"por {minutos} minutos tras múltiples intentos fallidos desde {ip}"
    )


# ─── Movimientos ──────────────────────────────────────────────────────────────

def log_movimiento_creado(
    nombre_usuario: str,
    tipo: str,
    cantidad: float,
    unidad: str,
    producto: str,
    container_codigo: str,
    sede_nombre: str,
    numero_lote: str,
) -> None:
    tipo_legible = _TIPOS_MOVIMIENTO.get(tipo, tipo)
    logger.info(
        f'📦 [MOVIMIENTO REGISTRADO] {nombre_usuario} registró una {tipo_legible} '
        f'de {cantidad} {unidad} de "{producto}" en el contenedor {container_codigo} '
        f"({sede_nombre}) — Lote: {numero_lote}"
    )


def log_movimiento_aprobado(
    nombre_aprobador: str,
    tipo: str,
    cantidad: float,
    unidad: str,
    producto: str,
    container_codigo: str,
    sede_nombre: str,
) -> None:
    tipo_legible = _TIPOS_MOVIMIENTO.get(tipo, tipo)
    logger.info(
        f'✅ [MOVIMIENTO APROBADO] {nombre_aprobador} aprobó una {tipo_legible} '
        f'de {cantidad} {unidad} de "{producto}" en {container_codigo} ({sede_nombre})'
    )


def log_movimiento_rechazado(
    nombre_aprobador: str,
    tipo: str,
    producto: str,
    container_codigo: str,
    motivo: str,
) -> None:
    tipo_legible = _TIPOS_MOVIMIENTO.get(tipo, tipo)
    logger.warning(
        f'❌ [MOVIMIENTO RECHAZADO] {nombre_aprobador} rechazó una {tipo_legible} '
        f'de "{producto}" en {container_codigo} — Motivo: {motivo}'
    )


# ─── Alertas ──────────────────────────────────────────────────────────────────

def log_alerta_creada(
    tipo_alerta: str,
    container_codigo: str,
    galpon_nombre: str,
    sede_nombre: str,
    detalle: str,
) -> None:
    tipo_legible = _TIPOS_ALERTA.get(tipo_alerta, f"Alerta: {tipo_alerta}")
    logger.warning(
        f"{tipo_legible} detectado en contenedor {container_codigo} "
        f"({galpon_nombre}, {sede_nombre}) — {detalle}"
    )


def log_alerta_resuelta(
    nombre_usuario: str,
    tipo_alerta: str,
    container_codigo: str,
    sede_nombre: str,
) -> None:
    tipo_legible = _TIPOS_ALERTA.get(tipo_alerta, tipo_alerta)
    logger.info(
        f'✅ [ALERTA RESUELTA] {nombre_usuario} marcó como resuelta la alerta '
        f'"{tipo_legible}" en {container_codigo} ({sede_nombre})'
    )


# ─── Usuarios ─────────────────────────────────────────────────────────────────

def log_usuario_creado(
    nombre_admin: str,
    nombre_nuevo_usuario: str,
    email: str,
    rol: str,
    sede_nombre: str,
) -> None:
    rol_legible = _ROLES.get(rol, rol)
    logger.info(
        f'👤 [USUARIO CREADO] {nombre_admin} creó el usuario "{nombre_nuevo_usuario}" '
        f"({email}) con rol {rol_legible} en {sede_nombre}"
    )


def log_usuario_desactivado(
    nombre_admin: str, nombre_usuario: str, email: str
) -> None:
    logger.warning(
        f'🔐 [USUARIO DESACTIVADO] {nombre_admin} desactivó la cuenta '
        f'de "{nombre_usuario}" ({email})'
    )


# ─── Inventario (contenedores y productos) ────────────────────────────────────

def log_producto_creado(
    nombre_usuario: str, nombre_producto: str, codigo: str
) -> None:
    logger.info(
        f'🏷️  [PRODUCTO REGISTRADO] {nombre_usuario} registró el producto '
        f'"{nombre_producto}" con código {codigo}'
    )


def log_container_creado(
    nombre_usuario: str,
    codigo: str,
    galpon_nombre: str,
    sede_nombre: str,
    capacidad: float,
    unidad: str,
) -> None:
    logger.info(
        f"📦 [CONTENEDOR CREADO] {nombre_usuario} creó el contenedor {codigo} "
        f"en {galpon_nombre} ({sede_nombre}) con capacidad de {capacidad} {unidad}"
    )


# ─── Scheduler ────────────────────────────────────────────────────────────────

def log_job_scheduler(descripcion: str, resultado: str) -> None:
    logger.info(f"🕐 [TAREA AUTOMÁTICA] {descripcion} — {resultado}")


def log_job_scheduler_error(descripcion: str, error: str) -> None:
    logger.error(f"❌ [ERROR TAREA AUTOMÁTICA] {descripcion} falló — {error}")


# ─── Sistema ──────────────────────────────────────────────────────────────────

def log_sistema_iniciado(version: str, entorno: str) -> None:
    logger.info(
        f"🚀 [SISTEMA INICIADO] Inventario Salmonera v{version} "
        f"iniciado correctamente en entorno {entorno}"
    )


def log_sistema_detenido() -> None:
    logger.info("🛑 [SISTEMA DETENIDO] El servidor fue detenido de forma controlada")


def log_error_inesperado(
    endpoint: str, error: str, usuario: Optional[str] = None
) -> None:
    quien = f" (usuario: {usuario})" if usuario else ""
    logger.error(
        f"❌ [ERROR DEL SISTEMA] Ocurrió un error inesperado en {endpoint}{quien} — "
        "Si persiste, contactar al administrador del sistema. "
        f"Detalle técnico: {error[:200]}"
    )

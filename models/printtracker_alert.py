# ================================================================================================
# MODELO: printtracker_alert.py - Sistema de Alertas PrintTracker
# Corregido: Email configurable a soporte, API real PrintTracker, timestamps naive
# ================================================================================================

from odoo import models, fields, api
import logging
import traceback
from datetime import datetime, timedelta, date
import json

_logger = logging.getLogger(__name__)


class PrintTrackerAlert(models.Model):
    _name = 'printtracker.alert'
    _description = 'Sistema de Alertas PrintTracker'
    _order = 'fecha_creacion desc, prioridad desc'
    _rec_name = 'display_name'

    # ==========================================
    # IDENTIFICACIÓN PRINCIPAL
    # ==========================================
    serie_equipo = fields.Char('Serie del Equipo', required=True, index=True)
    equipo_id = fields.Many2one(
        'alquiler', string='Equipo',
        compute='_compute_equipo_id', store=True, index=True
    )

    # ==========================================
    # TIPO Y CLASIFICACIÓN DE ALERTA
    # ==========================================
    tipo_alerta = fields.Selection([
        # Alertas internas (generadas por revisiones locales)
        ('suministro_bajo', 'Suministro Bajo'),
        ('suministro_critico', 'Suministro Crítico'),
        ('suministro_vacio', 'Suministro Vacío'),
        ('equipo_offline', 'Equipo Offline'),
        ('sin_lecturas', 'Sin Lecturas Recientes'),
        ('uso_anomalo_alto', 'Uso Anómalamente Alto'),
        ('uso_anomalo_bajo', 'Uso Anómalamente Bajo'),
        ('contador_decrece', 'Contador Decreció'),
        ('mantenimiento_debido', 'Mantenimiento Requerido'),
        ('error_sincronizacion', 'Error de Sincronización'),
        ('conflicto_datos', 'Conflicto en Datos'),
        # Alertas de API Events (PrintTracker Pro)
        ('paper_jam', 'Atasco de Papel'),
        ('device_error', 'Error de Dispositivo'),
        ('supply_replaced', 'Suministro Reemplazado'),
        ('supply_event', 'Evento de Suministro'),
        ('cover_open', 'Cubierta Abierta'),
        ('connectivity_issue', 'Problema de Conectividad'),
        ('device_event', 'Evento de Dispositivo'),
        ('custom', 'Personalizada'),
    ], string='Tipo de Alerta', required=True, index=True)

    prioridad = fields.Selection([
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
        ('urgente', 'Urgente'),
    ], string='Prioridad', required=True, default='media', index=True)

    # ==========================================
    # CONTENIDO DE LA ALERTA
    # ==========================================
    titulo = fields.Char('Título', required=True)
    descripcion = fields.Text('Descripción')
    mensaje_detallado = fields.Html('Mensaje Detallado')

    # ==========================================
    # FECHAS
    # ==========================================
    fecha_creacion = fields.Datetime('Fecha Creación', default=fields.Datetime.now, readonly=True)
    fecha_deteccion = fields.Datetime('Fecha Detección', help='Cuándo se detectó el problema')
    fecha_vencimiento = fields.Datetime('Fecha Vencimiento', help='Cuándo expira la alerta')

    # ==========================================
    # ESTADO DE LA ALERTA
    # ==========================================
    estado = fields.Selection([
        ('nueva', 'Nueva'),
        ('notificada', 'Notificada'),
        ('en_proceso', 'En Proceso'),
        ('resuelta', 'Resuelta'),
        ('cerrada', 'Cerrada'),
        ('ignorada', 'Ignorada'),
    ], string='Estado', default='nueva', index=True)

    # ==========================================
    # GESTIÓN Y RESOLUCIÓN
    # ==========================================
    asignado_a = fields.Many2one('res.users', string='Asignado A')
    resuelto_por = fields.Many2one('res.users', string='Resuelto Por')
    fecha_resolucion = fields.Datetime('Fecha Resolución')
    notas_resolucion = fields.Text('Notas de Resolución')

    # ==========================================
    # INFORMACIÓN ESPECÍFICA SEGÚN TIPO
    # ==========================================
    # Suministros
    suministro_id = fields.Many2one('printtracker.supply', string='Suministro Relacionado')
    porcentaje_suministro = fields.Float('Porcentaje Suministro (%)')

    # Equipos offline
    dias_sin_lecturas = fields.Integer('Días sin Lecturas')
    ultima_lectura = fields.Datetime('Última Lectura')

    # Contadores
    contador_actual = fields.Integer('Contador Actual')
    contador_anterior = fields.Integer('Contador Anterior')
    diferencia_contador = fields.Integer('Diferencia Contador')

    # ==========================================
    # CONFIGURACIÓN DE NOTIFICACIONES
    # ==========================================
    notificar_email = fields.Boolean('Notificar por Email', default=True)
    notificar_chatter = fields.Boolean('Notificar en Chatter', default=True)
    email_enviado = fields.Boolean('Email Enviado', readonly=True)
    chatter_enviado = fields.Boolean('Chatter Enviado', readonly=True)

    # ==========================================
    # CONTROL DE REPETICIÓN
    # ==========================================
    es_recurrente = fields.Boolean('Es Recurrente', default=False)
    frecuencia_revision = fields.Integer('Frecuencia Revisión (minutos)', default=60)
    ultima_revision = fields.Datetime('Última Revisión')
    contador_repeticiones = fields.Integer('Repeticiones', default=1)
    max_repeticiones = fields.Integer('Máximo Repeticiones', default=5)

    # ==========================================
    # ORIGEN DE DATOS
    # ==========================================
    origen_datos = fields.Selection([
        ('interno', 'Generado Internamente'),
        ('api_events', 'Event de PrintTracker API'),
    ], string='Origen de Datos', default='interno', required=True, index=True)

    # ==========================================
    # CAMPOS DE API EVENTS (PrintTracker Pro)
    # Estructura real del event:
    #   id, createdDate, modifiedDate, entityKey, installKey,
    #   deviceKey, deviceSerialNumber, timestamp, description,
    #   alertType, supplyKey, resolutionStatus, acknowledged, meterRead
    # ==========================================
    api_event_id = fields.Char(
        'Event ID de API', index=True,
        help='ID único del event de PrintTracker API'
    )
    api_event_type = fields.Char(
        'Tipo de Event API',
        help='alertType del event de PrintTracker API'
    )
    api_resolution_status = fields.Char(
        'Estado Resolución API',
        help='resolutionStatus del event (Open, Resolved, etc.)'
    )
    api_event_timestamp = fields.Datetime('Timestamp del Event API')
    api_supply_key = fields.Char(
        'Supply Key API',
        help='supplyKey del event (blackToner, cyanToner, etc.)'
    )
    api_device_key = fields.Char(
        'Device Key API',
        help='deviceKey del event en PrintTracker'
    )
    api_raw_data = fields.Text(
        'Datos Crudos de API',
        help='JSON completo del event para debugging'
    )

    # ==========================================
    # INFORMACIÓN DEL EQUIPO (CACHE)
    # ==========================================
    cliente_nombre = fields.Char('Cliente', compute='_compute_equipo_info', store=True)
    modelo_equipo = fields.Char('Modelo', compute='_compute_equipo_info', store=True)
    ubicacion_equipo = fields.Char('Ubicación', compute='_compute_equipo_info', store=True)

    # ==========================================
    # DISPLAY NAME
    # ==========================================
    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)

    # ==========================================
    # ACCIONES AUTOMÁTICAS
    # ==========================================
    accion_automatica = fields.Selection([
        ('ninguna', 'Ninguna'),
        ('crear_orden_compra', 'Crear Orden de Compra'),
        ('enviar_email_cliente', 'Enviar Email a Cliente'),
        ('crear_tarea', 'Crear Tarea'),
        ('notificar_tecnico', 'Notificar Técnico'),
    ], string='Acción Automática', default='ninguna')

    accion_ejecutada = fields.Boolean('Acción Ejecutada', default=False)
    resultado_accion = fields.Text('Resultado de Acción')

    # ==========================================
    # CONSTRAINTS
    # ==========================================
    _sql_constraints = [
        ('positive_percentage',
         'CHECK(porcentaje_suministro >= 0 AND porcentaje_suministro <= 100)',
         'Porcentaje de suministro debe estar entre 0 y 100'),
        ('positive_days',
         'CHECK(dias_sin_lecturas >= 0)',
         'Días sin lecturas debe ser positivo'),
        ('valid_repetitions_interno',
         "CHECK(origen_datos != 'interno' OR contador_repeticiones <= max_repeticiones)",
         'Contador repeticiones no puede exceder el máximo para alertas internas'),
        # Evita duplicados de events API (NULLs múltiples no violan UNIQUE en PostgreSQL)
        ('unique_api_event',
         'UNIQUE(api_event_id)',
         'No se puede procesar el mismo event de la API dos veces'),
    ]

    # ==========================================
    # COMPUTED FIELDS
    # ==========================================

    @api.depends('serie_equipo')
    def _compute_equipo_id(self):
        """Busca el equipo por serie."""
        for alert in self:
            if alert.serie_equipo:
                equipo = self.env['alquiler'].search([
                    ('serie', '=', alert.serie_equipo)
                ], limit=1)
                alert.equipo_id = equipo.id if equipo else False
            else:
                alert.equipo_id = False

    @api.depends('equipo_id')
    def _compute_equipo_info(self):
        """Cachea información básica del equipo."""
        for alert in self:
            if alert.equipo_id:
                equipo = alert.equipo_id
                alert.cliente_nombre = (
                    equipo.cliente_id.name
                    if hasattr(equipo, 'cliente_id') and equipo.cliente_id
                    else ''
                )
                alert.modelo_equipo = (
                    equipo.name.name
                    if hasattr(equipo, 'name') and equipo.name
                    else ''
                )
                alert.ubicacion_equipo = (
                    getattr(equipo, 'ubicacion', '') or
                    getattr(equipo, 'custom_location', '')
                )
            else:
                alert.cliente_nombre = ''
                alert.modelo_equipo = ''
                alert.ubicacion_equipo = ''

    @api.depends('tipo_alerta', 'serie_equipo', 'titulo', 'prioridad')
    def _compute_display_name(self):
        """Genera nombre descriptivo."""
        prioridad_icons = {
            'baja': '🔵', 'media': '🟡', 'alta': '🟠',
            'critica': '🔴', 'urgente': '🚨',
        }
        for alert in self:
            parts = []
            if alert.prioridad:
                parts.append(prioridad_icons.get(alert.prioridad, ''))
            if alert.serie_equipo:
                parts.append(alert.serie_equipo)
            if alert.tipo_alerta:
                tipo_display = dict(alert._fields['tipo_alerta'].selection).get(
                    alert.tipo_alerta, alert.tipo_alerta
                )
                parts.append(tipo_display)
            alert.display_name = " - ".join(parts) if parts else f"Alerta {alert.id or 'nueva'}"

    # ==========================================
    # HELPER: OBTENER EMAIL DE SOPORTE
    # ==========================================

    def _get_email_soporte(self):
        """
        Obtiene el email de soporte configurado en parámetros del sistema.
        Clave: printtracker.alert.email_destino
        Default: soporte@andescopiers.com.pe
        """
        config_params = self.env['ir.config_parameter'].sudo()
        return config_params.get_param(
            'printtracker.alert.email_destino',
            'soporte@andescopiers.com.pe'
        )

    # ==========================================
    # HELPER: PARSEAR TIMESTAMP DE API
    # ==========================================

    def _parse_api_timestamp(self, timestamp_str):
        """
        Convierte timestamp de API a datetime naive (sin timezone) para Odoo.
        Formato de la API: "2021-01-01T01:44:44.000Z"
        Odoo requiere datetimes naive (UTC).
        """
        if not timestamp_str:
            return fields.Datetime.now()
        try:
            # Limpiar el string
            ts = timestamp_str.replace('Z', '').strip()
            # Intentar con milisegundos
            if '.' in ts:
                return datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f')
            else:
                return datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
        except (ValueError, TypeError) as e:
            _logger.warning(f"⚠️ Error parseando timestamp '{timestamp_str}': {e}")
            return fields.Datetime.now()

    # ==========================================
    # CREAR ALERTAS: SUMINISTRO BAJO
    # ==========================================

    @api.model
    def crear_alerta_suministro_bajo(self, suministro_record):
        """Crea alerta para suministro bajo/crítico/vacío."""
        try:
            if not suministro_record.device_id or not suministro_record.device_id.serie:
                _logger.warning("⚠️ Suministro sin device_id o serie válida")
                return False

            serie_equipo = suministro_record.device_id.serie
            _logger.info(
                f"🎨 Procesando suministro {suministro_record.supply_type} "
                f"de {serie_equipo} ({suministro_record.percent_remaining:.1f}%)"
            )

            # Verificar alerta activa existente
            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', 'in', ['suministro_bajo', 'suministro_critico', 'suministro_vacio']),
                ('suministro_id', '=', suministro_record.id),
                ('origen_datos', '=', 'interno'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
            ], limit=1)

            if existing_alert:
                _logger.info(
                    f"🔄 Alerta existente: {existing_alert.display_name} "
                    f"(rep: {existing_alert.contador_repeticiones}/{existing_alert.max_repeticiones})"
                )

                if existing_alert.contador_repeticiones < existing_alert.max_repeticiones:
                    update_vals = {
                        'porcentaje_suministro': suministro_record.percent_remaining,
                        'contador_repeticiones': existing_alert.contador_repeticiones + 1,
                        'ultima_revision': fields.Datetime.now(),
                    }

                    # Escalamiento si empeoró
                    if suministro_record.percent_remaining <= 0 and existing_alert.tipo_alerta != 'suministro_vacio':
                        update_vals.update({
                            'tipo_alerta': 'suministro_vacio',
                            'prioridad': 'urgente',
                            'titulo': f"🚨 URGENTE: Suministro agotado - {suministro_record.display_name}",
                        })
                        _logger.error(f"🚨 Escalada a VACÍO: {existing_alert.display_name}")
                    elif suministro_record.percent_remaining < 5 and \
                            existing_alert.tipo_alerta not in ['suministro_critico', 'suministro_vacio']:
                        update_vals.update({
                            'tipo_alerta': 'suministro_critico',
                            'prioridad': 'critica',
                            'titulo': f"⚠️ CRÍTICO: Suministro agotándose - {suministro_record.display_name}",
                        })
                        _logger.warning(f"⬆️ Escalada a CRÍTICA: {existing_alert.display_name}")

                    existing_alert.write(update_vals)
                    return existing_alert
                else:
                    # Límite alcanzado
                    _logger.warning(f"🚨 Máximo repeticiones alcanzado: {existing_alert.display_name}")
                    existing_alert.write({
                        'estado': 'en_proceso',
                        'notas_resolucion': (
                            f'Máximo de {existing_alert.max_repeticiones} repeticiones alcanzado. '
                            f'Requiere atención manual. Último nivel: {suministro_record.percent_remaining:.1f}%'
                        ),
                    })
                    if suministro_record.percent_remaining > 5:
                        return existing_alert
                    # Si es crítico, crear nueva alerta

            # Determinar tipo y prioridad
            if suministro_record.percent_remaining <= 0:
                tipo_alerta = 'suministro_vacio'
                prioridad = 'urgente'
                titulo = f"🚨 URGENTE: Suministro agotado - {suministro_record.display_name}"
            elif suministro_record.percent_remaining < 5:
                tipo_alerta = 'suministro_critico'
                prioridad = 'critica'
                titulo = f"⚠️ CRÍTICO: Suministro agotándose - {suministro_record.display_name}"
            else:
                tipo_alerta = 'suministro_bajo'
                prioridad = 'alta'
                titulo = f"⚠️ Suministro bajo - {suministro_record.display_name}"

            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': tipo_alerta,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': (
                    f"El suministro {suministro_record.supply_type} "
                    f"{suministro_record.supply_color or ''} "
                    f"está al {suministro_record.percent_remaining:.1f}%"
                ),
                'suministro_id': suministro_record.id,
                'porcentaje_suministro': suministro_record.percent_remaining,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'accion_automatica': 'crear_orden_compra' if suministro_record.percent_remaining < 10 else 'ninguna',
            })

            _logger.info(f"🚨 Nueva alerta suministro: {nueva_alerta.display_name}")
            return nueva_alerta

        except Exception as e:
            _logger.error(f"❌ Error creando alerta suministro: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    # ==========================================
    # CREAR ALERTAS: EQUIPO OFFLINE
    # ==========================================

    @api.model
    def crear_alerta_equipo_offline(self, serie_equipo, dias_sin_lecturas, ultima_lectura=None):
        """Crea alerta para equipo offline."""
        try:
            _logger.info(f"📵 Procesando equipo offline: {serie_equipo} ({dias_sin_lecturas} días)")

            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', '=', 'equipo_offline'),
                ('origen_datos', '=', 'interno'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
            ], limit=1)

            if existing_alert:
                if existing_alert.contador_repeticiones < existing_alert.max_repeticiones:
                    update_vals = {
                        'dias_sin_lecturas': dias_sin_lecturas,
                        'contador_repeticiones': existing_alert.contador_repeticiones + 1,
                        'ultima_revision': fields.Datetime.now(),
                    }

                    # Escalamiento según días
                    if dias_sin_lecturas >= 14 and existing_alert.prioridad != 'urgente':
                        update_vals.update({
                            'prioridad': 'urgente',
                            'titulo': f"🚨 URGENTE: Equipo offline {dias_sin_lecturas} días - {serie_equipo}",
                        })
                    elif dias_sin_lecturas >= 7 and existing_alert.prioridad not in ['critica', 'urgente']:
                        update_vals.update({
                            'prioridad': 'critica',
                            'titulo': f"🔴 CRÍTICO: Equipo offline {dias_sin_lecturas} días - {serie_equipo}",
                        })

                    existing_alert.write(update_vals)
                    return existing_alert
                else:
                    # Límite alcanzado - escalar
                    existing_alert.write({
                        'prioridad': 'urgente',
                        'estado': 'en_proceso',
                        'notas_resolucion': (
                            f'Equipo offline {dias_sin_lecturas} días. '
                            f'Máximo repeticiones alcanzado. Requiere intervención técnica urgente.'
                        ),
                        'accion_automatica': 'notificar_tecnico',
                    })
                    return existing_alert

            # Determinar prioridad según días
            if dias_sin_lecturas >= 14:
                prioridad = 'urgente'
                titulo = f"🚨 URGENTE: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
            elif dias_sin_lecturas >= 7:
                prioridad = 'critica'
                titulo = f"🔴 CRÍTICO: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
            elif dias_sin_lecturas >= 3:
                prioridad = 'alta'
                titulo = f"📵 Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
            else:
                prioridad = 'media'
                titulo = f"📵 Equipo offline {dias_sin_lecturas} días - {serie_equipo}"

            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': 'equipo_offline',
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': (
                    f"El equipo no ha reportado lecturas en {dias_sin_lecturas} días. "
                    f"Última lectura: {ultima_lectura or 'No disponible'}"
                ),
                'dias_sin_lecturas': dias_sin_lecturas,
                'ultima_lectura': ultima_lectura,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'accion_automatica': 'notificar_tecnico' if dias_sin_lecturas >= 3 else 'ninguna',
            })

            _logger.info(f"📵 Nueva alerta offline: {nueva_alerta.display_name}")
            return nueva_alerta

        except Exception as e:
            _logger.error(f"❌ Error creando alerta offline: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    # ==========================================
    # CREAR ALERTAS: USO ANÓMALO
    # ==========================================

    @api.model
    def crear_alerta_uso_anomalo(self, serie_equipo, tipo_anomalia, contador_actual, contador_anterior):
        """Crea alerta para uso anómalo (muy alto o muy bajo)."""
        try:
            diferencia = contador_actual - contador_anterior

            if tipo_anomalia == 'alto':
                tipo_alerta = 'uso_anomalo_alto'
                titulo = f"📈 Uso anómalamente alto - {serie_equipo}"
                descripcion = f"Incremento de {diferencia:,} páginas en un día (mucho mayor al promedio)"
                prioridad = 'media'
            else:
                tipo_alerta = 'uso_anomalo_bajo'
                titulo = f"📉 Uso anómalamente bajo - {serie_equipo}"
                descripcion = f"Incremento de solo {diferencia:,} páginas (muy por debajo del promedio)"
                prioridad = 'baja'

            # Verificar alerta similar reciente (últimos 7 días)
            fecha_limite = datetime.now() - timedelta(days=7)
            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', '=', tipo_alerta),
                ('origen_datos', '=', 'interno'),
                ('fecha_creacion', '>=', fecha_limite),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
            ], limit=1)

            if existing_alert:
                _logger.info(f"⚠️ Alerta uso anómalo similar reciente: {existing_alert.display_name}")
                return existing_alert

            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': tipo_alerta,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': descripcion,
                'contador_actual': contador_actual,
                'contador_anterior': contador_anterior,
                'diferencia_contador': diferencia,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
            })

            _logger.info(f"📊 Nueva alerta uso anómalo: {nueva_alerta.display_name}")
            return nueva_alerta

        except Exception as e:
            _logger.error(f"❌ Error creando alerta uso anómalo: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    # ==========================================
    # CREAR ALERTAS: CONTADOR DECRECE
    # ==========================================

    @api.model
    def crear_alerta_contador_decrece(self, serie_equipo, tipo_contador, valor_actual, valor_anterior):
        """Crea alerta cuando un contador decrece (posible reset o error)."""
        try:
            diferencia = valor_anterior - valor_actual
            _logger.warning(f"⬇️ Contador decrece: {serie_equipo} - {tipo_contador} ({diferencia:,})")

            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': 'contador_decrece',
                'prioridad': 'alta',
                'titulo': f"⬇️ Contador decreció - {serie_equipo}",
                'descripcion': (
                    f"El contador {tipo_contador} decreció de {valor_anterior:,} "
                    f"a {valor_actual:,} (-{diferencia:,}). Posible reset o error."
                ),
                'contador_actual': valor_actual,
                'contador_anterior': valor_anterior,
                'diferencia_contador': -diferencia,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'accion_automatica': 'notificar_tecnico',
            })

            _logger.warning(f"⬇️ Nueva alerta contador decrece: {nueva_alerta.display_name}")
            return nueva_alerta

        except Exception as e:
            _logger.error(f"❌ Error creando alerta contador decrece: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    # ==========================================
    # CREAR ALERTAS: DESDE API EVENT
    # Estructura real del event de PrintTracker:
    # {
    #   "id": "000000000000000000000006",
    #   "createdDate": "2021-01-01T01:44:44.000Z",
    #   "modifiedDate": "2021-01-01T01:44:44.000Z",
    #   "entityKey": "000000000000000000000002",
    #   "installKey": "000000000000000000000003",
    #   "deviceKey": "000000000000000000000006",
    #   "deviceSerialNumber": "SN12345",
    #   "timestamp": "2021-01-01T01:44:44.000Z",
    #   "description": "A black toner was replaced",
    #   "alertType": null,
    #   "supplyKey": "blackToner",
    #   "resolutionStatus": "Open",
    #   "acknowledged": { "timestamp": "...", "note": "...", "userKey": "...", "userName": "..." },
    #   "meterRead": { ... }
    # }
    # ==========================================

    @api.model
    def crear_alerta_desde_api_event(self, event_data, device_serial):
        """
        Crea alerta desde un event de PrintTracker Pro API.
        Siempre crea nueva alerta (sin límites de repetición para events de API).
        """
        try:
            event_id = event_data.get('id')
            _logger.info(f"📋 Procesando API event: {event_id} para {device_serial}")

            # Verificar duplicado
            existing_alert = self.search([
                ('api_event_id', '=', event_id)
            ], limit=1)

            if existing_alert:
                _logger.info(f"⚠️ Event ya procesado: {event_id}")
                return existing_alert

            # Clasificar el event
            tipo_alerta, prioridad = self._clasificar_event_api(event_data)

            # Generar título
            titulo = self._generar_titulo_event(event_data, device_serial)

            # Parsear timestamp (naive para Odoo)
            event_timestamp = self._parse_api_timestamp(event_data.get('timestamp'))

            nueva_alerta = self.create({
                'serie_equipo': device_serial,
                'tipo_alerta': tipo_alerta,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': event_data.get('description', 'Event de PrintTracker Pro'),
                'fecha_deteccion': event_timestamp,
                'origen_datos': 'api_events',
                # Campos de API
                'api_event_id': event_data.get('id'),
                'api_event_type': event_data.get('alertType'),
                'api_resolution_status': event_data.get('resolutionStatus'),
                'api_event_timestamp': event_timestamp,
                'api_supply_key': event_data.get('supplyKey'),
                'api_device_key': event_data.get('deviceKey'),
                'api_raw_data': json.dumps(event_data, default=str),
                # Sin límite de repetición para events API
                'contador_repeticiones': 1,
                'max_repeticiones': 9999,
                'accion_automatica': self._determinar_accion_event(event_data),
            })

            _logger.info(f"📋 Nueva alerta API event: {nueva_alerta.display_name}")
            return nueva_alerta

        except Exception as e:
            _logger.error(f"❌ Error creando alerta desde API event: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    # ==========================================
    # CLASIFICACIÓN DE EVENTS API
    # ==========================================

    def _clasificar_event_api(self, event_data):
        """
        Clasifica event de API para determinar tipo_alerta y prioridad.
        Basado en campos reales: description, alertType, supplyKey, resolutionStatus
        """
        try:
            description = (event_data.get('description', '')).lower()
            supply_key = event_data.get('supplyKey', '')

            # Atascos de papel
            if any(word in description for word in ['jam', 'atasco', 'trabamiento', 'paper jam']):
                return 'paper_jam', 'alta'

            # Suministros (usar supplyKey si está disponible)
            if supply_key or any(word in description for word in ['toner', 'ink', 'cartridge', 'drum']):
                if 'replaced' in description or 'cambio' in description or 'reemplaz' in description:
                    return 'supply_replaced', 'media'
                elif any(word in description for word in ['low', 'bajo', 'empty', 'agotado', 'depleted']):
                    return 'suministro_bajo', 'alta'
                else:
                    return 'supply_event', 'media'

            # Errores de dispositivo
            if any(word in description for word in ['error', 'fault', 'codigo', 'code']):
                return 'device_error', 'critica'

            # Cubierta abierta
            if any(word in description for word in ['cover', 'door', 'open', 'abierta', 'tapa']):
                return 'cover_open', 'baja'

            # Mantenimiento
            if any(word in description for word in ['maintenance', 'service', 'mantenimiento']):
                return 'mantenimiento_debido', 'alta'

            # Conectividad
            if any(word in description for word in ['offline', 'connection', 'network', 'red']):
                return 'connectivity_issue', 'alta'

            # Event genérico
            return 'device_event', 'media'

        except Exception as e:
            _logger.error(f"❌ Error clasificando event API: {e}")
            return 'device_event', 'media'

    def _generar_titulo_event(self, event_data, device_serial):
        """Genera título descriptivo para el event."""
        try:
            description = event_data.get('description', 'Event')
            desc_lower = description.lower()

            emojis = {
                'jam': '📄', 'toner': '🎨', 'ink': '🎨', 'drum': '🎨',
                'error': '⚠️', 'fault': '⚠️', 'maintenance': '🔧',
                'service': '🔧', 'cover': '🚪', 'door': '🚪',
                'offline': '📡', 'replaced': '🔄',
            }

            emoji = '📋'  # Default
            for keyword, icon in emojis.items():
                if keyword in desc_lower:
                    emoji = icon
                    break

            return f"{emoji} {device_serial} - {description}"

        except Exception as e:
            _logger.error(f"❌ Error generando título event: {e}")
            return f"📋 {device_serial} - Event PrintTracker"

    def _determinar_accion_event(self, event_data):
        """Determina acción automática según el event."""
        try:
            description = (event_data.get('description', '')).lower()

            if 'jam' in description or 'atasco' in description:
                return 'notificar_tecnico'
            elif ('toner' in description or 'ink' in description) and \
                 any(w in description for w in ['low', 'bajo', 'empty', 'agotado']):
                return 'crear_orden_compra'
            elif 'error' in description or 'fault' in description:
                return 'notificar_tecnico'
            elif 'maintenance' in description or 'service' in description:
                return 'crear_tarea'
            else:
                return 'ninguna'

        except Exception as e:
            _logger.error(f"❌ Error determinando acción event: {e}")
            return 'ninguna'

    # ==========================================
    # PROCESAR NOTIFICACIONES
    # Email siempre va a soporte@andescopiers.com.pe (configurable)
    # ==========================================

    def procesar_notificaciones(self):
        """Procesa notificaciones pendientes para esta alerta."""
        try:
            for alert in self:
                if alert.estado != 'nueva':
                    continue

                _logger.info(f"📬 Procesando notificaciones: {alert.display_name}")
                notificaciones_enviadas = 0

                # Email a soporte
                if alert.notificar_email and not alert.email_enviado:
                    if alert._enviar_notificacion_email():
                        alert.email_enviado = True
                        notificaciones_enviadas += 1

                # Chatter del equipo
                if alert.notificar_chatter and not alert.chatter_enviado:
                    if alert._enviar_notificacion_chatter():
                        alert.chatter_enviado = True
                        notificaciones_enviadas += 1

                # Acción automática
                if alert.accion_automatica != 'ninguna' and not alert.accion_ejecutada:
                    alert._ejecutar_accion_automatica()

                # Actualizar estado
                if notificaciones_enviadas > 0:
                    alert.estado = 'notificada'
                    _logger.info(f"✅ Alerta notificada: {alert.display_name}")

        except Exception as e:
            _logger.error(f"❌ Error procesando notificaciones: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")

    def _enviar_notificacion_email(self):
        """
        Envía notificación por email a soporte (configurable).
        YA NO envía al email del cliente/entidad.
        El destino se configura en: Ajustes > Parámetros del sistema
        Clave: printtracker.alert.email_destino
        Default: soporte@andescopiers.com.pe
        """
        try:
            email_soporte = self._get_email_soporte()

            if not email_soporte:
                _logger.warning("⚠️ No hay email de soporte configurado")
                return False

            _logger.info(f"📧 Enviando alerta a {email_soporte}: {self.display_name}")

            # Construir asunto
            prioridad_label = dict(self._fields['prioridad'].selection).get(self.prioridad, '')
            subject = f"[PrintTracker - {prioridad_label.upper()}] {self.titulo}"

            # Construir cuerpo HTML
            body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px;">
                <h2 style="color: #333;">{self.titulo}</h2>
                <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold; width: 160px;">Equipo (Serie)</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.serie_equipo}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Cliente</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.cliente_nombre or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Modelo</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.modelo_equipo or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Ubicación</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.ubicacion_equipo or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Prioridad</td>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>{prioridad_label.upper()}</strong></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Tipo de Alerta</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{dict(self._fields['tipo_alerta'].selection).get(self.tipo_alerta, self.tipo_alerta)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Descripción</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.descripcion or 'N/A'}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Fecha Detección</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.fecha_deteccion or 'N/A'}</td>
                    </tr>
            """

            # Info adicional según tipo
            if self.suministro_id:
                body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Suministro</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.suministro_id.display_name} ({self.porcentaje_suministro:.1f}%)</td>
                    </tr>
                """

            if self.dias_sin_lecturas:
                body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Días sin lecturas</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.dias_sin_lecturas}</td>
                    </tr>
                """

            if self.origen_datos == 'api_events':
                body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Origen</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">Event PrintTracker API</td>
                    </tr>
                """
                if self.api_event_type:
                    body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Alert Type</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.api_event_type}</td>
                    </tr>
                    """
                if self.api_supply_key:
                    body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Supply Key</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.api_supply_key}</td>
                    </tr>
                    """
                if self.api_resolution_status:
                    body += f"""
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Estado Event</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{self.api_resolution_status}</td>
                    </tr>
                    """

            body += """
                </table>
                <p style="color: #666; font-size: 12px; margin-top: 20px;">
                    Este es un mensaje automático del sistema de alertas PrintTracker de Andes Copiers.
                </p>
            </div>
            """

            # Enviar email
            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_to': email_soporte,
                'email_from': self.env.company.email or 'noreply@andescopiers.com.pe',
                'reply_to': self.env.company.email or 'noreply@andescopiers.com.pe',
            }

            mail = self.env['mail.mail'].create(mail_values)
            mail.send()

            _logger.info(f"✅ Email enviado a {email_soporte}: {self.display_name}")
            return True

        except Exception as e:
            _logger.error(f"❌ Error enviando email: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _enviar_notificacion_chatter(self):
        """Envía notificación en el chatter del equipo."""
        try:
            if not self.equipo_id:
                _logger.warning(f"⚠️ Sin equipo para chatter: {self.serie_equipo}")
                return False

            _logger.info(f"💬 Chatter del equipo: {self.equipo_id.name}")

            mensaje = f"""
            🚨 <strong>{self.titulo}</strong><br/>
            📅 <strong>Fecha:</strong> {self.fecha_deteccion}<br/>
            ⚡ <strong>Prioridad:</strong> {self.prioridad.upper()}<br/>
            📝 <strong>Descripción:</strong> {self.descripcion}<br/>
            """

            if self.suministro_id:
                mensaje += (
                    f"🎨 <strong>Suministro:</strong> {self.suministro_id.display_name} "
                    f"({self.porcentaje_suministro:.1f}%)<br/>"
                )

            if self.origen_datos == 'api_events':
                mensaje += "📋 <strong>Origen:</strong> Event PrintTracker API<br/>"
                if self.api_event_type:
                    mensaje += f"🔧 <strong>Alert Type:</strong> {self.api_event_type}<br/>"
                if self.api_supply_key:
                    mensaje += f"🎨 <strong>Supply:</strong> {self.api_supply_key}<br/>"

            self.equipo_id.message_post(
                body=mensaje,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            _logger.info("✅ Chatter enviado")
            return True

        except Exception as e:
            _logger.error(f"❌ Error enviando chatter: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _ejecutar_accion_automatica(self):
        """Ejecuta la acción automática configurada."""
        try:
            _logger.info(f"⚡ Acción automática '{self.accion_automatica}': {self.display_name}")

            if self.accion_automatica == 'crear_orden_compra' and self.suministro_id:
                resultado = self.suministro_id.action_create_purchase_order()
                self.accion_ejecutada = True
                self.resultado_accion = f"Orden de compra creada: {resultado}"
                _logger.info("🛒 Orden de compra creada")

            elif self.accion_automatica == 'crear_tarea':
                tarea = self.env['project.task'].create({
                    'name': f"Resolver: {self.titulo}",
                    'description': self.descripcion,
                    'user_ids': [(6, 0, [self.asignado_a.id])] if self.asignado_a else [],
                    'priority': '1' if self.prioridad in ['critica', 'urgente'] else '0',
                })
                self.accion_ejecutada = True
                self.resultado_accion = f"Tarea creada: {tarea.name}"
                _logger.info(f"📋 Tarea creada: {tarea.name}")

            elif self.accion_automatica == 'notificar_tecnico':
                # Enviar email a soporte (mismo destino configurable)
                email_soporte = self._get_email_soporte()
                if email_soporte:
                    self.env['mail.message'].create({
                        'message_type': 'notification',
                        'subject': f"🔧 Alerta Técnica: {self.titulo}",
                        'body': (
                            f"<p><strong>Equipo:</strong> {self.serie_equipo}</p>"
                            f"<p><strong>Descripción:</strong> {self.descripcion}</p>"
                            f"<p><strong>Prioridad:</strong> {self.prioridad.upper()}</p>"
                        ),
                    })
                    self.accion_ejecutada = True
                    self.resultado_accion = f"Técnico notificado en: {email_soporte}"
                    _logger.info(f"✅ Técnico notificado: {email_soporte}")

        except Exception as e:
            _logger.error(f"❌ Error ejecutando acción automática: {e}")
            self.resultado_accion = f"Error: {str(e)}"
            _logger.error(f"Traceback: {traceback.format_exc()}")

    # ==========================================
    # ACCIONES DE INTERFAZ
    # ==========================================

    def action_resolver(self):
        """Acción manual para resolver alerta."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Resolver Alerta',
            'res_model': 'printtracker.alert.resolve.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_alert_id': self.id,
                'default_notas_resolucion': '',
            },
        }

    def action_asignar(self):
        """Acción para asignar alerta a un usuario."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar Alerta',
            'res_model': 'printtracker.alert.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_alert_id': self.id},
        }

    def marcar_como_resuelta(self, notas_resolucion=''):
        """Marca la alerta como resuelta."""
        self.write({
            'estado': 'resuelta',
            'resuelto_por': self.env.user.id,
            'fecha_resolucion': fields.Datetime.now(),
            'notas_resolucion': notas_resolucion,
        })
        _logger.info(f"✅ Alerta resuelta: {self.display_name} por {self.env.user.name}")

    def action_view_equipo(self):
        """Acción para ver el equipo relacionado."""
        self.ensure_one()
        if not self.equipo_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No se encontró equipo para esta serie',
                    'type': 'warning',
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'name': f'Equipo - {self.serie_equipo}',
            'res_model': 'alquiler',
            'res_id': self.equipo_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==========================================
    # UTILIDADES
    # ==========================================

    @api.model
    def limpiar_alertas_antiguas(self, dias=30):
        """Limpia alertas resueltas/cerradas/ignoradas antiguas."""
        try:
            fecha_limite = datetime.now() - timedelta(days=dias)
            _logger.info(f"🗑️ Limpiando alertas anteriores a: {fecha_limite}")

            alertas_antiguas = self.search([
                ('estado', 'in', ['resuelta', 'cerrada', 'ignorada']),
                ('fecha_creacion', '<', fecha_limite),
            ])

            count = len(alertas_antiguas)
            if count > 0:
                alertas_antiguas.unlink()
                _logger.info(f"✅ {count} alertas antiguas eliminadas")
            else:
                _logger.info("ℹ️ No hay alertas antiguas para eliminar")

            return count

        except Exception as e:
            _logger.error(f"❌ Error en limpieza de alertas: {e}")
            return 0

    @api.model
    def obtener_estadisticas_alertas(self, dias=7):
        """Obtiene estadísticas de alertas de los últimos N días."""
        try:
            fecha_inicio = datetime.now() - timedelta(days=dias)
            alertas = self.search([('fecha_creacion', '>=', fecha_inicio)])

            stats = {
                'total_alertas': len(alertas),
                'por_tipo': {},
                'por_prioridad': {},
                'por_estado': {},
                'por_origen': {},
                'resueltas': len(alertas.filtered(lambda a: a.estado == 'resuelta')),
                'pendientes': len(alertas.filtered(lambda a: a.estado in ['nueva', 'notificada', 'en_proceso'])),
                'equipos_con_alertas': len(set(alertas.mapped('serie_equipo'))),
            }

            # Por tipo
            for tipo in ['suministro_bajo', 'suministro_critico', 'equipo_offline',
                         'uso_anomalo_alto', 'contador_decrece', 'paper_jam',
                         'device_error', 'supply_event', 'supply_replaced']:
                count = len(alertas.filtered(lambda a, t=tipo: a.tipo_alerta == t))
                if count > 0:
                    stats['por_tipo'][tipo] = count

            # Por prioridad
            for prioridad in ['baja', 'media', 'alta', 'critica', 'urgente']:
                count = len(alertas.filtered(lambda a, p=prioridad: a.prioridad == p))
                if count > 0:
                    stats['por_prioridad'][prioridad] = count

            # Por estado
            for estado in ['nueva', 'notificada', 'en_proceso', 'resuelta', 'cerrada']:
                count = len(alertas.filtered(lambda a, e=estado: a.estado == e))
                if count > 0:
                    stats['por_estado'][estado] = count

            # Por origen
            for origen in ['interno', 'api_events']:
                count = len(alertas.filtered(lambda a, o=origen: a.origen_datos == o))
                if count > 0:
                    stats['por_origen'][origen] = count

            _logger.info(f"📊 Estadísticas: {stats['total_alertas']} alertas totales")
            return stats

        except Exception as e:
            _logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}
# ================================================================================================
# MODELO: printtracker_alert.py - Sistema de Alertas PrintTracker
# Email configurable vía ir.config_parameter: printtracker.alert.email_destino
# Timestamps naive para Odoo, campos alineados con API real PrintTracker
# ================================================================================================

from odoo import models, fields, api
import logging
import traceback
from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser
import json

_logger = logging.getLogger(__name__)


class PrintTrackerAlert(models.Model):
    _name = 'printtracker.alert'
    _description = 'Alertas PrintTracker'
    _order = 'fecha_creacion desc, prioridad desc'
    _rec_name = 'display_name'

    # ==========================================
    # IDENTIFICACIÓN
    # ==========================================
    serie_equipo = fields.Char('Serie del Equipo', required=True, index=True)
    equipo_id = fields.Many2one('alquiler', string='Equipo',
                                compute='_compute_equipo_id', store=True, index=True)

    # ==========================================
    # TIPO Y PRIORIDAD
    # ==========================================
    tipo_alerta = fields.Selection([
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
        ('baja', 'Baja'), ('media', 'Media'), ('alta', 'Alta'),
        ('critica', 'Crítica'), ('urgente', 'Urgente'),
    ], string='Prioridad', required=True, default='media', index=True)

    # ==========================================
    # CONTENIDO
    # ==========================================
    titulo = fields.Char('Título', required=True)
    descripcion = fields.Text('Descripción')
    mensaje_detallado = fields.Html('Mensaje Detallado')

    # ==========================================
    # FECHAS
    # ==========================================
    fecha_creacion = fields.Datetime('Fecha Creación', default=fields.Datetime.now, readonly=True)
    fecha_deteccion = fields.Datetime('Fecha Detección')
    fecha_vencimiento = fields.Datetime('Fecha Vencimiento')

    # ==========================================
    # ESTADO
    # ==========================================
    estado = fields.Selection([
        ('nueva', 'Nueva'), ('notificada', 'Notificada'),
        ('en_proceso', 'En Proceso'), ('resuelta', 'Resuelta'),
        ('cerrada', 'Cerrada'), ('ignorada', 'Ignorada'),
    ], string='Estado', default='nueva', index=True)

    # ==========================================
    # GESTIÓN
    # ==========================================
    asignado_a = fields.Many2one('res.users', string='Asignado A')
    resuelto_por = fields.Many2one('res.users', string='Resuelto Por')
    fecha_resolucion = fields.Datetime('Fecha Resolución')
    notas_resolucion = fields.Text('Notas de Resolución')

    # ==========================================
    # DATOS ESPECÍFICOS
    # ==========================================
    suministro_id = fields.Many2one('printtracker.supply', string='Suministro Relacionado')
    porcentaje_suministro = fields.Float('Porcentaje Suministro (%)')
    dias_sin_lecturas = fields.Integer('Días sin Lecturas')
    ultima_lectura = fields.Datetime('Última Lectura')
    contador_actual = fields.Integer('Contador Actual')
    contador_anterior = fields.Integer('Contador Anterior')
    diferencia_contador = fields.Integer('Diferencia Contador')

    # ==========================================
    # NOTIFICACIONES
    # ==========================================
    notificar_email = fields.Boolean('Notificar por Email', default=True)
    notificar_chatter = fields.Boolean('Notificar en Chatter', default=True)
    email_enviado = fields.Boolean('Email Enviado', readonly=True)
    chatter_enviado = fields.Boolean('Chatter Enviado', readonly=True)

    # ==========================================
    # REPETICIÓN Y CONTROL
    # ==========================================
    es_recurrente = fields.Boolean('Es Recurrente', default=False)
    frecuencia_revision = fields.Integer('Frecuencia Revisión (min)', default=60)
    ultima_revision = fields.Datetime('Última Revisión')
    contador_repeticiones = fields.Integer('Repeticiones', default=1)
    max_repeticiones = fields.Integer('Máximo Repeticiones', default=5)

    # ==========================================
    # ORIGEN
    # ==========================================
    origen_datos = fields.Selection([
        ('interno', 'Generado Internamente'),
        ('api_events', 'Event de PrintTracker API'),
    ], string='Origen', default='interno', required=True, index=True)

    # ==========================================
    # CAMPOS DE API EVENTS (PrintTracker real)
    # ==========================================
    api_event_id = fields.Char('Event ID API', index=True)
    api_event_type = fields.Char('Tipo Event API')
    api_resolution_status = fields.Char('Estado Resolución API')
    api_event_timestamp = fields.Datetime('Timestamp Event API')
    api_supply_key = fields.Char('Supply Key API')
    api_device_key = fields.Char('Device Key API')
    api_raw_data = fields.Text('Datos Crudos API')

    # ==========================================
    # INFO EQUIPO (cache)
    # ==========================================
    cliente_nombre = fields.Char('Cliente', compute='_compute_equipo_info', store=True)
    modelo_equipo = fields.Char('Modelo', compute='_compute_equipo_info', store=True)
    ubicacion_equipo = fields.Char('Ubicación', compute='_compute_equipo_info', store=True)

    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)

    # ==========================================
    # ACCIÓN AUTOMÁTICA
    # ==========================================
    accion_automatica = fields.Selection([
        ('ninguna', 'Ninguna'),
        ('crear_orden_compra', 'Crear Orden de Compra'),
        ('crear_tarea', 'Crear Tarea'),
        ('notificar_tecnico', 'Notificar Técnico'),
    ], string='Acción Automática', default='ninguna')
    accion_ejecutada = fields.Boolean('Acción Ejecutada', default=False)
    resultado_accion = fields.Text('Resultado de Acción')

    # ==========================================
    # CONSTRAINTS
    # ==========================================
    _sql_constraints = [
        ('positive_percentage', 'CHECK(porcentaje_suministro >= 0 AND porcentaje_suministro <= 100)',
         'Porcentaje debe estar entre 0 y 100'),
        ('positive_days', 'CHECK(dias_sin_lecturas >= 0)',
         'Días sin lecturas debe ser positivo'),
        ('unique_api_event', 'UNIQUE(api_event_id)',
         'Event de API ya procesado'),
    ]

    # ==========================================
    # COMPUTED FIELDS
    # ==========================================

    @api.depends('serie_equipo')
    def _compute_equipo_id(self):
        for alert in self:
            if alert.serie_equipo:
                equipo = self.env['alquiler'].search([('serie', '=', alert.serie_equipo)], limit=1)
                alert.equipo_id = equipo.id if equipo else False
            else:
                alert.equipo_id = False

    @api.depends('equipo_id')
    def _compute_equipo_info(self):
        for alert in self:
            if alert.equipo_id:
                eq = alert.equipo_id
                alert.cliente_nombre = eq.cliente_id.name if hasattr(eq, 'cliente_id') and eq.cliente_id else ''
                alert.modelo_equipo = eq.name.name if hasattr(eq, 'name') and eq.name else ''
                alert.ubicacion_equipo = getattr(eq, 'ubicacion', '') or getattr(eq, 'custom_location', '') or ''
            else:
                alert.cliente_nombre = ''
                alert.modelo_equipo = ''
                alert.ubicacion_equipo = ''

    @api.depends('serie_equipo', 'tipo_alerta', 'prioridad')
    def _compute_display_name(self):
        tipo_labels = dict(self._fields['tipo_alerta'].selection)
        prio_labels = dict(self._fields['prioridad'].selection)
        for alert in self:
            serie = alert.serie_equipo or 'N/A'
            tipo = tipo_labels.get(alert.tipo_alerta, alert.tipo_alerta or '')
            prio = prio_labels.get(alert.prioridad, alert.prioridad or '')
            alert.display_name = f"[{prio}] {serie} - {tipo}"

    # ==========================================
    # HELPER: EMAIL SOPORTE (configurable)
    # ==========================================
    def _get_email_soporte(self):
        """Obtiene email de soporte desde parámetro del sistema."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'printtracker.alert.email_destino', 'soporte@andescopiers.com.pe'
        )

    # ==========================================
    # HELPER: PARSE TIMESTAMP API → naive datetime
    # ==========================================
    @staticmethod
    def _parse_api_timestamp(timestamp_str):
        """
        Convierte timestamp de API a datetime naive (Odoo requiere naive UTC).
        Ejemplos API: '2024-01-15T10:30:00Z', '2024-01-15T10:30:00.000Z'
        """
        if not timestamp_str:
            return None
        try:
            dt = dateutil_parser.parse(timestamp_str)
            # Odoo requiere naive datetime (asume UTC)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            return None

    # ==========================================
    # CREAR ALERTAS - SUMINISTRO BAJO
    # ==========================================
    def crear_alerta_suministro_bajo(self, suministro):
        """
        Crea o actualiza alerta de suministro bajo.
        Si ya existe una activa para el mismo suministro, actualiza y escala.
        """
        try:
            serie = suministro.device_id.serie if suministro.device_id else None
            if not serie:
                return None

            percent = suministro.percent_remaining or 0

            # Determinar tipo y prioridad según porcentaje
            if percent <= 0:
                tipo = 'suministro_vacio'
                prioridad = 'urgente'
            elif percent < 5:
                tipo = 'suministro_critico'
                prioridad = 'critica'
            else:
                tipo = 'suministro_bajo'
                prioridad = 'alta'

            # Buscar alerta existente activa para este suministro
            existente = self.search([
                ('serie_equipo', '=', serie),
                ('suministro_id', '=', suministro.id),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                # Actualizar: incrementar repeticiones, escalar si empeoró
                vals = {
                    'ultima_revision': fields.Datetime.now(),
                    'porcentaje_suministro': percent,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                }

                # Escalar prioridad si empeoró
                prioridades = ['baja', 'media', 'alta', 'critica', 'urgente']
                if prioridades.index(prioridad) > prioridades.index(existente.prioridad):
                    vals['prioridad'] = prioridad
                    vals['tipo_alerta'] = tipo

                # Si llegó al máximo repeticiones → en_proceso
                if existente.contador_repeticiones + 1 >= existente.max_repeticiones:
                    vals['estado'] = 'en_proceso'

                existente.write(vals)
                _logger.debug(f"📝 Actualizada alerta suministro {serie} ({percent:.1f}%)")
                return existente

            # Crear nueva
            tipo_supply = dict(suministro._fields['supply_type'].selection).get(
                suministro.supply_type, suministro.supply_type)
            color_supply = dict(suministro._fields['supply_color'].selection).get(
                suministro.supply_color, '') if suministro.supply_color else ''

            titulo = f"Suministro {tipo} - {serie}"
            desc = (f"{tipo_supply} {color_supply} al {percent:.1f}% "
                    f"en equipo {serie}")

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': tipo,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': desc,
                'suministro_id': suministro.id,
                'porcentaje_suministro': percent,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
                'accion_automatica': 'crear_orden_compra' if percent < 5 else 'ninguna',
            })

            _logger.info(f"🆕 Alerta suministro: {serie} - {tipo_supply} {color_supply} ({percent:.1f}%)")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error crear alerta suministro: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - EQUIPO OFFLINE
    # ==========================================
    def crear_alerta_equipo_offline(self, serie, dias_offline, ultima_lectura):
        """
        Crea o actualiza alerta de equipo offline.
        Escala: 3+ días = alta, 7+ = crítica, 14+ = urgente
        """
        try:
            if not serie:
                return None

            # Prioridad por días
            if dias_offline >= 14:
                prioridad = 'urgente'
            elif dias_offline >= 7:
                prioridad = 'critica'
            else:
                prioridad = 'alta'

            existente = self.search([
                ('serie_equipo', '=', serie),
                ('tipo_alerta', '=', 'equipo_offline'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                vals = {
                    'ultima_revision': fields.Datetime.now(),
                    'dias_sin_lecturas': dias_offline,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                }
                prioridades = ['baja', 'media', 'alta', 'critica', 'urgente']
                if prioridades.index(prioridad) > prioridades.index(existente.prioridad):
                    vals['prioridad'] = prioridad

                if existente.contador_repeticiones + 1 >= existente.max_repeticiones:
                    vals['estado'] = 'en_proceso'

                existente.write(vals)
                return existente

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': 'equipo_offline',
                'prioridad': prioridad,
                'titulo': f"Equipo offline - {serie} ({dias_offline} días)",
                'descripcion': f"Equipo {serie} sin reportar hace {dias_offline} días. Última lectura: {ultima_lectura}",
                'dias_sin_lecturas': dias_offline,
                'ultima_lectura': ultima_lectura if isinstance(ultima_lectura, datetime) else None,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
            })

            _logger.info(f"🆕 Alerta offline: {serie} ({dias_offline} días)")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta offline: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - USO ANÓMALO
    # ==========================================
    def crear_alerta_uso_anomalo(self, serie, tipo_anomalia, contador_actual, contador_anterior):
        """tipo_anomalia: 'alto' o 'bajo'"""
        try:
            if not serie:
                return None

            tipo = f"uso_anomalo_{tipo_anomalia}"
            prioridad = 'alta' if tipo_anomalia == 'alto' else 'media'
            diferencia = abs(contador_actual - contador_anterior)

            existente = self.search([
                ('serie_equipo', '=', serie),
                ('tipo_alerta', '=', tipo),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                existente.write({
                    'ultima_revision': fields.Datetime.now(),
                    'contador_actual': contador_actual,
                    'contador_anterior': contador_anterior,
                    'diferencia_contador': diferencia,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                })
                return existente

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': tipo,
                'prioridad': prioridad,
                'titulo': f"Uso {tipo_anomalia} - {serie}",
                'descripcion': f"Incremento {'excesivo' if tipo_anomalia == 'alto' else 'muy bajo'}: "
                               f"{diferencia:,} páginas en equipo {serie}",
                'contador_actual': contador_actual,
                'contador_anterior': contador_anterior,
                'diferencia_contador': diferencia,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
            })

            _logger.info(f"🆕 Alerta uso {tipo_anomalia}: {serie} ({diferencia:,} págs)")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta uso anómalo: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - CONTADOR DECRECE
    # ==========================================
    def crear_alerta_contador_decrece(self, serie, tipo_contador, valor_actual, valor_anterior):
        """tipo_contador: 'B/N', 'Color', 'Scan'"""
        try:
            if not serie:
                return None

            diferencia = valor_anterior - valor_actual

            existente = self.search([
                ('serie_equipo', '=', serie),
                ('tipo_alerta', '=', 'contador_decrece'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('origen_datos', '=', 'interno'),
            ], limit=1)

            if existente:
                existente.write({
                    'ultima_revision': fields.Datetime.now(),
                    'contador_actual': valor_actual,
                    'contador_anterior': valor_anterior,
                    'diferencia_contador': diferencia,
                    'contador_repeticiones': existente.contador_repeticiones + 1,
                })
                return existente

            nueva = self.create({
                'serie_equipo': serie,
                'tipo_alerta': 'contador_decrece',
                'prioridad': 'critica' if diferencia > 10000 else 'alta',
                'titulo': f"Contador {tipo_contador} decreció - {serie}",
                'descripcion': f"Contador {tipo_contador} bajó de {valor_anterior:,} a {valor_actual:,} "
                               f"(dif: {diferencia:,}) en equipo {serie}",
                'contador_actual': valor_actual,
                'contador_anterior': valor_anterior,
                'diferencia_contador': diferencia,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',
                'max_repeticiones': 5,
            })

            _logger.info(f"🆕 Alerta contador decrece: {serie} {tipo_contador} ({diferencia:,})")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta contador: {e}\n{traceback.format_exc()}")
            return None

    # ==========================================
    # CREAR ALERTAS - DESDE API EVENT
    # ==========================================
    def crear_alerta_desde_api_event(self, event_data, device_serial):
        """
        Crea alerta desde un event de la API de PrintTracker.
        Campos del event: id, createdDate, modifiedDate, entityKey, installKey,
        deviceKey, deviceSerialNumber, timestamp, description, alertType,
        supplyKey, resolutionStatus, acknowledged, meterRead
        """
        try:
            event_id = event_data.get('id')
            if not event_id or not device_serial:
                return None

            # Verificar duplicado
            if self.search([('api_event_id', '=', event_id)], limit=1):
                return None

            # Clasificar event
            clasificacion = self._clasificar_event_api(event_data)

            # Parse timestamp
            ts_raw = event_data.get('timestamp') or event_data.get('createdDate')
            ts = self._parse_api_timestamp(ts_raw)

            nueva = self.create({
                'serie_equipo': device_serial,
                'tipo_alerta': clasificacion['tipo'],
                'prioridad': clasificacion['prioridad'],
                'titulo': f"{clasificacion['titulo']} - {device_serial}",
                'descripcion': event_data.get('description', 'Evento de PrintTracker API'),
                'fecha_deteccion': ts or fields.Datetime.now(),
                'origen_datos': 'api_events',
                'api_event_id': event_id,
                'api_event_type': event_data.get('alertType', ''),
                'api_resolution_status': event_data.get('resolutionStatus', ''),
                'api_event_timestamp': ts,
                'api_supply_key': event_data.get('supplyKey', ''),
                'api_device_key': event_data.get('deviceKey', ''),
                'api_raw_data': json.dumps(event_data, default=str)[:5000],
                'max_repeticiones': 9999,  # API events no tienen límite
            })

            _logger.info(f"🆕 Alerta API: {device_serial} - {clasificacion['tipo']} (event {event_id})")
            return nueva

        except Exception as e:
            _logger.error(f"❌ Error alerta API event: {e}\n{traceback.format_exc()}")
            return None

    def _clasificar_event_api(self, event_data):
        """Clasifica un event de la API según description/alertType/supplyKey."""
        desc = (event_data.get('description', '')).lower()
        alert_type = event_data.get('alertType', '') or ''
        supply_key = event_data.get('supplyKey', '') or ''

        # Atasco de papel
        if any(w in desc for w in ['jam', 'atasco', 'paper jam']):
            return {'tipo': 'paper_jam', 'prioridad': 'alta', 'titulo': 'Atasco de Papel'}

        # Suministro reemplazado
        if any(w in desc for w in ['replaced', 'reemplaz', 'installed', 'nuevo']):
            return {'tipo': 'supply_replaced', 'prioridad': 'media', 'titulo': 'Suministro Reemplazado'}

        # Suministro bajo (por supplyKey o descripción)
        if supply_key or any(w in desc for w in ['toner', 'ink', 'drum', 'supply', 'low']):
            if any(w in desc for w in ['empty', 'vacio', 'agotado', 'depleted', '0%']):
                return {'tipo': 'suministro_vacio', 'prioridad': 'urgente', 'titulo': 'Suministro Vacío'}
            if any(w in desc for w in ['critical', 'critico', 'very low']):
                return {'tipo': 'suministro_critico', 'prioridad': 'critica', 'titulo': 'Suministro Crítico'}
            if any(w in desc for w in ['low', 'bajo']):
                return {'tipo': 'suministro_bajo', 'prioridad': 'alta', 'titulo': 'Suministro Bajo'}
            if supply_key:
                return {'tipo': 'supply_event', 'prioridad': 'media', 'titulo': 'Evento de Suministro'}

        # Error de dispositivo
        if any(w in desc for w in ['error', 'fault', 'fallo', 'codigo']):
            return {'tipo': 'device_error', 'prioridad': 'critica', 'titulo': 'Error de Dispositivo'}

        # Cubierta abierta
        if any(w in desc for w in ['cover', 'door', 'tapa', 'cubierta', 'open']):
            return {'tipo': 'cover_open', 'prioridad': 'baja', 'titulo': 'Cubierta Abierta'}

        # Mantenimiento
        if any(w in desc for w in ['maintenance', 'mantenimiento', 'service']):
            return {'tipo': 'mantenimiento_debido', 'prioridad': 'alta', 'titulo': 'Mantenimiento Requerido'}

        # Conectividad
        if any(w in desc for w in ['offline', 'connection', 'connectivity', 'desconect']):
            return {'tipo': 'connectivity_issue', 'prioridad': 'alta', 'titulo': 'Problema de Conectividad'}

        # Genérico
        return {'tipo': 'device_event', 'prioridad': 'media', 'titulo': 'Evento de Dispositivo'}

    # ==========================================
    # NOTIFICACIONES
    # ==========================================
    def procesar_notificaciones(self):
        """Envía email a soporte + chatter en equipo."""
        for alert in self:
            try:
                if alert.notificar_email and not alert.email_enviado:
                    alert._enviar_notificacion_email()

                if alert.notificar_chatter and not alert.chatter_enviado:
                    alert._enviar_notificacion_chatter()

                # Ejecutar acción automática
                if alert.accion_automatica != 'ninguna' and not alert.accion_ejecutada:
                    alert._ejecutar_accion_automatica()

                # Cambiar estado
                if alert.estado == 'nueva':
                    alert.estado = 'notificada'

            except Exception as e:
                _logger.error(f"❌ Error notificación {alert.display_name}: {e}")

    def _enviar_notificacion_email(self):
        """
        Envía email a soporte (configurable).
        SIEMPRE a soporte, NUNCA al cliente/entidad.
        """
        self.ensure_one()
        try:
            email_destino = self._get_email_soporte()
            if not email_destino:
                _logger.warning("⚠️ Email soporte no configurado")
                return

            # Construir HTML del email
            html_body = self._construir_email_html()

            prioridad_label = dict(self._fields['prioridad'].selection).get(self.prioridad, self.prioridad)
            tipo_label = dict(self._fields['tipo_alerta'].selection).get(self.tipo_alerta, self.tipo_alerta)

            mail_values = {
                'subject': f"[{prioridad_label.upper()}] Alerta PrintTracker - {self.serie_equipo} - {tipo_label}",
                'body_html': html_body,
                'email_from': self.env.company.email or 'noreply@andescopiers.com.pe',
                'email_to': email_destino,
                'auto_delete': False,
            }

            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()

            self.email_enviado = True
            _logger.info(f"📧 Email enviado a {email_destino} para {self.serie_equipo}")

        except Exception as e:
            _logger.error(f"❌ Error email: {e}\n{traceback.format_exc()}")

    def _construir_email_html(self):
        """Construye HTML profesional para email."""
        self.ensure_one()
        prioridad_label = dict(self._fields['prioridad'].selection).get(self.prioridad, self.prioridad)
        tipo_label = dict(self._fields['tipo_alerta'].selection).get(self.tipo_alerta, self.tipo_alerta)

        # Color según prioridad
        colores = {
            'urgente': '#dc3545', 'critica': '#e74c3c',
            'alta': '#fd7e14', 'media': '#ffc107', 'baja': '#28a745',
        }
        color = colores.get(self.prioridad, '#6c757d')

        # Info adicional según tipo
        info_extra = ''
        if self.porcentaje_suministro:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Nivel Suministro</td><td style="padding:8px;border:1px solid #ddd;">{self.porcentaje_suministro:.1f}%</td></tr>'
        if self.dias_sin_lecturas:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Días Offline</td><td style="padding:8px;border:1px solid #ddd;">{self.dias_sin_lecturas}</td></tr>'
        if self.diferencia_contador:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Diferencia Contador</td><td style="padding:8px;border:1px solid #ddd;">{self.diferencia_contador:,}</td></tr>'
        if self.api_event_id:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Event ID</td><td style="padding:8px;border:1px solid #ddd;">{self.api_event_id}</td></tr>'
        if self.api_resolution_status:
            info_extra += f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Estado API</td><td style="padding:8px;border:1px solid #ddd;">{self.api_resolution_status}</td></tr>'

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:{color};color:white;padding:15px;border-radius:8px 8px 0 0;">
                <h2 style="margin:0;">🚨 Alerta PrintTracker - {prioridad_label.upper()}</h2>
            </div>
            <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
                <table style="width:100%;border-collapse:collapse;margin-bottom:15px;">
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;width:35%;">Equipo (Serie)</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.serie_equipo}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Cliente</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.cliente_nombre or 'N/A'}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Modelo</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.modelo_equipo or 'N/A'}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Ubicación</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.ubicacion_equipo or 'N/A'}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Tipo Alerta</td>
                        <td style="padding:8px;border:1px solid #ddd;">{tipo_label}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Prioridad</td>
                        <td style="padding:8px;border:1px solid #ddd;color:{color};font-weight:bold;">{prioridad_label}</td></tr>
                    <tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Fecha Detección</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.fecha_deteccion or self.fecha_creacion}</td></tr>
                    {info_extra}
                </table>
                <div style="background:#f8f9fa;padding:12px;border-radius:4px;margin-top:10px;">
                    <strong>Descripción:</strong><br/>{self.descripcion or 'Sin descripción adicional'}
                </div>
                <p style="color:#6c757d;font-size:12px;margin-top:15px;">
                    Origen: {self.origen_datos} | Alerta #{self.id or 'nueva'} |
                    Generado automáticamente por PrintTracker Alert System
                </p>
            </div>
        </div>
        """
        return html

    def _enviar_notificacion_chatter(self):
        """Publica notificación en el chatter del equipo."""
        self.ensure_one()
        try:
            if not self.equipo_id:
                return

            prioridad_label = dict(self._fields['prioridad'].selection).get(self.prioridad, self.prioridad)
            tipo_label = dict(self._fields['tipo_alerta'].selection).get(self.tipo_alerta, self.tipo_alerta)

            body = f"""
            <p><strong>🚨 Alerta PrintTracker [{prioridad_label}]</strong></p>
            <p><strong>Tipo:</strong> {tipo_label}</p>
            <p>{self.descripcion or ''}</p>
            """

            self.equipo_id.message_post(
                body=body,
                subject=f"Alerta: {tipo_label}",
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            self.chatter_enviado = True
            _logger.info(f"💬 Chatter en equipo {self.serie_equipo}")

        except Exception as e:
            _logger.error(f"❌ Error chatter: {e}")

    # ==========================================
    # ACCIONES AUTOMÁTICAS
    # ==========================================
    def _ejecutar_accion_automatica(self):
        """Ejecuta acción automática según configuración."""
        self.ensure_one()
        try:
            if self.accion_automatica == 'crear_orden_compra':
                self._accion_crear_orden_compra()
            elif self.accion_automatica == 'crear_tarea':
                self._accion_crear_tarea()
            elif self.accion_automatica == 'notificar_tecnico':
                self._accion_notificar_tecnico()
        except Exception as e:
            self.resultado_accion = f"Error: {e}"
            _logger.error(f"❌ Error acción automática: {e}")

    def _accion_crear_orden_compra(self):
        """Crea orden de compra si hay suministro y producto asociados."""
        self.ensure_one()
        if not self.suministro_id or not self.suministro_id.product_id:
            self.resultado_accion = "Sin suministro/producto asociado"
            return

        try:
            supply = self.suministro_id
            po = self.env['purchase.order'].create({
                'origin': f'Alerta PrintTracker - {self.serie_equipo}',
                'order_line': [(0, 0, {
                    'product_id': supply.product_id.id,
                    'name': f'{supply.product_id.name} - {self.serie_equipo}',
                    'product_qty': 1,
                    'price_unit': supply.supply_cost or supply.product_id.standard_price or 0,
                    'date_planned': fields.Datetime.now(),
                })],
            })
            self.accion_ejecutada = True
            self.resultado_accion = f"OC creada: {po.name}"
            _logger.info(f"📦 OC {po.name} creada para {self.serie_equipo}")
        except Exception as e:
            self.resultado_accion = f"Error OC: {e}"

    def _accion_crear_tarea(self):
        """Crea tarea en proyecto si está disponible."""
        self.ensure_one()
        try:
            if not hasattr(self.env, 'project.task'):
                self.resultado_accion = "Módulo project no instalado"
                return

            task = self.env['project.task'].create({
                'name': self.titulo,
                'description': self.descripcion or '',
            })
            self.accion_ejecutada = True
            self.resultado_accion = f"Tarea creada: {task.name}"
        except Exception as e:
            self.resultado_accion = f"Error tarea: {e}"

    def _accion_notificar_tecnico(self):
        """Envía email al equipo de soporte (no a todos los usuarios)."""
        self.ensure_one()
        try:
            email_soporte = self._get_email_soporte()
            if email_soporte:
                self._enviar_notificacion_email()
                self.accion_ejecutada = True
                self.resultado_accion = f"Notificación enviada a {email_soporte}"
        except Exception as e:
            self.resultado_accion = f"Error notificación: {e}"

    # ==========================================
    # ACCIONES MANUALES
    # ==========================================
    def action_marcar_resuelta(self):
        for alert in self:
            alert.write({
                'estado': 'resuelta',
                'resuelto_por': self.env.uid,
                'fecha_resolucion': fields.Datetime.now(),
            })
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': 'Alerta(s) marcada(s) como resuelta(s)', 'type': 'success'}}

    def action_marcar_en_proceso(self):
        for alert in self:
            alert.estado = 'en_proceso'

    def action_ignorar(self):
        for alert in self:
            alert.estado = 'ignorada'

    def action_reenviar_email(self):
        self.ensure_one()
        self.email_enviado = False
        self._enviar_notificacion_email()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': f'Email reenviado a {self._get_email_soporte()}', 'type': 'success'}}

    def action_resolver(self):
        """Botón 'Resolver' en la vista form."""
        return self.action_marcar_resuelta()

    def action_asignar(self):
        """Botón 'Asignar' en la vista form."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar Alerta',
            'res_model': 'printtracker.alert',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_view_equipo(self):
        """Botón 'Ver Equipo' en la vista form."""
        self.ensure_one()
        if not self.equipo_id:
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'message': 'No hay equipo vinculado', 'type': 'warning'}}
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
        """Elimina alertas resueltas/cerradas más antiguas que N días."""
        try:
            fecha_corte = datetime.now() - timedelta(days=dias)
            antiguas = self.search([
                ('estado', 'in', ['resuelta', 'cerrada', 'ignorada']),
                ('fecha_creacion', '<', fecha_corte),
            ])
            count = len(antiguas)
            antiguas.unlink()
            _logger.info(f"🗑️ {count} alertas antiguas eliminadas")
            return count
        except Exception as e:
            _logger.error(f"❌ Error limpieza: {e}")
            return 0

    @api.model
    def obtener_estadisticas_alertas(self):
        """Estadísticas generales de alertas."""
        try:
            activas = self.search([('estado', 'in', ['nueva', 'notificada', 'en_proceso'])])
            return {
                'total_activas': len(activas),
                'por_prioridad': {
                    p: len(activas.filtered(lambda a, pr=p: a.prioridad == pr))
                    for p in ['urgente', 'critica', 'alta', 'media', 'baja']
                },
                'por_tipo': {
                    t: len(activas.filtered(lambda a, tp=t: a.tipo_alerta == tp))
                    for t in set(activas.mapped('tipo_alerta'))
                },
                'por_origen': {
                    'interno': len(activas.filtered(lambda a: a.origen_datos == 'interno')),
                    'api_events': len(activas.filtered(lambda a: a.origen_datos == 'api_events')),
                },
                'equipos_afectados': len(set(activas.mapped('serie_equipo'))),
            }
        except Exception:
            return {}
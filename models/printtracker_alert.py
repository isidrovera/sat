from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date
import json
import requests

_logger = logging.getLogger(__name__)


class PrintTrackerAlert(models.Model):
    _name = 'printtracker.alert'
    _description = 'Sistema de Alertas PrintTracker'
    _order = 'fecha_creacion desc, prioridad desc'
    _rec_name = 'display_name'

    # Identificación principal
    serie_equipo = fields.Char('Serie del Equipo', required=True, index=True)
    equipo_id = fields.Many2one('alquiler', string='Equipo', 
                               compute='_compute_equipo_id', store=True, index=True)
    
    # Tipo y clasificación de alerta
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
        ('custom', 'Personalizada')
    ], string='Tipo de Alerta', required=True, index=True)
    
    prioridad = fields.Selection([
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
        ('urgente', 'Urgente')
    ], string='Prioridad', required=True, default='media', index=True)
    
    # Contenido de la alerta
    titulo = fields.Char('Título', required=True)
    descripcion = fields.Text('Descripción')
    mensaje_detallado = fields.Html('Mensaje Detallado')
    
    # Fechas importantes
    fecha_creacion = fields.Datetime('Fecha Creación', default=fields.Datetime.now, readonly=True)
    fecha_deteccion = fields.Datetime('Fecha Detección', help='Cuándo se detectó el problema')
    fecha_vencimiento = fields.Datetime('Fecha Vencimiento', help='Cuándo expira la alerta')
    
    # Estado de la alerta
    estado = fields.Selection([
        ('nueva', 'Nueva'),
        ('notificada', 'Notificada'),
        ('en_proceso', 'En Proceso'),
        ('resuelta', 'Resuelta'),
        ('cerrada', 'Cerrada'),
        ('ignorada', 'Ignorada')
    ], string='Estado', default='nueva', index=True)
    
    # Gestión y resolución
    asignado_a = fields.Many2one('res.users', string='Asignado A')
    resuelto_por = fields.Many2one('res.users', string='Resuelto Por')
    fecha_resolucion = fields.Datetime('Fecha Resolución')
    notas_resolucion = fields.Text('Notas de Resolución')
    
    # Información específica según tipo de alerta
    suministro_id = fields.Many2one('printtracker.supply', string='Suministro Relacionado')
    porcentaje_suministro = fields.Float('Porcentaje Suministro (%)')
    
    dias_sin_lecturas = fields.Integer('Días sin Lecturas')
    ultima_lectura = fields.Datetime('Última Lectura')
    
    contador_actual = fields.Integer('Contador Actual')
    contador_anterior = fields.Integer('Contador Anterior')
    diferencia_contador = fields.Integer('Diferencia Contador')
    
    # Configuración de notificaciones
    notificar_email = fields.Boolean('Notificar por Email', default=True)
    notificar_chatter = fields.Boolean('Notificar en Chatter', default=True)
    email_enviado = fields.Boolean('Email Enviado', readonly=True)
    chatter_enviado = fields.Boolean('Chatter Enviado', readonly=True)
    
    # Control de repetición
    es_recurrente = fields.Boolean('Es Recurrente', default=False)
    frecuencia_revision = fields.Integer('Frecuencia Revisión (minutos)', default=60)
    ultima_revision = fields.Datetime('Última Revisión')
    contador_repeticiones = fields.Integer('Repeticiones', default=1)
    max_repeticiones = fields.Integer('Máximo Repeticiones', default=5)
    
    # NUEVOS CAMPOS - ORIGEN DE DATOS Y API EVENTS
    origen_datos = fields.Selection([
        ('interno', 'Generado Internamente'),      # Suministros, offline, uso anómalo
        ('api_events', 'Event de PrintTracker API') # Todos los events de la API
    ], string='Origen de Datos', default='interno', required=True, index=True)
    
    # Campos específicos para events de API
    api_event_id = fields.Char('Event ID de API', index=True, 
                              help='ID único del event de PrintTracker API')
    api_event_type = fields.Char('Tipo de Event API',
                                help='alertType del event de PrintTracker API')
    api_resolution_status = fields.Char('Estado Resolución API',
                                       help='resolutionStatus del event')
    api_event_timestamp = fields.Datetime('Timestamp del Event API')
    api_supply_key = fields.Char('Supply Key API',
                                help='supplyKey del event de PrintTracker')
    
    # Metadatos adicionales del event
    api_raw_data = fields.Text('Datos Crudos de API', 
                              help='JSON completo del event para debugging')
    
    # Información del equipo (cache)
    cliente_nombre = fields.Char('Cliente', compute='_compute_equipo_info', store=True)
    modelo_equipo = fields.Char('Modelo', compute='_compute_equipo_info', store=True)
    ubicacion_equipo = fields.Char('Ubicación', compute='_compute_equipo_info', store=True)
    
    # Campo de display
    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)
    
    # Campos para acciones automaticas
    accion_automatica = fields.Selection([
        ('ninguna', 'Ninguna'),
        ('crear_orden_compra', 'Crear Orden de Compra'),
        ('enviar_email_cliente', 'Enviar Email a Cliente'),
        ('crear_tarea', 'Crear Tarea'),
        ('notificar_tecnico', 'Notificar Técnico')
    ], string='Acción Automática', default='ninguna')
    
    accion_ejecutada = fields.Boolean('Acción Ejecutada', default=False)
    resultado_accion = fields.Text('Resultado de Acción')
    
    # CONSTRAINTS MODIFICADOS
    _sql_constraints = [
        ('positive_percentage', 'CHECK(porcentaje_suministro >= 0 AND porcentaje_suministro <= 100)', 
         'Porcentaje de suministro debe estar entre 0 y 100'),
        ('positive_days', 'CHECK(dias_sin_lecturas >= 0)', 
         'Días sin lecturas debe ser positivo'),
        # CONSTRAINT MODIFICADO - Solo aplica a alertas internas
        ('valid_repetitions_interno', 
         'CHECK(origen_datos != \'interno\' OR contador_repeticiones <= max_repeticiones)', 
         'Contador repeticiones no puede exceder el máximo para alertas internas'),
        # NUEVO CONSTRAINT - Evita duplicados de events API
        ('unique_api_event', 
         'UNIQUE(api_event_id)', 
         'No se puede procesar el mismo event de la API dos veces')
    ]

    @api.depends('serie_equipo')
    def _compute_equipo_id(self):
        """Busca el equipo por serie"""
        for alert in self:
            if alert.serie_equipo:
                equipo = self.env['alquiler'].search([
                    ('serie', '=', alert.serie_equipo)
                ], limit=1)
                alert.equipo_id = equipo.id if equipo else False
                if equipo:
                    _logger.debug(f"🔍 Equipo encontrado para serie {alert.serie_equipo}: {equipo.name}")
                else:
                    _logger.warning(f"⚠️ No se encontró equipo para serie: {alert.serie_equipo}")
            else:
                alert.equipo_id = False

    @api.depends('equipo_id')
    def _compute_equipo_info(self):
        """Cachea información básica del equipo"""
        for alert in self:
            if alert.equipo_id:
                equipo = alert.equipo_id
                alert.cliente_nombre = equipo.cliente_id.name if hasattr(equipo, 'cliente_id') and equipo.cliente_id else ''
                alert.modelo_equipo = equipo.name.name if hasattr(equipo, 'name') and equipo.name else ''
                alert.ubicacion_equipo = getattr(equipo, 'ubicacion', '') or getattr(equipo, 'custom_location', '')
                _logger.debug(f"📋 Info equipo cacheada: {alert.serie_equipo} - {alert.cliente_nombre}")
            else:
                alert.cliente_nombre = ''
                alert.modelo_equipo = ''
                alert.ubicacion_equipo = ''

    @api.depends('tipo_alerta', 'serie_equipo', 'titulo', 'prioridad')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for alert in self:
            parts = []
            
            if alert.prioridad:
                prioridad_icon = {
                    'baja': '🔵',
                    'media': '🟡', 
                    'alta': '🟠',
                    'critica': '🔴',
                    'urgente': '🚨'
                }.get(alert.prioridad, '')
                parts.append(prioridad_icon)
            
            if alert.serie_equipo:
                parts.append(alert.serie_equipo)
            
            if alert.tipo_alerta:
                tipo_display = dict(alert._fields['tipo_alerta'].selection).get(alert.tipo_alerta, alert.tipo_alerta)
                parts.append(tipo_display)
            
            alert.display_name = " - ".join(parts) if parts else f"Alerta {alert.id or 'nueva'}"

    @api.model
    def crear_alerta_suministro_bajo(self, suministro_record):
        """
        Crea alerta para suministro bajo (CORREGIDO CON LOGS)
        """
        try:
            if not suministro_record.device_id or not suministro_record.device_id.serie:
                _logger.warning(f"⚠️ Suministro sin device_id o serie válida: {suministro_record}")
                return False
            
            serie_equipo = suministro_record.device_id.serie
            _logger.info(f"🎨 Procesando suministro {suministro_record.supply_type} del equipo {serie_equipo} ({suministro_record.percent_remaining:.1f}%)")
            
            # Verificar si ya existe alerta activa similar
            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', 'in', ['suministro_bajo', 'suministro_critico', 'suministro_vacio']),
                ('suministro_id', '=', suministro_record.id),
                ('origen_datos', '=', 'interno'),  # NUEVO: Solo alertas internas
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ], limit=1)
            
            if existing_alert:
                _logger.info(f"🔄 Alerta existente encontrada: {existing_alert.display_name} (rep: {existing_alert.contador_repeticiones}/{existing_alert.max_repeticiones})")
                
                # VERIFICAR LÍMITE antes de incrementar
                if existing_alert.contador_repeticiones < existing_alert.max_repeticiones:
                    update_vals = {
                        'porcentaje_suministro': suministro_record.percent_remaining,
                        'contador_repeticiones': existing_alert.contador_repeticiones + 1,
                        'ultima_revision': fields.Datetime.now()
                    }
                    
                    # Escalamiento si empeoró significativamente
                    if (suministro_record.percent_remaining <= 0 and existing_alert.tipo_alerta != 'suministro_vacio'):
                        update_vals.update({
                            'tipo_alerta': 'suministro_vacio',
                            'prioridad': 'urgente',
                            'titulo': f"🚨 URGENTE: Suministro agotado - {suministro_record.display_name}"
                        })
                        _logger.error(f"🚨 Alerta escalada a VACÍO: {existing_alert.display_name}")
                    elif (suministro_record.percent_remaining < 5 and existing_alert.tipo_alerta not in ['suministro_critico', 'suministro_vacio']):
                        update_vals.update({
                            'tipo_alerta': 'suministro_critico',
                            'prioridad': 'critica',
                            'titulo': f"⚠️ CRÍTICO: Suministro agotándose - {suministro_record.display_name}"
                        })
                        _logger.warning(f"⬆️ Alerta escalada a CRÍTICA: {existing_alert.display_name}")
                    
                    existing_alert.write(update_vals)
                    _logger.info(f"✅ Alerta actualizada: {existing_alert.display_name} (rep: {existing_alert.contador_repeticiones})")
                    return existing_alert
                else:
                    # Límite alcanzado - cambiar estado y crear nota
                    _logger.warning(f"🚨 Alerta {existing_alert.display_name} alcanzó máximo de {existing_alert.max_repeticiones} repeticiones")
                    existing_alert.write({
                        'estado': 'en_proceso',
                        'notas_resolucion': f'Alcanzó máximo de {existing_alert.max_repeticiones} repeticiones. Requiere atención manual. Última revisión: {suministro_record.percent_remaining:.1f}%'
                    })
                    
                    # Solo crear nueva si es un cambio crítico
                    if suministro_record.percent_remaining > 5:
                        _logger.info(f"📝 Alerta marcada como 'en_proceso' por límite alcanzado")
                        return existing_alert
                    else:
                        _logger.warning(f"🆕 Creando nueva alerta crítica por límite alcanzado pero suministro en estado crítico")
            
            # Determinar tipo y prioridad según porcentaje
            if suministro_record.percent_remaining <= 0:
                tipo_alerta = 'suministro_vacio'
                prioridad = 'urgente'
                titulo = f"🚨 URGENTE: Suministro agotado - {suministro_record.display_name}"
                _logger.error(f"🚨 SUMINISTRO VACÍO detectado: {serie_equipo}")
            elif suministro_record.percent_remaining < 5:
                tipo_alerta = 'suministro_critico'
                prioridad = 'critica'
                titulo = f"⚠️ CRÍTICO: Suministro agotándose - {suministro_record.display_name}"
                _logger.warning(f"🔴 SUMINISTRO CRÍTICO detectado: {serie_equipo} ({suministro_record.percent_remaining:.1f}%)")
            else:
                tipo_alerta = 'suministro_bajo'
                prioridad = 'alta'
                titulo = f"⚠️ Suministro bajo - {suministro_record.display_name}"
                _logger.info(f"🟠 SUMINISTRO BAJO detectado: {serie_equipo} ({suministro_record.percent_remaining:.1f}%)")
            
            # Crear nueva alerta
            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': tipo_alerta,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': f"El suministro {suministro_record.supply_type} {suministro_record.supply_color or ''} está al {suministro_record.percent_remaining:.1f}%",
                'suministro_id': suministro_record.id,
                'porcentaje_suministro': suministro_record.percent_remaining,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',  # NUEVO
                'accion_automatica': 'crear_orden_compra' if suministro_record.percent_remaining < 10 else 'ninguna'
            })
            
            _logger.info(f"🚨 Nueva alerta de suministro creada: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta de suministro: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    @api.model
    def crear_alerta_equipo_offline(self, serie_equipo, dias_sin_lecturas, ultima_lectura=None):
        """
        Crea alerta para equipo offline (CORREGIDO CON LOGS)
        """
        try:
            _logger.info(f"📵 Procesando equipo offline: {serie_equipo} ({dias_sin_lecturas} días sin lecturas)")
            
            # Verificar si ya existe alerta activa
            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', '=', 'equipo_offline'),
                ('origen_datos', '=', 'interno'),  # NUEVO
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ], limit=1)
            
            if existing_alert:
                _logger.info(f"🔄 Alerta offline existente: {existing_alert.display_name} (rep: {existing_alert.contador_repeticiones}/{existing_alert.max_repeticiones})")
                
                # VERIFICAR LÍMITE antes de incrementar
                if existing_alert.contador_repeticiones < existing_alert.max_repeticiones:
                    update_vals = {
                        'dias_sin_lecturas': dias_sin_lecturas,
                        'contador_repeticiones': existing_alert.contador_repeticiones + 1,
                        'ultima_revision': fields.Datetime.now()
                    }
                    
                    # Escalamiento según días
                    if dias_sin_lecturas >= 14 and existing_alert.prioridad != 'urgente':
                        update_vals.update({
                            'prioridad': 'urgente',
                            'titulo': f"🚨 URGENTE: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                        })
                        _logger.error(f"🚨 Alerta offline escalada a URGENTE: {serie_equipo}")
                    elif dias_sin_lecturas >= 7 and existing_alert.prioridad not in ['critica', 'urgente']:
                        update_vals.update({
                            'prioridad': 'critica',
                            'titulo': f"🔴 CRÍTICO: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                        })
                        _logger.warning(f"⬆️ Alerta offline escalada a CRÍTICA: {serie_equipo}")
                    
                    existing_alert.write(update_vals)
                    _logger.info(f"✅ Alerta offline actualizada: {existing_alert.display_name}")
                    return existing_alert
                else:
                    # Límite alcanzado - escalar a urgente y marcar como en proceso
                    _logger.warning(f"🚨 Alerta offline {existing_alert.display_name} alcanzó máximo repeticiones")
                    existing_alert.write({
                        'prioridad': 'urgente',
                        'estado': 'en_proceso',
                        'notas_resolucion': f'Equipo offline {dias_sin_lecturas} días. Máximo repeticiones alcanzado. Requiere intervención técnica urgente.',
                        'accion_automatica': 'notificar_tecnico'
                    })
                    _logger.error(f"🔥 Alerta offline escalada por límite: {serie_equipo}")
                    return existing_alert
            
            # Determinar prioridad según días offline
            if dias_sin_lecturas >= 14:
                prioridad = 'urgente'
                titulo = f"🚨 URGENTE: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                _logger.error(f"🚨 EQUIPO OFFLINE URGENTE: {serie_equipo} ({dias_sin_lecturas} días)")
            elif dias_sin_lecturas >= 7:
                prioridad = 'critica'
                titulo = f"🔴 CRÍTICO: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                _logger.warning(f"🔴 EQUIPO OFFLINE CRÍTICO: {serie_equipo} ({dias_sin_lecturas} días)")
            elif dias_sin_lecturas >= 3:
                prioridad = 'alta'
                titulo = f"📵 Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                _logger.warning(f"🟠 EQUIPO OFFLINE: {serie_equipo} ({dias_sin_lecturas} días)")
            else:
                prioridad = 'media'
                titulo = f"📵 Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                _logger.info(f"🟡 Equipo offline detectado: {serie_equipo} ({dias_sin_lecturas} días)")
            
            # Crear nueva alerta
            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': 'equipo_offline',
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': f"El equipo no ha reportado lecturas en {dias_sin_lecturas} días. Última lectura: {ultima_lectura or 'No disponible'}",
                'dias_sin_lecturas': dias_sin_lecturas,
                'ultima_lectura': ultima_lectura,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',  # NUEVO
                'accion_automatica': 'notificar_tecnico' if dias_sin_lecturas >= 3 else 'ninguna'
            })
            
            _logger.info(f"📵 Nueva alerta offline creada: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta offline: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    @api.model
    def crear_alerta_uso_anomalo(self, serie_equipo, tipo_anomalia, contador_actual, contador_anterior):
        """
        Crea alerta para uso anómalo (muy alto o muy bajo)
        """
        try:
            diferencia = contador_actual - contador_anterior
            _logger.info(f"📊 Procesando uso anómalo {tipo_anomalia}: {serie_equipo} (diferencia: {diferencia:,})")
            
            # Determinar tipo de alerta
            if tipo_anomalia == 'alto':
                tipo_alerta = 'uso_anomalo_alto'
                titulo = f"📈 Uso anómalamente alto - {serie_equipo}"
                descripcion = f"Incremento de {diferencia:,} páginas en un día (mucho mayor al promedio)"
                prioridad = 'media'
                _logger.warning(f"📈 USO ALTO ANÓMALO: {serie_equipo} (+{diferencia:,} páginas)")
            else:
                tipo_alerta = 'uso_anomalo_bajo'
                titulo = f"📉 Uso anómalamente bajo - {serie_equipo}"
                descripcion = f"Incremento de solo {diferencia:,} páginas en un día (muy por debajo del promedio)"
                prioridad = 'baja'
                _logger.info(f"📉 USO BAJO ANÓMALO: {serie_equipo} (+{diferencia:,} páginas)")
            
            # Verificar si ya existe alerta similar reciente
            fecha_limite = datetime.now() - timedelta(days=7)
            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', '=', tipo_alerta),
                ('origen_datos', '=', 'interno'),  # NUEVO
                ('fecha_creacion', '>=', fecha_limite),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ], limit=1)
            
            if existing_alert:
                _logger.info(f"⚠️ Alerta uso anómalo similar reciente encontrada: {existing_alert.display_name}")
                return existing_alert
            
            # Crear nueva alerta
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
                'origen_datos': 'interno'  # NUEVO
            })
            
            _logger.info(f"📊 Nueva alerta de uso anómalo creada: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta uso anómalo: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    @api.model
    def crear_alerta_contador_decrece(self, serie_equipo, tipo_contador, valor_actual, valor_anterior):
        """
        Crea alerta cuando un contador decrece (posible reset o error)
        """
        try:
            diferencia = valor_anterior - valor_actual
            _logger.warning(f"⬇️ Procesando contador que decrece: {serie_equipo} - {tipo_contador} (decreció {diferencia:,})")
            
            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': 'contador_decrece',
                'prioridad': 'alta',
                'titulo': f"⬇️ Contador decreció - {serie_equipo}",
                'descripcion': f"El contador {tipo_contador} decreció de {valor_anterior:,} a {valor_actual:,} (-{diferencia:,}). Posible reset o error.",
                'contador_actual': valor_actual,
                'contador_anterior': valor_anterior,
                'diferencia_contador': -diferencia,
                'fecha_deteccion': fields.Datetime.now(),
                'origen_datos': 'interno',  # NUEVO
                'accion_automatica': 'notificar_tecnico'
            })
            
            _logger.warning(f"⬇️ Nueva alerta de contador decrece creada: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta contador decrece: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    @api.model
    def crear_alerta_desde_api_event(self, event_data, device_serial):
        """
        Crea alerta desde un event de PrintTracker Pro API
        SIEMPRE crea nueva alerta (sin límites de repetición)
        """
        try:
            event_id = event_data.get('id')
            _logger.info(f"📋 Procesando event de API: {event_id} para device {device_serial}")
            
            # Verificar si ya existe este event específico
            existing_alert = self.search([
                ('api_event_id', '=', event_id)
            ], limit=1)
            
            if existing_alert:
                _logger.info(f"⚠️ Event ya procesado: {event_id}")
                return existing_alert
            
            # Determinar tipo de alerta basado en description y alertType
            tipo_alerta, prioridad = self._clasificar_event_api(event_data)
            
            # Crear título descriptivo
            titulo = self._generar_titulo_event(event_data, device_serial)
            
            # Crear nueva alerta
            nueva_alerta = self.create({
                'serie_equipo': device_serial,
                'tipo_alerta': tipo_alerta,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': event_data.get('description', 'Event de PrintTracker Pro'),
                'fecha_deteccion': self._parse_api_timestamp(event_data.get('timestamp')),
                'origen_datos': 'api_events',  # NUEVO
                'api_event_id': event_data.get('id'),
                'api_event_type': event_data.get('alertType'),
                'api_resolution_status': event_data.get('resolutionStatus'),
                'api_event_timestamp': self._parse_api_timestamp(event_data.get('timestamp')),
                'api_supply_key': event_data.get('supplyKey'),
                'api_raw_data': json.dumps(event_data),
                # Sin límites de repetición para events API
                'contador_repeticiones': 1,
                'max_repeticiones': 9999,  # Límite muy alto
                'accion_automatica': self._determinar_accion_event(event_data)
            })
            
            _logger.info(f"📋 Nueva alerta de API Event creada: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta desde API event: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _clasificar_event_api(self, event_data):
        """
        Clasifica el event de la API para determinar tipo y prioridad
        """
        try:
            description = (event_data.get('description', '')).lower()
            alert_type = event_data.get('alertType')
            resolution_status = event_data.get('resolutionStatus', 'Open')
            
            _logger.debug(f"🔍 Clasificando event: description='{description[:50]}...', alertType='{alert_type}', status='{resolution_status}'")
            
            # Clasificación basada en keywords en description
            if any(word in description for word in ['jam', 'atasco', 'trabamiento', 'paper']):
                _logger.info(f"📄 Event clasificado como: paper_jam")
                return 'paper_jam', 'alta'
            elif any(word in description for word in ['toner', 'ink', 'cartridge']):
                if 'replaced' in description or 'cambio' in description:
                    _logger.info(f"🎨 Event clasificado como: supply_replaced")
                    return 'supply_replaced', 'media'
                elif 'low' in description or 'bajo' in description:
                    _logger.info(f"🎨 Event clasificado como: suministro_bajo")
                    return 'suministro_bajo', 'alta'
                else:
                    _logger.info(f"🎨 Event clasificado como: supply_event")
                    return 'supply_event', 'media'
            elif any(word in description for word in ['error', 'fault', 'codigo']):
                _logger.warning(f"⚠️ Event clasificado como: device_error")
                return 'device_error', 'critica'
            elif any(word in description for word in ['cover', 'door', 'open', 'abierta']):
                _logger.info(f"🚪 Event clasificado como: cover_open")
                return 'cover_open', 'baja'
            elif any(word in description for word in ['maintenance', 'service', 'mantenimiento']):
                _logger.info(f"🔧 Event clasificado como: mantenimiento_debido")
                return 'mantenimiento_debido', 'alta'
            elif any(word in description for word in ['offline', 'connection', 'network']):
                _logger.warning(f"📡 Event clasificado como: connectivity_issue")
                return 'connectivity_issue', 'alta'
            else:
                # Event genérico
                _logger.info(f"📋 Event clasificado como: device_event (genérico)")
                return 'device_event', 'media'
                
        except Exception as e:
            _logger.error(f"❌ Error clasificando event API: {e}")
            return 'device_event', 'media'

    def _generar_titulo_event(self, event_data, device_serial):
        """
        Genera título descriptivo para el event
        """
        try:
            description = event_data.get('description', 'Event')
            alert_type = event_data.get('alertType')
            
            # Agregar emoji según tipo
            if 'jam' in description.lower():
                emoji = '📄'
            elif 'toner' in description.lower():
                emoji = '🎨'
            elif 'error' in description.lower():
                emoji = '⚠️'
            elif 'maintenance' in description.lower():
                emoji = '🔧'
            elif 'cover' in description.lower():
                emoji = '🚪'
            elif 'offline' in description.lower():
                emoji = '📡'
            else:
                emoji = '📋'
            
            titulo = f"{emoji} {device_serial} - {description}"
            _logger.debug(f"📝 Título generado: {titulo}")
            return titulo
            
        except Exception as e:
            _logger.error(f"❌ Error generando título event: {e}")
            return f"📋 {device_serial} - Event PrintTracker"

    def _parse_api_timestamp(self, timestamp_str):
        """
        Convierte timestamp de API a datetime de Odoo
        """
        try:
            if timestamp_str:
                # Formato: "2021-01-01T01:44:44.000Z"
                parsed_datetime = datetime.strptime(timestamp_str.replace('Z', '+00:00'), '%Y-%m-%dT%H:%M:%S.%f%z')
                _logger.debug(f"⏰ Timestamp parseado: {timestamp_str} -> {parsed_datetime}")
                return parsed_datetime
            return fields.Datetime.now()
        except Exception as e:
            _logger.warning(f"⚠️ Error parseando timestamp '{timestamp_str}': {e}")
            return fields.Datetime.now()

    def _determinar_accion_event(self, event_data):
        """
        Determina qué acción automática ejecutar según el event
        """
        try:
            description = (event_data.get('description', '')).lower()
            
            if 'jam' in description:
                _logger.info(f"🎯 Acción determinada: notificar_tecnico (jam)")
                return 'notificar_tecnico'
            elif 'toner' in description and 'low' in description:
                _logger.info(f"🎯 Acción determinada: crear_orden_compra (toner low)")
                return 'crear_orden_compra'
            elif 'error' in description:
                _logger.info(f"🎯 Acción determinada: notificar_tecnico (error)")
                return 'notificar_tecnico'
            elif 'maintenance' in description:
                _logger.info(f"🎯 Acción determinada: crear_tarea (maintenance)")
                return 'crear_tarea'
            else:
                _logger.debug(f"🎯 Acción determinada: ninguna (event genérico)")
                return 'ninguna'
                
        except Exception as e:
            _logger.error(f"❌ Error determinando acción event: {e}")
            return 'ninguna'

    def procesar_notificaciones(self):
        """
        Procesa notificaciones pendientes para esta alerta
        """
        try:
            for alert in self:
                if alert.estado != 'nueva':
                    _logger.debug(f"⏭️ Saltando alerta {alert.display_name} - estado: {alert.estado}")
                    continue
                
                _logger.info(f"📬 Procesando notificaciones para: {alert.display_name}")
                notificaciones_enviadas = 0
                
                # Enviar notificación por email
                if alert.notificar_email and not alert.email_enviado:
                    if alert._enviar_notificacion_email():
                        alert.email_enviado = True
                        notificaciones_enviadas += 1
                        _logger.info(f"📧 Email enviado para: {alert.display_name}")
                
                # Enviar notificación en chatter
                if alert.notificar_chatter and not alert.chatter_enviado:
                    if alert._enviar_notificacion_chatter():
                        alert.chatter_enviado = True
                        notificaciones_enviadas += 1
                        _logger.info(f"💬 Chatter enviado para: {alert.display_name}")
                
                # Ejecutar acción automática
                if alert.accion_automatica != 'ninguna' and not alert.accion_ejecutada:
                    alert._ejecutar_accion_automatica()
                
                # Actualizar estado si se enviaron notificaciones
                if notificaciones_enviadas > 0:
                    alert.estado = 'notificada'
                    _logger.info(f"✅ Alerta marcada como notificada: {alert.display_name} ({notificaciones_enviadas} notificaciones)")
                    
        except Exception as e:
            _logger.error(f"❌ Error procesando notificaciones: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")

    def _enviar_notificacion_email(self):
        """Envía notificación por email"""
        try:
            if not self.equipo_id or not hasattr(self.equipo_id, 'cliente_id') or not self.equipo_id.cliente_id:
                _logger.warning(f"⚠️ No se puede enviar email - equipo sin cliente: {self.serie_equipo}")
                return False
            
            cliente = self.equipo_id.cliente_id
            if not cliente.email:
                _logger.warning(f"⚠️ Cliente sin email: {cliente.name}")
                return False
            
            _logger.info(f"📧 Enviando email a {cliente.email} para alerta: {self.display_name}")
            
            # Preparar contenido del email
            subject = f"[PrintTracker] {self.titulo}"
            
            body = f"""
            <h3>{self.titulo}</h3>
            <p><strong>Equipo:</strong> {self.serie_equipo}</p>
            <p><strong>Cliente:</strong> {self.cliente_nombre}</p>
            <p><strong>Modelo:</strong> {self.modelo_equipo}</p>
            <p><strong>Prioridad:</strong> {self.prioridad.upper()}</p>
            <p><strong>Descripción:</strong> {self.descripcion}</p>
            <p><strong>Fecha:</strong> {self.fecha_deteccion}</p>
            """
            
            if self.suministro_id:
                body += f"<p><strong>Suministro:</strong> {self.suministro_id.display_name} ({self.porcentaje_suministro:.1f}%)</p>"
            
            if self.origen_datos == 'api_events':
                body += f"<p><strong>Origen:</strong> Event PrintTracker API</p>"
                if self.api_event_type:
                    body += f"<p><strong>Tipo Event:</strong> {self.api_event_type}</p>"
            
            body += "<p>Por favor, tome las acciones necesarias.</p>"
            
            # Enviar email usando el sistema de Odoo
            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_to': cliente.email,
                'email_from': self.env.company.email or 'noreply@company.com',
                'reply_to': self.env.company.email or 'noreply@company.com',
            }
            
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            
            _logger.info(f"✅ Email enviado exitosamente a {cliente.email}")
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error enviando email: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _enviar_notificacion_chatter(self):
        """Envía notificación en el chatter del equipo"""
        try:
            if not self.equipo_id:
                _logger.warning(f"⚠️ No se puede enviar chatter - sin equipo: {self.serie_equipo}")
                return False
            
            _logger.info(f"💬 Enviando mensaje al chatter del equipo: {self.equipo_id.name}")
            
            mensaje = f"""
            🚨 <strong>{self.titulo}</strong><br/>
            📅 <strong>Fecha:</strong> {self.fecha_deteccion}<br/>
            ⚡ <strong>Prioridad:</strong> {self.prioridad.upper()}<br/>
            📝 <strong>Descripción:</strong> {self.descripcion}<br/>
            """
            
            if self.suministro_id:
                mensaje += f"🎨 <strong>Suministro:</strong> {self.suministro_id.display_name} ({self.porcentaje_suministro:.1f}%)<br/>"
            
            if self.origen_datos == 'api_events':
                mensaje += f"📋 <strong>Origen:</strong> Event PrintTracker API<br/>"
                if self.api_event_type:
                    mensaje += f"🔧 <strong>Tipo Event:</strong> {self.api_event_type}<br/>"
            
            # Agregar al chatter del equipo
            self.equipo_id.message_post(
                body=mensaje,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"✅ Mensaje enviado al chatter exitosamente")
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error enviando mensaje chatter: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _ejecutar_accion_automatica(self):
        """Ejecuta la acción automática configurada"""
        try:
            _logger.info(f"⚡ Ejecutando acción automática '{self.accion_automatica}' para: {self.display_name}")
            
            if self.accion_automatica == 'crear_orden_compra' and self.suministro_id:
                resultado = self.suministro_id.action_create_purchase_order()
                self.accion_ejecutada = True
                self.resultado_accion = f"Orden de compra creada: {resultado}"
                _logger.info(f"🛒 Orden de compra creada para suministro")
                
            elif self.accion_automatica == 'crear_tarea':
                tarea = self.env['project.task'].create({
                    'name': f"Resolver: {self.titulo}",
                    'description': self.descripcion,
                    'user_ids': [(6, 0, [self.asignado_a.id])] if self.asignado_a else [],
                    'priority': '1' if self.prioridad in ['critica', 'urgente'] else '0'
                })
                self.accion_ejecutada = True
                self.resultado_accion = f"Tarea creada: {tarea.name}"
                _logger.info(f"📋 Tarea creada: {tarea.name}")
                
            elif self.accion_automatica == 'notificar_tecnico':
                # Buscar usuarios con grupo técnico
                tecnicos = self.env['res.users'].search([
                    ('groups_id', 'in', [self.env.ref('base.group_user').id])
                ])
                
                _logger.info(f"👥 Notificando a {len(tecnicos)} técnicos")
                
                for tecnico in tecnicos:
                    if tecnico.email:
                        # Enviar notificación interna
                        self.env['mail.message'].create({
                            'message_type': 'notification',
                            'subject': f"Alerta Técnica: {self.titulo}",
                            'body': self.descripcion,
                            'partner_ids': [(6, 0, [tecnico.partner_id.id])]
                        })
                
                self.accion_ejecutada = True
                self.resultado_accion = f"Técnicos notificados: {len(tecnicos)}"
                _logger.info(f"✅ {len(tecnicos)} técnicos notificados")
            
            else:
                _logger.debug(f"ℹ️ Sin acción automática o acción no reconocida: {self.accion_automatica}")
            
        except Exception as e:
            _logger.error(f"❌ Error ejecutando acción automática: {e}")
            self.resultado_accion = f"Error: {str(e)}"
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")

    def action_resolver(self):
        """Acción manual para marcar alerta como resuelta"""
        self.ensure_one()
        _logger.info(f"🎯 Iniciando resolución manual de alerta: {self.display_name}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Resolver Alerta',
            'res_model': 'printtracker.alert.resolve.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_alert_id': self.id,
                'default_notas_resolucion': ''
            }
        }

    def action_asignar(self):
        """Acción para asignar alerta a un usuario"""
        self.ensure_one()
        _logger.info(f"👤 Iniciando asignación de alerta: {self.display_name}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar Alerta',
            'res_model': 'printtracker.alert.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_alert_id': self.id
            }
        }

    def marcar_como_resuelta(self, notas_resolucion=''):
        """Marca la alerta como resuelta"""
        self.write({
            'estado': 'resuelta',
            'resuelto_por': self.env.user.id,
            'fecha_resolucion': fields.Datetime.now(),
            'notas_resolucion': notas_resolucion
        })
        
        _logger.info(f"✅ Alerta marcada como resuelta: {self.display_name} por {self.env.user.name}")

    @api.model
    def limpiar_alertas_antiguas(self, dias=30):
        """
        UTILIDAD: Limpia alertas resueltas/cerradas antiguas
        """
        try:
            fecha_limite = datetime.now() - timedelta(days=dias)
            _logger.info(f"🗑️ Iniciando limpieza de alertas anteriores a: {fecha_limite}")
            
            alertas_antiguas = self.search([
                ('estado', 'in', ['resuelta', 'cerrada', 'ignorada']),
                ('fecha_creacion', '<', fecha_limite)
            ])
            
            count = len(alertas_antiguas)
            if count > 0:
                alertas_antiguas.unlink()
                _logger.info(f"✅ Limpieza completada: {count} alertas antiguas eliminadas")
            else:
                _logger.info(f"ℹ️ No hay alertas antiguas para eliminar")
            
            return count
            
        except Exception as e:
            _logger.error(f"❌ Error en limpieza de alertas: {e}")
            return 0

    @api.model
    def obtener_estadisticas_alertas(self, dias=7):
        """
        Obtiene estadísticas de alertas de los últimos N días
        """
        try:
            fecha_inicio = datetime.now() - timedelta(days=dias)
            _logger.info(f"📊 Obteniendo estadísticas de alertas desde: {fecha_inicio}")
            
            domain = [('fecha_creacion', '>=', fecha_inicio)]
            alertas = self.search(domain)
            
            stats = {
                'total_alertas': len(alertas),
                'por_tipo': {},
                'por_prioridad': {},
                'por_estado': {},
                'por_origen': {},
                'resueltas': len(alertas.filtered(lambda a: a.estado == 'resuelta')),
                'pendientes': len(alertas.filtered(lambda a: a.estado in ['nueva', 'notificada', 'en_proceso'])),
                'equipos_con_alertas': len(set(alertas.mapped('serie_equipo')))
            }
            
            # Por tipo
            tipos_alertas = ['suministro_bajo', 'suministro_critico', 'equipo_offline', 'uso_anomalo_alto', 'contador_decrece', 'paper_jam', 'device_error', 'supply_event']
            for tipo in tipos_alertas:
                count = len(alertas.filtered(lambda a: a.tipo_alerta == tipo))
                if count > 0:
                    stats['por_tipo'][tipo] = count
            
            # Por prioridad  
            for prioridad in ['baja', 'media', 'alta', 'critica', 'urgente']:
                count = len(alertas.filtered(lambda a: a.prioridad == prioridad))
                if count > 0:
                    stats['por_prioridad'][prioridad] = count
            
            # Por estado
            for estado in ['nueva', 'notificada', 'en_proceso', 'resuelta', 'cerrada']:
                count = len(alertas.filtered(lambda a: a.estado == estado))
                if count > 0:
                    stats['por_estado'][estado] = count
            
            # Por origen
            for origen in ['interno', 'api_events']:
                count = len(alertas.filtered(lambda a: a.origen_datos == origen))
                if count > 0:
                    stats['por_origen'][origen] = count
            
            _logger.info(f"📊 Estadísticas generadas: {stats['total_alertas']} alertas totales")
            return stats
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}

    def action_view_equipo(self):
        """Acción para ver el equipo relacionado"""
        self.ensure_one()
        
        if not self.equipo_id:
            _logger.warning(f"⚠️ No se encontró equipo para serie: {self.serie_equipo}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No se encontró equipo para esta serie',
                    'type': 'warning'
                }
            }
        
        _logger.info(f"🎯 Abriendo vista de equipo: {self.equipo_id.name}")
        return {
            'type': 'ir.actions.act_window',
            'name': f'Equipo - {self.serie_equipo}',
            'res_model': 'alquiler',
            'res_id': self.equipo_id.id,
            'view_mode': 'form',
            'target': 'current'
        }
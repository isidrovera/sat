from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

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
    
    # Constrains
    _sql_constraints = [
        ('positive_percentage', 'CHECK(porcentaje_suministro >= 0 AND porcentaje_suministro <= 100)', 
         'Porcentaje de suministro debe estar entre 0 y 100'),
        ('positive_days', 'CHECK(dias_sin_lecturas >= 0)', 
         'Días sin lecturas debe ser positivo'),
        ('valid_repetitions', 'CHECK(contador_repeticiones <= max_repeticiones)', 
         'Contador repeticiones no puede exceder el máximo')
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
        Crea alerta para suministro bajo
        """
        try:
            if not suministro_record.device_id or not suministro_record.device_id.serie:
                return False
            
            # Verificar si ya existe alerta activa similar
            existing_alert = self.search([
                ('serie_equipo', '=', suministro_record.device_id.serie),
                ('tipo_alerta', 'in', ['suministro_bajo', 'suministro_critico']),
                ('suministro_id', '=', suministro_record.id),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ], limit=1)
            
            if existing_alert:
                # Actualizar alerta existente si empeoró
                if suministro_record.percent_remaining < 5 and existing_alert.tipo_alerta != 'suministro_critico':
                    existing_alert.write({
                        'tipo_alerta': 'suministro_critico',
                        'prioridad': 'critica',
                        'porcentaje_suministro': suministro_record.percent_remaining,
                        'contador_repeticiones': existing_alert.contador_repeticiones + 1
                    })
                    _logger.info(f"⬆️ Alerta escalada a crítica: {existing_alert.display_name}")
                return existing_alert
            
            # Determinar tipo y prioridad según porcentaje
            if suministro_record.percent_remaining < 5:
                tipo_alerta = 'suministro_critico'
                prioridad = 'critica'
                titulo = f"⚠️ CRÍTICO: Suministro agotándose - {suministro_record.display_name}"
            else:
                tipo_alerta = 'suministro_bajo'
                prioridad = 'alta'
                titulo = f"⚠️ Suministro bajo - {suministro_record.display_name}"
            
            # Crear nueva alerta
            nueva_alerta = self.create({
                'serie_equipo': suministro_record.device_id.serie,
                'tipo_alerta': tipo_alerta,
                'prioridad': prioridad,
                'titulo': titulo,
                'descripcion': f"El suministro {suministro_record.supply_type} {suministro_record.supply_color or ''} está al {suministro_record.percent_remaining:.1f}%",
                'suministro_id': suministro_record.id,
                'porcentaje_suministro': suministro_record.percent_remaining,
                'fecha_deteccion': fields.Datetime.now(),
                'accion_automatica': 'crear_orden_compra' if suministro_record.percent_remaining < 10 else 'ninguna'
            })
            
            _logger.info(f"🚨 Nueva alerta de suministro: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta de suministro: {e}")
            return False

    @api.model
    def crear_alerta_equipo_offline(self, serie_equipo, dias_sin_lecturas, ultima_lectura=None):
        """
        Crea alerta para equipo offline
        """
        try:
            # Verificar si ya existe alerta activa
            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', '=', 'equipo_offline'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ], limit=1)
            
            if existing_alert:
                # Actualizar días sin lecturas
                existing_alert.write({
                    'dias_sin_lecturas': dias_sin_lecturas,
                    'contador_repeticiones': existing_alert.contador_repeticiones + 1
                })
                return existing_alert
            
            # Determinar prioridad según días offline
            if dias_sin_lecturas >= 7:
                prioridad = 'critica'
            elif dias_sin_lecturas >= 3:
                prioridad = 'alta'
            else:
                prioridad = 'media'
            
            # Crear nueva alerta
            nueva_alerta = self.create({
                'serie_equipo': serie_equipo,
                'tipo_alerta': 'equipo_offline',
                'prioridad': prioridad,
                'titulo': f"📵 Equipo offline - {serie_equipo}",
                'descripcion': f"El equipo no ha reportado lecturas en {dias_sin_lecturas} días",
                'dias_sin_lecturas': dias_sin_lecturas,
                'ultima_lectura': ultima_lectura,
                'fecha_deteccion': fields.Datetime.now(),
                'accion_automatica': 'notificar_tecnico' if dias_sin_lecturas >= 3 else 'ninguna'
            })
            
            _logger.info(f"📵 Nueva alerta de equipo offline: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta offline: {e}")
            return False

    @api.model
    def crear_alerta_uso_anomalo(self, serie_equipo, tipo_anomalia, contador_actual, contador_anterior):
        """
        Crea alerta para uso anómalo (muy alto o muy bajo)
        """
        try:
            diferencia = contador_actual - contador_anterior
            
            # Determinar tipo de alerta
            if tipo_anomalia == 'alto':
                tipo_alerta = 'uso_anomalo_alto'
                titulo = f"📈 Uso anómalamente alto - {serie_equipo}"
                descripcion = f"Incremento de {diferencia:,} páginas en un día (mucho mayor al promedio)"
                prioridad = 'media'
            else:
                tipo_alerta = 'uso_anomalo_bajo'
                titulo = f"📉 Uso anómalamente bajo - {serie_equipo}"
                descripcion = f"Incremento de solo {diferencia:,} páginas en un día (muy por debajo del promedio)"
                prioridad = 'baja'
            
            # Verificar si ya existe alerta similar reciente
            fecha_limite = datetime.now() - timedelta(days=7)
            existing_alert = self.search([
                ('serie_equipo', '=', serie_equipo),
                ('tipo_alerta', '=', tipo_alerta),
                ('fecha_creacion', '>=', fecha_limite),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ], limit=1)
            
            if existing_alert:
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
                'fecha_deteccion': fields.Datetime.now()
            })
            
            _logger.info(f"📊 Nueva alerta de uso anómalo: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta uso anómalo: {e}")
            return False

    @api.model
    def crear_alerta_contador_decrece(self, serie_equipo, tipo_contador, valor_actual, valor_anterior):
        """
        Crea alerta cuando un contador decrece (posible reset o error)
        """
        try:
            diferencia = valor_anterior - valor_actual
            
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
                'accion_automatica': 'notificar_tecnico'
            })
            
            _logger.info(f"⬇️ Nueva alerta de contador decrece: {nueva_alerta.display_name}")
            return nueva_alerta
            
        except Exception as e:
            _logger.error(f"❌ Error creando alerta contador decrece: {e}")
            return False

    def procesar_notificaciones(self):
        """
        Procesa notificaciones pendientes para esta alerta
        """
        try:
            for alert in self:
                if alert.estado != 'nueva':
                    continue
                
                notificaciones_enviadas = 0
                
                # Enviar notificación por email
                if alert.notificar_email and not alert.email_enviado:
                    if alert._enviar_notificacion_email():
                        alert.email_enviado = True
                        notificaciones_enviadas += 1
                
                # Enviar notificación en chatter
                if alert.notificar_chatter and not alert.chatter_enviado:
                    if alert._enviar_notificacion_chatter():
                        alert.chatter_enviado = True
                        notificaciones_enviadas += 1
                
                # Ejecutar acción automática
                if alert.accion_automatica != 'ninguna' and not alert.accion_ejecutada:
                    alert._ejecutar_accion_automatica()
                
                # Actualizar estado si se enviaron notificaciones
                if notificaciones_enviadas > 0:
                    alert.estado = 'notificada'
                    _logger.info(f"📬 Notificaciones enviadas para: {alert.display_name}")
                    
        except Exception as e:
            _logger.error(f"❌ Error procesando notificaciones: {e}")

    def _enviar_notificacion_email(self):
        """Envía notificación por email"""
        try:
            if not self.equipo_id or not hasattr(self.equipo_id, 'cliente_id') or not self.equipo_id.cliente_id:
                return False
            
            cliente = self.equipo_id.cliente_id
            if not cliente.email:
                return False
            
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
            
            _logger.info(f"📧 Email enviado a {cliente.email} para alerta: {self.display_name}")
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error enviando email: {e}")
            return False

    def _enviar_notificacion_chatter(self):
        """Envía notificación en el chatter del equipo"""
        try:
            if not self.equipo_id:
                return False
            
            mensaje = f"""
            🚨 <strong>{self.titulo}</strong><br/>
            📅 <strong>Fecha:</strong> {self.fecha_deteccion}<br/>
            ⚡ <strong>Prioridad:</strong> {self.prioridad.upper()}<br/>
            📝 <strong>Descripción:</strong> {self.descripcion}<br/>
            """
            
            if self.suministro_id:
                mensaje += f"🎨 <strong>Suministro:</strong> {self.suministro_id.display_name} ({self.porcentaje_suministro:.1f}%)<br/>"
            
            # Agregar al chatter del equipo
            self.equipo_id.message_post(
                body=mensaje,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"💬 Mensaje enviado al chatter para: {self.display_name}")
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error enviando mensaje chatter: {e}")
            return False

    def _ejecutar_accion_automatica(self):
        """Ejecuta la acción automática configurada"""
        try:
            if self.accion_automatica == 'crear_orden_compra' and self.suministro_id:
                resultado = self.suministro_id.action_create_purchase_order()
                self.accion_ejecutada = True
                self.resultado_accion = f"Orden de compra creada: {resultado}"
                
            elif self.accion_automatica == 'crear_tarea':
                tarea = self.env['project.task'].create({
                    'name': f"Resolver: {self.titulo}",
                    'description': self.descripcion,
                    'user_ids': [(6, 0, [self.asignado_a.id])] if self.asignado_a else [],
                    'priority': '1' if self.prioridad in ['critica', 'urgente'] else '0'
                })
                self.accion_ejecutada = True
                self.resultado_accion = f"Tarea creada: {tarea.name}"
                
            elif self.accion_automatica == 'notificar_tecnico':
                # Buscar usuarios con grupo técnico
                tecnicos = self.env['res.users'].search([
                    ('groups_id', 'in', [self.env.ref('base.group_user').id])
                ])
                
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
            
            _logger.info(f"⚡ Acción automática ejecutada: {self.accion_automatica}")
            
        except Exception as e:
            _logger.error(f"❌ Error ejecutando acción automática: {e}")
            self.resultado_accion = f"Error: {str(e)}"

    def action_resolver(self):
        """Acción manual para marcar alerta como resuelta"""
        self.ensure_one()
        
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
        
        _logger.info(f"✅ Alerta resuelta: {self.display_name}")

    @api.model
    def limpiar_alertas_antiguas(self, dias=30):
        """
        UTILIDAD: Limpia alertas resueltas/cerradas antiguas
        """
        fecha_limite = datetime.now() - timedelta(days=dias)
        
        alertas_antiguas = self.search([
            ('estado', 'in', ['resuelta', 'cerrada', 'ignorada']),
            ('fecha_creacion', '<', fecha_limite)
        ])
        
        count = len(alertas_antiguas)
        alertas_antiguas.unlink()
        
        _logger.info(f"🗑️ Limpieza: {count} alertas antiguas eliminadas")
        return count

    @api.model
    def obtener_estadisticas_alertas(self, dias=7):
        """
        Obtiene estadísticas de alertas de los últimos N días
        """
        fecha_inicio = datetime.now() - timedelta(days=dias)
        
        domain = [('fecha_creacion', '>=', fecha_inicio)]
        alertas = self.search(domain)
        
        stats = {
            'total_alertas': len(alertas),
            'por_tipo': {},
            'por_prioridad': {},
            'por_estado': {},
            'resueltas': len(alertas.filtered(lambda a: a.estado == 'resuelta')),
            'pendientes': len(alertas.filtered(lambda a: a.estado in ['nueva', 'notificada', 'en_proceso'])),
            'equipos_con_alertas': len(set(alertas.mapped('serie_equipo')))
        }
        
        # Por tipo
        for tipo in ['suministro_bajo', 'suministro_critico', 'equipo_offline', 'uso_anomalo_alto', 'contador_decrece']:
            count = len(alertas.filtered(lambda a: a.tipo_alerta == tipo))
            stats['por_tipo'][tipo] = count
        
        # Por prioridad  
        for prioridad in ['baja', 'media', 'alta', 'critica', 'urgente']:
            count = len(alertas.filtered(lambda a: a.prioridad == prioridad))
            stats['por_prioridad'][prioridad] = count
        
        # Por estado
        for estado in ['nueva', 'notificada', 'en_proceso', 'resuelta', 'cerrada']:
            count = len(alertas.filtered(lambda a: a.estado == estado))
            stats['por_estado'][estado] = count
        
        return stats
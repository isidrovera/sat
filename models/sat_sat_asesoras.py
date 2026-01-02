# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class SatSatAsesoras(models.Model):
    """
    Herencia de sat.sat para agregar funcionalidad de control de asesoras.
    Maneja:
    - Control de plazos de venta (5 días hábiles post-descarga)
    - Detección de renovaciones artificiales
    - Sincronización de asesora entre cliente y usuario
    - Liberación automática de máquinas vencidas
    - Historial completo de asignaciones
    """
    _inherit = 'sat.sat'
    
    # ============================================
    # NUEVOS CAMPOS - CONTROL DE DESCARGA Y PLAZO
    # ============================================
    
    fecha_descarga_contenedor = fields.Date(
        string='Fecha de descarga del contenedor',
        tracking=True,
        copy=False,
        index=True,
        help='Fecha real cuando se descargó el contenedor. '
             'A partir de aquí inicia el conteo de 5 días hábiles.'
    )
    
    fecha_inicio_conteo_dias = fields.Date(
        string='Inicio conteo días',
        compute='_compute_fecha_inicio_conteo_dias',
        store=True,
        help='Fecha desde la cual se cuentan los 5 días hábiles. '
             'Si se asignó ANTES de descarga: usa fecha_descarga. '
             'Si se asignó DESPUÉS: usa fecha_separacion.'
    )
    
    dias_habiles_transcurridos = fields.Integer(
        string='Días hábiles transcurridos',
        compute='_compute_dias_habiles_transcurridos',
        store=True,
        help='Días hábiles (lun-vie) desde fecha_inicio_conteo_dias hasta hoy'
    )
    
    dias_tolerancia_total = fields.Integer(
        string='Días tolerancia total',
        compute='_compute_dias_tolerancia_total',
        store=True,
        help='Días base (5) + extensión otorgada por gerencia'
    )
    
    estado_plazo_venta = fields.Selection([
        ('pre_descarga', '📦 Pre-descarga (esperando contenedor)'),
        ('en_tolerancia', '✅ En tolerancia (0-5 días)'),
        ('proxima_vencer', '⚠️ Próxima a vencer (6-7 días)'),
        ('vencida', '🔴 Vencida (8+ días)'),
        ('vendida', '✅ Vendida'),
    ], string='Estado del plazo', 
       compute='_compute_estado_plazo_venta',
       store=True,
       tracking=True,
       index=True,
       help='Estado actual del plazo de venta según días transcurridos'
    )
    
    # ============================================
    # CAMPOS DE CONTROL ANTI-RENOVACIÓN
    # ============================================
    
    intentos_cambio_cliente = fields.Integer(
        string='Intentos de cambio de cliente',
        default=0,
        copy=False,
        help='Contador de veces que la asesora cambió el cliente '
             'de esta máquina después de la descarga'
    )
    
    ultima_fecha_cambio_cliente = fields.Datetime(
        string='Última fecha de cambio cliente',
        copy=False,
        readonly=True,
        help='Última vez que se cambió el cliente'
    )
    
    es_renovacion_sospechosa = fields.Boolean(
        string='¿Renovación sospechosa?',
        default=False,
        copy=False,
        help='Se activa cuando se detecta patrón de abuso'
    )
    
    # ============================================
    # CAMPOS DE GESTIÓN GERENCIAL
    # ============================================
    
    bloqueada_por_gerencia = fields.Boolean(
        string='Bloqueada por gerencia',
        default=False,
        copy=False,
        tracking=True,
        help='Si está marcada, no se liberará automáticamente'
    )
    
    razon_bloqueo = fields.Text(
        string='Razón del bloqueo',
        copy=False
    )
    
    dias_extension_gerencia = fields.Integer(
        string='Días de extensión otorgados',
        default=0,
        copy=False,
        tracking=True,
        help='Días adicionales otorgados por gerencia más allá de los 5 días base'
    )
    
    motivo_extension = fields.Text(
        string='Motivo de extensión',
        copy=False
    )
    
    fecha_vencimiento_calculada = fields.Date(
        string='Fecha de vencimiento',
        compute='_compute_fecha_vencimiento_calculada',
        store=True,
        help='Fecha calculada de vencimiento (inicio + días tolerancia)'
    )
    
    # ============================================
    # RELACIONES CON NUEVOS MODELOS
    # ============================================
    
    historial_asignacion_ids = fields.One2many(
        'asesora.asignacion.historial',
        'maquina_id',
        string='Historial de asignaciones',
        help='Registro completo de todas las asignaciones y cambios'
    )
    
    total_cambios_cliente = fields.Integer(
        string='Total cambios históricos',
        compute='_compute_total_cambios_cliente',
        help='Total histórico de cambios de cliente desde el historial'
    )
    
    # ============================================
    # CAMPOS RELACIONADOS CON ASESORA
    # ============================================
    
    asesora_actual_id = fields.Many2one(
        'res.users',
        string='Asesora actual',
        compute='_compute_asesora_actual',
        store=True,
        help='Usuario asesora obtenido del cliente'
    )
    
    # ============================================
    # MÉTODOS COMPUTE
    # ============================================
    
    @api.depends('fecha_separacion', 'fecha_descarga_contenedor')
    def _compute_fecha_inicio_conteo_dias(self):
        """
        Determina desde cuándo se cuentan los 5 días hábiles.
        REGLA:
        - Si se asignó ANTES de descarga: inicia desde fecha_descarga
        - Si se asignó DESPUÉS de descarga: inicia desde fecha_separacion
        - Si no hay descarga aún: NULL
        """
        for record in self:
            if not record.fecha_descarga_contenedor:
                record.fecha_inicio_conteo_dias = False
                continue
            
            if not record.fecha_separacion:
                record.fecha_inicio_conteo_dias = False
                continue
            
            # Si separó ANTES de la descarga
            if record.fecha_separacion < record.fecha_descarga_contenedor:
                record.fecha_inicio_conteo_dias = record.fecha_descarga_contenedor
            else:
                # Si separó DESPUÉS de la descarga
                record.fecha_inicio_conteo_dias = record.fecha_separacion
    
    @api.depends('fecha_inicio_conteo_dias')
    def _compute_dias_habiles_transcurridos(self):
        """
        Calcula días hábiles (lunes a viernes) desde fecha_inicio_conteo_dias.
        Excluye sábados (5) y domingos (6).
        """
        for record in self:
            if not record.fecha_inicio_conteo_dias:
                record.dias_habiles_transcurridos = 0
                continue
            
            fecha_inicio = record.fecha_inicio_conteo_dias
            fecha_actual = date.today()
            
            # Si la fecha de inicio es futura, días = 0
            if fecha_inicio > fecha_actual:
                record.dias_habiles_transcurridos = 0
                continue
            
            dias = 0
            fecha_iter = fecha_inicio
            
            while fecha_iter < fecha_actual:
                # weekday(): 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo
                if fecha_iter.weekday() < 5:  # Lunes a Viernes
                    dias += 1
                fecha_iter += timedelta(days=1)
            
            record.dias_habiles_transcurridos = dias
    
    @api.depends('dias_extension_gerencia')
    def _compute_dias_tolerancia_total(self):
        """Calcula días totales de tolerancia (5 base + extensión)"""
        for record in self:
            record.dias_tolerancia_total = 5 + record.dias_extension_gerencia
    
    @api.depends('dias_habiles_transcurridos', 'dias_tolerancia_total', 
                 'fecha_descarga_contenedor', 'estado_ventas_id')
    def _compute_estado_plazo_venta(self):
        """
        Determina el estado del plazo según días transcurridos.
        REGLAS:
        - Sin descarga → 'pre_descarga'
        - 0-5 días → 'en_tolerancia'
        - 6-7 días → 'proxima_vencer'
        - 8+ días → 'vencida'
        - Si factura_venta → 'vendida'
        """
        for record in self:
            # Si ya se vendió
            if record.estado_ventas_id == 'entregada' or record.factura_venta:
                record.estado_plazo_venta = 'vendida'
                continue
            
            # Si no ha llegado el contenedor
            if not record.fecha_descarga_contenedor:
                record.estado_plazo_venta = 'pre_descarga'
                continue
            
            # Si no tiene cliente asignado (no aplica plazo)
            if not record.cliente_id:
                record.estado_plazo_venta = False
                continue
            
            dias = record.dias_habiles_transcurridos
            tolerancia = record.dias_tolerancia_total
            
            if dias <= tolerancia:
                record.estado_plazo_venta = 'en_tolerancia'
            elif dias <= tolerancia + 2:  # +2 días de advertencia
                record.estado_plazo_venta = 'proxima_vencer'
            else:
                record.estado_plazo_venta = 'vencida'
    
    @api.depends('fecha_inicio_conteo_dias', 'dias_tolerancia_total')
    def _compute_fecha_vencimiento_calculada(self):
        """Calcula la fecha exacta de vencimiento"""
        for record in self:
            if not record.fecha_inicio_conteo_dias:
                record.fecha_vencimiento_calculada = False
                continue
            
            # Sumar días hábiles a la fecha de inicio
            fecha = record.fecha_inicio_conteo_dias
            dias_a_sumar = record.dias_tolerancia_total
            dias_sumados = 0
            
            while dias_sumados < dias_a_sumar:
                fecha += timedelta(days=1)
                if fecha.weekday() < 5:  # Día hábil
                    dias_sumados += 1
            
            record.fecha_vencimiento_calculada = fecha
    
    @api.depends('historial_asignacion_ids')
    def _compute_total_cambios_cliente(self):
        """Cuenta todos los cambios de cliente desde el historial"""
        for record in self:
            cambios = record.historial_asignacion_ids.filtered(
                lambda h: h.tipo_accion in ['cambio_cliente', 'renovacion_artificial']
            )
            record.total_cambios_cliente = len(cambios)
    
    @api.depends('cliente_id', 'cliente_id.asesora_id')
    def _compute_asesora_actual(self):
        """Obtiene la asesora desde el cliente"""
        for record in self:
            if record.cliente_id and record.cliente_id.asesora_id:
                # asesora_id en res.partner es Many2one a res.partner
                # Necesitamos encontrar el usuario asociado
                asesora_partner = record.cliente_id.asesora_id
                user = self.env['res.users'].search([
                    ('partner_id', '=', asesora_partner.id)
                ], limit=1)
                record.asesora_actual_id = user.id if user else False
            else:
                record.asesora_actual_id = False
    
    # ============================================
    # OVERRIDE DEL MÉTODO WRITE
    # ============================================
    
    def write(self, vals):
        """
        Override del write para agregar lógica de control de asesoras.
        Se ejecuta DESPUÉS de la lógica SNMP del padre.
        """
        # ======================================
        # FASE 1: LÓGICA PRE-WRITE (VALIDACIONES)
        # ======================================
        
        for record in self:
            # Detectar si viene cambio de cliente
            if 'cliente_id' in vals:
                cliente_anterior = record.cliente_id
                cliente_nuevo_id = vals.get('cliente_id')
                cliente_nuevo = self.env['res.partner'].browse(cliente_nuevo_id) if cliente_nuevo_id else False
                
                # ===== CASO 1: Asignación de cliente (nuevo o cambio) =====
                if cliente_nuevo:
                    # Sub-caso 1A: Sincronizar asesora del cliente
                    record._sincronizar_asesora_cliente(cliente_nuevo, vals)
                    
                    # Sub-caso 1B: Detectar renovación artificial
                    if cliente_anterior and record.fecha_descarga_contenedor:
                        record._detectar_renovacion_artificial(
                            cliente_anterior, 
                            cliente_nuevo, 
                            vals
                        )
                    
                    # Sub-caso 1C: Registrar pre-asignación (antes de descarga)
                    elif not record.fecha_descarga_contenedor:
                        # Se está asignando ANTES de la descarga
                        _logger.info(
                            "[PRE-ASIGNACIÓN] Máquina %s asignada a cliente antes de descarga",
                            record.serie_id
                        )
                
                # ===== CASO 2: Liberación de cliente (cliente → NULL) =====
                else:
                    _logger.info(
                        "[LIBERACIÓN] Cliente removido de máquina %s",
                        record.serie_id
                    )
            
            # Detectar si viene check_ingreso (descarga del contenedor)
            if vals.get('check_ingreso') and not record.check_ingreso:
                # Primera vez que se marca check_ingreso
                if not record.fecha_descarga_contenedor:
                    vals['fecha_descarga_contenedor'] = date.today()
                    _logger.info(
                        "[DESCARGA] Contenedor descargado. Máquina %s - Fecha: %s",
                        record.serie_id,
                        date.today()
                    )
        
        # ======================================
        # FASE 2: EJECUTAR WRITE ORIGINAL (incluye lógica SNMP del padre)
        # ======================================
        
        result = super(SatSatAsesoras, self).write(vals)
        
        # ======================================
        # FASE 3: LÓGICA POST-WRITE (REGISTROS EN HISTORIAL)
        # ======================================
        
        for record in self:
            # Registrar en historial según el tipo de acción
            if 'cliente_id' in vals:
                cliente_anterior_id = vals.get('_cliente_anterior_id')  # Lo guardamos en _sincronizar
                cliente_nuevo = record.cliente_id
                
                if cliente_nuevo:
                    # Verificar si es sospechoso
                    es_sospechoso = vals.get('_es_renovacion_sospechosa', False)
                    
                    # Registrar en historial
                    Historial = self.env['asesora.asignacion.historial']
                    
                    if not record.fecha_descarga_contenedor:
                        # Pre-asignación
                        Historial.registrar_pre_asignacion(
                            maquina=record,
                            asesora=self.env.user,
                            cliente=cliente_nuevo
                        )
                    else:
                        # Cambio post-descarga
                        cliente_ant = self.env['res.partner'].browse(cliente_anterior_id) if cliente_anterior_id else False
                        Historial.registrar_cambio_cliente(
                            maquina=record,
                            cliente_anterior=cliente_ant,
                            cliente_nuevo=cliente_nuevo,
                            dias_transcurridos=record.dias_habiles_transcurridos,
                            es_sospechoso=es_sospechoso,
                            intentos_acumulados=record.intentos_cambio_cliente,
                            motivo=vals.get('_motivo_cambio', '')
                        )
                
                else:
                    # Cliente fue removido
                    Historial = self.env['asesora.asignacion.historial']
                    Historial.create({
                        'maquina_id': record.id,
                        'asesora_id': self.env.user.id,
                        'cliente_anterior_id': cliente_anterior_id,
                        'tipo_accion': 'liberacion_por_cliente',
                        'estado_plazo_al_cambio': record.estado_plazo_venta,
                        'dias_transcurridos': record.dias_habiles_transcurridos,
                        'fecha_descarga_contexto': record.fecha_descarga_contenedor,
                        'motivo_cambio': 'Asesora removió el cliente manualmente'
                    })
            
            # Registrar confirmación de descarga
            if vals.get('check_ingreso') and vals.get('fecha_descarga_contenedor'):
                if record.cliente_id:  # Solo si tiene cliente pre-asignado
                    Historial = self.env['asesora.asignacion.historial']
                    Historial.registrar_confirmacion_descarga(maquina=record)
                    
                    # Notificar a la asesora
                    record._notificar_inicio_plazo_asesora()
        
        return result
    
    # ============================================
    # MÉTODOS PRIVADOS DE VALIDACIÓN
    # ============================================
    
    def _sincronizar_asesora_cliente(self, cliente, vals):
        """
        Verifica y sincroniza la asesora del cliente con el usuario actual.
        Si el cliente tiene otra asesora, requiere confirmación.
        """
        self.ensure_one()
        
        usuario_actual = self.env.user
        usuario_actual_partner = usuario_actual.partner_id
        
        # Obtener asesora actual del cliente
        asesora_del_cliente = cliente.asesora_id
        
        # CASO 1: Cliente no tiene asesora → Asignar automáticamente
        if not asesora_del_cliente:
            cliente.sudo().write({'asesora_id': usuario_actual_partner.id})
            _logger.info(
                "[SYNC ASESORA] Cliente %s sin asesora. Asignada automáticamente: %s",
                cliente.name,
                usuario_actual.name
            )
            return
        
        # CASO 2: Cliente tiene la misma asesora → OK
        if asesora_del_cliente.id == usuario_actual_partner.id:
            _logger.debug(
                "[SYNC ASESORA] Cliente %s ya tiene asesora correcta: %s",
                cliente.name,
                usuario_actual.name
            )
            return
        
        # CASO 3: Cliente tiene OTRA asesora → Transferencia
        _logger.warning(
            "[SYNC ASESORA] TRANSFERENCIA DETECTADA - Cliente: %s | "
            "Asesora anterior: %s | Asesora nueva: %s",
            cliente.name,
            asesora_del_cliente.name,
            usuario_actual.name
        )
        
        # Actualizar asesora del cliente
        cliente.sudo().write({'asesora_id': usuario_actual_partner.id})
        
        # Registrar en historial
        asesora_anterior_user = self.env['res.users'].search([
            ('partner_id', '=', asesora_del_cliente.id)
        ], limit=1)
        
        if asesora_anterior_user:
            Historial = self.env['asesora.asignacion.historial']
            Historial.registrar_transferencia_asesora(
                maquina=self,
                asesora_anterior=asesora_anterior_user,
                asesora_nueva=usuario_actual,
                cliente=cliente,
                motivo=f'Cliente {cliente.name} transferido al asignar máquina {self.serie_id}'
            )
            
            # Notificar a ambas asesoras
            self._notificar_transferencia_cliente(
                cliente=cliente,
                asesora_anterior=asesora_anterior_user,
                asesora_nueva=usuario_actual
            )
    
    def _detectar_renovacion_artificial(self, cliente_anterior, cliente_nuevo, vals):
        """
        Detecta si el cambio de cliente es un intento de renovación artificial.
        REGLAS:
        - Si días > 3 y es la misma asesora → Sospechoso
        - Si intentos >= 2 → Alerta gerencia
        """
        self.ensure_one()
        
        # Solo aplicar si ya pasaron más de 3 días
        if self.dias_habiles_transcurridos <= 3:
            return
        
        # Verificar si es la misma asesora
        usuario_actual_partner = self.env.user.partner_id
        asesora_cliente_anterior = cliente_anterior.asesora_id
        
        if asesora_cliente_anterior and asesora_cliente_anterior.id == usuario_actual_partner.id:
            # Es la misma asesora cambiando cliente
            intentos = self.intentos_cambio_cliente + 1
            
            _logger.warning(
                "[RENOVACIÓN ARTIFICIAL] Detectada en máquina %s | "
                "Día: %d | Intento #%d | Asesora: %s",
                self.serie_id,
                self.dias_habiles_transcurridos,
                intentos,
                self.env.user.name
            )
            
            # Actualizar campos
            vals['intentos_cambio_cliente'] = intentos
            vals['ultima_fecha_cambio_cliente'] = fields.Datetime.now()
            vals['_cliente_anterior_id'] = cliente_anterior.id  # Para historial
            vals['_es_renovacion_sospechosa'] = True
            
            # Si es el 2do intento o más → Alerta gerencia
            if intentos >= 2:
                vals['es_renovacion_sospechosa'] = True
                self._notificar_renovacion_sospechosa_gerencia(
                    cliente_anterior,
                    cliente_nuevo,
                    intentos
                )
        else:
            # Es otra asesora (transferencia legítima)
            vals['_cliente_anterior_id'] = cliente_anterior.id
            vals['_es_renovacion_sospechosa'] = False
    
    # ============================================
    # MÉTODOS DE NOTIFICACIÓN
    # ============================================
    
    def _notificar_inicio_plazo_asesora(self):
        """Notifica a la asesora que inició el contador de 5 días"""
        self.ensure_one()
        
        if not self.asesora_actual_id:
            return
        
        # Obtener teléfono de la asesora
        phone = self.asesora_actual_id.partner_id.mobile
        if not phone:
            _logger.warning(
                "[NOTIF PLAZO] Asesora %s sin teléfono",
                self.asesora_actual_id.name
            )
            return
        
        # Limpiar teléfono
        phone_clean = phone.replace('+', '').replace(' ', '')
        if not phone_clean.startswith('51'):
            phone_clean = '51' + phone_clean
        
        # Calcular fecha de vencimiento
        fecha_venc = self.fecha_vencimiento_calculada.strftime('%d/%m/%Y') if self.fecha_vencimiento_calculada else 'N/A'
        
        mensaje = f"""📦 *¡DESCARGA CONFIRMADA!*

Máquina: *{self.name.name if self.name else 'N/A'}*
Serie: *{self.serie_id}*
Cliente: *{self.cliente_id.name if self.cliente_id else 'N/A'}*

⏰ *Contador iniciado: 5 días hábiles*
📅 Vencimiento: *{fecha_venc}*

🎯 ¡Es hora de cerrar la venta!
Ver detalle: {self.generate_record_url(self)}"""
        
        try:
            self._send_whatsapp_message_boot(phone_clean, mensaje)
            _logger.info(
                "[NOTIF PLAZO] WhatsApp enviado a %s por máquina %s",
                self.asesora_actual_id.name,
                self.serie_id
            )
        except Exception as e:
            _logger.error(
                "[NOTIF PLAZO] Error enviando WhatsApp: %s",
                e
            )
    
    def _notificar_transferencia_cliente(self, cliente, asesora_anterior, asesora_nueva):
        """Notifica transferencia de cliente entre asesoras"""
        self.ensure_one()
        
        # Notificar a asesora anterior
        if asesora_anterior and asesora_anterior.partner_id.mobile:
            phone = asesora_anterior.partner_id.mobile.replace('+', '').replace(' ', '')
            if not phone.startswith('51'):
                phone = '51' + phone
            
            mensaje_anterior = f"""⚠️ *TRANSFERENCIA DE CLIENTE*

Cliente: *{cliente.name}*
fue transferido a: *{asesora_nueva.name}*
Máquina involucrada: *{self.serie_id}*

Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}"""
            
            try:
                self._send_whatsapp_message_boot(phone, mensaje_anterior)
            except Exception as e:
                _logger.error("[NOTIF TRANSFER] Error enviando a asesora anterior: %s", e)
        
        # Notificar a asesora nueva
        if asesora_nueva and asesora_nueva.partner_id.mobile:
            phone = asesora_nueva.partner_id.mobile.replace('+', '').replace(' ', '')
            if not phone.startswith('51'):
                phone = '51' + phone
            
            dias_restantes = self.dias_tolerancia_total - self.dias_habiles_transcurridos
            
            mensaje_nueva = f"""✅ *CLIENTE TRANSFERIDO*

Cliente: *{cliente.name}*
ahora es tu responsabilidad.
Máquina: *{self.serie_id}*

⏰ Días restantes: *{dias_restantes if dias_restantes > 0 else 0}*
Anterior asesora: {asesora_anterior.name if asesora_anterior else 'N/A'}

Ver detalle: {self.generate_record_url(self)}"""
            
            try:
                self._send_whatsapp_message_boot(phone, mensaje_nueva)
            except Exception as e:
                _logger.error("[NOTIF TRANSFER] Error enviando a asesora nueva: %s", e)
    
    def _notificar_renovacion_sospechosa_gerencia(self, cliente_anterior, cliente_nuevo, intentos):
        """Notifica a gerencia sobre renovación sospechosa"""
        self.ensure_one()
        
        # Buscar gerente (puedes personalizar esto)
        gerente = self.env.ref('base.user_admin', raise_if_not_found=False)
        if not gerente:
            gerente = self.env['res.users'].search([('groups_id', 'in', [self.env.ref('base.group_system').id])], limit=1)
        
        if not gerente:
            _logger.warning("[NOTIF GERENCIA] No se encontró gerente para notificar")
            return
        
        # Mensaje en chatter
        body = f"""🚨 <b>ALERTA: Renovación artificial detectada</b><br/>
<b>Máquina:</b> {self.name.name if self.name else 'N/A'} - {self.serie_id}<br/>
<b>Asesora:</b> {self.env.user.name}<br/>
<b>Cliente anterior:</b> {cliente_anterior.name}<br/>
<b>Cliente nuevo:</b> {cliente_nuevo.name}<br/>
<b>Día:</b> {self.dias_habiles_transcurridos}<br/>
<b>Intento #:</b> {intentos}<br/>
<br/>
<span style="color:red;">⚠️ Posible intento de retención indebida.</span><br/>
Enlace: {self.generate_record_url(self)}"""
        
        self.message_post(
            body=body,
            partner_ids=[gerente.partner_id.id],
            subtype_xmlid='mail.mt_comment'
        )
        
        _logger.warning(
            "[NOTIF GERENCIA] Alerta enviada por renovación sospechosa en %s",
            self.serie_id
        )
    
    # ============================================
    # MÉTODOS PÚBLICOS - ACCIONES
    # ============================================
    
    def action_otorgar_extension(self):
        """Permite a gerencia otorgar días de extensión"""
        self.ensure_one()
        
        return {
            'name': 'Otorgar extensión de plazo',
            'type': 'ir.actions.act_window',
            'res_model': 'sat.wizard.otorgar.extension',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_maquina_id': self.id}
        }
    
    def action_liberar_manualmente(self):
        """Permite a gerencia liberar manualmente una máquina"""
        self.ensure_one()
        
        if not self.cliente_id:
            raise UserError("Esta máquina no tiene cliente asignado.")
        
        # Registrar en historial
        Historial = self.env['asesora.asignacion.historial']
        Historial.create({
            'maquina_id': self.id,
            'asesora_id': self.env.user.id,
            'cliente_anterior_id': self.cliente_id.id,
            'tipo_accion': 'liberacion_manual',
            'estado_plazo_al_cambio': self.estado_plazo_venta,
            'dias_transcurridos': self.dias_habiles_transcurridos,
            'fecha_descarga_contexto': self.fecha_descarga_contenedor,
            'aprobado_por_id': self.env.user.id,
            'motivo_cambio': 'Liberación manual por gerencia'
        })
        
        # Liberar
        self.write({
            'cliente_id': False,
            'disponibilidad_id': 'disponible',
            'intentos_cambio_cliente': 0,
            'es_renovacion_sospechosa': False,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Máquina liberada"),
                'message': _("La máquina ha sido liberada y está disponible."),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_ver_historial_asignaciones(self):
        """Abre vista del historial de asignaciones"""
        self.ensure_one()
        
        return {
            'name': f'Historial de asignaciones - {self.serie_id}',
            'type': 'ir.actions.act_window',
            'res_model': 'asesora.asignacion.historial',
            'view_mode': 'tree,form',
            'domain': [('maquina_id', '=', self.id)],
            'context': {'default_maquina_id': self.id}
        }
    
    # ============================================
    # CRON - LIBERACIÓN AUTOMÁTICA
    # ============================================
    
    @api.model
    def cron_liberar_maquinas_vencidas(self):
        """
        CRON que se ejecuta diariamente para liberar máquinas vencidas.
        Solo libera si:
        - Días > tolerancia
        - No está bloqueada por gerencia
        - Tiene cliente asignado
        """
        _logger.info("[CRON LIBERACIÓN] Iniciando verificación de máquinas vencidas...")
        
        # Buscar máquinas vencidas
        maquinas_vencidas = self.search([
            ('estado_plazo_venta', '=', 'vencida'),
            ('bloqueada_por_gerencia', '=', False),
            ('cliente_id', '!=', False),
            ('estado_ventas_id', '!=', 'entregada'),
        ])
        
        liberadas = 0
        for maquina in maquinas_vencidas:
            try:
                # Verificar que realmente está vencida
                if maquina.dias_habiles_transcurridos <= maquina.dias_tolerancia_total:
                    continue
                
                _logger.info(
                    "[CRON LIBERACIÓN] Liberando máquina %s (Días: %d, Tolerancia: %d)",
                    maquina.serie_id,
                    maquina.dias_habiles_transcurridos,
                    maquina.dias_tolerancia_total
                )
                
                # Registrar en historial
                Historial = self.env['asesora.asignacion.historial']
                Historial.registrar_liberacion_automatica(
                    maquina=maquina,
                    dias_transcurridos=maquina.dias_habiles_transcurridos
                )
                
                # Actualizar performance de la asesora (penalización)
                if maquina.asesora_actual_id:
                    Performance = self.env['asesora.performance']
                    perf = Performance.get_or_create_performance(maquina.asesora_actual_id.id)
                    perf.aplicar_penalizacion(
                        tipo='liberacion_automatica',
                        puntos=10,
                        motivo=f'Máquina {maquina.serie_id} liberada por plazo vencido ({maquina.dias_habiles_transcurridos} días)'
                    )
                
                # Liberar máquina
                maquina.write({
                    'cliente_id': False,
                    'disponibilidad_id': 'disponible',
                })
                
                # Notificar a la asesora
                maquina._notificar_liberacion_automatica()
                
                liberadas += 1
                
            except Exception as e:
                _logger.error(
                    "[CRON LIBERACIÓN] Error liberando máquina %s: %s",
                    maquina.serie_id,
                    e
                )
        
        _logger.info(
            "[CRON LIBERACIÓN] Finalizado. Total liberadas: %d de %d",
            liberadas,
            len(maquinas_vencidas)
        )
        
        return liberadas
    
    def _notificar_liberacion_automatica(self):
        """Notifica a la asesora que su máquina fue liberada"""
        self.ensure_one()
        
        if not self.asesora_actual_id or not self.asesora_actual_id.partner_id.mobile:
            return
        
        phone = self.asesora_actual_id.partner_id.mobile.replace('+', '').replace(' ', '')
        if not phone.startswith('51'):
            phone = '51' + phone
        
        mensaje = f"""❌ *MÁQUINA LIBERADA AUTOMÁTICAMENTE*

Máquina: *{self.name.name if self.name else 'N/A'}*
Serie: *{self.serie_id}*
Días transcurridos: *{self.dias_habiles_transcurridos}*

La máquina fue liberada por exceder el plazo de tolerancia.
Score: -10 puntos

💡 Máquinas disponibles: {self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/web#action=sat.action_window"""
        
        try:
            self._send_whatsapp_message_boot(phone, mensaje)
        except Exception as e:
            _logger.error("[NOTIF LIBERACIÓN] Error enviando WhatsApp: %s", e)
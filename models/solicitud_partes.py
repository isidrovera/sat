import calendar
import requests
import uuid
from urllib.parse import urlencode
from odoo.exceptions import UserError, ValidationError
import io
import qrcode
import re
import base64
from io import BytesIO
import xlwt
from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
class SolicitudPartes(models.Model):
    _name = 'solicitud.partes'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Solicitud de Partes'
    _order = 'fecha_solicitud desc, id desc'

    name = fields.Char(string='Número de Solicitud',
                       readonly=True, copy=False, default='Nuevo')

    maquina_origen_id = fields.Many2one(
        'alquiler',
        string='Máquina Origen',
        required=True,
        tracking=True,
        domain="[('estado_alquiler_id', 'not in', ['vendida', 'partes'])]"
    )
    maquina_destino_id = fields.Many2one(
        'alquiler',
        string='Máquina Destino',
        tracking=True,
        domain="[('id', '!=', maquina_origen_id), ('estado_alquiler_id', 'not in', ['vendida'])]"
    )

    fecha_solicitud = fields.Datetime(
        string='Fecha de Solicitud', default=fields.Datetime.now, tracking=True, readonly=True)
    solicitante_id = fields.Many2one('res.users', string='Solicitante',
                                     default=lambda self: self.env.user, tracking=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('submitted', 'Enviado'),
        ('approved', 'Aprobado'),
        ('completed', 'Completado'),
        ('replaced', 'Reemplazado'),
        ('rejected', 'Rechazado')
    ], string='Estado', default='draft', tracking=True)

    # Campos de autorización
    autorizado_por = fields.Many2one(
        'res.users', string='Autorizado por', tracking=True, readonly=False)
    fecha_autorizacion = fields.Datetime(
        string='Fecha de Autorización', tracking=True, readonly=False)

    # Campos de retiro
    retirado_por = fields.Many2one(
        'res.users', string='Retirado por', tracking=True, readonly=False)
    fecha_retiro = fields.Datetime(
        string='Fecha de Retiro', tracking=True, readonly=False)

    # Campos de reemplazo
    reemplazado_por = fields.Many2one(
        'res.users', string='Reemplazado por', tracking=True, readonly=False)
    fecha_reemplazo = fields.Datetime(
        string='Fecha de Reemplazo', tracking=True, readonly=False)

    parte_ids = fields.One2many(
        'solicitud.partes.linea', 'solicitud_id', string='Partes Solicitadas')
    access_token = fields.Char('Token de Acceso', copy=False, readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'solicitud.partes') or 'Nuevo'
        vals['access_token'] = uuid.uuid4().hex
        return super().create(vals)

    def action_submit(self):
        self.ensure_one()
        if not self.parte_ids:
            raise UserError(
                _('Debe agregar al menos una parte antes de enviar la solicitud.'))
        self.write({'state': 'submitted'})
        template = self.env.ref('sat.email_template_solicitud_partes_alquiler')
        template.send_mail(self.id, force_send=True)

    def action_approve(self):
        self.ensure_one()
        self.write({
            'state': 'approved',
            'autorizado_por': self.env.user.id,
            'fecha_autorizacion': fields.Datetime.now()
        })

    def action_complete(self):
        self.ensure_one()
        if not all(line.estado in ['retirado', 'reemplazado'] for line in self.parte_ids):
            raise UserError(
                _('Todas las partes deben estar retiradas o reemplazadas.'))
        self.write({
            'state': 'completed',
            'retirado_por': self.env.user.id,
            'fecha_retiro': fields.Datetime.now()
        })
        self.maquina_origen_id.write({'estado_alquiler_id': 'con_problemas'})

    def action_replace(self):
        self.ensure_one()
        if not all(line.estado == 'reemplazado' for line in self.parte_ids):
            raise UserError(_('Todas las partes deben estar reemplazadas.'))
        self.write({
            'state': 'replaced',
            'reemplazado_por': self.env.user.id,
            'fecha_reemplazo': fields.Datetime.now()
        })
        # Si todas las partes están en buen estado, restaurar estado de la máquina
        if all(line.condicion == 'bueno' for line in self.parte_ids):
            self.maquina_origen_id.write({'estado_alquiler_id': 'alquilada'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    @api.model
    def approve_from_token(self, token):
        """Aprobar desde token de email"""
        solicitud = self.search([
            ('access_token', '=', token),
            ('state', '=', 'submitted')
        ], limit=1)

        if solicitud:
            try:
                # Aprobar con contexto de usuario público pero guardando quien autorizó
                solicitud.with_context(mail_create_nosubscribe=True).write({
                    'autorizado_por': self.env.ref('base.user_admin').id  # Usuario admin por defecto
                })
                solicitud._aprobar_y_notificar()
                return {'success': True, 'solicitud_id': solicitud.id}
            except Exception as e:
                _logger.error(f"Error aprobando solicitud {solicitud.name}: {str(e)}")
                return {'error': str(e)}
        
        # Buscar si ya fue aprobada
        solicitud_aprobada = self.search([
            ('access_token', '=', token),
            ('state', '!=', 'submitted')
        ], limit=1)
        
        if solicitud_aprobada:
            return {'error': 'Esta solicitud ya fue procesada anteriormente'}
        
        return {'error': 'Token inválido o solicitud no encontrada'}

    # ============================================================
# AGREGAR AL FINAL DE LA CLASE SolicitudPartes 
# (después del método approve_from_token)
# ============================================================

    # Nuevo campo: Autorizado para retirar (diferente de quien autoriza)
    autorizado_retirar_id = fields.Many2one(
        'res.users', 
        string='Autorizado para Retirar',
        tracking=True,
        help="Usuario autorizado para retirar las partes del equipo"
    )
    
    # Campo computed para teléfono limpio
    autorizado_retirar_mobile_clean = fields.Char(
        string='Teléfono Autorizado (limpio)',
        compute='_compute_autorizado_mobile_clean',
        store=True
    )
    
    # Control de notificaciones
    fecha_notificacion_retiro = fields.Datetime(
        string='Fecha Notificación Retiro',
        readonly=True,
        tracking=True
    )
    
    # Campos computed para estados
    todas_retiradas = fields.Boolean(
        string='Todas Retiradas',
        compute='_compute_estado_partes',
        store=True
    )
    todas_repuestas = fields.Boolean(
        string='Todas Repuestas',
        compute='_compute_estado_partes',
        store=True
    )
    pendientes_reposicion = fields.Boolean(
        string='Pendientes Reposición',
        compute='_compute_estado_partes',
        store=True
    )

    @api.depends('autorizado_retirar_id.mobile_phone')
    def _compute_autorizado_mobile_clean(self):
        """Limpia y formatea el teléfono del autorizado"""
        for record in self:
            if record.autorizado_retirar_id and record.autorizado_retirar_id.mobile_phone:
                phone = record.autorizado_retirar_id.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.autorizado_retirar_mobile_clean = phone
            else:
                record.autorizado_retirar_mobile_clean = ''
    
    @api.depends('parte_ids.estado')
    def _compute_estado_partes(self):
        """Calcula estados generales de las partes"""
        for record in self:
            if not record.parte_ids:
                record.todas_retiradas = False
                record.todas_repuestas = False
                record.pendientes_reposicion = False
                continue
            
            record.todas_retiradas = all(
                line.estado in ['retirado', 'reemplazado'] 
                for line in record.parte_ids
            )
            record.todas_repuestas = all(
                line.estado == 'reemplazado' 
                for line in record.parte_ids
            )
            record.pendientes_reposicion = any(
                line.estado == 'retirado' and line.instalado_por
                for line in record.parte_ids
            )

    # MODIFICAR el método action_approve existente
    def action_approve(self):
        """Aprobar solicitud - ahora con selección de autorizado"""
        self.ensure_one()
        
        # Si no hay autorizado, abrir wizard
        if not self.autorizado_retirar_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Seleccionar Autorizado para Retiro',
                'res_model': 'solicitud.partes.aprobar.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_solicitud_id': self.id}
            }
        
        # Si ya tiene autorizado, aprobar
        return self._aprobar_y_notificar()
    
    def _aprobar_y_notificar(self):
        """Aprobar y notificar al jefe de área"""
        self.ensure_one()
        
        self.write({
            'state': 'approved',
            'autorizado_por': self.env.user.id,
            'fecha_autorizacion': fields.Datetime.now()
        })
        
        # Notificar al jefe de área (número fijo)
        self._enviar_whatsapp_jefe_area()
        
        self.message_post(
            body=f"✅ Solicitud aprobada por {self.env.user.name}. Notificación enviada a jefe de área."
        )
    
    def _enviar_whatsapp_jefe_area(self):
        """Notifica al jefe de área que debe autorizar el retiro"""
        self.ensure_one()
        
        JEFE_AREA_PHONE = '51975399303'  # Número fijo del jefe
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_solicitud_partes_alquiler').id
        solicitud_url = f"{base_url}/web#id={self.id}&view_type=form&model=solicitud.partes&action={action_id}"
        
        partes_lista = "\n".join([
            f"  • {line.parte}" + (f" - {line.descripcion}" if line.descripcion else "")
            for line in self.parte_ids
        ])
        
        msg = f"""🔧 *Solicitud de Partes Aprobada*

*Solicitud:* {self.name}
*Aprobada por:* {self.autorizado_por.name}
*Solicitante:* {self.solicitante_id.name}

*Máquina Origen:* {self.maquina_origen_id.name.name} (Serie: {self.maquina_origen_id.serie})
{'*Máquina Destino:* ' + self.maquina_destino_id.name.name if self.maquina_destino_id else ''}

*Partes solicitadas:*
{partes_lista}

⚠️ *ACCIÓN REQUERIDA:*
Debes autorizar el retiro y asignar responsables.

👉 *ACCEDER A LA SOLICITUD:*
{solicitud_url}"""
        
        self.send_whatsapp_message(JEFE_AREA_PHONE, msg)
        _logger.info(f"WhatsApp enviado al jefe de área (975399303) para solicitud {self.name}")


    def action_autorizar_retiro(self):
        """Autorizar retiro - abre wizard para asignar responsables"""
        self.ensure_one()
        
        if self.state != 'approved':
            raise UserError(_('Solo se puede autorizar en estado Aprobado'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Autorizar Retiro y Asignar Responsables',
            'res_model': 'solicitud.partes.autorizar.retiro.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_solicitud_id': self.id}
        }
    
    def _autorizar_retiro_confirmar(self, autorizado_retirar_id, responsable_reposicion_id):
        """Confirma la autorización con responsables asignados"""
        self.ensure_one()
        
        self.write({
            'autorizado_retirar_id': autorizado_retirar_id,
            'responsable_reposicion_id': responsable_reposicion_id
        })
        
        # Notificar a quien retira
        self._enviar_whatsapp_autorizado_retiro()
        
        # Notificar a quien repone
        self._enviar_whatsapp_responsable_reposicion()
        
        self.message_post(
            body=f"✅ Retiro autorizado:\n"
                 f"- Autorizado para retirar: {self.autorizado_retirar_id.name}\n"
                 f"- Responsable de reposición: {self.responsable_reposicion_id.name}"
        )

    def _enviar_whatsapp_autorizado_retiro(self):
        """Notifica a quien retira"""
        if not self.autorizado_retirar_mobile_clean:
            return
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_solicitud_partes_alquiler').id
        url = f"{base_url}/web#id={self.id}&view_type=form&model=solicitud.partes&action={action_id}"
        
        partes = "\n".join([f"  • {l.parte}" for l in self.parte_ids])
        
        msg = f"""🔧 *Autorizado para Retirar Partes*

Hola *{self.autorizado_retirar_id.name}*,

Estás autorizado para retirar:

*Solicitud:* {self.name}
*Partes:*
{partes}

*Responsable de reposición:* {self.responsable_reposicion_id.name}

👉 *CONFIRMAR RETIRO:*
{url}

Ingresa y confirma el retiro desde el botón."""
        
        self.send_whatsapp_message(self.autorizado_retirar_mobile_clean, msg)
    
    def _enviar_whatsapp_responsable_reposicion(self):
        """Notifica a responsable de reposición"""
        if not self.responsable_reposicion_mobile_clean:
            return
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_solicitud_partes_alquiler').id
        url = f"{base_url}/web#id={self.id}&view_type=form&model=solicitud.partes&action={action_id}"
        
        partes = "\n".join([f"  • {l.parte}" for l in self.parte_ids])
        
        msg = f"""🔧 *Responsable de Reposición*

Hola *{self.responsable_reposicion_id.name}*,

Serás responsable de recibir e instalar:

*Solicitud:* {self.name}
*Partes:*
{partes}

⚠️ *IMPORTANTE:*
Después de instalar debes REPONER estas partes con foto.

👉 *VER SOLICITUD:*
{url}"""
        
        self.send_whatsapp_message(self.responsable_reposicion_mobile_clean, msg)
    
    def _enviar_whatsapp_autorizacion_retiro(self):
        """Envía WhatsApp al autorizado"""
        self.ensure_one()
        
        if not self.autorizado_retirar_mobile_clean:
            _logger.warning(
                f"Solicitud {self.name}: usuario {self.autorizado_retirar_id.name} sin teléfono"
            )
            return
        
        partes_lista = "\n".join([
            f"  • {line.parte}" + (f" - {line.descripcion}" if line.descripcion else "")
            for line in self.parte_ids
        ])
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        
        msg = f"""🔧 *Retiro de Partes Autorizado*

Hola *{self.autorizado_retirar_id.name}*,

Estás autorizado para retirar las siguientes partes:

*Solicitud:* {self.name}
*Máquina Origen:* {self.maquina_origen_id.name.name} (Serie: {self.maquina_origen_id.serie})
{'*Máquina Destino:* ' + self.maquina_destino_id.name.name if self.maquina_destino_id else ''}

*Partes:*
{partes_lista}

*Autorizado por:* {self.autorizado_por.name}

Confirma el retiro desde el sistema."""
        
        self.send_whatsapp_message(self.autorizado_retirar_mobile_clean, msg)
    
    def send_whatsapp_message(self, phone, message):
        """Envía WhatsApp usando API externa"""
        url = 'https://whatsapp.andessolutioncopiers.com/api/message'
        data = {'phone': phone, 'message': message}
        headers = {'Content-Type': 'application/json'}
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            _logger.info(f"WhatsApp - Status: {response.status_code}")
            return response.json()
        except Exception as e:
            _logger.error(f"Error WhatsApp: {str(e)}")
            return {"error": str(e)}
    
    def action_check_reposiciones_pendientes(self):
        """Verifica reposiciones pendientes (cron job)"""
        from datetime import timedelta
        limite = fields.Datetime.now() - timedelta(hours=48)
        
        solicitudes = self.search([
            ('state', 'in', ['completed', 'approved']),
            ('pendientes_reposicion', '=', True)
        ])
        
        for sol in solicitudes:
            for linea in sol.parte_ids:
                if (linea.estado == 'retirado' and 
                    linea.instalado_por and 
                    linea.fecha_retiro_real and 
                    linea.fecha_retiro_real < limite):
                    linea._enviar_recordatorio_reposicion()
        
        return True


    responsable_reposicion_id = fields.Many2one(
        'res.users',
        string='Responsable de Reposición',
        tracking=True,
        help="Usuario que recibirá e instalará la parte (responsable de reponer)"
    )
    responsable_reposicion_mobile_clean = fields.Char(
        string='Teléfono Responsable Reposición',
        compute='_compute_responsable_reposicion_mobile',
        store=True
    )

    @api.depends('responsable_reposicion_id.mobile_phone')
    def _compute_responsable_reposicion_mobile(self):
        """Limpia teléfono del responsable de reposición"""
        for record in self:
            if record.responsable_reposicion_id and record.responsable_reposicion_id.mobile_phone:
                phone = record.responsable_reposicion_id.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.responsable_reposicion_mobile_clean = phone
            else:
                record.responsable_reposicion_mobile_clean = ''
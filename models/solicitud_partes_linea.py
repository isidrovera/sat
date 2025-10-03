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
class SolicitudPartesLinea(models.Model):
    _name = 'solicitud.partes.linea'
    _description = 'Línea de Solicitud de Partes'

    solicitud_id = fields.Many2one('solicitud.partes', string='Solicitud')
    parte = fields.Char(string='Parte/Unidad', required=True)
    descripcion = fields.Text(string='Descripción')
    estado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('retirado', 'Retirado'),
        ('reemplazado', 'Reemplazado')
    ], string='Estado', default='pendiente')

    # Campos de reemplazo
    fecha_reemplazo = fields.Datetime(string='Fecha Reemplazo')
    reemplazado_por = fields.Many2one('res.users', string='Reemplazado por')
    condicion = fields.Selection([
        ('bueno', 'Buen Estado'),
        ('defectuoso', 'Defectuoso')
    ], string='Condición')

    # Relación con máquina origen a través de solicitud
    maquina_origen_id = fields.Many2one(
        'alquiler',
        string='Máquina Origen',
        related='solicitud_id.maquina_origen_id',
        store=True
    )

    def action_retirar(self):
        """Confirmar retiro - directo sin wizard"""
        self.ensure_one()
        
        if not self.solicitud_id.autorizado_retirar_id:
            raise UserError(_('Primero debe autorizar el retiro en la solicitud'))
        
        # Validar que solo el autorizado pueda retirar
        if self.env.user != self.solicitud_id.autorizado_retirar_id:
            raise UserError(_(f'Solo {self.solicitud_id.autorizado_retirar_id.name} puede confirmar este retiro'))
        
        # Confirmar retiro directo - el responsable ya está definido
        self.write({
            'estado': 'retirado',
            'fecha_retiro_real': fields.Datetime.now(),
            'instalado_por': self.solicitud_id.responsable_reposicion_id.id
        })
        
        self.solicitud_id.message_post(
            body=f"🔧 Parte retirada: {self.parte} por {self.env.user.name}. Responsable de reposición: {self.solicitud_id.responsable_reposicion_id.name}"
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Retiro Confirmado',
                'message': f'Parte "{self.parte}" retirada correctamente',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_reemplazar(self):
        """Reponer con foto - wizard"""
        self.ensure_one()
        
        if self.env.user != self.instalado_por:
            raise UserError(_(f'Solo {self.instalado_por.name} puede reponer esta parte'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmar Reposición',
            'res_model': 'solicitud.partes.reposicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_parte_linea_id': self.id}
        }

    def action_registrar_condicion(self):
        return {
            'name': 'Registrar Condición',
            'type': 'ir.actions.act_window',
            'res_model': 'registro.condicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_parte_id': self.id}
        }

    access_token_linea = fields.Char(
        'Token Acceso Línea',
        default=lambda self: str(uuid.uuid4()),
        copy=False,
        readonly=True
    )

    # Campo: quien instala (diferente de quien retira)
    instalado_por = fields.Many2one(
        'res.users',
        string='Instalado/Recibido por',
        tracking=True,
        help="Usuario que recibe e instala la parte"
    )
    
    instalado_por_mobile_clean = fields.Char(
        string='Teléfono Instalador',
        compute='_compute_instalado_mobile_clean',
        store=True
    )
    
    fecha_instalacion = fields.Datetime(
        string='Fecha Instalación',
        tracking=True
    )
    
    # Fecha real de retiro (distinta de la fecha_retiro del header)
    fecha_retiro_real = fields.Datetime(
        string='Fecha Retiro Real',
        tracking=True
    )
    
    # Control de reposición
    estado_reposicion = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('notificado', 'Notificado'),
        ('repuesta', 'Repuesta')
    ], string='Estado Reposición', default='pendiente', tracking=True)
    
    # Foto de reposición
    foto_reposicion = fields.Binary(
        string='Foto Reposición',
        attachment=True
    )
    foto_reposicion_filename = fields.Char(string='Nombre Foto')
    
    observaciones_instalacion = fields.Text(string='Observaciones')

    @api.depends('instalado_por.mobile_phone')
    def _compute_instalado_mobile_clean(self):
        """Limpia teléfono del instalador"""
        for record in self:
            if record.instalado_por and record.instalado_por.mobile_phone:
                phone = record.instalado_por.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.instalado_por_mobile_clean = phone
            else:
                record.instalado_por_mobile_clean = ''

   
    
    def _confirmar_retiro(self, instalado_por_id, yo_mismo=False):
        """Confirma el retiro interno"""
        self.ensure_one()
        
        self.write({
            'estado': 'retirado',
            'fecha_retiro_real': fields.Datetime.now(),
            'instalado_por': instalado_por_id,
            'fecha_instalacion': fields.Datetime.now() if yo_mismo else False
        })
        
        # Si es otra persona, notificar
        if not yo_mismo and self.instalado_por_mobile_clean:
            self._enviar_whatsapp_instalacion()
        
        mensaje = f"🔧 Parte retirada: {self.parte}"
        if yo_mismo:
            mensaje += f" - {self.instalado_por.name} la instalará"
        else:
            mensaje += f" - Entregada a {self.instalado_por.name}"
        
        self.solicitud_id.message_post(
            body=mensaje,
            partner_ids=[self.instalado_por.partner_id.id] if self.instalado_por else []
        )
    
    def _enviar_whatsapp_instalacion(self):
        """Notifica al instalador con URLs directas"""
        self.ensure_one()
        
        if not self.instalado_por_mobile_clean:
            return
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        
        # URLs directas con token
        url_reposicion = f"{base_url}/partes/reponer/{self.access_token_linea}"
        
        msg = f"""🔧 *Parte Recibida para Instalación*

Hola *{self.instalado_por.name}*,

Has recibido esta parte para instalar:

*Solicitud:* {self.solicitud_id.name}
*Parte:* {self.parte}
{f'*Descripción:* {self.descripcion}' if self.descripcion else ''}

*Máquina Origen:* {self.solicitud_id.maquina_origen_id.name.name} (Serie: {self.solicitud_id.maquina_origen_id.serie})

⚠️ *IMPORTANTE:* Después de instalar, debes reponer la parte con foto.

👉 *REPONER PARTE (con foto):*
{url_reposicion}

Este link te llevará directo al formulario de reposición."""
        
        self.solicitud_id.send_whatsapp_message(self.instalado_por_mobile_clean, msg)
    
    # MODIFICAR método action_reemplazar existente
    def action_reemplazar(self):
        """Reemplazar con foto - ahora con wizard"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmar Reposición',
            'res_model': 'solicitud.partes.reposicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_parte_linea_id': self.id}
        }
    
    def _confirmar_reposicion(self, condicion, foto, foto_filename, observaciones=None):
        """Confirma reposición interna"""
        self.ensure_one()
        
        if not foto:
            raise UserError(_('Debe adjuntar foto'))
        
        self.write({
            'estado': 'reemplazado',
            'fecha_reemplazo': fields.Datetime.now(),
            'reemplazado_por': self.env.user.id,
            'condicion': condicion,
            'estado_reposicion': 'repuesta',
            'foto_reposicion': foto,
            'foto_reposicion_filename': foto_filename,
            'observaciones_instalacion': observaciones
        })
        
        self.solicitud_id.message_post(
            body=f"✅ Parte repuesta: {self.parte} - {dict(self._fields['condicion'].selection).get(condicion)}"
        )
    
    def _enviar_recordatorio_reposicion(self):
        """Recordatorio con link directo"""
        self.ensure_one()
        
        if not self.instalado_por_mobile_clean:
            return
        
        # Solo 1 vez al día
        if (self.estado_reposicion == 'notificado' and 
            self.write_date and 
            self.write_date.date() == fields.Date.today()):
            return
        
        dias = (fields.Datetime.now() - self.fecha_retiro_real).days
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        url_reposicion = f"{base_url}/partes/reponer/{self.access_token_linea}"
        
        msg = f"""⚠️ *RECORDATORIO: Reposición Pendiente*

Hola *{self.instalado_por.name}*,

Parte pendiente de reponer:

*Solicitud:* {self.solicitud_id.name}
*Parte:* {self.parte}
*Retirada hace:* {dias} días

⚠️ *ACCIÓN REQUERIDA*

👉 *REPONER AHORA:*
{url_reposicion}"""
        
        self.solicitud_id.send_whatsapp_message(self.instalado_por_mobile_clean, msg)
        self.write({'estado_reposicion': 'notificado'})
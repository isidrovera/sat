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
class InspeccionResultado(models.Model):
    _name = 'inspeccion.resultado'
    _description = 'Resultado de inspección de sitio'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Número', readonly=True, copy=False, default='Nuevo')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'inspeccion.resultado') or 'Nuevo'
        records = super().create(vals_list)
        for record in records:
            record._update_estado()
            if record.alquiler_id:
                record.alquiler_id._compute_apto()
        return records

    def write(self, vals):
        res = super(InspeccionResultado, self).write(vals)
        self._update_estado()
        if any(field in vals for field in ['punto_corriente', 'punto_red', 'espacio']):
            for record in self:
                if record.alquiler_id:
                    record.alquiler_id._compute_apto()
        return res
    alquiler_id = fields.Many2one('alquiler', required=True)
    fecha = fields.Datetime('Fecha de inspección', default=fields.Datetime.now)

    # Instalación Eléctrica
    punto_corriente = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No'),
        ('pendiente', 'Requiere instalación')
    ], string='Punto eléctrico', required=True)
    voltaje = fields.Float('Voltaje medido (V)')

    # Infraestructura de Red
    punto_red = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No'),
        ('pendiente', 'Requiere instalación')
    ], string='Punto de red', required=True)
    wifi = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='Señal WiFi')
    area_sistemas = fields.Boolean('¿Cuenta con área de sistemas?')
    contacto_sistemas = fields.Char('Contacto del área de sistemas')

    # Control de Impresión
    control_impresion = fields.Boolean('¿Requiere control de impresión?')
    tipo_control = fields.Selection([
        ('usuario', 'Por usuario'),
        ('departamento', 'Por departamento'),
        ('proyecto', 'Por proyecto')
    ], string='Tipo de control')
    cantidad_usuarios = fields.Integer('Cantidad de usuarios')
    requiere_reportes = fields.Boolean('¿Requiere reportes de uso?')
    frecuencia_reportes = fields.Selection([
        ('diario', 'Diario'),
        ('semanal', 'Semanal'),
        ('mensual', 'Mensual')
    ], string='Frecuencia de reportes')

    # Entorno de PCs
    cantidad_windows = fields.Integer('Cantidad de PCs Windows')
    cantidad_mac = fields.Integer('Cantidad de PCs Mac')
    cantidad_linux = fields.Integer('Cantidad de PCs Linux')

    # Configuración de Escaneo
    usar_smb = fields.Boolean('¿Usará escaneo a carpeta compartida (SMB)?')
    usar_ftp = fields.Boolean('¿Usará escaneo a FTP?')
    usar_email = fields.Boolean('¿Usará escaneo a email?')
    tipo_servidor_email = fields.Selection([
        ('propio', 'Servidor de correo propio'),
        ('proveedor', 'Servidor del proveedor')
    ], string='Tipo de servidor email')
    servidor_email_propio = fields.Char(
        'Servidor SMTP propio', help='Solo si usará su propio servidor de correo')

    # Espacio Físico y Acceso
    piso = fields.Integer('Número de piso')
    ascensor = fields.Boolean('Tiene ascensor')
    espacio = fields.Float('Espacio disponible (m²)')
    ancho_pasillo = fields.Float('Ancho de pasillo (m)')
    tiene_estacionamiento = fields.Boolean(
        '¿Tiene estacionamiento para camión?')
    observaciones_estacionamiento = fields.Text(
        'Observaciones de estacionamiento')

    # Estado y Observaciones
    estado = fields.Selection([
        ('pendiente', 'Pendiente de revisión'),
        ('aprobado', 'Aprobado'),
        ('requiere_cambios', 'Requiere cambios'),
        ('rechazado', 'No viable')
    ], string='Estado', default='pendiente')
    observaciones = fields.Text('Observaciones')
    requisitos_pendientes = fields.Text('Requisitos pendientes')
    puede_reenviar = fields.Boolean('Puede reenviar formulario', default=True)

    @api.onchange('usar_email')
    def _onchange_usar_email(self):
        if not self.usar_email:
            self.tipo_servidor_email = False
            self.servidor_email_propio = False

    @api.onchange('tipo_servidor_email')
    def _onchange_tipo_servidor_email(self):
        if self.tipo_servidor_email == 'proveedor':
            self.servidor_email_propio = False

    @api.onchange('estado')
    def _onchange_estado(self):
        if self.estado in ['requiere_cambios', 'rechazado']:
            self.puede_reenviar = True
        else:
            self.puede_reenviar = False

    @api.onchange('control_impresion')
    def _onchange_control_impresion(self):
        if not self.control_impresion:
            self.tipo_control = False
            self.cantidad_usuarios = 0
            self.requiere_reportes = False
            self.frecuencia_reportes = False

    def action_view_alquiler(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Alquiler',
            'res_model': 'alquiler',
            'res_id': self.alquiler_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.constrains('cantidad_windows', 'cantidad_mac', 'cantidad_linux')
    def _check_total_pcs(self):
        for rec in self:
            total_pcs = rec.cantidad_windows + rec.cantidad_mac + rec.cantidad_linux
            if total_pcs <= 0:
                raise ValidationError(
                    "Debe haber al menos una computadora conectada (Windows, Mac o Linux).")

    def _update_estado(self):
        for record in self:
            problemas = []
            if record.punto_corriente == 'no':
                problemas.append("No tiene punto de corriente.")
            elif record.punto_corriente == 'pendiente':
                problemas.append("Requiere instalación de punto de corriente.")

            if record.punto_red == 'no' and record.wifi == 'no':
                problemas.append("No tiene conexión a red ni WiFi.")
            elif record.punto_red == 'pendiente':
                problemas.append("Requiere instalación de punto de red.")

            if record.espacio < 2.0 or record.ancho_pasillo < 1.0:
                problemas.append(
                    "Espacio insuficiente: mínimo 2m² y pasillo de 1m de ancho.")

            total_pcs = record.cantidad_windows + record.cantidad_mac + record.cantidad_linux
            if total_pcs <= 0:
                problemas.append("No hay computadoras conectadas.")

            nuevo_estado = 'aprobado' if not problemas else 'rechazado' if any(
                "Requiere" in p or "No tiene" in p for p in problemas) else 'requiere_cambios'
            nuevo_requisitos = '\n'.join(problemas) if problemas else False

            self.env.cr.execute("""
                UPDATE inspeccion_resultado 
                SET estado = %s, requisitos_pendientes = %s 
                WHERE id = %s
            """, (nuevo_estado, nuevo_requisitos, record.id))

    @api.onchange('punto_corriente', 'punto_red', 'wifi', 'espacio', 'ancho_pasillo', 'cantidad_windows', 'cantidad_mac', 'cantidad_linux')
    def _onchange_estado(self):
        self._update_estado()

# -*- coding: utf-8 -*-
from odoo import models, fields, api


class MdmCommandLog(models.Model):
    _name = 'mdm.command.log'
    _description = 'Historial de Comandos MDM'
    _rec_name = 'message_type'
    _order = 'create_date desc'

    device_id = fields.Many2one(
        'mdm.device', string='Dispositivo',
        required=True, ondelete='cascade', index=True
    )
    device_number = fields.Char(
        related='device_id.device_number',
        string='Número dispositivo', store=True
    )
    user_id = fields.Many2one(
        'res.users', string='Enviado por',
        default=lambda self: self.env.uid
    )
    message_type = fields.Selection([
        ('configUpdated', 'Actualizar configuración'),
        ('runApp', 'Abrir aplicación'),
        ('uninstallApp', 'Desinstalar aplicación'),
        ('deleteFile', 'Eliminar archivo'),
        ('deleteDir', 'Eliminar directorio'),
        ('purgeDir', 'Vaciar directorio'),
        ('permissiveMode', 'Modo permisivo'),
        ('runCommand', 'Ejecutar comando'),
        ('reboot', 'Reiniciar dispositivo'),
        ('exitKiosk', 'Salir de kiosk'),
        ('clearDownloadHistory', 'Limpiar historial de descargas'),
        ('custom', 'Personalizado'),
    ], string='Tipo de comando', required=True)
    payload = fields.Text(string='Payload enviado')
    status = fields.Selection([
        ('sent', 'Enviado'),
        ('error', 'Error'),
    ], string='Estado', default='sent')
    error_message = fields.Text(string='Mensaje de error')
    create_date = fields.Datetime(string='Fecha', readonly=True)
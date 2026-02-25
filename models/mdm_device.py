# -*- coding: utf-8 -*-
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

PUSH_TYPES = [
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
]

APP_SHORTCUTS = [
    ('org.traccar.client', 'Traccar'),
    ('com.whatsapp', 'WhatsApp'),
    ('com.waze', 'Waze'),
    ('com.google.android.apps.maps', 'Google Maps'),
    ('com.hmdm.launcher', 'Agente MDM'),
    ('com.android.settings', 'Configuración'),
    ('custom', 'Otro (manual)'),
]


class MdmDevice(models.Model):
    _name = 'mdm.device'
    _description = 'Dispositivo Headwind MDM'
    _rec_name = 'device_number'
    _order = 'status_code asc, device_number asc'

    # ── Relaciones ──────────────────────────────────────────────
    config_id = fields.Many2one(
        'mdm.config', string='Servidor MDM',
        required=True, ondelete='cascade'
    )
    user_id = fields.Many2one(
        'res.users', string='Técnico asignado',
        help='Usuario de Odoo vinculado a este dispositivo'
    )

    # ── Datos del dispositivo ────────────────────────────────────
    device_number = fields.Char(string='Número de dispositivo', required=True, index=True)
    device_id_mdm = fields.Integer(string='ID MDM')
    status_code = fields.Selection([
        ('green', 'En línea'),
        ('yellow', 'Advertencia'),
        ('red', 'Error'),
        ('grey', 'Desconectado'),
    ], string='Estado', default='grey')
    model = fields.Char(string='Modelo')
    android_version = fields.Char(string='Android')
    imei = fields.Char(string='IMEI')
    phone = fields.Char(string='Teléfono')
    battery_level = fields.Integer(string='Batería (%)')
    launcher_version = fields.Char(string='Versión agente')
    last_update = fields.Datetime(string='Última actualización')
    mdm_mode = fields.Boolean(string='Modo MDM')
    kiosk_mode = fields.Boolean(string='Modo Kiosk')

    # ── Campos para envío de push ────────────────────────────────
    push_type = fields.Selection(
        PUSH_TYPES,
        string='Tipo de comando',
        default='configUpdated'
    )
    push_app_shortcut = fields.Selection(
        APP_SHORTCUTS,
        string='Aplicación',
        default='org.traccar.client'
    )
    push_app_custom = fields.Char(string='Package personalizado')
    push_payload = fields.Text(string='Payload (JSON)')

    # ── Historial ────────────────────────────────────────────────
    command_log_ids = fields.One2many(
        'mdm.command.log', 'device_id',
        string='Historial de comandos'
    )
    command_count = fields.Integer(
        string='Comandos enviados',
        compute='_compute_command_count'
    )

    # ── Compute ──────────────────────────────────────────────────
    def _compute_command_count(self):
        for rec in self:
            rec.command_count = self.env['mdm.command.log'].search_count(
                [('device_id', '=', rec.id)]
            )

    @api.depends('status_code')
    def _compute_status_icon(self):
        pass

    # ── Onchange para payload automático ────────────────────────
    @api.onchange('push_type', 'push_app_shortcut', 'push_app_custom')
    def _onchange_push_type(self):
        pkg = self.push_app_custom if self.push_app_shortcut == 'custom' \
            else self.push_app_shortcut

        payloads = {
            'configUpdated': '',
            'runApp': f'{{"pkg":"{pkg}"}}' if pkg else '{"pkg":"org.traccar.client"}',
            'uninstallApp': f'{{"pkg":"{pkg}"}}' if pkg else '{"pkg":""}',
            'deleteFile': '{"path":"/sdcard/archivo.txt"}',
            'deleteDir': '{"path":"/sdcard/carpeta"}',
            'purgeDir': '{"path":"/sdcard/carpeta"}',
            'permissiveMode': '',
            'runCommand': '{"command":""}',
            'reboot': '',
            'exitKiosk': '',
            'clearDownloadHistory': '',
            'custom': '',
        }
        self.push_payload = payloads.get(self.push_type, '')

    # ── Acciones de envío ────────────────────────────────────────
    def action_send_push(self):
        """Envía el comando push al dispositivo"""
        self.ensure_one()
        self._send_push(
            message_type=self.push_type,
            payload=self.push_payload or '',
            broadcast=False,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Comando enviado',
                'message': f'Comando "{self.push_type}" enviado a {self.device_number}.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_send_push_traccar(self):
        """Atajo rápido: abrir Traccar"""
        for rec in self:
            rec._send_push('runApp', '{"pkg":"org.traccar.client"}')
        return self._notify_ok(f'Traccar abierto en {len(self)} dispositivo(s)')

    def action_send_push_config_updated(self):
        """Atajo rápido: actualizar configuración"""
        for rec in self:
            rec._send_push('configUpdated', '')
        return self._notify_ok(f'Configuración actualizada en {len(self)} dispositivo(s)')

    def action_send_push_reboot(self):
        """Atajo rápido: reiniciar dispositivo"""
        for rec in self:
            rec._send_push('reboot', '')
        return self._notify_ok(f'Reinicio enviado a {len(self)} dispositivo(s)')

    def action_send_push_whatsapp(self):
        """Atajo rápido: abrir WhatsApp"""
        for rec in self:
            rec._send_push('runApp', '{"pkg":"com.whatsapp"}')
        return self._notify_ok(f'WhatsApp abierto en {len(self)} dispositivo(s)')

    def action_send_push_exit_kiosk(self):
        """Atajo rápido: salir de kiosk"""
        for rec in self:
            rec._send_push('exitKiosk', '')
        return self._notify_ok(f'Salida de kiosk enviada a {len(self)} dispositivo(s)')

    # ── Método central de envío ──────────────────────────────────
    def _send_push(self, message_type, payload, broadcast=False):
        self.ensure_one()
        config = self.config_id
        headers = config._get_headers()
        url = f"{config.url}/rest/private/push"

        body = {
            'messageType': message_type,
            'payload': payload,
            'broadcast': broadcast,
            'deviceNumbers': [self.device_number],
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            status = 'sent' if result.get('status') == 'OK' else 'error'
            error_msg = '' if status == 'sent' else str(result)
        except Exception as e:
            status = 'error'
            error_msg = str(e)
            _logger.error(f'MDM Push error: {e}')

        # Registrar en historial
        self.env['mdm.command.log'].create({
            'device_id': self.id,
            'user_id': self.env.uid,
            'message_type': message_type,
            'payload': payload,
            'status': status,
            'error_message': error_msg,
        })

        if status == 'error':
            raise UserError(f'Error al enviar comando: {error_msg}')

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Historial - {self.device_number}',
            'res_model': 'mdm.command.log',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
        }

    def _notify_ok(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Listo',
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
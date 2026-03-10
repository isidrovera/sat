# -*- coding: utf-8 -*-
import hashlib
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class MdmConfig(models.Model):
    _name = 'mdm.config'
    _description = 'Configuración Headwind MDM'
    _rec_name = 'url'

    url = fields.Char(
        string='URL del servidor',
        required=True,
        default='https://it.andessolutioncopiers.com',
        help='URL base del servidor Headwind MDM'
    )
    login = fields.Char(string='Usuario', required=True, default='admin')
    password = fields.Char(string='Contraseña', required=True)
    active = fields.Boolean(string='Activo', default=True)
    jwt_token = fields.Char(string='JWT Token', readonly=True)
    token_expiry = fields.Datetime(string='Expiración Token', readonly=True)
    last_sync = fields.Datetime(string='Última sincronización', readonly=True)
    device_count = fields.Integer(
        string='Dispositivos',
        compute='_compute_device_count'
    )

    def _compute_device_count(self):
        for rec in self:
            rec.device_count = self.env['mdm.device'].search_count(
                [('config_id', '=', rec.id)]
            )

    def _get_password_md5(self):
        return hashlib.md5(self.password.encode()).hexdigest().upper()

    def action_test_connection(self):
        self.ensure_one()
        try:
            token = self._get_jwt_token()
            if token:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Conexión exitosa',
                        'message': 'Conectado a Headwind MDM correctamente.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
        except Exception as e:
            raise UserError(f'Error de conexión: {str(e)}')

    def _get_jwt_token(self):
        self.ensure_one()
        import datetime

        now = fields.Datetime.now()

        if self.jwt_token and self.token_expiry and self.token_expiry > now:
            return self.jwt_token

        # Paso 1: login
        login_url = f"{self.url}/rest/public/auth/login"
        resp = requests.post(login_url, json={
            'login': self.login,
            'password': self._get_password_md5()
        }, timeout=10)

        resp.raise_for_status()
        data = resp.json()

        if data.get('status') != 'OK':
            raise UserError('Login fallido en Headwind MDM')

        auth_token = data.get('data', {}).get('authToken')

        # Paso 2: obtener JWT
        jwt_url = f"{self.url}/rest/public/jwt/login"
        resp2 = requests.post(jwt_url, json={
            'authToken': auth_token
        }, timeout=10)

        resp2.raise_for_status()
        token = resp2.json().get('id_token')

        if not token:
            raise UserError('No se obtuvo JWT token')

        expiry = now + datetime.timedelta(hours=23)

        self.sudo().write({
            'jwt_token': token,
            'token_expiry': expiry,
        })

        return token

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self._get_jwt_token()}",
            "Content-Type": "application/json"
        }

    def action_sync_devices(self):
        self.ensure_one()
        headers = self._get_headers()
        url = f"{self.url}/rest/private/devices/search"
        resp = requests.post(url, headers=headers, json={
            'pageNum': 1,
            'pageSize': 200
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get('status') != 'OK':
            raise UserError('Error al obtener dispositivos')

        devices = data['data']['devices']['items']
        MdmDevice = self.env['mdm.device']
        synced = 0

        for dev in devices:
            info = dev.get('info') or {}
            existing = MdmDevice.search([
                ('device_number', '=', dev['number']),
                ('config_id', '=', self.id)
            ], limit=1)

            vals = {
                'config_id': self.id,
                'device_number': dev['number'],
                'device_id_mdm': dev.get('id'),
                'status_code': dev.get('statusCode', 'grey'),
                'model': info.get('model', ''),
                'android_version': info.get('androidVersion', ''),
                'imei': info.get('imei', ''),
                'phone': info.get('phone', ''),
                'battery_level': info.get('batteryLevel', 0),
                'launcher_version': dev.get('launcherVersion', ''),
                'last_update': fields.Datetime.now(),
                'mdm_mode': info.get('mdmMode', False),
                'kiosk_mode': info.get('kioskMode', False),
            }

            if existing:
                existing.write(vals)
            else:
                MdmDevice.create(vals)
            synced += 1

        self.sudo().write({'last_sync': fields.Datetime.now()})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Sincronización completada',
                'message': f'{synced} dispositivos sincronizados.',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def cron_sync_all_devices(self):
        """
        Ejecutar cada 10 minutos.
        Sincroniza estado, batería y conexión de todos los dispositivos
        de todas las configuraciones MDM activas.
        """
        configs = self.sudo().search([('active', '=', True)])
        if not configs:
            _logger.info("[MDM-CRON] Sin configuraciones activas")
            return

        _logger.info("[MDM-CRON] Sincronizando %d configuración(es)", len(configs))

        for config in configs:
            try:
                config._sync_devices_silencioso()
                _logger.info("[MDM-CRON] ✅ Config %s sincronizada", config.url)
            except Exception as e:
                _logger.error("[MDM-CRON] ❌ Error sincronizando %s: %s", config.url, e)

    def _sync_devices_silencioso(self):
        """
        Igual que action_sync_devices pero sin retornar notificación UI.
        Para uso desde cron.
        """
        self.ensure_one()
        headers = self._get_headers()
        url = f"{self.url}/rest/private/devices/search"

        resp = requests.post(url, headers=headers, json={
            'pageNum': 1,
            'pageSize': 200,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get('status') != 'OK':
            raise Exception(f'API respondió: {data.get("status")}')

        devices = data['data']['devices']['items']
        MdmDevice = self.env['mdm.device']
        synced = 0
        ahora = fields.Datetime.now()

        for dev in devices:
            info = dev.get('info') or {}
            existing = MdmDevice.search([
                ('device_number', '=', dev['number']),
                ('config_id', '=', self.id),
            ], limit=1)

            vals = {
                'config_id': self.id,
                'device_number': dev['number'],
                'device_id_mdm': dev.get('id'),
                'status_code': dev.get('statusCode', 'grey'),
                'model': info.get('model', ''),
                'android_version': info.get('androidVersion', ''),
                'imei': info.get('imei', ''),
                'phone': info.get('phone', ''),
                'battery_level': info.get('batteryLevel', 0),
                'launcher_version': dev.get('launcherVersion', ''),
                'last_update': ahora,
                'mdm_mode': info.get('mdmMode', False),
                'kiosk_mode': info.get('kioskMode', False),
            }

            if existing:
                existing.write(vals)
            else:
                MdmDevice.create(vals)
            synced += 1

        self.sudo().write({'last_sync': ahora})
        _logger.info("[MDM-CRON] %d dispositivos actualizados en %s", synced, self.url)

    def action_view_devices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Dispositivos MDM',
            'res_model': 'mdm.device',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
        }
# -*- coding: utf-8 -*-
import hashlib
import datetime
import requests
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MdmConfig(models.Model):
    _name = 'mdm.config'
    _description = 'Configuración Headwind MDM'
    _rec_name = 'url'

    url = fields.Char(
        string='URL del servidor',
        required=True,
        default='https://it.andessolutioncopiers.com'
    )

    login = fields.Char(
        string='Usuario',
        required=True,
        default='admin'
    )

    password = fields.Char(
        string='Contraseña',
        required=True
    )

    active = fields.Boolean(
        string='Activo',
        default=True
    )

    jwt_token = fields.Char(
        string='JWT Token',
        readonly=True
    )

    token_expiry = fields.Datetime(
        string='Expiración Token',
        readonly=True
    )

    last_sync = fields.Datetime(
        string='Última sincronización',
        readonly=True
    )

    device_count = fields.Integer(
        string='Dispositivos',
        compute='_compute_device_count'
    )

    # ---------------------------------------------------------
    # COMPUTE
    # ---------------------------------------------------------

    def _compute_device_count(self):
        for rec in self:
            rec.device_count = self.env['mdm.device'].search_count([
                ('config_id', '=', rec.id)
            ])

   

    # ---------------------------------------------------------
    # TEST CONEXION
    # ---------------------------------------------------------

    def action_test_connection(self):
        self.ensure_one()

        _logger.info("[MDM] Probando conexión con servidor %s", self.url)

        try:
            token = self._get_jwt_token()

            if token:
                _logger.info("[MDM] Conexión exitosa. JWT recibido")

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
            _logger.error("[MDM] Error conexión: %s", e)
            raise UserError(f'Error de conexión: {str(e)}')

    # ---------------------------------------------------------
    # OBTENER JWT TOKEN
    # ---------------------------------------------------------

    def _get_password_md5(self):
        md5 = hashlib.md5(self.password.encode()).hexdigest().upper()
        _logger.info("[MDM] Password MD5 generado: %s", md5)
        return md5

    def _get_jwt_token(self):

        login_url = f"{self.url}/rest/public/auth/login"

        payload = {
            "login": self.login,
            "password": self._get_password_md5()
        }

        resp = requests.post(
            login_url,
            json=payload,
            timeout=10
        )

        resp.raise_for_status()

        data = resp.json()

        if data.get("status") != "OK":
            raise UserError(f"Login fallido: {data}")

        token = data["data"]["authToken"]

        _logger.info("[MDM] Nuevo authToken obtenido: %s", token)

        return token


    def _get_headers(self):

        token = self._get_jwt_token()

        headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": self.url,
            "Referer": f"{self.url}/"
        }

        _logger.info("[MDM] Headers generados: %s", headers)

        return headers

    # ---------------------------------------------------------
    # SINCRONIZAR DISPOSITIVOS
    # ---------------------------------------------------------

    def action_sync_devices(self):

        self.ensure_one()

        _logger.info("[MDM] Iniciando sincronización manual")

        headers = self._get_headers()

        url = f"{self.url}/rest/private/devices/search"

        _logger.info("[MDM] Endpoint: %s", url)

        payload = {
            "pageNum": 1,
            "pageSize": 200
        }

        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )
        _logger.info("[MDM] Status API: %s", resp.status_code)
        _logger.debug("[MDM] Respuesta API: %s", resp.text)

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
                _logger.info("[MDM] Dispositivo actualizado: %s", dev['number'])
            else:
                MdmDevice.create(vals)
                _logger.info("[MDM] Dispositivo creado: %s", dev['number'])

            synced += 1

        self.sudo().write({
            'last_sync': fields.Datetime.now()
        })

        _logger.info("[MDM] Sincronización completada (%s dispositivos)", synced)

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

    # ---------------------------------------------------------
    # CRON SINCRONIZACION
    # ---------------------------------------------------------

    @api.model
    def cron_sync_all_devices(self):

        configs = self.sudo().search([
            ('active', '=', True)
        ])

        _logger.info("[MDM-CRON] Configuraciones activas: %s", len(configs))

        for config in configs:
            try:
                config._sync_devices_silencioso()
            except Exception as e:
                _logger.error("[MDM-CRON] Error: %s", e)

    # ---------------------------------------------------------
    # SYNC SILENCIOSO
    # ---------------------------------------------------------

    def _sync_devices_silencioso(self):

        self.ensure_one()

        _logger.info("[MDM-CRON] Sincronizando %s", self.url)

        headers = self._get_headers()

        url = f"{self.url}/rest/private/devices/search"

        resp = requests.get(
            f"{url}?pageNum=1&pageSize=200",
            headers=headers,
            timeout=15
        )

        resp.raise_for_status()

        data = resp.json()

        if data.get('status') != 'OK':
            raise Exception("API error")

        devices = data['data']['devices']['items']

        MdmDevice = self.env['mdm.device']

        now = fields.Datetime.now()

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
                'battery_level': info.get('batteryLevel', 0),
                'last_update': now,
            }

            if existing:
                existing.write(vals)
            else:
                MdmDevice.create(vals)

        self.sudo().write({'last_sync': now})

        _logger.info("[MDM-CRON] Sync finalizado")

    # ---------------------------------------------------------
    # VER DISPOSITIVOS
    # ---------------------------------------------------------

    def action_view_devices(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Dispositivos MDM',
            'res_model': 'mdm.device',
            'view_mode': 'list,form',
            'domain': [('config_id', '=', self.id)],
        }
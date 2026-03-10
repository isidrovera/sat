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
    # UTILIDADES
    # ---------------------------------------------------------

    def _get_password_md5(self):
        # SIN .upper() — Headwind MDM espera minúsculas
        md5 = hashlib.md5(self.password.encode()).hexdigest()
        _logger.info("[MDM] Password MD5 generado")
        return md5

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

    def _get_jwt_token(self):
        self.ensure_one()

        now = fields.Datetime.now()

        if self.jwt_token and self.token_expiry and self.token_expiry > now:
            _logger.info("[MDM] Reutilizando JWT existente")
            return self.jwt_token

        _logger.info("[MDM] Solicitando nuevo JWT")

        # Paso 1: Login
        login_url = f"{self.url}/rest/public/auth/login"

        payload = {
            'login': self.login,
            'password': self._get_password_md5()
        }

        _logger.info("[MDM] Login URL: %s", login_url)

        resp = requests.post(
            login_url,
            json=payload,
            timeout=10
        )

        _logger.info("[MDM] Login status: %s", resp.status_code)
        _logger.info("[MDM] Login response raw: %s", resp.text)  # VER RESPUESTA REAL

        resp.raise_for_status()

        data = resp.json()

        _logger.info("[MDM] Login response parsed: %s", data)  # VER ESTRUCTURA JSON

        # Intentar extraer authToken con múltiples estructuras posibles
        auth_token = (
            data.get('authToken')                        # estructura plana
            or data.get('data', {}).get('authToken')     # estructura anidada en 'data'
            or data.get('token')                         # campo alternativo
            or data.get('data', {}).get('token')         # anidado alternativo
        )

        _logger.info("[MDM] AuthToken extraído: %s", bool(auth_token))

        if not auth_token:
            _logger.error("[MDM] No se encontró authToken en: %s", data)
            raise UserError(f'No se recibió authToken. Respuesta: {data}')

        _logger.info("[MDM] AuthToken recibido OK")

        # Paso 2: Obtener JWT
        jwt_url = f"{self.url}/rest/public/jwt/login"

        _logger.info("[MDM] Solicitando JWT en: %s", jwt_url)

        resp2 = requests.post(
            jwt_url,
            json={'authToken': auth_token},
            timeout=10
        )

        _logger.info("[MDM] JWT status: %s", resp2.status_code)
        _logger.info("[MDM] JWT response raw: %s", resp2.text)  # VER RESPUESTA REAL

        resp2.raise_for_status()

        data2 = resp2.json()

        _logger.info("[MDM] JWT response parsed: %s", data2)  # VER ESTRUCTURA JSON

        # Intentar extraer token con múltiples estructuras posibles
        token = (
            data2.get('id_token')                    # estructura típica JWT
            or data2.get('token')                    # alternativo
            or data2.get('data', {}).get('token')    # anidado
            or data2.get('jwtToken')                 # otro posible nombre
        )

        if not token:
            _logger.error("[MDM] No se encontró JWT en: %s", data2)
            raise UserError(f'No se obtuvo JWT token. Respuesta: {data2}')

        expiry = now + datetime.timedelta(hours=23)

        self.sudo().write({
            'jwt_token': token,
            'token_expiry': expiry
        })

        _logger.info("[MDM] JWT guardado correctamente")

        return token
    # ---------------------------------------------------------
    # HEADERS API
    # ---------------------------------------------------------

    def _get_headers(self):

        token = self._get_jwt_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        _logger.debug("[MDM] Headers generados")

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

        resp = requests.get(
            f"{url}?pageNum=1&pageSize=200",
            headers=headers,
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
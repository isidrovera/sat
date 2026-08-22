# -*- coding: utf-8 -*-

import logging

from odoo import http, _
from odoo.http import request

from .common import MonitoringApiMixin, MonitoringApiError


_logger = logging.getLogger(__name__)


class MonitoringDeviceController(http.Controller, MonitoringApiMixin):

    @http.route(
        '/api/monitoring/agent/devices',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def list_devices(self, **kwargs):
        try:
            agent = self._authenticate_agent()

            domain = [
                ('agent_id', '=', agent.id),
                ('active', '=', True),
            ]

            network_id = request.httprequest.args.get('network_id')
            if network_id:
                network = self._get_agent_network(agent, network_id)
                domain.append(('network_id', '=', network.id))

            devices = request.env['sat.monitoring.device'].sudo().search(
                domain,
                order='network_id, ip_address, id',
            )

            return self._ok({
                'count': len(devices),
                'devices': [device.get_device_summary() for device in devices],
            })

        except Exception as error:
            return self._handle_api_exception(error, endpoint='device_list')

    @http.route(
        '/api/monitoring/agent/device/<int:device_id>/config',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def device_configuration(self, device_id, **kwargs):
        try:
            agent = self._authenticate_agent()
            device = self._get_agent_device(agent, device_id)

            return self._ok(device.get_agent_configuration())

        except Exception as error:
            return self._handle_api_exception(error, endpoint='device_config')

    @http.route(
        '/api/monitoring/agent/profile/match',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def match_profile(self, **kwargs):
        """
        Permite al agente consultar qué perfil corresponde a un equipo antes
        de crear o actualizar el registro permanente.
        """
        try:
            self._authenticate_agent()
            payload = self._read_json(required=True)

            result = request.env['sat.snmp.profile'].sudo().find_best_profile(
                brand_code=self._clean_text(payload.get('brand_code')),
                manufacturer=self._clean_text(payload.get('manufacturer')),
                model=self._clean_text(payload.get('model')),
                sysdescr=self._clean_text(payload.get('sysdescr')),
                enterprise_id=self._clean_text(payload.get('enterprise_id')),
                firmware=self._clean_text(payload.get('firmware')),
                technology=self._clean_text(payload.get('technology')) or None,
                include_testing=bool(payload.get('include_testing', True)),
            )

            profile = result.get('profile')
            match = result.get('match')

            if not profile:
                return self._ok({
                    'matched': False,
                    'evaluated_count': result.get('evaluated_count', 0),
                })

            return self._ok({
                'matched': True,
                'profile': profile.get_profile_summary(),
                'match': match,
                'evaluated_count': result.get('evaluated_count', 0),
            })

        except Exception as error:
            return self._handle_api_exception(error, endpoint='profile_match')

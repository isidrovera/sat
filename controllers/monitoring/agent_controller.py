# -*- coding: utf-8 -*-

import logging

from odoo import http, fields, _
from odoo.http import request

from .common import MonitoringApiMixin, MonitoringApiError


_logger = logging.getLogger(__name__)


class MonitoringAgentController(http.Controller, MonitoringApiMixin):

    @http.route(
        '/api/monitoring/agent/heartbeat',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def heartbeat(self, **kwargs):
        try:
            agent = self._authenticate_agent()
            payload = self._read_json(required=False)

            result = agent.register_heartbeat(payload)

            return self._ok(result)

        except Exception as error:
            return self._handle_api_exception(error, endpoint='heartbeat')

    @http.route(
        '/api/monitoring/agent/status',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def status(self, **kwargs):
        try:
            agent = self._authenticate_agent()

            return self._ok({
                'id': agent.id,
                'code': agent.code,
                'name': agent.name,
                'enabled': agent.enabled,
                'online': agent.online,
                'state': agent.state,
                'config_revision': agent.config_revision,
                'last_config_sync_revision': agent.last_config_sync_revision,
                'needs_config_sync': agent.needs_config_sync,
                'server_time': fields.Datetime.to_string(fields.Datetime.now()),
            })

        except Exception as error:
            return self._handle_api_exception(error, endpoint='agent_status')

    @http.route(
        '/api/monitoring/agent/config',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def configuration(self, **kwargs):
        try:
            agent = self._authenticate_agent()

            payload = agent.get_agent_configuration()

            return self._ok(payload)

        except Exception as error:
            return self._handle_api_exception(error, endpoint='agent_config')

    @http.route(
        '/api/monitoring/agent/config/ack',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def acknowledge_configuration(self, **kwargs):
        try:
            agent = self._authenticate_agent()
            payload = self._read_json(required=False)

            revision = payload.get('revision', agent.config_revision)
            revision = self._safe_int(revision, agent.config_revision, minimum=0)

            if revision > agent.config_revision:
                raise MonitoringApiError(
                    _('El agente no puede confirmar una revisión futura.'),
                    status=400,
                    code='invalid_config_revision',
                )

            agent.mark_config_synced(revision=revision)

            return self._ok({
                'revision': revision,
                'needs_config_sync': agent.needs_config_sync,
            })

        except Exception as error:
            return self._handle_api_exception(error, endpoint='config_ack')

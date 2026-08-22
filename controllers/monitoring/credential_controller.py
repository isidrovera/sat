# -*- coding: utf-8 -*-

import logging

from odoo import http

from .common import MonitoringApiMixin


_logger = logging.getLogger(__name__)


class MonitoringCredentialController(http.Controller, MonitoringApiMixin):

    @http.route(
        '/api/monitoring/agent/credential/<int:credential_id>',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        save_session=False,
    )
    def get_credential(self, credential_id, **kwargs):
        """
        Devuelve el secreto únicamente a un agente autenticado y autorizado.
        Nunca debe utilizarse desde una vista web pública.
        """
        try:
            agent = self._authenticate_agent()
            credential = self._get_agent_credential(agent, credential_id)

            payload = credential.get_agent_secret_payload(agent)

            return self._ok(payload)

        except Exception as error:
            return self._handle_api_exception(error, endpoint='credential')

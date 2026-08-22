# -*- coding: utf-8 -*-

import logging

from odoo import http, _

from .common import MonitoringApiMixin, MonitoringApiError


_logger = logging.getLogger(__name__)


class MonitoringPollController(http.Controller, MonitoringApiMixin):

    def _normalize_poll_state(self, payload):
        state = self._clean_text(payload.get('state')).lower()
        if state in ('success', 'partial', 'failed', 'timeout', 'offline'):
            return state

        if payload.get('success') is False:
            return 'failed'

        return 'success'

    @http.route(
        '/api/monitoring/agent/poll',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def poll(self, **kwargs):
        """
        Recibe una lectura completa del equipo.

        Payload esperado:
        {
            "device_id": 25,
            "state": "success|partial|failed|timeout|offline",
            "duration_ms": 900,
            "response_ms": 40,
            "snmp_version": "2c",
            "identity": {...},
            "readings": [...],
            "alerts": [...],
            "alerts_complete": true,
            "statistics": {...},
            "summary": "...",
            "raw": {...}
        }
        """
        try:
            agent = self._authenticate_agent()
            payload = self._read_json(required=True)

            device = self._get_agent_device(agent, payload.get('device_id'))

            if not device.monitoring_enabled and not device.inventory_enabled:
                raise MonitoringApiError(
                    _('El monitoreo está deshabilitado para este equipo.'),
                    status=403,
                    code='device_monitoring_disabled',
                )

            if device.network_id and device.network_id.agent_id != agent:
                raise MonitoringApiError(
                    _('La red del equipo no corresponde al agente.'),
                    status=403,
                    code='device_network_mismatch',
                )

            snapshot = self._create_snapshot(device, agent, payload)

            state = self._normalize_poll_state(payload)
            identity = payload.get('identity') or {}
            readings_payload = payload.get('readings') or []
            alerts_payload = payload.get('alerts') or []

            if not isinstance(identity, dict):
                raise MonitoringApiError(
                    _('identity debe ser un objeto.'),
                    code='invalid_identity',
                )
            if not isinstance(readings_payload, list):
                raise MonitoringApiError(
                    _('readings debe ser una lista.'),
                    code='invalid_readings',
                )
            if not isinstance(alerts_payload, list):
                raise MonitoringApiError(
                    _('alerts debe ser una lista.'),
                    code='invalid_alerts',
                )

            # Identidad observada en este ciclo.
            if identity:
                snapshot.apply_identity(identity)
                device.apply_identity_payload(identity)

            created_readings = snapshot.env['sat.monitoring.reading'].browse()
            if readings_payload:
                created_readings = snapshot.process_readings(readings_payload)

            if device.alert_monitoring_enabled:
                snapshot.process_alerts(
                    alerts_payload,
                    complete_list=bool(payload.get('alerts_complete', True)),
                )

            # Estado rápido opcional enviado por agente.
            device_status = self._clean_text(payload.get('device_status')).lower()
            if device_status:
                device.apply_status(status=device_status)

            # Recalcular siempre desde las lecturas realmente guardadas. De este
            # modo no confiamos ciegamente en estadísticas enviadas por el agente.
            snapshot.recalculate_statistics()

            # Si faltó una métrica obligatoria, una respuesta declarada success
            # se convierte en partial.
            if state == 'success' and snapshot.missing_required_metric_count > 0:
                state = 'partial'

            common_finish = {
                'duration_ms': payload.get('duration_ms'),
                'response_ms': payload.get('response_ms'),
                'statistics': payload.get('statistics') or {},
                'raw_payload': payload.get('raw'),
                'agent_payload': payload,
                'summary': payload.get('summary'),
            }

            if state == 'success':
                snapshot.finish_success(
                    **common_finish,
                    snmp_version=payload.get('snmp_version'),
                )

            elif state == 'partial':
                snapshot.finish_partial(
                    warning_message=(
                        payload.get('warning_message')
                        or payload.get('error_message')
                        or 'partial_poll'
                    ),
                    **common_finish,
                    snmp_version=payload.get('snmp_version'),
                )

            else:
                # En fallos completos no pasamos statistics porque el método del
                # modelo no las utiliza. Las lecturas ya creadas siguen asociadas
                # al snapshot si el agente alcanzó a obtener datos parciales.
                snapshot.finish_failure(
                    state=state,
                    error_code=payload.get('error_code'),
                    error_message=payload.get('error_message'),
                    duration_ms=payload.get('duration_ms'),
                    response_ms=payload.get('response_ms'),
                    raw_payload=payload.get('raw'),
                    agent_payload=payload,
                )

            # Los métodos finish_* registran tiempos/estado y pueden usar
            # estadísticas auxiliares del agente. Volvemos a calcular las
            # estadísticas de métricas desde la base para que el resultado
            # definitivo siempre refleje las lecturas realmente guardadas.
            snapshot.recalculate_statistics()

            # Detectar señales de incompatibilidad de perfil.
            if payload.get('profile_mismatch'):
                snapshot.mark_profile_mismatch(
                    reason=payload.get('profile_mismatch_reason') or 'agent_reported_mismatch'
                )

            return self._ok({
                'snapshot_id': snapshot.id,
                'device_id': device.id,
                'state': snapshot.state,
                'readings_saved': len(created_readings),
                'alerts_active': device.active_alert_count,
                'missing_required_metrics': snapshot.missing_required_metric_count,
                'profile_mismatch': snapshot.profile_mismatch,
            }, status=201)

        except Exception as error:
            return self._handle_api_exception(error, endpoint='poll')

    def _create_snapshot(self, device, agent, payload):
        agent_info = payload.get('agent') or {}
        if not isinstance(agent_info, dict):
            agent_info = {}

        if not agent_info.get('identifier'):
            agent_info['identifier'] = agent.code
        if not agent_info.get('version'):
            agent_info['version'] = agent.agent_version or ''
        if not agent_info.get('hostname'):
            agent_info['hostname'] = agent.hostname or ''

        return device.env['sat.monitoring.snapshot'].sudo().create_for_device(
            device=device,
            started_at=payload.get('started_at'),
            agent_info=agent_info,
        )

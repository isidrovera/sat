# -*- coding: utf-8 -*-

import logging

from datetime import (
    datetime,
    timezone,
)

from odoo import (
    http,
    fields,
    _,
)

from .common import (
    MonitoringApiMixin,
    MonitoringApiError,
)


_logger = logging.getLogger(__name__)


class MonitoringPollController(
    http.Controller,
    MonitoringApiMixin,
):

    # =========================================================
    # ESTADO DEL POLLING
    # =========================================================

    def _normalize_poll_state(
        self,
        payload,
    ):
        state = self._clean_text(
            payload.get('state')
        ).lower()

        if state in (
            'success',
            'partial',
            'failed',
            'timeout',
            'offline',
        ):
            return state

        if payload.get(
            'success'
        ) is False:
            return 'failed'

        return 'success'

    # =========================================================
    # NORMALIZAR DATETIME RECIBIDO DEL AGENTE
    # =========================================================

    def _normalize_datetime(
        self,
        value,
    ):
        """
        Convierte fechas enviadas por el agente a un datetime
        compatible con Odoo.

        Ejemplos aceptados:

            2026-08-24T22:51:49.785671+00:00
            2026-08-24T22:51:49+00:00
            2026-08-24T22:51:49Z
            2026-08-24 22:51:49
        """

        if not value:
            return False

        # Ya es datetime
        if isinstance(
            value,
            datetime,
        ):
            parsed = value

        else:

            text = self._clean_text(
                value
            )

            if not text:
                return False

            # -------------------------------------------------
            # Formato ISO UTC terminado en Z
            # -------------------------------------------------

            if text.endswith(
                'Z'
            ):
                text = (
                    text[:-1]
                    + '+00:00'
                )

            # -------------------------------------------------
            # Intentar ISO 8601
            # -------------------------------------------------

            try:

                parsed = (
                    datetime.fromisoformat(
                        text
                    )
                )

            except (
                ValueError,
                TypeError,
            ):

                # ---------------------------------------------
                # Intentar formato clásico de Odoo
                # ---------------------------------------------

                try:

                    parsed = (
                        fields.Datetime.to_datetime(
                            text
                        )
                    )

                except Exception as exc:

                    raise MonitoringApiError(
                        _(
                            'Formato de fecha inválido: %s'
                        )
                        % value,
                        status=400,
                        code='invalid_datetime',
                    ) from exc

        # -----------------------------------------------------
        # Odoo guarda datetime UTC sin tzinfo
        # -----------------------------------------------------

        if (
            parsed.tzinfo
            is not None
        ):

            parsed = (
                parsed
                .astimezone(
                    timezone.utc
                )
                .replace(
                    tzinfo=None
                )
            )

        # -----------------------------------------------------
        # Quitar microsegundos para mantener formato Odoo
        # -----------------------------------------------------

        parsed = parsed.replace(
            microsecond=0
        )

        return parsed

    # =========================================================
    # ENDPOINT POLL
    # =========================================================

    @http.route(
        '/api/monitoring/agent/poll',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def poll(
        self,
        **kwargs,
    ):
        """
        Recibe una lectura completa del equipo.

        Payload esperado:

        {
            "device_id": 25,
            "state": "success|partial|failed|timeout|offline",
            "duration_ms": 900,
            "response_ms": 40,
            "snmp_version": "2c",
            "started_at": "2026-08-24T22:51:49.785671+00:00",
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

            # -------------------------------------------------
            # AUTENTICACIÓN
            # -------------------------------------------------

            agent = (
                self._authenticate_agent()
            )

            payload = (
                self._read_json(
                    required=True
                )
            )

            # -------------------------------------------------
            # EQUIPO
            # -------------------------------------------------

            device = (
                self._get_agent_device(
                    agent,
                    payload.get(
                        'device_id'
                    ),
                )
            )

            # -------------------------------------------------
            # VALIDAR MONITOREO
            # -------------------------------------------------

            if (
                not device.monitoring_enabled
                and not device.inventory_enabled
            ):
                raise MonitoringApiError(
                    _(
                        'El monitoreo está '
                        'deshabilitado para este equipo.'
                    ),
                    status=403,
                    code='device_monitoring_disabled',
                )

            # -------------------------------------------------
            # VALIDAR RED
            # -------------------------------------------------

            if (
                device.network_id
                and device.network_id.agent_id
                != agent
            ):
                raise MonitoringApiError(
                    _(
                        'La red del equipo no '
                        'corresponde al agente.'
                    ),
                    status=403,
                    code='device_network_mismatch',
                )

            # -------------------------------------------------
            # LOG DE POLLING RECIBIDO
            # -------------------------------------------------

            _logger.info(
                '[MONITORING POLL] '
                'Recibido | '
                'agent=%s | '
                'device=%s | '
                'ip=%s | '
                'started_at=%s',
                agent.code,
                device.id,
                device.ip_address,
                payload.get(
                    'started_at'
                ),
            )

            # -------------------------------------------------
            # SNAPSHOT
            # -------------------------------------------------

            snapshot = (
                self._create_snapshot(
                    device,
                    agent,
                    payload,
                )
            )

            # -------------------------------------------------
            # PAYLOAD
            # -------------------------------------------------

            state = (
                self._normalize_poll_state(
                    payload
                )
            )

            identity = (
                payload.get(
                    'identity'
                )
                or {}
            )

            readings_payload = (
                payload.get(
                    'readings'
                )
                or []
            )

            alerts_payload = (
                payload.get(
                    'alerts'
                )
                or []
            )

            # -------------------------------------------------
            # VALIDACIONES
            # -------------------------------------------------

            if not isinstance(
                identity,
                dict,
            ):
                raise MonitoringApiError(
                    _(
                        'identity debe ser un objeto.'
                    ),
                    status=400,
                    code='invalid_identity',
                )

            if not isinstance(
                readings_payload,
                list,
            ):
                raise MonitoringApiError(
                    _(
                        'readings debe ser una lista.'
                    ),
                    status=400,
                    code='invalid_readings',
                )

            if not isinstance(
                alerts_payload,
                list,
            ):
                raise MonitoringApiError(
                    _(
                        'alerts debe ser una lista.'
                    ),
                    status=400,
                    code='invalid_alerts',
                )

            # =================================================
            # IDENTIDAD
            # =================================================

            if identity:

                snapshot.apply_identity(
                    identity
                )

                device.apply_identity_payload(
                    identity
                )

            # =================================================
            # LECTURAS
            # =================================================

            created_readings = (
                snapshot.env[
                    'sat.monitoring.reading'
                ].browse()
            )

            if readings_payload:

                created_readings = (
                    snapshot.process_readings(
                        readings_payload
                    )
                )

            # =================================================
            # ALERTAS
            # =================================================

            if (
                device.alert_monitoring_enabled
            ):

                snapshot.process_alerts(
                    alerts_payload,
                    complete_list=bool(
                        payload.get(
                            'alerts_complete',
                            True,
                        )
                    ),
                )

            # =================================================
            # ESTADO DEL EQUIPO
            # =================================================

            device_status = (
                self._clean_text(
                    payload.get(
                        'device_status'
                    )
                ).lower()
            )

            if device_status:

                device.apply_status(
                    status=device_status
                )

            # =================================================
            # ESTADÍSTICAS
            # =================================================

            snapshot.recalculate_statistics()

            if (
                state == 'success'
                and
                snapshot.missing_required_metric_count
                > 0
            ):
                state = 'partial'

            # =================================================
            # DATOS COMUNES FINALIZACIÓN
            # =================================================

            common_finish = {
                'duration_ms':
                    payload.get(
                        'duration_ms'
                    ),

                'response_ms':
                    payload.get(
                        'response_ms'
                    ),

                'statistics':
                    payload.get(
                        'statistics'
                    )
                    or {},

                'raw_payload':
                    payload.get(
                        'raw'
                    ),

                'agent_payload':
                    payload,

                'summary':
                    payload.get(
                        'summary'
                    ),
            }

            # =================================================
            # FINALIZAR SNAPSHOT
            # =================================================

            if state == 'success':

                snapshot.finish_success(
                    **common_finish,
                    snmp_version=(
                        payload.get(
                            'snmp_version'
                        )
                    ),
                )

            elif state == 'partial':

                snapshot.finish_partial(
                    warning_message=(
                        payload.get(
                            'warning_message'
                        )
                        or
                        payload.get(
                            'error_message'
                        )
                        or
                        'partial_poll'
                    ),
                    **common_finish,
                    snmp_version=(
                        payload.get(
                            'snmp_version'
                        )
                    ),
                )

            else:

                snapshot.finish_failure(
                    state=state,
                    error_code=(
                        payload.get(
                            'error_code'
                        )
                    ),
                    error_message=(
                        payload.get(
                            'error_message'
                        )
                    ),
                    duration_ms=(
                        payload.get(
                            'duration_ms'
                        )
                    ),
                    response_ms=(
                        payload.get(
                            'response_ms'
                        )
                    ),
                    raw_payload=(
                        payload.get(
                            'raw'
                        )
                    ),
                    agent_payload=payload,
                )

            # -------------------------------------------------
            # Recalcular siempre con datos realmente guardados
            # -------------------------------------------------

            snapshot.recalculate_statistics()

            # =================================================
            # PROFILE MISMATCH
            # =================================================

            if payload.get(
                'profile_mismatch'
            ):

                snapshot.mark_profile_mismatch(
                    reason=(
                        payload.get(
                            'profile_mismatch_reason'
                        )
                        or
                        'agent_reported_mismatch'
                    )
                )

            # =================================================
            # LOG RESULTADO
            # =================================================

            _logger.info(
                '[MONITORING POLL] '
                'Procesado OK | '
                'device=%s | '
                'snapshot=%s | '
                'state=%s | '
                'readings=%s',
                device.id,
                snapshot.id,
                snapshot.state,
                len(
                    created_readings
                ),
            )

            # =================================================
            # RESPUESTA
            # =================================================

            return self._ok(
                {
                    'snapshot_id':
                        snapshot.id,

                    'device_id':
                        device.id,

                    'state':
                        snapshot.state,

                    'readings_saved':
                        len(
                            created_readings
                        ),

                    'alerts_active':
                        device.active_alert_count,

                    'missing_required_metrics':
                        snapshot.missing_required_metric_count,

                    'profile_mismatch':
                        snapshot.profile_mismatch,
                },
                status=201,
            )

        except Exception as error:

            return (
                self._handle_api_exception(
                    error,
                    endpoint='poll',
                )
            )

    # =========================================================
    # CREAR SNAPSHOT
    # =========================================================

    def _create_snapshot(
        self,
        device,
        agent,
        payload,
    ):

        agent_info = (
            payload.get(
                'agent'
            )
            or {}
        )

        if not isinstance(
            agent_info,
            dict,
        ):
            agent_info = {}

        if not agent_info.get(
            'identifier'
        ):
            agent_info[
                'identifier'
            ] = agent.code

        if not agent_info.get(
            'version'
        ):
            agent_info[
                'version'
            ] = (
                agent.agent_version
                or ''
            )

        if not agent_info.get(
            'hostname'
        ):
            agent_info[
                'hostname'
            ] = (
                agent.hostname
                or ''
            )

        # -----------------------------------------------------
        # NORMALIZAR started_at
        # -----------------------------------------------------

        started_at_raw = (
            payload.get(
                'started_at'
            )
        )

        started_at = (
            self._normalize_datetime(
                started_at_raw
            )
            if started_at_raw
            else False
        )

        _logger.debug(
            '[MONITORING POLL] '
            'started_at raw=%s | normalizado=%s',
            started_at_raw,
            started_at,
        )

        return (
            device.env[
                'sat.monitoring.snapshot'
            ]
            .sudo()
            .create_for_device(
                device=device,
                started_at=started_at,
                agent_info=agent_info,
            )
        )
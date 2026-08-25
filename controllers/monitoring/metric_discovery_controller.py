# -*- coding: utf-8 -*-

import logging

from odoo import http, _
from odoo.http import request

from .common import MonitoringApiMixin, MonitoringApiError


_logger = logging.getLogger(__name__)


class MonitoringMetricDiscoveryController(
    http.Controller,
    MonitoringApiMixin,
):

    MAX_FEATURES_PER_REQUEST = 1000

    @http.route(
        '/api/monitoring/agent/device/<int:device_id>/features/discovery',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def register_discovered_features(
        self,
        device_id,
        **kwargs,
    ):
        """
        Recibe características/OIDs descubiertos dinámicamente por el agente.

        Payload esperado:

        {
            "features": [
                {
                    "code": "finisher_present",
                    "name": "Finisher detectado",
                    "category": "accessory",
                    "reading_category": "accessory",
                    "feature_type": "boolean",
                    "logical_type": "boolean",
                    "value": true,
                    "raw_value": "1",
                    "oid": "1.3.6.1....",
                    "oid_name": "",
                    "oid_index": "1",
                    "source_label": "Finisher",
                    "source_method": "dynamic_discovery",
                    "discovered_dynamically": true,
                    "confidence": "candidate"
                }
            ],
            "duration_ms": 1234,
            "statistics": {
                "walked_oids": 100,
                "candidates": 5
            },
            "summary": "Discovery estructural Ricoh"
        }
        """

        try:
            agent = self._authenticate_agent()

            device = self._get_agent_device(
                agent,
                device_id,
            )

            payload = self._read_json(
                required=True,
            )

            features = payload.get(
                'features'
            )

            if not isinstance(
                features,
                list,
            ):
                raise MonitoringApiError(
                    _(
                        'features debe ser una lista.'
                    ),
                    status=400,
                    code='invalid_features',
                )

            if len(features) > self.MAX_FEATURES_PER_REQUEST:
                raise MonitoringApiError(
                    _(
                        'La cantidad de características '
                        'excede el límite permitido.'
                    ),
                    status=400,
                    code='feature_limit_exceeded',
                    details={
                        'limit':
                            self.MAX_FEATURES_PER_REQUEST,

                        'received':
                            len(features),
                    },
                )

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

            agent_info = {
                'identifier':
                    agent.code,

                'version':
                    agent.agent_version
                    or '',

                'hostname':
                    agent.hostname
                    or '',
            }

            Snapshot = request.env[
                'sat.monitoring.snapshot'
            ].sudo()

            Feature = request.env[
                'sat.monitoring.device.feature'
            ].sudo()

            snapshot = Snapshot.create_for_device(
                device=device,
                agent_info=agent_info,
            )

            saved = []
            errors = []

            for index, feature_data in enumerate(
                features
            ):
                if not isinstance(
                    feature_data,
                    dict,
                ):
                    errors.append({
                        'index':
                            index,

                        'code':
                            '',

                        'error':
                            'invalid_feature_payload',
                    })
                    continue

                code = self._clean_text(
                    feature_data.get(
                        'code'
                    )
                )

                if not code:
                    errors.append({
                        'index':
                            index,

                        'code':
                            '',

                        'error':
                            'feature_code_required',
                    })
                    continue

                normalized = dict(
                    feature_data
                )

                normalized[
                    'code'
                ] = code

                normalized[
                    'source_method'
                ] = (
                    self._clean_text(
                        normalized.get(
                            'source_method'
                        )
                    )
                    or 'dynamic_discovery'
                )

                normalized[
                    'discovered_dynamically'
                ] = True

                normalized[
                    'confidence'
                ] = (
                    self._clean_text(
                        normalized.get(
                            'confidence'
                        )
                    )
                    or 'candidate'
                )

                try:
                    with request.env.cr.savepoint():
                        feature = (
                            Feature.register_feature(
                                device=device,
                                feature_data=normalized,
                                snapshot=snapshot,
                            )
                        )

                    if feature:
                        saved.append({
                            'index':
                                index,

                            'id':
                                feature.id,

                            'code':
                                feature.code,

                            'confidence':
                                feature.confidence,

                            'observation_count':
                                feature.observation_count,
                        })
                    else:
                        errors.append({
                            'index':
                                index,

                            'code':
                                code,

                            'error':
                                'feature_not_created',
                        })

                except Exception as error:
                    _logger.warning(
                        '[METRIC DISCOVERY] '
                        'Feature rechazado | '
                        'device=%s | '
                        'code=%s | '
                        'error=%s',
                        device.id,
                        code,
                        error,
                    )

                    errors.append({
                        'index':
                            index,

                        'code':
                            code,

                        'error':
                            str(error),
                    })

            try:
                snapshot.recalculate_statistics()
            except Exception:
                _logger.exception(
                    '[METRIC DISCOVERY] '
                    'No se pudieron recalcular '
                    'estadísticas | device=%s '
                    '| snapshot=%s',
                    device.id,
                    snapshot.id,
                )

            duration_ms = self._safe_int(
                payload.get(
                    'duration_ms'
                ),
                default=0,
                minimum=0,
            )

            summary = (
                self._clean_text(
                    payload.get(
                        'summary'
                    )
                )
                or (
                    'Discovery estructural | '
                    f'Recibidas={len(features)} | '
                    f'Guardadas={len(saved)} | '
                    f'Errores={len(errors)}'
                )
            )

            statistics = (
                payload.get(
                    'statistics'
                )
                if isinstance(
                    payload.get(
                        'statistics'
                    ),
                    dict,
                )
                else {}
            )

            statistics = dict(
                statistics
            )

            statistics.update({
                'features_received':
                    len(features),

                'features_saved':
                    len(saved),

                'features_failed':
                    len(errors),
            })

            if saved and not errors:
                snapshot.finish_success(
                    duration_ms=duration_ms,
                    statistics=statistics,
                    agent_payload=payload,
                    summary=summary,
                )

            elif saved:
                snapshot.finish_partial(
                    warning_message=(
                        'metric_discovery_partial'
                    ),
                    duration_ms=duration_ms,
                    statistics=statistics,
                    agent_payload=payload,
                    summary=summary,
                )

            else:
                snapshot.finish_failure(
                    state='failed',
                    error_code=(
                        'metric_discovery_failed'
                    ),
                    error_message=(
                        'No se pudo registrar '
                        'ninguna característica.'
                    ),
                    duration_ms=duration_ms,
                    agent_payload=payload,
                )

            try:
                snapshot.recalculate_statistics()
            except Exception:
                pass

            _logger.info(
                '[METRIC DISCOVERY] '
                'Procesado | '
                'agent=%s | '
                'device=%s | '
                'snapshot=%s | '
                'received=%s | '
                'saved=%s | '
                'errors=%s',
                agent.code,
                device.id,
                snapshot.id,
                len(features),
                len(saved),
                len(errors),
            )

            return self._ok(
                {
                    'device_id':
                        device.id,

                    'snapshot_id':
                        snapshot.id,

                    'received':
                        len(features),

                    'saved':
                        len(saved),

                    'failed':
                        len(errors),

                    'features':
                        saved,

                    'errors':
                        errors,
                },
                status=201,
            )

        except Exception as error:
            return self._handle_api_exception(
                error,
                endpoint='metric_discovery',
            )

# ================================================================================================
# MODELO: printtracker_alert_manager.py - Gestor de Alertas PrintTracker
# ------------------------------------------------------------------------------------------------
# ENFOQUE: Solo API events (códigos, atascos, toner, errores de dispositivo).
# No procesa offline, uso anómalo, contadores decrecientes ni suministros locales.
# ------------------------------------------------------------------------------------------------
# Comportamiento:
#   1. Cada 5 min consulta /v1/entity/{id}/events de PrintTracker (solo equipos alquilados).
#   2. Crea alerta + envía correo INMEDIATO al detectar un event nuevo.
#   3. Para alertas ya existentes con resolutionStatus=Open, reenvía correo cada 3 horas.
#   4. Cuando el event pasa a resolutionStatus=Resolved, marca la alerta local como 'resuelta'.
#   5. Procesa TODAS las alertas en estado 'nueva' (sin ventana de tiempo que pierda notificaciones).
# ------------------------------------------------------------------------------------------------
# COMPATIBILIDAD: Los campos revisar_* y sus contadores se MANTIENEN como legacy para que la
# vista XML existente (printtracker_views.xml) siga cargando sin modificaciones. Ya no se usan
# en la lógica, pero siguen existiendo en el modelo.
# ================================================================================================

from odoo import models, fields, api
import logging
import traceback
from datetime import datetime, timedelta
import requests

_logger = logging.getLogger(__name__)

# Ventana hacia atrás para consultar events de la API (con overlap generoso por seguridad)
HORAS_API_EVENTS = 6

# Intervalo de reenvío de correo para alertas con event Open
HORAS_REENVIO = 3


class PrintTrackerAlertManager(models.TransientModel):
    _name = 'printtracker.alert.manager'
    _description = 'Gestor de Alertas PrintTracker (solo API events)'

    # ==========================================
    # CAMPOS LEGACY (compatibilidad con vista XML existente)
    # Ya no se usan en la lógica, pero se mantienen para que la vista XML siga cargando.
    # ==========================================
    revisar_suministros = fields.Boolean('Revisar Suministros (legacy)', default=False)
    revisar_equipos_offline = fields.Boolean('Revisar Equipos Offline (legacy)', default=False)
    revisar_uso_anomalo = fields.Boolean('Revisar Uso Anómalo (legacy)', default=False)
    revisar_contadores_decrecen = fields.Boolean('Revisar Contadores (legacy)', default=False)
    revisar_api_events = fields.Boolean('Revisar Events de API', default=True)

    umbral_suministro_bajo = fields.Float('Umbral Suministro Bajo (legacy)', default=15.0)
    umbral_suministro_critico = fields.Float('Umbral Suministro Crítico (legacy)', default=5.0)
    dias_offline_alerta = fields.Integer('Días Offline Alerta (legacy)', default=3)
    dias_offline_critico = fields.Integer('Días Offline Crítico (legacy)', default=7)

    alertas_suministros = fields.Integer('Alertas Suministros (legacy)', readonly=True)
    alertas_offline = fields.Integer('Alertas Offline (legacy)', readonly=True)
    alertas_uso_anomalo = fields.Integer('Alertas Uso Anómalo (legacy)', readonly=True)
    alertas_contadores = fields.Integer('Alertas Contadores (legacy)', readonly=True)
    alertas_api_events = fields.Integer('Alertas API Events', readonly=True)
    ultimo_event_procesado = fields.Char('Último Event ID Procesado', readonly=True)

    # ==========================================
    # RESULTADOS DE EJECUCIÓN (nuevos)
    # ==========================================
    alertas_nuevas = fields.Integer('Alertas Nuevas', readonly=True)
    alertas_reenviadas = fields.Integer('Alertas Reenviadas', readonly=True)
    alertas_cerradas = fields.Integer('Alertas Auto-Cerradas', readonly=True)
    notificaciones_enviadas = fields.Integer('Correos Enviados', readonly=True)
    errores_encontrados = fields.Integer('Errores', readonly=True)
    tiempo_ejecucion = fields.Float('Tiempo Ejecución (seg)', readonly=True)
    log_ejecucion = fields.Text('Log de Ejecución', readonly=True)

    # ==========================================
    # HELPER: EQUIPOS ALQUILADOS ACTIVOS
    # ==========================================
    def _get_series_alquilados(self):
        """
        Retorna set de series normalizadas de equipos con contrato activo.

        Se normaliza con strip + upper para evitar perder events por
        diferencias de mayúsculas/minúsculas o espacios.
        """
        equipos = self.env['alquiler'].search([
            ('estado_alquiler_id', '=', 'alquilada'),
        ])

        series = set()
        for serie in equipos.mapped('serie'):
            normalizada = str(serie or '').strip().upper()
            if normalizada:
                series.add(normalizada)

        return series

    @api.model
    def ejecutar_revision_automatica(self):
        """Ejecutado por cron cada 5 min."""
        try:
            _logger.info("🚨 === REVISIÓN AUTOMÁTICA (API events) ===")

            alert_manager = self.create({})
            resultado = alert_manager.ejecutar_revision_completa()

            if resultado:
                _logger.info(
                    f"✅ Completado: {alert_manager.alertas_nuevas} nuevas, "
                    f"{alert_manager.alertas_reenviadas} reenvíos, "
                    f"{alert_manager.alertas_cerradas} auto-cerradas, "
                    f"{alert_manager.notificaciones_enviadas} correos"
                )
            else:
                _logger.error("❌ Error en revisión automática")

            return resultado

        except Exception as e:
            _logger.error(f"❌ Error crítico: {e}\n{traceback.format_exc()}")
            return False

    # ==========================================
    # EJECUTAR REVISIÓN COMPLETA
    # ==========================================
    def ejecutar_revision_completa(self):
        """Ejecuta las 4 fases: detección, auto-cierre, reenvíos, huérfanas."""
        try:
            inicio = datetime.now()
            log_lines = [
                "🚨 === INICIANDO REVISIÓN DE ALERTAS (API EVENTS) ===",
                f"⏰ {inicio.strftime('%Y-%m-%d %H:%M:%S')}",
                "🔍 Filtro: Solo equipos con estado 'Alquilada'",
                "",
            ]

            # FASE 1: Detectar nuevos events + notificar
            log_lines.append("📋 === FASE 1: DETECCIÓN DE EVENTS ===")
            res_detect = self._detectar_y_crear_alertas()
            log_lines.extend(res_detect['log'])
            self.alertas_nuevas = res_detect['alertas_nuevas']
            # Mantener compatibilidad con el campo legacy
            self.alertas_api_events = res_detect['alertas_nuevas']
            if res_detect.get('ultimo_event_id'):
                self.ultimo_event_procesado = res_detect['ultimo_event_id']
            log_lines.append("")

            # FASE 2: Auto-cerrar alertas cuyo event ya fue resuelto en PrintTracker
            log_lines.append("✅ === FASE 2: AUTO-CIERRE DE ALERTAS RESUELTAS ===")
            res_close = self._auto_cerrar_alertas_resueltas()
            log_lines.extend(res_close['log'])
            self.alertas_cerradas = res_close['cerradas']
            log_lines.append("")

            # FASE 3: Reenviar correos de alertas aún abiertas (cada 3h)
            log_lines.append("📧 === FASE 3: REENVÍO DE CORREOS (cada 3h) ===")
            res_resend = self._reenviar_alertas_pendientes()
            log_lines.extend(res_resend['log'])
            self.alertas_reenviadas = res_resend['reenviadas']
            log_lines.append("")

            # FASE 4: Procesar alertas 'nueva' sin notificar (por si alguna quedó huérfana)
            log_lines.append("📬 === FASE 4: NOTIFICACIONES PENDIENTES ===")
            res_notif = self._procesar_notificaciones_pendientes()
            log_lines.extend(res_notif['log'])
            self.notificaciones_enviadas = (
                res_detect['notificaciones']
                + res_resend['reenviadas']
                + res_notif['notificaciones']
            )
            log_lines.append("")

            # Estadísticas
            tiempo = (datetime.now() - inicio).total_seconds()
            self.tiempo_ejecucion = tiempo

            log_lines.extend([
                "📊 === ESTADÍSTICAS ===",
                f"⏱️ Tiempo: {tiempo:.2f}s",
                f"🆕 Alertas nuevas: {self.alertas_nuevas}",
                f"📧 Alertas reenviadas: {self.alertas_reenviadas}",
                f"✅ Alertas auto-cerradas: {self.alertas_cerradas}",
                f"📬 Correos totales enviados: {self.notificaciones_enviadas}",
                f"❌ Errores: {self.errores_encontrados}",
                "",
                "✅ === COMPLETADO ===",
            ])

            self.log_ejecucion = "\n".join(log_lines)
            return True

        except Exception as e:
            _logger.error(f"❌ Error revisión: {e}\n{traceback.format_exc()}")
            self.log_ejecucion = (self.log_ejecucion or "") + f"\n❌ {e}"
            self.errores_encontrados = (self.errores_encontrados or 0) + 1
            return False

    # ==========================================
    # FASE 1: DETECTAR EVENTS Y CREAR ALERTAS
    # ==========================================
    def _detectar_y_crear_alertas(self):
        """
        Consulta /events de PrintTracker.
        Crea alerta para CUALQUIER event nuevo de equipo alquilado y envía
        correo inmediato.

        No filtra por tipo de alerta: consumibles, atascos, errores,
        mantenimiento y tipos futuros se conservan en printtracker.alert.
        """
        try:
            log_lines = []
            alertas_nuevas = 0
            notificaciones = 0
            ultimo_event_id = None

            api_config = self._get_printtracker_api_config()
            if not api_config:
                log_lines.append("❌ Config API no encontrada")
                return {
                    'alertas_nuevas': 0,
                    'notificaciones': 0,
                    'log': log_lines,
                    'ultimo_event_id': None,
                }

            series_ok = self._get_series_alquilados()
            if not series_ok:
                log_lines.append("ℹ️ Sin equipos alquilados")
                return {
                    'alertas_nuevas': 0,
                    'notificaciones': 0,
                    'log': log_lines,
                    'ultimo_event_id': None,
                }

            log_lines.append(
                f"📋 Equipos alquilados monitoreados: {len(series_ok)}"
            )

            # Ventana de consulta: últimas HORAS_API_EVENTS.
            # Existe overlap intencional; api_event_id evita duplicados.
            start_from = datetime.utcnow() - timedelta(
                hours=HORAS_API_EVENTS
            )
            events = self._consultar_printtracker_events(
                api_config,
                start_from,
            )

            if not events:
                log_lines.append("ℹ️ Sin events en la ventana consultada")
                return {
                    'alertas_nuevas': 0,
                    'notificaciones': 0,
                    'log': log_lines,
                    'ultimo_event_id': None,
                }

            log_lines.append(
                f"📥 Events recibidos de PrintTracker: {len(events)}"
            )

            # Filtrar únicamente por pertenencia a equipos alquilados.
            # NO filtrar por alertType, description ni supplyKey.
            relevantes = []
            sin_serie = 0

            for event in events:
                serial_raw = event.get('deviceSerialNumber')
                serial_norm = str(serial_raw or '').strip().upper()

                if not serial_norm:
                    sin_serie += 1
                    continue

                if serial_norm in series_ok:
                    relevantes.append(event)

            ignorados = len(events) - len(relevantes)

            log_lines.append(
                f"📋 {len(relevantes)} events relevantes "
                f"({ignorados} ignorados; {sin_serie} sin serie)"
            )

            for event in relevantes:
                try:
                    eid = event.get('id')
                    serial = str(
                        event.get('deviceSerialNumber') or ''
                    ).strip()
                    desc = str(
                        event.get('description') or 'Sin descripción'
                    )[:120]
                    alert_type = event.get('alertType')
                    supply_key = event.get('supplyKey')
                    resolution = event.get('resolutionStatus')

                    if not eid:
                        log_lines.append(
                            f"⚠️ Event sin id omitido serie={serial or 'N/A'}"
                        )
                        continue

                    # Dedup: si ya existe alerta para este event_id, omitir.
                    if self._event_ya_procesado(eid):
                        continue

                    alerta = (
                        self.env['printtracker.alert']
                        .crear_alerta_desde_api_event(
                            event,
                            serial,
                        )
                    )

                    if alerta:
                        alertas_nuevas += 1
                        ultimo_event_id = eid

                        log_lines.append(
                            f"🆕 {serial}: {desc} "
                            f"[alertType={alert_type or '-'} "
                            f"supplyKey={supply_key or '-'} "
                            f"status={resolution or '-'}]"
                        )

                        # Enviar correo INMEDIATO para toda alerta nueva,
                        # independientemente de si es tóner, error u otro event.
                        alerta.procesar_notificaciones()

                        if alerta.email_enviado:
                            notificaciones += 1
                        else:
                            log_lines.append(
                                f"⚠️ Correo pendiente para event={eid} "
                                f"serie={serial}"
                            )

                except Exception as e:
                    log_lines.append(
                        f"❌ Event {event.get('id', '?')}: {e}"
                    )
                    self.errores_encontrados = (
                        self.errores_encontrados or 0
                    ) + 1

            log_lines.append(
                f"✅ {alertas_nuevas} alertas nuevas, "
                f"{notificaciones} correos inmediatos"
            )

            return {
                'alertas_nuevas': alertas_nuevas,
                'notificaciones': notificaciones,
                'log': log_lines,
                'ultimo_event_id': ultimo_event_id,
            }

        except Exception as e:
            _logger.error(
                f"❌ Error detección: {e}\n{traceback.format_exc()}"
            )
            return {
                'alertas_nuevas': 0,
                'notificaciones': 0,
                'log': [f"❌ {e}"],
                'ultimo_event_id': None,
            }

    def _auto_cerrar_alertas_resueltas(self):
        """
        Consulta events recientes y cierra alertas locales cuyo
        resolutionStatus sea Resolved.

        La documentación actual de PrintTracker define:
            Open
            In Progress
            Resolved

        Se acepta también Closed como compatibilidad histórica, pero no se
        envía como parámetro a GET /events porque ese filtro no está
        documentado para el endpoint.
        """
        try:
            log_lines = []
            cerradas = 0

            api_config = self._get_printtracker_api_config()
            if not api_config:
                log_lines.append("❌ Config API no encontrada")
                return {
                    'cerradas': 0,
                    'log': log_lines,
                }

            alertas_activas = self.env['printtracker.alert'].search([
                ('origen_datos', '=', 'api_events'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('api_event_id', '!=', False),
            ])

            if not alertas_activas:
                log_lines.append(
                    "ℹ️ Sin alertas activas de origen API"
                )
                return {
                    'cerradas': 0,
                    'log': log_lines,
                }

            log_lines.append(
                f"📋 {len(alertas_activas)} alertas activas a verificar"
            )

            start_from = datetime.utcnow() - timedelta(
                hours=HORAS_API_EVENTS
            )

            # GET /events no documenta resolutionStatus como query param.
            # Se consultan los events y el estado se filtra localmente.
            events = self._consultar_printtracker_events(
                api_config,
                start_from,
                solo_nuevos=False,
            )

            if not events:
                log_lines.append(
                    "ℹ️ Sin events recientes para verificar resolución"
                )
                return {
                    'cerradas': 0,
                    'log': log_lines,
                }

            events_by_id = {
                event.get('id'): event
                for event in events
                if event.get('id')
            }

            resolved_ids = {
                event_id
                for event_id, event in events_by_id.items()
                if str(
                    event.get('resolutionStatus') or ''
                ).strip().lower() in (
                    'resolved',
                    'closed',  # compatibilidad histórica
                )
            }

            log_lines.append(
                f"📋 {len(resolved_ids)} events resueltos recibidos"
            )

            for alerta in alertas_activas:
                try:
                    event = events_by_id.get(
                        alerta.api_event_id
                    )

                    if not event:
                        continue

                    status = str(
                        event.get('resolutionStatus') or ''
                    ).strip()

                    # Mantener sincronizado el estado API visible en Odoo.
                    if status and alerta.api_resolution_status != status:
                        alerta.api_resolution_status = status

                    if alerta.api_event_id in resolved_ids:
                        alerta.write({
                            'estado': 'resuelta',
                            'api_resolution_status': (
                                status or 'Resolved'
                            ),
                            'fecha_resolucion': fields.Datetime.now(),
                            'notas_resolucion': (
                                'Auto-cerrada: event resuelto '
                                'en PrintTracker'
                            ),
                        })
                        cerradas += 1
                        log_lines.append(
                            f"✅ Resuelta: {alerta.serie_equipo} "
                            f"(event {alerta.api_event_id})"
                        )

                except Exception as e:
                    log_lines.append(
                        f"❌ Error cerrando "
                        f"{alerta.display_name}: {e}"
                    )
                    self.errores_encontrados = (
                        self.errores_encontrados or 0
                    ) + 1

            log_lines.append(
                f"✅ {cerradas} alertas auto-cerradas"
            )
            return {
                'cerradas': cerradas,
                'log': log_lines,
            }

        except Exception as e:
            _logger.error(
                f"❌ Error auto-cierre: "
                f"{e}\n{traceback.format_exc()}"
            )
            return {
                'cerradas': 0,
                'log': [f"❌ {e}"],
            }

    def _reenviar_alertas_pendientes(self):
        """
        Reenvía correos de alertas API todavía activas.

        Casos:
        - Si nunca pudo enviarse el correo, se reintenta.
        - Si ya se envió, se reenvía cuando hayan pasado HORAS_REENVIO.
        - No reenvía alertas que localmente ya estén resueltas/cerradas.
        """
        try:
            log_lines = []
            reenviadas = 0

            corte = (
                fields.Datetime.now()
                - timedelta(hours=HORAS_REENVIO)
            )

            candidatas = self.env['printtracker.alert'].search([
                ('origen_datos', '=', 'api_events'),
                ('estado', 'in', ['notificada', 'en_proceso']),
            ])

            alertas = self.env['printtracker.alert'].browse()

            for alerta in candidatas:
                status = str(
                    alerta.api_resolution_status or ''
                ).strip().lower()

                if status in ('resolved', 'closed'):
                    continue

                # Primer envío fallido que quedó atrapado en una versión
                # anterior: reintentar.
                if not alerta.email_enviado:
                    alertas |= alerta
                    continue

                # Reenvío periódico de una alerta aún abierta.
                if (
                    not alerta.ultima_revision
                    or alerta.ultima_revision <= corte
                ):
                    alertas |= alerta

            if not alertas:
                log_lines.append(
                    f"ℹ️ Sin alertas pendientes de reenvío "
                    f"(umbral {HORAS_REENVIO}h)"
                )
                return {
                    'reenviadas': 0,
                    'log': log_lines,
                }

            log_lines.append(
                f"📧 {len(alertas)} alertas a enviar/reenviar"
            )

            for alerta in alertas:
                try:
                    era_reenvio = bool(alerta.email_enviado)

                    if era_reenvio:
                        alerta.write({
                            'email_enviado': False,
                            'contador_repeticiones': (
                                alerta.contador_repeticiones + 1
                            ),
                        })

                    enviado = alerta._enviar_notificacion_email()

                    if enviado and alerta.email_enviado:
                        reenviadas += 1

                        if era_reenvio:
                            log_lines.append(
                                f"📧 Reenvío "
                                f"#{alerta.contador_repeticiones}: "
                                f"{alerta.serie_equipo} - "
                                f"{alerta.tipo_alerta}"
                            )
                        else:
                            log_lines.append(
                                f"📧 Envío recuperado: "
                                f"{alerta.serie_equipo} - "
                                f"{alerta.tipo_alerta}"
                            )
                    else:
                        log_lines.append(
                            f"⚠️ Sigue pendiente el correo: "
                            f"{alerta.serie_equipo} - "
                            f"{alerta.tipo_alerta}"
                        )

                except Exception as e:
                    log_lines.append(
                        f"❌ Error reenvío "
                        f"{alerta.display_name}: {e}"
                    )
                    self.errores_encontrados = (
                        self.errores_encontrados or 0
                    ) + 1

            log_lines.append(
                f"✅ {reenviadas} correos enviados/re-enviados"
            )
            return {
                'reenviadas': reenviadas,
                'log': log_lines,
            }

        except Exception as e:
            _logger.error(
                f"❌ Error reenvíos: "
                f"{e}\n{traceback.format_exc()}"
            )
            return {
                'reenviadas': 0,
                'log': [f"❌ {e}"],
            }

    def _procesar_notificaciones_pendientes(self):
        """
        Procesa alertas en estado 'nueva' que por cualquier razón no se notificaron.
        Sin ventana de tiempo — procesa TODAS las nuevas.
        """
        try:
            log_lines = []
            enviadas = 0

            pendientes = self.env['printtracker.alert'].search([
                ('estado', '=', 'nueva'),
            ])

            if not pendientes:
                log_lines.append("ℹ️ Sin alertas huérfanas")
                return {'notificaciones': 0, 'log': log_lines}

            log_lines.append(f"📬 {len(pendientes)} alertas huérfanas a procesar")

            for alerta in pendientes:
                try:
                    alerta.procesar_notificaciones()
                    if alerta.estado == 'notificada':
                        enviadas += 1
                        log_lines.append(f"📧 {alerta.display_name}")
                except Exception as e:
                    log_lines.append(f"❌ {alerta.display_name}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {enviadas} notificaciones enviadas")
            return {'notificaciones': enviadas, 'log': log_lines}

        except Exception as e:
            return {'notificaciones': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # AUXILIARES API
    # ==========================================
    def _get_printtracker_api_config(self):
        """Obtiene configuración de la API: entity_id, api_key, base_url."""
        try:
            entity = self.env['printtracker.entity'].search([('is_active', '=', True)], limit=1)
            cp = self.env['ir.config_parameter'].sudo()
            base = cp.get_param('printtracker.api.base_url', 'https://papi.printtrackerpro.com/v1')

            if entity and entity.pt_entity_id:
                token = getattr(entity, 'api_token', None) or cp.get_param('printtracker.api.key')
                if token:
                    return {
                        'base_url': base.rstrip('/'),
                        'entity_id': entity.pt_entity_id,
                        'api_key': token,
                        'timeout': 30,
                    }

            eid = cp.get_param('printtracker.api.entity_id')
            key = cp.get_param('printtracker.api.key')
            if eid and key:
                return {
                    'base_url': base.rstrip('/'),
                    'entity_id': eid,
                    'api_key': key,
                    'timeout': 30,
                }

            # Fallback: usar printtracker.config si está disponible
            config = self.env['printtracker.config'].search([('sync_enabled', '=', True)], limit=1)
            if config:
                return {
                    'base_url': config.api_url.rstrip('/'),
                    'entity_id': config.entity_bbbb_id,
                    'api_key': config.api_key,
                    'timeout': config.timeout_seconds or 30,
                }

            return None
        except Exception as e:
            _logger.error(f"❌ Config API: {e}")
            return None

    def _consultar_printtracker_events(
        self,
        cfg,
        start_from,
        resolution_status=None,
        solo_nuevos=True,
    ):
        """
        Consulta GET /v1/entity/{id}/events.

        Según la documentación oficial, GET /events acepta:
            excludeDisabled
            includeChildren
            start
            end

        resolutionStatus forma parte del objeto event y se filtra
        localmente cuando este método recibe ese argumento.
        """
        try:
            url = (
                f"{cfg['base_url']}/entity/"
                f"{cfg['entity_id']}/events"
            )

            headers = {
                'x-api-key': cfg['api_key'],
                'Content-Type': 'application/json',
            }

            params = {
                'includeChildren': 'true',
                'start': start_from.strftime(
                    '%Y-%m-%dT%H:%M:%S.000Z'
                ),
                'end': datetime.utcnow().strftime(
                    '%Y-%m-%dT%H:%M:%S.000Z'
                ),
            }

            _logger.info(
                "🌐 API events GET %s start=%s end=%s "
                "includeChildren=true",
                url,
                params['start'],
                params['end'],
            )

            resp = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=cfg['timeout'],
            )

            _logger.info(
                "🌐 API events HTTP=%s url=%s",
                resp.status_code,
                resp.url,
            )

            if resp.status_code != 200:
                _logger.error(
                    "❌ API events HTTP=%s response=%s",
                    resp.status_code,
                    resp.text[:1000],
                )
                return []

            try:
                data = resp.json()
            except ValueError:
                _logger.error(
                    "❌ API events devolvió JSON inválido: %s",
                    resp.text[:1000],
                )
                return []

            if not isinstance(data, list):
                _logger.error(
                    "❌ API events respuesta inesperada tipo=%s "
                    "contenido=%s",
                    type(data).__name__,
                    str(data)[:1000],
                )
                return []

            events = data

            _logger.info(
                "📥 API events recibidos=%s",
                len(events),
            )

            # Compatibilidad interna: el filtro se hace localmente porque
            # resolutionStatus NO está documentado como query parameter.
            if resolution_status:
                wanted = str(
                    resolution_status
                ).strip().lower()

                if wanted == 'closed':
                    accepted = {'resolved', 'closed'}
                elif wanted == 'resolved':
                    accepted = {'resolved', 'closed'}
                else:
                    accepted = {wanted}

                events = [
                    event
                    for event in events
                    if str(
                        event.get('resolutionStatus') or ''
                    ).strip().lower() in accepted
                ]

            if solo_nuevos:
                events = [
                    event
                    for event in events
                    if (
                        event.get('id')
                        and not self._event_ya_procesado(
                            event.get('id')
                        )
                    )
                ]

            _logger.info(
                "📋 API events después de filtros=%s "
                "(status=%s solo_nuevos=%s)",
                len(events),
                resolution_status or 'todos',
                solo_nuevos,
            )

            return events

        except requests.exceptions.Timeout:
            _logger.error(
                "❌ Timeout consultando API events"
            )
            return []

        except requests.exceptions.RequestException as e:
            _logger.error(
                "❌ Error HTTP consultando API events: %s",
                e,
            )
            return []

        except Exception as e:
            _logger.error(
                f"❌ Error API events: "
                f"{e}\n{traceback.format_exc()}"
            )
            return []

    def _event_ya_procesado(self, event_id):
        """Verifica si ya existe alerta local para ese event_id."""
        try:
            return bool(
                self.env['printtracker.alert'].search([('api_event_id', '=', event_id)], limit=1)
            )
        except Exception:
            return False

    # ==========================================
    # INTERFAZ MANUAL
    # ==========================================
    def action_ejecutar_manual(self):
        """Permite ejecutar la revisión manualmente desde la UI."""
        self.ensure_one()
        try:
            self.ejecutar_revision_completa()

            msg = (
                f"✅ Revisión completada\n\n"
                f"• Alertas nuevas: {self.alertas_nuevas}\n"
                f"• Alertas reenviadas (3h+): {self.alertas_reenviadas}\n"
                f"• Auto-cerradas: {self.alertas_cerradas}\n"
                f"• Correos enviados: {self.notificaciones_enviadas}\n"
                f"• Tiempo: {self.tiempo_ejecucion:.2f}s\n"
                f"• Errores: {self.errores_encontrados}"
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Alertas PrintTracker',
                    'message': msg,
                    'type': 'success' if not self.errores_encontrados else 'warning',
                    'sticky': True,
                },
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'message': f'❌ {e}', 'type': 'danger'},
            }

    def action_view_log(self):
        """Abre el log en una ventana modal."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Log de Alertas',
            'res_model': 'printtracker.alert.manager',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    # ==========================================
    # UTILIDADES CRON
    # ==========================================
    @api.model
    def limpiar_alertas_resueltas(self):
        """Cron opcional para limpiar alertas resueltas antiguas."""
        try:
            return self.env['printtracker.alert'].limpiar_alertas_antiguas(30)
        except Exception:
            return 0

    @api.model
    def obtener_dashboard_alertas(self):
        """Resumen rápido para dashboard."""
        try:
            aa = self.env['printtracker.alert'].search([
                ('origen_datos', '=', 'api_events'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
            ])
            cp = self.env['ir.config_parameter'].sudo()
            return {
                'alertas_por_prioridad': {
                    p: len(aa.filtered(lambda a, pr=p: a.prioridad == pr))
                    for p in ['urgente', 'critica', 'alta', 'media', 'baja']
                },
                'total_activas': len(aa),
                'equipos_con_problemas': len(set(aa.mapped('serie_equipo'))),
                'email_soporte': cp.get_param(
                    'printtracker.alert.email_destino', 'soporte@andescopiers.com.pe'
                ),
                'ultima_revision': datetime.now().strftime('%H:%M:%S'),
            }
        except Exception:
            return {}
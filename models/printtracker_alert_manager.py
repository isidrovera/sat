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
#   4. Cuando el event pasa a resolutionStatus=Closed, marca la alerta local como 'resuelta'.
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
        """Retorna set de series de equipos con contrato activo."""
        equipos = self.env['alquiler'].search([
            ('estado_alquiler_id', '=', 'alquilada'),
        ])
        series = set(equipos.mapped('serie'))
        series.discard(False)
        return series

    # ==========================================
    # CRON - CADA 5 MINUTOS
    # ==========================================
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
        Crea alerta para cada event nuevo de equipo alquilado y envía correo inmediato.
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

            log_lines.append(f"📋 Equipos alquilados monitoreados: {len(series_ok)}")

            # Ventana de consulta: últimas HORAS_API_EVENTS
            start_from = datetime.utcnow() - timedelta(hours=HORAS_API_EVENTS)
            events = self._consultar_printtracker_events(api_config, start_from)

            if not events:
                log_lines.append("ℹ️ Sin events en la ventana consultada")
                return {
                    'alertas_nuevas': 0,
                    'notificaciones': 0,
                    'log': log_lines,
                    'ultimo_event_id': None,
                }

            # Filtrar solo equipos alquilados
            relevantes = [e for e in events if e.get('deviceSerialNumber', '') in series_ok]
            ignorados = len(events) - len(relevantes)

            log_lines.append(
                f"📋 {len(relevantes)} events relevantes ({ignorados} de equipos no alquilados)"
            )

            for event in relevantes:
                try:
                    eid = event.get('id')
                    serial = event.get('deviceSerialNumber', 'N/A')
                    desc = (event.get('description', 'N/A'))[:80]

                    # Dedup: si ya existe alerta para este event_id, omitir
                    if self._event_ya_procesado(eid):
                        continue

                    alerta = self.env['printtracker.alert'].crear_alerta_desde_api_event(
                        event, serial
                    )
                    if alerta:
                        alertas_nuevas += 1
                        ultimo_event_id = eid
                        log_lines.append(f"🆕 {serial}: {desc}")

                        # Enviar correo INMEDIATO para toda alerta nueva
                        alerta.procesar_notificaciones()
                        if alerta.email_enviado:
                            notificaciones += 1

                except Exception as e:
                    log_lines.append(f"❌ Event {event.get('id', '?')}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(
                f"✅ {alertas_nuevas} alertas nuevas, {notificaciones} correos inmediatos"
            )
            return {
                'alertas_nuevas': alertas_nuevas,
                'notificaciones': notificaciones,
                'log': log_lines,
                'ultimo_event_id': ultimo_event_id,
            }

        except Exception as e:
            _logger.error(f"❌ Error detección: {e}\n{traceback.format_exc()}")
            return {
                'alertas_nuevas': 0,
                'notificaciones': 0,
                'log': [f"❌ {e}"],
                'ultimo_event_id': None,
            }

    # ==========================================
    # FASE 2: AUTO-CERRAR ALERTAS RESUELTAS EN PRINTTRACKER
    # ==========================================
    def _auto_cerrar_alertas_resueltas(self):
        """
        Consulta events con resolutionStatus=Closed y cierra las alertas locales.
        Refleja el estado actual de PrintTracker sin intervención manual.
        """
        try:
            log_lines = []
            cerradas = 0

            api_config = self._get_printtracker_api_config()
            if not api_config:
                log_lines.append("❌ Config API no encontrada")
                return {'cerradas': 0, 'log': log_lines}

            # Buscar alertas locales aún activas originadas en API
            alertas_activas = self.env['printtracker.alert'].search([
                ('origen_datos', '=', 'api_events'),
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso']),
                ('api_event_id', '!=', False),
            ])

            if not alertas_activas:
                log_lines.append("ℹ️ Sin alertas activas de origen API")
                return {'cerradas': 0, 'log': log_lines}

            log_lines.append(f"📋 {len(alertas_activas)} alertas activas a verificar")

            # Consultar events Closed recientes
            start_from = datetime.utcnow() - timedelta(hours=HORAS_API_EVENTS)
            events_closed = self._consultar_printtracker_events(
                api_config, start_from, resolution_status='Closed', solo_nuevos=False
            )

            if not events_closed:
                log_lines.append("ℹ️ Sin events Closed en la ventana")
                return {'cerradas': 0, 'log': log_lines}

            # Indexar por event id para lookup rápido
            closed_ids = {e.get('id') for e in events_closed if e.get('id')}
            log_lines.append(f"📋 {len(closed_ids)} events Closed recibidos de la API")

            for alerta in alertas_activas:
                try:
                    if alerta.api_event_id in closed_ids:
                        alerta.write({
                            'estado': 'resuelta',
                            'api_resolution_status': 'Closed',
                            'fecha_resolucion': fields.Datetime.now(),
                            'notas_resolucion': 'Auto-cerrada: event resuelto en PrintTracker',
                        })
                        cerradas += 1
                        log_lines.append(
                            f"✅ Cerrada: {alerta.serie_equipo} (event {alerta.api_event_id})"
                        )
                except Exception as e:
                    log_lines.append(f"❌ Error cerrando {alerta.display_name}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {cerradas} alertas auto-cerradas")
            return {'cerradas': cerradas, 'log': log_lines}

        except Exception as e:
            _logger.error(f"❌ Error auto-cierre: {e}\n{traceback.format_exc()}")
            return {'cerradas': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # FASE 3: REENVIAR ALERTAS PENDIENTES CADA 3H
    # ==========================================
    def _reenviar_alertas_pendientes(self):
        """
        Reenvía correo para alertas aún activas cuyo último envío fue hace >= 3h.
        Usa ultima_revision como timestamp del último envío.
        """
        try:
            log_lines = []
            reenviadas = 0

            corte = fields.Datetime.now() - timedelta(hours=HORAS_REENVIO)

            alertas = self.env['printtracker.alert'].search([
                ('origen_datos', '=', 'api_events'),
                ('estado', 'in', ['notificada', 'en_proceso']),
                ('email_enviado', '=', True),
                '|',
                ('ultima_revision', '=', False),
                ('ultima_revision', '<=', corte),
            ])

            if not alertas:
                log_lines.append(
                    f"ℹ️ Sin alertas pendientes de reenvío (umbral {HORAS_REENVIO}h)"
                )
                return {'reenviadas': 0, 'log': log_lines}

            log_lines.append(
                f"📧 {len(alertas)} alertas a reenviar (>= {HORAS_REENVIO}h sin envío)"
            )

            for alerta in alertas:
                try:
                    # Forzar reenvío: resetear email_enviado y llamar al método estándar
                    alerta.write({
                        'email_enviado': False,
                        'contador_repeticiones': alerta.contador_repeticiones + 1,
                        'ultima_revision': fields.Datetime.now(),
                    })
                    alerta._enviar_notificacion_email()

                    if alerta.email_enviado:
                        reenviadas += 1
                        log_lines.append(
                            f"📧 Reenvío #{alerta.contador_repeticiones}: "
                            f"{alerta.serie_equipo} - {alerta.tipo_alerta}"
                        )
                except Exception as e:
                    log_lines.append(f"❌ Error reenvío {alerta.display_name}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {reenviadas} correos de reenvío enviados")
            return {'reenviadas': reenviadas, 'log': log_lines}

        except Exception as e:
            _logger.error(f"❌ Error reenvíos: {e}\n{traceback.format_exc()}")
            return {'reenviadas': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # FASE 4: PROCESAR ALERTAS 'NUEVA' HUÉRFANAS
    # ==========================================
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

    def _consultar_printtracker_events(self, cfg, start_from, resolution_status=None, solo_nuevos=True):
        """
        Consulta GET /v1/entity/{id}/events.
        Si resolution_status se especifica, filtra por ese estado (Open/Closed).
        Si solo_nuevos=True, devuelve solo los que no tienen alerta local previa.
        """
        try:
            url = f"{cfg['base_url']}/entity/{cfg['entity_id']}/events"
            headers = {'x-api-key': cfg['api_key'], 'Content-Type': 'application/json'}
            params = {
                'limit': 100,
                'page': 1,
                'includeChildren': 'true',
                'start': start_from.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                'end': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            }
            if resolution_status:
                params['resolutionStatus'] = resolution_status

            _logger.info(
                f"🌐 API events: {url} desde {params['start']} "
                f"(status={resolution_status or 'todos'})"
            )
            resp = requests.get(url, headers=headers, params=params, timeout=cfg['timeout'])

            if resp.status_code == 200:
                data = resp.json()
                events = data if isinstance(data, list) else []

                if solo_nuevos:
                    events = [
                        e for e in events
                        if e.get('id') and not self._event_ya_procesado(e['id'])
                    ]

                _logger.info(f"📋 {len(events)} events (status={resolution_status or 'todos'})")
                return events
            else:
                _logger.error(f"❌ API {resp.status_code}: {resp.text[:200]}")
                return []

        except requests.exceptions.Timeout:
            _logger.error("❌ Timeout API")
            return []
        except Exception as e:
            _logger.error(f"❌ Error API: {e}")
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
# ================================================================================================
# MODELO: printtracker_alert_manager.py - Gestor de Alertas PrintTracker
# Solo equipos con estado_alquiler_id = 'alquilada' (contratos activos)
# Offline máximo 30 días, API events últimas 24 horas
# Email configurable a soporte@andescopiers.com.pe
# ================================================================================================

from odoo import models, fields, api
import logging
import traceback
from datetime import datetime, timedelta, date
import json
import requests

_logger = logging.getLogger(__name__)

# Máximo días offline para alertar (más allá se ignora)
MAX_DIAS_OFFLINE = 30

# Horas hacia atrás para consultar events de la API
HORAS_API_EVENTS = 24


class PrintTrackerAlertManager(models.TransientModel):
    _name = 'printtracker.alert.manager'
    _description = 'Gestor de Alertas PrintTracker'

    # ==========================================
    # CAMPOS DE CONFIGURACIÓN
    # ==========================================
    revisar_suministros = fields.Boolean('Revisar Suministros', default=True)
    revisar_equipos_offline = fields.Boolean('Revisar Equipos Offline', default=True)
    revisar_uso_anomalo = fields.Boolean('Revisar Uso Anómalo', default=True)
    revisar_contadores_decrecen = fields.Boolean('Revisar Contadores que Decrecen', default=True)
    revisar_api_events = fields.Boolean('Revisar Events de API', default=True)

    umbral_suministro_bajo = fields.Float('Umbral Suministro Bajo (%)', default=15.0)
    umbral_suministro_critico = fields.Float('Umbral Suministro Crítico (%)', default=5.0)
    dias_offline_alerta = fields.Integer('Días Offline para Alerta', default=3)
    dias_offline_critico = fields.Integer('Días Offline Crítico', default=7)

    # ==========================================
    # RESULTADOS DE EJECUCIÓN
    # ==========================================
    alertas_suministros = fields.Integer('Alertas de Suministros', readonly=True)
    alertas_offline = fields.Integer('Alertas de Equipos Offline', readonly=True)
    alertas_uso_anomalo = fields.Integer('Alertas de Uso Anómalo', readonly=True)
    alertas_contadores = fields.Integer('Alertas de Contadores', readonly=True)
    alertas_api_events = fields.Integer('Alertas de API Events', readonly=True)
    notificaciones_enviadas = fields.Integer('Notificaciones Enviadas', readonly=True)
    errores_encontrados = fields.Integer('Errores Encontrados', readonly=True)
    ultimo_event_procesado = fields.Char('Último Event ID Procesado', readonly=True)
    tiempo_ejecucion = fields.Float('Tiempo de Ejecución (seg)', readonly=True)
    log_ejecucion = fields.Text('Log de Ejecución', readonly=True)

    # ==========================================
    # HELPER: EQUIPOS ALQUILADOS ACTIVOS
    # ==========================================
    def _get_equipos_alquilados(self):
        """Retorna recordset de equipos con estado 'alquilada'."""
        equipos = self.env['alquiler'].search([
            ('estado_alquiler_id', '=', 'alquilada'),
        ])
        _logger.info(f"📋 Equipos alquilados activos: {len(equipos)}")
        return equipos

    def _get_series_alquilados(self):
        """Retorna set de series de equipos alquilados."""
        equipos = self._get_equipos_alquilados()
        series = set(equipos.mapped('serie'))
        series.discard(False)
        return series

    # ==========================================
    # CRON - CADA 5 MINUTOS
    # ==========================================
    @api.model
    def ejecutar_revision_automatica(self):
        """Ejecutado por cron. Solo equipos alquilados."""
        try:
            _logger.info("🚨 === REVISIÓN AUTOMÁTICA (solo alquilados) ===")

            alert_manager = self.create({
                'revisar_suministros': True,
                'revisar_equipos_offline': True,
                'revisar_uso_anomalo': True,
                'revisar_contadores_decrecen': True,
                'revisar_api_events': True,
            })

            resultado = alert_manager.ejecutar_revision_completa()

            if resultado:
                total = (
                    alert_manager.alertas_suministros + alert_manager.alertas_offline +
                    alert_manager.alertas_uso_anomalo + alert_manager.alertas_contadores +
                    alert_manager.alertas_api_events
                )
                _logger.info(f"✅ Completado: {total} alertas, {alert_manager.notificaciones_enviadas} notificaciones")
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
        """Ejecuta las 5 revisiones + notificaciones."""
        try:
            inicio = datetime.now()
            log_lines = [
                "🚨 === INICIANDO REVISIÓN DE ALERTAS ===",
                f"⏰ {inicio.strftime('%Y-%m-%d %H:%M:%S')}",
                "🔍 Filtro: Solo equipos con estado 'Alquilada'",
                "",
            ]
            total_alertas = 0
            total_notif = 0

            revisiones = [
                (self.revisar_suministros, "🎨 === SUMINISTROS ===", self._revisar_suministros_bajos, 'alertas_suministros'),
                (self.revisar_equipos_offline, "📵 === EQUIPOS OFFLINE ===", self._revisar_equipos_offline, 'alertas_offline'),
                (self.revisar_uso_anomalo, "📊 === USO ANÓMALO ===", self._revisar_uso_anomalo, 'alertas_uso_anomalo'),
                (self.revisar_contadores_decrecen, "⬇️ === CONTADORES ===", self._revisar_contadores_decrecen, 'alertas_contadores'),
                (self.revisar_api_events, "📋 === API EVENTS ===", self._revisar_api_events, 'alertas_api_events'),
            ]

            for activa, titulo, metodo, campo in revisiones:
                if activa:
                    log_lines.append(titulo)
                    resultado = metodo()
                    log_lines.extend(resultado['log'])
                    setattr(self, campo, resultado['alertas'])
                    total_alertas += resultado['alertas']
                    total_notif += resultado['notificaciones']
                    if campo == 'alertas_api_events':
                        self.ultimo_event_procesado = resultado.get('ultimo_event_id', '')
                    log_lines.append("")

            # Notificaciones pendientes
            log_lines.append("📬 === NOTIFICACIONES ===")
            res_notif = self._procesar_notificaciones_pendientes()
            log_lines.extend(res_notif['log'])
            total_notif += res_notif['notificaciones']
            self.notificaciones_enviadas = total_notif

            # Estadísticas
            tiempo = (datetime.now() - inicio).total_seconds()
            self.tiempo_ejecucion = tiempo

            log_lines.extend([
                "📊 === ESTADÍSTICAS ===",
                f"⏱️ Tiempo: {tiempo:.2f}s",
                f"🎨 Suministros: {self.alertas_suministros}",
                f"📵 Offline: {self.alertas_offline}",
                f"📊 Uso anómalo: {self.alertas_uso_anomalo}",
                f"⬇️ Contadores: {self.alertas_contadores}",
                f"📋 API events: {self.alertas_api_events}",
                f"🚨 Total: {total_alertas}",
                f"📬 Notificaciones: {total_notif}",
                f"❌ Errores: {self.errores_encontrados}",
            ])
            if self.ultimo_event_procesado:
                log_lines.append(f"🆔 Último event: {self.ultimo_event_procesado}")
            log_lines.extend(["", "✅ === COMPLETADO ==="])

            self.log_ejecucion = "\n".join(log_lines)
            return True

        except Exception as e:
            _logger.error(f"❌ Error revisión: {e}\n{traceback.format_exc()}")
            self.log_ejecucion = (self.log_ejecucion or "") + f"\n❌ {e}"
            self.errores_encontrados = (self.errores_encontrados or 0) + 1
            return False

    # ==========================================
    # REV 1: SUMINISTROS (solo alquilados)
    # ==========================================
    def _revisar_suministros_bajos(self):
        try:
            log_lines = []
            alertas = 0
            notif = 0

            equipo_ids = self._get_equipos_alquilados().ids
            if not equipo_ids:
                log_lines.append("ℹ️ Sin equipos alquilados")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            suministros = self.env['printtracker.supply'].search([
                ('device_id', 'in', equipo_ids),
                ('is_active', '=', True),
                ('is_replaced', '=', False),
                '|',
                ('percent_remaining', '<=', self.umbral_suministro_bajo),
                ('percent_remaining', '=', 0),
            ])

            log_lines.append(f"🎨 {len(suministros)} suministros bajos (de {len(equipo_ids)} equipos)")

            for s in suministros:
                try:
                    serial = s.device_id.serie if s.device_id else 'N/A'
                    alerta = self.env['printtracker.alert'].crear_alerta_suministro_bajo(s)
                    if alerta:
                        alertas += 1
                        log_lines.append(f"🚨 {serial} - {s.supply_type} ({s.percent_remaining:.1f}%)")
                        if s.percent_remaining <= self.umbral_suministro_critico:
                            alerta.procesar_notificaciones()
                            notif += 1
                except Exception as e:
                    log_lines.append(f"❌ {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {alertas} alertas, {notif} notificaciones")
            return {'alertas': alertas, 'notificaciones': notif, 'log': log_lines}

        except Exception as e:
            return {'alertas': 0, 'notificaciones': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # REV 2: OFFLINE (alquilados + máx 30 días)
    # ==========================================
    def _revisar_equipos_offline(self):
        try:
            log_lines = []
            alertas = 0
            notif = 0

            series_ok = self._get_series_alquilados()
            if not series_ok:
                log_lines.append("ℹ️ Sin equipos alquilados")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            todos_offline = self.env['printtracker.meter'].get_devices_without_recent_readings(
                days=self.dias_offline_alerta
            )

            # FILTRAR: solo alquilados + máximo MAX_DIAS_OFFLINE
            filtrados = []
            ignorados = 0
            for info in todos_offline:
                serie = info.get('serie')
                dias = info.get('days_offline', 0)
                if serie not in series_ok or dias > MAX_DIAS_OFFLINE:
                    ignorados += 1
                    continue
                filtrados.append(info)

            log_lines.append(
                f"📵 {len(filtrados)} offline relevantes "
                f"({ignorados} ignorados: no alquilados o > {MAX_DIAS_OFFLINE} días)"
            )

            for info in filtrados:
                try:
                    serie = info['serie']
                    dias = info['days_offline']
                    ultima = info['last_reading']

                    alerta = self.env['printtracker.alert'].crear_alerta_equipo_offline(serie, dias, ultima)
                    if alerta:
                        alertas += 1
                        log_lines.append(f"📵 {serie} ({dias} días)")
                        if dias >= self.dias_offline_critico:
                            alerta.procesar_notificaciones()
                            notif += 1
                except Exception as e:
                    log_lines.append(f"❌ {info.get('serie', '?')}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {alertas} alertas, {notif} notificaciones")
            return {'alertas': alertas, 'notificaciones': notif, 'log': log_lines}

        except Exception as e:
            return {'alertas': 0, 'notificaciones': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # REV 3: USO ANÓMALO (solo alquilados)
    # ==========================================
    def _revisar_uso_anomalo(self):
        try:
            log_lines = []
            alertas = 0

            series_ok = self._get_series_alquilados()
            if not series_ok:
                log_lines.append("ℹ️ Sin equipos alquilados")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            fecha_ayer = date.today() - timedelta(days=1)

            lecturas = self.env['printtracker.daily.reading'].search([
                ('fecha', '=', fecha_ayer),
                ('estado', '=', 'aplicado'),
                ('serie', 'in', list(series_ok)),
            ])

            log_lines.append(f"📊 {len(lecturas)} lecturas de equipos alquilados")

            for lec in lecturas:
                try:
                    serie = lec.serie
                    hist = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '>=', fecha_ayer - timedelta(days=7)),
                        ('fecha', '<', fecha_ayer),
                        ('estado', '=', 'aplicado'),
                    ])
                    if len(hist) < 3:
                        continue

                    incs = [l.incremento_total for l in hist if l.incremento_total > 0]
                    if not incs:
                        continue

                    prom = sum(incs) / len(incs)
                    inc_ayer = lec.incremento_total

                    if inc_ayer > prom * 3 and inc_ayer > 1000:
                        a = self.env['printtracker.alert'].crear_alerta_uso_anomalo(
                            serie, 'alto', lec.contador_total, lec.contador_total - inc_ayer)
                        if a:
                            alertas += 1
                            log_lines.append(f"📈 {serie} ({inc_ayer:,} vs {prom:.0f})")

                    elif inc_ayer < prom * 0.3 and prom > 100:
                        a = self.env['printtracker.alert'].crear_alerta_uso_anomalo(
                            serie, 'bajo', lec.contador_total, lec.contador_total - inc_ayer)
                        if a:
                            alertas += 1
                            log_lines.append(f"📉 {serie} ({inc_ayer:,} vs {prom:.0f})")

                except Exception as e:
                    log_lines.append(f"❌ {lec.serie}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {alertas} alertas")
            return {'alertas': alertas, 'notificaciones': 0, 'log': log_lines}

        except Exception as e:
            return {'alertas': 0, 'notificaciones': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # REV 4: CONTADORES DECRECEN (solo alquilados)
    # ==========================================
    def _revisar_contadores_decrecen(self):
        try:
            log_lines = []
            alertas = 0
            notif = 0

            series_ok = self._get_series_alquilados()
            if not series_ok:
                log_lines.append("ℹ️ Sin equipos alquilados")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            fecha_ayer = date.today() - timedelta(days=1)
            fecha_ante = date.today() - timedelta(days=2)

            lecturas = self.env['printtracker.daily.reading'].search([
                ('fecha', '=', fecha_ayer),
                ('estado', '=', 'aplicado'),
                ('serie', 'in', list(series_ok)),
            ])

            log_lines.append(f"⬇️ {len(lecturas)} lecturas de equipos alquilados")

            for lec in lecturas:
                try:
                    serie = lec.serie
                    lec_ante = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '=', fecha_ante),
                        ('estado', '=', 'aplicado'),
                    ], limit=1)

                    if not lec_ante:
                        continue

                    decs = []
                    if lec.contador_bn < lec_ante.contador_bn - 100:
                        decs.append(('B/N', lec.contador_bn, lec_ante.contador_bn,
                                     lec_ante.contador_bn - lec.contador_bn))
                    if lec.contador_color < lec_ante.contador_color - 100:
                        decs.append(('Color', lec.contador_color, lec_ante.contador_color,
                                     lec_ante.contador_color - lec.contador_color))
                    if lec.contador_scan < lec_ante.contador_scan - 50:
                        decs.append(('Scan', lec.contador_scan, lec_ante.contador_scan,
                                     lec_ante.contador_scan - lec.contador_scan))

                    for tipo, actual, anterior, dif in decs:
                        a = self.env['printtracker.alert'].crear_alerta_contador_decrece(
                            serie, tipo, actual, anterior)
                        if a:
                            alertas += 1
                            log_lines.append(f"⬇️ {serie} - {tipo} ({anterior:,} → {actual:,})")
                            if dif > 10000:
                                a.procesar_notificaciones()
                                notif += 1

                except Exception as e:
                    log_lines.append(f"❌ {lec.serie}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {alertas} alertas, {notif} notificaciones")
            return {'alertas': alertas, 'notificaciones': notif, 'log': log_lines}

        except Exception as e:
            return {'alertas': 0, 'notificaciones': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # REV 5: API EVENTS (24h + solo alquilados)
    # GET /v1/entity/{entityId}/events
    # ==========================================
    def _revisar_api_events(self):
        try:
            log_lines = []
            alertas = 0
            notif = 0
            ultimo_id = None

            api_config = self._get_printtracker_api_config()
            if not api_config:
                log_lines.append("❌ Config API no encontrada")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            series_ok = self._get_series_alquilados()
            if not series_ok:
                log_lines.append("ℹ️ Sin equipos alquilados")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            # Desde cuándo consultar
            ultimo_ts = self._get_ultimo_event_timestamp()
            limite = datetime.utcnow() - timedelta(hours=HORAS_API_EVENTS)
            start_from = ultimo_ts if (ultimo_ts and ultimo_ts > limite) else limite

            events = self._consultar_printtracker_events(api_config, start_from)

            if not events:
                log_lines.append("ℹ️ Sin events nuevos")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            # Filtrar solo equipos alquilados
            relevantes = [e for e in events if e.get('deviceSerialNumber', '') in series_ok]
            ignorados = len(events) - len(relevantes)

            log_lines.append(f"📋 {len(relevantes)} events de alquilados ({ignorados} ignorados)")

            for event in relevantes:
                try:
                    eid = event.get('id')
                    serial = event.get('deviceSerialNumber', 'N/A')
                    desc = (event.get('description', 'N/A'))[:80]

                    if self._event_ya_procesado(eid):
                        continue

                    alerta = self.env['printtracker.alert'].crear_alerta_desde_api_event(event, serial)
                    if alerta:
                        alertas += 1
                        ultimo_id = eid
                        if self._event_requiere_notificacion_inmediata(event):
                            alerta.procesar_notificaciones()
                            notif += 1
                        log_lines.append(f"📋 {serial}: {desc}")

                except Exception as e:
                    log_lines.append(f"❌ Event {event.get('id', '?')}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {alertas} alertas, {notif} notificaciones")
            return {'alertas': alertas, 'notificaciones': notif, 'ultimo_event_id': ultimo_id, 'log': log_lines}

        except Exception as e:
            return {'alertas': 0, 'notificaciones': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # AUXILIARES API
    # ==========================================
    def _get_printtracker_api_config(self):
        try:
            entity = self.env['printtracker.entity'].search([('is_active', '=', True)], limit=1)
            cp = self.env['ir.config_parameter'].sudo()
            base = cp.get_param('printtracker.api.base_url', 'https://papi.printtrackerpro.com/v1')

            if entity and entity.entity_id:
                token = getattr(entity, 'api_token', None) or cp.get_param('printtracker.api.key')
                if token:
                    return {'base_url': base.rstrip('/'), 'entity_id': entity.entity_id, 'api_key': token, 'timeout': 30}

            eid = cp.get_param('printtracker.api.entity_id')
            key = cp.get_param('printtracker.api.key')
            if eid and key:
                return {'base_url': base.rstrip('/'), 'entity_id': eid, 'api_key': key, 'timeout': 30}

            return None
        except Exception as e:
            _logger.error(f"❌ Config API: {e}")
            return None

    def _get_ultimo_event_timestamp(self):
        try:
            a = self.env['printtracker.alert'].search([
                ('origen_datos', '=', 'api_events'),
                ('api_event_timestamp', '!=', False),
            ], order='api_event_timestamp desc', limit=1)
            return a.api_event_timestamp if a else None
        except Exception:
            return None

    def _consultar_printtracker_events(self, cfg, start_from):
        try:
            url = f"{cfg['base_url']}/entity/{cfg['entity_id']}/events"
            headers = {'Authorization': f"Bearer {cfg['api_key']}", 'Content-Type': 'application/json'}
            params = {
                'limit': 100, 'page': 1, 'includeChildren': 'true',
                'start': start_from.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                'end': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            }

            _logger.info(f"🌐 API events: {url} (desde {params['start']})")
            resp = requests.get(url, headers=headers, params=params, timeout=cfg['timeout'])

            if resp.status_code == 200:
                data = resp.json()
                events = data if isinstance(data, list) else []
                nuevos = [e for e in events if e.get('id') and not self._event_ya_procesado(e['id'])]
                _logger.info(f"📋 {len(events)} totales, {len(nuevos)} nuevos")
                return nuevos
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
        try:
            return bool(self.env['printtracker.alert'].search([('api_event_id', '=', event_id)], limit=1))
        except Exception:
            return False

    def _event_requiere_notificacion_inmediata(self, event):
        try:
            desc = (event.get('description', '')).lower()
            at = event.get('alertType')
            rs = event.get('resolutionStatus', 'Open')

            if any(w in desc for w in ['jam', 'atasco', 'trabamiento']):
                return True
            if any(w in desc for w in ['toner', 'ink']) and any(w in desc for w in ['empty', 'vacio', 'agotado']):
                return True
            if any(w in desc for w in ['error', 'fault', 'codigo']):
                return True
            if any(w in desc for w in ['offline', 'connection']):
                return True
            if rs == 'Open' and at:
                return True
            return False
        except Exception:
            return False

    # ==========================================
    # NOTIFICACIONES PENDIENTES
    # ==========================================
    def _procesar_notificaciones_pendientes(self):
        try:
            log_lines = []
            enviadas = 0

            pendientes = self.env['printtracker.alert'].search([
                ('estado', '=', 'nueva'),
                ('fecha_creacion', '>=', datetime.now() - timedelta(minutes=10)),
            ])
            log_lines.append(f"📬 {len(pendientes)} pendientes")

            for a in pendientes:
                try:
                    a.procesar_notificaciones()
                    if a.estado == 'notificada':
                        enviadas += 1
                        log_lines.append(f"📧 {a.display_name}")
                except Exception as e:
                    log_lines.append(f"❌ {a.display_name}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ {enviadas} enviadas")
            return {'notificaciones': enviadas, 'log': log_lines}
        except Exception as e:
            return {'notificaciones': 0, 'log': [f"❌ {e}"]}

    # ==========================================
    # INTERFAZ
    # ==========================================
    def action_ejecutar_manual(self):
        self.ensure_one()
        try:
            self.ejecutar_revision_completa()
            total = (self.alertas_suministros + self.alertas_offline +
                     self.alertas_uso_anomalo + self.alertas_contadores + self.alertas_api_events)

            msg = (
                f"✅ Revisión completada (solo equipos alquilados)\n\n"
                f"• Suministros: {self.alertas_suministros}\n"
                f"• Offline: {self.alertas_offline}\n"
                f"• Uso anómalo: {self.alertas_uso_anomalo}\n"
                f"• Contadores: {self.alertas_contadores}\n"
                f"• API events: {self.alertas_api_events}\n"
                f"• Total: {total} | Notificaciones: {self.notificaciones_enviadas}\n"
                f"• Tiempo: {self.tiempo_ejecucion:.2f}s | Errores: {self.errores_encontrados}"
            )
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Alertas PrintTracker', 'message': msg,
                           'type': 'success' if not self.errores_encontrados else 'warning', 'sticky': True},
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': f'❌ {e}', 'type': 'danger'},
            }

    def action_view_log(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'Log de Alertas',
            'res_model': 'printtracker.alert.manager', 'res_id': self.id,
            'view_mode': 'form', 'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    @api.model
    def limpiar_alertas_resueltas(self):
        try:
            return self.env['printtracker.alert'].limpiar_alertas_antiguas(30)
        except Exception:
            return 0

    @api.model
    def obtener_dashboard_alertas(self):
        try:
            aa = self.env['printtracker.alert'].search([('estado', 'in', ['nueva', 'notificada', 'en_proceso'])])
            cp = self.env['ir.config_parameter'].sudo()
            return {
                'alertas_por_prioridad': {p: len(aa.filtered(lambda a, pr=p: a.prioridad == pr))
                                          for p in ['urgente', 'critica', 'alta', 'media', 'baja']},
                'total_activas': len(aa),
                'equipos_con_problemas': len(set(aa.mapped('serie_equipo'))),
                'email_soporte': cp.get_param('printtracker.alert.email_destino', 'soporte@andescopiers.com.pe'),
                'ultima_revision': datetime.now().strftime('%H:%M:%S'),
            }
        except Exception:
            return {}
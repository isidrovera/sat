# -*- coding: utf-8 -*-

import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SatSatPruebasDashboard(models.Model):
    _inherit = 'sat.sat'

    prueba_tecnica_dashboard_json = fields.Text(
        string='Dashboard Pruebas Técnicas',
        compute='_compute_prueba_tecnica_dashboard_json',
        readonly=True,
    )

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _sat_dashboard_int(self, value):
        try:
            if value in (None, False, ''):
                return 0
            return int(float(value))
        except Exception:
            return 0

    def _sat_dashboard_float(self, value):
        try:
            if value in (None, False, ''):
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    def _sat_dashboard_selection_label(self, model_name, field_name, value):
        try:
            field = self.env[model_name]._fields.get(field_name)
            if not field or not getattr(field, 'selection', None):
                return value or ''
            return dict(field.selection).get(value, value or '')
        except Exception:
            return value or ''

    def _sat_dashboard_datetime_text(self, value):
        if not value:
            return ''
        try:
            return fields.Datetime.to_string(value)
        except Exception:
            return str(value)

    def _sat_dashboard_es_color(self):
        self.ensure_one()

        tipo = self.tipo_id or ''
        tipo_text = (self.tipo_maquina or '').lower()
        modelo_text = ''
        marca_text = ''

        try:
            modelo_text = (self.name.name or '').lower() if self.name else ''
        except Exception:
            modelo_text = ''

        try:
            marca_text = (self.marca or '').lower()
        except Exception:
            marca_text = ''

        texto = '%s %s %s %s' % (
            tipo.lower(),
            tipo_text,
            modelo_text,
            marca_text,
        )

        # Regla principal: campo selection del modelo
        if tipo == 'color':
            return True

        if tipo == 'monocromatica':
            return False

        # Respaldo por texto, por si algún registro antiguo no tiene tipo_id bien lleno
        palabras_color = [
            'color',
            'colour',
            'full color',
            'c color',
            'bizhub c',
            'mp c',
            'ir-adv c',
            'im c',
        ]

        palabras_bn = [
            'monocromatica',
            'monocromático',
            'monochrome',
            'blanco y negro',
            'b/n',
            'bn',
            'black',
            'mp 501',
            'mp 301',
            'ir ',
        ]

        for palabra in palabras_color:
            if palabra in texto:
                return True

        for palabra in palabras_bn:
            if palabra in texto:
                return False

        # Si no se puede saber, asumimos B/N para no mostrar colores falsos
        return False

    def _sat_dashboard_toner_estado_por_nivel(self, value):
        value = self._sat_dashboard_float(value)
        if value <= 0:
            return 'sin_datos'
        if value <= 10:
            return 'critico'
        if value <= 25:
            return 'bajo'
        return 'ok'

    # ==========================================================
    # COMPUTE JSON DASHBOARD
    # ==========================================================

    @api.depends(
        'name',
        'serie_id',
        'marca',
        'tipo_id',
        'tipo_maquina',
        'prueba_ids',
        'prueba_ids.fecha_inicio',
        'prueba_ids.fecha_ultima_actualizacion',
        'prueba_ids.snmp_ip',
        'prueba_ids.snmp_serie',
        'prueba_ids.snmp_marca',
        'prueba_ids.snmp_modelo',
        'prueba_ids.contador_inicial_total',
        'prueba_ids.contador_actual_total',
        'prueba_ids.contador_actual_bn',
        'prueba_ids.contador_actual_color',
        'prueba_ids.contador_impresiones',
        'prueba_ids.contador_copias',
        'prueba_ids.contador_scanner',
        'prueba_ids.contador_duplex',
        'prueba_ids.delta_total',
        'prueba_ids.delta_bn',
        'prueba_ids.delta_color',
        'prueba_ids.delta_impresiones',
        'prueba_ids.delta_copias',
        'prueba_ids.delta_scanner',
        'prueba_ids.delta_duplex',
        'prueba_ids.toner_negro',
        'prueba_ids.toner_cyan',
        'prueba_ids.toner_magenta',
        'prueba_ids.toner_amarillo',
        'prueba_ids.estado_toner',
        'prueba_ids.estado_prueba',
        'prueba_ids.nivel_prueba',
        'prueba_ids.cantidad_alertas_snmp',
        'prueba_ids.prueba_impresion_ok',
        'prueba_ids.prueba_copia_ok',
        'prueba_ids.prueba_scanner_ok',
        'prueba_ids.prueba_duplex_ok',
        'prueba_ids.prueba_bn_ok',
        'prueba_ids.prueba_color_ok',
    )
    def _compute_prueba_tecnica_dashboard_json(self):
        for rec in self:
            try:
                es_color = rec._sat_dashboard_es_color()

                pruebas = rec.prueba_ids.sorted(
                    key=lambda p: (
                        p.fecha_ultima_actualizacion
                        or p.fecha_inicio
                        or p.create_date
                        or fields.Datetime.now()
                    ),
                    reverse=True,
                )

                items = []

                for prueba in pruebas:
                    toner_negro = rec._sat_dashboard_float(prueba.toner_negro)
                    toner_cyan = rec._sat_dashboard_float(prueba.toner_cyan)
                    toner_magenta = rec._sat_dashboard_float(prueba.toner_magenta)
                    toner_amarillo = rec._sat_dashboard_float(prueba.toner_amarillo)

                    toners_validos = [toner_negro]

                    if es_color:
                        toners_validos += [
                            toner_cyan,
                            toner_magenta,
                            toner_amarillo,
                        ]

                    toners_con_dato = [
                        t for t in toners_validos
                        if t not in (None, False) and float(t) > 0
                    ]

                    toner_minimo = min(toners_con_dato) if toners_con_dato else 0.0

                    estado_toner = prueba.estado_toner or rec._sat_dashboard_toner_estado_por_nivel(toner_minimo)

                    item = {
                        'id': prueba.id,
                        'name': prueba.display_name or ('Prueba #%s' % prueba.id),

                        'fecha_inicio': rec._sat_dashboard_datetime_text(prueba.fecha_inicio),
                        'fecha_ultima_actualizacion': rec._sat_dashboard_datetime_text(
                            prueba.fecha_ultima_actualizacion or prueba.fecha_inicio
                        ),

                        'snmp_ip': prueba.snmp_ip or '',
                        'snmp_serie': prueba.snmp_serie or '',
                        'snmp_marca': prueba.snmp_marca or '',
                        'snmp_modelo': prueba.snmp_modelo or '',

                        'contador_inicial_total': rec._sat_dashboard_int(prueba.contador_inicial_total),
                        'contador_actual_total': rec._sat_dashboard_int(prueba.contador_actual_total),

                        'contador_actual_bn': rec._sat_dashboard_int(prueba.contador_actual_bn),
                        'contador_actual_color': rec._sat_dashboard_int(prueba.contador_actual_color),

                        'contador_impresiones': rec._sat_dashboard_int(prueba.contador_impresiones),
                        'contador_copias': rec._sat_dashboard_int(prueba.contador_copias),
                        'contador_scanner': rec._sat_dashboard_int(prueba.contador_scanner),
                        'contador_duplex': rec._sat_dashboard_int(prueba.contador_duplex),

                        'delta_total': rec._sat_dashboard_int(prueba.delta_total),
                        'delta_bn': rec._sat_dashboard_int(prueba.delta_bn),
                        'delta_color': rec._sat_dashboard_int(prueba.delta_color),
                        'delta_impresiones': rec._sat_dashboard_int(prueba.delta_impresiones),
                        'delta_copias': rec._sat_dashboard_int(prueba.delta_copias),
                        'delta_scanner': rec._sat_dashboard_int(prueba.delta_scanner),
                        'delta_duplex': rec._sat_dashboard_int(prueba.delta_duplex),

                        'toner_negro': toner_negro,
                        'toner_cyan': toner_cyan if es_color else 0.0,
                        'toner_magenta': toner_magenta if es_color else 0.0,
                        'toner_amarillo': toner_amarillo if es_color else 0.0,
                        'toner_minimo': toner_minimo,

                        'estado_toner': estado_toner,
                        'estado_toner_label': rec._sat_dashboard_selection_label(
                            'sat.prueba.maquina',
                            'estado_toner',
                            estado_toner,
                        ),

                        'estado_prueba': prueba.estado_prueba or 'pendiente',
                        'estado_prueba_label': rec._sat_dashboard_selection_label(
                            'sat.prueba.maquina',
                            'estado_prueba',
                            prueba.estado_prueba or 'pendiente',
                        ),

                        'nivel_prueba': prueba.nivel_prueba or 'sin_prueba',
                        'nivel_prueba_label': rec._sat_dashboard_selection_label(
                            'sat.prueba.maquina',
                            'nivel_prueba',
                            prueba.nivel_prueba or 'sin_prueba',
                        ),

                        'cantidad_alertas_snmp': rec._sat_dashboard_int(prueba.cantidad_alertas_snmp),

                        'prueba_impresion_ok': bool(prueba.prueba_impresion_ok),
                        'prueba_copia_ok': bool(prueba.prueba_copia_ok),
                        'prueba_scanner_ok': bool(prueba.prueba_scanner_ok),
                        'prueba_duplex_ok': bool(prueba.prueba_duplex_ok),
                        'prueba_bn_ok': bool(prueba.prueba_bn_ok),
                        'prueba_color_ok': bool(prueba.prueba_color_ok) if es_color else False,
                    }

                    items.append(item)

                ultima = items[0] if items else {}

                payload = {
                    'maquina_id': rec.id,
                    'modelo': rec.name.name if rec.name else '',
                    'serie': rec.serie_id or '',
                    'marca': rec.marca or '',
                    'tipo_id': rec.tipo_id or '',
                    'tipo_maquina': rec.tipo_maquina or '',
                    'es_color': bool(es_color),
                    'es_bn': not bool(es_color),
                    'total_pruebas': len(items),
                    'ultima': ultima,
                    'items': items,
                }

                rec.prueba_tecnica_dashboard_json = json.dumps(
                    payload,
                    ensure_ascii=False,
                )

            except Exception as e:
                _logger.error(
                    '[DASHBOARD PRUEBAS] Error generando dashboard para sat.sat ID %s: %s',
                    rec.id,
                    e,
                    exc_info=True,
                )
                rec.prueba_tecnica_dashboard_json = json.dumps({
                    'maquina_id': rec.id,
                    'modelo': rec.name.name if rec.name else '',
                    'serie': rec.serie_id or '',
                    'marca': rec.marca or '',
                    'tipo_id': rec.tipo_id or '',
                    'tipo_maquina': rec.tipo_maquina or '',
                    'es_color': False,
                    'es_bn': True,
                    'total_pruebas': 0,
                    'ultima': {},
                    'items': [],
                    'error': str(e),
                }, ensure_ascii=False)
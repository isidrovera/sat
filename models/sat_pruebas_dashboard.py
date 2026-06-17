# -*- coding: utf-8 -*-

import json
import logging
import re

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
    # HELPERS GENERALES
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

    def _sat_dashboard_norm(self, value):
        value = str(value or '').lower().strip()
        value = value.replace('á', 'a')
        value = value.replace('é', 'e')
        value = value.replace('í', 'i')
        value = value.replace('ó', 'o')
        value = value.replace('ú', 'u')
        value = value.replace('ñ', 'n')
        value = re.sub(r'[^a-z0-9]+', '_', value)
        value = re.sub(r'_+', '_', value).strip('_')
        return value

    def _sat_dashboard_percent_estado(self, value):
        value = self._sat_dashboard_float(value)

        if value <= 0:
            return 'sin_datos'
        if value <= 10:
            return 'critico'
        if value <= 25:
            return 'bajo'
        return 'ok'

    def _sat_dashboard_percent_clamp(self, value):
        value = self._sat_dashboard_float(value)

        if value < 0:
            return 0.0
        if value > 100:
            return 100.0
        return value

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

        # Regla principal: selection del SAT
        if tipo == 'color':
            return True

        if tipo == 'monocromatica':
            return False

        # Respaldo por texto
        palabras_color = [
            'color',
            'colour',
            'full color',
            'bizhub c',
            'mp c',
            'im c',
            'ir-adv c',
            'ir adv c',
            'image runner c',
        ]

        palabras_bn = [
            'monocromatica',
            'monocromatico',
            'monochrome',
            'blanco y negro',
            'b/n',
            'bn',
            'black',
            'mp 501',
            'mp 301',
        ]

        for palabra in palabras_color:
            if palabra in texto:
                return True

        for palabra in palabras_bn:
            if palabra in texto:
                return False

        # Si no se puede saber, asumimos B/N para no mostrar CMY falsos
        return False

    # ==========================================================
    # HELPERS TÓNER
    # ==========================================================

    def _sat_dashboard_toner_card(self, key, label, code, value, description, css_class):
        value = self._sat_dashboard_percent_clamp(value)
        estado = self._sat_dashboard_percent_estado(value)

        return {
            'key': key,
            'label': label,
            'code': code,
            'value': value,
            'estado': estado,
            'description': description,
            'className': css_class,
        }

    def _sat_dashboard_toner_cards(self, prueba, es_color):
        toner_negro = self._sat_dashboard_float(prueba.toner_negro)
        toner_cyan = self._sat_dashboard_float(prueba.toner_cyan)
        toner_magenta = self._sat_dashboard_float(prueba.toner_magenta)
        toner_amarillo = self._sat_dashboard_float(prueba.toner_amarillo)

        cards = [
            self._sat_dashboard_toner_card(
                key='negro',
                label='Negro',
                code='K',
                value=toner_negro,
                description='Tóner principal',
                css_class='sat_toner_k',
            )
        ]

        if es_color:
            cards += [
                self._sat_dashboard_toner_card(
                    key='cyan',
                    label='Cyan',
                    code='C',
                    value=toner_cyan,
                    description='Color cyan',
                    css_class='sat_toner_c',
                ),
                self._sat_dashboard_toner_card(
                    key='magenta',
                    label='Magenta',
                    code='M',
                    value=toner_magenta,
                    description='Color magenta',
                    css_class='sat_toner_m',
                ),
                self._sat_dashboard_toner_card(
                    key='amarillo',
                    label='Amarillo',
                    code='Y',
                    value=toner_amarillo,
                    description='Color amarillo',
                    css_class='sat_toner_y',
                ),
            ]

        return cards

    def _sat_dashboard_toner_minimo(self, toner_cards):
        valores = []

        for item in toner_cards:
            value = self._sat_dashboard_float(item.get('value'))
            if value > 0:
                valores.append(value)

        return min(valores) if valores else 0.0

    # ==========================================================
    # HELPERS COMPONENTES SNMP
    # ==========================================================

    def _sat_dashboard_component_tipo_visual(self, nombre, categoria):
        texto = str(nombre or '').lower()
        categoria = str(categoria or '').lower()

        if 'developer' in texto or 'revelador' in texto:
            return 'developer', 'Developer', 'fa-flask', 'sat_component_developer'

        if (
            'drum' in texto
            or 'tambor' in texto
            or 'opc' in texto
            or 'image unit' in texto
            or 'imaging unit' in texto
        ):
            return 'drum', 'Drum / Tambor', 'fa-circle-o-notch', 'sat_component_drum'

        if (
            'fuser' in texto
            or 'fusor' in texto
            or 'fusora' in texto
            or 'fixing' in texto
            or 'fixation' in texto
        ):
            return 'fuser', 'Fusora', 'fa-fire', 'sat_component_fuser'

        if (
            'transfer' in texto
            or 'transferencia' in texto
            or 'belt' in texto
            or 'faja' in texto
            or 'transfer belt' in texto
        ):
            return 'transfer', 'Transferencia', 'fa-exchange', 'sat_component_transfer'

        if (
            'waste' in texto
            or 'residual' in texto
            or 'waste toner' in texto
            or 'toner residual' in texto
            or 'tóner residual' in texto
        ):
            return 'waste', 'Residual', 'fa-trash', 'sat_component_waste'

        if 'toner' in texto or 'tóner' in texto:
            return 'toner', 'Tóner', 'fa-tint', 'sat_component_toner'

        if (
            'hdd' in texto
            or 'hard disk' in texto
            or 'firmware' in texto
            or 'flash memory' in texto
            or 'memory' in texto
            or 'memoria' in texto
        ):
            return 'system', 'Sistema', 'fa-hdd-o', 'sat_component_system'

        if (
            'feeder' in texto
            or 'document feeder' in texto
            or 'reader' in texto
            or 'finisher' in texto
            or 'finalizador' in texto
            or 'staple' in texto
            or 'grapa' in texto
        ):
            return 'accessory', 'Accesorio', 'fa-puzzle-piece', 'sat_component_accessory'

        if categoria == 'unidad':
            return 'unit', 'Unidad', 'fa-cube', 'sat_component_unit'

        if categoria == 'consumible':
            return 'supply', 'Consumible', 'fa-cube', 'sat_component_supply'

        if categoria == 'sistema':
            return 'system', 'Sistema', 'fa-hdd-o', 'sat_component_system'

        if categoria == 'accesorio':
            return 'accessory', 'Accesorio', 'fa-puzzle-piece', 'sat_component_accessory'

        return 'other', 'Componente', 'fa-cube', 'sat_component_other'

    def _sat_dashboard_component_estado(self, valor, unidad):
        valor = self._sat_dashboard_float(valor)
        unidad = str(unidad or '').lower()

        # Si no hay lectura numérica
        if valor <= 0:
            return 'sin_datos'

        # Si parece porcentaje
        if '%' in unidad or 'percent' in unidad or valor <= 100:
            if valor <= 10:
                return 'critico'
            if valor <= 25:
                return 'bajo'
            return 'ok'

        # Para contadores de vida/uso que no son porcentaje
        return 'info'

    def _sat_dashboard_detalle_value(self, det):
        """
        Lee el valor numérico de sat.prueba.maquina.snmp.detalle
        sin romper si el campo cambia de nombre.
        """
        for field_name in [
            'valor_actual_numero',
            'valor_numero',
            'valor_float',
            'valor',
            'value',
            'nivel',
        ]:
            try:
                if field_name in det._fields:
                    value = getattr(det, field_name)
                    if value not in (None, False, ''):
                        return self._sat_dashboard_float(value)
            except Exception:
                pass

        return 0.0

    def _sat_dashboard_detalle_text(self, det, *field_names):
        for field_name in field_names:
            try:
                if field_name in det._fields:
                    value = getattr(det, field_name)
                    if value not in (None, False, ''):
                        return str(value).strip()
            except Exception:
                pass
        return ''

    def _sat_dashboard_snmp_items(self, prueba):
        """
        Devuelve componentes/consumibles desde snmp_detalle_ids.

        Categorías esperadas:
          - consumible
          - unidad
          - accesorio
          - sistema

        Aquí aparecen:
          developer, drum, fusora, transfer belt, waste toner,
          image unit, maintenance kit, feeder, finisher, HDD, firmware, etc.
        """
        resultado = []

        try:
            if 'snmp_detalle_ids' not in prueba._fields:
                return resultado

            detalles = prueba.snmp_detalle_ids.filtered(
                lambda d: (d.categoria or '') in (
                    'consumible',
                    'unidad',
                    'accesorio',
                    'sistema',
                )
            )

            vistos = set()

            for det in detalles:
                categoria = self._sat_dashboard_detalle_text(det, 'categoria') or 'otro'

                nombre = self._sat_dashboard_detalle_text(
                    det,
                    'nombre',
                    'descripcion',
                    'description',
                    'source_name',
                ) or 'Elemento SNMP'

                source_name = self._sat_dashboard_detalle_text(
                    det,
                    'source_name',
                    'origen',
                )

                oid = self._sat_dashboard_detalle_text(
                    det,
                    'oid',
                    'oid_valor',
                    'oid_value',
                    'oid_counter',
                )

                unidad = self._sat_dashboard_detalle_text(
                    det,
                    'unidad',
                    'unit',
                ) or '%'

                valor = self._sat_dashboard_detalle_value(det)

                tipo_visual, tipo_label, icono, css_class = self._sat_dashboard_component_tipo_visual(
                    nombre=nombre,
                    categoria=categoria,
                )

                estado = self._sat_dashboard_component_estado(valor, unidad)

                key = '%s|%s|%s|%s' % (
                    categoria,
                    self._sat_dashboard_norm(nombre),
                    self._sat_dashboard_norm(source_name),
                    oid,
                )

                if key in vistos:
                    continue

                vistos.add(key)

                resultado.append({
                    'id': det.id,
                    'categoria': categoria,
                    'tipo_visual': tipo_visual,
                    'tipo_label': tipo_label,
                    'icono': icono,
                    'css_class': css_class,
                    'nombre': nombre,
                    'valor': valor,
                    'valor_percent': self._sat_dashboard_percent_clamp(valor),
                    'unidad': unidad,
                    'oid': oid,
                    'source_name': source_name,
                    'estado': estado,
                })

        except Exception as e:
            _logger.warning(
                '[DASHBOARD PRUEBAS] No se pudo leer snmp_detalle_ids de prueba %s: %s',
                prueba.id,
                e,
            )

        # Orden visual: primero lo más técnico/importante
        prioridad = {
            'developer': 1,
            'drum': 2,
            'fuser': 3,
            'transfer': 4,
            'waste': 5,
            'toner': 6,
            'unit': 7,
            'supply': 8,
            'accessory': 9,
            'system': 10,
            'other': 99,
        }

        resultado.sort(
            key=lambda x: (
                prioridad.get(x.get('tipo_visual'), 99),
                x.get('nombre') or '',
            )
        )

        return resultado

    def _sat_dashboard_component_groups(self, componentes):
        unidades = []
        consumibles = []
        accesorios = []
        sistema = []
        otros = []

        for item in componentes or []:
            categoria = item.get('categoria')

            if categoria == 'unidad':
                unidades.append(item)
            elif categoria == 'consumible':
                consumibles.append(item)
            elif categoria == 'accesorio':
                accesorios.append(item)
            elif categoria == 'sistema':
                sistema.append(item)
            else:
                otros.append(item)

        return {
            'unidades': unidades,
            'consumibles': consumibles,
            'accesorios': accesorios,
            'sistema': sistema,
            'otros': otros,
        }

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

        # Detalle SNMP para unidades / consumibles
        'prueba_ids.snmp_detalle_ids',
        'prueba_ids.snmp_detalle_ids.categoria',
        'prueba_ids.snmp_detalle_ids.nombre',
        'prueba_ids.snmp_detalle_ids.descripcion',
        'prueba_ids.snmp_detalle_ids.source_name',
        'prueba_ids.snmp_detalle_ids.valor_actual_numero',
        'prueba_ids.snmp_detalle_ids.unidad',
        'prueba_ids.snmp_detalle_ids.oid',
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
                    toner_cards = rec._sat_dashboard_toner_cards(prueba, es_color)
                    toner_minimo = rec._sat_dashboard_toner_minimo(toner_cards)

                    estado_toner = (
                        prueba.estado_toner
                        or rec._sat_dashboard_percent_estado(toner_minimo)
                    )

                    componentes = rec._sat_dashboard_snmp_items(prueba)
                    component_groups = rec._sat_dashboard_component_groups(componentes)

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

                        # Contadores
                        'contador_inicial_total': rec._sat_dashboard_int(prueba.contador_inicial_total),
                        'contador_actual_total': rec._sat_dashboard_int(prueba.contador_actual_total),

                        'contador_actual_bn': rec._sat_dashboard_int(prueba.contador_actual_bn),
                        'contador_actual_color': rec._sat_dashboard_int(prueba.contador_actual_color),

                        'contador_impresiones': rec._sat_dashboard_int(prueba.contador_impresiones),
                        'contador_copias': rec._sat_dashboard_int(prueba.contador_copias),
                        'contador_scanner': rec._sat_dashboard_int(prueba.contador_scanner),
                        'contador_duplex': rec._sat_dashboard_int(prueba.contador_duplex),

                        # Deltas
                        'delta_total': rec._sat_dashboard_int(prueba.delta_total),
                        'delta_bn': rec._sat_dashboard_int(prueba.delta_bn),
                        'delta_color': rec._sat_dashboard_int(prueba.delta_color),
                        'delta_impresiones': rec._sat_dashboard_int(prueba.delta_impresiones),
                        'delta_copias': rec._sat_dashboard_int(prueba.delta_copias),
                        'delta_scanner': rec._sat_dashboard_int(prueba.delta_scanner),
                        'delta_duplex': rec._sat_dashboard_int(prueba.delta_duplex),

                        # Tóner antiguo compatible
                        'toner_negro': rec._sat_dashboard_float(prueba.toner_negro),
                        'toner_cyan': rec._sat_dashboard_float(prueba.toner_cyan) if es_color else 0.0,
                        'toner_magenta': rec._sat_dashboard_float(prueba.toner_magenta) if es_color else 0.0,
                        'toner_amarillo': rec._sat_dashboard_float(prueba.toner_amarillo) if es_color else 0.0,

                        # Tóner nuevo organizado
                        'toner_cards': toner_cards,
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

                        # Checks
                        'prueba_impresion_ok': bool(prueba.prueba_impresion_ok),
                        'prueba_copia_ok': bool(prueba.prueba_copia_ok),
                        'prueba_scanner_ok': bool(prueba.prueba_scanner_ok),
                        'prueba_duplex_ok': bool(prueba.prueba_duplex_ok),
                        'prueba_bn_ok': bool(prueba.prueba_bn_ok),
                        'prueba_color_ok': bool(prueba.prueba_color_ok) if es_color else False,

                        # Componentes SNMP
                        'componentes_snmp': componentes,
                        'componentes_count': len(componentes),

                        'unidades_snmp': component_groups.get('unidades') or [],
                        'consumibles_snmp': component_groups.get('consumibles') or [],
                        'accesorios_snmp': component_groups.get('accesorios') or [],
                        'sistema_snmp': component_groups.get('sistema') or [],
                        'otros_snmp': component_groups.get('otros') or [],

                        'unidades_count': len(component_groups.get('unidades') or []),
                        'consumibles_count': len(component_groups.get('consumibles') or []),
                        'accesorios_count': len(component_groups.get('accesorios') or []),
                        'sistema_count': len(component_groups.get('sistema') or []),
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
                    'machine_type_label': 'Color' if es_color else 'B/N',

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
                    'machine_type_label': 'B/N',
                    'total_pruebas': 0,
                    'ultima': {},
                    'items': [],
                    'error': str(e),
                }, ensure_ascii=False)
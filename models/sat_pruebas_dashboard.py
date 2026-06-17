# -*- coding: utf-8 -*-

import json
import logging
import re
from datetime import date, datetime

from odoo import api, fields, models
from odoo.models import NewId

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

    def _sat_dashboard_safe_id(self, value):
        """
        Devuelve un ID seguro para JSON.

        En onchange Odoo puede usar IDs temporales tipo NewId.
        Ese objeto no se puede serializar con json.dumps, por eso
        cualquier NewId se convierte a False.
        """
        if not value:
            return False

        if isinstance(value, NewId):
            return False

        try:
            if value.__class__.__name__ == 'NewId':
                return False
        except Exception:
            pass

        try:
            return int(value)
        except Exception:
            return False

    def _sat_dashboard_json_safe(self, value):
        """
        Limpia cualquier estructura antes de convertirla a JSON.

        Protege contra:
        - NewId en registros nuevos o líneas One2many en memoria.
        - recordsets de Odoo.
        - fechas/datetimes.
        - listas, tuplas, sets y diccionarios anidados.
        """
        if isinstance(value, NewId):
            return False

        try:
            if value.__class__.__name__ == 'NewId':
                return False
        except Exception:
            pass

        if isinstance(value, dict):
            return {
                str(k): self._sat_dashboard_json_safe(v)
                for k, v in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                self._sat_dashboard_json_safe(v)
                for v in value
            ]

        if isinstance(value, models.BaseModel):
            if len(value) == 1:
                return {
                    'id': self._sat_dashboard_safe_id(value.id),
                    'name': value.display_name or '',
                }
            return [
                {
                    'id': self._sat_dashboard_safe_id(rec.id),
                    'name': rec.display_name or '',
                }
                for rec in value
            ]

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, bytes):
            return False

        return value

    def _sat_dashboard_json_dumps(self, payload):
        """
        Convierte el payload del dashboard a JSON de forma segura.
        """
        return json.dumps(
            self._sat_dashboard_json_safe(payload),
            ensure_ascii=False,
        )

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
        """
        Clasifica visualmente cualquier elemento SNMP para el dashboard.

        Detecta:
        - developer / revelador
        - drum / tambor / opc / image unit
        - fuser / fusor / fusora / fixing
        - transfer / transferencia / belt / faja
        - waste toner / residual
        - toner
        - sistema
        - accesorios
        - unidades genéricas
        - consumibles genéricos
        """
        texto = str(nombre or '').lower()
        categoria = str(categoria or '').lower()

        texto_norm = texto
        texto_norm = texto_norm.replace('á', 'a')
        texto_norm = texto_norm.replace('é', 'e')
        texto_norm = texto_norm.replace('í', 'i')
        texto_norm = texto_norm.replace('ó', 'o')
        texto_norm = texto_norm.replace('ú', 'u')
        texto_norm = texto_norm.replace('ñ', 'n')

        categoria_norm = categoria
        categoria_norm = categoria_norm.replace('á', 'a')
        categoria_norm = categoria_norm.replace('é', 'e')
        categoria_norm = categoria_norm.replace('í', 'i')
        categoria_norm = categoria_norm.replace('ó', 'o')
        categoria_norm = categoria_norm.replace('ú', 'u')
        categoria_norm = categoria_norm.replace('ñ', 'n')

        # Developer / Revelador
        if (
            'developer' in texto_norm
            or 'developing' in texto_norm
            or 'revelador' in texto_norm
            or 'unidad revelado' in texto_norm
            or 'unidad de revelado' in texto_norm
            or 'dv unit' in texto_norm
            or 'dv-unit' in texto_norm
        ):
            return 'developer', 'Developer', 'fa-flask', 'sat_component_developer'

        # Drum / Tambor / OPC / Image Unit
        if (
            'drum' in texto_norm
            or 'tambor' in texto_norm
            or 'opc' in texto_norm
            or 'image unit' in texto_norm
            or 'imaging unit' in texto_norm
            or 'photoconductor' in texto_norm
            or 'pc unit' in texto_norm
            or 'pc-unit' in texto_norm
            or 'unidad imagen' in texto_norm
            or 'unidad de imagen' in texto_norm
        ):
            return 'drum', 'Drum / Tambor', 'fa-circle-o-notch', 'sat_component_drum'

        # Fusor / Fusora / Fuser / Fixing
        if (
            'fuser' in texto_norm
            or 'fusor' in texto_norm
            or 'fusora' in texto_norm
            or 'fixing' in texto_norm
            or 'fixation' in texto_norm
            or 'heat roller' in texto_norm
            or 'hot roller' in texto_norm
            or 'unidad fusora' in texto_norm
            or 'unidad de fusion' in texto_norm
            or 'unidad fusion' in texto_norm
        ):
            return 'fuser', 'Fusora', 'fa-fire', 'sat_component_fuser'

        # Transferencia / Transfer Belt / Faja
        if (
            'transfer' in texto_norm
            or 'transferencia' in texto_norm
            or 'transfer belt' in texto_norm
            or 'belt' in texto_norm
            or 'faja' in texto_norm
            or 'cinta transferencia' in texto_norm
            or 'unidad transferencia' in texto_norm
            or 'unidad de transferencia' in texto_norm
        ):
            return 'transfer', 'Transferencia', 'fa-exchange', 'sat_component_transfer'

        # Waste / Residual
        if (
            'waste' in texto_norm
            or 'residual' in texto_norm
            or 'waste toner' in texto_norm
            or 'toner residual' in texto_norm
            or 'tóner residual' in texto_norm
            or 'toner waste' in texto_norm
            or 'waste box' in texto_norm
            or 'waste container' in texto_norm
            or 'residu' in texto_norm
        ):
            return 'waste', 'Residual', 'fa-trash', 'sat_component_waste'

        # Toner
        if (
            'toner' in texto_norm
            or 'tóner' in texto_norm
            or 'black toner' in texto_norm
            or 'cyan toner' in texto_norm
            or 'magenta toner' in texto_norm
            or 'yellow toner' in texto_norm
        ):
            return 'toner', 'Tóner', 'fa-tint', 'sat_component_toner'

        # Sistema
        if (
            'hdd' in texto_norm
            or 'hard disk' in texto_norm
            or 'disco' in texto_norm
            or 'firmware' in texto_norm
            or 'flash memory' in texto_norm
            or 'memory' in texto_norm
            or 'memoria' in texto_norm
            or 'rom' in texto_norm
            or 'version' in texto_norm
            or 'versión' in texto_norm
        ):
            return 'system', 'Sistema', 'fa-hdd-o', 'sat_component_system'

        # Accesorios
        if (
            'feeder' in texto_norm
            or 'document feeder' in texto_norm
            or 'adf' in texto_norm
            or 'reader' in texto_norm
            or 'finisher' in texto_norm
            or 'finalizador' in texto_norm
            or 'staple' in texto_norm
            or 'grapa' in texto_norm
            or 'punch' in texto_norm
            or 'booklet' in texto_norm
            or 'cassette' in texto_norm
            or 'tray' in texto_norm
            or 'bandeja' in texto_norm
        ):
            return 'accessory', 'Accesorio', 'fa-puzzle-piece', 'sat_component_accessory'

        # Clasificación por categoría
        if categoria_norm in ('unidad', 'unit', 'units', 'life', 'maintenance'):
            return 'unit', 'Unidad', 'fa-cube', 'sat_component_unit'

        if categoria_norm in ('consumible', 'consumibles', 'supply', 'supplies', 'consumable', 'consumables'):
            return 'supply', 'Consumible', 'fa-cube', 'sat_component_supply'

        if categoria_norm in ('sistema', 'system', 'raw_system'):
            return 'system', 'Sistema', 'fa-hdd-o', 'sat_component_system'

        if categoria_norm in ('accesorio', 'accessory', 'accessories'):
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
        Devuelve componentes/consumibles para el dashboard moderno.

        Lee primero desde snmp_detalle_ids.
        Si no encuentra nada o si el detalle viene incompleto,
        también lee desde raw_payload_json.

        Permite mostrar:
        - developer
        - drum / tambor / image unit
        - fusora / fuser / fixing
        - transfer belt / faja transferencia
        - waste toner / tóner residual
        - accesorios
        - sistema

        Importante:
        No filtra de forma cerrada por categoria, porque algunos SNMP
        guardan developer/drum/fuser como raw, life, maintenance,
        supply, unit, drum, developer, fuser, etc.
        """
        resultado = []
        vistos = set()

        def _categoria_dashboard(categoria_original, nombre, source_name=''):
            """
            Convierte cualquier categoría/nombre SNMP a las categorías
            que entiende el dashboard:
            - unidad
            - consumible
            - accesorio
            - sistema
            - otro
            """
            texto = "%s %s %s" % (
                nombre or '',
                source_name or '',
                categoria_original or '',
            )

            tipo_visual, tipo_label, icono, css_class = self._sat_dashboard_component_tipo_visual(
                nombre=texto,
                categoria=categoria_original,
            )

            if tipo_visual in ('developer', 'drum', 'fuser', 'transfer', 'unit'):
                return 'unidad'

            if tipo_visual in ('waste', 'toner', 'supply'):
                return 'consumible'

            if tipo_visual == 'accessory':
                return 'accesorio'

            if tipo_visual == 'system':
                return 'sistema'

            cat = str(categoria_original or '').lower().strip()
            cat = cat.replace('á', 'a')
            cat = cat.replace('é', 'e')
            cat = cat.replace('í', 'i')
            cat = cat.replace('ó', 'o')
            cat = cat.replace('ú', 'u')
            cat = cat.replace('ñ', 'n')

            if cat in ('unidad', 'unit', 'units', 'life', 'maintenance', 'drum', 'developer', 'fuser', 'transfer'):
                return 'unidad'

            if cat in ('consumible', 'consumibles', 'supply', 'supplies', 'consumable', 'consumables', 'toner', 'waste'):
                return 'consumible'

            if cat in ('accesorio', 'accessory', 'accessories', 'tray', 'trays', 'paper_tray'):
                return 'accesorio'

            if cat in ('sistema', 'system', 'raw_system', 'firmware', 'memory'):
                return 'sistema'

            return 'otro'

        def _add_item(
            item_id,
            categoria,
            nombre,
            valor,
            unidad='%',
            oid='',
            source_name='',
        ):
            nombre = str(nombre or '').strip()
            categoria = str(categoria or 'otro').strip()

            if not nombre:
                return

            valor = self._sat_dashboard_float(valor)
            unidad = str(unidad or '%').strip()
            oid = str(oid or '').strip()
            source_name = str(source_name or '').strip()

            categoria_dashboard = _categoria_dashboard(
                categoria_original=categoria,
                nombre=nombre,
                source_name=source_name,
            )

            texto_clasificacion = "%s %s %s" % (
                nombre,
                source_name,
                categoria,
            )

            tipo_visual, tipo_label, icono, css_class = self._sat_dashboard_component_tipo_visual(
                nombre=texto_clasificacion,
                categoria=categoria_dashboard,
            )

            estado = self._sat_dashboard_component_estado(valor, unidad)

            key = '%s|%s|%s|%s' % (
                categoria_dashboard,
                self._sat_dashboard_norm(nombre),
                self._sat_dashboard_norm(source_name),
                oid,
            )

            if key in vistos:
                return

            vistos.add(key)

            resultado.append({
                'id': self._sat_dashboard_safe_id(item_id) if not isinstance(item_id, str) else item_id,
                'categoria': categoria_dashboard,
                'categoria_original': categoria,
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

        def _valor_from_dict(data):
            """
            Lee valores con nombres comunes usados por distintos payloads SNMP.
            """
            if not isinstance(data, dict):
                return data

            for key in (
                'level',
                'percent',
                'percentage',
                'remaining',
                'remaining_percent',
                'life',
                'life_percent',
                'value',
                'valor',
                'current',
                'current_value',
                'valor_actual_numero',
                'valor_numero',
                'count',
                'counter',
            ):
                value = data.get(key)
                if value not in (None, False, ''):
                    return value

            return 0

        def _nombre_from_dict(key, data):
            """
            Lee nombre/descripción con nombres comunes usados por distintos payloads SNMP.
            """
            if not isinstance(data, dict):
                return key

            return (
                data.get('name')
                or data.get('description')
                or data.get('descripcion')
                or data.get('nombre')
                or data.get('label')
                or data.get('source_name')
                or data.get('key')
                or key
            )

        # ======================================================
        # 1) Leer desde líneas SNMP guardadas
        # ======================================================
        try:
            if 'snmp_detalle_ids' in prueba._fields:
                detalles = prueba.snmp_detalle_ids

                for det in detalles:
                    categoria = self._sat_dashboard_detalle_text(
                        det,
                        'categoria',
                        'category',
                        'tipo',
                        'type',
                    ) or 'otro'

                    nombre = self._sat_dashboard_detalle_text(
                        det,
                        'nombre',
                        'name',
                        'descripcion',
                        'description',
                        'source_name',
                        'label',
                    ) or 'Elemento SNMP'

                    source_name = self._sat_dashboard_detalle_text(
                        det,
                        'source_name',
                        'origen',
                        'key',
                        'source',
                    )

                    oid = self._sat_dashboard_detalle_text(
                        det,
                        'oid',
                        'oid_valor',
                        'oid_value',
                        'oid_counter',
                        'snmp_oid',
                    )

                    unidad = self._sat_dashboard_detalle_text(
                        det,
                        'unidad',
                        'unit',
                        'units',
                    ) or '%'

                    valor = self._sat_dashboard_detalle_value(det)

                    _add_item(
                        item_id=self._sat_dashboard_safe_id(det.id),
                        categoria=categoria,
                        nombre=nombre,
                        valor=valor,
                        unidad=unidad,
                        oid=oid,
                        source_name=source_name,
                    )

        except Exception as e:
            _logger.warning(
                '[DASHBOARD PRUEBAS] No se pudo leer snmp_detalle_ids de prueba %s: %s',
                prueba.id,
                e,
            )

        # ======================================================
        # 2) Fallback: leer desde raw_payload_json
        # ======================================================
        try:
            raw_payload = {}

            if 'raw_payload_json' in prueba._fields and prueba.raw_payload_json:
                raw_payload = json.loads(prueba.raw_payload_json or '{}')

            if isinstance(raw_payload, dict):
                bloques = [
                    # Consumibles
                    ('consumible', 'supplies'),
                    ('consumible', 'raw_supplies'),
                    ('consumible', 'consumables'),
                    ('consumible', 'raw_consumables'),
                    ('consumible', 'supply'),
                    ('consumible', 'toner'),
                    ('consumible', 'waste'),
                    ('consumible', 'waste_toner'),
                    ('consumible', 'wasteToner'),

                    # Unidades
                    ('unidad', 'units'),
                    ('unidad', 'raw_units'),
                    ('unidad', 'unit'),
                    ('unidad', 'life'),
                    ('unidad', 'lifetime'),
                    ('unidad', 'maintenance'),
                    ('unidad', 'maintenance_parts'),
                    ('unidad', 'parts'),
                    ('unidad', 'drum'),
                    ('unidad', 'drums'),
                    ('unidad', 'developer'),
                    ('unidad', 'developers'),
                    ('unidad', 'fuser'),
                    ('unidad', 'fusers'),
                    ('unidad', 'fixing'),
                    ('unidad', 'transfer'),
                    ('unidad', 'transfer_belt'),
                    ('unidad', 'image_unit'),
                    ('unidad', 'imaging_unit'),

                    # Accesorios
                    ('accesorio', 'accessories'),
                    ('accesorio', 'raw_accessories'),
                    ('accesorio', 'accessory'),
                    ('accesorio', 'trays'),
                    ('accesorio', 'paper_trays'),
                    ('accesorio', 'paper_sources'),

                    # Sistema
                    ('sistema', 'system'),
                    ('sistema', 'raw_system'),
                    ('sistema', 'firmware'),
                    ('sistema', 'memory'),
                    ('sistema', 'storage'),

                    # Bloques amplios por si el controlador guarda todo mezclado
                    ('otro', 'raw'),
                    ('otro', 'details'),
                    ('otro', 'detalle'),
                    ('otro', 'snmp_details'),
                    ('otro', 'snmp_detalles'),
                ]

                for categoria, key_bloque in bloques:
                    bloque = raw_payload.get(key_bloque)

                    if bloque in (None, False, ''):
                        continue

                    # Caso dict: {'drum_black': {'level': 80}, ...}
                    if isinstance(bloque, dict):
                        for key, data in bloque.items():
                            if isinstance(data, dict):
                                nombre = _nombre_from_dict(key, data)
                                valor = _valor_from_dict(data)
                                unidad = data.get('unit') or data.get('unidad') or data.get('units') or '%'
                                oid = data.get('oid') or data.get('oid_value') or data.get('snmp_oid') or ''
                                source_name = data.get('source_name') or data.get('source') or key_bloque
                            else:
                                nombre = key
                                valor = data
                                unidad = '%'
                                oid = ''
                                source_name = key_bloque

                            _add_item(
                                item_id='%s_%s' % (key_bloque, self._sat_dashboard_norm(key)),
                                categoria=categoria,
                                nombre=nombre,
                                valor=valor,
                                unidad=unidad,
                                oid=oid,
                                source_name=source_name,
                            )

                    # Caso list: [{'name': 'Drum Black', 'level': 80}, ...]
                    elif isinstance(bloque, list):
                        for index, data in enumerate(bloque):
                            key = '%s_%s' % (key_bloque, index)

                            if isinstance(data, dict):
                                nombre = _nombre_from_dict(key, data)
                                valor = _valor_from_dict(data)
                                unidad = data.get('unit') or data.get('unidad') or data.get('units') or '%'
                                oid = data.get('oid') or data.get('oid_value') or data.get('snmp_oid') or ''
                                source_name = data.get('source_name') or data.get('source') or key_bloque
                            else:
                                nombre = key
                                valor = data
                                unidad = '%'
                                oid = ''
                                source_name = key_bloque

                            _add_item(
                                item_id='%s_%s' % (key_bloque, index),
                                categoria=categoria,
                                nombre=nombre,
                                valor=valor,
                                unidad=unidad,
                                oid=oid,
                                source_name=source_name,
                            )

        except Exception as e:
            _logger.warning(
                '[DASHBOARD PRUEBAS] No se pudo leer raw_payload_json de prueba %s: %s',
                prueba.id,
                e,
            )

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

                    prueba_safe_id = rec._sat_dashboard_safe_id(prueba.id)

                    item = {
                        'id': prueba_safe_id,
                        'name': prueba.display_name or ('Prueba #%s' % (prueba_safe_id or 'Nueva')),

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
                    'maquina_id': rec._sat_dashboard_safe_id(rec.id),
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

                rec.prueba_tecnica_dashboard_json = rec._sat_dashboard_json_dumps(payload)

            except Exception as e:
                _logger.error(
                    '[DASHBOARD PRUEBAS] Error generando dashboard para sat.sat ID %s: %s',
                    rec.id,
                    e,
                    exc_info=True,
                )

                rec.prueba_tecnica_dashboard_json = rec._sat_dashboard_json_dumps({
                    'maquina_id': rec._sat_dashboard_safe_id(rec.id),
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
                })
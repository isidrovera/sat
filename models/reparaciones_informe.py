# -*- coding: utf-8 -*-
from odoo import _, models, fields, api
from odoo.exceptions import UserError
import logging
import re
import unicodedata
import json
import html as html_lib

_logger = logging.getLogger(__name__)

# ===== IMPORTAR GEMINI (con manejo de errores) =====
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    _logger.warning("google-genai no instalado")

class ReparacionesInforme(models.Model):
    _inherit = 'reparaciones.reparaciones'
    _description = 'Informe Reparaciones (Generación automática/IA con checklist y apoyo SNMP)'

    # ========================================
    # CAMPOS EXISTENTES
    # ========================================
    intervencion_ids = fields.One2many(
        'reparacion.intervencion',
        'reparacion_id',
        string='Intervenciones / Cambios'
    )

    # ========================================
    # CAMPOS NUEVOS PARA IA
    # ========================================
    modo_generacion_informe = fields.Selection([
        ('automatico', 'Automático (sin IA)'),
        ('ia', 'Con Inteligencia Artificial'),
    ], string='Modo de Generación', default='ia',
       help='Automático: usa lógica programada. IA: usa Google Gemini para redactar.')
    
    observaciones_tecnico = fields.Html(
        string='Observaciones Generales del Técnico',
        help='Escribe aquí cualquier observación general sobre la reparación. '
             'La IA usará este texto para generar un informe más preciso.'
    )
    
    informe_generado_por_ia = fields.Boolean(
        string='Informe generado por IA',
        readonly=True,
        default=False,
        help='Indica si este informe fue generado usando IA'
    )
    
    observaciones_tecnico_original = fields.Html(
        string='Observaciones originales (backup)',
        readonly=True,
        help='Copia de las observaciones antes de procesamiento por IA'
    )
    
    calidad_justificacion = fields.Text(
        string='Justificación de Calidad',
        readonly=True,
        help='Explicación de por qué la IA determinó esta calidad'
    )

    # ========================================
    # HELPERS DE VALIDACIÓN
    # ========================================
    def _rep__is_autogen_informe(self):
        """Detecta si el informe fue autogenerado (marca data-autogen=1)."""
        html = (self.informe or '').lower()
        res = 'data-autogen="1"' in html
        _logger.debug("[_rep__is_autogen_informe] id=%s autogen=%s", self.id, res)
        return res

    def _rep__html_is_empty(self, html):
        """True si el HTML está vacío (solo tags/espacios/&nbsp;/<br>)."""
        if not html:
            _logger.debug("[_rep__html_is_empty] HTML vacío (None/''), retorna True")
            return True
        s = html.replace('&nbsp;', ' ')
        s = re.sub(r'<br\s*/?>', ' ', s, flags=re.I)
        s = re.sub(r'<[^>]*>', '', s)  # quitar etiquetas
        res = (s.strip() == '')
        _logger.debug("[_rep__html_is_empty] limpio='%s' vacío=%s", s.strip(), res)
        return res

    # ========================================
    # HELPERS DE COLOR
    # ========================================
    def _rep__normalize_color_name(self, name):
        """Convierte nombres en código 'k/c/m/y' cuando no hay code en color_id."""
        if not name:
            return False
        n = str(name).strip().lower()
        mapping = {
            'k': 'k', 'black': 'k', 'negro': 'k',
            'c': 'c', 'cyan': 'c',
            'm': 'm', 'magenta': 'm',
            'y': 'y', 'yellow': 'y', 'amarillo': 'y',
        }
        res = mapping.get(n, False)
        _logger.debug("[_rep__normalize_color_name] name='%s' -> '%s'", name, res)
        return res

    def _rep__get_color_code_from_eval(self, eval_comp):
        """
        Retorna 'k'/'c'/'m'/'y' o False desde la evaluación.
        Prioridad:
        1) eval_comp.color (legacy),
        2) eval_comp.color_id.code,
        3) eval_comp.color_id.name -> k/c/m/y.
        """
        color_legacy = getattr(eval_comp, 'color', False)
        if color_legacy:
            code = str(color_legacy).strip().lower()
            if code in ('k', 'c', 'm', 'y'):
                _logger.debug("[_rep__get_color_code_from_eval] legacy color=%s", code)
                return code

        color_id = getattr(eval_comp, 'color_id', False)
        if color_id:
            code = getattr(color_id, 'code', False)
            if code:
                code = str(code).strip().lower()
                _logger.debug("[_rep__get_color_code_from_eval] color_id.code=%s", code)
                return code if code in ('k', 'c', 'm', 'y') else False
            norm = self._rep__normalize_color_name(getattr(color_id, 'name', False))
            _logger.debug("[_rep__get_color_code_from_eval] color_id.name->%s", norm)
            return norm

        _logger.debug("[_rep__get_color_code_from_eval] sin color en evaluación %s", eval_comp.id)
        return False

    # ========================================
    # HELPER: NORMALIZAR TIPO A CLAVE CANÓNICA
    # ========================================
    def _rep__canonical_tipo_code(self, tipo):
        """
        Devuelve un código canónico del tipo (independiente de idioma/acentos/espacios).
        Ej.: 'IU', 'DEVELOPER', 'FUSORA', 'ITB', 'ADF', 'FINISHER', 'OPTICO', 'TRAY', 'BYPASS', 'PAPEL'
        """
        if not tipo:
            return ''

        raw = (tipo.code or tipo.name or '').strip()

        def _norm(s):
            s = unicodedata.normalize('NFKD', s)
            s = ''.join(c for c in s if not unicodedata.combining(c))
            s = s.upper().strip()
            s = re.sub(r'\s+', ' ', s)
            return s

        txt = _norm(raw)

        alias = [
            (('IMAGEN', 'IMAGING', 'DRUM', 'DRUM UNIT', 'IU', 'UNIDAD IMAGEN', 'UNIDAD DE IMAGEN'), 'IU'),
            (('DEVELOPER', 'DEV'), 'DEVELOPER'),
            (('FUSORA', 'FUSOR', 'FUSER', 'FUSING', 'CALENTADOR'), 'FUSORA'),
            (('ITB', 'TRANSFER BELT', 'TRANSFERENCIA', 'FAJA', 'BANDA'), 'ITB'),
            (('ADF', 'ALIMENTADOR', 'ALIMENTADOR DE DOCUMENTOS'), 'ADF'),
            (('FINISHER', 'FIN', 'ENGRAPADORA', 'GRAPADORA'), 'FINISHER'),
            (('OPTICO', 'OPTICAL', 'ESCANER', 'SCANNER', 'OPTICO/ESCANER', 'LSU'), 'OPTICO'),
            (('TRAY', 'BANDEJA', 'BANDEJAS'), 'TRAY'),
            (('BYPASS',), 'BYPASS'),
            (('PAPEL', 'PAPER', 'TRANSPORTE PAPEL', 'TRANSPORTE DE PAPEL'), 'PAPEL'),
            (('TRANSFER ROLLER', 'ROLLER TRANSFER', 'TRANSFER_ROLLER'), 'FUSORA'),
            (('CARCASA', 'TAPAS'), 'CARCASA'),
            (('PANEL', 'PANEL CONTROL', 'PANEL_CONTROL'), 'PANEL_CONTROL'),
        ]

        for keys, canon in alias:
            for k in keys:
                if k in txt:
                    return canon

        return txt  # para logging cuando no matchea ningún alias

    # ========================================
    # HELPERS PARA INFORME DINÁMICO
    # ========================================
    def _rep__safe_code(self, value):
        """Normaliza códigos técnicos sin depender de mayúsculas o espacios."""
        return str(value or '').strip().lower()

    def _rep__html_to_text(self, value):
        """Convierte observaciones HTML en texto limpio para informe y prompt."""
        if not value:
            return ''
        txt = re.sub(r'<br\s*/?>', '\n', str(value), flags=re.I)
        txt = re.sub(r'</p\s*>', '\n', txt, flags=re.I)
        txt = re.sub(r'<[^>]+>', '', txt)
        txt = html_lib.unescape(txt).replace('\xa0', ' ')
        txt = re.sub(r'[ \t]+', ' ', txt)
        txt = re.sub(r'\n\s*\n+', '\n', txt)
        return txt.strip()

    def _rep__unique(self, values):
        """Elimina duplicados conservando el orden."""
        result = []
        seen = set()
        for value in values:
            key = str(value or '').strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    def _rep__escape(self, value):
        return html_lib.escape(str(value or ''), quote=True)

    def _rep__get_accessory_records(self):
        """
        Obtiene las evaluaciones de accesorios sin romper instalaciones donde
        el campo tenga otro nombre. Solo usa campos realmente existentes.
        """
        for field_name in ('accesorio_eval_ids', 'accesorio_evaluacion_ids', 'evaluacion_accesorio_ids'):
            if field_name in self._fields:
                return self[field_name]
        return self.env['ir.model'].browse([])

    def _rep__get_accessory_type(self, record):
        for field_name in ('accesorio_tipo_id', 'tipo_id', 'accesorio_id'):
            if field_name in record._fields and record[field_name]:
                return record[field_name]
        return False

    def _rep__get_accessory_state(self, record):
        for field_name in ('estado_id', 'accesorio_estado_id'):
            if field_name in record._fields and record[field_name]:
                return record[field_name]
        return False

    def _rep__get_observation(self, record):
        for field_name in ('observaciones', 'observacion', 'nota', 'detalle'):
            if field_name in record._fields and record[field_name]:
                return self._rep__html_to_text(record[field_name])
        return ''

    def _rep__get_component_subparts(self, evaluacion):
        """Devuelve las subpartes seleccionadas para una recomendación."""
        return self._rep__unique(self.get_subpartes_componente(evaluacion))

    def _rep__component_dict(self, evaluacion):
        tipo = evaluacion.componente_tipo_id
        estado = evaluacion.estado_id
        return {
            'evaluacion_id': evaluacion.id,
            'tipo_code': self._rep__safe_code(tipo.code if tipo else ''),
            'nombre': self._get_nombre_componente_con_color(evaluacion),
            'estado_code': self._rep__safe_code(estado.code if estado else ''),
            'estado_nombre': estado.name if estado else 'Sin estado',
            'observaciones': self._rep__get_observation(evaluacion),
            'subpartes': self._rep__get_component_subparts(evaluacion),
        }

    def _rep__collect_relevant_data(self):
        """
        Lee todo el checklist, pero devuelve únicamente información útil para
        redactar el informe. Los estados normales se usan para saber si hubo
        pruebas, pero no se enumeran.
        """
        self.ensure_one()
        data = {
            'requiere_cambio': [],
            'desgaste': [],
            'mantenimiento': [],
            'fallas_componentes': [],
            'pendientes_componentes': [],
            'funciones_ok': [],
            'funciones_falla': [],
            'funciones_pendientes': [],
            'toners_relevantes': [],
            'estado_fisico': [],
            'accesorios_relevantes': [],
            'componentes_ok_count': 0,
            'evaluados_count': 0,
        }

        ok_codes = {'correcto', 'revisado', 'nuevo', 'bueno', 'operativo'}
        desgaste_codes = {'regular', 'gastada_pero_puede_trabajar'}
        mantenimiento_codes = {'mantenimiento'}
        cambio_codes = {'requiere_cambio'}
        falla_codes = {'falla'}
        pendiente_codes = {'sin_revisar', 'sin_probar'}
        toner_relevante = {
            'toner_40', 'toner_30', 'toner_25', 'toner_20', 'toner_10',
            'toner_vacio', 'toner_sin_contenedor', 'vacio', 'sin_botella',
        }
        fisicos = {
            'carcasa_amarilla', 'carcasa_rota', 'carcasa_faltante',
            'panel_amarillo',
        }

        for evaluacion in self.evaluacion_ids:
            if not evaluacion.componente_tipo_id:
                continue
            item = self._rep__component_dict(evaluacion)
            tipo_code = item['tipo_code'].upper()
            estado_code = item['estado_code']
            data['evaluados_count'] += 1

            if tipo_code.startswith('FUNCION_'):
                if estado_code in falla_codes:
                    data['funciones_falla'].append(item)
                elif estado_code in pendiente_codes or not estado_code:
                    data['funciones_pendientes'].append(item)
                elif estado_code not in {'no_aplica', 'no_instalado'}:
                    data['funciones_ok'].append(item)
                continue

            if tipo_code == 'TONER_SYSTEM':
                if estado_code in toner_relevante:
                    data['toners_relevantes'].append(item)
                continue

            if tipo_code in {'CARCASA', 'PANEL_CONTROL'}:
                if estado_code in fisicos:
                    data['estado_fisico'].append(item)
                continue

            if estado_code in cambio_codes:
                data['requiere_cambio'].append(item)
            elif estado_code in desgaste_codes:
                data['desgaste'].append(item)
            elif estado_code in mantenimiento_codes:
                data['mantenimiento'].append(item)
            elif estado_code in falla_codes:
                data['fallas_componentes'].append(item)
            elif estado_code in pendiente_codes or not estado_code:
                data['pendientes_componentes'].append(item)
            elif estado_code in ok_codes:
                data['componentes_ok_count'] += 1

        for accesorio in self._rep__get_accessory_records():
            tipo = self._rep__get_accessory_type(accesorio)
            estado = self._rep__get_accessory_state(accesorio)
            if not tipo or not estado:
                continue
            code = self._rep__safe_code(estado.code)
            if code in {'instalado_operativo', 'no_aplica'}:
                continue
            if code not in {'instalado_con_falla', 'no_instalado', 'wifi_sin_senal'}:
                continue
            data['accesorios_relevantes'].append({
                'nombre': tipo.name,
                'tipo_code': self._rep__safe_code(getattr(tipo, 'code', '')),
                'estado_code': code,
                'estado_nombre': estado.name,
                'observaciones': self._rep__get_observation(accesorio),
            })

        data['snmp'] = self._rep__get_snmp_test_data()
        return data

    def _rep__get_snmp_test_data(self):
        """
        Obtiene información SNMP relacionada con la reparación.

        La información SNMP es secundaria:
        - confirma actividad registrada;
        - muestra alertas observadas durante la revisión;
        - no determina la calidad técnica;
        - no utiliza niveles de tóner ni vida de unidades.
        """
        self.ensure_one()

        result = {
            'disponible': False,
            'prueba_id': False,
            'fecha': False,
            'actividades': [],
            'cantidad_alertas': 0,
            'alertas': [],
        }

        Prueba = self.env.get('sat.prueba.maquina')
        if not Prueba:
            _logger.warning(
                '[INFORME SNMP] No existe sat.prueba.maquina | reparación=%s',
                self.id,
            )
            return result

        # ======================================================
        # BUSCAR PRUEBA
        # ======================================================
        prueba = Prueba.sudo().search(
            [('reparacion_id', '=', self.id)],
            order='fecha_ultima_actualizacion desc, fecha_inicio desc, id desc',
            limit=1,
        )

        origen = 'reparacion_id'

        if not prueba and self.maquina_id:
            prueba = Prueba.sudo().search(
                [('maquina_id', '=', self.maquina_id.id)],
                order='fecha_ultima_actualizacion desc, fecha_inicio desc, id desc',
                limit=1,
            )
            origen = 'maquina_id'

        if not prueba:
            _logger.warning(
                '[INFORME SNMP] Sin prueba | reparación=%s máquina=%s',
                self.id,
                self.maquina_id.id if self.maquina_id else False,
            )
            return result

        # ======================================================
        # ACTIVIDADES REGISTRADAS
        # ======================================================
        actividades = []

        campos_actividad = [
            ('prueba_copia_ok', 'Copia'),
            ('prueba_impresion_ok', 'Impresión'),
            ('prueba_scanner_ok', 'Escaneo'),
            ('prueba_duplex_ok', 'Dúplex'),
            ('prueba_bn_ok', 'Blanco y negro'),
            ('prueba_color_ok', 'Color'),
        ]

        for field_name, etiqueta in campos_actividad:
            if field_name in prueba._fields and prueba[field_name]:
                actividades.append(etiqueta)

        # Respaldo directo mediante deltas.
        campos_delta = [
            ('delta_copias', 'Copia'),
            ('delta_impresiones', 'Impresión'),
            ('delta_scanner', 'Escaneo'),
            ('delta_duplex', 'Dúplex'),
            ('delta_bn', 'Blanco y negro'),
            ('delta_color', 'Color'),
        ]

        for field_name, etiqueta in campos_delta:
            if (
                field_name in prueba._fields
                and (prueba[field_name] or 0) > 0
                and etiqueta not in actividades
            ):
                actividades.append(etiqueta)

        # ======================================================
        # BUSCAR ALERTAS DIRECTAMENTE
        # ======================================================
        AlertModel = self.env.get('sat.prueba.maquina.snmp.alerta')
        registros_alerta = self.env['ir.model'].browse([])

        if AlertModel:
            dominio_alertas = ['|', '|',
                ('prueba_id', '=', prueba.id),
                ('reparacion_id', '=', self.id),
                ('maquina_id', '=', self.maquina_id.id if self.maquina_id else False),
            ]

            registros_alerta = AlertModel.sudo().search(
                dominio_alertas,
                order='fecha asc, id asc',
            )

        # Respaldo desde el One2many.
        if not registros_alerta and 'snmp_alerta_ids' in prueba._fields:
            registros_alerta = prueba.snmp_alerta_ids.sudo()

        alertas = []
        alertas_vistas = set()

        for alerta in registros_alerta:
            descripcion = str(
                getattr(alerta, 'descripcion', '') or ''
            ).strip()

            codigo = str(
                getattr(alerta, 'codigo', '') or ''
            ).strip()

            ubicacion = str(
                getattr(alerta, 'ubicacion', '') or ''
            ).strip()

            severidad = str(
                getattr(alerta, 'severidad', '') or ''
            ).strip()

            if not descripcion and not codigo:
                continue

            clave = (
                descripcion.lower(),
                codigo.lower(),
                ubicacion.lower(),
            )

            if clave in alertas_vistas:
                continue

            alertas_vistas.add(clave)

            alertas.append({
                'descripcion': descripcion or codigo,
                'codigo': codigo,
                'ubicacion': ubicacion,
                'severidad': severidad,
            })

        result.update({
            'disponible': True,
            'prueba_id': prueba.id,
            'fecha': (
                prueba.fecha_ultima_actualizacion
                or prueba.fecha_inicio
                or False
            ),
            'actividades': actividades,
            'cantidad_alertas': len(alertas),
            'alertas': alertas,
        })

        _logger.warning(
            '[INFORME SNMP RESULTADO] reparación=%s máquina=%s '
            'prueba=%s origen=%s actividades=%s '
            'registros_alerta=%s alertas_finales=%s',
            self.id,
            self.maquina_id.id if self.maquina_id else False,
            prueba.id,
            origen,
            actividades,
            len(registros_alerta),
            len(alertas),
        )

        return result

    def _rep__join_human_list(self, values):
        """Une una lista corta en español sin modificar sus valores."""
        values = [str(value).strip() for value in (values or []) if str(value).strip()]
        if not values:
            return ''
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return '%s y %s' % (values[0], values[1])
        return '%s y %s' % (', '.join(values[:-1]), values[-1])

    def _rep__general_status_text(self, data):
        """
        Redacción prudente del resultado general.

        El checklist determina si una función está correcta, con falla o
        pendiente. SNMP solamente confirma que hubo actividad durante la prueba.
        """
        snmp = data.get('snmp') or self._rep__get_snmp_test_data()
        actividades = snmp.get('actividades') or []
        actividad_texto = self._rep__join_human_list(actividades)

        if data['funciones_falla']:
            if actividad_texto:
                return (
                    'Durante la evaluación se registró actividad de %s. De acuerdo con '
                    'la revisión del técnico, se detectaron incidencias en las funciones '
                    'señaladas.'
                ) % actividad_texto
            return (
                'Durante la revisión y las pruebas realizadas se detectaron incidencias '
                'en las funciones señaladas por el técnico.'
            )

        if data['funciones_ok'] and data['funciones_pendientes']:
            if actividad_texto:
                return (
                    'Durante la evaluación se registró actividad de %s. Las funciones '
                    'verificadas por el técnico respondieron operativamente y quedaron '
                    'algunas pruebas pendientes.'
                ) % actividad_texto
            return (
                'Se realizaron pruebas generales de funcionamiento. Las funciones '
                'verificadas por el técnico respondieron operativamente, aunque quedaron '
                'pruebas pendientes.'
            )

        if data['funciones_ok']:
            if actividad_texto:
                return (
                    'Durante la evaluación se registró actividad de %s. Las funciones '
                    'verificadas por el técnico respondieron operativamente.'
                ) % actividad_texto
            return (
                'Se realizaron pruebas generales de funcionamiento y las funciones '
                'verificadas por el técnico respondieron operativamente.'
            )

        if actividad_texto:
            return (
                'Durante la evaluación se registró actividad de %s. La condición de las '
                'funciones y componentes corresponde a la revisión registrada por el técnico.'
            ) % actividad_texto

        return 'Se realizó una revisión general del equipo de acuerdo con el checklist técnico.'

    # ========================================
    # EXTRACCIÓN DE DATOS DESDE EVALUACIONES
    # ========================================
    def _rep__funciones_con_falla(self):
        data = self._rep__collect_relevant_data()
        return [item['nombre'] for item in data['funciones_falla']]

    def _rep__toners_criticos(self):
        data = self._rep__collect_relevant_data()
        return [item['nombre'] for item in data['toners_relevantes']]

    def _rep__collect_findings(self):
        """Compatibilidad con la lógica anterior usando la nueva clasificación."""
        data = self._rep__collect_relevant_data()
        cambio = [x['nombre'] for x in data['requiere_cambio']]
        cambio += [x['nombre'] for x in data['fallas_componentes']]
        desgaste = [x['nombre'] for x in data['desgaste'] + data['mantenimiento']]
        pendientes = [x['nombre'] for x in data['pendientes_componentes']]
        pendientes += [x['nombre'] for x in data['funciones_pendientes']]
        return {
            'cambio_inmediato': self._rep__unique(cambio),
            'desgaste': self._rep__unique(desgaste),
            'pendientes': self._rep__unique(pendientes),
            'no_aplica': [],
            'score': (
                len(cambio) * 6
                + len(desgaste) * 3
                + len(pendientes)
            ),
        }

    def _rep__calc_calidad(self, findings, funciones_falla, toners_criticos):
        """Calidad de respaldo; calidad_id sigue teniendo prioridad."""
        if findings['cambio_inmediato'] or funciones_falla or toners_criticos:
            return 'mala'
        if findings['desgaste'] or findings['pendientes']:
            return 'regular'
        return 'buena'

    def _rep__status_visual(self, estado_code):
        """Devuelve etiqueta y colores del estado para tarjetas HTML."""
        code = self._rep__safe_code(estado_code)
        mapping = {
            'requiere_cambio': ('Requiere cambio', '#c62828', '#ffebee'),
            'cambio_de_repuestos': ('Cambio recomendado', '#c62828', '#ffebee'),
            'falla': ('Falla detectada', '#b71c1c', '#fce4ec'),
            'gastada_pero_puede_trabajar': ('Presenta desgaste, pero puede trabajar', '#ef6c00', '#fff3e0'),
            'regular': ('Estado regular', '#ef6c00', '#fff8e1'),
            'mantenimiento': ('Mantenimiento recomendado', '#8d6e00', '#fffde7'),
            'sin_revisar': ('Sin revisar', '#616161', '#f5f5f5'),
            'sin_probar': ('Sin probar', '#616161', '#f5f5f5'),
            'toner_vacio': ('Tóner vacío', '#c62828', '#ffebee'),
            'vacio': ('Tóner vacío', '#c62828', '#ffebee'),
            'toner_sin_contenedor': ('Sin botella de tóner', '#ef6c00', '#fff3e0'),
            'sin_botella': ('Sin botella de tóner', '#ef6c00', '#fff3e0'),
            'carcasa_rota': ('Daño físico', '#c62828', '#ffebee'),
            'carcasa_faltante': ('Piezas faltantes', '#c62828', '#ffebee'),
            'carcasa_amarilla': ('Decoloración por uso', '#8d6e00', '#fffde7'),
            'panel_amarillo': ('Decoloración por uso', '#8d6e00', '#fffde7'),
            'instalado_con_falla': ('Instalado con falla', '#b71c1c', '#fce4ec'),
            'wifi_sin_senal': ('Sin señal', '#ef6c00', '#fff3e0'),
            'no_instalado': ('No instalado', '#616161', '#f5f5f5'),
        }
        return mapping.get(code, ('Observación', '#616161', '#f5f5f5'))

    def _rep__build_component_card(self, item, texto=None):
        """
        Construye una tarjeta ordenada por componente. Las subpartes se muestran
        debajo y conservan exactamente el nombre registrado en subparte_id.name.
        """
        etiqueta, borde, fondo = self._rep__status_visual(item.get('estado_code'))
        nombre = self._rep__escape(item.get('nombre'))
        parts = [
            f'<div style="margin:10px 0;padding:11px 14px;border-left:5px solid {borde};'
            f'background:{fondo};border-radius:6px;">',
            f'<div style="font-weight:bold;color:{borde};margin-bottom:6px;">{nombre}'
            f'<span style="font-weight:normal;"> — {self._rep__escape(etiqueta)}</span></div>',
        ]
        if texto:
            parts.append(f'<div style="margin:0 0 7px 0;color:#333;">{texto}</div>')
        subpartes = item.get('subpartes') or []
        if subpartes:
            parts.append('<div style="font-weight:bold;color:#444;margin:5px 0 3px 12px;">Subpartes recomendadas:</div>')
            parts.append('<ul style="margin:0 0 0 34px;padding:0;color:#333;">')
            for subparte in subpartes:
                parts.append(f'<li style="margin:4px 0;">{self._rep__escape(subparte)}</li>')
            parts.append('</ul>')
        obs = item.get('observaciones')
        if obs:
            parts.append(
                f'<div style="margin-top:8px;color:#444;"><strong>Observación del técnico:</strong> '
                f'{self._rep__escape(obs)}</div>'
            )
        parts.append('</div>')
        return ''.join(parts)

    def _rep__build_simple_card(self, titulo, estado_code, texto, observacion=''):
        etiqueta, borde, fondo = self._rep__status_visual(estado_code)
        parts = [
            f'<div style="margin:10px 0;padding:11px 14px;border-left:5px solid {borde};'
            f'background:{fondo};border-radius:6px;">',
            f'<div style="font-weight:bold;color:{borde};margin-bottom:5px;">'
            f'{self._rep__escape(titulo)}<span style="font-weight:normal;"> — '
            f'{self._rep__escape(etiqueta)}</span></div>',
            f'<div style="color:#333;">{texto}</div>',
        ]
        if observacion:
            parts.append(
                f'<div style="margin-top:7px;color:#444;"><strong>Observación del técnico:</strong> '
                f'{self._rep__escape(observacion)}</div>'
            )
        parts.append('</div>')
        return ''.join(parts)

    def _rep__build_snmp_alerts_block(self, snmp_data):
        """
        Muestra la actividad y las alertas registradas durante la revisión.

        La información se presenta únicamente como referencia de la evaluación.
        """
        snmp_data = snmp_data or {}

        if not snmp_data.get('disponible'):
            return ''

        actividades = snmp_data.get('actividades') or []
        alertas = snmp_data.get('alertas') or []

        parts = [
            '<div style="margin:12px 0;padding:11px 14px;'
            'border-left:5px solid #546e7a;'
            'background:#eceff1;border-radius:6px;color:#263238;">',

            '<div style="font-weight:bold;color:#37474f;'
            'margin-bottom:6px;">'
            'Información registrada durante las pruebas'
            '</div>',

            '<div style="margin-bottom:8px;color:#455a64;">'
            'La siguiente información fue registrada mientras se realizaba '
            'la revisión del equipo y se incluye únicamente como referencia.'
            '</div>',
        ]

        # ======================================================
        # ACTIVIDADES
        # ======================================================
        if actividades:
            parts.append(
                '<div style="font-weight:bold;margin:7px 0 4px 0;">'
                'Actividad detectada:</div>'
            )
            parts.append(
                '<ul style="margin:0 0 8px 24px;padding:0;">'
            )

            for actividad in actividades:
                parts.append(
                    '<li style="margin:3px 0;">%s</li>'
                    % self._rep__escape(actividad)
                )

            parts.append('</ul>')
        else:
            parts.append(
                '<div style="margin:6px 0;color:#607d8b;">'
                'Se encontró el registro de prueba, pero no se detectaron '
                'incrementos de actividad en los contadores consultados.'
                '</div>'
            )

        # ======================================================
        # ALERTAS
        # ======================================================
        if alertas:
            parts.append(
                '<div style="font-weight:bold;margin:9px 0 4px 0;">'
                'Alertas mostradas durante la revisión:</div>'
            )

            parts.append(
                '<ul style="margin:0 0 0 24px;padding:0;">'
            )

            for alerta in alertas:
                if isinstance(alerta, dict):
                    descripcion = str(
                        alerta.get('descripcion') or ''
                    ).strip()

                    codigo = str(
                        alerta.get('codigo') or ''
                    ).strip()

                    ubicacion = str(
                        alerta.get('ubicacion') or ''
                    ).strip()
                else:
                    descripcion = str(alerta or '').strip()
                    codigo = ''
                    ubicacion = ''

                if not descripcion and not codigo:
                    continue

                linea = []

                if descripcion:
                    linea.append(self._rep__escape(descripcion))

                if ubicacion:
                    linea.append(
                        'Ubicación: %s'
                        % self._rep__escape(ubicacion)
                    )

                if (
                    codigo
                    and codigo.lower() not in descripcion.lower()
                ):
                    linea.append(
                        'Código: %s'
                        % self._rep__escape(codigo)
                    )

                parts.append(
                    '<li style="margin:4px 0;">%s</li>'
                    % ' — '.join(linea)
                )

            parts.append('</ul>')
        else:
            parts.append(
                '<div style="margin-top:8px;color:#607d8b;">'
                'No se registraron alertas SNMP en esta prueba.'
                '</div>'
            )

        parts.extend([
            '<div style="margin-top:9px;font-size:12px;color:#607d8b;">'
            'Esta información corresponde al momento de la revisión y puede '
            'variar después de instalar consumibles, cerrar cubiertas, '
            'reiniciar el equipo o repetir las pruebas.'
            '</div>',
            '</div>',
        ])

        return ''.join(parts)

    def _rep__default_conclusion(self, calidad):
        """Conclusión comercial sin convertir las recomendaciones en trabajos obligatorios."""
        if calidad == 'buena':
            return (
                'El equipo presenta una condición general favorable y puede ofrecerse en su '
                'condición evaluada, considerando el mantenimiento estándar que corresponda.'
            )
        if calidad == 'regular':
            return (
                'El equipo presenta observaciones preventivas. Puede ofrecerse en su condición '
                'evaluada o considerando los repuestos recomendados, según el acuerdo de venta.'
            )
        return (
            'El equipo presenta observaciones relevantes en los componentes indicados. Puede '
            'ofrecerse en su condición evaluada o incluir los repuestos recomendados, según el '
            'acuerdo de venta.'
        )

    def _rep__build_informe_html_from_data(self, data, calidad, resumen=None, conclusion=None):
        """
        Construye el informe comercial para ventas.

        La redacción puede venir de IA o del modo automático, pero el detalle
        técnico visible se limita estrictamente a evaluaciones con estado
        exacto ``requiere_cambio`` y sus subpartes seleccionadas.
        """
        self.ensure_one()

        requiere_cambio = [
            item for item in (data.get('requiere_cambio') or [])
            if self._rep__safe_code(item.get('estado_code')) == 'requiere_cambio'
        ]

        if not resumen:
            if requiere_cambio:
                resumen = (
                    'Se realizó la revisión técnica del equipo de acuerdo con el checklist registrado. '
                    'Durante la evaluación se identificaron componentes que requieren cambio. '
                    'A continuación se detallan únicamente los componentes y subpartes considerados '
                    'para cambio, con el fin de facilitar la evaluación comercial.'
                )
            else:
                resumen = (
                    'Se realizó la revisión técnica del equipo de acuerdo con el checklist registrado. '
                    'En esta evaluación no se identificaron componentes con estado Requiere cambio.'
                )

        if not conclusion:
            if requiere_cambio:
                conclusion = (
                    'Los componentes indicados corresponden exclusivamente a los elementos registrados '
                    'por el técnico con estado Requiere cambio y pueden ser considerados por ventas '
                    'al momento de definir las condiciones comerciales.'
                )
            else:
                conclusion = (
                    'En esta evaluación no se registraron componentes con estado Requiere cambio.'
                )

        parts = [
            '<div data-autogen="1" style="font-family:Arial;line-height:1.55;color:#222;">',
            f'<p style="margin:0 0 14px 0;">{self._rep__escape(resumen)}</p>',
        ]

        if requiere_cambio:
            parts.append(
                '<h4 style="margin:0 0 10px 0;font-size:16px;color:#c62828;">'
                'Componentes que requieren cambio'
                '</h4>'
            )
            for item in requiere_cambio:
                parts.append(self._rep__build_component_card(item))
        else:
            parts.append(
                '<div style="margin:8px 0;padding:11px 14px;'
                'background:#f5f5f5;border-left:5px solid #757575;'
                'border-radius:6px;color:#424242;">'
                'No se registraron componentes con estado <strong>Requiere cambio</strong>.'
                '</div>'
            )

        parts.append('<h5 style="margin:15px 0 7px;font-size:15px;">Conclusión</h5>')
        parts.append(
            '<div style="padding:11px 14px;border-radius:6px;background:#f5f5f5;color:#424242;">'
            f'{self._rep__escape(conclusion)}</div>'
        )
        parts.append(
            '<div style="margin-top:12px;padding:10px 13px;border-left:5px solid #607d8b;'
            'background:#eef3f8;border-radius:6px;color:#37474f;">'
            '<strong>Importante:</strong> Para mayor detalle sobre el estado general del equipo, '
            'revise el checklist técnico y la sección de accesorios registrados en la evaluación.'
            '</div>'
        )
        parts.append('</div>')
        return ''.join(parts)

    def _rep__build_informe_html(self):
        """Genera el informe automático con tarjetas ordenadas y colores por estado."""
        self.ensure_one()
        data = self._rep__collect_relevant_data()
        findings = self._rep__collect_findings()
        calidad = self._rep__get_calidad_actual(
            findings=findings,
            funciones_falla=[x['nombre'] for x in data['funciones_falla']],
            toners_criticos=[x['nombre'] for x in data['toners_relevantes']],
        )
        return self._rep__build_informe_html_from_data(data, calidad), calidad

    def _generar_subpartes_estructuradas(self):
        """
        Compatibilidad: lista subpartes asociadas a evaluaciones marcadas como
        requiere cambio. No interpreta la intervención como trabajo realizado.
        """
        items = self._rep__collect_relevant_data()['requiere_cambio']
        con_subpartes = [x for x in items if x['subpartes']]
        if not con_subpartes:
            return ''
        html_parts = ['<ul style="margin:5px 0 10px 20px;">']
        for item in con_subpartes:
            html_parts.append(f'<li><strong>{self._rep__escape(item["nombre"])}</strong><ul>')
            for subparte in item['subpartes']:
                html_parts.append(f'<li>{self._rep__escape(subparte)}</li>')
            html_parts.append('</ul></li>')
        html_parts.append('</ul>')
        return ''.join(html_parts)

    def _generar_texto_repuestos(self):
        """Genera texto corto de subpartes que requieren cambio"""
        if not self.intervencion_ids:
            return ""

        intervenciones_con_detalles = self.intervencion_ids.filtered(lambda x: x.detalle_ids)
        if not intervenciones_con_detalles:
            return ""

        # Agrupar subpartes por componente
        componentes_con_subpartes = []
        for intervencion in intervenciones_con_detalles:
            codigo = intervencion.componente_code if intervencion.componente_code else intervencion.componente
            componente_nombre = self._get_component_display_name(codigo)
            
            subpartes = [d.subparte_id.name for d in intervencion.detalle_ids if d.subparte_id]
            if subpartes:
                subpartes_texto = ', '.join(subpartes)
                componentes_con_subpartes.append(f"{componente_nombre} ({subpartes_texto})")
        
        if not componentes_con_subpartes:
            return ""
        
        # Construir texto natural
        texto = "Específicamente: " + '; '.join(componentes_con_subpartes) + "."
        return texto

    def _generar_seccion_repuestos(self):
        """Genera la sección HTML de componentes y subpartes que requieren cambio (sin duplicados)."""
        if not self.intervencion_ids:
            _logger.debug("[_generar_seccion_repuestos] Sin intervenciones id=%s", self.id)
            return ""

        intervenciones_con_detalles = self.intervencion_ids.filtered(lambda x: x.detalle_ids)
        if not intervenciones_con_detalles:
            _logger.debug("[_generar_seccion_repuestos] Sin detalles en intervenciones id=%s", self.id)
            return ""

        repuestos_por_componente = {}
        for intervencion in intervenciones_con_detalles:
            # ✅ CAMBIO: Usar componente_code (dinámico) en lugar de componente (Selection)
            codigo = intervencion.componente_code if intervencion.componente_code else intervencion.componente
            componente_nombre = self._get_component_display_name(codigo)
            
            nombres = set()
            for detalle in intervencion.detalle_ids:
                if detalle.subparte_id:
                    nombres.add(detalle.subparte_id.name)
            if nombres:
                repuestos_por_componente[componente_nombre] = sorted(nombres)

        if not repuestos_por_componente:
            _logger.debug("[_generar_seccion_repuestos] No hay subpartes agrupadas id=%s", self.id)
            return ""

        html_componentes = []
        for componente, subpartes in repuestos_por_componente.items():
            html_componentes.append(f"<p style='margin:8px 0 4px 0; font-weight:bold;'>{componente}</p>")
            html_componentes.append("<ul style='margin:0 0 8px 20px;'>")
            for subparte in subpartes:
                html_componentes.append(f"<li>{subparte}</li>")
            html_componentes.append("</ul>")

        html = (
            f"<p style='margin:6px 0;color:#e65100;'><strong>{_('Subpartes específicas que requieren cambio')}:</strong></p>"
            f"<div style='margin:0 0 8px 10px;'>{''.join(html_componentes)}</div>"
        )
        _logger.debug("[_generar_seccion_repuestos] HTML subpartes len=%s id=%s", len(html), self.id)
        return html
    def _rep__get_calidad_actual(self, findings=None, funciones_falla=None, toners_criticos=None):
        """
        Devuelve la calidad actual que se debe usar en el informe:
        - Si calidad_id (Selection) está definida, usar ese valor ('buena', 'regular' o 'mala').
        - Si no está definida, calcula una calidad de respaldo usando los hallazgos.
        IMPORTANTE: Este método NO escribe nada en la BD, solo devuelve un string.
        """
        self.ensure_one()

        # 1) Si el usuario ya seleccionó la calidad en el checklist, usarla tal cual
        if self.calidad_id:
            return self.calidad_id

        # 2) Fallback: calcular a partir de los hallazgos (para registros antiguos)
        if findings is None:
            findings = self._rep__collect_findings()
        if funciones_falla is None:
            funciones_falla = self._rep__funciones_con_falla()
        if toners_criticos is None:
            toners_criticos = self._rep__toners_criticos()

        calidad_calc = self._rep__calc_calidad(findings, funciones_falla, toners_criticos)
        return calidad_calc or 'regular'

    def _get_component_display_name(self, componente_code):
        """
        Devuelve un nombre amigable para el código de componente usado en
        reparacion.intervencion.componente.

        Formato nuevo (dinámico):
          - "t<TIPO_ID>"
          - "t<TIPO_ID>_<k|c|m|y>"

        También soporta algunos códigos antiguos simples como "fuser", "itb",
        "adf", "fin", "opt", "papel", etc. por compatibilidad de pruebas.
        """
        if not componente_code:
            return ''

        code = str(componente_code).strip()

        # =========================
        # 1) ESQUEMA NUEVO: t<ID>[_color]
        # =========================
        m = re.match(r'^t(\d+)(?:_([kcmy]))?$', code)
        if m:
            tipo_id = int(m.group(1))
            color_code = m.group(2)

            Tipo = self.env['componente.tipo']
            tipo = Tipo.browse(tipo_id)

            if tipo and tipo.exists():
                nombre = tipo.name or f"Componente {tipo_id}"
            else:
                nombre = f"Componente {tipo_id}"

            # Mapear color a descripción legible
            if color_code:
                color_map = {
                    'k': 'Black',
                    'c': 'Cyan',
                    'm': 'Magenta',
                    'y': 'Yellow',
                }
                color_desc = color_map.get(color_code.lower(), color_code.upper())
                nombre = f"{nombre} ({color_desc})"

            _logger.debug(
                "[_get_component_display_name] code='%s' -> tipo_id=%s nombre='%s'",
                code, tipo_id, nombre
            )
            return nombre

        # =========================
        # 2) COMPATIBILIDAD LEGACY
        # (por si tienes registros viejos tipo 'fuser', 'ui_k', etc.)
        # =========================
        component_names = {
            'ui_k': 'Unidad de imagen Black',
            'ui_c': 'Unidad de imagen Cyan',
            'ui_m': 'Unidad de imagen Magenta',
            'ui_y': 'Unidad de imagen Yellow',
            'dev_k': 'Developer Black',
            'dev_c': 'Developer Cyan',
            'dev_m': 'Developer Magenta',
            'dev_y': 'Developer Yellow',
            'fuser': 'Fusora / Rodillos',
            'fusora': 'Fusora / Rodillos',
            'itb': 'Faja/Banda de transferencia',
            'adf': 'ADF',
            'fin': 'Finalizador',
            'finisher': 'Finalizador',
            'opt': 'Óptico',
            'papel': 'Transporte de papel',
            'tray': 'Bandejas de papel',
            'bypass': 'Bypass',
            'otro': 'Otro',
        }

        nombre_legacy = component_names.get(code.lower(), code)
        _logger.debug(
            "[_get_component_display_name] LEGACY code='%s' -> '%s'",
            code, nombre_legacy
        )
        return nombre_legacy


    # ========================================
    # GENERACIÓN CON IA
    # ========================================
    def _generar_informe_con_ia(self):
        """
        Genera una redacción natural con Gemini usando únicamente información
        permitida para ventas: componentes con estado exacto ``requiere_cambio``.
        No envía datos identificativos de la máquina. Python conserva el control
        del detalle HTML.
        """
        self.ensure_one()

        if not GEMINI_AVAILABLE:
            html, calidad = self._rep__build_informe_html()
            return html, calidad, 'Generado automáticamente: google-genai no está instalado.', False

        try:
            config_gemini = self.env['gemini.configuracion'].get_config_activa()
            gemini_setup = self._init_gemini_model(config_gemini)
            datos = self._preparar_datos_para_ia()
            prompt = self._construir_prompt_ia(datos)

            response = gemini_setup['client'].models.generate_content(
                model=gemini_setup['modelo'],
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=gemini_setup['temperature'],
                    max_output_tokens=gemini_setup['max_tokens'],
                    response_mime_type='application/json',
                )
            )

            resultado = self._parsear_respuesta_ia(response.text)
            calidad = datos['calidad_actual']
            data = self._rep__collect_relevant_data()

            informe_html = self._rep__build_informe_html_from_data(
                data,
                calidad,
                resumen=resultado.get('resumen_general'),
                conclusion=resultado.get('conclusion'),
            )

            config_gemini.incrementar_contador()
            return informe_html, calidad, resultado.get('justificacion_calidad', ''), True

        except Exception as e:
            _logger.exception('Error generando informe con IA: %s', e)
            html, calidad = self._rep__build_informe_html()
            return html, calidad, f'Generado automáticamente por error en IA: {e}', False

    def _init_gemini_model(self, config):
        """Inicializa cliente de Gemini (NUEVA SINTAXIS)"""
        # Crear cliente con API key
        client = genai.Client(api_key=config.api_key)
        
        # Retornar objeto con config
        return {
            'client': client,
            'modelo': config.modelo,
            'temperature': config.temperature,
            'max_tokens': config.max_output_tokens,
        }
    
    def _preparar_datos_para_ia(self):
        """
        Prepara únicamente la información comercial permitida para el informe:
        componentes con estado ``requiere_cambio`` y sus subpartes.
        """
        self.ensure_one()
        data = self._rep__collect_relevant_data()
        findings = self._rep__collect_findings()
        calidad = self._rep__get_calidad_actual(
            findings=findings,
            funciones_falla=[x['nombre'] for x in data['funciones_falla']],
            toners_criticos=[x['nombre'] for x in data['toners_relevantes']],
        )

        requiere_cambio = [
            item for item in (data.get('requiere_cambio') or [])
            if self._rep__safe_code(item.get('estado_code')) == 'requiere_cambio'
        ]

        return {
            'calidad_actual': calidad or 'regular',
            'requiere_cambio': requiere_cambio,
        }

    def _construir_prompt_ia(self, datos):
        """
        La IA redacta únicamente introducción y conclusión en lenguaje natural.
        No recibe otros estados del checklist, por lo que no puede incorporarlos
        al informe comercial.
        """
        componentes = []
        for item in (datos.get('requiere_cambio') or []):
            componentes.append({
                'nombre': item.get('nombre') or '',
                'subpartes': item.get('subpartes') or [],
                'observacion_tecnico': item.get('observaciones') or '',
            })

        hechos = {
            'componentes_requieren_cambio': componentes,
        }
        hechos_json = json.dumps(hechos, ensure_ascii=False, indent=2)
        calidad = datos.get('calidad_actual') or 'regular'

        return f"""
Redacta un informe técnico-comercial breve y natural, como lo escribiría una persona
responsable de taller después de revisar una máquina que será evaluada por el área de ventas.

Usa EXCLUSIVAMENTE los datos entregados abajo.

REGLAS OBLIGATORIAS:
1. El texto debe sonar humano, profesional, claro y sencillo; evita frases robóticas o repetitivas.
2. La introducción debe indicar de forma natural que se realizó la revisión/evaluación del equipo.
3. No menciones marca, modelo, serie, contador ni ningún dato identificativo de la máquina, porque esos datos ya aparecen en el formulario.
4. Solo puedes mencionar componentes incluidos en "componentes_requieren_cambio".
5. No menciones desgaste, mantenimiento, fallas adicionales, tóner, accesorios, SNMP,
   estado físico, componentes correctos, pruebas pendientes ni ningún otro estado del checklist.
6. No inventes piezas, causas, daños, pruebas ni trabajos realizados.
7. "Requiere cambio" significa que el técnico lo registró para considerar su cambio;
   nunca afirmes que la pieza ya fue reemplazada.
8. No digas que el equipo está inoperativo, que no puede venderse o que una reparación es
   obligatoria, salvo que esos hechos aparezcan expresamente en los datos (no los infieras).
9. No enumeres las subpartes en el resumen ni en la conclusión, porque Python las mostrará después.
10. No menciones la calidad "{calidad}" en el texto. Se conserva solo como dato interno del sistema.
11. Si no hay componentes en "componentes_requieren_cambio", indica únicamente que después de la
    revisión no se registraron componentes con estado Requiere cambio.
12. La conclusión debe servir a ventas: indicar que los componentes detallados son los registrados
    por el técnico para considerar su cambio dentro de las condiciones comerciales del equipo.
13. El resumen debe tener entre 2 y 4 oraciones y la conclusión entre 1 y 2 oraciones.

DATOS PERMITIDOS:
{hechos_json}

Devuelve únicamente JSON válido con esta estructura:
{{
  "calidad": "{calidad}",
  "justificacion_calidad": "Redacción comercial basada únicamente en componentes con estado Requiere cambio",
  "resumen_general": "texto natural de introducción",
  "conclusion": "texto natural de conclusión"
}}
"""

    def _parsear_respuesta_ia(self, response_text):
        """Parsea y valida la respuesta JSON de Gemini."""
        try:
            texto = (response_text or '').strip()
            texto = re.sub(r'^```(?:json)?\s*', '', texto, flags=re.I)
            texto = re.sub(r'\s*```$', '', texto)
            resultado = json.loads(texto)
            if not isinstance(resultado, dict):
                raise ValueError('La respuesta no es un objeto JSON.')
            if not resultado.get('resumen_general'):
                raise ValueError("Respuesta sin 'resumen_general'.")
            if not resultado.get('conclusion'):
                raise ValueError("Respuesta sin 'conclusion'.")
            resultado.setdefault('calidad', '')
            resultado.setdefault('justificacion_calidad', '')
            # La IA ya no devuelve HTML; Python construye toda la estructura visual.
            return resultado
        except Exception as e:
            _logger.error('Respuesta IA inválida: %s', (response_text or '')[:800])
            raise UserError(_('La IA generó una respuesta inválida: %s') % e)

    def _check_campos_requieren_cambio_sin_intervencion(self):
        """
        Devuelve evaluaciones que requieren cambio y NO tienen intervención con subpartes.
        Se deduplica por componente_code para no repetir el mismo componente en el wizard.
        """
        self.ensure_one()
        _logger.info("[_check_campos_requieren_cambio_sin_intervencion] Inicio id=%s", self.id)

        componentes_pendientes = []
        seen = set()  # evita duplicados por componente_code

        for evaluacion in self.evaluacion_ids:
            if not evaluacion.estado_id or evaluacion.estado_id.code != 'requiere_cambio':
                continue

            componente_code = self._get_componente_code_from_evaluacion(evaluacion)
            if not componente_code:
                _logger.warning(
                    "[_check_campos_requieren_cambio_sin_intervencion] No se pudo mapear eval %s (tipo=%s color=%s)",
                    evaluacion.id,
                    evaluacion.componente_tipo_id and (evaluacion.componente_tipo_id.code or evaluacion.componente_tipo_id.name),
                    self._rep__get_color_code_from_eval(evaluacion),
                )
                continue

            # Si ya evaluamos este componente_code, saltar
            if componente_code in seen:
                _logger.debug(
                    "[_check_campos_requieren_cambio_sin_intervencion] componente_code '%s' ya considerado, se omite duplicado",
                    componente_code,
                )
                continue
            seen.add(componente_code)

            # 🔧 OJO: ahora se busca por componente_code dinámico, NO por componente (Selection)
            intervencion_existente = self.intervencion_ids.filtered(
                lambda x: x.componente_code == componente_code and x.detalle_ids
            )
            if not intervencion_existente:
                comp = {
                    'evaluacion_id': evaluacion.id,
                    'componente_code': componente_code,
                    'tipo_id': evaluacion.componente_tipo_id.id,
                    'color_code': self._rep__get_color_code_from_eval(evaluacion) or None,
                }
                _logger.debug("[_check_campos_requieren_cambio_sin_intervencion] pendiente=%s", comp)
                componentes_pendientes.append(comp)

        _logger.info(
            "[_check_campos_requieren_cambio_sin_intervencion] total_pendientes=%s id=%s",
            len(componentes_pendientes),
            self.id,
        )
        return componentes_pendientes



    def _get_componente_code_from_evaluacion(self, evaluacion):
        """
        Mapea una evaluación a su código de componente para intervenciones,
        de forma 100% dinámica.

        Nuevo formato de código:
          - Sin color:    t<TIPO_ID>
          - Con color:    t<TIPO_ID>_<k|c|m|y>

        Ejemplos:
          tipo_id = 15 (IU), color=k  -> "t15_k"
          tipo_id = 8  (Fusora) sin color -> "t8"
        """
        tipo = evaluacion.componente_tipo_id
        if not tipo:
            _logger.warning(
                "[_get_componente_code_from_evaluacion] Eval %s sin tipo",
                evaluacion.id
            )
            return False

        # base dinámico: prefijo "t" + id del tipo
        base_code = f"t{tipo.id}"

        # obtener color lógico k/c/m/y (si lo hay)
        color = self._rep__get_color_code_from_eval(evaluacion)

        # si el tipo es sensible a color, exigimos color
        if tipo.is_color_sensitive:
            if not color:
                _logger.warning(
                    "[_get_componente_code_from_evaluacion] Tipo '%s' (id=%s) "
                    "requiere color pero la evaluación %s no tiene color válido.",
                    tipo.name, tipo.id, evaluacion.id
                )
                return False
            componente_code = f"{base_code}_{color}"
        else:
            componente_code = base_code

        _logger.debug(
            "[_get_componente_code_from_evaluacion] eval=%s tipo='%s' (id=%s) "
            "is_color_sensitive=%s color=%s -> code='%s'",
            evaluacion.id,
            (tipo.code or tipo.name),
            tipo.id,
            tipo.is_color_sensitive,
            color,
            componente_code,
        )
        return componente_code

    def _map_componente_code_to_selection(self, componente_code):
        """
        Convierte un código dinámico (ui_k, dev_c, t88_k, etc.) en un valor
        válido para el Selection reparacion.intervencion.componente.

        - Si el código ya es uno de los permitidos, se usa tal cual.
        - Si no, cae a 'otro'.
        """
        if not componente_code:
            return 'otro'

        componente_code = str(componente_code).strip()
        allowed = {
            'ui_k', 'ui_c', 'ui_m', 'ui_y',
            'dev_k', 'dev_c', 'dev_m', 'dev_y',
            'fuser', 'itb', 'adf', 'fin',
            'opt', 'papel', 'otro',
        }
        if componente_code in allowed:
            return componente_code
        # cualquier cosa no mapeada (como 't88_k') va a 'otro'
        return 'otro'


    def _ensure_intervencion_for_component(self, componente_code):
        """Crea o retorna intervención existente para un componente (dinámico)."""
        self.ensure_one()
        Interv = self.env['reparacion.intervencion']

        # Buscar por código dinámico
        interv = Interv.search([
            ('reparacion_id', '=', self.id),
            ('componente_code', '=', componente_code),
        ], limit=1)

        if not interv:
            # mapear a valor Selection válido para campo 'componente'
            sel_value = self._map_componente_code_to_selection(componente_code)
            _logger.info(
                "[_ensure_intervencion_for_component] creando intervencion %s (selection=%s) para rep=%s",
                componente_code, sel_value, self.id
            )
            interv = Interv.create({
                'reparacion_id': self.id,
                'componente_code': componente_code,
                'componente': sel_value,
                'accion': 'cambiado',
                'observacion': _('Creado automáticamente al marcar "requiere cambio".'),
            })
        else:
            _logger.debug(
                "[_ensure_intervencion_for_component] usando intervencion id=%s (code=%s)",
                interv.id, componente_code
            )
        return interv


    # ========================================
    # WIZARD DE SUBPARTES
    # ========================================
    def _abrir_wizard_multiple_componentes(self, componentes_pendientes):
        self.ensure_one()
        _logger.info("[_abrir_wizard_multiple_componentes] start id=%s count=%s", self.id, len(componentes_pendientes))
        if not componentes_pendientes:
            return

        wizard = self.env['reparacion.add.subparts.wizard'].create({'reparacion_id': self.id})

        modelo_maquina = self.maquina_id
        if not modelo_maquina:
            _logger.error("[_abrir_wizard_multiple_componentes] Máquina sin modelo id=%s", self.id)
            raise UserError(_("La máquina no tiene modelo asignado"))

        for comp_info in componentes_pendientes:
            componente_code = comp_info['componente_code']

            # Crear/obtener intervención (ya soporta componente_code + bucket)
            intervencion = self._ensure_intervencion_for_component(componente_code)

            # Evitar duplicados
            ya_existentes = set(intervencion.detalle_ids.mapped('subparte_id').ids)
            agregadas = set()

            # Buscar componentes del modelo
            componentes_modelo = self._buscar_componentes_modelo_por_evaluacion(modelo_maquina, comp_info)
            _logger.debug(
                "[_abrir_wizard_multiple_componentes] comp=%s encontró %s componentes modelo",
                componente_code, len(componentes_modelo)
            )

            total_lineas = 0

            # 1) Subpartes detalladas del modelo
            for componente_modelo in componentes_modelo:
                if not getattr(componente_modelo, 'detalle_ids', False):
                    continue

                for detalle in componente_modelo.detalle_ids:
                    sid = detalle.subparte_id.id
                    if not sid:
                        continue

                    if sid in ya_existentes or sid in agregadas:
                        continue

                    self.env['reparacion.add.subparts.wizard.line'].create({
                        'wizard_id': wizard.id,
                        'componente': 'otro',                 # <- FIJO: siempre 'otro' (campo legacy)
                        'componente_code': componente_code,   # <- DINÁMICO: el valor real
                        'intervencion_id': intervencion.id,
                        'subparte_id': sid,
                        'selected': False,
                        'accion_sub': 'cambiado',
                        'cantidad': detalle.cantidad or 1.0,
                    })

                    agregadas.add(sid)
                    total_lineas += 1

            # 2) Fallback genérico por tipo
            if total_lineas == 0:
                genericas = self._fallback_subpartes_por_tipo(comp_info['tipo_id'])
                if genericas:
                    _logger.warning(
                        "[_abrir_wizard_multiple_componentes] sin detalle_ids; usando %s subpartes genéricas por tipo.",
                        len(genericas)
                    )
                    for sp in genericas:
                        sid = sp.id
                        if not sid or sid in ya_existentes or sid in agregadas:
                            continue

                        self.env['reparacion.add.subparts.wizard.line'].create({
                            'wizard_id': wizard.id,
                            'componente': 'otro',                 # <- FIJO: siempre 'otro' (campo legacy)
                            'componente_code': componente_code,   # <- DINÁMICO: el valor real
                            'intervencion_id': intervencion.id,
                            'subparte_id': sid,
                            'selected': False,
                            'accion_sub': 'cambiado',
                            'cantidad': 1.0,
                        })

                        agregadas.add(sid)
                        total_lineas += 1

            # 3) Notificación si no se pudo encontrar nada
            if total_lineas == 0:
                self.message_post(body=_(
                    "No se hallaron subpartes para <b>%(nombre)s</b> %(color)s. "
                    "Completa el catálogo de <i>modelo.maquina.componente</i> o defínelas en <i>componente.subparte</i>.",
                ) % {
                    'nombre': self.env['componente.tipo'].browse(comp_info['tipo_id']).name,
                    'color': comp_info.get('color_code') and f"({comp_info['color_code'].upper()})" or "",
                })

        # Título dinámico del wizard
        nombres = []
        for comp in componentes_pendientes:
            eval_rec = self.env['reparacion.componente.evaluacion'].browse(comp['evaluacion_id'])
            nombre = eval_rec.componente_tipo_id.name
            if comp.get('color_code'):
                nombre = f"{nombre} ({comp['color_code'].upper()})"
            nombres.append(nombre)

        titulo = f"Subpartes para: {', '.join(nombres)}"
        _logger.info("[_abrir_wizard_multiple_componentes] wizard id=%s titulo='%s'", wizard.id, titulo)

        return self._abrir_wizard_multiple_componentes_con_contexto(
            componentes_pendientes,
            origen_accion='generar_informe',
            auto_finalize=False
        )
    def _buscar_componentes_modelo_por_evaluacion(self, modelo_maquina, comp_info):
        """
        Busca componentes del catálogo para poblar el wizard de subpartes con
        una estrategia de fallbacks:
          A) modelo + tipo + color
          B) modelo + tipo
          C) cualquier modelo + tipo
        """
        mmc = self.env['modelo.maquina.componente']
        color_code = comp_info.get('color_code')
        tipo_id = comp_info['tipo_id']

        def _dom(base, with_color):
            dom = list(base)
            if with_color and color_code:
                if 'color' in mmc._fields:
                    dom.append(('color', '=', color_code))
                elif 'color_id' in mmc._fields:
                    color_rec = self.env['color.tipo'].search([('code', '=', color_code)], limit=1)
                    if color_rec:
                        dom.append(('color_id', '=', color_rec.id))
            return dom

        # A) modelo + tipo + color
        domA = _dom([('modelo_id', '=', modelo_maquina.id), ('tipo_id', '=', tipo_id)], True)
        resA = mmc.search(domA)
        if resA:
            _logger.debug("[_buscar_componentes...] A) %s -> %s", domA, len(resA))
            return resA

        # B) modelo + tipo (sin color)
        domB = [('modelo_id', '=', modelo_maquina.id), ('tipo_id', '=', tipo_id)]
        resB = mmc.search(domB)
        if resB:
            _logger.warning("[_buscar_componentes...] sin match por color='%s'. Usando modelo+tipo. dom=%s -> %s",
                            color_code, domB, len(resB))
            return resB

        # C) cualquier modelo + tipo
        domC = [('tipo_id', '=', tipo_id)]
        resC = mmc.search(domC)
        if resC:
            _logger.warning("[_buscar_componentes...] sin match por modelo. Usando cualquier modelo con el mismo tipo. dom=%s -> %s",
                            domC, len(resC))
            return resC

        _logger.error("[_buscar_componentes...] Catálogo vacío para tipo_id=%s", tipo_id)
        return mmc.browse([])

    def _fallback_subpartes_por_tipo(self, tipo_id):
        """
        Último recurso: devuelve subpartes genéricas del tipo (sin depender del modelo).
        Requiere que exista el modelo 'componente.subparte' y tenga un campo 'tipo_id'.
        """
        Subparte = self.env.get('componente.subparte')
        if not Subparte:
            _logger.error("[_fallback_subpartes_por_tipo] No existe el modelo 'componente.subparte'")
            return self.env['ir.model'].browse([])

        # Intento 1: subpartes ligadas al tipo exacto
        if 'tipo_id' in Subparte._fields:
            res = Subparte.search([('tipo_id', '=', tipo_id)])
            if res:
                _logger.debug("[_fallback_subpartes_por_tipo] usando %s subpartes por tipo_id=%s", len(res), tipo_id)
                return res

        # Intento 2: cualquier subparte (muy laxo, solo para no dejar vacío)
        res_any = Subparte.search([], limit=10)
        if res_any:
            _logger.warning("[_fallback_subpartes_por_tipo] no hay subpartes por tipo; devolviendo %s subpartes arbitrarias.", len(res_any))
            return res_any

        _logger.error("[_fallback_subpartes_por_tipo] catálogo de subpartes vacío.")
        return Subparte.browse([])

    # ========================================
    # ACCIÓN DEL BOTÓN
    # ========================================
    def action_generar_informe(self):
        """Genera el informe o abre el wizard de subpartes requeridas."""
        acciones = []
        errores = []

        for rec in self:
            try:
                pendientes = rec._check_campos_requieren_cambio_sin_intervencion()
                if pendientes:
                    return rec._abrir_wizard_multiple_componentes_con_contexto(
                        pendientes,
                        origen_accion='generar_informe',
                        auto_finalize=False,
                    )

                if rec.informe and not rec._rep__html_is_empty(rec.informe) and not rec._rep__is_autogen_informe():
                    rec.message_post(body=_('El informe fue editado manualmente y no se sobrescribió.'))
                    continue

                if rec.modo_generacion_informe == 'ia':
                    html, calidad, justificacion, generado_con_ia = rec._generar_informe_con_ia()
                else:
                    html, calidad = rec._rep__build_informe_html()
                    justificacion = ''
                    generado_con_ia = False

                rec.write({
                    'informe': html,
                    'informe_generado_por_ia': generado_con_ia,
                    'calidad_justificacion': justificacion,
                })
                rec.message_post(body=(
                    _('✨ Informe técnico generado con IA.')
                    if generado_con_ia
                    else _('Informe técnico generado automáticamente.')
                ))
                acciones.append(rec.id)
            except Exception as e:
                _logger.exception('No se pudo generar el informe de %s', rec.id)
                errores.append(f'{rec.display_name}: {e}')
                rec.message_post(body=_('❌ No se pudo generar el informe: %s') % e)

        if self.env.context.get('from_finalizar_reparacion'):
            return False

        if errores and len(self) == 1:
            raise UserError(errores[0])

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informe técnico'),
                'message': (
                    _('✅ Informe generado correctamente.')
                    if acciones and not errores
                    else _('Se generaron %s informes y ocurrieron %s errores.') % (len(acciones), len(errores))
                    if acciones
                    else _('⚠️ No se generó ningún informe.')
                ),
                'type': 'success' if acciones and not errores else 'warning',
            }
        }

    def get_subpartes_accesorio(self, accesorio_eval):
        """
        Retorna lista de nombres de subpartes para un accesorio evaluado
        """
        if not accesorio_eval or not accesorio_eval.subparte_ids:
            return []
        return [sp.name for sp in accesorio_eval.subparte_ids]

    def get_subpartes_componente(self, componente_eval):
        """
        Retorna lista de nombres de subpartes para un componente evaluado.
        Busca en las intervenciones asociadas donde realmente están guardadas.
        """
        if not componente_eval:
            return []
        
        # Primero intentar desde el campo directo subpartes_ids (si está lleno)
        if hasattr(componente_eval, 'subpartes_ids') and componente_eval.subpartes_ids:
            return [sp.name for sp in componente_eval.subpartes_ids]
        
        # Si no hay, buscar en las intervenciones (DONDE REALMENTE ESTÁN)
        componente_code = self._get_componente_code_from_evaluacion(componente_eval)
        if not componente_code:
            _logger.debug("[get_subpartes_componente] No se pudo obtener código para eval %s", componente_eval.id)
            return []
        
        # ✅ CAMBIO: Buscar por componente_code (dinámico) en lugar de componente (Selection)
        intervencion = self.intervencion_ids.filtered(lambda x: x.componente_code == componente_code)
        if not intervencion or not intervencion.detalle_ids:
            _logger.debug("[get_subpartes_componente] No hay intervención/detalles para código %s", componente_code)
            return []
        
        # Retornar los nombres de las subpartes desde los detalles
        subpartes = [detalle.subparte_id.name for detalle in intervencion.detalle_ids if detalle.subparte_id]
        _logger.info("[get_subpartes_componente] eval=%s código=%s -> %s subpartes", componente_eval.id, componente_code, len(subpartes))
        return subpartes

    def _get_nombre_componente_con_color(self, eval_comp):
        """Nombre del componente con color, sin fallar en registros incompletos."""
        tipo = eval_comp.componente_tipo_id
        nombre = tipo.name if tipo else _('Componente sin definir')
        color_id = getattr(eval_comp, 'color_id', False)
        if color_id:
            color_map = {
                'k': 'Black', 'black': 'Black', 'negro': 'Black',
                'c': 'Cyan', 'cyan': 'Cyan',
                'm': 'Magenta', 'magenta': 'Magenta',
                'y': 'Yellow', 'yellow': 'Yellow', 'amarillo': 'Yellow',
            }
            code = self._rep__safe_code(getattr(color_id, 'code', ''))
            display = color_map.get(code, color_id.name)
            nombre = f'{nombre} ({display})'
        return nombre

    def _handle_subpartes_pendientes(self, origen_accion='generar_informe', auto_finalize=False):
        """
        Verifica si hay componentes con 'requiere_cambio' que NO tienen subpartes.
        Si los hay, abre el wizard para que el usuario las agregue.
        
        Args:
            origen_accion: 'generar_informe' o 'finalizar_reparacion'
            auto_finalize: Si True, después de confirmar el wizard se ejecutará
                        automáticamente action_finalizar_reparacion()
        
        Returns:
            - dict (acción del wizard) si hay pendientes
            - False si NO hay pendientes (puede continuar)
        """
        self.ensure_one()
        _logger.info(
            "[_handle_subpartes_pendientes] rep.id=%s origen=%s auto_finalize=%s",
            self.id, origen_accion, auto_finalize
        )
        
        # Si ya viene del wizard confirmado, no volver a abrir
        if self.env.context.get('skip_subpartes_validation'):
            _logger.info(
                "[_handle_subpartes_pendientes] rep.id=%s -> skip_subpartes_validation=True",
                self.id
            )
            return False
        
        # Buscar componentes pendientes (sin duplicados)
        componentes_pendientes = self._check_campos_requieren_cambio_sin_intervencion()
        
        if not componentes_pendientes:
            _logger.info(
                "[_handle_subpartes_pendientes] rep.id=%s -> No hay pendientes",
                self.id
            )
            return False
        
        # Hay pendientes → abrir wizard
        _logger.info(
            "[_handle_subpartes_pendientes] rep.id=%s -> %s componentes pendientes, abriendo wizard",
            self.id, len(componentes_pendientes)
        )
        
        return self._abrir_wizard_multiple_componentes_con_contexto(
            componentes_pendientes,
            origen_accion=origen_accion,
            auto_finalize=auto_finalize
        )


    def _abrir_wizard_multiple_componentes_con_contexto(self, componentes_pendientes, 
                                                        origen_accion='generar_informe', 
                                                        auto_finalize=False):
        """
        Abre el wizard de subpartes con contexto adicional para saber qué hacer al confirmar.
        
        Args:
            componentes_pendientes: Lista de dicts con info de componentes
            origen_accion: De dónde se llamó ('generar_informe' o 'finalizar_reparacion')
            auto_finalize: Si True, al confirmar wizard se finalizará automáticamente
        """
        self.ensure_one()
        _logger.info(
            "[_abrir_wizard_multiple_componentes_con_contexto] id=%s count=%s origen=%s auto_finalize=%s",
            self.id, len(componentes_pendientes), origen_accion, auto_finalize
        )
        
        if not componentes_pendientes:
            return False

        wizard = self.env['reparacion.add.subparts.wizard'].create({
            'reparacion_id': self.id
        })

        modelo_maquina = self.maquina_id
        if not modelo_maquina:
            _logger.error(
                "[_abrir_wizard_multiple_componentes_con_contexto] Máquina sin modelo id=%s",
                self.id
            )
            raise UserError(_("La máquina no tiene modelo asignado"))

        # Poblar líneas del wizard
        for comp_info in componentes_pendientes:
            componente_code = comp_info['componente_code']

            # Crear/obtener intervención
            intervencion = self._ensure_intervencion_for_component(componente_code)

            # Evitar duplicados
            ya_existentes = set(intervencion.detalle_ids.mapped('subparte_id').ids)
            agregadas = set()

            # Buscar componentes del modelo
            componentes_modelo = self._buscar_componentes_modelo_por_evaluacion(
                modelo_maquina, comp_info
            )
            _logger.debug(
                "[_abrir_wizard_multiple_componentes_con_contexto] comp=%s encontró %s componentes modelo",
                componente_code, len(componentes_modelo)
            )

            total_lineas = 0

            # 1) Subpartes detalladas del modelo
            for componente_modelo in componentes_modelo:
                if not getattr(componente_modelo, 'detalle_ids', False):
                    continue

                for detalle in componente_modelo.detalle_ids:
                    sid = detalle.subparte_id.id
                    if not sid:
                        continue

                    if sid in ya_existentes or sid in agregadas:
                        continue

                    self.env['reparacion.add.subparts.wizard.line'].create({
                        'wizard_id': wizard.id,
                        'componente': 'otro',
                        'componente_code': componente_code,
                        'intervencion_id': intervencion.id,
                        'subparte_id': sid,
                        'selected': False,
                        'accion_sub': 'cambiado',
                        'cantidad': detalle.cantidad or 1.0,
                    })

                    agregadas.add(sid)
                    total_lineas += 1

            # 2) Fallback genérico por tipo
            if total_lineas == 0:
                genericas = self._fallback_subpartes_por_tipo(comp_info['tipo_id'])
                if genericas:
                    _logger.warning(
                        "[_abrir_wizard_multiple_componentes_con_contexto] sin detalle_ids; "
                        "usando %s subpartes genéricas por tipo.",
                        len(genericas)
                    )
                    for sp in genericas:
                        sid = sp.id
                        if not sid or sid in ya_existentes or sid in agregadas:
                            continue

                        self.env['reparacion.add.subparts.wizard.line'].create({
                            'wizard_id': wizard.id,
                            'componente': 'otro',
                            'componente_code': componente_code,
                            'intervencion_id': intervencion.id,
                            'subparte_id': sid,
                            'selected': False,
                            'accion_sub': 'cambiado',
                            'cantidad': 1.0,
                        })

                        agregadas.add(sid)
                        total_lineas += 1

            # 3) Notificación si no se pudo encontrar nada
            if total_lineas == 0:
                self.message_post(body=_(
                    "No se hallaron subpartes para <b>%(nombre)s</b> %(color)s. "
                    "Completa el catálogo de <i>modelo.maquina.componente</i> o "
                    "defínelas en <i>componente.subparte</i>.",
                ) % {
                    'nombre': self.env['componente.tipo'].browse(comp_info['tipo_id']).name,
                    'color': comp_info.get('color_code') and f"({comp_info['color_code'].upper()})" or "",
                })

        # Título dinámico del wizard
        nombres = []
        for comp in componentes_pendientes:
            eval_rec = self.env['reparacion.componente.evaluacion'].browse(
                comp['evaluacion_id']
            )
            nombre = eval_rec.componente_tipo_id.name
            if comp.get('color_code'):
                nombre = f"{nombre} ({comp['color_code'].upper()})"
            nombres.append(nombre)

        titulo = f"Subpartes requeridas para: {', '.join(nombres)}"
        
        # Mensaje contextual según origen
        if origen_accion == 'finalizar_reparacion':
            mensaje = (
                "Estos componentes requieren cambio pero no tienen subpartes especificadas.\n"
                "Por favor, selecciona las subpartes necesarias antes de finalizar."
            )
        else:
            mensaje = (
                "Estos componentes requieren cambio pero no tienen subpartes especificadas.\n"
                "Por favor, selecciona las subpartes necesarias para generar el informe."
            )
        
        _logger.info(
            "[_abrir_wizard_multiple_componentes_con_contexto] wizard id=%s titulo='%s'",
            wizard.id, titulo
        )

        # Contexto para que el wizard sepa qué hacer al confirmar
        context = {
            'from_generar_informe': (origen_accion == 'generar_informe'),
            'from_finalizar_reparacion': (origen_accion == 'finalizar_reparacion'),
            'auto_finalize': auto_finalize,
        }

        return {
            'type': 'ir.actions.act_window',
            'name': titulo,
            'res_model': 'reparacion.add.subparts.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': self.env.ref('sat.view_reparacion_add_subparts_wizard_form').id,
            'target': 'new',
            'context': context,
        }
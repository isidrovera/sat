# -*- coding: utf-8 -*-
from odoo import _, models, fields, api
from odoo.exceptions import UserError
import logging
import re
import unicodedata
import json

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
    _description = 'Informe Reparaciones (Generación automática/IA con hallazgos)'

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
    # EXTRACCIÓN DE DATOS DESDE EVALUACIONES
    # ========================================
    def _rep__funciones_con_falla(self):
        """Lista funciones con falla (tipo FUNCION_*, estado 'falla')."""
        funciones_falla = []
        for eval_comp in self.evaluacion_ids:
            if not eval_comp.estado_id:
                continue
            tipo_code = (eval_comp.componente_tipo_id.code or '').strip().upper() if eval_comp.componente_tipo_id else ''
            if tipo_code.startswith('FUNCION_') and eval_comp.estado_id.code == 'falla':
                funciones_falla.append(eval_comp.componente_tipo_id.name)
        _logger.debug("[_rep__funciones_con_falla] id=%s -> %s", self.id, funciones_falla)
        return funciones_falla

    def _rep__toners_criticos(self):
        """Lista consumibles críticos (TONER_SYSTEM con estado 'vacio'/'sin_botella')."""
        toners_criticos = []
        for eval_comp in self.evaluacion_ids:
            if not eval_comp.estado_id:
                continue
            tipo_code = (eval_comp.componente_tipo_id.code or '').strip().upper() if eval_comp.componente_tipo_id else ''
            if tipo_code == 'TONER_SYSTEM' and eval_comp.estado_id.code in ('vacio', 'sin_botella'):
                nombre = eval_comp.componente_tipo_id.name
                if eval_comp.color_id:
                    nombre = f"{nombre} {eval_comp.color_id.name}"
                toners_criticos.append(nombre)
        _logger.debug("[_rep__toners_criticos] id=%s -> %s", self.id, toners_criticos)
        return toners_criticos

    def _rep__collect_findings(self):
        """
        Clasifica hallazgos desde evaluaciones.
        Retorna: cambio_inmediato, desgaste, pendientes, no_aplica, score.
        """
        cambio_inmediato, desgaste, pendientes, no_aplica = [], [], [], []
        score = 0

        # Componentes
        for eval_comp in self.evaluacion_ids:
            # Usar el método para obtener el nombre con color
            nombre = self._get_nombre_componente_con_color(eval_comp)
            
            if not eval_comp.estado_id:
                pendientes.append(nombre)
                score += 1
                continue

            estado_code = eval_comp.estado_id.code

            peso = 2
            if hasattr(eval_comp.componente_tipo_id, 'prioridad'):
                prioridad = eval_comp.componente_tipo_id.prioridad
                peso = {'1': 3, '2': 2, '3': 1}.get(prioridad, 2)

            if estado_code in ('requiere_cambio', 'cambio_de_repuestos', 'vacio', 'sin_botella', 'carcasa_rota', 'carcasa_faltante'):
                cambio_inmediato.append(nombre); score += 3 * peso
            elif estado_code in ('regular', 'gastada_pero_puede_trabajar', 'mantenimiento', 'carcasa_amarilla', 'panel_amarillo'):
                desgaste.append(nombre); score += 2 * peso
            elif estado_code in ('sin_revisar', 'sin_probar'):
                pendientes.append(nombre); score += 1 * peso
            elif estado_code == 'no_aplica':
                no_aplica.append(nombre)

        # NO incluir accesorios en el informe (como solicitaste)
        # for eval_acc in getattr(self, 'accesorio_eval_ids', self.env['reparacion.accesorio.evaluacion']):
        #     ...

        findings = {
            'cambio_inmediato': cambio_inmediato,
            'desgaste': desgaste,
            'pendientes': pendientes,
            'no_aplica': no_aplica,
            'score': score,
        }
        _logger.debug("[_rep__collect_findings] id=%s -> %s", self.id, findings)
        return findings

    def _rep__calc_calidad(self, findings, funciones_falla, toners_criticos):
        """Calcula calidad general."""
        if findings['cambio_inmediato'] or funciones_falla or toners_criticos:
            return 'mala'
        if findings['desgaste'] or findings['pendientes']:
            return 'regular'
        return 'buena'

    # ========================================
    # CONSTRUCCIÓN DEL INFORME HTML (AUTOMÁTICO)
    # ========================================
    def _rep__build_informe_html(self):
        """
        Construye un informe automático sin IA que:
        - Resume las intervenciones realizadas (componente, acción, subpartes reemplazadas)
        - Lista los componentes que requieren cambio con sus subpartes (si las hay)
        - Incluye observaciones del técnico
        NO incluye datos del equipo (marca/serie/contador).
        """
        self.ensure_one()
        _logger.info("[_rep__build_informe_html] Iniciando para reparacion id=%s", self.id)

        # 1) Intervenciones realizadas
        intervenciones = []
        for interv in self.intervencion_ids:
            comp = self._get_component_display_name(interv.componente_code or interv.componente)
            accion = interv.accion or ''
            subpartes = [d.subparte_id.name for d in interv.detalle_ids if d.subparte_id]
            obs_interv = getattr(interv, 'observacion', '') or getattr(interv, 'observaciones', '') or ''
            line = {
                'componente': comp,
                'accion': accion,
                'subpartes': subpartes,
                'observacion': obs_interv
            }
            intervenciones.append(line)

        # 2) Componentes que requieren cambio (desde evaluaciones)
        componentes_requieren_cambio = []
        for evaluacion in self.evaluacion_ids:
            if not evaluacion.estado_id or evaluacion.estado_id.code != 'requiere_cambio':
                continue
            nombre = self._get_nombre_componente_con_color(evaluacion)
            subpartes = self.get_subpartes_componente(evaluacion) or []
            componentes_requieren_cambio.append({
                'nombre': nombre,
                'subpartes': subpartes
            })

        # 3) Observaciones técnico
        observaciones_texto = ''
        if self.observaciones_tecnico:
            observaciones_texto = re.sub(r'<[^>]+>', '', self.observaciones_tecnico).strip()

        # 4) Construir HTML
        html_parts = []
        html_parts.append('<p>Resumen del trabajo realizado: se describen a continuación las intervenciones llevadas a cabo.</p>')

        if intervenciones:
            html_parts.append('<h5 style="margin:12px 0 6px;">Trabajo realizado</h5>')
            for it in intervenciones:
                sub = ''
                if it['subpartes']:
                    sub = f" — Repuestos/partes: {', '.join(it['subpartes'])}."
                obs = f" Observación: {it['observacion']}" if it['observacion'] else ''
                html_parts.append(f"<p><strong>{it['componente']}</strong>: {it['accion']}{sub}{obs}</p>")

        if componentes_requieren_cambio:
            html_parts.append('<h5 style="margin:12px 0 6px;">Componentes que requieren cambio</h5>')
            for cr in componentes_requieren_cambio:
                if cr['subpartes']:
                    html_parts.append(f"<p><strong>{cr['nombre']}:</strong></p><ul>")
                    for sp in cr['subpartes']:
                        html_parts.append(f"<li>{sp}</li>")
                    html_parts.append("</ul>")
                else:
                    html_parts.append(f"<p><strong>{cr['nombre']}</strong></p>")

        if observaciones_texto:
            html_parts.append('<h5 style="margin:12px 0 6px;">Observaciones</h5>')
            html_parts.append(f"<p>{observaciones_texto}</p>")

        html = (
            '<div data-autogen="1" style="font-family: Arial; line-height:1.5;">'
            + ''.join(html_parts) +
            '</div>'
        )

        # La calidad automática puede seguir calculándose para uso interno,
        # pero no la grabamos aquí (la decisión de grabar la calidad la tienes en action_generar_informe).
        calidad = self._rep__calc_calidad(self._rep__collect_findings(), self._rep__funciones_con_falla(), self._rep__toners_criticos())

        _logger.info("[_rep__build_informe_html] HTML construido (len=%s) para id=%s", len(html), self.id)
        return html, calidad

    def _generar_subpartes_estructuradas(self):
        """Genera HTML estructurado de componentes y sus subpartes SOLO para los que requieren cambio"""
        if not self.intervencion_ids:
            return ""

        # Filtrar solo intervenciones que tienen detalles Y cuya acción es 'cambiado'
        intervenciones_cambio = self.intervencion_ids.filtered(
            lambda x: x.detalle_ids and x.accion == 'cambiado'
        )
        
        if not intervenciones_cambio:
            return ""

        html_parts = []
        
        for intervencion in intervenciones_cambio:
            # Obtener nombre del componente
            codigo = intervencion.componente_code if intervencion.componente_code else intervencion.componente
            componente_nombre = self._get_component_display_name(codigo)
            
            # Obtener subpartes
            subpartes = [d.subparte_id.name for d in intervencion.detalle_ids if d.subparte_id]
            
            if subpartes:
                # Componente como título
                html_parts.append(f'<p style="margin:10px 0 5px 0;"><strong>{componente_nombre}:</strong></p>')
                
                # Lista de subpartes
                html_parts.append('<ul style="margin:0 0 10px 20px;">')
                for subparte in subpartes:
                    html_parts.append(f'<li>{subparte}</li>')
                html_parts.append('</ul>')
        
        if not html_parts:
            return ""
        
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
        Llamada robusta a Gemini:
        - Logea la respuesta cruda para depuración.
        - Intenta varios accesos al contenido devuelto por la API.
        - Si hay error, devuelve el informe automático como fallback (y registra por qué).
        """
        self.ensure_one()
        if not GEMINI_AVAILABLE:
            raise UserError("google-genai no instalado")

        _logger.info("[_generar_informe_con_ia] Iniciando para id=%s", self.id)

        try:
            # 1) Configuración
            config_gemini = self.env['gemini.configuracion'].get_config_activa()
            gemini_setup = self._init_gemini_model(config_gemini)

            # 2) Preparar datos y prompt
            datos = self._preparar_datos_para_ia()
            prompt = self._construir_prompt_ia(datos)
            _logger.debug("[_generar_informe_con_ia] Prompt len=%s", len(prompt))

            # 3) Llamar API (registrar la llamada)
            _logger.info("[_generar_informe_con_ia] Llamando Gemini modelo=%s temperature=%s max_tokens=%s",
                        gemini_setup.get('modelo'),
                        gemini_setup.get('temperature'),
                        gemini_setup.get('max_output_tokens') or gemini_setup.get('max_tokens'))

            # Nota: usar keys exactas según tu gemini_setup
            cfg_max_tokens = gemini_setup.get('max_output_tokens') or gemini_setup.get('max_tokens')
            cfg_temperature = min(float(gemini_setup.get('temperature', 0.0)), 0.2)

            response = gemini_setup['client'].models.generate_content(
                model=gemini_setup['modelo'],
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=cfg_temperature,
                    max_output_tokens=int(cfg_max_tokens) if cfg_max_tokens else None,
                    response_mime_type='application/json',
                )
            )

            # 4) Loguear la respuesta cruda (para depuración)
            # response puede ser objeto; intentamos leer atributos comunes
            raw_text = None
            try:
                # muchos SDK colocan el resultado en response.text o response.result or response.output
                if hasattr(response, 'text'):
                    raw_text = response.text
                elif hasattr(response, 'result'):
                    raw_text = getattr(response, 'result')
                elif hasattr(response, 'output'):
                    raw_text = getattr(response, 'output')
                else:
                    # fallback a str()
                    raw_text = str(response)
            except Exception as e:
                raw_text = str(response)

            _logger.debug("[_generar_informe_con_ia] Respuesta cruda Gemini (truncada): %s", (raw_text or '')[:4000])

            # 5) Normalizar texto recibido para parsear JSON
            texto_limpio = raw_text or ''
            if isinstance(texto_limpio, bytes):
                try:
                    texto_limpio = texto_limpio.decode('utf-8', errors='ignore')
                except Exception:
                    texto_limpio = str(texto_limpio)

            texto_limpio = texto_limpio.strip()
            # quitar fences si vienen en triple backticks
            if texto_limpio.startswith('```'):
                # quitar la línea de apertura
                try:
                    # Si es ```json\n{...}\n```
                    texto_limpio = texto_limpio.split('```', 1)[1]
                except Exception:
                    texto_limpio = texto_limpio[3:]
            if texto_limpio.endswith('```'):
                texto_limpio = texto_limpio[:-3]
            texto_limpio = texto_limpio.strip()

            _logger.debug("[_generar_informe_con_ia] Texto limpio para JSON (truncado): %s", texto_limpio[:2000])

            # 6) Intentar parsear como JSON estándar
            resultado = None
            try:
                resultado = json.loads(texto_limpio)
            except Exception as json_err:
                _logger.warning("[_generar_informe_con_ia] JSONDecodeError: %s", json_err)
                # intentar extraer un objeto JSON dentro del texto con regex
                import re
                m = re.search(r'\\{.*\\}', texto_limpio, flags=re.S)
                if m:
                    try:
                        resultado = json.loads(m.group(0))
                    except Exception as inner_err:
                        _logger.warning("[_generar_informe_con_ia] fallo parseo JSON interno: %s", inner_err)
                        resultado = None

            # 7) Si no logramos parsear, lanzar excepción para fallback controlado
            if not resultado or 'informe_html' not in resultado:
                _logger.error("[_generar_informe_con_ia] Respuesta IA inválida o faltan campos requeridos. Se usará fallback.")
                _logger.debug("[_generar_informe_con_ia] Respuesta cruda completa: %s", texto_limpio[:8000])
                raise ValueError("Respuesta IA inválida o incompleta")

            # 8) Registrar uso
            try:
                config_gemini.incrementar_contador()
            except Exception as incr_err:
                _logger.warning("[_generar_informe_con_ia] No se pudo incrementar contador uso: %s", incr_err)

            # 9) Mensaje y retorno
            informe_html = resultado.get('informe_html', '')
            calidad = resultado.get('calidad', 'regular')
            justificacion = resultado.get('justificacion_calidad', '')
            self.message_post(
                body=(
                    "<b>✨ Informe generado con IA</b><br/>"
                    f"Modelo: {gemini_setup.get('modelo')}<br/>"
                    f"Calidad sugerida por IA: <b>{calidad.upper()}</b><br/>"
                    f"Justificación: {justificacion}"
                )
            )
            _logger.info("[_generar_informe_con_ia] Éxito. Calidad_sugerida=%s", calidad)
            return informe_html, calidad, justificacion

        except Exception as e:
            # Registrar detalle del error y usar el informe automático como fallback
            _logger.exception("[_generar_informe_con_ia] Error llamando a Gemini o parseando respuesta: %s", e)
            # Intentar fallback automático (tu método existente)
            try:
                html, calidad = self._rep__build_informe_html()
                return html, calidad, 'Generado automáticamente (error en IA)'
            except Exception as inner_fallback_err:
                _logger.exception("[_generar_informe_con_ia] Error en fallback automático: %s", inner_fallback_err)
                # Último recurso: devolver texto mínimo
                html = (
                    '<div data-autogen="1" style="font-family: Arial; line-height:1.5;">'
                    '<p>Resumen del trabajo: no fue posible generar el detalle automáticamente.</p>'
                    '</div>'
                )
                return html, 'regular', 'Generado automáticamente (error en IA y fallo en fallback)'

    
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
        Prepara los datos que realmente necesita la IA para redactar el resumen
        del trabajo realizado. NO incluye datos del equipo (marca, serie, contador).
        Retorna un dict con:
        - componentes_criticos: [{nombre, subpartes[], observaciones}]
        - componentes_desgaste: [{nombre, observaciones}]
        - funciones_falla: [..]
        - toners_criticos: [..]
        - intervenciones_realizadas: [{componente, accion, subpartes_reemplazadas[], observacion_intervencion}]
        - observaciones_tecnico: texto limpio
        """
        self.ensure_one()

        # Hallazgos desde evaluaciones (cambios/criticos/desgaste)
        findings = self._rep__collect_findings()
        funciones_falla = self._rep__funciones_con_falla()
        toners_crit = self._rep__toners_criticos()

        # Componentes críticos: usar la misma lógica que ya tenías (buscar subpartes asociadas)
        componentes_criticos_detalle = []
        for comp_nombre in findings.get('cambio_inmediato', []):
            # buscar evaluación que coincida con ese nombre para extraer observaciones y subpartes
            encontrado = False
            for eval_comp in self.evaluacion_ids:
                nombre_eval = self._get_nombre_componente_con_color(eval_comp)
                if nombre_eval == comp_nombre:
                    subpartes = self.get_subpartes_componente(eval_comp)
                    componentes_criticos_detalle.append({
                        'nombre': comp_nombre,
                        'subpartes': subpartes or [],
                        'observaciones': eval_comp.observaciones or ''
                    })
                    encontrado = True
                    break
            if not encontrado:
                # Si no lo encontramos por evaluación, lo añadimos sin subpartes (seguridad)
                componentes_criticos_detalle.append({
                    'nombre': comp_nombre,
                    'subpartes': [],
                    'observaciones': ''
                })

        # Componentes con desgaste
        componentes_desgaste_detalle = []
        for comp_nombre in findings.get('desgaste', []):
            for eval_comp in self.evaluacion_ids:
                nombre_eval = self._get_nombre_componente_con_color(eval_comp)
                if nombre_eval == comp_nombre:
                    componentes_desgaste_detalle.append({
                        'nombre': comp_nombre,
                        'observaciones': eval_comp.observaciones or ''
                    })
                    break

        # Intervenciones realizadas: listar intervenciones con accion 'cambiado' u otras acciones relevantes
        intervenciones_realizadas = []
        for interv in self.intervencion_ids:
            # buscamos subpartes realmente aplicadas en esta intervención
            subpartes_reemplazadas = [d.subparte_id.name for d in interv.detalle_ids if d.subparte_id]
            componente_display = self._get_component_display_name(interv.componente_code or interv.componente)
            intervenciones_realizadas.append({
                'componente': componente_display,
                'accion': interv.accion or '',
                'subpartes_reemplazadas': subpartes_reemplazadas,
                'observacion_intervencion': getattr(interv, 'observacion', '') or getattr(interv, 'observaciones', '') or ''
            })

        # Observaciones técnico: limpiar HTML si existe
        observaciones_texto = ''
        if self.observaciones_tecnico:
            observaciones_texto = re.sub(r'<[^>]+>', '', self.observaciones_tecnico).strip()

        datos = {
            # NO incluir 'maquina', 'serie', 'contador' por petición explícita
            'componentes_criticos': componentes_criticos_detalle,
            'componentes_desgaste': componentes_desgaste_detalle,
            'funciones_falla': funciones_falla,
            'toners_criticos': toners_crit,
            'intervenciones_realizadas': intervenciones_realizadas,
            'observaciones_tecnico': observaciones_texto,
        }

        _logger.debug("[_preparar_datos_para_ia] preparados: criticos=%s, desgaste=%s, interv=%s",
                    len(componentes_criticos_detalle), len(componentes_desgaste_detalle), len(intervenciones_realizadas))
        return datos

    
    def _construir_prompt_ia(self, datos):
        """
        Construye el prompt para Gemini usando SOLO los datos estructurados pasados en `datos`.
        - NO debe incluir datos del equipo (marca/serie/contador).
        - Debe generar un resumen humano del trabajo realizado y listar COMPONENTES QUE REQUIEREN CAMBIO
        con sus subpartes EXACTAS (si las hay).
        - Debe devolver SÓLO un JSON válido con claves: "informe_html" y "nota_interna".
        """
        import json
        import logging
        _logger = logging.getLogger(__name__)
        self.ensure_one()

        try:
            datos_json = json.dumps(datos, ensure_ascii=False)
            _logger.debug("[_construir_prompt_ia] Datos para IA: %s", datos_json[:2000])

            prompt = f"""
    Eres un técnico que redacta informes breves y claros sobre trabajos de reparación,
    dirigidos al área de logística/ventas (no al cliente final). TU ÚNICA FUENTE DE
    VERDAD es el JSON que aparece abajo. NO agregues datos del equipo (marca, serie, contador)
    ni ningún dato que no esté en ese JSON.

    INSTRUCCIONES OBLIGATORIAS:
    1) Usa SOLO el JSON provisto: no inventes fallas, piezas, cantidades, ni acciones.
    2) El informe debe ser un RESUMEN HUMANO y NATURAL del trabajo realizado:
    - Qué intervenciones se realizaron (componente — acción — subpartes reemplazadas si las hubo).
    - Observaciones relevantes del técnico.
    3) Si existen elementos en "componentes_criticos", debes listarlos y mostrar sus SUBPARTES EXACTAS
    tal como aparecen en el JSON (no las transformes ni las inventes).
    4) Omitir secciones que estén vacías (no escribir "sin problemas" salvo que TODO esté vacío).
    5) Máximo 130–150 palabras en el cuerpo principal (resumen).
    6) Elimina cualquier marca interna, etiquetas de sistema o metadatos: responde únicamente con el JSON que se solicita.

    AQUÍ ESTÁ EL JSON (ÚNICA FUENTE DE VERDAD). NO USES NADA QUE NO ESTÉ AQUÍ:
    ```json
    {datos_json}
    ```

    RESPONDE SOLO CON UN JSON VÁLIDO (sin texto adicional) con estas claves:

    {{ 
    "informe_html": "HTML del informe (estructura indicada abajo)",
    "nota_interna": "Texto corto opcional con observaciones del técnico (máx. 120 caracteres)"
    }}

    ESTRUCTURA REQUERIDA PARA "informe_html":
    <div data-autogen="1" style="font-family: Arial; line-height:1.5;">
    <p>[Resumen humano y breve del trabajo realizado, 1–3 líneas]</p>

    <h5 style="margin:12px 0 6px;">Trabajo realizado</h5>
    [Para cada elemento en intervenciones_realizadas: "Componente — acción — subpartes reemplazadas (si las hay)".]

    <h5 style="margin:12px 0 6px;">Componentes que requieren cambio</h5>
    [Para cada elemento en componentes_criticos: mostrar componente y sus subpartes EXACTAS en una lista.]

    <h5 style="margin:12px 0 6px;">Observaciones</h5>
    [Texto con observaciones_tecnico si existe]
    </div>

    NOTAS FINALES:
    - NO incluir datos del equipo (marca/serie/contador) en el informe: esos datos forman parte del formulario, no del resumen.
    - Si alguna sección está vacía en el JSON, omítela del HTML.
    - No devuelvas ningún texto fuera del JSON final solicitado.
    """
            return prompt

        except Exception as e:
            _logger.exception("[_construir_prompt_ia] Error construyendo prompt: %s", e)
            fallback = (
                "Eres un técnico. Usa SOLO el JSON provisto para generar un informe breve. "
                "Devuelve únicamente un JSON con 'informe_html' y 'nota_interna'."
                f"\nJSON:\n{json.dumps(datos, ensure_ascii=False)}"
            )
            return fallback

    
    def _parsear_respuesta_ia(self, response_text):
        """Parsea la respuesta JSON de Gemini"""
        try:
            # Limpiar posibles markdown wrappings
            texto_limpio = response_text.strip()
            if texto_limpio.startswith('```json'):
                texto_limpio = texto_limpio[7:]
            if texto_limpio.startswith('```'):
                texto_limpio = texto_limpio[3:]
            if texto_limpio.endswith('```'):
                texto_limpio = texto_limpio[:-3]
            texto_limpio = texto_limpio.strip()
            
            # Parsear JSON
            resultado = json.loads(texto_limpio)
            
            # Validar campos requeridos
            if 'calidad' not in resultado:
                raise ValueError("Respuesta sin campo 'calidad'")
            if 'informe_html' not in resultado:
                raise ValueError("Respuesta sin campo 'informe_html'")
            if 'justificacion_calidad' not in resultado:
                resultado['justificacion_calidad'] = ''
            
            # Validar calidad
            if resultado['calidad'] not in ['buena', 'regular', 'mala']:
                _logger.warning("[_parsear_respuesta_ia] Calidad inválida: %s, usando 'regular'", 
                              resultado['calidad'])
                resultado['calidad'] = 'regular'
            
            return resultado
            
        except json.JSONDecodeError as e:
            _logger.error("[_parsear_respuesta_ia] Error parseando JSON: %s", e)
            _logger.error("[_parsear_respuesta_ia] Respuesta recibida: %s", response_text[:500])
            raise UserError(_(
                "La IA generó una respuesta inválida.\n\n"
                "Intenta nuevamente o usa el modo automático."
            ))
        except Exception as e:
            _logger.error("[_parsear_respuesta_ia] Error inesperado: %s", e)
            raise

    # ========================================
    # VALIDACIÓN PARA WIZARD
    # ========================================
    def _check_campos_requieren_cambio_sin_intervencion(self):
        """
        Devuelve evaluaciones que requieren cambio y NO tienen intervención con subpartes.
        Se deduplica por componente_code para no repetir el mismo componente en el wizard.
        """
        self.ensure_one()
        _logger.info("[_check_campos_requieren_cambio_sin_intervencion] Inicio id=%s", self.id)

        componentes_pendientes = []
        seen = set()  # <-- evita duplicados por componente_code

        for evaluacion in self.evaluacion_ids:
            if not evaluacion.estado_id or evaluacion.estado_id.code != 'requiere_cambio':
                continue

            componente_code = self._get_componente_code_from_evaluacion(evaluacion)
            if not componente_code:
                _logger.warning(
                    "[_check_campos...] No se pudo mapear eval %s (tipo=%s color=%s)",
                    evaluacion.id,
                    evaluacion.componente_tipo_id and (evaluacion.componente_tipo_id.code or evaluacion.componente_tipo_id.name),
                    self._rep__get_color_code_from_eval(evaluacion),
                )
                continue

            # Si ya evaluamos este componente_code, saltar
            if componente_code in seen:
                _logger.debug("[_check_campos...] componente_code '%s' ya considerado, se omite duplicado", componente_code)
                continue
            seen.add(componente_code)

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
                _logger.debug("[_check_campos...] pendiente=%s", comp)
                componentes_pendientes.append(comp)

        _logger.info("[_check_campos...] total_pendientes=%s id=%s", len(componentes_pendientes), self.id)
        return componentes_pendientes
    def _handle_subpartes_pendientes(self, origen_accion=None, auto_finalize=False):
        """
        Verifica si hay componentes en 'requiere_cambio' sin subpartes
        y, si los hay, abre el wizard de subpartes.

        Retorna:
        - dict action (ir.actions.act_window) si abre wizard
        - False si no hay pendientes
        """
        self.ensure_one()
        _logger.info(
            "[_handle_subpartes_pendientes] Inicio rep.id=%s origen=%s auto_finalize=%s",
            self.id, origen_accion, auto_finalize
        )

        campos_pendientes = self._check_campos_requieren_cambio_sin_intervencion()
        if not campos_pendientes:
            _logger.info("[_handle_subpartes_pendientes] Sin pendientes rep.id=%s", self.id)
            return False

        # Abrir wizard base (sin contexto especial)
        action = self._abrir_wizard_multiple_componentes(campos_pendientes)
        ctx = dict(action.get('context') or {})

        # Si viene desde generar_informe, marcamos ese flag
        if origen_accion == 'generar_informe':
            ctx['from_generar_informe'] = True

        # Guardamos quién llamó
        if origen_accion:
            ctx['from_action'] = origen_accion

        # Si queremos que al cerrar el wizard se relance la acción (ej: finalizar)
        if auto_finalize:
            ctx['auto_finalize'] = True

        action['context'] = ctx

        _logger.info(
            "[_handle_subpartes_pendientes] Abriendo wizard subpartes rep.id=%s, "
            "origen=%s, auto_finalize=%s ctx=%s",
            self.id, origen_accion, auto_finalize, ctx
        )
        return action


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

        return {
            'type': 'ir.actions.act_window',
            'name': titulo,
            'res_model': 'reparacion.add.subparts.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': self.env.ref('sat.view_reparacion_add_subparts_wizard_form').id,
            'target': 'new',
            'context': {},
        }
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
        """
        Genera el informe técnico (con o sin IA según configuración) y/o abre wizard.
        - Abre wizard de subpartes si hay componentes en 'requiere_cambio' sin subpartes.
        - No sobrescribe informes editados manualmente.
        - Solo graba 'informe', 'informe_generado_por_ia' y 'calidad_justificacion' (si existe),
        NO modifica el campo de calidad principal.
        """
        _logger.info("[action_generar_informe] >>> INICIO batch ids=%s", self.ids)

        acciones = []
        for rec in self:
            try:
                _logger.info("[action_generar_informe] Procesando rep.id=%s modo=%s",
                            rec.id, rec.modo_generacion_informe)

                # 1) Subpartes pendientes -> abre wizard (para que el técnico llene subpartes antes)
                action_sub = rec._handle_subpartes_pendientes('generar_informe')
                if action_sub:
                    _logger.info("[action_generar_informe] rep.id=%s -> abre wizard subpartes", rec.id)
                    return action_sub

                # 2) Si hay contenido manual, no sobrescribir
                if (rec.informe and not rec._rep__html_is_empty(rec.informe) and not rec._rep__is_autogen_informe()):
                    rec.message_post(body=_("El informe ya fue editado manualmente. No se sobrescribió."))
                    _logger.info("[action_generar_informe] rep.id=%s -> informe manual existente, no se toca", rec.id)
                    continue

                # 3) Generar informe (IA o automático)
                if rec.modo_generacion_informe == 'ia':
                    html, calidad_sugerida, justificacion = rec._generar_informe_con_ia()
                else:
                    html, calidad_sugerida = rec._rep__build_informe_html()
                    justificacion = ''

                # 4) Guardar SOLO el informe y flags informativos (no tocar calidad principal)
                vals = {
                    'informe': html,
                    'informe_generado_por_ia': (rec.modo_generacion_informe == 'ia'),
                    'calidad_justificacion': justificacion,
                }
                rec.write(vals)

                mensaje = _("✨ Informe técnico generado con IA.") if rec.modo_generacion_informe == 'ia' \
                        else _("Informe técnico generado automáticamente.")
                rec.message_post(body=mensaje)

                _logger.info("[action_generar_informe] rep.id=%s -> informe generado (len=%s)", rec.id, len(html))
                acciones.append(rec.id)

            except Exception as e:
                _logger.exception("[action_generar_informe] rep.id=%s ERROR %s", rec.id, e)
                rec.message_post(body=_("❌ No se pudo generar el informe: %s") % e)

        _logger.info("[action_generar_informe] <<< FIN. generados=%s", len(acciones))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informe técnico'),
                'message': _('✅ Informe generado correctamente.') if acciones else _('⚠️ No se generó ningún informe.'),
                'type': 'success' if acciones else 'warning'
            }
        }

    # ========================================
    # HELPERS PARA SUBPARTES
    # ========================================
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
        """
        Retorna el nombre completo del componente con su color formateado correctamente.
        """
        nombre = eval_comp.componente_tipo_id.name
        
        if eval_comp.color_id:
            color_nombre = eval_comp.color_id.name
            # Traducir nombres de colores si es necesario
            color_map = {
                'k': 'Negro', 'black': 'Negro', 'negro': 'Negro',
                'c': 'Cyan', 'cyan': 'Cyan',
                'm': 'Magenta', 'magenta': 'Magenta',
                'y': 'Amarillo', 'yellow': 'Amarillo', 'amarillo': 'Amarillo',
            }
            color_code = eval_comp.color_id.code or ''
            color_display = color_map.get(color_code.lower(), color_nombre)
            nombre = f"{nombre} ({color_display})"
        
        return nombre
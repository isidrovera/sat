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
        """Construye el HTML del informe técnico (método automático sin IA)."""
        self.ensure_one()
        _logger.info("[_rep__build_informe_html] Iniciando para reparacion id=%s", self.id)

        # Hallazgos estructurados
        f = self._rep__collect_findings()
        funciones_no = self._rep__funciones_con_falla()
        toners_crit = self._rep__toners_criticos()

        # Calidad: usar SIEMPRE lo que ya está en calidad_id; si no hay, calcular como respaldo
        calidad = self._rep__get_calidad_actual(
            findings=f,
            funciones_falla=funciones_no,
            toners_criticos=toners_crit,
        )
        _logger.debug("[_rep__build_informe_html] calidad_usada=%s", calidad)

        html_parts = []

        # Texto inicial, corto y natural
        html_parts.append(
            '<p>Se realizó una revisión general de la máquina y pruebas básicas de funcionamiento.</p>'
        )

        # Subpartes específicas SOLO para componentes que requieren cambio
        subpartes_html = self._generar_subpartes_estructuradas()
        if subpartes_html:
            html_parts.append(
                '<p><strong>Se identifican los siguientes componentes que requieren cambio, con sus subpartes asociadas:</strong></p>'
            )
            html_parts.append(subpartes_html)

        # Componentes con desgaste (cambio preventivo recomendado)
        if f['desgaste']:
            html_parts.append('<p><strong>Se recomienda cambio preventivo de:</strong></p>')
            html_parts.append('<ul style="margin:5px 0 10px 20px;">')
            for comp in f['desgaste']:
                html_parts.append(f'<li>{comp}</li>')
            html_parts.append('</ul>')

        # Funciones con falla (si las hay)
        if funciones_no:
            html_parts.append('<p><strong>Funciones con incidencia detectada:</strong></p>')
            html_parts.append('<ul style="margin:5px 0 10px 20px;">')
            for fun in funciones_no:
                html_parts.append(f'<li>{fun}</li>')
            html_parts.append('</ul>')

        # Toners críticos (si los hay)
        if toners_crit:
            html_parts.append('<p><strong>Consumibles en estado crítico:</strong></p>')
            html_parts.append('<ul style="margin:5px 0 10px 20px;">')
            for t in toners_crit:
                html_parts.append(f'<li>{t}</li>')
            html_parts.append('</ul>')

        # Conclusión basada en la calidad ya definida
        if calidad == 'mala':
            html_parts.append(
                '<p>El equipo requiere inversión inmediata en repuestos antes de ser entregado.</p>'
            )
        elif calidad == 'regular':
            html_parts.append(
                '<p>El equipo se encuentra operativo, pero se recomienda realizar los cambios preventivos indicados.</p>'
            )
        else:  # 'buena' u otro valor
            html_parts.append(
                '<p>El equipo presenta una calidad de impresión acorde y está listo para entrega con mantenimiento estándar.</p>'
            )

        # Construir HTML final
        html = f'''
    <div data-autogen="1" style="font-family: Arial; line-height:1.6;">
        {''.join(html_parts)}
    </div>
    '''
        _logger.info(
            "[_rep__build_informe_html] HTML construido (len=%s) para id=%s",
            len(html),
            self.id,
        )
        # ⚠️ Importante: devolvemos la calidad usada SOLO como dato, no se escribe a la BD aquí
        return html, calidad


    def _generar_subpartes_estructuradas(self):
        """Genera HTML con viñetas de componentes y sus subpartes SOLO para los que requieren cambio"""
        if not self.intervencion_ids:
            return ""

        # Filtrar solo intervenciones que tienen detalles Y cuya acción es 'cambiado'
        intervenciones_cambio = self.intervencion_ids.filtered(
            lambda x: x.detalle_ids and x.accion == 'cambiado'
        )
        
        if not intervenciones_cambio:
            return ""

        html_parts = []
        html_parts.append('<ul style="margin:5px 0 10px 20px; list-style-type: disc;">')
        
        for intervencion in intervenciones_cambio:
            # Obtener nombre del componente
            codigo = intervencion.componente_code if intervencion.componente_code else intervencion.componente
            componente_nombre = self._get_component_display_name(codigo)
            
            # Obtener subpartes
            subpartes = [d.subparte_id.name for d in intervencion.detalle_ids if d.subparte_id]
            
            if subpartes:
                # Componente como item de lista
                html_parts.append(f'<li style="margin-bottom:8px;"><strong>{componente_nombre}:</strong>')
                
                # Sub-lista de subpartes
                html_parts.append('<ul style="margin:3px 0 0 20px; list-style-type: circle;">')
                for subparte in subpartes:
                    html_parts.append(f'<li>{subparte}</li>')
                html_parts.append('</ul>')
                html_parts.append('</li>')
        
        html_parts.append('</ul>')
        
        if len(html_parts) == 2:  # Solo etiquetas de apertura/cierre, sin contenido
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
        """Genera informe con IA (NUEVA SINTAXIS) usando la calidad ya definida en checklist."""
        self.ensure_one()
        
        if not GEMINI_AVAILABLE:
            raise UserError("google-genai no instalado")
        
        _logger.info("[_generar_informe_con_ia] Iniciando para id=%s", self.id)
        
        try:
            # 1) Configuración
            config_gemini = self.env['gemini.configuracion'].get_config_activa()
            gemini_setup = self._init_gemini_model(config_gemini)
            
            # 2) Preparar datos (incluye calidad_actual desde checklist)
            datos = self._preparar_datos_para_ia()
            
            # 3) Construir prompt
            prompt = self._construir_prompt_ia(datos)
            
            _logger.debug("[_generar_informe_con_ia] Prompt len=%s", len(prompt))
            
            # 4) Llamar API (NUEVA SINTAXIS)
            _logger.info("[_generar_informe_con_ia] Llamando Gemini...")
            
            response = gemini_setup['client'].models.generate_content(
                model=gemini_setup['modelo'],
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=gemini_setup['temperature'],
                    max_output_tokens=gemini_setup['max_tokens'],
                    response_mime_type='application/json',  # Forzar JSON
                )
            )
            
            # 5) Parsear respuesta
            resultado = self._parsear_respuesta_ia(response.text)
            
            # 6) Determinar calidad efectiva (SIEMPRE desde checklist / lógica interna)
            calidad_efectiva = datos.get('calidad_actual') or 'regular'
            
            # 7) Registrar uso
            config_gemini.incrementar_contador()
            
            # 8) Log en chatter (clarificando que la calidad viene del checklist)
            self.message_post(
                body=(
                    f"<b>✨ Informe generado con IA</b><br/>"
                    f"Modelo: {gemini_setup['modelo']}<br/>"
                    f"Calidad (desde checklist): <b>{calidad_efectiva.upper()}</b><br/>"
                    f"Justificación IA: {resultado.get('justificacion_calidad', '')}"
                )
            )
            
            _logger.info(
                "[_generar_informe_con_ia] ✅ Éxito. Calidad_usada=%s", calidad_efectiva
            )
            
            return (
                resultado['informe_html'],
                calidad_efectiva,
                resultado.get('justificacion_calidad', ''),
            )
            
        except Exception as e:
            _logger.error("[_generar_informe_con_ia] ❌ Error: %s", str(e))
            # Fallback
            _logger.warning("Usando método automático como fallback")
            html, calidad = self._rep__build_informe_html()
            return (html, calidad, 'Generado automáticamente (error en IA)')

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
        Prepara todos los datos necesarios para el prompt de IA.
        Retorna diccionario con datos estructurados.
        Usa la calidad ya definida en calidad_id (checklist) cuando exista.
        """
        self.ensure_one()
        
        # Recolectar hallazgos
        findings = self._rep__collect_findings()
        funciones_falla = self._rep__funciones_con_falla()
        toners_crit = self._rep__toners_criticos()
        
        # Calidad actual DESDE CHECKLIST (o calculada como fallback)
        calidad_actual = self._rep__get_calidad_actual(
            findings=findings,
            funciones_falla=funciones_falla,
            toners_criticos=toners_crit,
        )
        
        # Obtener estados de carcasa y panel (usar solo el primero si hay varios)
        carcasa_eval = self.evaluacion_ids.filtered(
            lambda e: e.componente_tipo_id.code == 'CARCASA'
        )
        panel_eval = self.evaluacion_ids.filtered(
            lambda e: e.componente_tipo_id.code == 'PANEL_CONTROL'
        )

        carcasa_estado = carcasa_eval[:1].estado_id.name if carcasa_eval else 'No evaluado'
        panel_estado = panel_eval[:1].estado_id.name if panel_eval else 'No evaluado'

        # Contador: evitar mandar un Many2one raro al prompt
        contador_val = '0'
        if self.contometrok_id:
            try:
                # Ajusta estos nombres según tu modelo real de contómetro
                if hasattr(self.contometrok_id, 'contador'):
                    contador_val = str(self.contometrok_id.contador or 0)
                elif hasattr(self.contometrok_id, 'name'):
                    contador_val = str(self.contometrok_id.name)
                else:
                    contador_val = str(self.contometrok_id)
            except Exception as cex:
                _logger.warning(
                    "[_preparar_datos_para_ia] No se pudo obtener contador limpio de contometrok_id (%s). Usando '0'.",
                    cex,
                )
                contador_val = '0'

        # Formatear componentes críticos con sus subpartes (según intervenciones reales)
        componentes_criticos_detalle = []
        for comp_nombre in findings['cambio_inmediato']:
            for eval_comp in self.evaluacion_ids:
                nombre_eval = self._get_nombre_componente_con_color(eval_comp)
                if nombre_eval == comp_nombre:
                    subpartes = self.get_subpartes_componente(eval_comp)
                    if subpartes:
                        componentes_criticos_detalle.append({
                            'nombre': comp_nombre,
                            'subpartes': subpartes,
                            'observaciones': eval_comp.observaciones or ''
                        })
                    else:
                        componentes_criticos_detalle.append({
                            'nombre': comp_nombre,
                            'subpartes': [],
                            'observaciones': eval_comp.observaciones or ''
                        })
                    break
        
        # Formatear componentes con desgaste
        componentes_desgaste_detalle = []
        for comp_nombre in findings['desgaste']:
            for eval_comp in self.evaluacion_ids:
                nombre_eval = self._get_nombre_componente_con_color(eval_comp)
                if nombre_eval == comp_nombre:
                    componentes_desgaste_detalle.append({
                        'nombre': comp_nombre,
                        'observaciones': eval_comp.observaciones or ''
                    })
                    break
        
        # Observaciones del técnico (limpiar HTML si existe)
        observaciones_texto = ''
        if self.observaciones_tecnico:
            observaciones_texto = re.sub(r'<[^>]+>', '', self.observaciones_tecnico or '')
            observaciones_texto = observaciones_texto.strip()
        
        datos = {
            'maquina': f"{self.marca or ''} {self.nombre_maquina or ''}".strip(),
            'serie': self.serie_id or 'N/A',
            'contador': contador_val,
            'componentes_criticos': componentes_criticos_detalle,
            'componentes_desgaste': componentes_desgaste_detalle,
            'funciones_falla': funciones_falla,
            'toners_criticos': toners_crit,
            'observaciones_tecnico': observaciones_texto,
            'estado_carcasa': carcasa_estado,
            'estado_panel': panel_estado,
            'calidad_actual': calidad_actual or 'regular',
        }
        
        _logger.debug(
            "[_preparar_datos_para_ia] Datos preparados: criticos=%s, desgaste=%s, calidad_actual=%s",
            len(componentes_criticos_detalle),
            len(componentes_desgaste_detalle),
            datos['calidad_actual'],
        )
        
        return datos

    
    def _construir_prompt_ia(self, datos):
        """Construye el prompt para Gemini (usando la calidad ya definida en checklist)."""
        
        # Formatear componentes críticos
        criticos_text = ""
        if datos['componentes_criticos']:
            for comp in datos['componentes_criticos']:
                criticos_text += f"- {comp['nombre']}\n"
                if comp['subpartes']:
                    criticos_text += f"  Subpartes: {', '.join(comp['subpartes'])}\n"
                if comp['observaciones']:
                    criticos_text += f"  Observaciones: {comp['observaciones']}\n"
        else:
            criticos_text = "(ninguno)"
        
        # Formatear componentes con desgaste
        desgaste_text = ""
        if datos['componentes_desgaste']:
            for comp in datos['componentes_desgaste']:
                desgaste_text += f"- {comp['nombre']}\n"
                if comp['observaciones']:
                    desgaste_text += f"  Observaciones: {comp['observaciones']}\n"
        else:
            desgaste_text = "(ninguno)"
        
        # Formatear funciones con falla
        funciones_text = ", ".join(datos['funciones_falla']) if datos['funciones_falla'] else "(ninguna)"
        
        # Formatear toners críticos
        toners_text = ", ".join(datos['toners_criticos']) if datos['toners_criticos'] else "(ninguno)"
        
        calidad_actual = datos.get('calidad_actual', 'regular')

        prompt = f"""
    Eres un técnico experto de fotocopiadoras. Analiza esta evaluación técnica y genera un informe CORTO para VENTAS MAYORISTAS.

    INSTRUCCIONES IMPORTANTES:
    1. La calidad general YA ESTÁ DEFINIDA como: "{calidad_actual}". Úsala tal cual y no la cambies.
    2. Genera un informe HTML conciso (máximo 150 palabras), en tono humano y profesional.
    3. Corrige errores ortográficos en las observaciones del técnico.
    4. Normaliza términos técnicos (ejemplo: "rodillo negro" → "Unidad de Imagen Black") solo cuando sea evidente.
    5. NO inventes detalles técnicos, ni componentes, ni subpartes que no estén en los datos.
    6. Usa lenguaje profesional pero directo.
    7. El enfoque es para DISTRIBUIDORES (no usuario final).

    CRITERIOS (SOLO DE CONTEXTO, NO PARA QUE CAMBIES LA CALIDAD):
    - BUENA: Equipo listo para entrega. Solo requiere mantenimiento estándar en instalación.
    - REGULAR: Equipo operativo pero requiere cambios preventivos recomendados antes de entrega.
    - MALA: Equipo requiere inversión inmediata en repuestos críticos antes de entregarse a distribuidor.

    ═══════════════════════════════════════════════════════════════
    DATOS DE LA MÁQUINA:
    ═══════════════════════════════════════════════════════════════
    Marca/Modelo: {datos['maquina']}
    Serie: {datos['serie']}
    Contador: {datos['contador']} copias
    Calidad actual (definida por checklist): {calidad_actual}

    ═══════════════════════════════════════════════════════════════
    EVALUACIÓN TÉCNICA:
    ═══════════════════════════════════════════════════════════════

    COMPONENTES CRÍTICOS (requieren cambio inmediato):
    {criticos_text}

    COMPONENTES CON DESGASTE (cambio preventivo recomendado):
    {desgaste_text}

    FUNCIONES CON FALLA:
    {funciones_text}

    CONSUMIBLES CRÍTICOS (tóners vacíos o sin botella):
    {toners_text}

    ESTADO FÍSICO:
    - Carcasa: {datos['estado_carcasa']}
    - Panel de control: {datos['estado_panel']}

    OBSERVACIONES DEL TÉCNICO:
    {datos['observaciones_tecnico'] or 'Sin observaciones adicionales'}

    ═══════════════════════════════════════════════════════════════
    GENERA (en formato JSON estricto):
    ═══════════════════════════════════════════════════════════════

    IMPORTANTE:
    - El campo "calidad" del JSON DEBE ser exactamente "{calidad_actual}".
    - No propongas otra calidad distinta.

    {{
    "calidad": "{calidad_actual}",
    "justificacion_calidad": "Una línea de máximo 100 caracteres explicando por qué esa calidad, basada SOLO en los datos entregados",
    "informe_html": "HTML del informe aquí"
    }}

    ESTRUCTURA REQUERIDA DEL INFORME HTML:
    <div data-autogen="1" style="font-family: Arial; line-height:1.5;">
    <p>[Resumen general del estado en 1-2 líneas, coherente con la calidad {calidad_actual}]</p>

    <h5 style="margin:12px 0 6px;">Observaciones para entrega a distribuidor</h5>
    [SI hay componentes críticos, listar sólo esos componentes y sus subpartes específicas indicadas en los datos]
    [SI hay desgaste, listar componentes con desgaste sin inventar elementos nuevos]
    [SI hay tóners críticos, listarlos]

    <h5 style="margin:12px 0 6px;">Conclusión</h5>
    <div style="padding:10px; border-radius:6px; background:[color según calidad]; color:[texto según calidad];">
    <strong style="text-transform:capitalize;">[calidad]</strong>: [justificacion_calidad]
    </div>

    </div>

    COLORES PARA LA CONCLUSIÓN:
    - buena: background:#e8f5e9; color:#2e7d32;
    - regular: background:#fff8e1; color:#ef6c00;
    - mala: background:#ffebee; color:#c62828;

    RESPONDE SOLO CON EL JSON, SIN TEXTO ADICIONAL.
    """
        
        return prompt

    
    def _parsear_respuesta_ia(self, response_text):
        """Parsea la respuesta JSON de Gemini (informe_html + justificación)."""
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
            
            # Validar campos requeridos mínimos
            if 'informe_html' not in resultado:
                raise ValueError("Respuesta sin campo 'informe_html'")
            if 'calidad' not in resultado:
                _logger.warning("[_parsear_respuesta_ia] Respuesta sin campo 'calidad' (se ignorará para la BD)")
            if 'justificacion_calidad' not in resultado:
                resultado['justificacion_calidad'] = ''
            
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
        """Genera el informe técnico (con o sin IA según configuración) y/o abre wizard"""
        _logger.info("[action_generar_informe] >>> INICIO batch ids=%s", self.ids)

        acciones = []
        for rec in self:
            try:
                _logger.info(
                    "[action_generar_informe] Procesando rep.id=%s modo=%s",
                    rec.id,
                    rec.modo_generacion_informe,
                )

                # 1) Juntar TODOS los que requieren cambio y no tienen subpartes
                campos_pendientes = rec._check_campos_requieren_cambio_sin_intervencion()
                if campos_pendientes:
                    _logger.info(
                        "[action_generar_informe] rep.id=%s -> abre wizard por pendientes=%s",
                        rec.id,
                        len(campos_pendientes),
                    )
                    # aquí puedes seguir usando tu versión simple o la que tiene contexto
                    return rec._abrir_wizard_multiple_componentes_con_contexto(
                        campos_pendientes,
                        origen_accion='generar_informe',
                        auto_finalize=False,
                    )

                # 2) Si hay contenido manual, no sobrescribir
                if (
                    rec.informe
                    and not rec._rep__html_is_empty(rec.informe)
                    and not rec._rep__is_autogen_informe()
                ):
                    rec.message_post(
                        body=_("El informe ya fue editado manualmente. No se sobrescribió.")
                    )
                    _logger.info(
                        "[action_generar_informe] rep.id=%s -> informe manual existente, no se toca",
                        rec.id,
                    )
                    continue

                # 3) Generar según modo (IA o automático)
                if rec.modo_generacion_informe == 'ia':
                    html, calidad, justificacion = rec._generar_informe_con_ia()
                else:
                    html, calidad = rec._rep__build_informe_html()
                    justificacion = ''

                # 4) Guardar resultados (SIN tocar calidad_id)
                vals = {
                    'informe': html,
                    'informe_generado_por_ia': (rec.modo_generacion_informe == 'ia'),
                    'calidad_justificacion': justificacion,
                }

                rec.write(vals)

                mensaje = (
                    _("✨ Informe técnico generado con IA.")
                    if rec.modo_generacion_informe == 'ia'
                    else _("Informe técnico generado automáticamente.")
                )
                rec.message_post(body=mensaje)

                _logger.info(
                    "[action_generar_informe] rep.id=%s -> informe generado (len=%s)",
                    rec.id,
                    len(html),
                )
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
                'message': _(
                    '✅ Informe generado correctamente.'
                ) if acciones else _(
                    '⚠️ No se generó ningún informe.'
                ),
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
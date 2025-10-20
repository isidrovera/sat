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

        f = self._rep__collect_findings()
        funciones_no = self._rep__funciones_con_falla()
        toners_crit = self._rep__toners_criticos()

        calidad = self._rep__calc_calidad(f, funciones_no, toners_crit)
        _logger.debug("[_rep__build_informe_html] calidad=%s", calidad)

        if calidad == 'mala':
            concl = _("Unidad requiere inversión inmediata en repuestos antes de entregarse a distribuidor.")
        elif calidad == 'regular':
            concl = _("Unidad operativa para prueba; sugerimos cambio preventivo previo a la entrega.")
        else:
            concl = _("Unidad lista para entrega; se recomienda mantenimiento estándar en instalación.")

        texto_general = _(
            "Se realizó limpieza, puesta a punto básica y verificación general de funcionamiento y consumibles para la venta mayorista."
        )

        color_sev = {'critico': '#d32f2f', 'medio': '#ef6c00', 'pend': '#616161'}
        color_calidad_bg = {'mala': '#ffebee', 'regular': '#fff8e1', 'buena': '#e8f5e9'}
        color_calidad_txt = {'mala': '#c62828', 'regular': '#ef6c00', 'buena': '#2e7d32'}

        bloques = []
        if funciones_no:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Funciones con incidencia')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>" + "".join(f"<li>{x}</li>" for x in funciones_no) + "</ul>"
            )
        if f['cambio_inmediato']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Puntos críticos (cambio inmediato)')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>" + "".join(f"<li>{x}</li>" for x in f['cambio_inmediato']) + "</ul>"
            )
        if f['desgaste']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['medio']};'><strong>{_('Componentes con desgaste')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>" + "".join(f"<li>{x}</li>" for x in f['desgaste']) + "</ul>"
            )
        if f['pendientes']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['pend']};'><strong>{_('Pendientes / sin revisar')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>" + "".join(f"<li>{x}</li>" for x in f['pendientes']) + "</ul>"
            )
        if toners_crit:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Consumibles críticos')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>" + "".join(f"<li>{x}</li>" for x in toners_crit) + "</ul>"
            )

        repuestos_html = self._generar_seccion_repuestos()
        if repuestos_html:
            bloques.append(repuestos_html)

        observ_html = ""
        if bloques:
            observ_html = "<h5 style='margin:12px 0 6px;'>" + _("Observaciones para entrega a distribuidor") + "</h5>" + "".join(bloques)

        html = f"""
<div data-autogen="1" style="font-family: Arial; line-height:1.5;">
<p>{texto_general}</p>
{observ_html}
<h5 style="margin:12px 0 6px;">{_('Conclusión')}</h5>
<div style="padding:10px;border-radius:6px;background:{color_calidad_bg[calidad]};color:{color_calidad_txt[calidad]};">
    <strong style="text-transform:capitalize;">{calidad}</strong>: {concl}
</div>
<p style="color:#888; font-size:12px; margin-top:10px;">
    *{_('Bloque generado automáticamente a partir del checklist técnico.')}*
</p>
</div>
"""
        _logger.info("[_rep__build_informe_html] HTML construido (len=%s) para id=%s", len(html), self.id)
        return html, calidad

    def _generar_seccion_repuestos(self):
        """Genera la sección HTML de componentes y subpartes que requieren cambio."""
        if not self.intervencion_ids:
            _logger.debug("[_generar_seccion_repuestos] Sin intervenciones id=%s", self.id)
            return ""

        intervenciones_con_detalles = self.intervencion_ids.filtered(lambda x: x.detalle_ids)
        if not intervenciones_con_detalles:
            _logger.debug("[_generar_seccion_repuestos] Sin detalles en intervenciones id=%s", self.id)
            return ""

        repuestos_por_componente = {}
        for intervencion in intervenciones_con_detalles:
            componente_nombre = self._get_component_display_name(intervencion.componente)
            repuestos_por_componente.setdefault(componente_nombre, [])
            for detalle in intervencion.detalle_ids:
                repuestos_por_componente[componente_nombre].append(detalle.subparte_id.name)

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
        """Nombre amigable para códigos de intervención."""
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
            'itb': 'Faja/Banda de transferencia',
            'adf': 'ADF',
            'fin': 'Finalizador',
            'opt': 'Óptico',
            'papel': 'Transporte de papel',
            'otro': 'Otro',
        }
        res = component_names.get(componente_code, componente_code)
        _logger.debug("[_get_component_display_name] %s -> %s", componente_code, res)
        return res

    # ========================================
    # GENERACIÓN CON IA
    # ========================================
    def _generar_informe_con_ia(self):
        """Genera informe con IA (NUEVA SINTAXIS)"""
        self.ensure_one()
        
        if not GEMINI_AVAILABLE:
            raise UserError("google-genai no instalado")
        
        _logger.info("[_generar_informe_con_ia] Iniciando para id=%s", self.id)
        
        try:
            # 1) Configuración
            config_gemini = self.env['gemini.configuracion'].get_config_activa()
            gemini_setup = self._init_gemini_model(config_gemini)
            
            # 2) Preparar datos
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
            
            # 6) Registrar uso
            config_gemini.incrementar_contador()
            
            # 7) Log
            self.message_post(
                body=f"<b>✨ Informe generado con IA</b><br/>"
                    f"Modelo: {gemini_setup['modelo']}<br/>"
                    f"Calidad: <b>{resultado['calidad'].upper()}</b><br/>"
                    f"Justificación: {resultado['justificacion_calidad']}"
            )
            
            _logger.info("[_generar_informe_con_ia] ✅ Éxito. Calidad=%s", resultado['calidad'])
            
            return (
                resultado['informe_html'],
                resultado['calidad'],
                resultado['justificacion_calidad']
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
        """
        self.ensure_one()
        
        # Recolectar hallazgos (tu método existente)
        findings = self._rep__collect_findings()
        funciones_falla = self._rep__funciones_con_falla()
        toners_crit = self._rep__toners_criticos()
        
        # Obtener estados de carcasa y panel
        carcasa_eval = self.evaluacion_ids.filtered(
            lambda e: e.componente_tipo_id.code == 'CARCASA'
        )
        panel_eval = self.evaluacion_ids.filtered(
            lambda e: e.componente_tipo_id.code == 'PANEL_CONTROL'
        )
        
        # Formatear componentes críticos con sus subpartes
        componentes_criticos_detalle = []
        for comp_nombre in findings['cambio_inmediato']:
            # Buscar subpartes asociadas
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
            # Quitar tags HTML básicos
            observaciones_texto = re.sub(r'<[^>]+>', '', self.observaciones_tecnico)
            observaciones_texto = observaciones_texto.strip()
        
        datos = {
            'maquina': f"{self.marca or ''} {self.nombre_maquina or ''}".strip(),
            'serie': self.serie_id or 'N/A',
            'contador': self.contometrok_id or '0',
            'componentes_criticos': componentes_criticos_detalle,
            'componentes_desgaste': componentes_desgaste_detalle,
            'funciones_falla': funciones_falla,
            'toners_criticos': toners_crit,
            'observaciones_tecnico': observaciones_texto,
            'estado_carcasa': carcasa_eval.estado_id.name if carcasa_eval else 'No evaluado',
            'estado_panel': panel_eval.estado_id.name if panel_eval else 'No evaluado',
        }
        
        _logger.debug("[_preparar_datos_para_ia] Datos preparados: criticos=%s, desgaste=%s",
                     len(componentes_criticos_detalle), len(componentes_desgaste_detalle))
        
        return datos
    
    def _construir_prompt_ia(self, datos):
        """Construye el prompt para Gemini"""
        
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
        
        prompt = f"""
Eres un técnico experto de fotocopiadoras. Analiza esta evaluación técnica y genera un informe CORTO para VENTAS MAYORISTAS.

INSTRUCCIONES IMPORTANTES:
1. Determina la calidad general: "buena", "regular" o "mala"
2. Genera informe HTML conciso (máximo 150 palabras)
3. Corrige errores ortográficos en las observaciones del técnico
4. Normaliza términos técnicos (ejemplo: "rodillo negro" → "Unidad de Imagen Black")
5. NO inventes detalles técnicos que no estén en los datos
6. Usa lenguaje profesional pero directo
7. Enfoque para DISTRIBUIDORES (no usuario final)

CRITERIOS DE CALIDAD:
- BUENA: Equipo listo para entrega. Solo requiere mantenimiento estándar en instalación.
- REGULAR: Equipo operativo pero requiere cambios preventivos recomendados antes de entrega.
- MALA: Equipo requiere inversión inmediata en repuestos críticos antes de entregarse a distribuidor.

═══════════════════════════════════════════════════════════════
DATOS DE LA MÁQUINA:
═══════════════════════════════════════════════════════════════
Marca/Modelo: {datos['maquina']}
Serie: {datos['serie']}
Contador: {datos['contador']} copias

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

{{
  "calidad": "buena|regular|mala",
  "justificacion_calidad": "Una línea de máximo 100 caracteres explicando por qué esa calidad",
  "informe_html": "HTML del informe aquí"
}}

ESTRUCTURA REQUERIDA DEL INFORME HTML:
<div data-autogen="1" style="font-family: Arial; line-height:1.5;">
<p>[Resumen general del estado en 1-2 líneas]</p>

<h5 style="margin:12px 0 6px;">Observaciones para entrega a distribuidor</h5>
[SOLO si hay problemas, listar componentes críticos con sus subpartes específicas]
[SOLO si hay desgaste, listar componentes con desgaste]
[SOLO si hay toners críticos, listarlos]

<h5 style="margin:12px 0 6px;">Conclusión</h5>
<div style="padding:10px; border-radius:6px; background:[color según calidad]; color:[texto según calidad];">
<strong style="text-transform:capitalize;">[calidad]</strong>: [justificacion_calidad]
</div>

<p style="color:#888; font-size:12px; margin-top:10px;">
*Informe generado con IA basado en evaluación técnica del checklist*
</p>
</div>

COLORES PARA LA CONCLUSIÓN:
- buena: background:#e8f5e9; color:#2e7d32;
- regular: background:#fff8e1; color:#ef6c00;
- mala: background:#ffebee; color:#c62828;

RESPONDE SOLO CON EL JSON, SIN TEXTO ADICIONAL.
"""
        
        return prompt
    
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
        Devuelve TODAS las evaluaciones que requieren cambio y no tienen intervención con subpartes.
        (Estas serán listadas en el wizard.)
        """
        self.ensure_one()
        _logger.info("[_check_campos_requieren_cambio_sin_intervencion] Inicio id=%s", self.id)

        componentes_pendientes = []
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

            intervencion_existente = self.intervencion_ids.filtered(
                lambda x: x.componente == componente_code and x.detalle_ids
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

    def _get_componente_code_from_evaluacion(self, evaluacion):
        """
        Mapea una evaluación a su código de componente para intervenciones.
        Devuelve: ui_k/dev_c/fuser/itb/adf/fin/opt/papel/otro o False.
        """
        tipo = evaluacion.componente_tipo_id
        if not tipo:
            _logger.warning("[_get_componente_code_from_evaluacion] Eval %s sin tipo", evaluacion.id)
            return False

        tipo_key = self._rep__canonical_tipo_code(tipo)
        color = self._rep__get_color_code_from_eval(evaluacion)

        TIPO_TO_CODE = {
            'IU': {'k': 'ui_k', 'c': 'ui_c', 'm': 'ui_m', 'y': 'ui_y'},
            'DEVELOPER': {'k': 'dev_k', 'c': 'dev_c', 'm': 'dev_m', 'y': 'dev_y'},
            'FUSORA': 'fuser',
            'ITB': 'itb',
            'ADF': 'adf',
            'FINISHER': 'fin',
            'OPTICO': 'opt',
            'TRAY': 'papel',
            'BYPASS': 'papel',
            'PAPEL': 'papel',
        }

        _logger.debug(
            "[_get_componente_code_from_evaluacion] eval=%s raw_code='%s' name='%s' -> tipo_key='%s' color=%s",
            evaluacion.id, (tipo.code or ''), (tipo.name or ''), tipo_key, color
        )

        mapping = TIPO_TO_CODE.get(tipo_key)
        if isinstance(mapping, dict):
            if not color:
                _logger.debug("[_get_componente_code...] tipo_key=%s requiere color y no hay", tipo_key)
                return False
            res = mapping.get(color)
            _logger.debug("[_get_componente_code...] tipo_key=%s color=%s -> %s", tipo_key, color, res)
            return res
        else:
            _logger.debug("[_get_componente_code...] tipo_key=%s -> %s", tipo_key, mapping or False)
            return mapping or False

    def _ensure_intervencion_for_component(self, componente_code):
        """Crea o retorna intervención existente para un componente."""
        self.ensure_one()
        Interv = self.env['reparacion.intervencion']
        interv = Interv.search([
            ('reparacion_id', '=', self.id),
            ('componente', '=', componente_code),
        ], limit=1)
        if not interv:
            _logger.info("[_ensure_intervencion_for_component] creando intervencion %s para rep=%s", componente_code, self.id)
            interv = Interv.create({
                'reparacion_id': self.id,
                'componente': componente_code,
                'accion': 'cambiado',
                'observacion': _('Creado automáticamente al marcar "requiere cambio".'),
            })
        else:
            _logger.debug("[_ensure_intervencion_for_component] usando intervencion id=%s", interv.id)
        return interv

    # ========================================
    # WIZARD DE SUBPARTES
    # ========================================
    def _abrir_wizard_multiple_componentes(self, componentes_pendientes):
        """
        Abre un único wizard que lista TODOS los componentes que requieren cambio,
        con sus subpartes encontradas (usando fallbacks).
        """
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
            intervencion = self._ensure_intervencion_for_component(componente_code)

            # 1) Busca componentes de catálogo con fallbacks
            componentes_modelo = self._buscar_componentes_modelo_por_evaluacion(modelo_maquina, comp_info)
            _logger.debug("[_abrir_wizard_multiple_componentes] comp=%s encontró %s componentes modelo",
                          componente_code, len(componentes_modelo))

            # 2) Crear líneas por cada detalle encontrado
            total_lineas = 0
            for componente_modelo in componentes_modelo:
                if not getattr(componente_modelo, 'detalle_ids', False):
                    continue
                for detalle in componente_modelo.detalle_ids:
                    self.env['reparacion.add.subparts.wizard.line'].create({
                        'wizard_id': wizard.id,
                        'componente': componente_code,
                        'intervencion_id': intervencion.id,
                        'subparte_id': detalle.subparte_id.id,
                        'selected': False,
                        'accion_sub': 'cambiado',
                        'cantidad': detalle.cantidad or 1.0,
                    })
                    total_lineas += 1

            # 3) Si no hubo detalle_ids, usar fallback genérico por tipo (no dependiente de modelo)
            if total_lineas == 0:
                genericas = self._fallback_subpartes_por_tipo(comp_info['tipo_id'])
                if genericas:
                    _logger.warning("[_abrir_wizard_multiple_componentes] sin detalle_ids; usando %s subpartes genéricas por tipo.",
                                    len(genericas))
                    for sp in genericas:
                        self.env['reparacion.add.subparts.wizard.line'].create({
                            'wizard_id': wizard.id,
                            'componente': componente_code,
                            'intervencion_id': intervencion.id,
                            'subparte_id': sp.id,
                            'selected': False,
                            'accion_sub': 'cambiado',
                            'cantidad': 1.0,
                        })
                        total_lineas += 1

            # 4) Si aún no hay nada, notifica al usuario
            if total_lineas == 0:
                self.message_post(body=_(
                    "No se hallaron subpartes para <b>%(nombre)s</b> %(color)s. "
                    "Completa el catálogo de <i>modelo.maquina.componente</i> o defínelas en <i>componente.subparte</i>.",
                ) % {
                    'nombre': self.env['componente.tipo'].browse(comp_info['tipo_id']).name,
                    'color': comp_info.get('color_code') and f"({comp_info['color_code'].upper()})" or "",
                })

        # Título con todos los componentes involucrados
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
            'context': {'from_generar_informe': True},
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
        """Genera el informe técnico (con o sin IA según configuración) y/o abre wizard"""
        _logger.info("[action_generar_informe] >>> INICIO batch ids=%s", self.ids)

        acciones = []
        for rec in self:
            try:
                _logger.info("[action_generar_informe] Procesando rep.id=%s modo=%s", 
                           rec.id, rec.modo_generacion_informe)

                # 1) Juntar TODOS los que requieren cambio y no tienen subpartes
                campos_pendientes = rec._check_campos_requieren_cambio_sin_intervencion()
                if campos_pendientes:
                    _logger.info("[action_generar_informe] rep.id=%s -> abre wizard por pendientes=%s",
                                 rec.id, len(campos_pendientes))
                    return rec._abrir_wizard_multiple_componentes(campos_pendientes)

                # 2) Si hay contenido manual, no sobrescribir
                if (rec.informe and not rec._rep__html_is_empty(rec.informe) and not rec._rep__is_autogen_informe()):
                    rec.message_post(body=_("El informe ya fue editado manualmente. No se sobrescribió."))
                    _logger.info("[action_generar_informe] rep.id=%s -> informe manual existente, no se toca", rec.id)
                    continue

                # 3) Generar según modo (IA o automático)
                if rec.modo_generacion_informe == 'ia':
                    html, calidad, justificacion = rec._generar_informe_con_ia()
                else:
                    html, calidad = rec._rep__build_informe_html()
                    justificacion = ''

                # 4) Guardar resultados
                vals = {
                    'informe': html,
                    'informe_generado_por_ia': (rec.modo_generacion_informe == 'ia'),
                    'calidad_justificacion': justificacion,
                }
                
                # Seteo robusto de calidad, si el campo existe
                if 'calidad_id' in rec._fields:
                    field = rec._fields['calidad_id']
                    try:
                        if isinstance(field, fields.Selection) or isinstance(field, fields.Char):
                            vals['calidad_id'] = calidad
                        else:
                            Calidad = rec.env.get('reparacion.calidad')
                            if Calidad:
                                cal = Calidad.search([('code', '=', calidad)], limit=1) or \
                                      Calidad.search([('name', 'ilike', calidad)], limit=1)
                                if cal:
                                    vals['calidad_id'] = cal.id
                                    _logger.debug("[action_generar_informe] calidad M2O=%s", cal.id)
                    except Exception as fex:
                        _logger.warning("[action_generar_informe] No se pudo setear calidad_id (%s)", fex)

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
        
        # Buscar la intervención correspondiente
        intervencion = self.intervencion_ids.filtered(lambda x: x.componente == componente_code)
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
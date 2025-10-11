# -*- coding: utf-8 -*-
from odoo import _, models, fields, api
from odoo.exceptions import UserError
import logging
import re
import unicodedata

_logger = logging.getLogger(__name__)


class ReparacionesInforme(models.Model):
    _inherit = 'reparaciones.reparaciones'
    _description = 'Informe Reparaciones (Generación automática con hallazgos)'

    # ========================================
    # CAMPOS
    # ========================================
    intervencion_ids = fields.One2many(
        'reparacion.intervencion',
        'reparacion_id',
        string='Intervenciones / Cambios'
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
        1) eval_comp.color (si existiese en DBs viejas),
        2) eval_comp.color_id.code,
        3) eval_comp.color_id.name -> mapeado a k/c/m/y.
        """
        color_legacy = getattr(eval_comp, 'color', False)
        if color_legacy:
            code = str(color_legacy).strip().lower()
            if code in ('k', 'c', 'm', 'y'):
                _logger.debug("[_rep__get_color_code_from_eval] legacy color=%s", code)
                return code

        color_id = getattr(eval_comp, 'color_id', False)
        if color_id:
            # code directo
            code = getattr(color_id, 'code', False)
            if code:
                code = str(code).strip().lower()
                _logger.debug("[_rep__get_color_code_from_eval] color_id.code=%s", code)
                return code if code in ('k', 'c', 'm', 'y') else False
            # por nombre
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
        Devuelve un código canónico para el tipo de componente, independientemente de cómo
        esté escrito en el catálogo (con acentos, en español/inglés, con espacios, etc.).

        Posibles retornos (ejemplos):
          'IU', 'DEVELOPER', 'FUSORA', 'ITB', 'ADF', 'FINISHER', 'OPTICO', 'TRAY', 'BYPASS', 'PAPEL'
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
            # Unidad de imagen / tambor
            (('IMAGEN', 'IMAGING', 'DRUM', 'DRUM UNIT', 'IU', 'UNIDAD IMAGEN', 'UNIDAD DE IMAGEN'), 'IU'),
            # Developer
            (('DEVELOPER', 'DEV'), 'DEVELOPER'),
            # Fusora
            (('FUSORA', 'FUSOR', 'FUSER', 'FUSING', 'CALENTADOR'), 'FUSORA'),
            # Banda de transferencia
            (('ITB', 'TRANSFER BELT', 'TRANSFERENCIA', 'FAJA', 'BANDA'), 'ITB'),
            # Alimentador de documentos
            (('ADF', 'ALIMENTADOR', 'ALIMENTADOR DE DOCUMENTOS'), 'ADF'),
            # Finalizador
            (('FINISHER', 'FIN', 'ENGRAPADORA', 'GRAPADORA'), 'FINISHER'),
            # Óptico / escáner
            (('OPTICO', 'OPTICO/ESCANER', 'OPTICO ESCANER', 'OPTICO-ESCANER', 'OPTICAL', 'ESCANER', 'SCANNER', 'LSU'), 'OPTICO'),
            # Papel / bandejas / bypass
            (('TRAY', 'BANDEJA', 'BANDEJAS'), 'TRAY'),
            (('BYPASS',), 'BYPASS'),
            (('PAPEL', 'PAPER', 'TRANSPORTE PAPEL', 'TRANSPORTE DE PAPEL'), 'PAPEL'),
            # Transfer roller a fusora (como agrupabas)
            (('TRANSFER ROLLER', 'ROLLER TRANSFER', 'TRANSFER_ROLLER'), 'FUSORA'),
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
        """
        Retorna lista de funciones con falla desde evaluaciones.
        Busca componentes tipo FUNCION_* con estado 'falla'.
        """
        funciones_falla = []
        for eval_comp in self.evaluacion_ids:
            if not eval_comp.estado_id:
                continue
            tipo_code = (eval_comp.componente_tipo_id.code or '').strip().upper() if eval_comp.componente_tipo_id else ''
            if tipo_code.startswith('FUNCION_') and eval_comp.estado_id.code == 'falla':
                nombre = eval_comp.componente_tipo_id.name
                funciones_falla.append(nombre)
        _logger.debug("[_rep__funciones_con_falla] id=%s -> %s", self.id, funciones_falla)
        return funciones_falla

    def _rep__toners_criticos(self):
        """
        Retorna lista de consumibles críticos desde evaluaciones.
        Usa tipo 'TONER_SYSTEM' y estados 'vacio' o 'sin_botella'.
        """
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
        Clasifica hallazgos desde evaluaciones (NO desde campos Selection).
        Retorna dict: cambio_inmediato, desgaste, pendientes, no_aplica, score.
        """
        cambio_inmediato, desgaste, pendientes, no_aplica = [], [], [], []
        score = 0

        # Componentes
        for eval_comp in self.evaluacion_ids:
            if not eval_comp.estado_id:
                nombre = eval_comp.componente_tipo_id.name
                if eval_comp.color_id:
                    nombre = f"{nombre} ({eval_comp.color_id.name})"
                pendientes.append(nombre)
                score += 1
                continue

            estado_code = eval_comp.estado_id.code
            nombre = eval_comp.componente_tipo_id.name
            if eval_comp.color_id:
                nombre = f"{nombre} ({eval_comp.color_id.name})"

            # Prioridad (si existe)
            peso = 2  # default
            if hasattr(eval_comp.componente_tipo_id, 'prioridad'):
                prioridad = eval_comp.componente_tipo_id.prioridad
                if prioridad == '1':
                    peso = 3
                elif prioridad == '2':
                    peso = 2
                elif prioridad == '3':
                    peso = 1

            if estado_code in ('requiere_cambio', 'cambio_de_repuestos'):
                cambio_inmediato.append(nombre); score += 3 * peso
            elif estado_code in ('regular', 'gastada_pero_puede_trabajar', 'mantenimiento'):
                desgaste.append(nombre); score += 2 * peso
            elif estado_code in ('sin_revisar', 'sin_probar'):
                pendientes.append(nombre); score += 1 * peso
            elif estado_code == 'no_aplica':
                no_aplica.append(nombre)

        # Accesorios (si existe el one2many)
        for eval_acc in getattr(self, 'accesorio_eval_ids', self.env['reparacion.accesorio.evaluacion']):
            if not eval_acc.estado_id:
                pendientes.append(eval_acc.tipo_id.name); score += 1; continue
            estado_code = eval_acc.estado_id.code
            nombre = eval_acc.tipo_id.name
            if estado_code == 'instalado_con_falla':
                cambio_inmediato.append(nombre); score += 3
            elif estado_code == 'no_instalado':
                desgaste.append(f"{nombre} (no instalado)"); score += 1
            elif estado_code == 'no_aplica':
                no_aplica.append(nombre)

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
    # CONSTRUCCIÓN DEL INFORME HTML
    # ========================================
    def _rep__build_informe_html(self):
        """Construye el HTML del informe técnico."""
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
    # VALIDACIÓN PARA WIZARD
    # ========================================
    def _check_campos_requieren_cambio_sin_intervencion(self):
        """
        Retorna lista de evaluaciones que requieren cambio pero no tienen intervenciones CON SUBPARTES.
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
                color_code = self._rep__get_color_code_from_eval(evaluacion) or None
                comp = {
                    'evaluacion_id': evaluacion.id,
                    'componente_code': componente_code,
                    'tipo_id': evaluacion.componente_tipo_id.id,
                    'color_code': color_code,
                }
                _logger.debug("[_check_campos...] pendiente=%s", comp)
                componentes_pendientes.append(comp)

        _logger.info("[_check_campos...] total_pendientes=%s id=%s", len(componentes_pendientes), self.id)
        return componentes_pendientes

    def _get_componente_code_from_evaluacion(self, evaluacion):
        """
        Mapea una evaluación a su código de componente para intervenciones.
        Devuelve str como: ui_k, dev_c, fuser, itb, adf, fin, opt, papel, otro... o False.
        """
        tipo = evaluacion.componente_tipo_id
        if not tipo:
            _logger.warning("[_get_componente_code_from_evaluacion] Eval %s sin tipo", evaluacion.id)
            return False

        tipo_key = self._rep__canonical_tipo_code(tipo)
        color = self._rep__get_color_code_from_eval(evaluacion)

        TIPO_TO_CODE = {
            # Sensibles a color
            'IU': {'k': 'ui_k', 'c': 'ui_c', 'm': 'ui_m', 'y': 'ui_y'},
            'DEVELOPER': {'k': 'dev_k', 'c': 'dev_c', 'm': 'dev_m', 'y': 'dev_y'},

            # No sensibles a color
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
        """Abre wizard con subpartes del modelo de máquina."""
        self.ensure_one()
        _logger.info("[_abrir_wizard_multiple_componentes] start id=%s count=%s", self.id, len(componentes_pendientes))

        if not componentes_pendientes:
            return

        wizard = self.env['reparacion.add.subparts.wizard'].create({'reparacion_id': self.id})
        modelo_maquina = self.maquina_id  # usar record, no name
        if not modelo_maquina:
            _logger.error("[_abrir_wizard_multiple_componentes] Máquina sin modelo id=%s", self.id)
            raise UserError(_("La máquina no tiene modelo asignado"))

        for comp_info in componentes_pendientes:
            componente_code = comp_info['componente_code']
            intervencion = self._ensure_intervencion_for_component(componente_code)

            componentes_modelo = self._buscar_componentes_modelo_por_evaluacion(modelo_maquina, comp_info)
            _logger.debug("[_abrir_wizard_multiple_componentes] comp=%s encontró %s componentes modelo",
                          componente_code, len(componentes_modelo))

            for componente_modelo in componentes_modelo:
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

        # Título
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
        Busca componentes del modelo según la evaluación.

        Args:
            modelo_maquina: record de modelo.maquina
            comp_info: { evaluacion_id, tipo_id, color_code?, componente_code }
        """
        domain = [
            ('modelo_id', '=', modelo_maquina.id),
            ('tipo_id', '=', comp_info['tipo_id']),
        ]

        color_code = comp_info.get('color_code')
        mmc = self.env['modelo.maquina.componente']
        if color_code:
            if 'color' in mmc._fields:
                domain.append(('color', '=', color_code))
                _logger.debug("[_buscar_componentes...] usando campo 'color'='%s'", color_code)
            elif 'color_id' in mmc._fields:
                color_rec = self.env['color.tipo'].search([('code', '=', color_code)], limit=1)
                if color_rec:
                    domain.append(('color_id', '=', color_rec.id))
                    _logger.debug("[_buscar_componentes...] usando 'color_id'=%s", color_rec.id)
                else:
                    _logger.warning("[_buscar_componentes...] color.tipo code='%s' no encontrado; omito filtro", color_code)
            else:
                _logger.debug("[_buscar_componentes...] catálogo sin campo de color; omito filtro")

        res = mmc.search(domain)
        _logger.debug("[_buscar_componentes...] domain=%s -> %s registros", domain, len(res))
        return res

    # ========================================
    # ACCIÓN DEL BOTÓN
    # ========================================
    def action_generar_informe(self):
        """Genera el informe técnico automáticamente y/o abre wizard de subpartes."""
        _logger.info("[action_generar_informe] >>> INICIO batch ids=%s", self.ids)

        acciones = []
        for rec in self:
            try:
                _logger.info("[action_generar_informe] Procesando rep.id=%s", rec.id)

                # 1) Validación de pendientes que requieren wizard
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

                # 3) Generar informe
                html, calidad = rec._rep__build_informe_html()

                vals = {'informe': html}
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
                rec.message_post(body=_("Informe técnico generado automáticamente."))
                _logger.info("[action_generar_informe] rep.id=%s -> informe generado (len=%s)", rec.id, len(html))
                acciones.append(rec.id)

            except Exception as e:
                _logger.exception("[action_generar_informe] rep.id=%s ERROR %s", rec.id, e)
                rec.message_post(body=_("No se pudo generar el informe: %s") % e)

        _logger.info("[action_generar_informe] <<< FIN. generados=%s", len(acciones))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informe técnico'),
                'message': _('Informe generado correctamente.') if acciones else _('No se generó ningún informe.'),
                'type': 'success' if acciones else 'warning'
            }
        }

from odoo import _, models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging
import re

_logger = logging.getLogger(__name__)


class ReparacionesInforme(models.Model):
    _inherit = 'reparaciones.reparaciones'
    _description = 'Informe Reparaciones'

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
        """Detecta si el informe fue autogenerado"""
        html = (self.informe or '').lower()
        return 'data-autogen="1"' in html

    def _rep__html_is_empty(self, html):
        """True si el HTML está vacío (solo tags/espacios/&nbsp;/<br>)"""
        if not html:
            return True
        s = html.replace('&nbsp;', ' ')
        s = re.sub(r'<br\s*/?>', ' ', s, flags=re.I)
        s = re.sub(r'<[^>]*>', '', s)  # quitar etiquetas
        return s.strip() == ''

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
            
            tipo_code = eval_comp.componente_tipo_id.code if eval_comp.componente_tipo_id else ''
            
            if tipo_code.startswith('FUNCION_') and eval_comp.estado_id.code == 'falla':
                nombre = eval_comp.componente_tipo_id.name
                funciones_falla.append(nombre)
        
        return funciones_falla

    def _rep__toners_criticos(self):
        """
        Retorna lista de tóners en estado crítico desde evaluaciones.
        Busca componentes tipo TONER_* con estados 'vacio' o 'sin_botella'.
        """
        toners_criticos = []
        
        for eval_comp in self.evaluacion_ids:
            if not eval_comp.estado_id:
                continue
            
            tipo_code = eval_comp.componente_tipo_id.code if eval_comp.componente_tipo_id else ''
            
            if tipo_code == 'TONER_SYSTEM' and eval_comp.estado_id.code in ('vacio', 'sin_botella'):
                nombre = eval_comp.componente_tipo_id.name
                if eval_comp.color_id:
                    nombre = f"{nombre} {eval_comp.color_id.name}"
                toners_criticos.append(nombre)
        
        return toners_criticos

    def _rep__collect_findings(self):
        """
        Clasifica hallazgos desde evaluaciones (NO desde campos Selection).
        Retorna dict con:
        - cambio_inmediato: componentes/accesorios que requieren cambio urgente
        - desgaste: componentes con desgaste pero operativos
        - pendientes: evaluaciones sin estado asignado
        - no_aplica: componentes/accesorios marcados como no aplica
        - score: puntuación ponderada
        """
        cambio_inmediato = []
        desgaste = []
        pendientes = []
        no_aplica = []
        score = 0
        
        # ========================================
        # ANALIZAR COMPONENTES
        # ========================================
        for eval_comp in self.evaluacion_ids:
            if not eval_comp.estado_id:
                # Sin estado asignado
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
            
            # Prioridad del tipo de componente
            peso = 2  # peso por defecto
            if hasattr(eval_comp.componente_tipo_id, 'prioridad'):
                prioridad = eval_comp.componente_tipo_id.prioridad
                if prioridad == '1':  # Crítico
                    peso = 3
                elif prioridad == '2':  # Medio
                    peso = 2
                elif prioridad == '3':  # Bajo
                    peso = 1
            
            # Clasificar según estado
            if estado_code in ('requiere_cambio', 'cambio_de_repuestos'):
                cambio_inmediato.append(nombre)
                score += 3 * peso
            elif estado_code in ('regular', 'gastada_pero_puede_trabajar', 'mantenimiento'):
                desgaste.append(nombre)
                score += 2 * peso
            elif estado_code in ('sin_revisar', 'sin_probar'):
                pendientes.append(nombre)
                score += 1 * peso
            elif estado_code == 'no_aplica':
                no_aplica.append(nombre)
            # Estados OK: 'nuevo', 'revisado', 'correcto' → no se listan
        
        # ========================================
        # ANALIZAR ACCESORIOS
        # ========================================
        for eval_acc in self.accesorio_eval_ids:
            if not eval_acc.estado_id:
                pendientes.append(eval_acc.tipo_id.name)
                score += 1
                continue
            
            estado_code = eval_acc.estado_id.code
            nombre = eval_acc.tipo_id.name
            
            if estado_code == 'instalado_con_falla':
                cambio_inmediato.append(nombre)
                score += 3
            elif estado_code == 'no_instalado':
                desgaste.append(f"{nombre} (no instalado)")
                score += 1
            elif estado_code == 'no_aplica':
                no_aplica.append(nombre)
            # 'instalado_operativo' → OK, no se lista
        
        return {
            'cambio_inmediato': cambio_inmediato,
            'desgaste': desgaste,
            'pendientes': pendientes,
            'no_aplica': no_aplica,
            'score': score,
        }

    def _rep__calc_calidad(self, findings, funciones_falla, toners_criticos):
        """Calcula calidad general de la máquina"""
        if findings['cambio_inmediato'] or funciones_falla or toners_criticos:
            return 'mala'
        if findings['desgaste'] or findings['pendientes']:
            return 'regular'
        return 'buena'

    # ========================================
    # CONSTRUCCIÓN DEL INFORME HTML
    # ========================================
    def _rep__build_informe_html(self):
        """Construye el HTML del informe técnico"""
        self.ensure_one()

        f = self._rep__collect_findings()
        funciones_no = self._rep__funciones_con_falla()
        toners_crit = self._rep__toners_criticos()

        # Conclusión orientada a venta B2B
        calidad = self._rep__calc_calidad(f, funciones_no, toners_crit)
        if calidad == 'mala':
            concl = _("Unidad requiere inversión inmediata en repuestos antes de entregarse a distribuidor.")
        elif calidad == 'regular':
            concl = _("Unidad operativa para prueba; sugerimos cambio preventivo previo a la entrega.")
        else:
            concl = _("Unidad lista para entrega; se recomienda mantenimiento estándar en instalación.")

        texto_general = _(
            "Se realizó limpieza, puesta a punto básica y verificación general de funcionamiento y consumibles para la venta mayorista."
        )

        # Paleta de colores
        color_sev = {
            'critico': '#d32f2f',
            'medio':   '#ef6c00',
            'pend':    '#616161',
        }
        color_calidad_bg = {
            'mala':    '#ffebee',
            'regular': '#fff8e1',
            'buena':   '#e8f5e9',
        }
        color_calidad_txt = {
            'mala':    '#c62828',
            'regular': '#ef6c00',
            'buena':   '#2e7d32',
        }

        # Bloques de observaciones
        bloques = []
        if funciones_no:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Funciones con incidencia')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in funciones_no) + "</ul>"
            )
        if f['cambio_inmediato']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Puntos críticos (cambio inmediato)')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in f['cambio_inmediato']) + "</ul>"
            )
        if f['desgaste']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['medio']};'><strong>{_('Componentes con desgaste')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in f['desgaste']) + "</ul>"
            )
        if f['pendientes']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['pend']};'><strong>{_('Pendientes / sin revisar')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in f['pendientes']) + "</ul>"
            )
        if toners_crit:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Consumibles críticos')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in toners_crit) + "</ul>"
            )

        # Sección de repuestos cambiados
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
        return html, calidad

    def _generar_seccion_repuestos(self):
        """Genera la sección HTML de componentes y subpartes que requieren cambio"""
        if not self.intervencion_ids:
            return ""
        
        intervenciones_con_detalles = self.intervencion_ids.filtered(lambda x: x.detalle_ids)
        if not intervenciones_con_detalles:
            return ""
        
        repuestos_por_componente = {}
        
        for intervencion in intervenciones_con_detalles:
            componente_nombre = self._get_component_display_name(intervencion.componente)
            if componente_nombre not in repuestos_por_componente:
                repuestos_por_componente[componente_nombre] = []
            
            for detalle in intervencion.detalle_ids:
                repuestos_por_componente[componente_nombre].append(detalle.subparte_id.name)
        
        if not repuestos_por_componente:
            return ""
        
        html_componentes = []
        for componente, subpartes in repuestos_por_componente.items():
            html_componentes.append(f"<p style='margin:8px 0 4px 0; font-weight:bold;'>{componente}</p>")
            html_componentes.append("<ul style='margin:0 0 8px 20px;'>")
            for subparte in subpartes:
                html_componentes.append(f"<li>{subparte}</li>")
            html_componentes.append("</ul>")
        
        return f"""
<p style='margin:6px 0;color:#e65100;'><strong>{_('Subpartes específicas que requieren cambio')}:</strong></p>
<div style='margin:0 0 8px 10px;'>
{"".join(html_componentes)}
</div>
"""

    def _get_component_display_name(self, componente_code):
        """Obtiene el nombre display de un componente basado en su código"""
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
        return component_names.get(componente_code, componente_code)

    # ========================================
    # VALIDACIÓN PARA WIZARD
    # ========================================
    def _check_campos_requieren_cambio_sin_intervencion(self):
        """
        Retorna lista de evaluaciones que requieren cambio pero no tienen intervenciones CON SUBPARTES.
        """
        self.ensure_one()
        componentes_pendientes = []
        
        for evaluacion in self.evaluacion_ids:
            if not evaluacion.estado_id:
                continue
            
            # Solo procesar si requiere cambio
            if evaluacion.estado_id.code != 'requiere_cambio':
                continue
            
            # Mapear a código de componente
            componente_code = self._get_componente_code_from_evaluacion(evaluacion)
            
            if not componente_code:
                _logger.warning(f"No se pudo mapear evaluación {evaluacion.id} a código de intervención")
                continue
            
            # Verificar si existe intervención CON detalles
            intervencion_existente = self.intervencion_ids.filtered(
                lambda x: x.componente == componente_code and x.detalle_ids
            )
            
            if not intervencion_existente:
                componentes_pendientes.append({
                    'evaluacion_id': evaluacion.id,
                    'componente_code': componente_code,
                    'tipo_id': evaluacion.componente_tipo_id.id,
                    'color': evaluacion.color if evaluacion.color else None,
                })
        
        return componentes_pendientes

    def _get_componente_code_from_evaluacion(self, evaluacion):
        """
        Mapea una evaluación a su código de componente para intervenciones.
        
        Args:
            evaluacion: Registro de reparacion.componente.evaluacion
        
        Returns:
            Código de componente (str) o False
        """
        tipo_code = evaluacion.componente_tipo_id.code
        color = evaluacion.color  # 'k', 'c', 'm', 'y' o False
        
        # Mapeo de tipos a códigos
        TIPO_TO_CODE = {
            'UI': {
                'k': 'ui_k',
                'c': 'ui_c',
                'm': 'ui_m',
                'y': 'ui_y',
            },
            'DEVELOPER': {
                'k': 'dev_k',
                'c': 'dev_c',
                'm': 'dev_m',
                'y': 'dev_y',
            },
            'FUSORA': 'fuser',
            'TRANSFER_ROLLER': 'fuser',
            'FAJA': 'itb',
            'ADF': 'adf',
            'FINISHER': 'fin',
            'OPTICO': 'opt',
            'BYPASS': 'papel',
            'TRAY': 'papel',
        }
        
        mapping = TIPO_TO_CODE.get(tipo_code)
        
        if isinstance(mapping, dict):
            # Componente sensible a color
            if not color:
                return False
            return mapping.get(color)
        else:
            # Componente sin color
            return mapping

    def _ensure_intervencion_for_component(self, componente_code):
        """Crea o retorna intervención existente para un componente"""
        self.ensure_one()
        Interv = self.env['reparacion.intervencion']
        interv = Interv.search([
            ('reparacion_id', '=', self.id),
            ('componente', '=', componente_code),
        ], limit=1)
        if not interv:
            interv = Interv.create({
                'reparacion_id': self.id,
                'componente': componente_code,
                'accion': 'cambiado',
                'observacion': _('Creado automáticamente al marcar "requiere cambio".'),
            })
        return interv

    # ========================================
    # WIZARD DE SUBPARTES
    # ========================================
    def _abrir_wizard_multiple_componentes(self, componentes_pendientes):
        """Abre wizard con subpartes del modelo de máquina"""
        self.ensure_one()
        
        if not componentes_pendientes:
            return
        
        wizard = self.env['reparacion.add.subparts.wizard'].create({
            'reparacion_id': self.id,
        })
        
        modelo_maquina = self.maquina_id.name
        
        if not modelo_maquina:
            raise UserError(_("La máquina no tiene modelo asignado"))
        
        for comp_info in componentes_pendientes:
            componente_code = comp_info['componente_code']
            
            # Crear intervención
            intervencion = self._ensure_intervencion_for_component(componente_code)
            
            # Buscar componentes del modelo según evaluación
            componentes_modelo = self._buscar_componentes_modelo_por_evaluacion(
                modelo_maquina,
                comp_info
            )
            
            # Agregar subpartes
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
        
        # Construir título
        nombres = []
        for comp in componentes_pendientes:
            eval_rec = self.env['reparacion.componente.evaluacion'].browse(comp['evaluacion_id'])
            nombre = eval_rec.componente_tipo_id.name
            if comp.get('color'):
                nombre = f"{nombre} ({comp['color'].upper()})"
            nombres.append(nombre)
        
        titulo = f"Subpartes para: {', '.join(nombres)}"
        
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
            modelo_maquina: Registro de modelo.maquina
            comp_info: Dict con evaluacion_id, tipo_id, color
        
        Returns:
            Recordset de modelo.maquina.componente
        """
        domain = [
            ('modelo_id', '=', modelo_maquina.id),
            ('tipo_id', '=', comp_info['tipo_id'])
        ]
        
        if comp_info.get('color'):
            domain.append(('color', '=', comp_info['color']))
        
        return self.env['modelo.maquina.componente'].search(domain)

    # ========================================
    # ACCIÓN DEL BOTÓN
    # ========================================
    def action_generar_informe(self):
        """Genera el informe técnico automáticamente"""
        for rec in self:
            try:
                # VALIDACIÓN: Verificar componentes que requieren cambio
                campos_pendientes = rec._check_campos_requieren_cambio_sin_intervencion()
                if campos_pendientes:
                    return rec._abrir_wizard_multiple_componentes(campos_pendientes)
                
                # Si hay contenido manual, no sobrescribir
                if (rec.informe
                    and not rec._rep__html_is_empty(rec.informe)
                    and not rec._rep__is_autogen_informe()):
                    rec.message_post(body=_("El informe ya fue editado manualmente. No se sobrescribió."))
                    continue

                # Generar informe
                html, calidad = rec._rep__build_informe_html()
                rec.write({'informe': html, 'calidad_id': calidad})
                rec.message_post(body=_("Informe técnico generado automáticamente."))

            except Exception as e:
                _logger.exception("Error generando informe: %s", e)
                rec.message_post(body=_("No se pudo generar el informe: %s") % e)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Informe técnico'),
                'message': _('Informe generado correctamente.'),
                'type': 'success'
            }
        }
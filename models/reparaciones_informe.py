from odoo import _, models, fields, api, exceptions, _
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re
import qrcode
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)
import requests
import json
from odoo.tools import config
from odoo.exceptions import UserError
import zipfile
import io
from odoo.http import request
import uuid

class ReparacionesInforme(models.Model):
    _inherit = 'reparaciones.reparaciones'
    _description = 'Informe Reparaciones'

         # --- NUEVO: Intervenciones y subpartes (para repuestos/cambios) ---
    intervencion_ids = fields.One2many(
        'reparacion.intervencion',
        'reparacion_id',
        string='Intervenciones / Cambios'
    )
    # Mapa: campo de selección -> código de componente (ReparacionSubparte.COMPONENTE)
    _COMP_MAP_REQCAMBIO = {
        # Módulos / sistemas
        'adf_id': 'adf',
        'finalizador_id': 'fin',
        'bypass_id': 'papel',
        'transfer_id': 'itb',
        'fusora_id': 'fuser',
        'rodillo_id': 'fuser',   # si prefieres separar rodillo/calor en otro componente, cámbialo
        'calor_id':   'fuser',

        # Unidades de imagen / developers
        'black_id':      'ui_k',
        'developerk_id': 'dev_k',
        'magenta_id':    'ui_m',
        'developerm_id': 'dev_m',
        'cyan_id':       'ui_c',
        'developerc_id': 'dev_c',
        'yellow_id':     'ui_y',
        'developery_id': 'dev_y',
    }


    _REP_CHECK_MAP = {
        'adf_id': ('ADF', 2),
        'bypass_id': ('Bypass', 1),
        'finalizador_id': ('Finalizador', 2),
        'tray1_id': ('Bandeja 1', 1),
        'tray2_id': ('Bandeja 2', 1),
        'tray3_id': ('Bandeja 3', 1),
        'tray4_id': ('Bandeja 4', 1),
        'optico_id': ('Sistema óptico', 3),   # aquí tus valores: sin_revisar/mantenimiento/revisado
        'transfer_id': ('Banda de transferencia', 3),
        'fusora_id': ('Faja fusora', 3),
        'rodillo_id': ('Rodillo de presión', 2),
        'calor_id': ('Rodillo de calor', 2),
        'tacho_id': ('Tacho residual', 1),    # sí/no/no_aplica
    }

    # Unidades de imagen / developers con valores: requiere_cambio / nuevo / regular / gastada_pero_puede_trabajar / (no_aplica en color)
    _REP_UNIDADES_IMG = {
        'black_id': ('Unidad de imagen Black', 3),
        'developerk_id': ('Developer Black', 3),
        'magenta_id': ('Unidad de imagen Magenta', 3),
        'developerm_id': ('Developer Magenta', 3),
        'cyan_id': ('Unidad de imagen Cyan', 3),
        'developerc_id': ('Developer Cyan', 3),
        'yellow_id': ('Unidad de imagen Yellow', 3),
        'developery_id': ('Developer Yellow', 3),
    }

    # Funciones con valores: correcto / sin_probar / falla / no_aplica
    _REP_FUNCIONES = [
        ('copia_id', 'Copia'),
        ('impresion_id', 'Impresión'),
        ('impresion_usb_id', 'Impresión USB'),
        ('scaner_smb_id', 'Scanner SMB'),
        ('scaner_usb_id', 'Scanner USB'),
        ('scaner_ftp_id', 'Scanner FTP'),
        ('scaner_mail_id', 'Scanner Mail'),
    ]

    # Tóners
    _REP_TONERS = [
        ('toner_black_id', 'Tóner Negro'),
        ('toner_cyan_id', 'Tóner Cian'),
        ('toner_magenta_id', 'Tóner Magenta'),
        ('toner_yellow_id', 'Tóner Amarillo'),
    ]

    # ====================
    # Helpers de extracción
    # ====================
    def _rep__is_autogen_informe(self):
        html = (self.informe or '').lower()
        return 'data-autogen="1"' in html

    def _rep__funciones_con_falla(self):
        """
        Retorna lista de funciones con falla desde evaluaciones.
        Busca componentes tipo FUNCION_* con estado 'falla'.
        """
        funciones_falla = []
        
        for eval_comp in self.evaluacion_ids:
            if not eval_comp.estado_id:
                continue
            
            # Verificar si es un componente de tipo función
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
            
            # Verificar si es un tóner
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
        Retorna:
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
            
            # Prioridad del tipo de componente (si existe)
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
                # No es crítico, pero se menciona
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
        # Régimen simple y efectivo:
        if findings['cambio_inmediato'] or funciones_falla or toners_criticos:
            return 'mala'
        if findings['desgaste'] or findings['pendientes']:
            return 'regular'
        return 'buena'

    def _rep__infer_intervencion(self, findings, funciones_falla):
        """
        Deducción automática del 'tipo de intervención' para el texto del informe (no crea campos nuevos):
        - Si hay requerimientos de cambio o funciones con falla → Reparación / cambio de repuestos
        - Si hay 'mantenimiento'/'desgaste' y sin fallas graves → Mantenimiento preventivo
        - Si todo está ok o sin revisar → Revisión/Diagnóstico
        """
        if findings['cambio_inmediato'] or funciones_falla:
            return "Reparación / cambio de repuestos"
        if findings['desgaste'] and not funciones_falla:
            return "Mantenimiento preventivo"
        return "Revisión / diagnóstico"

    # ==========================
    # Constructor del HTML (botón)
    # ==========================
    def _rep__build_informe_html(self):
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

        # Texto general para máquina usada destinada a reventa
        texto_general = _(
            "Se realizó limpieza, puesta a punto básica y verificación general de funcionamiento y consumibles para la venta mayorista."
        )

        # Paleta de colores (inline CSS para HTML/PDF)
        color_sev = {
            'critico': '#d32f2f',   # rojo
            'medio':   '#ef6c00',   # naranja
            'pend':    '#616161',   # gris
        }
        color_calidad_bg = {
            'mala':    '#ffebee',   # fondo rosado claro
            'regular': '#fff8e1',   # fondo ámbar claro
            'buena':   '#e8f5e9',   # fondo verde claro
        }
        color_calidad_txt = {
            'mala':    '#c62828',
            'regular': '#ef6c00',
            'buena':   '#2e7d32',
        }

        # Bloques de observaciones con lenguaje comercial
        bloques = []
        if funciones_no:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Funciones con incidencia')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in funciones_no) + "</ul>"
            )
        if f['cambio_inmediato']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Puntos críticos para entrega (cambio inmediato)')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in f['cambio_inmediato']) + "</ul>"
            )
        if f['desgaste']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['medio']};'><strong>{_('Componentes con desgaste (recomendado cambio preventivo)')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in f['desgaste']) + "</ul>"
            )
        if f['pendientes']:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['pend']};'><strong>{_('Pendientes menores / sin revisar')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in f['pendientes']) + "</ul>"
            )
        if toners_crit:
            bloques.append(
                f"<p style='margin:6px 0;color:{color_sev['critico']};'><strong>{_('Consumibles críticos (no incluidos en garantía de venta)')}:</strong></p>"
                "<ul style='margin:0 0 8px 18px;'>"
                + "".join(f"<li>{x}</li>" for x in toners_crit) + "</ul>"
            )

        # NUEVO: Agregar sección de repuestos cambiados
        repuestos_html = self._generar_seccion_repuestos()
        if repuestos_html:
            bloques.append(repuestos_html)

        observ_html = ""
        if bloques:
            observ_html = "<h5 style='margin:12px 0 6px;'>" + _("Observaciones para entrega a distribuidor") + "</h5>" + "".join(bloques)

        # SOLO "Se realizó…" → "Conclusión"
        html = f"""
    <div data-autogen="1" style="font-family: Arial; line-height:1.5;">
    <p>{texto_general}</p>
    {observ_html}
    <h5 style="margin:12px 0 6px;">{_('Conclusión')}</h5>
    <div style="padding:10px;border-radius:6px;background:{color_calidad_bg[calidad]};color:{color_calidad_txt[calidad]};">
        <strong style="text-transform:capitalize;">{calidad}</strong>: {concl}
    </div>
    <p style="color:#888; font-size:12px; margin-top:10px;">
        *{_('Bloque generado automáticamente a partir del checklist técnico, orientado a venta B2B.')}*
    </p>
    </div>
    """
        return html, calidad

    def _generar_seccion_repuestos(self):
        """Genera la sección HTML de componentes y subpartes que requieren cambio"""
        if not self.intervencion_ids:
            return ""
        
        # Filtrar intervenciones que tienen detalles
        intervenciones_con_detalles = self.intervencion_ids.filtered(lambda x: x.detalle_ids)
        if not intervenciones_con_detalles:
            return ""
        
        # Usar mapeo de códigos a nombres display
        repuestos_por_componente = {}
        
        for intervencion in intervenciones_con_detalles:
            componente_nombre = self._get_component_display_name(intervencion.componente)
            if componente_nombre not in repuestos_por_componente:
                repuestos_por_componente[componente_nombre] = []
            
            # Agregar subpartes (ahora usa componente.subparte)
            for detalle in intervencion.detalle_ids:
                repuestos_por_componente[componente_nombre].append(detalle.subparte_id.name)
        
        if not repuestos_por_componente:
            return ""
        
        # Generar HTML simple
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


    # ==========================
    # Acción del botón
    # ==========================

    def _rep__html_is_empty(self, html):
        """True si el HTML está vacío (solo tags/espacios/&nbsp;/<br>)."""
        if not html:
            return True
        s = html.replace('&nbsp;', ' ')
        s = re.sub(r'<br\s*/?>', ' ', s, flags=re.I)
        s = re.sub(r'<[^>]*>', '', s)  # quitar etiquetas
        return s.strip() == ''

    def _abrir_wizard_multiple_componentes(self, campos_pendientes):
        """Abre wizard con subpartes del modelo específico de máquina"""
        self.ensure_one()
        
        # Crear wizard
        wizard = self.env['reparacion.add.subparts.wizard'].create({
            'reparacion_id': self.id,
        })
        
        # Obtener modelo de máquina
        modelo_maquina = self.maquina_id.name  # modelo.maquina
        
        if not modelo_maquina:
            raise UserError(_("La máquina no tiene modelo asignado"))
        
        for field_name, componente_code in campos_pendientes:
            # Crear intervención
            intervencion = self._ensure_intervencion_for_component(componente_code)
            
            # Buscar componentes de este modelo que correspondan al tipo
            componentes_modelo = self._buscar_componentes_por_checklist(modelo_maquina, field_name)
            
            # Agregar todas las subpartes de los componentes encontrados
            for componente_modelo in componentes_modelo:
                # ✅ CAMBIO: subparte_ids → detalle_ids
                for detalle in componente_modelo.detalle_ids:
                    self.env['reparacion.add.subparts.wizard.line'].create({
                        'wizard_id': wizard.id,
                        'componente': componente_code,
                        'intervencion_id': intervencion.id,
                        'subparte_id': detalle.subparte_id.id,  # ✅ Acceder al subparte a través de detalle
                        'selected': False,
                        'accion_sub': 'cambiado',
                        'cantidad': detalle.cantidad,  # ✅ Usar la cantidad del detalle
                    })
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Subpartes Específicas - {modelo_maquina.name}',
            'res_model': 'reparacion.add.subparts.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': self.env.ref('sat.view_reparacion_add_subparts_wizard_form').id,
            'target': 'new',
            'context': {'from_generar_informe': True},
        }
    def _buscar_componentes_por_checklist(self, modelo_maquina, field_name):
        """Busca componentes del modelo según el campo del checklist marcado"""
        
        # MAPEO CORREGIDO con los códigos reales de tu base de datos
        mapeo_campos = {
            # Unidades de imagen
            'black_id': ('Imagen Black', 'k'),  # Cambié 'IU' por 'Imagen Black'
            'magenta_id': ('Imagen Magenta', 'm'),
            'cyan_id': ('Imagen Cyan', 'c'),
            'yellow_id': ('Imagen Yellow', 'y'),
            
            # Developers
            'developerk_id': ('DEVELOPER', 'k'),
            'developerm_id': ('DEVELOPER', 'm'),
            'developerc_id': ('DEVELOPER', 'c'),
            'developery_id': ('DEVELOPER', 'y'),
            
            # Otros componentes sin color
            'transfer_id': ('FAJA', None),
            'fusora_id': ('Fusora', None),    # Cambié 'FUSORA' por 'Fusora'
            'rodillo_id': ('Fusora', None),   # Cambié 'FUSORA' por 'Fusora'
            'calor_id': ('Fusora', None),     # Cambié 'FUSORA' por 'Fusora'
            'adf_id': ('ADF', None),
            'finalizador_id': ('FINISHER', None),
            'optico_id': ('OPTICO', None),
            'bypass_id': ('TRAY', None),
            'tray1_id': ('TRAY', None),
            'tray2_id': ('TRAY', None),
            'tray3_id': ('TRAY', None),
            'tray4_id': ('TRAY', None),
        }
        
        if field_name not in mapeo_campos:
            return self.env['modelo.maquina.componente']
        
        codigo_componente, color = mapeo_campos[field_name]
        
        # Buscar tipo de componente por código
        tipo_componente = self.env['componente.tipo'].search([('code', '=', codigo_componente)], limit=1)
        if not tipo_componente:
            return self.env['modelo.maquina.componente']
        
        # Filtrar componentes del modelo
        domain = [
            ('modelo_id', '=', modelo_maquina.id),
            ('tipo_id', '=', tipo_componente.id)
        ]
        
        # Agregar filtro de color si aplica
        if color and tipo_componente.is_color_sensitive:
            domain.append(('color', '=', color))
        
        return self.env['modelo.maquina.componente'].search(domain)
    def action_generar_informe(self):
        for rec in self:
            try:
                # VALIDACIÓN: Verificar campos que requieren cambio sin intervenciones detalladas
                campos_pendientes = rec._check_campos_requieren_cambio_sin_intervencion()
                if campos_pendientes:
                    # Abrir wizard unificado con todas las subpartes
                    return rec._abrir_wizard_multiple_componentes(campos_pendientes)
                
                # Si hay contenido NO vacío y NO es autogenerado → se supone manual
                if (rec.informe
                    and not rec._rep__html_is_empty(rec.informe)
                    and not rec._rep__is_autogen_informe()):
                    rec.message_post(body=_("El informe ya fue editado manualmente. No se sobrescribió."))
                    continue

                html, calidad = rec._rep__build_informe_html()
                rec.write({'informe': html, 'calidad_id': calidad})
                rec.message_post(body=_("Informe técnico generado automáticamente."))

            except Exception as e:
                _logger.exception("Error generando informe en reparaciones: %s", e)
                rec.message_post(body=_("No se pudo generar el informe: %s") % e)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Informe técnico'), 'message': _('Informe generado.'), 'type': 'success'}
        }
    def _check_campos_requieren_cambio_sin_intervencion(self):
        """Retorna lista de componentes que requieren cambio pero no tienen intervenciones CON SUBPARTES"""
        self.ensure_one()
        componentes_pendientes = []
        
        for field_name, componente_code in self._COMP_MAP_REQCAMBIO.items():
            valor_campo = getattr(self, field_name, False)
            if valor_campo == 'requiere_cambio':
                # Verificar si existe intervención CON detalles de subpartes
                intervencion_existente = self.intervencion_ids.filtered(
                    lambda x: x.componente == componente_code and x.detalle_ids
                )
                if not intervencion_existente:
                    componentes_pendientes.append((field_name, componente_code))
        
        return componentes_pendientes

    def _abrir_wizard_subpartes(self, campo_componente_tuple):
        """Abre wizard de subpartes para un componente específico"""
        self.ensure_one()
        field_name, componente_code = campo_componente_tuple
        
        # Crear la intervención para este componente
        intervencion = self._ensure_intervencion_for_component(componente_code)
        
        # Obtener el nombre legible del componente
        componente_dict = dict(self.env['reparacion.subparte'].COMPONENTE)
        nombre_componente = componente_dict.get(componente_code, componente_code)
        
        # Buscar subpartes disponibles para este componente
        subpartes_disponibles = self.env['reparacion.subparte'].search([
            ('componente', '=', componente_code),
            ('active', '=', True)
        ])
        
        # Crear líneas iniciales con todas las subpartes del componente
        lineas_iniciales = []
        for subparte in subpartes_disponibles:
            lineas_iniciales.append((0, 0, {
                'subparte_id': subparte.id,
                'accion_sub': 'cambiado',
                'cantidad': 1.0,
            }))
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Especificar subpartes - {nombre_componente}',
            'res_model': 'reparacion.add.subparts.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('sat.view_reparacion_add_subparts_wizard_form').id,
            'target': 'new',
            'context': {
                'active_intervencion_id': intervencion.id,
                'default_intervencion_id': intervencion.id,
                'default_reparacion_id': self.id,
                'default_line_ids': lineas_iniciales,
                'from_generar_informe': True,
            },
        }
    def _get_component_display_name(self, componente_code):
        """Obtiene el nombre display de un componente basado en su código"""
        # Mapeo de códigos internos a nombres de display
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
            'papel': 'Transporte de papel / bandejas / bypass',
            'otro': 'Otro',
        }
        return component_names.get(componente_code, componente_code)
    def _ensure_intervencion_for_component(self, componente_code):
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

    @api.model
    def rpc_prepare_subparts_wizard(self, rec_id, field_name):
        """Llamado desde el widget JS al seleccionar 'requiere_cambio' (antes de guardar)."""
        rec = self.browse(rec_id)
        if not rec.exists():
            raise UserError(_("Registro no encontrado."))
        comp = rec._COMP_MAP_REQCAMBIO.get(field_name)
        if not comp:
            raise UserError(_("No se reconoce el componente para el campo: %s") % field_name)
        interv = rec._ensure_intervencion_for_component(comp)
        return {'intervencion_id': interv.id}


    
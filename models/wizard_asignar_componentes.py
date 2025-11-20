# models/wizard_asignar_componentes.py
from odoo import models, fields, api
from markupsafe import Markup


class WizardAsignarComponentes(models.TransientModel):
    _name = 'wizard.asignar.componentes'
    _description = 'Asistente para asignar componentes y accesorios masivamente'

    # Modelos a los que se aplicará la asignación
    modelo_ids = fields.Many2many(
        'modelo.maquina',
        string='Modelos seleccionados',
        readonly=True
    )

    # Líneas de componentes (cada línea = un tipo de componente)
    componente_line_ids = fields.One2many(
        'wizard.asignar.componentes.linea',
        'wizard_id',
        string='Componentes a agregar'
    )

    # 🔥 Accesorios: selección múltiple directa
    accesorio_ids = fields.Many2many(
        'accesorio.tipo',
        'wiz_comp_acc_rel',     # nombre corto para la tabla M2M
        'wizard_id',
        'tipo_id',
        string='Tipos de Accesorio'
    )

    accesorio_obligatorio = fields.Boolean(
        string='Obligatorio por defecto',
        default=False,
    )

    accesorio_nota = fields.Char(
        string='Nota por defecto'
    )

    # Opciones globales
    sobrescribir_existentes = fields.Boolean(
        string='Sobrescribir si ya existen',
        default=False,
        help='Si está marcado, actualizará componentes/accesorios existentes'
    )

    # Resumen HTML
    resumen = fields.Html(
        string='Resumen',
        compute='_compute_resumen',
        sanitize=False
    )

    @api.depends(
        'modelo_ids',
        'componente_line_ids',
        'componente_line_ids.subparte_ids',
        'componente_line_ids.subparte_cantidad',
        'componente_line_ids.subparte_nota',
        'accesorio_ids',
        'accesorio_obligatorio',
        'accesorio_nota',
    )
    def _compute_resumen(self):
        for wizard in self:
            html = '<div style="padding: 10px;">'
            html += '<h4>&#128203; Se procesarán %s modelo(s)</h4>' % len(wizard.modelo_ids)

            # Clasificar modelos por tipo
            modelos_mono = wizard.modelo_ids.filtered(lambda m: m.tipo_id == 'monocromatica')
            modelos_color = wizard.modelo_ids.filtered(lambda m: m.tipo_id == 'color')

            if modelos_mono:
                html += '<p style="margin: 5px 0;">&#8226; <strong>Monocromáticos:</strong> %s</p>' % len(modelos_mono)
                html += '<ul style="margin: 2px 0 5px 20px;">'
                for modelo in modelos_mono:
                    html += '<li style="font-size: 0.9em;">%s</li>' % modelo.name
                html += '</ul>'

            if modelos_color:
                html += '<p style="margin: 5px 0;">&#8226; <strong>A Color:</strong> %s</p>' % len(modelos_color)
                html += '<ul style="margin: 2px 0 5px 20px;">'
                for modelo in modelos_color:
                    html += '<li style="font-size: 0.9em;">%s</li>' % modelo.name
                html += '</ul>'

            html += '<ul>'

            # ===== RESUMEN COMPONENTES =====
            if wizard.componente_line_ids:
                html += '<li><strong>Componentes:</strong> %s tipo(s)</li>' % len(wizard.componente_line_ids)
                for line in wizard.componente_line_ids:
                    is_color_sensitive = getattr(line.tipo_id, 'is_color_sensitive', False)

                    if is_color_sensitive:
                        html += '<li style="margin-left: 20px;">&#8226; %s' % line.tipo_id.name
                        if modelos_mono and modelos_color:
                            html += ' (<strong>K</strong> para %s monocromo(s), ' % len(modelos_mono)
                            html += '<strong>K,C,M,Y</strong> para %s color(es))' % len(modelos_color)
                        elif modelos_mono:
                            html += ' (<strong>solo K</strong> - todas monocromáticas)'
                        else:
                            html += ' (<strong>K,C,M,Y</strong> - todas a color)'
                        html += '</li>'
                    else:
                        html += '<li style="margin-left: 20px;">&#8226; %s</li>' % line.tipo_id.name

                    # Subpartes (Many2many)
                    if line.subparte_ids:
                        html += '<ul style="margin-left: 40px; font-size: 0.9em; color: #666;">'
                        for subparte in line.subparte_ids:
                            html += '<li>%s (x%s)</li>' % (
                                subparte.name,
                                line.subparte_cantidad or 1.0,
                            )
                        html += '</ul>'

            # ===== RESUMEN ACCESORIOS =====
            if wizard.accesorio_ids:
                html += '<li><strong>Accesorios:</strong> %s tipo(s)</li>' % len(wizard.accesorio_ids)
                for tipo in wizard.accesorio_ids:
                    obligatorio_txt = ''
                    if wizard.accesorio_obligatorio:
                        obligatorio_txt = ' <span style="color: red;">*Obligatorio</span>'
                    html += '<li style="margin-left: 20px;">&#8226; %s%s</li>' % (tipo.name, obligatorio_txt)

            html += '</ul>'

            # ===== TOTALES ESTIMADOS =====
            total_componentes = 0
            for line in wizard.componente_line_ids:
                is_color_sensitive = getattr(line.tipo_id, 'is_color_sensitive', False)
                if is_color_sensitive:
                    total_componentes += len(modelos_mono) * 1      # K
                    total_componentes += len(modelos_color) * 4     # K,C,M,Y
                else:
                    total_componentes += len(wizard.modelo_ids)

            total_accesorios = len(wizard.modelo_ids) * len(wizard.accesorio_ids)
            total_registros = total_componentes + total_accesorios

            html += '<hr style="margin: 15px 0;"/>'
            html += '<p><strong>&#128202; Total estimado de registros principales:</strong> %s</p>' % total_registros
            html += '<p style="font-size: 0.9em; color: #666;">&#8226; Componentes: %s | Accesorios: %s</p>' % (
                total_componentes, total_accesorios
            )
            html += '</div>'

            wizard.resumen = Markup(html)

    # ===== DEFAULT_GET PARA TRAER MODELOS SELECCIONADOS =====
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        modelo_ids = self.env.context.get('active_ids', [])
        if modelo_ids:
            res['modelo_ids'] = [(6, 0, modelo_ids)]
        return res

    # ===== ACCIÓN PRINCIPAL =====
    def action_asignar(self):
        self.ensure_one()

        componentes_creados = 0
        componentes_actualizados = 0
        subpartes_creadas = 0
        accesorios_creados = 0
        accesorios_actualizados = 0
        errores = []

        ComponenteModel = self.env['modelo.maquina.componente']
        SubparteModel = self.env['modelo.maquina.componente.subparte']
        AccesorioModel = self.env['modelo.maquina.accesorio']

        for modelo in self.modelo_ids:
            es_monocromo = modelo.tipo_id == 'monocromatica'

            # ===== COMPONENTES =====
            for comp_line in self.componente_line_ids:
                is_color_sensitive = getattr(comp_line.tipo_id, 'is_color_sensitive', False)

                if is_color_sensitive:
                    colores = ['k'] if es_monocromo else ['k', 'c', 'm', 'y']
                    for color in colores:
                        try:
                            result, componente = self._crear_o_actualizar_componente(
                                ComponenteModel, modelo, comp_line, color
                            )
                            if result == 'creado':
                                componentes_creados += 1
                            elif result == 'actualizado':
                                componentes_actualizados += 1

                            # Subpartes por cada componente generado
                            for subparte in comp_line.subparte_ids:
                                try:
                                    created = self._crear_subparte(
                                        SubparteModel,
                                        componente,
                                        subparte,
                                        comp_line,
                                    )
                                    if created:
                                        subpartes_creadas += 1
                                except Exception as e:
                                    errores.append(
                                        "Error subparte en %s - %s (%s) - %s: %s" % (
                                            modelo.name,
                                            comp_line.tipo_id.name,
                                            color.upper(),
                                            subparte.name,
                                            str(e)
                                        )
                                    )
                        except Exception as e:
                            errores.append(
                                "Error en %s - %s (%s): %s" % (
                                    modelo.name,
                                    comp_line.tipo_id.name,
                                    color.upper(),
                                    str(e)
                                )
                            )
                else:
                    try:
                        result, componente = self._crear_o_actualizar_componente(
                            ComponenteModel, modelo, comp_line, False
                        )
                        if result == 'creado':
                            componentes_creados += 1
                        elif result == 'actualizado':
                            componentes_actualizados += 1

                        for subparte in comp_line.subparte_ids:
                            try:
                                created = self._crear_subparte(
                                    SubparteModel,
                                    componente,
                                    subparte,
                                    comp_line,
                                )
                                if created:
                                    subpartes_creadas += 1
                            except Exception as e:
                                errores.append(
                                    "Error subparte en %s - %s - %s: %s" % (
                                        modelo.name,
                                        comp_line.tipo_id.name,
                                        subparte.name,
                                        str(e)
                                    )
                                )
                    except Exception as e:
                        errores.append("Error en %s - %s: %s" % (modelo.name, comp_line.tipo_id.name, str(e)))

            # ===== ACCESORIOS =====
            for tipo_acc in self.accesorio_ids:
                try:
                    result = self._crear_o_actualizar_accesorio(
                        AccesorioModel,
                        modelo,
                        tipo_acc
                    )
                    if result == 'creado':
                        accesorios_creados += 1
                    elif result == 'actualizado':
                        accesorios_actualizados += 1
                except Exception as e:
                    errores.append("Error en %s - %s: %s" % (modelo.name, tipo_acc.name, str(e)))

        # Mensaje final
        mensaje_partes = [
            "Componentes creados: %s" % componentes_creados,
            "Componentes actualizados: %s" % componentes_actualizados,
            "Subpartes agregadas: %s" % subpartes_creadas,
            "Accesorios creados: %s" % accesorios_creados,
            "Accesorios actualizados: %s" % accesorios_actualizados,
        ]

        if errores:
            mensaje_partes.append("ERRORES: %s" % len(errores))
            if len(errores) <= 3:
                for error in errores:
                    mensaje_partes.append("  - %s" % error)

        mensaje_simple = " | ".join(mensaje_partes)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Asignación Completada' if not errores else 'Completado con Errores',
                'message': mensaje_simple,
                'type': 'success' if not errores else 'warning',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    # ===== HELPERS =====
    def _crear_o_actualizar_componente(self, ComponenteModel, modelo, comp_line, color):
        domain = [
            ('modelo_id', '=', modelo.id),
            ('tipo_id', '=', comp_line.tipo_id.id),
            ('color', '=', color)
        ]

        existente = ComponenteModel.search(domain, limit=1)

        vals = {
            'modelo_id': modelo.id,
            'tipo_id': comp_line.tipo_id.id,
            'color': color,
            'prioridad': comp_line.prioridad,
            'vida_util_paginas': comp_line.vida_util_paginas,
            'vida_util_meses': comp_line.vida_util_meses,
            'frase_desgaste': comp_line.frase_desgaste,
            'frase_cambio': comp_line.frase_cambio,
        }

        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
                return 'actualizado', existente
            return 'existente', existente
        else:
            nuevo = ComponenteModel.create(vals)
            return 'creado', nuevo

    def _crear_subparte(self, SubparteModel, componente, subparte, comp_line):
        """Crea o actualiza una subparte real desde el M2M del wizard."""
        domain = [
            ('componente_id', '=', componente.id),
            ('subparte_id', '=', subparte.id)
        ]

        existente = SubparteModel.search(domain, limit=1)

        vals = {
            'componente_id': componente.id,
            'subparte_id': subparte.id,
            'cantidad': comp_line.subparte_cantidad or 1.0,
            'nota': comp_line.subparte_nota,
        }

        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
            return False
        else:
            SubparteModel.create(vals)
            return True

    def _crear_o_actualizar_accesorio(self, AccesorioModel, modelo, tipo_acc):
        """Crea o actualiza accesorio real por modelo."""
        domain = [
            ('modelo_id', '=', modelo.id),
            ('tipo_id', '=', tipo_acc.id)
        ]

        existente = AccesorioModel.search(domain, limit=1)

        vals = {
            'modelo_id': modelo.id,
            'tipo_id': tipo_acc.id,
            'obligatorio': self.accesorio_obligatorio,
            'nota': self.accesorio_nota,
        }

        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
                return 'actualizado'
            return 'existente'
        else:
            AccesorioModel.create(vals)
            return 'creado'


# ===== LÍNEA DE COMPONENTE =====
class WizardAsignarComponentesLinea(models.TransientModel):
    _name = 'wizard.asignar.componentes.linea'
    _description = 'Línea de componente para asignación masiva'

    wizard_id = fields.Many2one(
        'wizard.asignar.componentes',
        string='Wizard',
        ondelete='cascade'
    )

    tipo_id = fields.Many2one(
        'componente.tipo',
        string='Tipo de Componente',
        required=True
    )

    prioridad = fields.Selection(
        [('1', 'Crítico'), ('2', 'Medio'), ('3', 'Bajo')],
        string='Prioridad',
        default='2',
        required=True
    )

    vida_util_paginas = fields.Integer(
        string='Vida útil (páginas)',
        default=0
    )

    vida_util_meses = fields.Integer(
        string='Vida útil (meses)',
        default=0
    )

    frase_desgaste = fields.Char(string='Frase de desgaste')
    frase_cambio = fields.Char(string='Frase de cambio')

    # 🔥 Subpartes: Many2many directo (abre popup con selección múltiple)
    subparte_ids = fields.Many2many(
        'componente.subparte',
        'wiz_comp_line_subp_rel',
        'line_id',
        'subparte_id',
        string='Subpartes',
        domain="[('tipo_id', '=', tipo_id), ('active', '=', True)]",
    )

    subparte_cantidad = fields.Float(
        string='Cantidad por subparte',
        default=1.0,
    )

    subparte_nota = fields.Char(
        string='Nota por subparte'
    )

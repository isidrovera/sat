# models/wizard_asignar_componentes.py
from odoo import models, fields, api
from markupsafe import Markup


class WizardAsignarComponentes(models.TransientModel):
    _name = 'wizard.asignar.componentes'
    _description = 'Asistente para asignar componentes y accesorios masivamente'

    modelo_ids = fields.Many2many(
        'modelo.maquina',
        string='Modelos seleccionados',
        readonly=True
    )

    # Líneas de componentes con sus subpartes
    componente_line_ids = fields.One2many(
        'wizard.asignar.componentes.linea',
        'wizard_id',
        string='Componentes a agregar'
    )

    # Líneas de accesorios
    accesorio_line_ids = fields.One2many(
        'wizard.asignar.componentes.accesorio',
        'wizard_id',
        string='Accesorios a agregar'
    )

    # Opciones globales
    sobrescribir_existentes = fields.Boolean(
        string='Sobrescribir si ya existen',
        default=False,
        help='Si está marcado, actualizará componentes/accesorios existentes'
    )

    # Resumen
    resumen = fields.Html(
        string='Resumen',
        compute='_compute_resumen',
        sanitize=False
    )

    @api.depends(
        'modelo_ids',
        'componente_line_ids',
        'componente_line_ids.subparte_ids',
        'componente_line_ids.subparte_ids.cantidad',
        'componente_line_ids.subparte_ids.nota',
        'accesorio_line_ids',
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

            # Resumen de componentes
            if wizard.componente_line_ids:
                html += '<li><strong>Componentes:</strong> %s tipo(s)</li>' % len(wizard.componente_line_ids)
                for line in wizard.componente_line_ids:
                    is_color_sensitive = getattr(line.tipo_id, 'is_color_sensitive', False)

                    if is_color_sensitive:
                        html += '<li style="margin-left: 20px;">&#8226; %s' % line.tipo_id.name

                        # Detallar por tipo de máquina
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

                    # Mostrar subpartes
                    subpartes_count = len(line.subparte_ids)
                    if subpartes_count:
                        html += '<ul style="margin-left: 40px; font-size: 0.9em; color: #666;">'
                        for subparte in line.subparte_ids:
                            html += '<li>%s (x%s)</li>' % (subparte.subparte_id.name, subparte.cantidad)
                        html += '</ul>'

            # Resumen de accesorios
            if wizard.accesorio_line_ids:
                html += '<li><strong>Accesorios:</strong> %s tipo(s)</li>' % len(wizard.accesorio_line_ids)
                for line in wizard.accesorio_line_ids:
                    obligatorio_txt = ' <span style="color: red;">*Obligatorio</span>' if line.obligatorio else ''
                    html += '<li style="margin-left: 20px;">&#8226; %s%s</li>' % (line.tipo_id.name, obligatorio_txt)

            html += '</ul>'

            # Calcular total estimado
            total_componentes = 0
            for line in wizard.componente_line_ids:
                is_color_sensitive = getattr(line.tipo_id, 'is_color_sensitive', False)
                if is_color_sensitive:
                    # K para monocromos + K,C,M,Y para color
                    total_componentes += len(modelos_mono) * 1  # solo K
                    total_componentes += len(modelos_color) * 4  # K,C,M,Y
                else:
                    # 1 por cada modelo
                    total_componentes += len(wizard.modelo_ids)

            total_accesorios = len(wizard.modelo_ids) * len(wizard.accesorio_line_ids)
            total_registros = total_componentes + total_accesorios

            html += '<hr style="margin: 15px 0;"/>'
            html += '<p><strong>&#128202; Total estimado de registros principales:</strong> %s</p>' % total_registros
            html += '<p style="font-size: 0.9em; color: #666;">&#8226; Componentes: %s | Accesorios: %s</p>' % (
                total_componentes, total_accesorios
            )
            html += '</div>'

            wizard.resumen = Markup(html)

    @api.model
    def default_get(self, fields_list):
        """Obtiene los modelos seleccionados del contexto"""
        res = super().default_get(fields_list)

        # Obtener IDs de modelos seleccionados
        modelo_ids = self.env.context.get('active_ids', [])
        if modelo_ids:
            res['modelo_ids'] = [(6, 0, modelo_ids)]

        return res

    def action_asignar(self):
        """Ejecuta la asignación masiva"""
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
            # Determinar colores según el tipo de máquina
            es_monocromo = modelo.tipo_id == 'monocromatica'

            # ===== PROCESAR COMPONENTES =====
            for comp_line in self.componente_line_ids:
                is_color_sensitive = getattr(comp_line.tipo_id, 'is_color_sensitive', False)

                if is_color_sensitive:
                    # Solo negro para monocroma, todos los colores para color
                    if es_monocromo:
                        colores = ['k']  # Solo negro
                    else:
                        colores = ['k', 'c', 'm', 'y']  # Todos los colores

                    for color in colores:
                        try:
                            result, componente = self._crear_o_actualizar_componente(
                                ComponenteModel,
                                modelo,
                                comp_line,
                                color
                            )

                            if result == 'creado':
                                componentes_creados += 1
                            elif result == 'actualizado':
                                componentes_actualizados += 1

                            # Agregar subpartes si existen
                            for subparte_line in comp_line.subparte_ids:
                                try:
                                    created = self._crear_subparte(
                                        SubparteModel,
                                        componente,
                                        subparte_line
                                    )
                                    if created:
                                        subpartes_creadas += 1
                                except Exception as e:
                                    errores.append(
                                        "Error subparte en %s - %s (%s) - %s: %s" % (
                                            modelo.name,
                                            comp_line.tipo_id.name,
                                            color.upper(),
                                            subparte_line.subparte_id.name,
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
                    # Crear componente sin color
                    try:
                        result, componente = self._crear_o_actualizar_componente(
                            ComponenteModel,
                            modelo,
                            comp_line,
                            False
                        )

                        if result == 'creado':
                            componentes_creados += 1
                        elif result == 'actualizado':
                            componentes_actualizados += 1

                        # Agregar subpartes si existen
                        for subparte_line in comp_line.subparte_ids:
                            try:
                                created = self._crear_subparte(
                                    SubparteModel,
                                    componente,
                                    subparte_line
                                )
                                if created:
                                    subpartes_creadas += 1
                            except Exception as e:
                                errores.append(
                                    "Error subparte en %s - %s - %s: %s" % (
                                        modelo.name,
                                        comp_line.tipo_id.name,
                                        subparte_line.subparte_id.name,
                                        str(e)
                                    )
                                )
                    except Exception as e:
                        errores.append("Error en %s - %s: %s" % (modelo.name, comp_line.tipo_id.name, str(e)))

            # ===== PROCESAR ACCESORIOS =====
            for acc_line in self.accesorio_line_ids:
                try:
                    result = self._crear_o_actualizar_accesorio(
                        AccesorioModel,
                        modelo,
                        acc_line
                    )
                    if result == 'creado':
                        accesorios_creados += 1
                    elif result == 'actualizado':
                        accesorios_actualizados += 1
                except Exception as e:
                    errores.append("Error en %s - %s: %s" % (modelo.name, acc_line.tipo_id.name, str(e)))

        # Preparar mensaje de resultado
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

        # Acción que cierra el wizard y muestra notificación
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

    def _crear_o_actualizar_componente(self, ComponenteModel, modelo, comp_line, color):
        """Crea o actualiza un componente. Retorna (resultado, componente)"""
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

    def _crear_subparte(self, SubparteModel, componente, subparte_line):
        """Crea o actualiza una subparte. Retorna True si creó, False si ya existía"""
        domain = [
            ('componente_id', '=', componente.id),
            ('subparte_id', '=', subparte_line.subparte_id.id)
        ]

        existente = SubparteModel.search(domain, limit=1)

        vals = {
            'componente_id': componente.id,
            'subparte_id': subparte_line.subparte_id.id,
            'cantidad': subparte_line.cantidad,
            'nota': subparte_line.nota,
        }

        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
            return False  # Ya existía
        else:
            SubparteModel.create(vals)
            return True  # Creada

    def _crear_o_actualizar_accesorio(self, AccesorioModel, modelo, acc_line):
        """Crea o actualiza un accesorio"""
        domain = [
            ('modelo_id', '=', modelo.id),
            ('tipo_id', '=', acc_line.tipo_id.id)
        ]

        existente = AccesorioModel.search(domain, limit=1)

        vals = {
            'modelo_id': modelo.id,
            'tipo_id': acc_line.tipo_id.id,
            'obligatorio': acc_line.obligatorio,
            'nota': acc_line.nota,
        }

        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
                return 'actualizado'
            return 'existente'
        else:
            AccesorioModel.create(vals)
            return 'creado'

    # ==== WIZARD MULTI PARA ACCESORIOS ====
    def action_open_accesorio_multi_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.asignar.componentes.accesorio.multi',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_wizard_id': self.id,
            }
        }


# ===== LÍNEA DE COMPONENTE CON SUS SUBPARTES =====
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

    # Subpartes de este componente
    subparte_ids = fields.One2many(
        'wizard.asignar.componentes.subparte',
        'componente_line_id',
        string='Subpartes'
    )

    # ==== WIZARD MULTI PARA SUBPARTES ====
    def action_open_subparte_multi_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.asignar.componentes.subparte.multi',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_componente_line_id': self.id,
            }
        }


# ===== SUBPARTE DENTRO DE UN COMPONENTE =====
class WizardAsignarComponentesSubparte(models.TransientModel):
    _name = 'wizard.asignar.componentes.subparte'
    _description = 'Subparte de componente para asignación masiva'

    componente_line_id = fields.Many2one(
        'wizard.asignar.componentes.linea',
        string='Componente',
        required=True,
        ondelete='cascade'
    )

    # Campo relacionado para obtener el tipo desde la línea padre
    tipo_componente_id = fields.Many2one(
        'componente.tipo',
        related='componente_line_id.tipo_id',
        string='Tipo Componente',
        store=False,
        readonly=True
    )

    # Filtro dinámico - solo muestra subpartes del tipo seleccionado
    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte',
        required=True,
        domain="[('tipo_id', '=', tipo_componente_id), ('active', '=', True)]"
    )

    cantidad = fields.Float(
        string='Cantidad',
        default=1.0
    )

    nota = fields.Char(string='Nota')


# ===== LÍNEA DE ACCESORIO =====
class WizardAsignarComponentesAccesorio(models.TransientModel):
    _name = 'wizard.asignar.componentes.accesorio'
    _description = 'Línea de accesorio para asignación masiva'

    wizard_id = fields.Many2one(
        'wizard.asignar.componentes',
        string='Wizard',
        ondelete='cascade'
    )


    tipo_id = fields.Many2one(
        'accesorio.tipo',
        string='Tipo de Accesorio',
        required=True
    )

    obligatorio = fields.Boolean(
        string='Obligatorio',
        default=False
    )

    nota = fields.Char(string='Nota')


# ===== WIZARD MULTI-SUBPARTES =====
class WizardAsignarComponentesSubparteMulti(models.TransientModel):
    _name = 'wizard.asignar.componentes.subparte.multi'
    _description = 'Seleccionar múltiples subpartes para un componente'

    componente_line_id = fields.Many2one(
        'wizard.asignar.componentes.linea',
        string='Línea de componente',
        required=True,
        ondelete='cascade'
    )

    tipo_componente_id = fields.Many2one(
        'componente.tipo',
        related='componente_line_id.tipo_id',
        string='Tipo Componente',
        store=False,
        readonly=True
    )

    subparte_ids = fields.Many2many(
        'componente.subparte',
        'wiz_comp_subp_multi_rel',
        'wizard_id',
        'subparte_id',
        string='Subpartes',
        domain="[('tipo_id', '=', tipo_componente_id), ('active', '=', True)]"
    )

    cantidad = fields.Float(
        string='Cantidad por subparte',
        default=1.0
    )

    nota = fields.Char(
        string='Nota por subparte'
    )

    def action_confirm(self):
        SubparteModel = self.env['wizard.asignar.componentes.subparte']
        for wiz in self:
            for subparte in wiz.subparte_ids:
                existente = SubparteModel.search([
                    ('componente_line_id', '=', wiz.componente_line_id.id),
                    ('subparte_id', '=', subparte.id),
                ], limit=1)
                if not existente:
                    SubparteModel.create({
                        'componente_line_id': wiz.componente_line_id.id,
                        'subparte_id': subparte.id,
                        'cantidad': wiz.cantidad,
                        'nota': wiz.nota,
                    })

        # 🔥 Reabrir wizard principal
        main_wizard = self.componente_line_id.wizard_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.asignar.componentes',
            'view_mode': 'form',
            'target': 'new',
            'res_id': main_wizard.id,
        }


# ===== WIZARD MULTI-ACCESORIOS =====
class WizardAsignarComponentesAccesorioMulti(models.TransientModel):
    _name = 'wizard.asignar.componentes.accesorio.multi'
    _description = 'Seleccionar múltiples accesorios para el wizard principal'

    wizard_id = fields.Many2one(
        'wizard.asignar.componentes',
        string='Wizard principal',
        required=True,
        ondelete='cascade'
    )

    accesorio_ids = fields.Many2many(
        'accesorio.tipo',
        'wiz_comp_acc_multi_rel',
        'wizard_id',
        'tipo_id',
        string='Tipos de Accesorio'
    )

    obligatorio = fields.Boolean(
        string='Obligatorio por defecto',
        default=False
    )

    nota = fields.Char(
        string='Nota por defecto'
    )

    def action_confirm(self):
        LineModel = self.env['wizard.asignar.componentes.accesorio']
        for wiz in self:
            for acc in wiz.accesorio_ids:
                existente = LineModel.search([
                    ('wizard_id', '=', wiz.wizard_id.id),
                    ('tipo_id', '=', acc.id),
                ], limit=1)
                if not existente:
                    LineModel.create({
                        'wizard_id': wiz.wizard_id.id,
                        'tipo_id': acc.id,
                        'obligatorio': wiz.obligatorio,
                        'nota': wiz.nota,
                    })

        # 🔥 En lugar de cerrar sin más, reabrimos el wizard principal
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.asignar.componentes',
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.wizard_id.id,
        }

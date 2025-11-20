# models/wizard_asignar_componentes.py
from odoo import models, fields, api
from odoo.exceptions import UserError
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)


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

    # -------------------------------------------------------------------------
    # RESUMEN
    # -------------------------------------------------------------------------
    @api.depends(
        'modelo_ids',
        'componente_line_ids',
        'componente_line_ids.subparte_ids',
        'componente_line_ids.subparte_ids.seleccionado',
        'accesorio_line_ids',
        'accesorio_line_ids.seleccionado'
    )
    def _compute_resumen(self):
        for wizard in self:
            html = '<div style="padding: 10px;">'
            html += '<h4>&#128203; Se procesarán %s modelo(s)</h4>' % len(wizard.modelo_ids)

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

            # Componentes
            if wizard.componente_line_ids:
                html += '<li><strong>Componentes:</strong> %s tipo(s)</li>' % len(wizard.componente_line_ids)
                for line in wizard.componente_line_ids:
                    is_color_sensitive = line.tipo_id.is_color_sensitive if line.tipo_id else False

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

                    subpartes_seleccionadas = line.subparte_ids.filtered(lambda s: s.seleccionado)
                    if subpartes_seleccionadas:
                        html += '<ul style="margin-left: 40px; font-size: 0.9em; color: #666;">'
                        for subparte in subpartes_seleccionadas:
                            html += '<li>&#10004; %s (x%s)</li>' % (
                                subparte.subparte_id.display_name if subparte.subparte_id else '?',
                                subparte.cantidad,
                            )
                        html += '</ul>'

            # Accesorios
            if wizard.accesorio_line_ids:
                accesorios_seleccionados = wizard.accesorio_line_ids.filtered(lambda a: a.seleccionado)
                total_acc = len(accesorios_seleccionados)
                html += '<li><strong>Accesorios:</strong> %s seleccionado(s) de %s disponible(s)</li>' % (
                    total_acc,
                    len(wizard.accesorio_line_ids),
                )
                if accesorios_seleccionados:
                    for line in accesorios_seleccionados:
                        obligatorio_txt = ' <span style="color: red;">*Obligatorio</span>' if line.obligatorio else ''
                        html += '<li style="margin-left: 20px;">&#10004; %s%s</li>' % (
                            line.tipo_id.name,
                            obligatorio_txt,
                        )

            html += '</ul>'

            # Totales estimados
            total_componentes = 0
            for line in wizard.componente_line_ids:
                is_color_sensitive = line.tipo_id.is_color_sensitive if line.tipo_id else False
                if is_color_sensitive:
                    total_componentes += len(modelos_mono) * 1
                    total_componentes += len(modelos_color) * 4
                else:
                    total_componentes += len(wizard.modelo_ids)

            total_subpartes = 0
            for line in wizard.componente_line_ids:
                subpartes_sel = len(line.subparte_ids.filtered(lambda s: s.seleccionado))
                is_color_sensitive = line.tipo_id.is_color_sensitive if line.tipo_id else False
                if is_color_sensitive:
                    total_subpartes += subpartes_sel * (len(modelos_mono) + len(modelos_color) * 4)
                else:
                    total_subpartes += subpartes_sel * len(wizard.modelo_ids)

            total_accesorios = len(wizard.modelo_ids) * len(
                wizard.accesorio_line_ids.filtered(lambda a: a.seleccionado)
            )

            html += '<hr style="margin: 15px 0;"/>'
            html += '<p><strong>&#128202; Total estimado:</strong></p>'
            html += '<ul style="margin: 5px 0; font-size: 0.9em; color: #666;">'
            html += '<li>Componentes principales: %s</li>' % total_componentes
            html += '<li>Subpartes: %s</li>' % total_subpartes
            html += '<li>Accesorios: %s</li>' % total_accesorios
            html += '</ul>'
            html += '</div>'

            wizard.resumen = Markup(html)

    # -------------------------------------------------------------------------
    # DEFAULT_GET: autocargar accesorios disponibles
    # -------------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        modelo_ids = self.env.context.get('active_ids', [])
        if modelo_ids:
            res['modelo_ids'] = [(6, 0, modelo_ids)]

            accesorios_disponibles = self.env['accesorio.tipo'].search([
                ('active', '=', True)
            ])

            if accesorios_disponibles:
                accesorio_lines = []
                for accesorio in accesorios_disponibles:
                    accesorio_lines.append((0, 0, {
                        'tipo_id': accesorio.id,
                        'seleccionado': False,
                        'obligatorio': False,
                        'nota': '',
                    }))
                res['accesorio_line_ids'] = accesorio_lines

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Procesar las líneas de componentes y sus subpartes al crear"""
        records = super().create(vals_list)

        for record in records:
            _logger.info("🆕 Wizard creado ID:%s con %s líneas de componentes",
                         record.id, len(record.componente_line_ids))
            for comp_line in record.componente_line_ids:
                _logger.info("  📦 Componente: %s con %s subpartes",
                             comp_line.tipo_id.name if comp_line.tipo_id else '?',
                             len(comp_line.subparte_ids))

        return records

    def write(self, vals):
        """Actualizar el wizard"""
        result = super().write(vals)

        # Log para debugging
        if 'componente_line_ids' in vals:
            for record in self:
                _logger.info("💾 Wizard actualizado ID:%s con %s líneas",
                             record.id, len(record.componente_line_ids))
                for comp_line in record.componente_line_ids:
                    _logger.info("  📦 %s: %s subpartes",
                                 comp_line.tipo_id.name if comp_line.tipo_id else '?',
                                 len(comp_line.subparte_ids))

        return result

    # -------------------------------------------------------------------------
    # ACCIÓN PRINCIPAL
    # -------------------------------------------------------------------------
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
            _logger.info("=" * 80)
            _logger.info("PROCESANDO MODELO: %s (%s)", modelo.name, 'MONO' if es_monocromo else 'COLOR')
            _logger.info("=" * 80)

            # ===== COMPONENTES =====
            for comp_line in self.componente_line_ids:
                is_color_sensitive = comp_line.tipo_id.is_color_sensitive if comp_line.tipo_id else False
                _logger.info("  📦 Tipo componente: %s (sensible_color=%s)",
                             comp_line.tipo_id.name, is_color_sensitive)

                # 🎯 CLAVE: Obtener subpartes seleccionadas del wizard
                subpartes_sel = comp_line.subparte_ids.filtered(
                    lambda s: s.seleccionado and s.subparte_id
                )

                _logger.info("    📋 Total líneas subparte en wizard: %s", len(comp_line.subparte_ids))
                _logger.info("    ✅ Subpartes SELECCIONADAS: %s", len(subpartes_sel))

                for sp in subpartes_sel:
                    _logger.info("      → %s (ID:%s) - Cant: %s",
                                 sp.subparte_id.display_name, sp.subparte_id.id, sp.cantidad)

                if is_color_sensitive:
                    # Componente sensible a color
                    colores = ['k'] if es_monocromo else ['k', 'c', 'm', 'y']
                    _logger.info("    🎨 Colores a crear: %s", colores)

                    for color in colores:
                        try:
                            result, componente = self._crear_o_actualizar_componente(
                                ComponenteModel, modelo, comp_line, color
                            )
                            _logger.info("    ✓ Componente %s color=%s → %s (ID:%s)",
                                         comp_line.tipo_id.name, color.upper(), result, componente.id)

                            if result == 'creado':
                                componentes_creados += 1
                            elif result == 'actualizado':
                                componentes_actualizados += 1

                            # 🎯 Crear subpartes para este componente
                            subpartes_count = 0
                            for subparte_line in subpartes_sel:
                                try:
                                    created = self._crear_subparte(
                                        SubparteModel, componente, subparte_line
                                    )
                                    if created:
                                        subpartes_creadas += 1
                                        subpartes_count += 1
                                        _logger.info("      ✓ Subparte creada: %s → Componente ID:%s",
                                                     subparte_line.subparte_id.display_name, componente.id)
                                except Exception as e:
                                    msg = "Error subparte en %s - %s (%s) - %s: %s" % (
                                        modelo.name, comp_line.tipo_id.name, color.upper(),
                                        subparte_line.subparte_id.name, str(e)
                                    )
                                    _logger.error("      ✗ %s", msg)
                                    errores.append(msg)

                            _logger.info("    📊 Total subpartes creadas para color %s: %s",
                                         color.upper(), subpartes_count)

                        except Exception as e:
                            msg = "Error en %s - %s (%s): %s" % (
                                modelo.name, comp_line.tipo_id.name, color.upper(), str(e)
                            )
                            _logger.error("    ✗ %s", msg)
                            errores.append(msg)
                else:
                    # Componente SIN sensibilidad a color
                    _logger.info("    🔧 Componente sin color")
                    try:
                        result, componente = self._crear_o_actualizar_componente(
                            ComponenteModel, modelo, comp_line, False
                        )
                        _logger.info("    ✓ Componente %s → %s (ID:%s)",
                                     comp_line.tipo_id.name, result, componente.id)

                        if result == 'creado':
                            componentes_creados += 1
                        elif result == 'actualizado':
                            componentes_actualizados += 1

                        # 🎯 Crear subpartes
                        subpartes_count = 0
                        for subparte_line in subpartes_sel:
                            try:
                                created = self._crear_subparte(
                                    SubparteModel, componente, subparte_line
                                )
                                if created:
                                    subpartes_creadas += 1
                                    subpartes_count += 1
                                    _logger.info("      ✓ Subparte creada: %s → Componente ID:%s",
                                                 subparte_line.subparte_id.display_name, componente.id)
                            except Exception as e:
                                msg = "Error subparte en %s - %s - %s: %s" % (
                                    modelo.name, comp_line.tipo_id.name,
                                    subparte_line.subparte_id.name, str(e)
                                )
                                _logger.error("      ✗ %s", msg)
                                errores.append(msg)

                        _logger.info("    📊 Total subpartes creadas: %s", subpartes_count)

                    except Exception as e:
                        msg = "Error en %s - %s: %s" % (modelo.name, comp_line.tipo_id.name, str(e))
                        _logger.error("    ✗ %s", msg)
                        errores.append(msg)

            # ===== ACCESORIOS =====
            accesorios_seleccionados = self.accesorio_line_ids.filtered(lambda a: a.seleccionado)
            if accesorios_seleccionados:
                _logger.info("  🔧 Procesando %s accesorios", len(accesorios_seleccionados))

            for acc_line in accesorios_seleccionados:
                try:
                    result = self._crear_o_actualizar_accesorio(AccesorioModel, modelo, acc_line)
                    if result == 'creado':
                        accesorios_creados += 1
                    elif result == 'actualizado':
                        accesorios_actualizados += 1
                    _logger.info("    ✓ Accesorio %s → %s", acc_line.tipo_id.name, result)
                except Exception as e:
                    msg = "Error en %s - %s: %s" % (modelo.name, acc_line.tipo_id.name, str(e))
                    _logger.error("    ✗ %s", msg)
                    errores.append(msg)

        # ===== RESUMEN FINAL =====
        _logger.info("=" * 80)
        _logger.info("RESUMEN FINAL")
        _logger.info("=" * 80)
        _logger.info("✓ Componentes creados: %s", componentes_creados)
        _logger.info("✓ Componentes actualizados: %s", componentes_actualizados)
        _logger.info("✓ Subpartes creadas: %s", subpartes_creadas)
        _logger.info("✓ Accesorios creados: %s", accesorios_creados)
        _logger.info("✓ Accesorios actualizados: %s", accesorios_actualizados)
        if errores:
            _logger.error("✗ Errores: %s", len(errores))
        _logger.info("=" * 80)

        mensaje_partes = [
            "Componentes: %s creados, %s actualizados" % (componentes_creados, componentes_actualizados),
            "Subpartes: %s agregadas" % subpartes_creadas,
            "Accesorios: %s creados, %s actualizados" % (accesorios_creados, accesorios_actualizados),
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

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def _crear_o_actualizar_componente(self, ComponenteModel, modelo, comp_line, color):
        """Crea o actualiza un componente. Retorna (resultado, componente)"""
        domain = [
            ('modelo_id', '=', modelo.id),
            ('tipo_id', '=', comp_line.tipo_id.id),
            ('color', '=', color),
        ]

        existente = ComponenteModel.search(domain, limit=1)

        vals = {
            'modelo_id': modelo.id,
            'tipo_id': comp_line.tipo_id.id,
            'color': color,
            'prioridad': comp_line.prioridad,
            'vida_util_paginas': comp_line.vida_util_paginas,
            'vida_util_meses': comp_line.vida_util_meses,
            'frase_desgaste': comp_line.frase_desgaste or '',
            'frase_cambio': comp_line.frase_cambio or '',
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
        """
        Crea o actualiza una subparte. 
        Retorna True si creó, False si ya existía o hubo error.
        """
        if not subparte_line.subparte_id:
            _logger.warning(
                "⚠️  Intento de crear subparte SIN subparte_id (comp=%s, wizard_line=%s)",
                componente.id, subparte_line.id
            )
            return False

        # Verificar que el componente existe
        if not componente or not componente.id:
            _logger.error("⚠️  Componente inválido o sin ID: %s", componente)
            return False

        domain = [
            ('componente_id', '=', componente.id),
            ('subparte_id', '=', subparte_line.subparte_id.id),
        ]

        existente = SubparteModel.search(domain, limit=1)

        vals = {
            'componente_id': componente.id,
            'subparte_id': subparte_line.subparte_id.id,
            'cantidad': subparte_line.cantidad,
            'nota': subparte_line.nota or '',
        }

        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
                _logger.info(
                    "      ↻ Subparte ACTUALIZADA (ID:%s, comp:%s, subparte:%s)",
                    existente.id, componente.id, subparte_line.subparte_id.id
                )
            else:
                _logger.info(
                    "      ⊘ Subparte YA EXISTE (ID:%s, comp:%s, subparte:%s) - no se sobrescribe",
                    existente.id, componente.id, subparte_line.subparte_id.id
                )
            return False
        else:
            try:
                nuevo = SubparteModel.create(vals)
                _logger.info(
                    "      ✓ Subparte CREADA (ID:%s, comp:%s, subparte:%s, cant:%s)",
                    nuevo.id, componente.id, subparte_line.subparte_id.id, vals['cantidad']
                )
                return True
            except Exception as e:
                _logger.error(
                    "      ✗ ERROR al crear subparte (comp:%s, subparte:%s): %s",
                    componente.id, subparte_line.subparte_id.id, str(e)
                )
                raise

    def _crear_o_actualizar_accesorio(self, AccesorioModel, modelo, acc_line):
        """Crea o actualiza un accesorio"""
        domain = [
            ('modelo_id', '=', modelo.id),
            ('tipo_id', '=', acc_line.tipo_id.id),
        ]

        existente = AccesorioModel.search(domain, limit=1)

        vals = {
            'modelo_id': modelo.id,
            'tipo_id': acc_line.tipo_id.id,
            'obligatorio': acc_line.obligatorio,
            'nota': acc_line.nota or '',
        }

        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
                return 'actualizado'
            return 'existente'
        else:
            AccesorioModel.create(vals)
            return 'creado'


# ============================================================================
# LÍNEA DE COMPONENTE
# ============================================================================
class WizardAsignarComponentesLinea(models.TransientModel):
    _name = 'wizard.asignar.componentes.linea'
    _description = 'Línea de componente para asignación masiva'

    wizard_id = fields.Many2one(
        'wizard.asignar.componentes',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )

    tipo_id = fields.Many2one(
        'componente.tipo',
        string='Tipo de Componente',
        required=True
    )

    # Campo auxiliar para mostrar info al usuario
    subpartes_info = fields.Html(
        string='Información',
        compute='_compute_subpartes_info',
        sanitize=False
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

    subparte_ids = fields.One2many(
        'wizard.asignar.componentes.subparte',
        'componente_line_id',
        string='Subpartes'
    )

    @api.depends('tipo_id', 'subparte_ids')
    def _compute_subpartes_info(self):
        """Mostrar información sobre las subpartes disponibles"""
        for record in self:
            if not record.tipo_id:
                record.subpartes_info = False
                continue

            # Si ya hay subpartes cargadas
            if record.subparte_ids:
                total = len(record.subparte_ids)
                seleccionadas = len(record.subparte_ids.filtered(lambda s: s.seleccionado))
                record.subpartes_info = (
                    f'<div class="alert alert-success" style="margin: 10px 0;">'
                    f'✅ <strong>{seleccionadas} de {total}</strong> subpartes seleccionadas. '
                    f'Puedes desmarcar las que NO quieras agregar.'
                    f'</div>'
                )
            else:
                # Verificar si hay subpartes disponibles
                disponibles = self.env['componente.subparte'].search_count([
                    ('tipo_id', '=', record.tipo_id.id),
                    ('active', '=', True)
                ])

                if disponibles > 0:
                    record.subpartes_info = (
                        f'<div class="alert alert-info" style="margin: 10px 0;">'
                        f'ℹ️ Hay <strong>{disponibles} subpartes</strong> disponibles. '
                        f'Haz clic en el botón "Cargar/Seleccionar Subpartes" para elegir cuáles agregar.'
                        f'</div>'
                    )
                else:
                    record.subpartes_info = (
                        f'<div class="alert alert-warning" style="margin: 10px 0;">'
                        f'⚠️ No hay subpartes configuradas para este tipo de componente.'
                        f'</div>'
                    )

    def action_cargar_subpartes(self):
        """Abrir popup para seleccionar subpartes"""
        self.ensure_one()

        if not self.tipo_id:
            raise UserError("Primero debes seleccionar un tipo de componente")

        # Buscar subpartes disponibles
        subpartes_disponibles = self.env['componente.subparte'].search([
            ('tipo_id', '=', self.tipo_id.id),
            ('active', '=', True)
        ])

        if not subpartes_disponibles:
            raise UserError(f"No hay subpartes configuradas para el tipo '{self.tipo_id.name}'")

        # Si el registro ya está guardado (tiene ID entero real), crear directamente
        if self.id and isinstance(self.id, int):
            _logger.info("🔘 Recreando subpartes para línea existente ID:%s", self.id)
            self._recrear_subpartes()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Subpartes cargadas',
                    'message': f'Se cargaron {len(subpartes_disponibles)} subpartes',
                    'type': 'success',
                }
            }

        # Si es registro nuevo (NewId), abrir wizard de selección
        _logger.info("🆕 Abriendo wizard de selección para registro nuevo")

        # Crear wizard de selección
        wizard = self.env['wizard.seleccionar.subpartes'].create({
            'componente_line_id': self.id,
            'tipo_id': self.tipo_id.id,
        })

        # Crear líneas de selección
        for subparte in subpartes_disponibles:
            self.env['wizard.seleccionar.subpartes.linea'].create({
                'wizard_id': wizard.id,
                'subparte_id': subparte.id,
                'seleccionado': True,
                'cantidad': 1.0,
            })

        return {
            'name': 'Seleccionar Subpartes',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.seleccionar.subpartes',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.onchange('tipo_id')
    def _onchange_tipo_id(self):
        """
        Cuando cambia el tipo, solo limpiamos las subpartes existentes.
        Las subpartes se crearán automáticamente al guardar.
        """
        if not self.tipo_id:
            self.subparte_ids = [(5, 0, 0)]
            return

        # Si es un registro ya guardado, crear las subpartes inmediatamente
        if self.id and isinstance(self.id, int):
            _logger.info("🔄 Tipo cambiado en registro existente ID:%s - recreando subpartes", self.id)
            self._recrear_subpartes()
        else:
            # Record nuevo - solo limpiar, se crearán al guardar
            _logger.info("🆕 Tipo seleccionado en registro nuevo - subpartes se crearán al guardar")
            self.subparte_ids = [(5, 0, 0)]

    def _recrear_subpartes(self):
        """Recrear las subpartes para el tipo actual"""
        self.ensure_one()

        if not self.tipo_id:
            return

        # Limpiar existentes
        self.subparte_ids.unlink()

        # Buscar subpartes disponibles
        subpartes_disponibles = self.env['componente.subparte'].search([
            ('tipo_id', '=', self.tipo_id.id),
            ('active', '=', True)
        ])

        if not subpartes_disponibles:
            _logger.info("  No hay subpartes para tipo %s", self.tipo_id.name)
            return

        _logger.info("  Creando %s subpartes", len(subpartes_disponibles))

        # Crear nuevas
        SubparteModel = self.env['wizard.asignar.componentes.subparte']
        for subparte in subpartes_disponibles:
            SubparteModel.create({
                'componente_line_id': self.id,
                'subparte_id': subparte.id,
                'cantidad': 1.0,
                'seleccionado': True,
                'nota': '',
            })

        # Refrescar
        self.invalidate_recordset(['subparte_ids'])

    @api.model_create_multi
    def create(self, vals_list):
        """Crear líneas de componente y sus subpartes, asegurando wizard_id"""
        _logger.info("🔨 Creando %s líneas de componente", len(vals_list))

        # Intentar obtener wizard_id por contexto si no viene en vals
        default_wizard_id = self.env.context.get('default_wizard_id') or self.env.context.get('active_id')

        for vals in vals_list:
            if not vals.get('wizard_id') and default_wizard_id:
                _logger.info("  ➕ Inyectando wizard_id=%s en línea sin wizard_id", default_wizard_id)
                vals['wizard_id'] = default_wizard_id

        # Crear las líneas primero
        records = super().create(vals_list)

        # Ahora crear las subpartes para cada línea que tenga tipo
        for record in records:
            if record.tipo_id:
                _logger.info("  ✓ Línea creada ID:%s tipo=%s - creando subpartes",
                             record.id, record.tipo_id.name)
                record._crear_subpartes_para_tipo()
            else:
                _logger.info("  ✓ Línea creada ID:%s sin tipo", record.id)

        return records

    def write(self, vals):
        """Actualizar línea de componente y mantener coherencia de subpartes"""
        # Si se está cambiando tipo_id
        if 'tipo_id' in vals:
            if vals['tipo_id']:
                _logger.info("🔄 Cambiando tipo_id a %s", vals['tipo_id'])

            # Si no se están tocando subparte_ids, limpiarlas para recargarlas
            if 'subparte_ids' not in vals:
                _logger.info("🔄 Cambiando tipo_id sin cambios en subparte_ids - limpiando")
                vals['subparte_ids'] = [(5, 0, 0)]

        result = super().write(vals)

        # Verificar después del write
        for record in self:
            _logger.info("💾 Línea componente ID:%s tipo=%s tiene %s subpartes después del write",
                         record.id,
                         record.tipo_id.name if record.tipo_id else '?',
                         len(record.subparte_ids))
            if record.subparte_ids:
                for sp in record.subparte_ids:
                    _logger.info("  → %s (ID:%s, sel=%s)",
                                 sp.subparte_id.display_name if sp.subparte_id else 'None',
                                 sp.id,
                                 sp.seleccionado)

        return result

    def _crear_subpartes_para_tipo(self):
        """
        Crear todas las subpartes disponibles para el tipo de componente.
        Todas se crean con seleccionado=True por defecto.
        """
        self.ensure_one()

        if not self.tipo_id:
            return

        # Buscar subpartes disponibles para este tipo
        subpartes_disponibles = self.env['componente.subparte'].search([
            ('tipo_id', '=', self.tipo_id.id),
            ('active', '=', True)
        ])

        if not subpartes_disponibles:
            _logger.info("    No hay subpartes disponibles para tipo %s", self.tipo_id.name)
            return

        _logger.info("    Creando %s subpartes para tipo %s",
                     len(subpartes_disponibles), self.tipo_id.name)

        # Crear todas las subpartes
        SubparteModel = self.env['wizard.asignar.componentes.subparte']
        for subparte in subpartes_disponibles:
            SubparteModel.create({
                'componente_line_id': self.id,
                'subparte_id': subparte.id,
                'cantidad': 1.0,
                'seleccionado': True,  # Todas activas por defecto
                'nota': '',
            })
            _logger.info("      ✓ %s", subparte.display_name)


# ============================================================================
# SUBPARTE DENTRO DEL WIZARD
# ============================================================================
class WizardAsignarComponentesSubparte(models.TransientModel):
    _name = 'wizard.asignar.componentes.subparte'
    _description = 'Subparte de componente para asignación masiva'
    _rec_name = 'subparte_id'

    componente_line_id = fields.Many2one(
        'wizard.asignar.componentes.linea',
        string='Componente',
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

    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte',
        required=True,
        readonly=True
    )

    seleccionado = fields.Boolean(
        string='Agregar',
        default=True,
        help='Marcar para incluir esta subparte en la asignación'
    )

    cantidad = fields.Float(
        string='Cantidad',
        default=1.0
    )

    nota = fields.Char(string='Nota')

    @api.model_create_multi
    def create(self, vals_list):
        """Crear líneas de subparte, permitiendo valores None temporalmente"""
        _logger.info("🔨 Intentando crear %s líneas de subparte", len(vals_list))

        for i, vals in enumerate(vals_list):
            _logger.info("  Línea %s: %s", i + 1, vals)

        # Filtrar solo las que tienen subparte_id válido
        clean_vals = []
        for v in vals_list:
            if v.get('subparte_id'):
                clean_vals.append(v)
            else:
                _logger.warning("  ⚠️  Línea sin subparte_id: %s", v)

        if not clean_vals:
            _logger.warning("⚠️  No hay líneas válidas para crear - todas sin subparte_id")
            return self.browse()

        _logger.info("✓ Creando %s líneas válidas de subparte", len(clean_vals))
        records = super().create(clean_vals)

        for rec in records:
            _logger.info("  ✓ Subparte creada ID:%s → %s (sel=%s, cant=%s)",
                         rec.id,
                         rec.subparte_id.display_name if rec.subparte_id else '?',
                         rec.seleccionado,
                         rec.cantidad)

        return records


# ============================================================================
# LÍNEA DE ACCESORIO
# ============================================================================
class WizardAsignarComponentesAccesorio(models.TransientModel):
    _name = 'wizard.asignar.componentes.accesorio'
    _description = 'Línea de accesorio para asignación masiva'

    wizard_id = fields.Many2one(
        'wizard.asignar.componentes',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )

    tipo_id = fields.Many2one(
        'accesorio.tipo',
        string='Tipo de Accesorio',
        required=True
    )

    seleccionado = fields.Boolean(
        string='Agregar',
        default=False,
        help='Marcar para incluir este accesorio en la asignación'
    )

    obligatorio = fields.Boolean(
        string='Obligatorio',
        default=False
    )

    nota = fields.Char(string='Nota')


# ============================================================================
# WIZARD AUXILIAR PARA SELECCIONAR SUBPARTES
# ============================================================================
class WizardSeleccionarSubpartes(models.TransientModel):
    _name = 'wizard.seleccionar.subpartes'
    _description = 'Wizard para seleccionar subpartes a cargar'

    componente_line_id = fields.Many2one(
        'wizard.asignar.componentes.linea',
        string='Línea de Componente',
        required=True
    )

    tipo_id = fields.Many2one(
        'componente.tipo',
        string='Tipo de Componente',
        readonly=True
    )

    subparte_seleccion_ids = fields.One2many(
        'wizard.seleccionar.subpartes.linea',
        'wizard_id',
        string='Subpartes Disponibles'
    )

    def action_aplicar(self):
        """Aplicar las subpartes seleccionadas a la línea de componente"""
        self.ensure_one()

        componente_line = self.componente_line_id

        # Limpiar subpartes existentes en la línea
        if componente_line.subparte_ids:
            componente_line.subparte_ids.unlink()

        # Crear las subpartes seleccionadas
        SubparteModel = self.env['wizard.asignar.componentes.subparte']
        creadas = 0

        for linea in self.subparte_seleccion_ids.filtered(lambda l: l.seleccionado):
            SubparteModel.create({
                'componente_line_id': componente_line.id,
                'subparte_id': linea.subparte_id.id,
                'cantidad': linea.cantidad,
                'seleccionado': True,
                'nota': linea.nota or '',
            })
            creadas += 1

        _logger.info("✅ Se crearon %s subpartes para componente ID:%s", creadas, componente_line.id)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Subpartes agregadas',
                'message': f'Se agregaron {creadas} subpartes al componente',
                'type': 'success',
            }
        }


class WizardSeleccionarSubpartesLinea(models.TransientModel):
    _name = 'wizard.seleccionar.subpartes.linea'
    _description = 'Línea de subparte para selección'

    wizard_id = fields.Many2one(
        'wizard.seleccionar.subpartes',
        required=True,
        ondelete='cascade'
    )

    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte',
        required=True,
        readonly=True
    )

    seleccionado = fields.Boolean(
        string='Agregar',
        default=True
    )

    cantidad = fields.Float(
        string='Cantidad',
        default=1.0
    )

    nota = fields.Char(string='Nota')

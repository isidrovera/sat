# models/wizard_asignar_componentes.py
from odoo import models, fields, api
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
        """Actualizar el wizard y procesar líneas de componentes con subpartes"""
        # Antes del write, procesar componente_line_ids si están presentes
        if 'componente_line_ids' in vals:
            _logger.info("📝 Procesando componente_line_ids antes del write")
            processed_commands = []
            
            for cmd in vals['componente_line_ids']:
                if cmd[0] == 0:  # Comando create (0, 0, {vals})
                    cmd_vals = cmd[2]
                    _logger.info("  → Procesando comando CREATE para componente")
                    
                    # Si tiene subparte_ids, procesarlas
                    if 'subparte_ids' in cmd_vals and cmd_vals['subparte_ids']:
                        clean_subparte_cmds = []
                        for sub_cmd in cmd_vals['subparte_ids']:
                            if sub_cmd[0] == 0 and sub_cmd[2]:
                                sub_vals = sub_cmd[2]
                                # Solo incluir si tiene subparte_id
                                if sub_vals.get('subparte_id'):
                                    clean_subparte_cmds.append(sub_cmd)
                                    _logger.info("    ✓ Subparte válida: %s", sub_vals.get('subparte_id'))
                                else:
                                    _logger.warning("    ✗ Subparte sin subparte_id - ignorando")
                            else:
                                clean_subparte_cmds.append(sub_cmd)
                        
                        cmd_vals['subparte_ids'] = clean_subparte_cmds
                        _logger.info("  → %s subpartes limpias de %s originales",
                                   len(clean_subparte_cmds), len(cmd_vals.get('subparte_ids', [])))
                
                processed_commands.append(cmd)
            
            vals['componente_line_ids'] = processed_commands
        
        result = super().write(vals)
        
        # Después del write, verificar y corregir líneas sin subpartes
        for record in self:
            _logger.info("💾 Wizard actualizado ID:%s con %s líneas de componentes", 
                       record.id, len(record.componente_line_ids))
            
            for comp_line in record.componente_line_ids:
                _logger.info("  📦 Componente: %s (ID:%s) con %s subpartes", 
                           comp_line.tipo_id.name if comp_line.tipo_id else '?',
                           comp_line.id,
                           len(comp_line.subparte_ids))
                
                # Si el componente tiene tipo pero no subpartes, crearlas
                if comp_line.tipo_id and not comp_line.subparte_ids and isinstance(comp_line.id, int):
                    _logger.info("    ⚠️  Línea sin subpartes - creándolas automáticamente")
                    comp_line._crear_subpartes_para_tipo()
        
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

    @api.onchange('tipo_id')
    def _onchange_tipo_id(self):
        """Autocarga todas las subpartes disponibles para este tipo de componente"""
        if not self.tipo_id:
            self.subparte_ids = [(5, 0, 0)]  # Limpiar todas
            return

        subpartes_disponibles = self.env['componente.subparte'].search([
            ('tipo_id', '=', self.tipo_id.id),
            ('active', '=', True)
        ])

        if not subpartes_disponibles:
            self.subparte_ids = [(5, 0, 0)]
            _logger.info("No hay subpartes disponibles para tipo_id=%s", self.tipo_id.id)
            return

        _logger.info("🔍 Cargando %s subpartes para tipo '%s'", 
                   len(subpartes_disponibles), self.tipo_id.name)

        # Si el record ya existe (tiene ID real, no NewId), crear directamente
        if self.id and isinstance(self.id, int):
            # Record ya guardado - crear directamente en base de datos
            _logger.info("  📝 Record YA existe (ID:%s) - creando subpartes directamente", self.id)
            
            # Limpiar subpartes existentes
            self.env['wizard.asignar.componentes.subparte'].search([
                ('componente_line_id', '=', self.id)
            ]).unlink()
            
            # Crear nuevas directamente
            SubparteModel = self.env['wizard.asignar.componentes.subparte']
            for subparte in subpartes_disponibles:
                nueva = SubparteModel.create({
                    'componente_line_id': self.id,
                    'subparte_id': subparte.id,
                    'cantidad': 1.0,
                    'seleccionado': True,
                    'nota': '',
                })
                _logger.info("    ✓ Subparte creada ID:%s → %s", nueva.id, subparte.display_name)
            
            # Refrescar la relación
            self.invalidate_recordset(['subparte_ids'])
        else:
            # Record nuevo (NewId) - construir registros virtuales
            _logger.info("  📝 Record NUEVO (NewId) - creando recordset virtual")
            
            # Crear recordset de subpartes virtuales
            SubparteModel = self.env['wizard.asignar.componentes.subparte']
            subparte_records = SubparteModel.browse()
            
            for subparte in subpartes_disponibles:
                # Crear registro virtual (sin guardar en BD)
                virtual_record = SubparteModel.new({
                    'componente_line_id': self.id,
                    'subparte_id': subparte.id,
                    'cantidad': 1.0,
                    'seleccionado': True,
                    'nota': '',
                })
                subparte_records |= virtual_record
                _logger.info("  → Registro virtual creado: %s", subparte.display_name)
            
            self.subparte_ids = subparte_records
            _logger.info("✓ Total subpartes virtuales: %s", len(subparte_records))

    def write(self, vals):
        """Asegurar que las subpartes se persistan correctamente"""
        # Si se está cambiando tipo_id, las subpartes se limpiarán y recargarán
        if 'tipo_id' in vals and vals['tipo_id']:
            _logger.info("🔄 Cambiando tipo_id a %s", vals['tipo_id'])
        
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

    @api.model_create_multi
    def create(self, vals_list):
        """Crear líneas de componente"""
        _logger.info("🔨 Creando %s líneas de componente", len(vals_list))
        
        # 🎯 CLAVE: Procesar subparte_ids ANTES de crear
        for vals in vals_list:
            if 'subparte_ids' in vals and vals['subparte_ids']:
                # Limpiar comandos que no tienen subparte_id
                clean_commands = []
                for cmd in vals['subparte_ids']:
                    if cmd[0] == 0 and cmd[2] and cmd[2].get('subparte_id'):
                        # Comando válido con subparte_id
                        clean_commands.append(cmd)
                    elif cmd[0] in (1, 2, 3, 4, 5, 6):
                        # Otros comandos (update, delete, etc.)
                        clean_commands.append(cmd)
                
                vals['subparte_ids'] = clean_commands
                _logger.info("  📋 Limpiados comandos de subpartes: %s válidos de %s totales",
                           len(clean_commands), len(vals.get('subparte_ids', [])))
        
        records = super().create(vals_list)
        
        # Verificar después de crear
        for record in records:
            _logger.info("  ✓ Componente creado ID:%s tipo=%s con %s subpartes", 
                       record.id,
                       record.tipo_id.name if record.tipo_id else '?',
                       len(record.subparte_ids))
            
            # Solo forzar si NO hay subpartes Y el tipo tiene subpartes disponibles
            if record.tipo_id and not record.subparte_ids:
                subpartes_disponibles = self.env['componente.subparte'].search([
                    ('tipo_id', '=', record.tipo_id.id),
                    ('active', '=', True)
                ], limit=1)
                
                if subpartes_disponibles:
                    _logger.warning("    ⚠️  Componente sin subpartes pero tipo tiene subpartes disponibles")
                    _logger.warning("    ⚠️  Esto puede indicar un problema con los comandos One2many")
        
        return records
    
    def write(self, vals):
        """Actualizar línea de componente"""
        # Si se está cambiando tipo_id Y no hay cambios en subparte_ids, limpiar subpartes
        if 'tipo_id' in vals and 'subparte_ids' not in vals:
            _logger.info("🔄 Cambiando tipo_id sin cambios en subparte_ids - limpiando")
            vals['subparte_ids'] = [(5, 0, 0)]
        
        result = super().write(vals)
        
        # Verificar después del write
        for record in self:
            _logger.info("💾 Línea componente ID:%s tipo=%s tiene %s subpartes después del write", 
                       record.id, 
                       record.tipo_id.name if record.tipo_id else '?',
                       len(record.subparte_ids))
        
        return result
    
    def _crear_subpartes_para_tipo(self):
        """
        Método helper para crear subpartes basadas en el tipo.
        SOLO debe usarse cuando se cambia el tipo en un registro YA guardado.
        """
        self.ensure_one()
        
        if not self.tipo_id:
            return
        
        subpartes_disponibles = self.env['componente.subparte'].search([
            ('tipo_id', '=', self.tipo_id.id),
            ('active', '=', True)
        ])
        
        if not subpartes_disponibles:
            _logger.info("      No hay subpartes disponibles para tipo %s", self.tipo_id.name)
            return
        
        _logger.info("      Creando %s subpartes para tipo %s", 
                   len(subpartes_disponibles), self.tipo_id.name)
        
        SubparteModel = self.env['wizard.asignar.componentes.subparte']
        for subparte in subpartes_disponibles:
            nueva = SubparteModel.create({
                'componente_line_id': self.id,
                'subparte_id': subparte.id,
                'cantidad': 1.0,
                'seleccionado': True,
                'nota': '',
            })
            _logger.info("        ✓ Subparte creada ID:%s → %s", nueva.id, subparte.display_name)


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
            _logger.info("  Línea %s: %s", i+1, vals)
        
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
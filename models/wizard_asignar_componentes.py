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
    
    @api.depends('modelo_ids', 'componente_line_ids', 'componente_line_ids.subparte_ids',
                 'componente_line_ids.subparte_ids.seleccionado', 'accesorio_line_ids',
                 'accesorio_line_ids.seleccionado')
    def _compute_resumen(self):
        for wizard in self:
            html = '<div style="padding: 10px;">'
            html += '<h4>&#128203; Se procesarán %s modelo(s)</h4>' % len(wizard.modelo_ids)
            
            # 🎯 Clasificar modelos por tipo
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
                    
                    # Mostrar subpartes SELECCIONADAS
                    subpartes_seleccionadas = line.subparte_ids.filtered(lambda s: s.seleccionado)
                    if subpartes_seleccionadas:
                        html += '<ul style="margin-left: 40px; font-size: 0.9em; color: #666;">'
                        for subparte in subpartes_seleccionadas:
                            html += '<li>&#10004; %s (x%s)</li>' % (subparte.subparte_id.name, subparte.cantidad)
                        html += '</ul>'
            
            # Resumen de accesorios
            if wizard.accesorio_line_ids:
                accesorios_seleccionados = wizard.accesorio_line_ids.filtered(lambda a: a.seleccionado)
                total_acc = len(accesorios_seleccionados)
                html += '<li><strong>Accesorios:</strong> %s seleccionado(s) de %s disponible(s)</li>' % (
                    total_acc, len(wizard.accesorio_line_ids)
                )
                if accesorios_seleccionados:
                    for line in accesorios_seleccionados:
                        obligatorio_txt = ' <span style="color: red;">*Obligatorio</span>' if line.obligatorio else ''
                        html += '<li style="margin-left: 20px;">&#10004; %s%s</li>' % (line.tipo_id.name, obligatorio_txt)
            
            html += '</ul>'
            
            # 🎯 Calcular total estimado CORRECTO
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
            
            # Contar subpartes seleccionadas por modelo
            total_subpartes = 0
            for line in wizard.componente_line_ids:
                subpartes_sel = len(line.subparte_ids.filtered(lambda s: s.seleccionado))
                is_color_sensitive = getattr(line.tipo_id, 'is_color_sensitive', False)
                if is_color_sensitive:
                    # Subpartes por cada color creado
                    total_subpartes += subpartes_sel * (len(modelos_mono) + len(modelos_color) * 4)
                else:
                    total_subpartes += subpartes_sel * len(wizard.modelo_ids)
            
            # Contar solo accesorios seleccionados
            total_accesorios = len(wizard.modelo_ids) * len(wizard.accesorio_line_ids.filtered(lambda a: a.seleccionado))
            
            html += '<hr style="margin: 15px 0;"/>'
            html += '<p><strong>&#128202; Total estimado:</strong></p>'
            html += '<ul style="margin: 5px 0; font-size: 0.9em; color: #666;">'
            html += '<li>Componentes principales: %s</li>' % total_componentes
            html += '<li>Subpartes: %s</li>' % total_subpartes
            html += '<li>Accesorios: %s</li>' % total_accesorios
            html += '</ul>'
            html += '</div>'
            
            wizard.resumen = Markup(html)
    
    @api.model
    def default_get(self, fields_list):
        """Obtiene los modelos seleccionados del contexto y autocarga accesorios"""
        res = super().default_get(fields_list)
        
        # Obtener IDs de modelos seleccionados
        modelo_ids = self.env.context.get('active_ids', [])
        if modelo_ids:
            res['modelo_ids'] = [(6, 0, modelo_ids)]
            
            # 🔥 AUTOCARGAR TODOS LOS ACCESORIOS DISPONIBLES
            accesorios_disponibles = self.env['accesorio.tipo'].search([
                ('active', '=', True)
            ])
            
            if accesorios_disponibles:
                accesorio_lines = []
                for accesorio in accesorios_disponibles:
                    accesorio_lines.append((0, 0, {
                        'tipo_id': accesorio.id,
                        'seleccionado': False,  # Por defecto NO seleccionado
                        'obligatorio': False,
                        'nota': '',
                    }))
                res['accesorio_line_ids'] = accesorio_lines
        
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
            # 🎯 Determinar colores según el tipo de máquina
            es_monocromo = modelo.tipo_id == 'monocromatica'
            
            # ===== PROCESAR COMPONENTES =====
            for comp_line in self.componente_line_ids:
                is_color_sensitive = getattr(comp_line.tipo_id, 'is_color_sensitive', False)
                
                if is_color_sensitive:
                    # 🔥 Solo negro para monocroma, todos los colores para color
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
                            
                            # 🎯 Agregar solo subpartes SELECCIONADAS
                            subpartes_seleccionadas = comp_line.subparte_ids.filtered(lambda s: s.seleccionado)
                            for subparte_line in subpartes_seleccionadas:
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
                        
                        # 🎯 Agregar solo subpartes SELECCIONADAS
                        subpartes_seleccionadas = comp_line.subparte_ids.filtered(lambda s: s.seleccionado)
                        for subparte_line in subpartes_seleccionadas:
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
            # 🎯 Solo procesar accesorios SELECCIONADOS
            accesorios_seleccionados = self.accesorio_line_ids.filtered(lambda a: a.seleccionado)
            for acc_line in accesorios_seleccionados:
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
        
        # 🎯 RETORNAR ACCIÓN QUE CIERRA EL WIZARD Y MUESTRA NOTIFICACIÓN
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
    
    # Subpartes de este componente
    subparte_ids = fields.One2many(
        'wizard.asignar.componentes.subparte',
        'componente_line_id',
        string='Subpartes'
    )
    
    # 🎯 NUEVO: Evento cuando cambia el tipo de componente
    @api.onchange('tipo_id')
    def _onchange_tipo_id(self):
        """Autocarga todas las subpartes disponibles para este tipo de componente"""
        if not self.tipo_id:
            self.subparte_ids = [(5, 0, 0)]
            return
        
        # Buscar todas las subpartes de este tipo de componente
        subpartes_disponibles = self.env['componente.subparte'].search([
            ('tipo_id', '=', self.tipo_id.id),
            ('active', '=', True)
        ])
        
        if not subpartes_disponibles:
            self.subparte_ids = [(5, 0, 0)]
            return
        
        # 🔥 Autocargar todas las subpartes con checkbox pre-seleccionado
        subparte_lines = []
        for subparte in subpartes_disponibles:
            subparte_lines.append((0, 0, {
                'subparte_id': subparte.id,
                'cantidad': 1.0,
                'seleccionado': True,  # 🎯 Pre-seleccionado por defecto
                'nota': '',
            }))
        
        self.subparte_ids = subparte_lines


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
        readonly=True  # esto puede quedarse
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

    # 🔐 Blindaje: NO crear registros sin subparte_id
    @api.model_create_multi
    def create(self, vals_list):
        clean_vals = []
        for vals in vals_list:
            if not vals.get('subparte_id'):
                # Simplemente ignoramos líneas inválidas
                continue
            clean_vals.append(vals)
        if not clean_vals:
            return self.browse()  # vacío
        return super().create(clean_vals)



# ===== LÍNEA DE ACCESORIO CON AUTOCARGA =====
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
        required=True,   # 👈 requerido, pero SIN readonly aquí
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

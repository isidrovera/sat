# models/wizard_asignar_componentes.py
from odoo import models, fields, api

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
        compute='_compute_resumen'
    )
    
    @api.depends('modelo_ids', 'componente_line_ids', 'accesorio_line_ids')
    def _compute_resumen(self):
        for wizard in self:
            html = '<div style="padding: 10px;">'
            html += f'<h4>📋 Se procesarán {len(wizard.modelo_ids)} modelo(s)</h4>'
            html += '<ul>'
            
            # Resumen de componentes
            if wizard.componente_line_ids:
                html += f'<li><strong>Componentes:</strong> {len(wizard.componente_line_ids)} configuración(es)</li>'
                for line in wizard.componente_line_ids:
                    sensible = ' (K, C, M, Y)' if getattr(line.tipo_id, 'is_color_sensitive', False) else ''
                    subpartes_count = len(line.subparte_ids)
                    subpartes_info = f' con {subpartes_count} subparte(s)' if subpartes_count else ''
                    html += f'<li style="margin-left: 20px;">• {line.tipo_id.name}{sensible}{subpartes_info}</li>'
            
            # Resumen de accesorios
            if wizard.accesorio_line_ids:
                html += f'<li><strong>Accesorios:</strong> {len(wizard.accesorio_line_ids)} configuración(es)</li>'
                for line in wizard.accesorio_line_ids:
                    html += f'<li style="margin-left: 20px;">• {line.tipo_id.name}</li>'
            
            html += '</ul>'
            
            # Calcular total estimado
            total_componentes = 0
            for line in wizard.componente_line_ids:
                if getattr(line.tipo_id, 'is_color_sensitive', False):
                    total_componentes += 4  # K, C, M, Y
                else:
                    total_componentes += 1
            
            total_registros = (
                len(wizard.modelo_ids) * total_componentes +
                len(wizard.modelo_ids) * len(wizard.accesorio_line_ids)
            )
            
            html += f'<p><strong>Total estimado de registros principales:</strong> {total_registros}</p>'
            html += '</div>'
            
            wizard.resumen = html
    
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
            # ===== PROCESAR COMPONENTES =====
            for comp_line in self.componente_line_ids:
                is_color_sensitive = getattr(comp_line.tipo_id, 'is_color_sensitive', False)
                
                if is_color_sensitive:
                    # Crear un componente por cada color
                    colores = ['k', 'c', 'm', 'y']
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
                                    self._crear_subparte(
                                        SubparteModel,
                                        componente,
                                        subparte_line
                                    )
                                    subpartes_creadas += 1
                                except Exception as e:
                                    errores.append(
                                        f"Error subparte en {modelo.name} - {comp_line.tipo_id.name} ({color.upper()}) - "
                                        f"{subparte_line.subparte_id.name}: {str(e)}"
                                    )
                        except Exception as e:
                            errores.append(
                                f"Error en {modelo.name} - {comp_line.tipo_id.name} ({color.upper()}): {str(e)}"
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
                                self._crear_subparte(
                                    SubparteModel,
                                    componente,
                                    subparte_line
                                )
                                subpartes_creadas += 1
                            except Exception as e:
                                errores.append(
                                    f"Error subparte en {modelo.name} - {comp_line.tipo_id.name} - "
                                    f"{subparte_line.subparte_id.name}: {str(e)}"
                                )
                    except Exception as e:
                        errores.append(f"Error en {modelo.name} - {comp_line.tipo_id.name}: {str(e)}")
            
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
                    errores.append(f"Error en {modelo.name} - {acc_line.tipo_id.name}: {str(e)}")
        
        # Preparar mensaje de resultado
        mensaje = f"""
        <div style="font-family: Arial;">
            <h3>✅ Asignación Completada</h3>
            <ul>
                <li><strong>Componentes creados:</strong> {componentes_creados}</li>
                <li><strong>Componentes actualizados:</strong> {componentes_actualizados}</li>
                <li><strong>Subpartes agregadas:</strong> {subpartes_creadas}</li>
                <li><strong>Accesorios creados:</strong> {accesorios_creados}</li>
                <li><strong>Accesorios actualizados:</strong> {accesorios_actualizados}</li>
            </ul>
        """
        
        if errores:
            mensaje += "<h4 style='color: orange;'>⚠️ Errores encontrados:</h4><ul>"
            for error in errores[:10]:
                mensaje += f"<li>{error}</li>"
            if len(errores) > 10:
                mensaje += f"<li>... y {len(errores) - 10} errores más</li>"
            mensaje += "</ul>"
        
        mensaje += "</div>"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Proceso Completado',
                'message': mensaje,
                'type': 'success' if not errores else 'warning',
                'sticky': True,
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
        """Crea una subparte si no existe"""
        domain = [
            ('componente_id', '=', componente.id),
            ('subparte_id', '=', subparte_line.subparte_id.id)
        ]
        
        existente = SubparteModel.search(domain, limit=1)
        
        if not existente:
            SubparteModel.create({
                'componente_id': componente.id,
                'subparte_id': subparte_line.subparte_id.id,
                'cantidad': subparte_line.cantidad,
                'nota': subparte_line.nota,
            })
    
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


# ===== LÍNEA DE COMPONENTE CON SUS SUBPARTES =====
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
    
    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte',
        required=True
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
        required=True,
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
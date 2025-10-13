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
    
    # Tab de Componentes
    componente_tipo_ids = fields.Many2many(
        'componente.tipo',
        'wizard_componente_tipo_rel',
        'wizard_id',
        'tipo_id',
        string='Tipos de Componentes a agregar'
    )
    
    # Tab de Accesorios
    accesorio_tipo_ids = fields.Many2many(
        'accesorio.tipo',
        'wizard_accesorio_tipo_rel',
        'wizard_id',
        'tipo_id',
        string='Tipos de Accesorios a agregar'
    )
    
    # Opciones
    sobrescribir_existentes = fields.Boolean(
        string='Sobrescribir si ya existen',
        default=False,
        help='Si está marcado, actualizará componentes/accesorios existentes'
    )
    
    # Campos para configuración de componentes
    prioridad_default = fields.Selection(
        [('1', 'Crítico'), ('2', 'Medio'), ('3', 'Bajo')],
        string='Prioridad por defecto',
        default='2'
    )
    
    vida_util_paginas_default = fields.Integer(
        string='Vida útil por defecto (páginas)',
        default=0
    )
    
    vida_util_meses_default = fields.Integer(
        string='Vida útil por defecto (meses)',
        default=0
    )
    
    # Para accesorios
    obligatorio_default = fields.Boolean(
        string='Marcar accesorios como obligatorios',
        default=False
    )
    
    # Resumen
    resumen = fields.Html(
        string='Resumen',
        compute='_compute_resumen'
    )
    
    @api.depends('modelo_ids', 'componente_tipo_ids', 'accesorio_tipo_ids')
    def _compute_resumen(self):
        for wizard in self:
            html = '<div style="padding: 10px;">'
            html += f'<h4>📋 Se crearán registros para {len(wizard.modelo_ids)} modelo(s)</h4>'
            html += '<ul>'
            
            if wizard.componente_tipo_ids:
                html += f'<li><strong>Componentes:</strong> {len(wizard.componente_tipo_ids)} tipo(s)</li>'
                for tipo in wizard.componente_tipo_ids:
                    sensible = '(requiere color)' if getattr(tipo, 'is_color_sensitive', False) else ''
                    html += f'<li style="margin-left: 20px;">• {tipo.name} {sensible}</li>'
            
            if wizard.accesorio_tipo_ids:
                html += f'<li><strong>Accesorios:</strong> {len(wizard.accesorio_tipo_ids)} tipo(s)</li>'
                for tipo in wizard.accesorio_tipo_ids:
                    html += f'<li style="margin-left: 20px;">• {tipo.name}</li>'
            
            html += '</ul>'
            
            total_registros = (
                len(wizard.modelo_ids) * len(wizard.componente_tipo_ids) +
                len(wizard.modelo_ids) * len(wizard.accesorio_tipo_ids)
            )
            html += f'<p><strong>Total estimado de registros a crear:</strong> {total_registros}</p>'
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
        accesorios_creados = 0
        accesorios_actualizados = 0
        errores = []
        
        ComponenteModel = self.env['modelo.maquina.componente']
        AccesorioModel = self.env['modelo.maquina.accesorio']
        
        for modelo in self.modelo_ids:
            # ===== PROCESAR COMPONENTES =====
            for tipo_comp in self.componente_tipo_ids:
                # Verificar si el tipo requiere color
                is_color_sensitive = getattr(tipo_comp, 'is_color_sensitive', False)
                
                if is_color_sensitive:
                    # Crear un componente por cada color
                    colores = ['k', 'c', 'm', 'y']
                    for color in colores:
                        try:
                            self._crear_o_actualizar_componente(
                                ComponenteModel,
                                modelo,
                                tipo_comp,
                                color,
                                componentes_creados,
                                componentes_actualizados
                            )
                        except Exception as e:
                            errores.append(f"Error en {modelo.name} - {tipo_comp.name} ({color.upper()}): {str(e)}")
                else:
                    # Crear componente sin color
                    try:
                        result = self._crear_o_actualizar_componente(
                            ComponenteModel,
                            modelo,
                            tipo_comp,
                            False,
                            componentes_creados,
                            componentes_actualizados
                        )
                        if result == 'creado':
                            componentes_creados += 1
                        elif result == 'actualizado':
                            componentes_actualizados += 1
                    except Exception as e:
                        errores.append(f"Error en {modelo.name} - {tipo_comp.name}: {str(e)}")
            
            # ===== PROCESAR ACCESORIOS =====
            for tipo_acc in self.accesorio_tipo_ids:
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
                    errores.append(f"Error en {modelo.name} - {tipo_acc.name}: {str(e)}")
        
        # Preparar mensaje de resultado
        mensaje = f"""
        <div style="font-family: Arial;">
            <h3>✅ Asignación Completada</h3>
            <ul>
                <li><strong>Componentes creados:</strong> {componentes_creados}</li>
                <li><strong>Componentes actualizados:</strong> {componentes_actualizados}</li>
                <li><strong>Accesorios creados:</strong> {accesorios_creados}</li>
                <li><strong>Accesorios actualizados:</strong> {accesorios_actualizados}</li>
            </ul>
        """
        
        if errores:
            mensaje += "<h4 style='color: orange;'>⚠️ Errores encontrados:</h4><ul>"
            for error in errores[:10]:  # Mostrar máximo 10 errores
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
    
    def _crear_o_actualizar_componente(self, ComponenteModel, modelo, tipo_comp, color):
        """Crea o actualiza un componente"""
        domain = [
            ('modelo_id', '=', modelo.id),
            ('tipo_id', '=', tipo_comp.id),
            ('color', '=', color)
        ]
        
        existente = ComponenteModel.search(domain, limit=1)
        
        vals = {
            'modelo_id': modelo.id,
            'tipo_id': tipo_comp.id,
            'color': color,
            'prioridad': self.prioridad_default,
            'vida_util_paginas': self.vida_util_paginas_default,
            'vida_util_meses': self.vida_util_meses_default,
        }
        
        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
                return 'actualizado'
            return 'existente'
        else:
            ComponenteModel.create(vals)
            return 'creado'
    
    def _crear_o_actualizar_accesorio(self, AccesorioModel, modelo, tipo_acc):
        """Crea o actualiza un accesorio"""
        domain = [
            ('modelo_id', '=', modelo.id),
            ('tipo_id', '=', tipo_acc.id)
        ]
        
        existente = AccesorioModel.search(domain, limit=1)
        
        vals = {
            'modelo_id': modelo.id,
            'tipo_id': tipo_acc.id,
            'obligatorio': self.obligatorio_default,
        }
        
        if existente:
            if self.sobrescribir_existentes:
                existente.write(vals)
                return 'actualizado'
            return 'existente'
        else:
            AccesorioModel.create(vals)
            return 'creado'
# models/modelo_maquina.py
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class ModelosMaquina(models.Model):
    _inherit = 'modelo.maquina'
    
    # 🎯 Campo para copiar configuración automáticamente
    modelo_referencia_id = fields.Many2one(
        'modelo.maquina',
        string='Modelo de Referencia',
        help='Selecciona un modelo existente para copiar automáticamente sus componentes y accesorios',
        domain="[('id', '!=', id)]"
    )
    
    # Campos informativos
    total_componentes = fields.Integer(
        string='Componentes',
        compute='_compute_totales_config'
    )
    
    total_accesorios = fields.Integer(
        string='Accesorios',
        compute='_compute_totales_config'
    )
    
    def _compute_totales_config(self):
        """Cuenta componentes y accesorios configurados"""
        for record in self:
            record.total_componentes = self.env['modelo.maquina.componente'].search_count([
                ('modelo_id', '=', record.id)
            ])
            record.total_accesorios = self.env['modelo.maquina.accesorio'].search_count([
                ('modelo_id', '=', record.id)
            ])
    
    @api.onchange('modelo_referencia_id')
    def _onchange_modelo_referencia(self):
        """
        🔥 Cuando selecciona un modelo de referencia, 
        muestra información pero NO copia hasta guardar
        """
        if not self.modelo_referencia_id:
            return
        
        # Para registros nuevos, informar que se copiará al guardar
        if not self.id or isinstance(self.id, models.NewId):
            comp_count = self.env['modelo.maquina.componente'].search_count([
                ('modelo_id', '=', self.modelo_referencia_id.id)
            ])
            acc_count = self.env['modelo.maquina.accesorio'].search_count([
                ('modelo_id', '=', self.modelo_referencia_id.id)
            ])
            
            return {
                'warning': {
                    'title': 'Configuración se copiará al guardar',
                    'message': 'Al guardar este modelo, se copiarán automáticamente %d componentes y %d accesorios desde "%s"' % (
                        comp_count,
                        acc_count,
                        self.modelo_referencia_id.name
                    )
                }
            }
        
        # Para registros existentes, solo informar
        return {
            'warning': {
                'title': 'Información',
                'message': 'Para copiar configuración en un modelo existente, use el botón "Copiar Configuración desde Modelo"'
            }
        }
    
    def _copiar_configuracion_desde_modelo(self, modelo_origen):
        """
        Copia componentes y accesorios desde otro modelo.
        Esta función se usa tanto en create como en el botón manual.
        """
        if not modelo_origen:
            return {'componentes': 0, 'accesorios': 0}
        
        # VALIDACIÓN CRÍTICA: No copiar si no tenemos ID válido
        if not self.id or isinstance(self.id, models.NewId):
            return {'componentes': 0, 'accesorios': 0}
        
        ComponenteModel = self.env['modelo.maquina.componente']
        SubparteModel = self.env['modelo.maquina.componente.subparte']
        AccesorioModel = self.env['modelo.maquina.accesorio']
        
        # 🎯 Determinar si el destino es monocromático
        es_destino_monocromo = self.tipo_id == 'monocromatica'
        
        # ===== COPIAR COMPONENTES =====
        componentes_origen = ComponenteModel.search([
            ('modelo_id', '=', modelo_origen.id)
        ])
        
        componentes_copiados = 0
        for comp_origen in componentes_origen:
            # 🔥 Validar color: si destino es monocroma, solo copiar negro
            is_color_sensitive = getattr(comp_origen.tipo_id, 'is_color_sensitive', False)
            if is_color_sensitive and es_destino_monocromo and comp_origen.color != 'k':
                continue  # Saltar colores CMY en máquinas monocromáticas
            
            # Verificar si ya existe
            existe = ComponenteModel.search([
                ('modelo_id', '=', self.id),
                ('tipo_id', '=', comp_origen.tipo_id.id),
                ('color', '=', comp_origen.color)
            ], limit=1)
            
            if existe:
                continue  # No duplicar
            
            # Crear componente
            vals_comp = {
                'modelo_id': self.id,
                'tipo_id': comp_origen.tipo_id.id,
                'color': comp_origen.color,
                'prioridad': comp_origen.prioridad,
                'vida_util_paginas': comp_origen.vida_util_paginas,
                'vida_util_meses': comp_origen.vida_util_meses,
                'frase_desgaste': comp_origen.frase_desgaste,
                'frase_cambio': comp_origen.frase_cambio,
            }
            
            # Agregar estado_sugerido_id si existe
            if comp_origen.estado_sugerido_id:
                vals_comp['estado_sugerido_id'] = comp_origen.estado_sugerido_id.id
            
            try:
                comp_nuevo = ComponenteModel.create(vals_comp)
                componentes_copiados += 1
                
                # ===== COPIAR SUBPARTES DEL COMPONENTE =====
                subpartes_origen = SubparteModel.search([
                    ('componente_id', '=', comp_origen.id)
                ])
                
                for subparte_origen in subpartes_origen:
                    SubparteModel.create({
                        'componente_id': comp_nuevo.id,
                        'subparte_id': subparte_origen.subparte_id.id,
                        'cantidad': subparte_origen.cantidad,
                        'nota': subparte_origen.nota,
                    })
            except Exception as e:
                # Log el error pero continúa con los demás
                continue
        
        # ===== COPIAR ACCESORIOS =====
        accesorios_origen = AccesorioModel.search([
            ('modelo_id', '=', modelo_origen.id)
        ])
        
        accesorios_copiados = 0
        for acc_origen in accesorios_origen:
            existe_acc = AccesorioModel.search([
                ('modelo_id', '=', self.id),
                ('tipo_id', '=', acc_origen.tipo_id.id)
            ], limit=1)
            
            if existe_acc:
                continue  # No duplicar
            
            vals_acc = {
                'modelo_id': self.id,
                'tipo_id': acc_origen.tipo_id.id,
                'obligatorio': acc_origen.obligatorio,
                'nota': acc_origen.nota,
            }
            
            # Solo agregar estado_predeterminado_id si existe
            if acc_origen.estado_predeterminado_id:
                vals_acc['estado_predeterminado_id'] = acc_origen.estado_predeterminado_id.id
            
            # Copiar subpartes del accesorio si existen
            if hasattr(acc_origen, 'subparte_ids') and acc_origen.subparte_ids:
                vals_acc['subparte_ids'] = [(6, 0, acc_origen.subparte_ids.ids)]
            
            try:
                AccesorioModel.create(vals_acc)
                accesorios_copiados += 1
            except Exception as e:
                # Log el error pero continúa con los demás
                continue
        
        return {
            'componentes': componentes_copiados,
            'accesorios': accesorios_copiados
        }
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create para copiar configuración automáticamente
        cuando se crea un nuevo modelo con referencia
        """
        # Extraer modelo_referencia_id antes de crear
        modelos_referencia = []
        for vals in vals_list:
            modelo_ref_id = vals.get('modelo_referencia_id', False)
            modelos_referencia.append(modelo_ref_id)
        
        # Crear los registros
        records = super().create(vals_list)
        
        # Ahora copiar la configuración después de que el registro existe
        for record, modelo_ref_id in zip(records, modelos_referencia):
            if modelo_ref_id:
                modelo_referencia = self.env['modelo.maquina'].browse(modelo_ref_id)
                if modelo_referencia.exists():
                    record._copiar_configuracion_desde_modelo(modelo_referencia)
        
        return records
    
    def action_copiar_desde_modelo(self):
        """
        Botón para copiar configuración en modelos existentes
        """
        self.ensure_one()
        
        if not self.modelo_referencia_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Debe seleccionar un Modelo de Referencia primero',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Contar lo que se va a copiar
        comp_count = self.env['modelo.maquina.componente'].search_count([
            ('modelo_id', '=', self.modelo_referencia_id.id)
        ])
        acc_count = self.env['modelo.maquina.accesorio'].search_count([
            ('modelo_id', '=', self.modelo_referencia_id.id)
        ])
        
        # Ejecutar copia
        resultado = self._copiar_configuracion_desde_modelo(self.modelo_referencia_id)
        
        if not resultado or (resultado.get('componentes', 0) == 0 and resultado.get('accesorios', 0) == 0):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Información',
                    'message': 'No se copió ningún elemento. Pueden ya existir o no haber elementos que copiar.',
                    'type': 'info',
                    'sticky': True,
                }
            }
        
        # Recalcular totales
        self._compute_totales_config()
        
        comp_copiados = resultado.get('componentes', 0)
        acc_copiados = resultado.get('accesorios', 0)
        
        mensaje = 'Se copiaron %d de %d componentes y %d de %d accesorios desde "%s"' % (
            comp_copiados,
            comp_count,
            acc_copiados,
            acc_count,
            self.modelo_referencia_id.name
        )
        
        if comp_copiados < comp_count or acc_copiados < acc_count:
            mensaje += '\n\nNota: Algunos elementos ya existían y no se duplicaron.'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Configuración Copiada',
                'message': mensaje,
                'type': 'success',
                'sticky': True,
            }
        }
    
    def action_ver_componentes(self):
        """Abre vista de componentes de este modelo"""
        self.ensure_one()
        return {
            'name': 'Componentes - %s' % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'modelo.maquina.componente',
            'view_mode': 'list,form',
            'domain': [('modelo_id', '=', self.id)],
            'context': {
                'default_modelo_id': self.id,
                'search_default_modelo_id': self.id
            }
        }
    
    def action_ver_accesorios(self):
        """Abre vista de accesorios de este modelo"""
        self.ensure_one()
        return {
            'name': 'Accesorios - %s' % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'modelo.maquina.accesorio',
            'view_mode': 'list,form',
            'domain': [('modelo_id', '=', self.id)],
            'context': {
                'default_modelo_id': self.id,
                'search_default_modelo_id': self.id
            }
        }
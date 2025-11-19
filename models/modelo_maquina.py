# models/modelo_maquina.py
from odoo import models, fields, api

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
        carga automáticamente su configuración
        """
        if not self.modelo_referencia_id:
            return
        
        # Solo copiar si es un registro nuevo (sin ID aún)
        if self.id:
            return {
                'warning': {
                    'title': 'Información',
                    'message': 'Para copiar configuración en un modelo existente, use el botón "Copiar Configuración desde Modelo"'
                }
            }
        
        self._copiar_configuracion_desde_modelo(self.modelo_referencia_id)
        
        return {
            'warning': {
                'title': 'Configuración Cargada',
                'message': 'Se ha cargado la configuración del modelo %s. Guarde el registro para aplicar los cambios.' % self.modelo_referencia_id.name
            }
        }
    
    def _copiar_configuracion_desde_modelo(self, modelo_origen):
        """
        Copia componentes y accesorios desde otro modelo.
        Esta función se usa tanto en onchange como en el botón manual.
        """
        if not modelo_origen:
            return
        
        ComponenteModel = self.env['modelo.maquina.componente']
        SubparteModel = self.env['modelo.maquina.componente.subparte']
        AccesorioModel = self.env['modelo.maquina.accesorio']
        
        # 🎯 Determinar si el destino es monocromático
        es_destino_monocromo = self.tipo_id == 'monocromatica'
        
        # ===== COPIAR COMPONENTES =====
        componentes_origen = ComponenteModel.search([
            ('modelo_id', '=', modelo_origen.id)
        ])
        
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
            comp_nuevo = ComponenteModel.create(vals_comp)
            
            # ===== COPIAR SUBPARTES =====
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
        
        # ===== COPIAR ACCESORIOS =====
        accesorios_origen = AccesorioModel.search([
            ('modelo_id', '=', modelo_origen.id)
        ])
        
        for acc_origen in accesorios_origen:
            existe_acc = AccesorioModel.search([
                ('modelo_id', '=', self.id),
                ('tipo_id', '=', acc_origen.tipo_id.id)
            ], limit=1)
            
            if existe_acc:
                continue  # No duplicar
            
            AccesorioModel.create({
                'modelo_id': self.id,
                'tipo_id': acc_origen.tipo_id.id,
                'obligatorio': acc_origen.obligatorio,
                'nota': acc_origen.nota,
            })
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create para copiar configuración automáticamente
        cuando se crea un nuevo modelo con referencia
        """
        records = super().create(vals_list)
        
        for record in records:
            if record.modelo_referencia_id:
                record._copiar_configuracion_desde_modelo(record.modelo_referencia_id)
        
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
        self._copiar_configuracion_desde_modelo(self.modelo_referencia_id)
        
        # Recalcular totales
        self._compute_totales_config()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Configuración Copiada',
                'message': 'Se copiaron %s componentes y %s accesorios desde %s' % (
                    comp_count,
                    acc_count,
                    self.modelo_referencia_id.name
                ),
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
            'context': {'default_modelo_id': self.id}
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
            'context': {'default_modelo_id': self.id}
        }
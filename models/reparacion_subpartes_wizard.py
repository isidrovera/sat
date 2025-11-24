# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Definir la selección localmente para evitar importación circular
COMPONENTE_SELECTION = [
    ('ui_k', 'Unidad de imagen Black'),
    ('ui_c', 'Unidad de imagen Cyan'),
    ('ui_m', 'Unidad de imagen Magenta'),
    ('ui_y', 'Unidad de imagen Yellow'),
    ('dev_k', 'Developer Black'),
    ('dev_c', 'Developer Cyan'),
    ('dev_m', 'Developer Magenta'),
    ('dev_y', 'Developer Yellow'),
    ('fuser', 'Fusora / Rodillos'),
    ('itb', 'Faja/Banda de transferencia'),
    ('adf', 'ADF'),
    ('fin', 'Finalizador'),
    ('opt', 'Óptico'),
    ('papel', 'Transporte de papel / bandejas / bypass'),
    ('otro', 'Otro'),
]

class ReparacionAddSubpartsWizardLine(models.TransientModel):
    _name = 'reparacion.add.subparts.wizard.line'
    _description = 'Línea de subpartes wizard múltiple'

    wizard_id = fields.Many2one(
        'reparacion.add.subparts.wizard',
        required=True,
        ondelete='cascade'
    )

    # ⚠️ Campo CHAR dinámico (el que usamos realmente)
    componente_code = fields.Char(
        string='Código componente',
        required=True,
        help="Código interno del componente: ui_k, dev_c, fuser, t88_k, etc."
    )
    
    # ⚠️ Campo Selection LEGACY (mantener para evitar errores de BD, pero siempre será 'otro')
    componente = fields.Selection(
        COMPONENTE_SELECTION,
        string='Componente',
        default='otro',
    )

    # Nombre bonito calculado para mostrar en el wizard
    componente_display = fields.Char(
        'Componente',
        compute='_compute_componente_display',
        store=True
    )

    intervencion_id = fields.Many2one(
        'reparacion.intervencion',
        string='Intervención'
    )

    selected = fields.Boolean('Seleccionar', default=False)

    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte',
        required=True
    )

    accion_sub = fields.Selection([
        ('cambiado', 'Cambiado'),
        ('ajustado', 'Ajustado'),
        ('limpieza', 'Limpieza'),
        ('diagnosticado', 'Diagnosticado'),
        ('na', 'No aplica'),
    ], string='Acción', default='cambiado')

    codigo = fields.Char('Código/SKU')
    cantidad = fields.Float('Cantidad', default=1.0)
    nota = fields.Char('Nota')

    @api.depends('componente', 'componente_code')
    def _compute_componente_display(self):
        for record in self:
            if record.componente_code:
                # Intentar obtener nombre amigable
                try:
                    nombre = self.env['reparaciones.reparaciones']._get_component_display_name(
                        record.componente_code
                    )
                    record.componente_display = nombre
                except:
                    # Fallback si falla
                    comp_dict = dict(COMPONENTE_SELECTION)
                    record.componente_display = comp_dict.get(record.componente_code, record.componente_code)
            else:
                comp_dict = dict(COMPONENTE_SELECTION)
                record.componente_display = comp_dict.get(record.componente, record.componente or '')


class ReparacionAddSubpartsWizard(models.TransientModel):
    _name = 'reparacion.add.subparts.wizard'
    _description = 'Wizard: seleccionar subpartes múltiples componentes'

    reparacion_id = fields.Many2one('reparaciones.reparaciones', string='Reparación', required=True, readonly=True)
    componentes_info = fields.Html('Componentes', compute='_compute_componentes_info')
    line_ids = fields.One2many('reparacion.add.subparts.wizard.line', 'wizard_id', string='Subpartes')

    @api.depends('line_ids')
    def _compute_componentes_info(self):
        for record in self:
            if not record.line_ids:
                record.componentes_info = ""
                continue
            
            componentes = record.line_ids.mapped('componente_display')
            componentes_unicos = list(set(componentes))
            info = f"<p><strong>Componentes que requieren especificación:</strong><br/>"
            info += "<br/>".join(f"• {comp}" for comp in componentes_unicos)
            info += "</p>"
            record.componentes_info = info

    def action_apply(self):
        self.ensure_one()
        
        # Procesar cada intervención
        intervenciones_procesadas = set()
        
        for wline in self.line_ids.filtered('selected'):
            interv = wline.intervencion_id
            
            # Si es la primera vez que procesamos esta intervención, limpiar detalles existentes
            if interv.id not in intervenciones_procesadas:
                interv.detalle_ids.unlink()
                intervenciones_procesadas.add(interv.id)
            
            # Crear el detalle
            self.env['reparacion.intervencion.detalle'].create({
                'line_id': interv.id,
                'subparte_id': wline.subparte_id.id,
                'accion_sub': wline.accion_sub,
                'codigo': wline.codigo,
                'cantidad': wline.cantidad,
                'nota': wline.nota,
            })

        repar = self.reparacion_id
        from_action = self.env.context.get('from_action')
        auto_finalize = self.env.context.get('auto_finalize')
        from_generar_informe = self.env.context.get('from_generar_informe')

        # 🔁 Caso 1: venimos de FINALIZAR y queremos auto-finalizar
        if auto_finalize and from_action == 'finalizar_reparacion' and repar:
            return repar.action_finalizar_reparacion()

        # 📝 Caso 2: venimos de GENERAR INFORME -> regenerar informe
        if from_generar_informe and repar:
            try:
                html, calidad = repar._rep__build_informe_html()
                vals = {'informe': html}
                # si usas calidad_id como selección/char, lo dejas así; si es M2O, ya lo manejas en tu otra lógica
                if 'calidad_id' in repar._fields:
                    vals['calidad_id'] = calidad
                repar.write(vals)
                repar.message_post(body=_("Informe técnico actualizado con subpartes especificadas."))
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Informe actualizado'),
                        'message': _('Las subpartes han sido guardadas y el informe regenerado.'),
                        'type': 'success'
                    }
                }
            except Exception as e:
                repar.message_post(body=_("Error regenerando informe: %s") % str(e))

        # 🎯 Caso 3: cualquier otro origen -> solo cerrar
        return {'type': 'ir.actions.act_window_close'}

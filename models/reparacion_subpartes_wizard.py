# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ReparacionAddSubpartsWizardLine(models.TransientModel):
    _name = 'reparacion.add.subparts.wizard.line'
    _description = 'Línea temporal de subpartes (wizard)'

    wizard_id = fields.Many2one('reparacion.add.subparts.wizard', required=True, ondelete='cascade')
    subparte_id = fields.Many2one('reparacion.subparte', string='Subparte', required=True,
                                  domain="[('componente', '=', parent.componente)]")
    accion_sub = fields.Selection([
        ('cambiado', 'Cambiado'),
        ('ajustado', 'Ajustado'),
        ('limpieza', 'Limpieza'),
        ('diagnosticado', 'Diagnosticado'),
        ('na', 'No aplica'),
    ], string='Acción', required=True, default='cambiado')
    codigo = fields.Char('Código / SKU')
    cantidad = fields.Float('Cantidad', default=1.0)
    nota = fields.Char('Nota')


class ReparacionAddSubpartsWizard(models.TransientModel):
    _name = 'reparacion.add.subparts.wizard'
    _description = 'Wizard: añadir subpartes a intervención'

    reparacion_id = fields.Many2one('reparaciones.reparaciones', string='Reparación', required=True, readonly=True)
    intervencion_id = fields.Many2one('reparacion.intervencion', string='Intervención', required=True, readonly=True)
    componente = fields.Selection(related='intervencion_id.componente', store=False, readonly=True)

    line_ids = fields.One2many('reparacion.add.subparts.wizard.line', 'wizard_id', string='Subpartes')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        intervencion = self.env['reparacion.intervencion'].browse(self.env.context.get('active_intervencion_id'))
        reparacion = intervencion.reparacion_id
        res.update({
            'reparacion_id': reparacion.id,
            'intervencion_id': intervencion.id,
        })

        # pre-cargar líneas con lo que ya tuviera la intervención (si existe)
        lines_vals = []
        for d in intervencion.detalle_ids:
            lines_vals.append((0, 0, {
                'subparte_id': d.subparte_id.id,
                'accion_sub': d.accion_sub,
                'codigo': d.codigo,
                'cantidad': d.cantidad,
                'nota': d.nota,
            }))
        if lines_vals:
            res['line_ids'] = lines_vals
        return res

    def action_apply(self):
        self.ensure_one()
        interv = self.intervencion_id

        # borrar detalle previo y recrear con lo del wizard
        interv.detalle_ids.unlink()
        for wline in self.line_ids:
            self.env['reparacion.intervencion.detalle'].create({
                'line_id': interv.id,
                'subparte_id': wline.subparte_id.id,
                'accion_sub': wline.accion_sub,
                'codigo': wline.codigo,
                'cantidad': wline.cantidad,
                'nota': wline.nota,
            })

        # forzar actualización de informe si es autogenerado
        interv.reparacion_id._autofill_informe_si_corresponde()

        return {
            'type': 'ir.actions.act_window_close'
        }

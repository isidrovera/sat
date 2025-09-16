# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ReparacionAddSubpartsWizardLine(models.TransientModel):
    _name = 'reparacion.add.subparts.wizard.line'
    _description = 'Línea temporal de subpartes (wizard)'

    wizard_id = fields.Many2one('reparacion.add.subparts.wizard', required=True, ondelete='cascade')
    subparte_id = fields.Many2one(
        'reparacion.subparte', string='Subparte', required=True,
        domain="[('componente', '=', parent.componente)]"
    )
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

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', string='Reparación', required=True, readonly=True
    )
    intervencion_id = fields.Many2one(
        'reparacion.intervencion', string='Intervención', required=True, readonly=True
    )
    componente = fields.Selection(related='intervencion_id.componente', store=False, readonly=True)
    line_ids = fields.One2many('reparacion.add.subparts.wizard.line', 'wizard_id', string='Subpartes')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context or {}
        interv_id = (
            ctx.get('active_intervencion_id')
            or ctx.get('default_intervencion_id')
            or ctx.get('active_id')  # por si abren desde acción con active_id
        )
        if not interv_id:
            raise UserError(_("No se recibió la intervención activa en el contexto."))

        intervencion = self.env['reparacion.intervencion'].browse(interv_id)
        if not intervencion.exists():
            raise UserError(_("La intervención indicada no existe (ID: %s).") % interv_id)

        res.update({
            'reparacion_id': intervencion.reparacion_id.id,
            'intervencion_id': intervencion.id,
        })

        # Precarga de líneas existentes
        if intervencion.detalle_ids:
            res['line_ids'] = [(0, 0, {
                'subparte_id': d.subparte_id.id,
                'accion_sub': d.accion_sub,
                'codigo': d.codigo,
                'cantidad': d.cantidad,
                'nota': d.nota,
            }) for d in intervencion.detalle_ids]
        return res

    def action_apply(self):
        self.ensure_one()
        interv = self.intervencion_id

        # Borrar detalle previo y recrear con lo del wizard
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

        # Recalcular informe SOLO si tu modelo lo soporta
        repar = interv.reparacion_id
        if hasattr(repar, '_autofill_informe_si_corresponde'):
            try:
                repar._autofill_informe_si_corresponde()
            except Exception:
                # No bloquees el guardado del wizard si falla este paso
                pass

        return {'type': 'ir.actions.act_window_close'}

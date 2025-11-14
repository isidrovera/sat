# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ReparacionSubparte(models.Model):
    _name = 'reparacion.subparte'
    _description = 'Catálogo de Subpartes por Componente'
    _order = 'componente, name'

    # NOTA:
    # Esta lista se puede seguir usando como referencia "clásica",
    # pero YA NO limita a reparacion.intervencion.componente,
    # porque ahora ese campo es Char dinámico.
    COMPONENTE = [
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

    name = fields.Char('Subparte', required=True)
    # Este catálogo puede seguir usando Selection porque es estático
    componente = fields.Selection(COMPONENTE, string='Componente', required=True)
    default_code = fields.Char('Código sugerido')
    active = fields.Boolean(default=True)


class ReparacionIntervencionDetalle(models.Model):
    _name = 'reparacion.intervencion.detalle'
    _description = 'Detalle de Subpartes Intervenidas'

    line_id = fields.Many2one(
        'reparacion.intervencion',
        string='Intervención',
        required=True,
        ondelete='cascade'
    )
    # Ya migrado a componente.subparte (catálogo nuevo)
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
    ], string='Acción', required=True, default='cambiado')
    codigo = fields.Char('Código / SKU')
    cantidad = fields.Float('Cantidad', default=1.0)
    nota = fields.Char('Nota')


class ReparacionIntervencion(models.Model):
    _name = 'reparacion.intervencion'
    _description = 'Intervenciones y Cambios en Reparaciones'
    _order = 'id desc'

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        required=True,
        ondelete='cascade'
    )

    # ⚠️ CAMBIO IMPORTANTE:
    # Antes: Selection(ReparacionSubparte.COMPONENTE)
    # Ahora: Char dinámico para aceptar cualquier código ('ui_k', 'dev_c', 't88_k', etc.)
    #
    # A nivel de BD, Selection se guarda como VARCHAR, así que el cambio es
    # transparente: no se pierde data y Odoo no necesita migración manual.
    componente = fields.Char(
        string='Componente',
        required=True,
        help="Código interno del componente (ej: ui_k, dev_c, fuser, t88_k, etc.)"
    )

    # Si quieres, podemos más adelante añadir un campo compute Many2one/Selection
    # solo para mostrar una etiqueta bonita en formularios, pero no es obligatorio
    # para que el flujo del wizard/informe funcione.

    accion = fields.Selection([
        ('cambiado', 'Cambio de repuesto(s)'),
        ('ajustado', 'Ajuste / calibración'),
        ('limpieza', 'Limpieza'),
        ('diagnosticado', 'Diagnóstico'),
    ], string='Acción realizada', required=True, default='cambiado')

    detalle_ids = fields.One2many(
        'reparacion.intervencion.detalle',
        'line_id',
        string='Subpartes'
    )
    observacion = fields.Char('Observación')

    es_cambio = fields.Boolean(
        compute='_compute_es_cambio',
        store=True,
        string='Implica cambio de repuesto'
    )

    @api.depends('accion', 'detalle_ids.accion_sub')
    def _compute_es_cambio(self):
        for rec in self:
            rec.es_cambio = (
                rec.accion == 'cambiado'
                or any(d.accion_sub == 'cambiado' for d in rec.detalle_ids)
            )

    def action_open_subparts_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Añadir/Editar Subpartes',
            'res_model': 'reparacion.add.subparts.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('sat.view_reparacion_add_subparts_wizard_form').id,
            'target': 'new',
            'context': {
                'active_intervencion_id': self.id,
                'default_intervencion_id': self.id,
                'default_reparacion_id': self.reparacion_id.id,
            },
        }

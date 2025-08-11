from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)


class PrintTrackerEntityLabel(models.Model):
    _name = 'printtracker.entity.label'
    _description = 'Etiquetas de Entidades PrintTracker'
    _rec_name = 'display_name'

    entity_id = fields.Many2one('printtracker.entity', string='Entidad',
                               required=True, ondelete='cascade')
    key = fields.Char('Clave', required=True)
    value = fields.Char('Valor', required=True)
    display_name = fields.Char('Etiqueta', compute='_compute_display_name', store=True)
    
    @api.depends('key', 'value')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.key}: {record.value}"

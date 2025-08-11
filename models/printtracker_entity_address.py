from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

class PrintTrackerEntityAddress(models.Model):
    _name = 'printtracker.entity.address'
    _description = 'Direcciones de Entidades PrintTracker'
    _rec_name = 'name'

    entity_id = fields.Many2one('printtracker.entity', string='Entidad',
                               required=True, ondelete='cascade')
    name = fields.Char('Nombre Dirección', required=True)
    address1 = fields.Char('Dirección 1')
    address2 = fields.Char('Dirección 2')
    city = fields.Char('Ciudad')
    state = fields.Char('Estado/Provincia')
    zip_code = fields.Char('Código Postal')
    country = fields.Char('País')
    
    def get_formatted_address(self):
        """Retorna la dirección formateada"""
        parts = [
            self.address1,
            self.address2,
            self.city,
            self.state,
            self.zip_code,
            self.country
        ]
        return ', '.join([part for part in parts if part])


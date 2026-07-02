# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.osv import expression


class SatSat(models.Model):
    _inherit = 'sat.sat'

    @api.depends('serie_id', 'name', 'cliente_id', 'marca')
    def _compute_display_name(self):
        """
        Muestra la máquina en los Many2one como:
        SERIE - MODELO - CLIENTE
        """
        for record in self:
            partes = []

            if record.serie_id:
                partes.append(record.serie_id)

            if record.name:
                partes.append(record.name.name or record.name.display_name)

            if record.cliente_id:
                partes.append(record.cliente_id.name)

            record.display_name = ' - '.join(partes) if partes else 'Sin serie'

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """
        Permite buscar sat.sat por:
        - serie_id
        - modelo de máquina
        - cliente
        - marca
        """
        domain = list(domain or [])

        if name:
            search_domain = [
                '|', '|', '|',
                ('serie_id', operator, name),
                ('name.name', operator, name),
                ('cliente_id.name', operator, name),
                ('marca', operator, name),
            ]
            domain = expression.AND([domain, search_domain])

        return self._search(domain, limit=limit, order=order)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """
        Compatibilidad para que el desplegable del Many2one muestre también la serie.
        """
        args = args or []
        domain = list(args)

        if name:
            search_domain = [
                '|', '|', '|',
                ('serie_id', operator, name),
                ('name.name', operator, name),
                ('cliente_id.name', operator, name),
                ('marca', operator, name),
            ]
            domain = expression.AND([domain, search_domain])

        records = self.search(domain, limit=limit)

        result = []
        for record in records:
            partes = []

            if record.serie_id:
                partes.append(record.serie_id)

            if record.name:
                partes.append(record.name.name or record.name.display_name)

            if record.cliente_id:
                partes.append(record.cliente_id.name)

            display = ' - '.join(partes) if partes else record.display_name
            result.append((record.id, display))

        return result
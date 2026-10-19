
# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class SatSat(models.Model):
    _inherit = 'sat.sat'

    @api.depends('serie_id', 'name', 'name.name', 'cliente_id', 'cliente_id.name', 'marca')
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
                partes.append(
                    record.name.name or record.name.display_name
                )

            if record.cliente_id:
                partes.append(record.cliente_id.name)

            record.display_name = (
                ' - '.join(partes) if partes else 'Sin serie'
            )

    @api.model
    def _name_search(
        self,
        name='',
        domain=None,
        operator='ilike',
        limit=100,
        order=None,
    ):
        """
        Permite buscar sat.sat por:
        - Serie
        - Modelo de máquina
        - Cliente
        - Marca

        Compatible con Odoo 19.
        """
        search_domain = fields.Domain(domain or [])

        if name:
            filters = fields.Domain.OR([
                fields.Domain('serie_id', operator, name),
                fields.Domain('name.name', operator, name),
                fields.Domain('cliente_id.name', operator, name),
                fields.Domain('marca', operator, name),
            ])

            search_domain = fields.Domain.AND([
                search_domain,
                filters,
            ])

        return self._search(
            search_domain,
            limit=limit,
            order=order,
        )

    @api.model
    def name_search(
        self,
        name='',
        domain=None,
        operator='ilike',
        limit=100,
    ):
        """
        Devuelve los equipos encontrados mostrando:
        SERIE - MODELO - CLIENTE.
        """
        ids = self._name_search(
            name=name,
            domain=domain,
            operator=operator,
            limit=limit,
        )

        records = self.browse(ids)

        return [
            (record.id, record.display_name)
            for record in records
        ]

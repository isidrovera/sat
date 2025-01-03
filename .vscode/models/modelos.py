from odoo import _, models, fields, api

class ModelosMaquin(models.Model):

    _name = 'modelo.maquina'
    _description = 'Modelo_de_maquina'

    name = fields.Char(string='Modelo de maquina', required=True )
    marca_id = fields.Many2one('marca.marca', string='Marca', required=True )
    tipo_id = fields.Selection([('color', 'Color'), ('monocromatica', 'Monocromatica')], required=True
                               )
    precio_venta = fields.Float('Precio de venta', required=True
                                )
    tipo_maquina_id = fields.Many2one('tipo.maquina', string='Tipo de maquina', required=True )

    @api.model
    def _default_currency_id(self):
        value = self.env['res.currency'].search(
            [('name', '=', 'USD')], limit=1)
        return value and value.id or False
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency', default=_default_currency_id)
    _sql_constraints = [("unique_name", "unique (name)",
                         "El modelo de maquina que intenta agregar ya existe")]

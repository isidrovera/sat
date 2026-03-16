from odoo import models, fields, api

class SatEntregaWizard(models.TransientModel):
    _name = 'sat.entrega.wizard'
    _description = 'Registrar entrega de máquina'

    maquina_id = fields.Many2one(
        'sat.sat',
        string="Máquina",
        required=True
    )

    factura_venta = fields.Char(
        string="Número de factura",
        required=True
    )

    fecha_entrega = fields.Date(
        string="Fecha de entrega",
        default=fields.Date.context_today,
        required=True
    )

    def action_confirmar(self):
        self.ensure_one()

        self.maquina_id.write({
            'factura_venta': self.factura_venta,
            'fecha_entrega': self.fecha_entrega,
            'estado_ventas_id': 'entregada',
        })

        self.maquina_id.message_post(
            body=f"""
            Entrega registrada:
            Factura: {self.factura_venta}<br/>
            Fecha: {self.fecha_entrega}
            """
        )
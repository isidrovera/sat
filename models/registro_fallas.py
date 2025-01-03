from odoo import _, models, fields, api
from bs4 import BeautifulSoup

class registro_fallas(models.Model):

    _name = 'fallas'
    _description = 'Registra las fallas de maquinas'
    name = fields.Char(string="invoice",  required=True)
    serie = fields.Char(string="Serie N°")
    marca = fields.Char(string='Marca')
    modelo_id = fields.Char(string='Modelo', required=True)
    proveedor_id = fields.Char(string='proveedor',)
    proveedor_short = fields.Char('Proveedor ', compute='_compute_proveedor_short', store=True)

    @api.depends('proveedor_id')
    def _compute_proveedor_short(self):
        for record in self:
            if record.proveedor_id:
                record.proveedor_short = record.proveedor_id[:20]

    descripcion = fields.Html(string='Descripcion de falla')
    descripcion_procesada = fields.Html(compute='_compute_descripcion_procesada', string="Descripción")

    @api.depends('descripcion')
    def _compute_descripcion_procesada(self):
        for record in self:
            if record.descripcion:
                plain_text = BeautifulSoup(record.descripcion, 'html.parser').get_text()
                chunks = [plain_text[i:i + 50] for i in range(0, len(plain_text), 50)]
                processed = '<br/>'.join(chunks)
                record.descripcion_procesada = processed

    importacion = fields.Char(string="Importación")
    invoice = fields.Char(string="Invoice")
    usuario_id = fields.Char(string='Técnico',)
    foto = fields.Binary(string='Foto')
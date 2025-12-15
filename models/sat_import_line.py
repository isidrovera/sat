# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SatImportLine(models.Model):
    _name = "sat.import.line"
    _description = "Staging de ingreso (tipo Excel) para crear sat.sat"
    _order = "create_date desc, id desc"

    active = fields.Boolean(default=True)

    # === Datos de línea (los que llenas primero) ===
    modelo_id = fields.Many2one(
        "modelo.maquina",
        string="Modelo",
        required=True,
        index=True,
        ondelete="restrict",
    )
    serie_id = fields.Char(string="Serie", required=True, index=True)
    contometro = fields.Char(string="Contómetro", required=True)
    precio_compra = fields.Float(string="Precio de compra")

    # === Cabecera (se setea luego con acción masiva) ===
    importacion = fields.Char(string="Importación", index=True)
    invoice = fields.Char(string="Invoice", index=True)
    proveedor_id = fields.Many2one("res.partner", string="Proveedor", index=True)

    # === Control / trazabilidad ===
    state = fields.Selection([
        ("draft", "Borrador"),
        ("ready", "Listo"),
        ("done", "Creado en SAT"),
        ("error", "Error"),
        ("cancel", "Cancelado"),
    ], string="Estado", default="draft", index=True, tracking=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        required=True,
        default=lambda self: self._default_currency_id(),
    )

    @api.model
    def _default_currency_id(self):
        # Primero intenta USD
        usd = self.env["res.currency"].search([("name", "=", "USD")], limit=1)
        if usd:
            return usd.id
        # Fallback: moneda de la compañía
        return self.env.company.currency_id.id

    error_msg = fields.Char(string="Detalle de error")
    sat_id = fields.Many2one("sat.sat", string="SAT creado", readonly=True, index=True)

    @api.constrains("serie_id")
    def _check_unique_serie_in_staging(self):
        for rec in self:
            if not rec.serie_id:
                continue
            dup = self.search([
                ("id", "!=", rec.id),
                ("serie_id", "=", rec.serie_id),
                ("active", "=", True),
                ("state", "not in", ("cancel",)),
            ], limit=1)
            if dup:
                raise ValidationError(_("La serie ya existe en Carga rápida (staging)."))

    @api.onchange("importacion", "invoice", "proveedor_id")
    def _onchange_header_fields(self):
        for rec in self:
            # Si ya tiene cabecera completa, marcar "ready"
            if rec.importacion and rec.invoice and rec.proveedor_id and rec.state in ("draft", "error"):
                rec.state = "ready"
            # Si se vacía algo, vuelve a draft (solo si no está done)
            if (not rec.importacion or not rec.invoice or not rec.proveedor_id) and rec.state in ("ready",):
                rec.state = "draft"
    def action_create_sat(self):
        # Trabaja con selección
        lines = self.exists()
        if not lines:
            raise UserError(_("No hay registros seleccionados."))

        Sat = self.env["sat.sat"]

        created = 0
        errors = 0

        for l in lines:
            # Saltar si ya está hecho o cancelado
            if l.state in ("done", "cancel"):
                continue

            # Validación mínima de cabecera
            if not (l.importacion and l.invoice and l.proveedor_id):
                l.state = "error"
                l.error_msg = _("Falta Importación/Invoice/Proveedor.")
                errors += 1
                continue

            # Validar duplicado contra sat.sat
            if Sat.search_count([("serie_id", "=", l.serie_id)]) > 0:
                l.state = "error"
                l.error_msg = _("La serie ya existe en SAT.")
                errors += 1
                continue

            try:
                sat = Sat.create({
                    "name": l.modelo_id.id,          # en sat.sat tu campo 'name' es Many2one modelo.maquina
                    "serie_id": l.serie_id,
                    "contometro": l.contometro,
                    "precio_compra": l.precio_compra or 0.0,
                    "importacion": l.importacion,
                    "invoice": l.invoice,
                    "proveedor_id": l.proveedor_id.id,
                })
                l.sat_id = sat.id
                l.state = "done"
                l.error_msg = False
                l.active = False   # archivar para que no estorbe
                created += 1
            except Exception as e:
                l.state = "error"
                l.error_msg = str(e)
                errors += 1

        # Notificación
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Resultado"),
                "message": _("Creados: %s | Errores: %s") % (created, errors),
                "type": "success" if errors == 0 else "warning",
                "sticky": False,
            }
        }
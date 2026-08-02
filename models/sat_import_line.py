# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SatImportLine(models.Model):
    _name = "sat.import.line"
    _description = "Staging de ingreso (tipo Excel) para crear sat.sat"
    _order = "create_date desc, id desc"

    active = fields.Boolean(
        string="Activo",
        default=True,
        index=True,
    )

    # =========================================================
    # DATOS DE LA LÍNEA
    # =========================================================

    modelo_id = fields.Many2one(
        "modelo.maquina",
        string="Modelo",
        required=True,
        index=True,
        ondelete="restrict",
    )

    serie_id = fields.Char(
        string="Serie",
        required=True,
        index=True,
    )

    contometro = fields.Char(
        string="Contómetro",
        required=True,
    )

    precio_compra = fields.Float(
        string="Precio de compra",
    )

    # =========================================================
    # CABECERA DE IMPORTACIÓN
    # =========================================================

    importacion = fields.Char(
        string="Importación",
        index=True,
    )

    invoice = fields.Char(
        string="Invoice",
        index=True,
    )

    proveedor_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        index=True,
        ondelete="restrict",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        required=True,
        default=lambda self: self._default_currency_id(),
    )

    # =========================================================
    # CONTROL Y TRAZABILIDAD
    # =========================================================

    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("ready", "Listo"),
            ("done", "Creado en SAT"),
            ("error", "Error"),
            ("cancel", "Cancelado"),
        ],
        string="Estado",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )

    error_msg = fields.Char(
        string="Detalle de error",
        readonly=True,
    )

    sat_id = fields.Many2one(
        "sat.sat",
        string="SAT creado",
        readonly=True,
        index=True,
        ondelete="set null",
    )

    # =========================================================
    # VALORES PREDETERMINADOS
    # =========================================================

    @api.model
    def _default_currency_id(self):
        usd = self.env["res.currency"].search(
            [("name", "=", "USD")],
            limit=1,
        )

        if usd:
            return usd.id

        return self.env.company.currency_id.id

    # =========================================================
    # VALIDACIONES
    # =========================================================

    @api.constrains("serie_id", "active", "state")
    def _check_unique_serie_in_staging(self):
        for record in self:
            if not record.serie_id:
                continue

            duplicate = self.search(
                [
                    ("id", "!=", record.id),
                    ("serie_id", "=", record.serie_id),
                    ("active", "=", True),
                    ("state", "!=", "cancel"),
                ],
                limit=1,
            )

            if duplicate:
                raise ValidationError(
                    _(
                        "La serie %s ya existe en Carga rápida."
                    )
                    % record.serie_id
                )

    # =========================================================
    # ONCHANGE
    # =========================================================

    @api.onchange(
        "importacion",
        "invoice",
        "proveedor_id",
    )
    def _onchange_header_fields(self):
        for record in self:
            header_complete = bool(
                record.importacion
                and record.invoice
                and record.proveedor_id
            )

            if (
                header_complete
                and record.state in ("draft", "error")
            ):
                record.state = "ready"
                record.error_msg = False

            elif (
                not header_complete
                and record.state == "ready"
            ):
                record.state = "draft"

    # =========================================================
    # ACCIONES
    # =========================================================

    def action_create_sat(self):
        lines = self.exists()

        if not lines:
            raise UserError(
                _("No hay registros seleccionados.")
            )

        Sat = self.env["sat.sat"]

        created = 0
        errors = 0

        for line in lines:
            if line.state in ("done", "cancel"):
                continue

            if not (
                line.importacion
                and line.invoice
                and line.proveedor_id
            ):
                line.write(
                    {
                        "state": "error",
                        "error_msg": _(
                            "Falta Importación, Invoice o Proveedor."
                        ),
                    }
                )
                errors += 1
                continue

            existing_sat = Sat.search(
                [
                    ("serie_id", "=", line.serie_id),
                ],
                limit=1,
            )

            if existing_sat:
                line.write(
                    {
                        "state": "error",
                        "error_msg": _(
                            "La serie %s ya existe en SAT."
                        )
                        % line.serie_id,
                    }
                )
                errors += 1
                continue

            try:
                sat = Sat.create(
                    {
                        # En sat.sat el campo name es Many2one
                        # relacionado con modelo.maquina.
                        "name": line.modelo_id.id,
                        "serie_id": line.serie_id,
                        "contometro": line.contometro,
                        "precio_compra": (
                            line.precio_compra or 0.0
                        ),
                        "importacion": line.importacion,
                        "invoice": line.invoice,
                        "proveedor_id": line.proveedor_id.id,
                    }
                )

                line.write(
                    {
                        "sat_id": sat.id,
                        "state": "done",
                        "error_msg": False,
                        "active": False,
                    }
                )

                created += 1

            except Exception as error:
                line.write(
                    {
                        "state": "error",
                        "error_msg": str(error),
                    }
                )
                errors += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Resultado"),
                "message": _(
                    "Creados: %s | Errores: %s"
                )
                % (
                    created,
                    errors,
                ),
                "type": (
                    "success"
                    if errors == 0
                    else "warning"
                ),
                "sticky": False,
            },
        }

    def action_cancel(self):
        pending_lines = self.filtered(
            lambda line: line.state != "done"
        )

        if not pending_lines:
            raise UserError(
                _(
                    "No hay líneas pendientes que puedan cancelarse."
                )
            )

        pending_lines.write(
            {
                "state": "cancel",
                "error_msg": False,
                "active": False,
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Líneas canceladas"),
                "message": _(
                    "Se cancelaron y archivaron %s línea(s)."
                )
                % len(pending_lines),
                "type": "success",
                "sticky": False,
            },
        }
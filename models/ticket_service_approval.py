# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TicketServiceApproval(models.Model):
    _inherit = "ticket.alquiler"

    # ============================================================
    # VISTO BUENO / CONFORMIDAD DEL SERVICIO
    # ============================================================

    conformidad_contacto_id = fields.Many2one(
        "res.partner",
        string="Contacto que dio conformidad",
        tracking=True,
        copy=False,
        index=True,
        help=(
            "Contacto de la empresa que recibió el servicio y dio "
            "su visto bueno. El contacto maestro puede reutilizarse "
            "en futuros tickets."
        ),
    )

    # Snapshot histórico: no usar related para no alterar tickets
    # antiguos cuando cambien los datos del contacto maestro.
    conformidad_nombre = fields.Char(
        string="Nombre de quien dio conformidad",
        tracking=True,
        copy=False,
    )

    conformidad_dni = fields.Char(
        string="DNI de quien dio conformidad",
        tracking=True,
        copy=False,
        index=True,
    )

    conformidad_celular = fields.Char(
        string="Celular de quien dio conformidad",
        tracking=True,
        copy=False,
    )

    conformidad_correo = fields.Char(
        string="Correo de quien dio conformidad",
        tracking=True,
        copy=False,
    )

    conformidad_firma = fields.Binary(
        string="Firma de conformidad",
        attachment=True,
        copy=False,
        help="Firma capturada al momento de aprobar el servicio.",
    )

    conformidad_firma_filename = fields.Char(
        string="Nombre archivo firma",
        copy=False,
    )

    conformidad_fecha = fields.Datetime(
        string="Fecha y hora de conformidad",
        tracking=True,
        copy=False,
        readonly=True,
    )

    conformidad_tecnico_id = fields.Many2one(
        "res.users",
        string="Técnico que obtuvo la conformidad",
        tracking=True,
        copy=False,
        readonly=True,
        index=True,
    )

    conformidad_registrada = fields.Boolean(
        string="Conformidad registrada",
        compute="_compute_conformidad_registrada",
        store=True,
        index=True,
        help=(
            "Indica que el ticket ya cuenta con los datos mínimos "
            "de la persona y su firma."
        ),
    )

    @api.depends(
        "conformidad_nombre",
        "conformidad_dni",
        "conformidad_celular",
        "conformidad_correo",
        "conformidad_firma",
        "conformidad_fecha",
    )
    def _compute_conformidad_registrada(self):
        for ticket in self:
            ticket.conformidad_registrada = bool(
                ticket.conformidad_nombre
                and ticket.conformidad_dni
                and ticket.conformidad_celular
                and ticket.conformidad_correo
                and ticket.conformidad_firma
                and ticket.conformidad_fecha
            )

    @api.constrains("conformidad_dni")
    def _check_conformidad_dni(self):
        for ticket in self:
            if not ticket.conformidad_dni:
                continue

            dni = "".join(
                char
                for char in str(ticket.conformidad_dni)
                if char.isdigit()
            )

            if len(dni) != 8:
                raise ValidationError(
                    "El DNI de quien da conformidad debe contener "
                    "exactamente 8 dígitos."
                )

    @api.constrains("conformidad_correo")
    def _check_conformidad_correo(self):
        for ticket in self:
            if not ticket.conformidad_correo:
                continue

            email = ticket.conformidad_correo.strip()

            if (
                "@" not in email
                or "." not in email.split("@")[-1]
            ):
                raise ValidationError(
                    "El correo de quien da conformidad no tiene "
                    "un formato válido."
                )

    def action_limpiar_conformidad(self):
        for ticket in self:
            if ticket.estado == "finalizado":
                raise ValidationError(
                    "No se puede eliminar la conformidad de un "
                    "ticket ya finalizado."
                )

            ticket.write(
                {
                    "conformidad_contacto_id": False,
                    "conformidad_nombre": False,
                    "conformidad_dni": False,
                    "conformidad_celular": False,
                    "conformidad_correo": False,
                    "conformidad_firma": False,
                    "conformidad_firma_filename": False,
                    "conformidad_fecha": False,
                    "conformidad_tecnico_id": False,
                }
            )

        return True

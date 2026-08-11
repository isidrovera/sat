# -*- coding: utf-8 -*-

import re

from odoo import http
from odoo.http import request

from .base import AppBaseController


class AppServiceApprovalController(AppBaseController):
    """
    API para buscar y crear el contacto que dará conformidad
    a un ticket de servicio.

    Esta etapa NO guarda todavía la firma ni finaliza el ticket.
    Solo resuelve/reutiliza el contacto de la empresa.
    """

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            (
                "/api/app/services/<int:service_id>"
                "/approval/contact"
            ),
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def service_approval_options(
        self,
        service_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # HELPERS
    # ============================================================

    def _approval_get_service(
        self,
        service_id,
        user,
    ):
        """
        Solo permite trabajar con tickets asignados
        al técnico autenticado.
        """
        return request.env[
            "ticket.alquiler"
        ].search(
            [
                (
                    "id",
                    "=",
                    service_id,
                ),
                (
                    "responsable",
                    "=",
                    user.id,
                ),
            ],
            limit=1,
        )

    def _approval_service_not_found_response(
        self,
    ):
        return self._json_response(
            {
                "success": False,
                "code": "SERVICE_NOT_FOUND",
                "message": (
                    "El servicio no existe o no está "
                    "asignado a este usuario."
                ),
            },
            status=404,
        )

    def _clean_dni(
        self,
        value,
    ):
        """
        Devuelve únicamente dígitos.
        Para DNI peruano se exigen 8 dígitos.
        """
        return re.sub(
            r"\D",
            "",
            str(
                value
                or ""
            ),
        )

    def _clean_text(
        self,
        value,
    ):
        if value in (
            None,
            False,
        ):
            return ""

        return str(
            value
        ).strip()

    def _serialize_contact(
        self,
        contact,
        company,
    ):
        if not contact:
            return False

        identification_type = False

        if (
            "l10n_latam_identification_type_id"
            in contact._fields
            and
            contact.l10n_latam_identification_type_id
        ):
            identification_type = self._many2one(
                contact.l10n_latam_identification_type_id
            )

        return {
            "id": contact.id,
            "name": (
                contact.name
                or ""
            ),
            "dni": (
                contact.vat
                if "vat" in contact._fields
                else False
            ),
            "phone": (
                contact.phone
                if "phone" in contact._fields
                else False
            ),
            "mobile": (
                contact.mobile
                if "mobile" in contact._fields
                else False
            ),
            "email": (
                contact.email
                if "email" in contact._fields
                else False
            ),
            "identification_type": (
                identification_type
            ),
            "company": (
                self._many2one(
                    company
                )
                if company
                else False
            ),
        }

    def _get_ticket_company(
        self,
        ticket,
    ):
        """
        Devuelve la empresa comercial del ticket.

        Si partner_id ya es la empresa, commercial_partner_id
        será la misma empresa.
        """
        partner = (
            ticket.partner_id
            if ticket.partner_id
            else False
        )

        if not partner:
            return False

        commercial = getattr(
            partner,
            "commercial_partner_id",
            False,
        )

        return (
            commercial
            or partner
        )

    def _find_contact_by_dni(
        self,
        company,
        dni,
    ):
        """
        Busca primero solamente entre los contactos hijos
        de la empresa del ticket.

        Se normaliza el VAT en Python para evitar perder
        coincidencias por espacios o signos.
        """
        if (
            not company
            or
            not dni
        ):
            return False

        Partner = request.env[
            "res.partner"
        ]

        candidates = Partner.search(
            [
                (
                    "parent_id",
                    "=",
                    company.id,
                ),
                (
                    "vat",
                    "!=",
                    False,
                ),
            ],
            limit=500,
        )

        for contact in candidates:
            contact_dni = self._clean_dni(
                contact.vat
            )

            if contact_dni == dni:
                return contact

        return False

    def _find_dni_identification_type(
        self,
    ):
        """
        Intenta localizar dinámicamente el tipo de identificación
        DNI existente en Odoo.

        No se fija un XML ID de otro módulo para mantener
        esta funcionalidad desacoplada.
        """
        try:
            IdentificationType = request.env[
                "l10n_latam.identification.type"
            ]
        except Exception:
            return False

        domain = [
            (
                "name",
                "ilike",
                "DNI",
            ),
        ]

        if (
            "active"
            in IdentificationType._fields
        ):
            domain.append(
                (
                    "active",
                    "=",
                    True,
                )
            )

        return IdentificationType.search(
            domain,
            limit=1,
        )

    def _validate_contact_payload(
        self,
        data,
    ):
        dni = self._clean_dni(
            data.get(
                "dni"
            )
        )

        name = self._clean_text(
            data.get(
                "name"
            )
        )

        mobile = self._clean_text(
            data.get(
                "mobile"
            )
        )

        email = self._clean_text(
            data.get(
                "email"
            )
        )

        errors = []

        if len(dni) != 8:
            errors.append(
                "El DNI debe contener exactamente 8 dígitos."
            )

        if not name:
            errors.append(
                "El nombre es obligatorio."
            )

        if not mobile:
            errors.append(
                "El celular es obligatorio."
            )

        if not email:
            errors.append(
                "El correo es obligatorio."
            )
        elif (
            "@" not in email
            or
            "." not in email.split(
                "@"
            )[-1]
        ):
            errors.append(
                "El correo no tiene un formato válido."
            )

        return {
            "dni": dni,
            "name": name,
            "mobile": mobile,
            "email": email,
            "errors": errors,
        }

    # ============================================================
    # BUSCAR CONTACTO POR DNI
    # GET /api/app/services/<id>/approval/contact?dni=12345678
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/approval/contact"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_approval_contact_find(
        self,
        service_id,
        **kwargs,
    ):
        user, error = self._require_user()

        if error:
            return error

        try:
            ticket = self._approval_get_service(
                service_id,
                user,
            )

            if not ticket:
                return (
                    self
                    ._approval_service_not_found_response()
                )

            company = self._get_ticket_company(
                ticket
            )

            if not company:
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_WITHOUT_CLIENT",
                        "message": (
                            "El ticket no tiene una empresa "
                            "cliente asociada."
                        ),
                    },
                    status=400,
                )

            dni = self._clean_dni(
                kwargs.get(
                    "dni"
                )
                or
                request.httprequest.args.get(
                    "dni"
                )
            )

            if len(dni) != 8:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_DNI",
                        "message": (
                            "El DNI debe contener "
                            "exactamente 8 dígitos."
                        ),
                    },
                    status=400,
                )

            contact = self._find_contact_by_dni(
                company,
                dni,
            )

            if not contact:
                return self._json_response(
                    {
                        "success": True,
                        "found": False,
                        "dni": dni,
                        "client": self._many2one(
                            company
                        ),
                        "message": (
                            "El DNI no está registrado "
                            "como contacto de este cliente."
                        ),
                    }
                )

            return self._json_response(
                {
                    "success": True,
                    "found": True,
                    "contact": self._serialize_contact(
                        contact,
                        company,
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # CREAR CONTACTO PARA LA EMPRESA DEL TICKET
    #
    # POST /api/app/services/<id>/approval/contact
    #
    # JSON:
    # {
    #     "dni": "12345678",
    #     "name": "JUAN PEREZ",
    #     "mobile": "999999999",
    #     "email": "juan@empresa.com"
    # }
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/approval/contact"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_approval_contact_create(
        self,
        service_id,
        **kwargs,
    ):
        user, error = self._require_user()

        if error:
            return error

        try:
            ticket = self._approval_get_service(
                service_id,
                user,
            )

            if not ticket:
                return (
                    self
                    ._approval_service_not_found_response()
                )

            if ticket.estado == "finalizado":
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_READ_ONLY",
                        "message": (
                            "No se puede crear o modificar "
                            "el contacto de conformidad de "
                            "un ticket finalizado."
                        ),
                    },
                    status=409,
                )

            company = self._get_ticket_company(
                ticket
            )

            if not company:
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_WITHOUT_CLIENT",
                        "message": (
                            "El ticket no tiene una empresa "
                            "cliente asociada."
                        ),
                    },
                    status=400,
                )

            data = self._get_json_body()

            values = self._validate_contact_payload(
                data
            )

            if values[
                "errors"
            ]:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_CONTACT_DATA",
                        "message": (
                            "No se puede registrar el contacto."
                        ),
                        "errors": values[
                            "errors"
                        ],
                    },
                    status=400,
                )

            existing = self._find_contact_by_dni(
                company,
                values[
                    "dni"
                ],
            )

            if existing:
                return self._json_response(
                    {
                        "success": True,
                        "created": False,
                        "already_exists": True,
                        "message": (
                            "El contacto ya estaba registrado "
                            "para este cliente."
                        ),
                        "contact": self._serialize_contact(
                            existing,
                            company,
                        ),
                    }
                )

            partner_vals = {
                "name": values[
                    "name"
                ],
                "parent_id": company.id,
                "company_type": "person",
                "type": "contact",
                "vat": values[
                    "dni"
                ],
                "mobile": values[
                    "mobile"
                ],
                "email": values[
                    "email"
                ],
            }

            identification_type = (
                self
                ._find_dni_identification_type()
            )

            Partner = request.env[
                "res.partner"
            ]

            if (
                identification_type
                and
                "l10n_latam_identification_type_id"
                in Partner._fields
            ):
                partner_vals[
                    "l10n_latam_identification_type_id"
                ] = identification_type.id

            contact = Partner.create(
                partner_vals
            )

            ticket.message_post(
                body=(
                    "Contacto para visto bueno creado "
                    "desde Copier OS App:<br/>"
                    f"<b>{contact.name}</b><br/>"
                    f"DNI: {values['dni']}<br/>"
                    f"Celular: {values['mobile']}<br/>"
                    f"Correo: {values['email']}"
                ),
                message_type="notification",
            )

            return self._json_response(
                {
                    "success": True,
                    "created": True,
                    "already_exists": False,
                    "message": (
                        "Contacto registrado correctamente "
                        "para este cliente."
                    ),
                    "contact": self._serialize_contact(
                        contact,
                        company,
                    ),
                },
                status=201,
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

# -*- coding: utf-8 -*-

import base64
import logging
import re

from odoo import fields, http
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppServiceApprovalController(AppBaseController):
    """
    API completa para el visto bueno de un ticket de servicio.

    Permite consultar la conformidad, buscar/crear el contacto
    responsable y registrar el snapshot histórico con firma.
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
            (
                "/api/app/services/<int:service_id>"
                "/approval"
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
        _logger.info(
            "[APP APPROVAL] Buscando ticket service_id=%s user_id=%s",
            service_id,
            user.id,
        )

        ticket = request.env[
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

        _logger.info(
            "[APP APPROVAL] Ticket encontrado=%s ticket_id=%s estado=%s",
            bool(ticket),
            ticket.id if ticket else False,
            ticket.estado if ticket else False,
        )

        return ticket

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

    def _get_contact_for_company(
        self,
        company,
        contact_id,
    ):
        try:
            contact_id = int(contact_id or 0)
        except Exception:
            contact_id = 0

        if not company or not contact_id:
            return False

        return request.env["res.partner"].search(
            [
                ("id", "=", contact_id),
                ("parent_id", "=", company.id),
            ],
            limit=1,
        )

    def _safe_signature_base64(
        self,
        value,
    ):
        if not value:
            return False, False

        value = str(value).strip()

        if "," in value:
            value = value.split(",", 1)[1]

        try:
            decoded = base64.b64decode(
                value,
                validate=True,
            )
        except Exception:
            return False, False

        if not decoded:
            return False, False

        if len(decoded) > 3 * 1024 * 1024:
            return False, False

        is_png = decoded.startswith(
            b"\x89PNG\r\n\x1a\n"
        )
        is_jpeg = decoded.startswith(
            b"\xff\xd8\xff"
        )

        if not (is_png or is_jpeg):
            return False, False

        return value, decoded

    def _approval_required_fields(self):
        return {
            "conformidad_contacto_id",
            "conformidad_nombre",
            "conformidad_dni",
            "conformidad_celular",
            "conformidad_correo",
            "conformidad_firma",
            "conformidad_firma_filename",
            "conformidad_fecha",
            "conformidad_tecnico_id",
            "conformidad_registrada",
        }

    def _approval_missing_fields(self, ticket):
        missing_fields = sorted(
            self._approval_required_fields()
            - set(ticket._fields.keys())
        )

        if missing_fields:
            _logger.error(
                "[APP APPROVAL] Campos de conformidad faltantes "
                "en ticket.alquiler: %s",
                ", ".join(missing_fields),
            )
        else:
            _logger.info(
                "[APP APPROVAL] Todos los campos de conformidad "
                "están registrados en ticket.alquiler."
            )

        return missing_fields

    def _serialize_approval(self, ticket):
        _logger.info(
            "[APP APPROVAL] Serializando conformidad ticket_id=%s",
            ticket.id,
        )

        contact = (
            ticket.conformidad_contacto_id
            if (
                "conformidad_contacto_id" in ticket._fields
                and ticket.conformidad_contacto_id
            )
            else False
        )

        technician = (
            ticket.conformidad_tecnico_id
            if (
                "conformidad_tecnico_id" in ticket._fields
                and ticket.conformidad_tecnico_id
            )
            else False
        )

        return {
            "registered": bool(
                ticket.conformidad_registrada
                if "conformidad_registrada" in ticket._fields
                else False
            ),
            "contact": (
                self._many2one(contact)
                if contact
                else False
            ),
            "name": (
                ticket.conformidad_nombre
                if "conformidad_nombre" in ticket._fields
                else False
            ),
            "dni": (
                ticket.conformidad_dni
                if "conformidad_dni" in ticket._fields
                else False
            ),
            "mobile": (
                ticket.conformidad_celular
                if "conformidad_celular" in ticket._fields
                else False
            ),
            "email": (
                ticket.conformidad_correo
                if "conformidad_correo" in ticket._fields
                else False
            ),
            "signed_at": (
                ticket.conformidad_fecha
                if "conformidad_fecha" in ticket._fields
                else False
            ),
            "technician": (
                self._many2one(technician)
                if technician
                else False
            ),
            "has_signature": bool(
                ticket.conformidad_firma
                if "conformidad_firma" in ticket._fields
                else False
            ),
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
        _logger.info(
            "[APP APPROVAL] GET /approval/contact iniciado "
            "service_id=%s dni=%s",
            service_id,
            kwargs.get("dni")
            or request.httprequest.args.get("dni"),
        )

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
                _logger.info(
                    "[APP APPROVAL] Contacto NO encontrado "
                    "service_id=%s company_id=%s dni=%s",
                    service_id,
                    company.id,
                    dni,
                )

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

            _logger.info(
                "[APP APPROVAL] Contacto encontrado "
                "service_id=%s contact_id=%s dni=%s",
                service_id,
                contact.id,
                dni,
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
            _logger.exception(
                "[APP APPROVAL] ERROR GET /approval/contact "
                "service_id=%s error=%s",
                service_id,
                exc,
            )
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
        _logger.info(
            "[APP APPROVAL] POST /approval/contact iniciado "
            "service_id=%s",
            service_id,
        )

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

            _logger.info(
                "[APP APPROVAL] Creando contacto "
                "service_id=%s company_id=%s dni=%s name=%s",
                service_id,
                company.id,
                values["dni"],
                values["name"],
            )

            contact = Partner.create(
                partner_vals
            )

            _logger.info(
                "[APP APPROVAL] Contacto creado contact_id=%s",
                contact.id,
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
            _logger.exception(
                "[APP APPROVAL] ERROR POST /approval/contact "
                "service_id=%s error=%s",
                service_id,
                exc,
            )
            return self._error_response(
                exc
            )

    # ============================================================
    # CONSULTAR VISTO BUENO
    # GET /api/app/services/<id>/approval
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/approval"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_approval_get(
        self,
        service_id,
        **kwargs,
    ):
        _logger.info(
            "[APP APPROVAL] GET /approval iniciado service_id=%s",
            service_id,
        )

        user, error = self._require_user()

        if error:
            _logger.warning(
                "[APP APPROVAL] GET /approval sin sesión válida "
                "service_id=%s",
                service_id,
            )
            return error

        try:
            _logger.info(
                "[APP APPROVAL] Usuario autenticado user_id=%s login=%s",
                user.id,
                user.login,
            )

            ticket = self._approval_get_service(
                service_id,
                user,
            )

            if not ticket:
                return self._approval_service_not_found_response()

            missing_fields = self._approval_missing_fields(
                ticket
            )

            if missing_fields:
                return self._json_response(
                    {
                        "success": False,
                        "code": "APPROVAL_MODEL_NOT_READY",
                        "message": (
                            "La estructura de visto bueno todavía "
                            "no está disponible en Odoo. "
                            "Actualiza primero el módulo SAT."
                        ),
                        "missing_fields": missing_fields,
                    },
                    status=500,
                )

            approval_data = self._serialize_approval(
                ticket
            )

            _logger.info(
                "[APP APPROVAL] GET /approval OK "
                "service_id=%s registered=%s has_signature=%s",
                service_id,
                approval_data.get("registered"),
                approval_data.get("has_signature"),
            )

            return self._json_response(
                {
                    "success": True,
                    "approval": approval_data,
                }
            )

        except Exception as exc:
            _logger.exception(
                "[APP APPROVAL] ERROR GET /approval "
                "service_id=%s error=%s",
                service_id,
                exc,
            )
            return self._error_response(exc)

    # ============================================================
    # REGISTRAR VISTO BUENO + FIRMA
    # POST /api/app/services/<id>/approval
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/approval"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_approval_register(
        self,
        service_id,
        **kwargs,
    ):
        _logger.info(
            "[APP APPROVAL] POST /approval iniciado service_id=%s",
            service_id,
        )

        user, error = self._require_user()

        if error:
            return error

        try:
            ticket = self._approval_get_service(
                service_id,
                user,
            )

            if not ticket:
                return self._approval_service_not_found_response()

            if ticket.estado == "finalizado":
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_READ_ONLY",
                        "message": (
                            "No se puede registrar o modificar "
                            "el visto bueno de un ticket finalizado."
                        ),
                    },
                    status=409,
                )

            missing_fields = self._approval_missing_fields(
                ticket
            )

            if missing_fields:
                return self._json_response(
                    {
                        "success": False,
                        "code": "APPROVAL_MODEL_NOT_READY",
                        "message": (
                            "Primero debe actualizarse el módulo "
                            "SAT con ticket_service_approval.py."
                        ),
                        "missing_fields": missing_fields,
                    },
                    status=500,
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

            _logger.info(
                "[APP APPROVAL] Payload recibido "
                "service_id=%s contact_id=%s dni=%s "
                "name=%s mobile_present=%s email_present=%s "
                "signature_present=%s",
                service_id,
                data.get("contact_id"),
                data.get("dni"),
                data.get("name"),
                bool(data.get("mobile")),
                bool(data.get("email")),
                bool(data.get("signature")),
            )

            contact = self._get_contact_for_company(
                company,
                data.get("contact_id"),
            )

            if not contact:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_APPROVAL_CONTACT",
                        "message": (
                            "El contacto seleccionado no existe "
                            "o no pertenece a la empresa "
                            "de este ticket."
                        ),
                    },
                    status=400,
                )

            values = self._validate_contact_payload(
                data
            )

            if values["errors"]:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_APPROVAL_DATA",
                        "message": (
                            "Los datos de quien da conformidad "
                            "no están completos."
                        ),
                        "errors": values["errors"],
                    },
                    status=400,
                )

            contact_dni = self._clean_dni(
                contact.vat
                if "vat" in contact._fields
                else False
            )

            if (
                contact_dni
                and contact_dni != values["dni"]
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONTACT_DNI_MISMATCH",
                        "message": (
                            "El DNI enviado no coincide con "
                            "el contacto seleccionado."
                        ),
                    },
                    status=400,
                )

            (
                signature_base64,
                signature_bytes,
            ) = self._safe_signature_base64(
                data.get("signature")
            )

            if (
                not signature_base64
                or not signature_bytes
            ):
                _logger.warning(
                    "[APP APPROVAL] Firma inválida "
                    "service_id=%s",
                    service_id,
                )

                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_SIGNATURE",
                        "message": (
                            "La firma es obligatoria y debe "
                            "ser una imagen PNG o JPEG válida "
                            "de hasta 3 MB."
                        ),
                    },
                    status=400,
                )

            filename = self._clean_text(
                data.get(
                    "signature_filename"
                )
            )

            if not filename:
                extension = (
                    "jpg"
                    if signature_bytes.startswith(
                        b"\xff\xd8\xff"
                    )
                    else "png"
                )
                filename = (
                    f"firma_{ticket.name or ticket.id}.{extension}"
                )

            _logger.info(
                "[APP APPROVAL] Guardando visto bueno "
                "service_id=%s contact_id=%s user_id=%s "
                "signature_bytes=%s",
                service_id,
                contact.id,
                user.id,
                len(signature_bytes),
            )

            ticket.write(
                {
                    "conformidad_contacto_id": contact.id,
                    "conformidad_nombre": values["name"],
                    "conformidad_dni": values["dni"],
                    "conformidad_celular": values["mobile"],
                    "conformidad_correo": values["email"],
                    "conformidad_firma": signature_base64,
                    "conformidad_firma_filename": filename,
                    "conformidad_fecha": fields.Datetime.now(),
                    "conformidad_tecnico_id": user.id,
                }
            )

            _logger.info(
                "[APP APPROVAL] Escritura completada "
                "service_id=%s conformidad_registrada=%s",
                service_id,
                ticket.conformidad_registrada,
            )

            if not ticket.conformidad_registrada:
                return self._json_response(
                    {
                        "success": False,
                        "code": "APPROVAL_INCOMPLETE",
                        "message": (
                            "El visto bueno fue guardado, "
                            "pero no quedó completo."
                        ),
                        "approval": self._serialize_approval(
                            ticket
                        ),
                    },
                    status=409,
                )

            ticket.message_post(
                body=(
                    "✅ <b>Visto bueno del servicio "
                    "registrado desde Copier OS App</b><br/>"
                    f"Persona: {values['name']}<br/>"
                    f"DNI: {values['dni']}<br/>"
                    f"Celular: {values['mobile']}<br/>"
                    f"Correo: {values['email']}<br/>"
                    f"Técnico: {user.name or 'N/A'}"
                ),
                message_type="notification",
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Visto bueno registrado correctamente."
                    ),
                    "approval": self._serialize_approval(
                        ticket
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "[APP APPROVAL] ERROR POST /approval "
                "service_id=%s error=%s",
                service_id,
                exc,
            )
            return self._error_response(exc)


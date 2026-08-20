# -*- coding: utf-8 -*-

from collections import OrderedDict
import logging

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import (
    CustomerPortal,
    pager as portal_pager,
)
from odoo.osv import expression


_logger = logging.getLogger(__name__)


class PortalAlquiler(CustomerPortal):

    # ==========================================================
    # MULTIEMPRESA PORTAL
    # ==========================================================

    def _get_portal_user_partner(self):
        """
        Contacto directamente relacionado al usuario portal.

        Importante:
        NO usamos commercial_partner_id directamente porque
        whatsapp_company_ids normalmente está configurado
        en el contacto.
        """
        return request.env.user.partner_id.sudo()

    def _get_portal_allowed_companies(self):
        """
        Devuelve todas las empresas que el usuario puede gestionar.

        Incluye:
        - Su empresa comercial principal.
        - Su empresa padre.
        - Empresas configuradas en whatsapp_company_ids.
        - El propio partner si es empresa.

        Utiliza _get_whatsapp_available_companies() del modelo
        res.partner para mantener una sola lógica.
        """
        partner = self._get_portal_user_partner()

        Partner = request.env["res.partner"].sudo()
        companies = Partner.browse()

        # ------------------------------------------------------
        # Empresa comercial principal
        # ------------------------------------------------------
        commercial_partner = partner.commercial_partner_id

        if commercial_partner and commercial_partner.is_company:
            companies |= commercial_partner

        # ------------------------------------------------------
        # Empresas configuradas para WhatsApp
        # ------------------------------------------------------
        if hasattr(partner, "_get_whatsapp_available_companies"):
            try:
                companies |= partner._get_whatsapp_available_companies()
            except Exception:
                _logger.exception(
                    "Error obteniendo empresas WhatsApp para partner %s",
                    partner.id,
                )

        # ------------------------------------------------------
        # Fallback directo
        # ------------------------------------------------------
        if "whatsapp_company_ids" in partner._fields:
            companies |= partner.whatsapp_company_ids.filtered(
                lambda company: company.is_company
            )

        # ------------------------------------------------------
        # Empresa padre
        # ------------------------------------------------------
        if partner.parent_id and partner.parent_id.is_company:
            companies |= partner.parent_id

        # ------------------------------------------------------
        # El propio partner si es empresa
        # ------------------------------------------------------
        if partner.is_company:
            companies |= partner

        # Solo empresas reales
        companies = companies.filtered(lambda company: company.is_company)

        return companies

    def _get_portal_active_company(self):
        """
        Obtiene la empresa actualmente seleccionada en el portal.

        Orden:
        1. company_id enviado en URL/querystring.
        2. Empresa guardada en la sesión.
        3. whatsapp_active_company_id.
        4. commercial_partner_id.
        5. Primera empresa autorizada.

        Nunca acepta una empresa que no pertenezca al conjunto
        de empresas autorizadas.
        """
        partner = self._get_portal_user_partner()
        allowed_companies = self._get_portal_allowed_companies()

        if not allowed_companies:
            return request.env["res.partner"].sudo().browse()

        allowed_ids = allowed_companies.ids

        # ------------------------------------------------------
        # 1. Empresa enviada mediante parámetro
        # ------------------------------------------------------
        requested_company_id = request.params.get("company_id")

        if requested_company_id:
            try:
                requested_company_id = int(requested_company_id)
            except (TypeError, ValueError):
                requested_company_id = False

            if requested_company_id in allowed_ids:
                request.session["portal_active_company_id"] = (
                    requested_company_id
                )

        # ------------------------------------------------------
        # 2. Empresa guardada en sesión
        # ------------------------------------------------------
        session_company_id = request.session.get(
            "portal_active_company_id"
        )

        try:
            session_company_id = int(session_company_id or 0)
        except (TypeError, ValueError):
            session_company_id = 0

        if session_company_id in allowed_ids:
            return allowed_companies.filtered(
                lambda company: company.id == session_company_id
            )[:1]

        # ------------------------------------------------------
        # 3. Empresa activa de WhatsApp como valor inicial
        # ------------------------------------------------------
        whatsapp_active_company = False

        if "whatsapp_active_company_id" in partner._fields:
            whatsapp_active_company = (
                partner.whatsapp_active_company_id
            )

        if (
            whatsapp_active_company
            and whatsapp_active_company.id in allowed_ids
        ):
            request.session["portal_active_company_id"] = (
                whatsapp_active_company.id
            )
            return whatsapp_active_company

        # ------------------------------------------------------
        # 4. Empresa comercial principal
        # ------------------------------------------------------
        commercial_partner = partner.commercial_partner_id

        if commercial_partner.id in allowed_ids:
            request.session["portal_active_company_id"] = (
                commercial_partner.id
            )
            return commercial_partner

        # ------------------------------------------------------
        # 5. Primera empresa disponible
        # ------------------------------------------------------
        company = allowed_companies[:1]

        if company:
            request.session["portal_active_company_id"] = company.id

        return company

    def _prepare_portal_company_values(self):
        """
        Variables disponibles para las vistas QWeb del portal.
        """
        companies = self._get_portal_allowed_companies()
        active_company = self._get_portal_active_company()

        return {
            "portal_allowed_companies": companies,
            "portal_active_company": active_company,
            "portal_has_multiple_companies": len(companies) > 1,
            "portal_company_count": len(companies),
        }

    def _partner_belongs_to_allowed_company(
        self,
        partner,
        allowed_companies=None,
    ):
        """
        Comprueba si un partner pertenece a alguna empresa
        permitida del usuario portal.

        Considera tanto el partner directamente como su
        commercial_partner_id.
        """
        if not partner:
            return False

        if allowed_companies is None:
            allowed_companies = (
                self._get_portal_allowed_companies()
            )

        allowed_ids = set(allowed_companies.ids)

        if partner.id in allowed_ids:
            return True

        commercial_partner = partner.commercial_partner_id

        if (
            commercial_partner
            and commercial_partner.id in allowed_ids
        ):
            return True

        return False

    # ==========================================================
    # CAMBIAR EMPRESA ACTIVA
    # ==========================================================

    @http.route(
        ["/my/company/<int:company_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_switch_company(
        self,
        company_id,
        redirect=None,
        **kw,
    ):
        """
        Cambia la empresa activa solamente para la sesión
        actual del portal.

        NO modifica whatsapp_active_company_id.
        """
        allowed_companies = (
            self._get_portal_allowed_companies()
        )

        if company_id not in allowed_companies.ids:
            _logger.warning(
                "Intento de seleccionar empresa no autorizada. "
                "Usuario=%s Partner=%s Empresa=%s",
                request.env.user.id,
                request.env.user.partner_id.id,
                company_id,
            )

            return request.redirect("/my")

        request.session["portal_active_company_id"] = company_id

        _logger.info(
            "Portal: usuario %s cambió a empresa ID %s",
            request.env.user.name,
            company_id,
        )

        # Evitar redirecciones externas
        if (
            redirect
            and isinstance(redirect, str)
            and redirect.startswith("/my")
            and not redirect.startswith("//")
        ):
            return request.redirect(redirect)

        return request.redirect("/my")

    # ==========================================================
    # PORTAL HOME
    # ==========================================================

    def _prepare_home_portal_values(self, counters):
        """
        Agregar contadores de equipos y tickets
        correspondientes a la empresa activa.
        """
        values = super()._prepare_home_portal_values(counters)

        company_values = self._prepare_portal_company_values()
        values.update(company_values)

        active_company = company_values[
            "portal_active_company"
        ]

        if not active_company:
            if "equipo_count" in counters:
                values["equipo_count"] = 0

            if "ticket_count" in counters:
                values["ticket_count"] = 0

            return values

        # IMPORTANTE:
        # sudo() se usa después de validar que active_company
        # pertenece a las empresas permitidas.
        Alquiler = request.env["alquiler"].sudo()
        Ticket = request.env["ticket.alquiler"].sudo()

        if "equipo_count" in counters:
            values["equipo_count"] = Alquiler.search_count(
                [
                    (
                        "cliente_id",
                        "child_of",
                        active_company.id,
                    )
                ]
            )

        if "ticket_count" in counters:
            values["ticket_count"] = Ticket.search_count(
                [
                    (
                        "partner_id",
                        "child_of",
                        active_company.id,
                    )
                ]
            )

        return values

    # ==========================================================
    # PORTAL LAYOUT
    # ==========================================================

    def _prepare_portal_layout_values(self):
        """
        Preparar valores globales del portal.
        """
        values = super()._prepare_portal_layout_values()

        company_values = self._prepare_portal_company_values()
        values.update(company_values)

        active_company = company_values[
            "portal_active_company"
        ]

        if not active_company:
            values.update(
                {
                    "equipo_count": 0,
                    "ticket_count": 0,
                }
            )

            return values

        Alquiler = request.env["alquiler"].sudo()
        Ticket = request.env["ticket.alquiler"].sudo()

        values.update(
            {
                "equipo_count": Alquiler.search_count(
                    [
                        (
                            "cliente_id",
                            "child_of",
                            active_company.id,
                        )
                    ]
                ),
                "ticket_count": Ticket.search_count(
                    [
                        (
                            "partner_id",
                            "child_of",
                            active_company.id,
                        )
                    ]
                ),
            }
        )

        return values

    # ==========================================================
    # EQUIPOS
    # ==========================================================

    @http.route(
        [
            "/my/equipos",
            "/my/equipos/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_equipos(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="all",
        **kw,
    ):
        """
        Lista de equipos de la empresa actualmente
        seleccionada en el portal.
        """
        values = self._prepare_portal_layout_values()

        active_company = values.get(
            "portal_active_company"
        )

        if not active_company:
            return request.render(
                "sat.portal_my_equipos",
                {
                    **values,
                    "equipos": request.env[
                        "alquiler"
                    ].browse(),
                    "page_name": "equipo",
                    "equipo_count": 0,
                },
            )

        Alquiler = request.env["alquiler"].sudo()

        # ------------------------------------------------------
        # Dominio principal
        # ------------------------------------------------------
        domain = [
            (
                "cliente_id",
                "child_of",
                active_company.id,
            ),
            (
                "estado_alquiler_id",
                "=",
                "alquilada",
            ),
        ]

        _logger.info(
            "Portal Equipos - Usuario: %s - Empresa activa: "
            "%s (ID %s)",
            request.env.user.name,
            active_company.name,
            active_company.id,
        )

        # ------------------------------------------------------
        # Ordenamientos
        # ------------------------------------------------------
        searchbar_sortings = {
            "date": {
                "label": _("Fecha más reciente"),
                "order": "create_date desc",
            },
            "name": {
                "label": _("Modelo"),
                "order": "name",
            },
            "serie": {
                "label": _("Serie"),
                "order": "serie",
            },
            "estado": {
                "label": _("Estado"),
                "order": "estado_alquiler_id",
            },
        }

        # ------------------------------------------------------
        # Filtros
        # ------------------------------------------------------
        searchbar_filters = {
            "all": {
                "label": _("Todos"),
                "domain": [],
            },
            "alquilada": {
                "label": _("Alquilados"),
                "domain": [
                    (
                        "estado_alquiler_id",
                        "=",
                        "alquilada",
                    )
                ],
            },
            "lista": {
                "label": _("Listos"),
                "domain": [
                    (
                        "estado_alquiler_id",
                        "=",
                        "lista",
                    )
                ],
            },
            "con_problemas": {
                "label": _("Con Problemas"),
                "domain": [
                    (
                        "estado_alquiler_id",
                        "=",
                        "con_problemas",
                    )
                ],
            },
        }

        # ------------------------------------------------------
        # Búsqueda
        # ------------------------------------------------------
        searchbar_inputs = {
            "all": {
                "input": "all",
                "label": _("Buscar en Todo"),
            },
            "serie": {
                "input": "serie",
                "label": _("Buscar por Serie"),
            },
            "modelo": {
                "input": "modelo",
                "label": _("Buscar por Modelo"),
            },
        }

        if not sortby or sortby not in searchbar_sortings:
            sortby = "date"

        if not filterby or filterby not in searchbar_filters:
            filterby = "all"

        if (
            not search_in
            or search_in not in searchbar_inputs
        ):
            search_in = "all"

        order = searchbar_sortings[sortby]["order"]

        domain = expression.AND(
            [
                domain,
                searchbar_filters[filterby]["domain"],
            ]
        )

        # ------------------------------------------------------
        # Texto de búsqueda
        # ------------------------------------------------------
        if search:
            search_domains = []

            if search_in in ("all", "serie"):
                search_domains.append(
                    [
                        (
                            "serie",
                            "ilike",
                            search,
                        )
                    ]
                )

            if search_in in ("all", "modelo"):
                search_domains.append(
                    [
                        (
                            "name.name",
                            "ilike",
                            search,
                        )
                    ]
                )

            if search_domains:
                domain = expression.AND(
                    [
                        domain,
                        expression.OR(
                            search_domains
                        ),
                    ]
                )

        # ------------------------------------------------------
        # Conteo
        # ------------------------------------------------------
        equipo_count = Alquiler.search_count(domain)

        _logger.info(
            "Portal Equipos - encontrados: %s - Empresa: %s",
            equipo_count,
            active_company.name,
        )

        # ------------------------------------------------------
        # Paginación
        # ------------------------------------------------------
        pager = portal_pager(
            url="/my/equipos",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
                "company_id": active_company.id,
            },
            total=equipo_count,
            page=page,
            step=self._items_per_page,
        )

        # ------------------------------------------------------
        # Equipos
        # ------------------------------------------------------
        equipos = Alquiler.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )

        values.update(
            {
                "date": date_begin,
                "equipos": equipos,
                "page_name": "equipo",
                "default_url": "/my/equipos",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_filters": OrderedDict(
                    sorted(
                        searchbar_filters.items()
                    )
                ),
                "searchbar_inputs": searchbar_inputs,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
                "equipo_count": equipo_count,
            }
        )

        return request.render(
            "sat.portal_my_equipos",
            values,
        )

    # ==========================================================
    # DETALLE EQUIPO
    # ==========================================================

    @http.route(
        ["/my/equipo/<int:equipo_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_equipo_detail(
        self,
        equipo_id,
        access_token=None,
        **kw,
    ):
        """
        Detalle de equipo.

        Se permite acceso si el equipo pertenece a cualquiera
        de las empresas autorizadas del usuario.
        """
        allowed_companies = (
            self._get_portal_allowed_companies()
        )

        equipo_sudo = (
            request.env["alquiler"]
            .sudo()
            .browse(equipo_id)
            .exists()
        )

        if not equipo_sudo:
            return request.redirect("/my/equipos")

        cliente = equipo_sudo.cliente_id

        if not self._partner_belongs_to_allowed_company(
            cliente,
            allowed_companies,
        ):
            _logger.warning(
                "ACCESO DENEGADO EQUIPO - Usuario=%s "
                "Partner=%s Equipo=%s Cliente=%s",
                request.env.user.name,
                request.env.user.partner_id.id,
                equipo_id,
                cliente.id if cliente else False,
            )

            return request.redirect("/my/equipos")

        # Empresa real propietaria del equipo
        equipment_company = cliente.commercial_partner_id

        _logger.info(
            "ACCESO PERMITIDO EQUIPO - Usuario=%s "
            "Equipo=%s Empresa=%s",
            request.env.user.name,
            equipo_sudo.serie,
            equipment_company.name,
        )

        # ------------------------------------------------------
        # Tickets del equipo
        # ------------------------------------------------------
        tickets = (
            request.env["ticket.alquiler"]
            .sudo()
            .search(
                [
                    (
                        "product_alquiler",
                        "=",
                        equipo_id,
                    ),
                    (
                        "partner_id",
                        "child_of",
                        equipment_company.id,
                    ),
                ],
                order="create_date desc",
                limit=10,
            )
        )

        # ------------------------------------------------------
        # Pedidos relacionados
        # ------------------------------------------------------
        pedidos = (
            request.env["sale.order"]
            .sudo()
            .search(
                [
                    (
                        "equipo_id",
                        "=",
                        equipo_id,
                    ),
                    (
                        "partner_id",
                        "child_of",
                        equipment_company.id,
                    ),
                ],
                order="create_date desc",
                limit=5,
            )
        )

        company_values = (
            self._prepare_portal_company_values()
        )

        values = {
            **company_values,
            "equipo": equipo_sudo,
            "tickets": tickets,
            "pedidos": pedidos,
            "page_name": "equipo_detail",
            "user": request.env.user,
        }

        return request.render(
            "sat.portal_equipo_detail",
            values,
        )

    # ==========================================================
    # TICKETS
    # ==========================================================

    @http.route(
        [
            "/my/tickets",
            "/my/tickets/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tickets(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        **kw,
    ):
        """
        Lista de tickets de la empresa actualmente activa.
        """
        values = self._prepare_portal_layout_values()

        active_company = values.get(
            "portal_active_company"
        )

        if not active_company:
            return request.render(
                "sat.portal_my_tickets",
                {
                    **values,
                    "tickets": request.env[
                        "ticket.alquiler"
                    ].browse(),
                    "page_name": "ticket",
                    "ticket_count": 0,
                },
            )

        Ticket = request.env["ticket.alquiler"].sudo()

        # ------------------------------------------------------
        # Dominio
        # ------------------------------------------------------
        domain = [
            (
                "partner_id",
                "child_of",
                active_company.id,
            )
        ]

        _logger.info(
            "Portal Tickets - Usuario=%s Empresa=%s ID=%s",
            request.env.user.name,
            active_company.name,
            active_company.id,
        )

        # ------------------------------------------------------
        # Ordenamientos
        # ------------------------------------------------------
        searchbar_sortings = {
            "date": {
                "label": _("Fecha más reciente"),
                "order": "create_date desc",
            },
            "name": {
                "label": _("Número"),
                "order": "name",
            },
            "estado": {
                "label": _("Estado"),
                "order": "estado",
            },
            "agenda": {
                "label": _("Fecha de visita"),
                "order": "agenda desc",
            },
        }

        # ------------------------------------------------------
        # Filtros
        # ------------------------------------------------------
        searchbar_filters = {
            "all": {
                "label": _("Todos"),
                "domain": [],
            },
            "nuevo": {
                "label": _("Nuevos"),
                "domain": [
                    (
                        "estado",
                        "=",
                        "nuevo",
                    )
                ],
            },
            "proceso": {
                "label": _("En Proceso"),
                "domain": [
                    (
                        "estado",
                        "=",
                        "proceso",
                    )
                ],
            },
            "finalizado": {
                "label": _("Finalizados"),
                "domain": [
                    (
                        "estado",
                        "=",
                        "finalizado",
                    )
                ],
            },
        }

        if not sortby or sortby not in searchbar_sortings:
            sortby = "date"

        if not filterby or filterby not in searchbar_filters:
            filterby = "all"

        order = searchbar_sortings[sortby]["order"]

        domain = expression.AND(
            [
                domain,
                searchbar_filters[filterby]["domain"],
            ]
        )

        # ------------------------------------------------------
        # Búsqueda
        # ------------------------------------------------------
        if search:
            domain = expression.AND(
                [
                    domain,
                    expression.OR(
                        [
                            [
                                (
                                    "name",
                                    "ilike",
                                    search,
                                )
                            ],
                            [
                                (
                                    "serie_id_r",
                                    "ilike",
                                    search,
                                )
                            ],
                        ]
                    ),
                ]
            )

        # ------------------------------------------------------
        # Conteo
        # ------------------------------------------------------
        ticket_count = Ticket.search_count(domain)

        _logger.info(
            "Portal Tickets encontrados=%s Empresa=%s",
            ticket_count,
            active_company.name,
        )

        # ------------------------------------------------------
        # Paginación
        # ------------------------------------------------------
        pager = portal_pager(
            url="/my/tickets",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search": search,
                "company_id": active_company.id,
            },
            total=ticket_count,
            page=page,
            step=self._items_per_page,
        )

        tickets = Ticket.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )

        values.update(
            {
                "date": date_begin,
                "tickets": tickets,
                "page_name": "ticket",
                "default_url": "/my/tickets",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_filters": OrderedDict(
                    sorted(
                        searchbar_filters.items()
                    )
                ),
                "sortby": sortby,
                "filterby": filterby,
                "search": search,
                "ticket_count": ticket_count,
            }
        )

        return request.render(
            "sat.portal_my_tickets",
            values,
        )

    # ==========================================================
    # DETALLE TICKET
    # ==========================================================

    @http.route(
        ["/my/ticket/<int:ticket_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_ticket_detail(
        self,
        ticket_id,
        access_token=None,
        **kw,
    ):
        """
        Detalle del ticket.

        Se valida contra todas las empresas autorizadas
        mediante whatsapp_company_ids + empresa principal.
        """
        allowed_companies = (
            self._get_portal_allowed_companies()
        )

        ticket_sudo = (
            request.env["ticket.alquiler"]
            .sudo()
            .browse(ticket_id)
            .exists()
        )

        if not ticket_sudo:
            return request.redirect("/my/tickets")

        ticket_partner = ticket_sudo.partner_id

        if not self._partner_belongs_to_allowed_company(
            ticket_partner,
            allowed_companies,
        ):
            _logger.warning(
                "ACCESO DENEGADO TICKET - Usuario=%s "
                "Partner usuario=%s Ticket=%s "
                "Cliente=%s",
                request.env.user.name,
                request.env.user.partner_id.id,
                ticket_id,
                (
                    ticket_partner.id
                    if ticket_partner
                    else False
                ),
            )

            return request.redirect("/my/tickets")

        _logger.info(
            "ACCESO PERMITIDO TICKET - Usuario=%s "
            "Ticket=%s Empresa=%s",
            request.env.user.name,
            ticket_sudo.name,
            ticket_partner.commercial_partner_id.name,
        )

        company_values = (
            self._prepare_portal_company_values()
        )

        values = {
            **company_values,
            "ticket": ticket_sudo,
            "page_name": "ticket_detail",
            "user": request.env.user,
        }

        return request.render(
            "sat.portal_ticket_detail",
            values,
        )
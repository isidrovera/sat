# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from collections import OrderedDict
from operator import itemgetter
import logging


_logger = logging.getLogger(__name__)


class PortalAlquiler(CustomerPortal):

    # ==========================================================
    # EMPRESAS AUTORIZADAS
    # ==========================================================

    def _get_portal_company_ids(self):
        """
        Devuelve las empresas que puede gestionar el usuario portal.

        Incluye:
        1. La empresa principal original del portal
           (commercial_partner_id).
        2. Las empresas agregadas en whatsapp_company_ids.

        No cambia ninguna lógica del portal.
        No usa sudo.
        No guarda nada en sesión.
        """

        user_partner = request.env.user.partner_id

        # Empresa que utilizaba originalmente el portal
        main_partner = user_partner.commercial_partner_id

        company_ids = []

        if main_partner:
            company_ids.append(main_partner.id)

        # Empresas adicionales autorizadas
        if "whatsapp_company_ids" in user_partner._fields:
            company_ids += user_partner.whatsapp_company_ids.ids

        # Evitar IDs repetidos
        company_ids = list(dict.fromkeys(company_ids))

        _logger.info(
            "Portal empresas autorizadas - Usuario: %s - "
            "Partner principal: %s (%s) - IDs permitidos: %s",
            request.env.user.name,
            main_partner.name if main_partner else False,
            main_partner.id if main_partner else False,
            company_ids,
        )

        return company_ids

    # ==========================================================
    # HOME PORTAL
    # ==========================================================

    def _prepare_home_portal_values(self, counters):
        """
        Agregar contadores de equipos y tickets al portal home.
        """

        values = super()._prepare_home_portal_values(counters)

        company_ids = self._get_portal_company_ids()

        if "equipo_count" in counters:

            if company_ids:
                values["equipo_count"] = request.env["alquiler"].search_count([
                    ("cliente_id", "in", company_ids)
                ])
            else:
                values["equipo_count"] = 0

        if "ticket_count" in counters:

            if company_ids:
                values["ticket_count"] = request.env["ticket.alquiler"].search_count([
                    ("partner_id", "in", company_ids)
                ])
            else:
                values["ticket_count"] = 0

        return values

    # ==========================================================
    # LAYOUT PORTAL
    # ==========================================================

    def _prepare_portal_layout_values(self):
        """
        Preparar valores base del layout del portal.
        """

        values = super()._prepare_portal_layout_values()

        company_ids = self._get_portal_company_ids()

        if company_ids:

            values.update({
                "equipo_count": request.env["alquiler"].search_count([
                    ("cliente_id", "in", company_ids)
                ]),

                "ticket_count": request.env["ticket.alquiler"].search_count([
                    ("partner_id", "in", company_ids)
                ]),
            })

        else:

            values.update({
                "equipo_count": 0,
                "ticket_count": 0,
            })

        return values

    # ==========================================================
    # EQUIPOS
    # ==========================================================

    @http.route(
        ["/my/equipos", "/my/equipos/page/<int:page>"],
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
        Lista de equipos del cliente autenticado.

        Incluye:
        - empresa principal;
        - empresas agregadas en whatsapp_company_ids.
        """

        values = self._prepare_portal_layout_values()

        company_ids = self._get_portal_company_ids()

        Alquiler = request.env["alquiler"]

        domain = [
            ("cliente_id", "in", company_ids),
            ("estado_alquiler_id", "=", "alquilada"),
        ]

        _logger.info(
            "🔍 Portal Equipos - Usuario: %s - Empresas IDs: %s",
            request.env.user.name,
            company_ids,
        )

        _logger.info(
            "🔍 Dominio de búsqueda: %s",
            domain,
        )

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

        searchbar_filters = {
            "all": {
                "label": _("Todos"),
                "domain": [],
            },
            "alquilada": {
                "label": _("Alquilados"),
                "domain": [
                    ("estado_alquiler_id", "=", "alquilada")
                ],
            },
            "lista": {
                "label": _("Listos"),
                "domain": [
                    ("estado_alquiler_id", "=", "lista")
                ],
            },
            "con_problemas": {
                "label": _("Con Problemas"),
                "domain": [
                    ("estado_alquiler_id", "=", "con_problemas")
                ],
            },
        }

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

        if not sortby:
            sortby = "date"

        if not filterby:
            filterby = "all"

        order = searchbar_sortings[sortby]["order"]

        domain += searchbar_filters[filterby]["domain"]

        if search and search_in:

            search_domain = []

            if search_in in ("all", "serie"):
                search_domain = [
                    "|",
                    ("serie", "ilike", search),
                ]

            if search_in in ("all", "modelo"):
                search_domain += [
                    "|",
                    ("name.name", "ilike", search),
                ]

            if search_domain:
                domain += search_domain

        equipo_count = Alquiler.search_count(domain)

        _logger.info(
            "📊 Total equipos encontrados: %s",
            equipo_count,
        )

        pager = portal_pager(
            url="/my/equipos",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=equipo_count,
            page=page,
            step=self._items_per_page,
        )

        equipos = Alquiler.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )

        values.update({
            "date": date_begin,
            "equipos": equipos,
            "page_name": "equipo",
            "default_url": "/my/equipos",
            "pager": pager,
            "searchbar_sortings": searchbar_sortings,
            "searchbar_filters": OrderedDict(
                sorted(searchbar_filters.items())
            ),
            "searchbar_inputs": searchbar_inputs,
            "sortby": sortby,
            "filterby": filterby,
            "search_in": search_in,
            "search": search,
        })

        return request.render(
            "sat.portal_my_equipos",
            values,
        )

    # ==========================================================
    # DETALLE DE EQUIPO
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
        Detalle de un equipo específico.
        """

        try:
            equipo_sudo = self._document_check_access(
                "alquiler",
                equipo_id,
                access_token,
            )

        except (AccessError, MissingError):
            return request.redirect("/my")

        company_ids = self._get_portal_company_ids()

        # ======================================================
        # VALIDAR EMPRESA
        # ======================================================

        if equipo_sudo.cliente_id.id not in company_ids:

            _logger.warning(
                "⚠️ Acceso denegado - Usuario: %s - "
                "Equipo: %s - Cliente: %s (%s) - "
                "Empresas permitidas: %s",
                request.env.user.name,
                equipo_sudo.serie,
                equipo_sudo.cliente_id.name,
                equipo_sudo.cliente_id.id,
                company_ids,
            )

            return request.redirect("/my")

        _logger.info(
            "✅ Acceso permitido - Equipo: %s - Cliente: %s",
            equipo_sudo.serie,
            equipo_sudo.cliente_id.name,
        )

        # ======================================================
        # IMPORTANTE:
        # usar la empresa REAL del equipo
        # ======================================================

        equipo_partner = equipo_sudo.cliente_id

        tickets = request.env["ticket.alquiler"].search([
            ("product_alquiler", "=", equipo_id),
            ("partner_id", "=", equipo_partner.id),
        ], order="create_date desc", limit=10)

        pedidos = request.env["sale.order"].search([
            ("equipo_id", "=", equipo_id),
            ("partner_id", "=", equipo_partner.id),
        ], order="create_date desc", limit=5)

        values = {
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
        ["/my/tickets", "/my/tickets/page/<int:page>"],
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
        Lista de tickets del cliente autenticado.

        Incluye:
        - empresa principal;
        - empresas agregadas en whatsapp_company_ids.
        """

        values = self._prepare_portal_layout_values()

        company_ids = self._get_portal_company_ids()

        Ticket = request.env["ticket.alquiler"]

        domain = [
            ("partner_id", "in", company_ids)
        ]

        _logger.info(
            "🎫 Portal Tickets - Usuario: %s - "
            "Empresas IDs: %s",
            request.env.user.name,
            company_ids,
        )

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

        searchbar_filters = {
            "all": {
                "label": _("Todos"),
                "domain": [],
            },
            "nuevo": {
                "label": _("Nuevos"),
                "domain": [
                    ("estado", "=", "nuevo")
                ],
            },
            "proceso": {
                "label": _("En Proceso"),
                "domain": [
                    ("estado", "=", "proceso")
                ],
            },
            "finalizado": {
                "label": _("Finalizados"),
                "domain": [
                    ("estado", "=", "finalizado")
                ],
            },
        }

        if not sortby:
            sortby = "date"

        if not filterby:
            filterby = "all"

        order = searchbar_sortings[sortby]["order"]

        domain += searchbar_filters[filterby]["domain"]

        if search:
            domain += [
                "|",
                ("name", "ilike", search),
                ("serie_id_r", "ilike", search),
            ]

        ticket_count = Ticket.search_count(domain)

        _logger.info(
            "📊 Total tickets encontrados: %s",
            ticket_count,
        )

        pager = portal_pager(
            url="/my/tickets",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search": search,
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

        values.update({
            "date": date_begin,
            "tickets": tickets,
            "page_name": "ticket",
            "default_url": "/my/tickets",
            "pager": pager,
            "searchbar_sortings": searchbar_sortings,
            "searchbar_filters": OrderedDict(
                sorted(searchbar_filters.items())
            ),
            "sortby": sortby,
            "filterby": filterby,
            "search": search,
        })

        return request.render(
            "sat.portal_my_tickets",
            values,
        )

    # ==========================================================
    # DETALLE DE TICKET
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
        Detalle de un ticket específico.
        """

        try:
            ticket_sudo = self._document_check_access(
                "ticket.alquiler",
                ticket_id,
                access_token,
            )

        except (AccessError, MissingError):
            return request.redirect("/my")

        company_ids = self._get_portal_company_ids()

        # ======================================================
        # VALIDAR QUE EL TICKET SEA DE UNA EMPRESA AUTORIZADA
        # ======================================================

        if ticket_sudo.partner_id.id not in company_ids:

            _logger.warning(
                "⚠️ Acceso denegado a ticket - "
                "Usuario: %s - "
                "Ticket: %s - "
                "Cliente: %s (%s) - "
                "Empresas permitidas: %s",
                request.env.user.name,
                ticket_sudo.name,
                ticket_sudo.partner_id.name,
                ticket_sudo.partner_id.id,
                company_ids,
            )

            return request.redirect("/my")

        _logger.info(
            "✅ Acceso permitido a ticket - "
            "Usuario: %s - Ticket: %s - Cliente: %s",
            request.env.user.name,
            ticket_sudo.name,
            ticket_sudo.partner_id.name,
        )

        values = {
            "ticket": ticket_sudo,
            "page_name": "ticket_detail",
            "user": request.env.user,
        }

        return request.render(
            "sat.portal_ticket_detail",
            values,
        )
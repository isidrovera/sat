# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import (
    CustomerPortal,
    pager as portal_pager,
)
from collections import OrderedDict
import logging


_logger = logging.getLogger(__name__)


class PortalAlquiler(CustomerPortal):

    # ==========================================================
    # EMPRESAS AUTORIZADAS DEL PORTAL
    # ==========================================================

    def _get_portal_allowed_companies(self):
        """
        Obtiene todas las empresas que el usuario portal
        está autorizado a gestionar.

        Incluye:
        1. Empresa principal del usuario.
        2. Empresas agregadas en whatsapp_company_ids.

        No modifica ninguna empresa activa.
        No guarda nada en sesión.
        """

        user_partner = request.env.user.partner_id.sudo()

        Partner = request.env["res.partner"].sudo()
        companies = Partner.browse()

        # ------------------------------------------------------
        # Empresa principal del usuario
        # ------------------------------------------------------
        commercial_partner = user_partner.commercial_partner_id

        if commercial_partner and commercial_partner.is_company:
            companies |= commercial_partner

        # ------------------------------------------------------
        # Empresas adicionales configuradas en WhatsApp
        # ------------------------------------------------------
        if "whatsapp_company_ids" in user_partner._fields:
            companies |= user_partner.whatsapp_company_ids.filtered(
                lambda company: company.is_company
            )

        # ------------------------------------------------------
        # Evitar registros que no sean empresas
        # ------------------------------------------------------
        companies = companies.filtered(
            lambda company: company.is_company
        )

        _logger.info(
            "Portal multiempresa - Usuario: %s - Partner: %s - "
            "Empresas permitidas: %s",
            request.env.user.name,
            user_partner.name,
            [
                "%s (%s)" % (company.name, company.id)
                for company in companies
            ],
        )

        return companies

    def _portal_partner_is_allowed(
        self,
        partner,
        allowed_companies=None,
    ):
        """
        Comprueba que un partner pertenezca a una empresa
        autorizada del usuario portal.
        """

        if not partner:
            return False

        if allowed_companies is None:
            allowed_companies = (
                self._get_portal_allowed_companies()
            )

        allowed_ids = set(allowed_companies.ids)

        # Coincidencia directa
        if partner.id in allowed_ids:
            return True

        # También comprobar empresa comercial padre
        commercial_partner = partner.commercial_partner_id

        if (
            commercial_partner
            and commercial_partner.id in allowed_ids
        ):
            return True

        return False

    # ==========================================================
    # HOME PORTAL
    # ==========================================================

    def _prepare_home_portal_values(self, counters):
        """
        Agregar contadores de equipos y tickets al portal home,
        considerando empresa principal + whatsapp_company_ids.
        """

        values = super()._prepare_home_portal_values(counters)

        companies = self._get_portal_allowed_companies()
        company_ids = companies.ids

        if not company_ids:

            if "equipo_count" in counters:
                values["equipo_count"] = 0

            if "ticket_count" in counters:
                values["ticket_count"] = 0

            return values

        if "equipo_count" in counters:
            values["equipo_count"] = (
                request.env["alquiler"]
                .sudo()
                .search_count([
                    (
                        "cliente_id",
                        "in",
                        company_ids,
                    )
                ])
            )

        if "ticket_count" in counters:
            values["ticket_count"] = (
                request.env["ticket.alquiler"]
                .sudo()
                .search_count([
                    (
                        "partner_id",
                        "in",
                        company_ids,
                    )
                ])
            )

        return values

    # ==========================================================
    # LAYOUT PORTAL
    # ==========================================================

    def _prepare_portal_layout_values(self):
        """
        Preparar valores base del layout del portal,
        considerando todas las empresas autorizadas.
        """

        values = super()._prepare_portal_layout_values()

        companies = self._get_portal_allowed_companies()
        company_ids = companies.ids

        if not company_ids:

            values.update({
                "equipo_count": 0,
                "ticket_count": 0,
            })

            return values

        values.update({

            "equipo_count": (
                request.env["alquiler"]
                .sudo()
                .search_count([
                    (
                        "cliente_id",
                        "in",
                        company_ids,
                    )
                ])
            ),

            "ticket_count": (
                request.env["ticket.alquiler"]
                .sudo()
                .search_count([
                    (
                        "partner_id",
                        "in",
                        company_ids,
                    )
                ])
            ),
        })

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
        Lista de equipos de todas las empresas autorizadas
        para el usuario portal.
        """

        values = self._prepare_portal_layout_values()

        companies = self._get_portal_allowed_companies()
        company_ids = companies.ids

        Alquiler = request.env["alquiler"].sudo()

        # ------------------------------------------------------
        # Dominio principal
        # ------------------------------------------------------

        domain = [
            (
                "cliente_id",
                "in",
                company_ids,
            ),
            (
                "estado_alquiler_id",
                "=",
                "alquilada",
            ),
        ]

        _logger.info(
            "Portal Equipos - Usuario: %s - "
            "Empresas autorizadas: %s",
            request.env.user.name,
            [
                "%s (%s)" % (c.name, c.id)
                for c in companies
            ],
        )

        _logger.info(
            "Portal Equipos - Dominio: %s",
            domain,
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
        # Campos de búsqueda
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

        # ------------------------------------------------------
        # Valores por defecto
        # ------------------------------------------------------

        if not sortby:
            sortby = "date"

        if sortby not in searchbar_sortings:
            sortby = "date"

        if not filterby:
            filterby = "all"

        if filterby not in searchbar_filters:
            filterby = "all"

        if search_in not in searchbar_inputs:
            search_in = "all"

        order = searchbar_sortings[sortby]["order"]

        # ------------------------------------------------------
        # Filtro seleccionado
        # ------------------------------------------------------

        domain += searchbar_filters[filterby]["domain"]

        # ------------------------------------------------------
        # Búsqueda
        # ------------------------------------------------------

        if search and search_in:

            if search_in == "serie":

                domain += [
                    (
                        "serie",
                        "ilike",
                        search,
                    )
                ]

            elif search_in == "modelo":

                domain += [
                    (
                        "name.name",
                        "ilike",
                        search,
                    )
                ]

            else:

                domain += [
                    "|",
                    (
                        "serie",
                        "ilike",
                        search,
                    ),
                    (
                        "name.name",
                        "ilike",
                        search,
                    ),
                ]

        # ------------------------------------------------------
        # Conteo
        # ------------------------------------------------------

        equipo_count = Alquiler.search_count(domain)

        _logger.info(
            "Portal Equipos - Total encontrados: %s",
            equipo_count,
        )

        # ------------------------------------------------------
        # Paginador
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
            },

            total=equipo_count,

            page=page,

            step=self._items_per_page,
        )

        # ------------------------------------------------------
        # Buscar equipos
        # ------------------------------------------------------

        equipos = Alquiler.search(

            domain,

            order=order,

            limit=self._items_per_page,

            offset=pager["offset"],
        )

        # ------------------------------------------------------
        # Valores QWeb
        # ------------------------------------------------------

        values.update({

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

            # Empresas permitidas disponibles para QWeb,
            # por si luego quieres mostrar el nombre.
            "portal_allowed_companies": companies,
        })

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
        Detalle de un equipo.

        Permite acceso si pertenece a:
        - empresa principal;
        - cualquier empresa de whatsapp_company_ids.
        """

        companies = self._get_portal_allowed_companies()

        # ------------------------------------------------------
        # Obtener equipo
        # ------------------------------------------------------

        equipo_sudo = (
            request.env["alquiler"]
            .sudo()
            .browse(equipo_id)
            .exists()
        )

        if not equipo_sudo:

            _logger.warning(
                "Portal - Equipo inexistente ID %s",
                equipo_id,
            )

            return request.redirect(
                "/my/equipos"
            )

        # ------------------------------------------------------
        # Seguridad
        # ------------------------------------------------------

        if not self._portal_partner_is_allowed(
            equipo_sudo.cliente_id,
            companies,
        ):

            _logger.warning(
                "ACCESO DENEGADO EQUIPO - "
                "Usuario: %s - "
                "Equipo: %s - "
                "Cliente: %s - "
                "Empresas autorizadas: %s",
                request.env.user.name,
                equipo_id,
                equipo_sudo.cliente_id.name,
                companies.ids,
            )

            return request.redirect(
                "/my/equipos"
            )

        _logger.info(
            "ACCESO PERMITIDO EQUIPO - "
            "Usuario: %s - "
            "Equipo: %s - "
            "Cliente: %s",
            request.env.user.name,
            equipo_sudo.serie,
            equipo_sudo.cliente_id.name,
        )

        # ------------------------------------------------------
        # Empresa correspondiente al equipo
        # ------------------------------------------------------

        equipo_partner = (
            equipo_sudo.cliente_id.commercial_partner_id
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
                        "=",
                        equipo_partner.id,
                    ),
                ],
                order="create_date desc",
                limit=10,
            )
        )

        # ------------------------------------------------------
        # Pedidos del equipo
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
                        "=",
                        equipo_partner.id,
                    ),
                ],
                order="create_date desc",
                limit=5,
            )
        )

        # ------------------------------------------------------
        # QWeb
        # ------------------------------------------------------

        values = {

            "equipo": equipo_sudo,

            "tickets": tickets,

            "pedidos": pedidos,

            "page_name": "equipo_detail",

            "user": request.env.user,

            "portal_allowed_companies": companies,
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
        Lista de tickets de todas las empresas autorizadas.
        """

        values = self._prepare_portal_layout_values()

        companies = self._get_portal_allowed_companies()
        company_ids = companies.ids

        Ticket = request.env[
            "ticket.alquiler"
        ].sudo()

        # ------------------------------------------------------
        # Dominio principal
        # ------------------------------------------------------

        domain = [
            (
                "partner_id",
                "in",
                company_ids,
            )
        ]

        _logger.info(
            "Portal Tickets - Usuario: %s - "
            "Empresas permitidas: %s",
            request.env.user.name,
            [
                "%s (%s)" % (c.name, c.id)
                for c in companies
            ],
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

        # ------------------------------------------------------
        # Valores por defecto
        # ------------------------------------------------------

        if not sortby:
            sortby = "date"

        if sortby not in searchbar_sortings:
            sortby = "date"

        if not filterby:
            filterby = "all"

        if filterby not in searchbar_filters:
            filterby = "all"

        order = searchbar_sortings[
            sortby
        ]["order"]

        # ------------------------------------------------------
        # Filtro
        # ------------------------------------------------------

        domain += searchbar_filters[
            filterby
        ]["domain"]

        # ------------------------------------------------------
        # Búsqueda
        # ------------------------------------------------------

        if search:

            domain += [
                "|",
                (
                    "name",
                    "ilike",
                    search,
                ),
                (
                    "serie_id_r",
                    "ilike",
                    search,
                ),
            ]

        # ------------------------------------------------------
        # Conteo
        # ------------------------------------------------------

        ticket_count = Ticket.search_count(
            domain
        )

        _logger.info(
            "Portal Tickets - Total encontrados: %s",
            ticket_count,
        )

        # ------------------------------------------------------
        # Paginador
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # Tickets
        # ------------------------------------------------------

        tickets = Ticket.search(

            domain,

            order=order,

            limit=self._items_per_page,

            offset=pager["offset"],
        )

        # ------------------------------------------------------
        # QWeb
        # ------------------------------------------------------

        values.update({

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

            "portal_allowed_companies": companies,
        })

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
        Detalle de ticket.

        Permite acceder a tickets pertenecientes a:
        - empresa principal;
        - empresas configuradas en whatsapp_company_ids.
        """

        companies = self._get_portal_allowed_companies()

        # ------------------------------------------------------
        # Buscar ticket
        # ------------------------------------------------------

        ticket_sudo = (
            request.env["ticket.alquiler"]
            .sudo()
            .browse(ticket_id)
            .exists()
        )

        if not ticket_sudo:

            _logger.warning(
                "Portal - Ticket inexistente ID %s",
                ticket_id,
            )

            return request.redirect(
                "/my/tickets"
            )

        # ------------------------------------------------------
        # Seguridad
        # ------------------------------------------------------

        if not self._portal_partner_is_allowed(
            ticket_sudo.partner_id,
            companies,
        ):

            _logger.warning(
                "ACCESO DENEGADO TICKET - "
                "Usuario: %s - "
                "Ticket: %s - "
                "Cliente: %s - "
                "Empresas permitidas: %s",
                request.env.user.name,
                ticket_id,
                ticket_sudo.partner_id.name,
                companies.ids,
            )

            return request.redirect(
                "/my/tickets"
            )

        _logger.info(
            "ACCESO PERMITIDO TICKET - "
            "Usuario: %s - "
            "Ticket: %s - "
            "Cliente: %s",
            request.env.user.name,
            ticket_sudo.name,
            ticket_sudo.partner_id.name,
        )

        # ------------------------------------------------------
        # QWeb
        # ------------------------------------------------------

        values = {

            "ticket": ticket_sudo,

            "page_name": "ticket_detail",

            "user": request.env.user,

            "portal_allowed_companies": companies,
        }

        return request.render(
            "sat.portal_ticket_detail",
            values,
        )
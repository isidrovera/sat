# -*- coding: utf-8 -*-

from collections import OrderedDict
import logging

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


_logger = logging.getLogger(__name__)


class PortalAlquiler(CustomerPortal):

    # ==========================================================
    # EMPRESAS AUTORIZADAS DEL PORTAL
    # ==========================================================

    def _get_portal_allowed_companies(self):
        """
        Empresas que puede gestionar el usuario portal.

        Incluye SIEMPRE:
        1. La empresa principal original del usuario portal.
        2. La empresa padre directa, si existe.
        3. Todas las empresas agregadas en whatsapp_company_ids.

        No usa empresa activa ni sesión: el usuario ve los registros
        de todas sus empresas autorizadas en un mismo portal.
        """
        user_partner = request.env.user.partner_id.sudo()

        Partner = request.env["res.partner"].sudo()
        companies = Partner.browse()

        # 1. Empresa principal que ya manejaba el portal originalmente.
        main_company = user_partner.commercial_partner_id
        if main_company:
            companies |= main_company

        # 2. Empresa padre directa (normalmente coincide con commercial_partner_id,
        #    pero se conserva explícitamente para no perder el comportamiento previo).
        if user_partner.parent_id:
            companies |= user_partner.parent_id

        # 3. Empresas adicionales autorizadas desde WhatsApp.
        if "whatsapp_company_ids" in user_partner._fields:
            companies |= user_partner.whatsapp_company_ids

        _logger.info(
            "Portal multiempresa - Usuario: %s - Partner: %s (%s) - "
            "Empresa principal: %s (%s) - Empresas permitidas: %s",
            request.env.user.name,
            user_partner.name,
            user_partner.id,
            main_company.name if main_company else False,
            main_company.id if main_company else False,
            ["%s (%s)" % (company.name, company.id) for company in companies],
        )

        return companies

    def _portal_partner_is_allowed(self, partner, allowed_companies=None):
        """Comprueba si un partner pertenece a una empresa autorizada."""
        if not partner:
            return False

        if allowed_companies is None:
            allowed_companies = self._get_portal_allowed_companies()

        allowed_ids = set(allowed_companies.ids)

        # Coincidencia directa.
        if partner.id in allowed_ids:
            return True

        # Empresa comercial del partner.
        commercial_partner = partner.commercial_partner_id
        if commercial_partner and commercial_partner.id in allowed_ids:
            return True

        # Empresa padre directa.
        if partner.parent_id and partner.parent_id.id in allowed_ids:
            return True

        return False

    def _get_portal_company_values(self):
        """Valores multiempresa reutilizables por las plantillas QWeb."""
        companies = self._get_portal_allowed_companies()
        return {
            "portal_allowed_companies": companies,
            "portal_has_multiple_companies": len(companies) > 1,
            "portal_company_count": len(companies),
        }

    # ==========================================================
    # HOME PORTAL
    # ==========================================================

    def _prepare_home_portal_values(self, counters):
        """Agregar contadores de equipos y tickets al portal home."""
        values = super()._prepare_home_portal_values(counters)

        company_values = self._get_portal_company_values()
        values.update(company_values)

        company_ids = company_values["portal_allowed_companies"].ids

        if "equipo_count" in counters:
            values["equipo_count"] = (
                request.env["alquiler"].sudo().search_count([
                    ("cliente_id", "in", company_ids)
                ])
                if company_ids
                else 0
            )

        if "ticket_count" in counters:
            values["ticket_count"] = (
                request.env["ticket.alquiler"].sudo().search_count([
                    ("partner_id", "in", company_ids)
                ])
                if company_ids
                else 0
            )

        return values

    def _prepare_portal_layout_values(self):
        """Preparar valores base del layout del portal."""
        values = super()._prepare_portal_layout_values()

        company_values = self._get_portal_company_values()
        values.update(company_values)

        company_ids = company_values["portal_allowed_companies"].ids

        values.update({
            "equipo_count": (
                request.env["alquiler"].sudo().search_count([
                    ("cliente_id", "in", company_ids)
                ])
                if company_ids
                else 0
            ),
            "ticket_count": (
                request.env["ticket.alquiler"].sudo().search_count([
                    ("partner_id", "in", company_ids)
                ])
                if company_ids
                else 0
            ),
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
        """Lista de equipos de todas las empresas autorizadas."""
        values = self._prepare_portal_layout_values()

        companies = values["portal_allowed_companies"]
        company_ids = companies.ids

        Alquiler = request.env["alquiler"].sudo()

        domain = [
            ("cliente_id", "in", company_ids),
            ("estado_alquiler_id", "=", "alquilada"),
        ]

        _logger.info(
            "Portal Equipos - Usuario: %s - Empresas: %s",
            request.env.user.name,
            ["%s (%s)" % (c.name, c.id) for c in companies],
        )
        _logger.info("Portal Equipos - Dominio: %s", domain)

        searchbar_sortings = {
            "date": {"label": _("Fecha más reciente"), "order": "create_date desc"},
            "name": {"label": _("Modelo"), "order": "name"},
            "serie": {"label": _("Serie"), "order": "serie"},
            "estado": {"label": _("Estado"), "order": "estado_alquiler_id"},
        }

        searchbar_filters = {
            "all": {"label": _("Todos"), "domain": []},
            "alquilada": {
                "label": _("Alquilados"),
                "domain": [("estado_alquiler_id", "=", "alquilada")],
            },
            "lista": {
                "label": _("Listos"),
                "domain": [("estado_alquiler_id", "=", "lista")],
            },
            "con_problemas": {
                "label": _("Con Problemas"),
                "domain": [("estado_alquiler_id", "=", "con_problemas")],
            },
        }

        searchbar_inputs = {
            "all": {"input": "all", "label": _("Buscar en Todo")},
            "serie": {"input": "serie", "label": _("Buscar por Serie")},
            "modelo": {"input": "modelo", "label": _("Buscar por Modelo")},
        }

        if not sortby or sortby not in searchbar_sortings:
            sortby = "date"
        if not filterby or filterby not in searchbar_filters:
            filterby = "all"
        if not search_in or search_in not in searchbar_inputs:
            search_in = "all"

        order = searchbar_sortings[sortby]["order"]
        domain += searchbar_filters[filterby]["domain"]

        if search:
            if search_in == "serie":
                domain += [("serie", "ilike", search)]
            elif search_in == "modelo":
                domain += [("name.name", "ilike", search)]
            else:
                domain += [
                    "|",
                    ("serie", "ilike", search),
                    ("name.name", "ilike", search),
                ]

        equipo_count = Alquiler.search_count(domain)

        _logger.info("Portal Equipos - Total encontrados: %s", equipo_count)

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
            "searchbar_filters": OrderedDict(sorted(searchbar_filters.items())),
            "searchbar_inputs": searchbar_inputs,
            "sortby": sortby,
            "filterby": filterby,
            "search_in": search_in,
            "search": search,
        })

        return request.render("sat.portal_my_equipos", values)

    @http.route(
        ["/my/equipo/<int:equipo_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_equipo_detail(self, equipo_id, access_token=None, **kw):
        """Detalle de un equipo perteneciente a cualquier empresa autorizada."""
        company_values = self._get_portal_company_values()
        companies = company_values["portal_allowed_companies"]

        equipo_sudo = request.env["alquiler"].sudo().browse(equipo_id).exists()
        if not equipo_sudo:
            return request.redirect("/my/equipos")

        if not self._portal_partner_is_allowed(equipo_sudo.cliente_id, companies):
            _logger.warning(
                "Acceso denegado a equipo - Usuario: %s - Equipo: %s - Cliente: %s - Empresas: %s",
                request.env.user.name,
                equipo_id,
                equipo_sudo.cliente_id.name,
                companies.ids,
            )
            return request.redirect("/my/equipos")

        _logger.info(
            "Acceso permitido - Equipo: %s - Cliente: %s",
            equipo_sudo.serie,
            equipo_sudo.cliente_id.name,
        )

        # Se filtra por el cliente real del equipo para no mezclar información
        # de otra empresa autorizada dentro del detalle.
        equipo_company = equipo_sudo.cliente_id.commercial_partner_id

        tickets = request.env["ticket.alquiler"].sudo().search([
            ("product_alquiler", "=", equipo_id),
            ("partner_id", "=", equipo_company.id),
        ], order="create_date desc", limit=10)

        pedidos = request.env["sale.order"].sudo().search([
            ("equipo_id", "=", equipo_id),
            ("partner_id", "=", equipo_company.id),
        ], order="create_date desc", limit=5)

        values = {
            "equipo": equipo_sudo,
            "tickets": tickets,
            "pedidos": pedidos,
            "page_name": "equipo_detail",
            "user": request.env.user,
            **company_values,
        }

        return request.render("sat.portal_equipo_detail", values)

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
        """Lista de tickets de todas las empresas autorizadas."""
        values = self._prepare_portal_layout_values()

        companies = values["portal_allowed_companies"]
        company_ids = companies.ids

        Ticket = request.env["ticket.alquiler"].sudo()

        domain = [("partner_id", "in", company_ids)]

        _logger.info(
            "Portal Tickets - Usuario: %s - Empresas: %s",
            request.env.user.name,
            ["%s (%s)" % (c.name, c.id) for c in companies],
        )

        searchbar_sortings = {
            "date": {"label": _("Fecha más reciente"), "order": "create_date desc"},
            "name": {"label": _("Número"), "order": "name"},
            "estado": {"label": _("Estado"), "order": "estado"},
            "agenda": {"label": _("Fecha de visita"), "order": "agenda desc"},
        }

        searchbar_filters = {
            "all": {"label": _("Todos"), "domain": []},
            "nuevo": {"label": _("Nuevos"), "domain": [("estado", "=", "nuevo")]},
            "proceso": {"label": _("En Proceso"), "domain": [("estado", "=", "proceso")]},
            "finalizado": {"label": _("Finalizados"), "domain": [("estado", "=", "finalizado")]},
        }

        if not sortby or sortby not in searchbar_sortings:
            sortby = "date"
        if not filterby or filterby not in searchbar_filters:
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

        _logger.info("Portal Tickets - Total encontrados: %s", ticket_count)

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
            "searchbar_filters": OrderedDict(sorted(searchbar_filters.items())),
            "sortby": sortby,
            "filterby": filterby,
            "search": search,
        })

        return request.render("sat.portal_my_tickets", values)

    @http.route(
        ["/my/ticket/<int:ticket_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_ticket_detail(self, ticket_id, access_token=None, **kw):
        """Detalle de un ticket perteneciente a cualquier empresa autorizada."""
        company_values = self._get_portal_company_values()
        companies = company_values["portal_allowed_companies"]

        ticket_sudo = request.env["ticket.alquiler"].sudo().browse(ticket_id).exists()
        if not ticket_sudo:
            return request.redirect("/my/tickets")

        if not self._portal_partner_is_allowed(ticket_sudo.partner_id, companies):
            _logger.warning(
                "Acceso denegado a ticket - Usuario: %s - Ticket: %s - Cliente: %s - Empresas: %s",
                request.env.user.name,
                ticket_id,
                ticket_sudo.partner_id.name,
                companies.ids,
            )
            return request.redirect("/my/tickets")

        values = {
            "ticket": ticket_sudo,
            "page_name": "ticket_detail",
            "user": request.env.user,
            **company_values,
        }

        return request.render("sat.portal_ticket_detail", values)
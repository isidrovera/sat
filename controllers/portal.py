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
    
    def _prepare_home_portal_values(self, counters):
        """Agregar contadores de equipos y tickets al portal home"""
        values = super()._prepare_home_portal_values(counters)

        # CAMBIO: usar la empresa del usuario
        partner = request.env.user.partner_id.commercial_partner_id
        
        if 'equipo_count' in counters:
            values['equipo_count'] = request.env['alquiler'].search_count([
                ('cliente_id', '=', partner.id)
            ]) if partner else 0
            
        if 'ticket_count' in counters:
            values['ticket_count'] = request.env['ticket.alquiler'].search_count([
                ('partner_id', '=', partner.id)
            ]) if partner else 0
            
        return values
    

    def _prepare_portal_layout_values(self):
        """Preparar valores base del layout del portal"""
        values = super()._prepare_portal_layout_values()

        # CAMBIO
        partner = request.env.user.partner_id.commercial_partner_id
        
        values.update({
            'equipo_count': request.env['alquiler'].search_count([
                ('cliente_id', '=', partner.id)
            ]),
            'ticket_count': request.env['ticket.alquiler'].search_count([
                ('partner_id', '=', partner.id)
            ]),
        })
        
        return values
    

    # ========== EQUIPOS ==========
    @http.route(['/my/equipos', '/my/equipos/page/<int:page>'], 
                type='http', auth="user", website=True)
    def portal_my_equipos(self, page=1, date_begin=None, date_end=None, 
                          sortby=None, filterby=None, search=None, search_in='all', **kw):
        """Lista de equipos del cliente autenticado"""
        
        values = self._prepare_portal_layout_values()

        # CAMBIO
        partner = request.env.user.partner_id.commercial_partner_id

        Alquiler = request.env['alquiler']
        
        domain = [
            ('cliente_id', '=', partner.id),
            ('estado_alquiler_id', '=', 'alquilada')
        ]
        
        _logger.info(f"🔍 Portal Equipos - Usuario: {request.env.user.name}, Partner: {partner.name} (ID: {partner.id})")
        _logger.info(f"🔍 Dominio de búsqueda: {domain}")
        
        searchbar_sortings = {
            'date': {'label': _('Fecha más reciente'), 'order': 'create_date desc'},
            'name': {'label': _('Modelo'), 'order': 'name'},
            'serie': {'label': _('Serie'), 'order': 'serie'},
            'estado': {'label': _('Estado'), 'order': 'estado_alquiler_id'},
        }
        
        searchbar_filters = {
            'all': {'label': _('Todos'), 'domain': []},
            'alquilada': {'label': _('Alquilados'), 'domain': [('estado_alquiler_id', '=', 'alquilada')]},
            'lista': {'label': _('Listos'), 'domain': [('estado_alquiler_id', '=', 'lista')]},
            'con_problemas': {'label': _('Con Problemas'), 'domain': [('estado_alquiler_id', '=', 'con_problemas')]},
        }
        
        searchbar_inputs = {
            'all': {'input': 'all', 'label': _('Buscar en Todo')},
            'serie': {'input': 'serie', 'label': _('Buscar por Serie')},
            'modelo': {'input': 'modelo', 'label': _('Buscar por Modelo')},
        }
        
        if not sortby:
            sortby = 'date'
        if not filterby:
            filterby = 'all'
        
        order = searchbar_sortings[sortby]['order']
        
        domain += searchbar_filters[filterby]['domain']
        
        if search and search_in:
            search_domain = []
            if search_in in ('all', 'serie'):
                search_domain = ['|', ('serie', 'ilike', search)]
            if search_in in ('all', 'modelo'):
                search_domain += ['|', ('name.name', 'ilike', search)]
            if search_domain:
                domain += search_domain
        
        equipo_count = Alquiler.search_count(domain)
        
        _logger.info(f"📊 Total equipos encontrados: {equipo_count}")
        
        pager = portal_pager(
            url="/my/equipos",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 
                      'filterby': filterby, 'search_in': search_in, 'search': search},
            total=equipo_count,
            page=page,
            step=self._items_per_page
        )
        
        equipos = Alquiler.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )
        
        values.update({
            'date': date_begin,
            'equipos': equipos,
            'page_name': 'equipo',
            'default_url': '/my/equipos',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'searchbar_inputs': searchbar_inputs,
            'sortby': sortby,
            'filterby': filterby,
            'search_in': search_in,
            'search': search,
        })
        
        return request.render("sat.portal_my_equipos", values)
    

    @http.route(['/my/equipo/<int:equipo_id>'], type='http', auth="user", website=True)
    def portal_equipo_detail(self, equipo_id, access_token=None, **kw):
        """Detalle de un equipo específico"""
        
        try:
            equipo_sudo = self._document_check_access('alquiler', equipo_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        
        partner = request.env.user.partner_id.commercial_partner_id
        
        if equipo_sudo.cliente_id.id != partner.id:
            _logger.warning(
                f"⚠️ Acceso denegado - Usuario: {request.env.user.name}, "
                f"Partner usuario: {partner.name}, "
                f"Cliente del equipo: {equipo_sudo.cliente_id.name}"
            )
            return request.redirect('/my')
        
        _logger.info(
            f"✅ Acceso permitido - Equipo: {equipo_sudo.serie}, "
            f"Cliente: {equipo_sudo.cliente_id.name}"
        )
        
        tickets = request.env['ticket.alquiler'].search([
            ('product_alquiler', '=', equipo_id),
            ('partner_id', '=', partner.id)
        ], order='create_date desc', limit=10)
        
        pedidos = request.env['sale.order'].search([
            ('equipo_id', '=', equipo_id),
            ('partner_id', '=', partner.id)
        ], order='create_date desc', limit=5)
        
        values = {
            'equipo': equipo_sudo,
            'tickets': tickets,
            'pedidos': pedidos,
            'page_name': 'equipo_detail',
            'user': request.env.user,
        }
        
        return request.render("sat.portal_equipo_detail", values)
    

    # ========== TICKETS ==========
    @http.route(['/my/tickets', '/my/tickets/page/<int:page>'], 
                type='http', auth="user", website=True)
    def portal_my_tickets(self, page=1, date_begin=None, date_end=None, 
                          sortby=None, filterby=None, search=None, **kw):
        """Lista de tickets del cliente autenticado"""
        
        values = self._prepare_portal_layout_values()

        # CAMBIO
        partner = request.env.user.partner_id.commercial_partner_id

        Ticket = request.env['ticket.alquiler']
        
        domain = [('partner_id', '=', partner.id)]
        
        _logger.info(
            f"🎫 Portal Tickets - Usuario: {request.env.user.name}, "
            f"Partner: {partner.name} (ID: {partner.id})"
        )
        
        searchbar_sortings = {
            'date': {'label': _('Fecha más reciente'), 'order': 'create_date desc'},
            'name': {'label': _('Número'), 'order': 'name'},
            'estado': {'label': _('Estado'), 'order': 'estado'},
            'agenda': {'label': _('Fecha de visita'), 'order': 'agenda desc'},
        }
        
        searchbar_filters = {
            'all': {'label': _('Todos'), 'domain': []},
            'nuevo': {'label': _('Nuevos'), 'domain': [('estado', '=', 'nuevo')]},
            'proceso': {'label': _('En Proceso'), 'domain': [('estado', '=', 'proceso')]},
            'finalizado': {'label': _('Finalizados'), 'domain': [('estado', '=', 'finalizado')]},
        }
        
        if not sortby:
            sortby = 'date'
        if not filterby:
            filterby = 'all'
        
        order = searchbar_sortings[sortby]['order']
        domain += searchbar_filters[filterby]['domain']
        
        if search:
            domain += ['|', ('name', 'ilike', search), ('serie_id_r', 'ilike', search)]
        
        ticket_count = Ticket.search_count(domain)
        
        _logger.info(f"📊 Total tickets encontrados: {ticket_count}")
        
        pager = portal_pager(
            url="/my/tickets",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 
                      'filterby': filterby, 'search': search},
            total=ticket_count,
            page=page,
            step=self._items_per_page
        )
        
        tickets = Ticket.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )
        
        values.update({
            'date': date_begin,
            'tickets': tickets,
            'page_name': 'ticket',
            'default_url': '/my/tickets',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'sortby': sortby,
            'filterby': filterby,
            'search': search,
        })
        
        return request.render("sat.portal_my_tickets", values)
    
    @http.route(['/my/ticket/<int:ticket_id>'], type='http', auth="user", website=True)
    def portal_ticket_detail(self, ticket_id, access_token=None, **kw):
        """Detalle de un ticket específico"""
        
        try:
            ticket_sudo = self._document_check_access('ticket.alquiler', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Usar la empresa del usuario
        partner = request.env.user.partner_id.commercial_partner_id

        # Verificar que el ticket pertenece a la empresa del usuario
        if ticket_sudo.partner_id.id != partner.id:
            _logger.warning(
                f"⚠️ Acceso denegado a ticket - Usuario: {request.env.user.name}, "
                f"Partner usuario: {partner.name}, "
                f"Cliente del ticket: {ticket_sudo.partner_id.name}"
            )
            return request.redirect('/my')
        
        values = {
            'ticket': ticket_sudo,
            'page_name': 'ticket_detail',
            'user': request.env.user,
        }
        
        return request.render("sat.portal_ticket_detail", values)
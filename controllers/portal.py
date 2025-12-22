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
        partner = request.env.user.partner_id
        
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
        partner = request.env.user.partner_id
        
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
        partner = request.env.user.partner_id
        Alquiler = request.env['alquiler']
        
        # Dominio base: solo equipos del cliente
        domain = [('cliente_id', '=', partner.id)]
        
        # Opciones de ordenamiento
        searchbar_sortings = {
            'date': {'label': _('Fecha más reciente'), 'order': 'create_date desc'},
            'name': {'label': _('Modelo'), 'order': 'name'},
            'serie': {'label': _('Serie'), 'order': 'serie'},
            'estado': {'label': _('Estado'), 'order': 'estado_alquiler_id'},
        }
        
        # Opciones de filtrado
        searchbar_filters = {
            'all': {'label': _('Todos'), 'domain': []},
            'alquilada': {'label': _('Alquilados'), 'domain': [('estado_alquiler_id', '=', 'alquilada')]},
            'lista': {'label': _('Listos'), 'domain': [('estado_alquiler_id', '=', 'lista')]},
            'con_problemas': {'label': _('Con Problemas'), 'domain': [('estado_alquiler_id', '=', 'con_problemas')]},
        }
        
        # Búsqueda
        searchbar_inputs = {
            'all': {'input': 'all', 'label': _('Buscar en Todo')},
            'serie': {'input': 'serie', 'label': _('Buscar por Serie')},
            'modelo': {'input': 'modelo', 'label': _('Buscar por Modelo')},
        }
        
        # Valores por defecto
        if not sortby:
            sortby = 'date'
        if not filterby:
            filterby = 'all'
        
        order = searchbar_sortings[sortby]['order']
        
        # Aplicar filtro
        domain += searchbar_filters[filterby]['domain']
        
        # Aplicar búsqueda
        if search and search_in:
            search_domain = []
            if search_in in ('all', 'serie'):
                search_domain = ['|', ('serie', 'ilike', search)]
            if search_in in ('all', 'modelo'):
                search_domain += ['|', ('name.name', 'ilike', search)]
            if search_domain:
                domain += search_domain
        
        # Contar total de equipos
        equipo_count = Alquiler.search_count(domain)
        
        # Paginación
        pager = portal_pager(
            url="/my/equipos",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 
                      'filterby': filterby, 'search_in': search_in, 'search': search},
            total=equipo_count,
            page=page,
            step=self._items_per_page
        )
        
        # Obtener equipos
        equipos = Alquiler.search(domain, order=order, limit=self._items_per_page, 
                                  offset=pager['offset'])
        
        # Preparar valores para la vista
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
        
        # Verificar que el equipo pertenece al cliente
        if equipo_sudo.cliente_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        
        # Obtener tickets relacionados
        tickets = request.env['ticket.alquiler'].search([
            ('product_alquiler', '=', equipo_id),
            ('partner_id', '=', request.env.user.partner_id.id)
        ], order='create_date desc', limit=10)
        
        # Obtener pedidos relacionados
        pedidos = request.env['sale.order'].search([
            ('equipo_id', '=', equipo_id),
            ('partner_id', '=', request.env.user.partner_id.id)
        ], order='create_date desc', limit=5)
        
        # Obtener contadores automáticos recientes
        contadores = request.env['contador.automatico'].search([
            ('equipo_id', '=', equipo_id)
        ], order='fecha desc', limit=5)
        
        values = {
            'equipo': equipo_sudo,
            'tickets': tickets,
            'pedidos': pedidos,
            'contadores': contadores,
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
        partner = request.env.user.partner_id
        Ticket = request.env['ticket.alquiler']
        
        # Dominio base: solo tickets del cliente
        domain = [('partner_id', '=', partner.id)]
        
        # Opciones de ordenamiento
        searchbar_sortings = {
            'date': {'label': _('Fecha más reciente'), 'order': 'create_date desc'},
            'name': {'label': _('Número'), 'order': 'name'},
            'estado': {'label': _('Estado'), 'order': 'estado'},
            'agenda': {'label': _('Fecha de visita'), 'order': 'agenda desc'},
        }
        
        # Opciones de filtrado
        searchbar_filters = {
            'all': {'label': _('Todos'), 'domain': []},
            'nuevo': {'label': _('Nuevos'), 'domain': [('estado', '=', 'nuevo')]},
            'proceso': {'label': _('En Proceso'), 'domain': [('estado', '=', 'proceso')]},
            'finalizado': {'label': _('Finalizados'), 'domain': [('estado', '=', 'finalizado')]},
        }
        
        # Valores por defecto
        if not sortby:
            sortby = 'date'
        if not filterby:
            filterby = 'all'
        
        order = searchbar_sortings[sortby]['order']
        domain += searchbar_filters[filterby]['domain']
        
        # Búsqueda por número de ticket o serie
        if search:
            domain += ['|', ('name', 'ilike', search), ('serie_id_r', 'ilike', search)]
        
        # Contar tickets
        ticket_count = Ticket.search_count(domain)
        
        # Paginación
        pager = portal_pager(
            url="/my/tickets",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 
                      'filterby': filterby, 'search': search},
            total=ticket_count,
            page=page,
            step=self._items_per_page
        )
        
        # Obtener tickets
        tickets = Ticket.search(domain, order=order, limit=self._items_per_page, 
                                offset=pager['offset'])
        
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
        
        # Verificar que el ticket pertenece al cliente
        if ticket_sudo.partner_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')
        
        values = {
            'ticket': ticket_sudo,
            'page_name': 'ticket_detail',
            'user': request.env.user,
        }
        
        return request.render("sat.portal_ticket_detail", values)
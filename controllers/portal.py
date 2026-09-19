# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from collections import OrderedDict
from operator import itemgetter
from datetime import datetime, time, timedelta
from pytz import UTC, timezone
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

        Mantiene la validación de acceso y la lógica multiempresa existente,
        y agrega datos de análisis para el dashboard del cliente.

        La fecha usada para estadísticas es ``agenda`` porque es el campo real
        de fecha de visita del modelo ``ticket.alquiler``.
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
        Ticket = request.env["ticket.alquiler"]

        base_domain = [
            ("product_alquiler", "=", equipo_id),
            ("partner_id", "=", equipo_partner.id),
        ]

        # ======================================================
        # FILTROS DEL DASHBOARD
        # ======================================================

        user_tz = timezone(request.env.user.tz or "America/Lima")
        now_local = datetime.now(user_tz)
        today_local = now_local.date()

        periodo = (kw.get("periodo") or "todos").strip()
        if periodo not in {"hoy", "7dias", "mes", "anio", "todos", "personalizado"}:
            periodo = "todos"

        def _safe_int(value, default=False):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def _safe_date(value):
            if not value:
                return False
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                return False

        def _local_midnight_to_utc(local_date):
            local_dt = user_tz.localize(datetime.combine(local_date, time.min))
            return local_dt.astimezone(UTC).replace(tzinfo=None)

        selected_year = _safe_int(kw.get("anio"), now_local.year)
        if selected_year < 2000 or selected_year > 2100:
            selected_year = now_local.year

        selected_month = _safe_int(kw.get("mes"), now_local.month)
        if selected_month < 1 or selected_month > 12:
            selected_month = now_local.month

        selected_tecnico_id = _safe_int(kw.get("tecnico_id"), False)
        selected_tipo_servicio = (kw.get("tipo_servicio") or "").strip()
        selected_estado = (kw.get("estado") or "").strip()
        date_begin_value = (kw.get("date_begin") or "").strip()
        date_end_value = (kw.get("date_end") or "").strip()

        start_date = False
        end_date = False

        if periodo == "hoy":
            start_date = today_local
            end_date = today_local

        elif periodo == "7dias":
            start_date = today_local - timedelta(days=6)
            end_date = today_local

        elif periodo == "mes":
            start_date = datetime(selected_year, selected_month, 1).date()
            if selected_month == 12:
                next_month = datetime(selected_year + 1, 1, 1).date()
            else:
                next_month = datetime(selected_year, selected_month + 1, 1).date()
            end_date = next_month - timedelta(days=1)

        elif periodo == "anio":
            start_date = datetime(selected_year, 1, 1).date()
            end_date = datetime(selected_year, 12, 31).date()

        elif periodo == "personalizado":
            start_date = _safe_date(date_begin_value)
            end_date = _safe_date(date_end_value)
            if start_date and end_date and start_date > end_date:
                start_date, end_date = end_date, start_date
                date_begin_value = start_date.strftime("%Y-%m-%d")
                date_end_value = end_date.strftime("%Y-%m-%d")

        filtered_domain = list(base_domain)

        if start_date:
            filtered_domain.append(("agenda", ">=", _local_midnight_to_utc(start_date)))

        if end_date:
            next_day = end_date + timedelta(days=1)
            filtered_domain.append(("agenda", "<", _local_midnight_to_utc(next_day)))

        if selected_tecnico_id:
            filtered_domain.append(("responsable", "=", selected_tecnico_id))

        tipo_servicio_selection = dict(Ticket._fields["tipo_servicio_id"].selection)
        if selected_tipo_servicio not in tipo_servicio_selection:
            selected_tipo_servicio = ""
        if selected_tipo_servicio:
            filtered_domain.append(("tipo_servicio_id", "=", selected_tipo_servicio))

        estado_selection = dict(Ticket._fields["estado"].selection)
        if selected_estado not in estado_selection:
            selected_estado = ""
        if selected_estado:
            filtered_domain.append(("estado", "=", selected_estado))

        # Se mantiene la colección ``tickets`` usada por la plantilla, pero
        # ahora responde a los filtros. El límite alto evita cargar historiales
        # ilimitados en una sola página.
        # Conjunto completo para estadísticas. No se limita para que los
        # gráficos y KPI representen todos los servicios del filtro.
        stats_tickets = Ticket.search(
            filtered_domain,
            order="agenda desc, create_date desc",
        )

        # Historial visible: se limita solo la tabla para evitar una página
        # excesivamente pesada cuando el equipo acumule muchos años de datos.
        tickets = stats_tickets[:100]
        tickets_total = len(stats_tickets)

        # Pedidos: se conserva exactamente la consulta que ya funcionaba.
        pedidos = request.env["sale.order"].search([
            ("equipo_id", "=", equipo_id),
            ("partner_id", "=", equipo_partner.id),
        ], order="create_date desc", limit=5)

        # ======================================================
        # KPI DEL EQUIPO
        # ======================================================

        current_month_start = today_local.replace(day=1)
        if current_month_start.month == 12:
            current_month_next = current_month_start.replace(
                year=current_month_start.year + 1,
                month=1,
                day=1,
            )
        else:
            current_month_next = current_month_start.replace(
                month=current_month_start.month + 1,
                day=1,
            )

        current_year_start = today_local.replace(month=1, day=1)
        current_year_next = current_year_start.replace(year=current_year_start.year + 1)

        servicios_mes_actual = Ticket.search_count(
            base_domain + [
                ("agenda", ">=", _local_midnight_to_utc(current_month_start)),
                ("agenda", "<", _local_midnight_to_utc(current_month_next)),
            ]
        )

        servicios_anio_actual = Ticket.search_count(
            base_domain + [
                ("agenda", ">=", _local_midnight_to_utc(current_year_start)),
                ("agenda", "<", _local_midnight_to_utc(current_year_next)),
            ]
        )

        servicios_finalizados = Ticket.search_count(
            filtered_domain + [("estado", "=", "finalizado")]
        ) if selected_estado != "finalizado" else tickets_total

        tecnicos_distintos = stats_tickets.mapped("responsable")

        ultimo_ticket = Ticket.search(
            base_domain + [("agenda", "!=", False)],
            order="agenda desc",
            limit=1,
        )

        # ======================================================
        # OPCIONES DISPONIBLES PARA FILTROS
        # ======================================================

        all_equipment_tickets = Ticket.search(
            base_domain,
            order="agenda asc, create_date asc",
        )

        year_values = set()
        for ticket in all_equipment_tickets:
            if ticket.agenda:
                local_agenda = ticket.agenda.replace(tzinfo=UTC).astimezone(user_tz)
                year_values.add(local_agenda.year)
        year_values.add(now_local.year)
        available_years = sorted(year_values, reverse=True)

        available_tecnicos = all_equipment_tickets.mapped("responsable").sorted(
            key=lambda rec: (rec.name or "").lower()
        )

        # ======================================================
        # GRÁFICO PRINCIPAL: DÍA / MES / AÑO SEGÚN PERIODO
        # ======================================================

        chart_tickets = stats_tickets
        chart_mode = "month"
        chart_title = "Servicios por mes"
        chart_subtitle = "Distribución de visitas del periodo seleccionado"
        chart_rows = []

        if periodo == "todos":
            chart_mode = "year"
            chart_title = "Servicios por año"
            counts = {}
            source_tickets = Ticket.search(
                filtered_domain + [("agenda", "!=", False)],
                order="agenda asc",
            )
            for ticket in source_tickets:
                local_agenda = ticket.agenda.replace(tzinfo=UTC).astimezone(user_tz)
                counts[local_agenda.year] = counts.get(local_agenda.year, 0) + 1
            for year in sorted(counts):
                chart_rows.append({"label": str(year), "value": counts[year]})

        elif periodo == "anio":
            month_names = [
                "Ene", "Feb", "Mar", "Abr", "May", "Jun",
                "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
            ]
            counts = {month: 0 for month in range(1, 13)}
            for ticket in chart_tickets:
                if not ticket.agenda:
                    continue
                local_agenda = ticket.agenda.replace(tzinfo=UTC).astimezone(user_tz)
                if local_agenda.year == selected_year:
                    counts[local_agenda.month] += 1
            for month in range(1, 13):
                chart_rows.append({
                    "label": month_names[month - 1],
                    "value": counts[month],
                })

        else:
            effective_start = start_date
            effective_end = end_date
            if not effective_start or not effective_end:
                dated = []
                for ticket in chart_tickets:
                    if ticket.agenda:
                        dated.append(ticket.agenda.replace(tzinfo=UTC).astimezone(user_tz).date())
                if dated:
                    effective_start = min(dated)
                    effective_end = max(dated)

            days_span = (effective_end - effective_start).days + 1 if effective_start and effective_end else 0

            if days_span and days_span <= 45:
                chart_mode = "day"
                chart_title = "Servicios por día"
                counts = {}
                cursor = effective_start
                while cursor <= effective_end:
                    counts[cursor] = 0
                    cursor += timedelta(days=1)

                for ticket in chart_tickets:
                    if not ticket.agenda:
                        continue
                    local_date = ticket.agenda.replace(tzinfo=UTC).astimezone(user_tz).date()
                    if local_date in counts:
                        counts[local_date] += 1

                for local_date, count in counts.items():
                    chart_rows.append({
                        "label": local_date.strftime("%d/%m"),
                        "value": count,
                    })
            else:
                chart_mode = "month"
                chart_title = "Servicios por mes"
                counts = {}
                for ticket in chart_tickets:
                    if not ticket.agenda:
                        continue
                    local_agenda = ticket.agenda.replace(tzinfo=UTC).astimezone(user_tz)
                    key = (local_agenda.year, local_agenda.month)
                    counts[key] = counts.get(key, 0) + 1
                for year, month in sorted(counts):
                    chart_rows.append({
                        "label": f"{month:02d}/{year}",
                        "value": counts[(year, month)],
                    })

        chart_max = max([row["value"] for row in chart_rows] or [1])
        for row in chart_rows:
            row["percent"] = round((row["value"] / chart_max) * 100, 2) if chart_max else 0

        # ======================================================
        # DISTRIBUCIÓN POR TIPO DE SERVICIO
        # ======================================================

        type_counts = {}
        for ticket in stats_tickets:
            key = ticket.tipo_servicio_id or "sin_tipo"
            label = tipo_servicio_selection.get(key, "Sin especificar")
            if key == "sin_tipo":
                label = "Sin especificar"
            type_counts[label] = type_counts.get(label, 0) + 1

        type_max = max(type_counts.values() or [1])
        service_type_chart = [
            {
                "label": label,
                "value": value,
                "percent": round((value / type_max) * 100, 2),
            }
            for label, value in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

        # ======================================================
        # DISTRIBUCIÓN POR TÉCNICO
        # ======================================================

        technician_counts = {}
        for ticket in stats_tickets:
            label = ticket.responsable.name if ticket.responsable else "Sin asignar"
            technician_counts[label] = technician_counts.get(label, 0) + 1

        technician_max = max(technician_counts.values() or [1])
        technician_chart = [
            {
                "label": label,
                "value": value,
                "percent": round((value / technician_max) * 100, 2),
            }
            for label, value in sorted(technician_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

        # ======================================================
        # DISTRIBUCIÓN POR ESTADO
        # ======================================================

        state_counts = {}
        for ticket in stats_tickets:
            key = ticket.estado or "sin_estado"
            label = estado_selection.get(key, "Sin estado")
            if key == "sin_estado":
                label = "Sin estado"
            state_counts[label] = state_counts.get(label, 0) + 1

        state_chart = [
            {"label": label, "value": value}
            for label, value in sorted(state_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

        # ======================================================
        # DATOS PARA LA VISTA
        # ======================================================

        values = {
            "equipo": equipo_sudo,
            "tickets": tickets,
            "tickets_total": tickets_total,
            "pedidos": pedidos,
            "page_name": "equipo_detail",
            "user": request.env.user,
            "periodo": periodo,
            "selected_year": selected_year,
            "selected_month": selected_month,
            "selected_tecnico_id": selected_tecnico_id,
            "selected_tipo_servicio": selected_tipo_servicio,
            "selected_estado": selected_estado,
            "date_begin": date_begin_value,
            "date_end": date_end_value,
            "available_years": available_years,
            "available_tecnicos": available_tecnicos,
            "tipo_servicio_selection": tipo_servicio_selection,
            "estado_selection": estado_selection,
            "servicios_mes_actual": servicios_mes_actual,
            "servicios_anio_actual": servicios_anio_actual,
            "servicios_finalizados": servicios_finalizados,
            "tecnicos_distintos_count": len(tecnicos_distintos),
            "ultimo_ticket": ultimo_ticket,
            "chart_mode": chart_mode,
            "chart_title": chart_title,
            "chart_subtitle": chart_subtitle,
            "chart_rows": chart_rows,
            "service_type_chart": service_type_chart,
            "technician_chart": technician_chart,
            "state_chart": state_chart,
        }

        _logger.info(
            "📊 Dashboard equipo=%s periodo=%s inicio=%s fin=%s tickets=%s tecnico=%s tipo=%s estado=%s",
            equipo_sudo.serie,
            periodo,
            start_date,
            end_date,
            tickets_total,
            selected_tecnico_id,
            selected_tipo_servicio,
            selected_estado,
        )

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
# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from collections import OrderedDict, Counter, defaultdict
from urllib.parse import urlencode
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
        # GRÁFICO MENSUAL APILADO POR TIPO DE SERVICIO
        # ======================================================
        # Este gráfico es independiente del selector de periodo para que el
        # cliente siempre pueda visualizar los 12 meses del año seleccionado.
        # Respeta los demás filtros: técnico, tipo de servicio y estado.

        powerbi_service_colors = {
            "instalacion": "#118DFF",
            "retiro": "#12239E",
            "mantenimiento_preventivo": "#00A6A6",
            "mantenimiento_correctivo": "#E66C37",
            "cambio_repuestos": "#D64550",
            "remoto": "#6B007B",
            "revision": "#E044A7",
            "alquiler": "#744EC2",
            "sin_tipo": "#8A8A8A",
        }

        monthly_domain = list(base_domain)
        monthly_domain += [
            ("agenda", ">=", _local_midnight_to_utc(datetime(selected_year, 1, 1).date())),
            ("agenda", "<", _local_midnight_to_utc(datetime(selected_year + 1, 1, 1).date())),
        ]

        if selected_tecnico_id:
            monthly_domain.append(("responsable", "=", selected_tecnico_id))
        if selected_tipo_servicio:
            monthly_domain.append(("tipo_servicio_id", "=", selected_tipo_servicio))
        if selected_estado:
            monthly_domain.append(("estado", "=", selected_estado))

        monthly_tickets = Ticket.search(
            monthly_domain,
            order="agenda asc, create_date asc",
        )

        month_names_full = [
            "Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
        ]

        monthly_counts = {
            month: {} for month in range(1, 13)
        }

        service_keys_present = set()
        for ticket in monthly_tickets:
            if not ticket.agenda:
                continue
            local_agenda = ticket.agenda.replace(tzinfo=UTC).astimezone(user_tz)
            service_key = ticket.tipo_servicio_id or "sin_tipo"
            service_keys_present.add(service_key)
            month_bucket = monthly_counts[local_agenda.month]
            month_bucket[service_key] = month_bucket.get(service_key, 0) + 1

        # Mantener el orden definido en el Selection del modelo y colocar
        # "Sin especificar" al final cuando exista.
        service_order = [key for key in tipo_servicio_selection if key in service_keys_present]
        if "sin_tipo" in service_keys_present:
            service_order.append("sin_tipo")

        monthly_service_legend = []
        for service_key in service_order:
            label = tipo_servicio_selection.get(service_key, "Sin especificar")
            if service_key == "sin_tipo":
                label = "Sin especificar"
            monthly_service_legend.append({
                "key": service_key,
                "label": label,
                "color": powerbi_service_colors.get(service_key, "#8A8A8A"),
            })

        month_totals = {
            month: sum(monthly_counts[month].values())
            for month in range(1, 13)
        }
        monthly_max = max(month_totals.values() or [1]) or 1

        monthly_type_chart = []
        for month in range(1, 13):
            segments = []
            for service_key in service_order:
                value = monthly_counts[month].get(service_key, 0)
                if not value:
                    continue
                label = tipo_servicio_selection.get(service_key, "Sin especificar")
                if service_key == "sin_tipo":
                    label = "Sin especificar"
                segments.append({
                    "key": service_key,
                    "label": label,
                    "value": value,
                    "height_percent": round((value / monthly_max) * 100, 2),
                    "color": powerbi_service_colors.get(service_key, "#8A8A8A"),
                })

            monthly_type_chart.append({
                "month": month,
                "label": month_names_full[month - 1],
                "total": month_totals[month],
                "active": periodo == "mes" and selected_month == month,
                "segments": segments,
            })

        # ======================================================
        # DISTRIBUCIÓN POR TIPO DE SERVICIO
        # ======================================================

        type_counts = {}
        for ticket in stats_tickets:
            key = ticket.tipo_servicio_id or "sin_tipo"
            type_counts[key] = type_counts.get(key, 0) + 1

        type_max = max(type_counts.values() or [1])
        service_type_chart = []
        for service_key, value in sorted(
            type_counts.items(),
            key=lambda item: (-item[1], tipo_servicio_selection.get(item[0], "Sin especificar")),
        ):
            label = tipo_servicio_selection.get(service_key, "Sin especificar")
            if service_key == "sin_tipo":
                label = "Sin especificar"
            service_type_chart.append({
                "key": service_key,
                "label": label,
                "value": value,
                "percent": round((value / type_max) * 100, 2),
                "color": powerbi_service_colors.get(service_key, "#8A8A8A"),
            })

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
            "monthly_type_chart": monthly_type_chart,
            "monthly_service_legend": monthly_service_legend,
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
        type="http", auth="user", website=True,
    )
    def portal_my_tickets(self, page=1, date_begin=None, date_end=None,
                          sortby=None, filterby=None, search=None, **kw):
        """Dashboard de tickets del portal, limitado por ACL y empresas autorizadas."""
        values = self._prepare_portal_layout_values()
        company_ids = self._get_portal_company_ids()
        Ticket = request.env["ticket.alquiler"]  # Sin sudo: conservar ACL / reglas.
        Partner = request.env["res.partner"].sudo()  # Solo nombres de empresas previamente autorizadas.
        company_domain = [("partner_id", "in", company_ids)]

        def integer(value, default=0):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def parse_date(value):
            try:
                return datetime.strptime(value, "%Y-%m-%d").date() if value else None
            except (TypeError, ValueError):
                return None

        user_tz = timezone(request.env.user.tz or "America/Lima")
        local_now = datetime.now(user_tz)
        today = local_now.date()

        def start_utc(day):
            # El campo agenda es datetime UTC almacenado sin zona por Odoo.
            local_dt = user_tz.localize(datetime.combine(day, time.min))
            return local_dt.astimezone(UTC).replace(tzinfo=None)

        company_id = integer(kw.get("company_id"))
        if company_id not in company_ids:
            company_id = 0  # Parámetro manipulado no amplía acceso.
        equipment_id = integer(kw.get("equipment_id"))
        tecnico_id = integer(kw.get("tecnico_id"))
        tipo = (kw.get("tipo_servicio") or "").strip()
        estado = (kw.get("estado") or "").strip()
        periodo = (kw.get("periodo") or "todos").strip()
        if periodo not in ("todos", "hoy", "7dias", "mes", "anio", "personalizado"):
            periodo = "todos"
        anio = integer(kw.get("anio"), today.year)
        mes = integer(kw.get("mes"), today.month)
        if not 2000 <= anio <= 2100:
            anio = today.year
        if not 1 <= mes <= 12:
            mes = today.month

        tipo_selection = dict(Ticket._fields["tipo_servicio_id"].selection)
        estado_selection = dict(Ticket._fields["estado"].selection)
        if tipo not in tipo_selection and tipo != "__sin_tipo__":
            tipo = ""
        if estado not in estado_selection:
            estado = ""
        sortings = {
            "date": {"label": _("Más recientes"), "order": "create_date desc"},
            "agenda": {"label": _("Fecha de visita"), "order": "agenda desc, create_date desc"},
            "name": {"label": _("Número"), "order": "name"},
            "estado": {"label": _("Estado"), "order": "estado, create_date desc"},
        }
        sortby = sortby if sortby in sortings else "date"
        # Compatibilidad con los enlaces existentes /my/tickets?filterby=...
        if not estado and filterby in ("nuevo", "proceso", "finalizado"):
            estado = filterby
        search = (search or "").strip()[:120]

        # El universo de opciones procede únicamente de tickets accesibles.
        authorized_tickets = Ticket.search(company_domain)
        available_equipment = authorized_tickets.mapped("product_alquiler").sorted(
            key=lambda r: (r.display_name or "").lower())
        available_technicians = authorized_tickets.mapped("responsable").sorted(
            key=lambda r: (r.name or "").lower())
        equipment_ids = set(available_equipment.ids)
        technician_ids = set(available_technicians.ids)
        if equipment_id not in equipment_ids:
            equipment_id = 0
        if tecnico_id not in technician_ids and tecnico_id != -1:
            tecnico_id = 0

        domain = list(company_domain)
        if company_id:
            domain.append(("partner_id", "=", company_id))
        if equipment_id:
            domain.append(("product_alquiler", "=", equipment_id))
        if tecnico_id:
            domain.append(("responsable", "=", tecnico_id if tecnico_id > 0 else False))
        if tipo:
            domain.append(("tipo_servicio_id", "=", tipo if tipo != "__sin_tipo__" else False))
        if estado:
            domain.append(("estado", "=", estado))
        if search:
            domain.extend(["|", "|", "|",
                           ("name", "ilike", search),
                           ("serie_id_r", "ilike", search),
                           ("product_alquiler.name.name", "ilike", search),
                           ("partner_id.name", "ilike", search)])

        date_start = date_end_value = None
        if periodo == "hoy":
            date_start = date_end_value = today
        elif periodo == "7dias":
            date_start, date_end_value = today - timedelta(days=6), today
        elif periodo == "mes":
            date_start = datetime(anio, mes, 1).date()
            date_end_value = (datetime(anio + 1, 1, 1).date() if mes == 12
                              else datetime(anio, mes + 1, 1).date()) - timedelta(days=1)
        elif periodo == "anio":
            date_start = datetime(anio, 1, 1).date()
            date_end_value = datetime(anio, 12, 31).date()
        elif periodo == "personalizado":
            date_start, date_end_value = parse_date(date_begin), parse_date(date_end)
            if date_start and date_end_value and date_start > date_end_value:
                date_start, date_end_value = date_end_value, date_start
        if date_start:
            domain.append(("agenda", ">=", start_utc(date_start)))
        if date_end_value:
            domain.append(("agenda", "<", start_utc(date_end_value + timedelta(days=1))))

        # Estadísticas siempre sobre todo el resultado filtrado; paginación solo tabla.
        stats = Ticket.search(domain, order=sortings[sortby]["order"])
        total = len(stats)
        type_counts = Counter(t.tipo_servicio_id or "sin_tipo" for t in stats)
        state_counts = Counter(t.estado or "sin_estado" for t in stats)
        tech_counts = Counter((t.responsable.id, t.responsable.name)
                              if t.responsable else (0, "Sin asignar") for t in stats)
        company_counts = Counter((t.partner_id.id, t.partner_id.name)
                                 for t in stats if t.partner_id)
        machines = defaultdict(lambda: {"model": "", "serie": "", "total": 0,
                                        "incidencias": 0, "id": 0})
        # Definición operativa visible, no se considera instalación o preventiva como falla.
        incident_type_keys = {"mantenimiento_correctivo", "cambio_repuestos"}
        incident_total = 0
        for t in stats:
            if not t.product_alquiler:
                continue
            info = machines[t.product_alquiler.id]
            info["id"] = t.product_alquiler.id
            info["model"] = str(t.modelo_id_r or t.product_alquiler.display_name or "Equipo")
            info["serie"] = str(t.serie_id_r or "Sin serie")
            info["total"] += 1
            if t.tipo_servicio_id in incident_type_keys:
                info["incidencias"] += 1
                incident_total += 1
        # Se incluyen correctivos sin equipo en el KPI, aunque no en el ranking.
        incident_total = sum(t.tipo_servicio_id in incident_type_keys for t in stats)
        ranking = sorted((i for i in machines.values() if i["incidencias"]),
                         key=lambda x: (-x["incidencias"], x["model"]))[:8]
        ranking_max = max([i["incidencias"] for i in ranking] or [1])
        types_chart = [{"key": key, "label": tipo_selection.get(key, "Sin especificar"),
                        "value": value} for key, value in type_counts.most_common()]
        types_max = max(list(type_counts.values()) or [1])
        for item in types_chart:
            item["pct"] = round(item["value"] / types_max * 100, 2)
        for item in ranking:
            item["pct"] = round(item["incidencias"] / ranking_max * 100, 2)
        tech_chart = [{"id": key[0], "label": key[1], "value": value,
                       "pct": round(value / total * 100, 1) if total else 0}
                      for key, value in tech_counts.most_common()[:8]]
        companies_chart = [{"id": key[0], "label": key[1], "value": value}
                           for key, value in company_counts.most_common()[:8]]
        company_max = max([r["value"] for r in companies_chart] or [1])
        for item in companies_chart:
            item["pct"] = round(item["value"] / company_max * 100, 2)

        month_counts = Counter()
        for t in stats:
            if t.agenda:
                dt = t.agenda.replace(tzinfo=UTC).astimezone(user_tz)
                month_counts[(dt.year, dt.month)] += 1
        if periodo == "anio":
            month_keys = [(anio, m) for m in range(1, 13)]
        elif periodo == "mes":
            month_keys = [(anio, mes)]
        elif month_counts:
            last = max(month_counts)
            month_keys = []
            y, m = last
            for _ in range(12):
                month_keys.append((y, m))
                y, m = (y-1, 12) if m == 1 else (y, m-1)
            month_keys.reverse()
        else:
            month_keys = [(today.year, m) for m in range(1, 13)]
        month_max = max([month_counts.get(k, 0) for k in month_keys] or [1]) or 1
        months_chart = [{"label": "%02d/%s" % (m, str(y)[-2:]),
                         "value": month_counts.get((y, m), 0),
                         "pct": round(month_counts.get((y, m), 0) / month_max * 100, 2),
                         "year": y, "month": m} for y, m in month_keys]

        # URL con filtros actuales; los gráficos actúan como filtros navegables.
        params = {"company_id": company_id or "", "equipment_id": equipment_id or "",
                  "tecnico_id": tecnico_id or "", "tipo_servicio": tipo,
                  "estado": estado, "periodo": periodo, "anio": anio, "mes": mes,
                  "date_begin": date_begin or "", "date_end": date_end or "",
                  "sortby": sortby, "search": search}
        def dashboard_link(**changes):
            current = dict(params)
            current.update(changes)
            return "/my/tickets?" + urlencode({k: v for k, v in current.items()
                                                 if v is not None and v != ""})
        for item in types_chart:
            item["url"] = dashboard_link(tipo_servicio=item["key"] if item["key"] != "sin_tipo" else "__sin_tipo__")
        for item in ranking:
            item["url"] = dashboard_link(equipment_id=item["id"])
        for item in tech_chart:
            item["url"] = dashboard_link(tecnico_id=item["id"] or -1)
        for item in companies_chart:
            item["url"] = dashboard_link(company_id=item["id"])
        for item in months_chart:
            item["url"] = dashboard_link(periodo="mes", anio=item["year"], mes=item["month"])

        pager = portal_pager(
            url="/my/tickets", url_args={k: v for k, v in params.items() if v != ""},
            total=total, page=page, step=self._items_per_page)
        tickets = stats[pager["offset"]:pager["offset"] + self._items_per_page]
        empresas = Partner.browse(company_ids).exists().sorted(key=lambda x: (x.name or "").lower())
        available_years = sorted({today.year} | {t.agenda.replace(tzinfo=UTC).astimezone(user_tz).year
                                                   for t in authorized_tickets if t.agenda}, reverse=True)
        values.update({
            "tickets": tickets, "ticket_total": total, "page_name": "ticket",
            "default_url": "/my/tickets", "pager": pager,
            "searchbar_sortings": sortings, "sortby": sortby,
            "search": search, "periodo": periodo, "anio": anio, "mes": mes,
            "date_begin": date_begin or "", "date_end": date_end or "",
            "company_id": company_id, "equipment_id": equipment_id,
            "tecnico_id": tecnico_id, "tipo_servicio": tipo, "estado": estado,
            "empresas": empresas, "available_equipment": available_equipment,
            "available_technicians": available_technicians,
            "tipo_selection": tipo_selection, "estado_selection": estado_selection,
            "available_years": available_years,
            "total_finalizados": state_counts.get("finalizado", 0),
            "total_pendientes": total - state_counts.get("finalizado", 0),
            "total_equipos": len(machines), "total_incidencias": incident_total,
            "types_chart": types_chart, "ranking": ranking, "tech_chart": tech_chart,
            "companies_chart": companies_chart, "months_chart": months_chart,
            "dashboard_link": dashboard_link, "company_count": len(empresas),
        })
        return request.render("sat.portal_my_tickets", values)

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
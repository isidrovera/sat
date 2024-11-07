from odoo import models, fields, api
from datetime import date, timedelta
import logging

# Configuración de logger
_logger = logging.getLogger(__name__)

class SatDashboard(models.Model):
    _name = 'sat.dashboard'
    _description = 'Dashboard de análisis'

    @api.model
    def get_dashboard_data(self):
        # Total de máquinas en `sat.sat`
        total_maquinas = self.env['sat.sat'].search_count([])
        _logger.info("Total de máquinas: %s", total_maquinas)

        # Máquinas por disponibilidad
        maquinas_disponibles = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'disponible')])
        maquinas_separadas = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'separada')])
        maquinas_no_disponibles = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'no_disponible')])
        _logger.info("Máquinas - Disponibles: %s, Separadas: %s, No Disponibles: %s", maquinas_disponibles, maquinas_separadas, maquinas_no_disponibles)

        # Máquinas por estado
        maquinas_sin_revisar = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'sin_revisar')])
        maquinas_en_revision = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'en_revision')])
        maquinas_finalizadas = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'finalizado')])
        maquinas_problemas = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'con_problemas')])
        _logger.info("Máquinas por estado - Sin Revisar: %s, En Revisión: %s, Finalizadas: %s, Con Problemas: %s", maquinas_sin_revisar, maquinas_en_revision, maquinas_finalizadas, maquinas_problemas)

        # Máquinas por asesora
        asesora_data = self.env['sat.sat'].read_group([('asesora_id', '!=', False)], ['asesora_id'], ['asesora_id'])
        asesora_totales = {a['asesora_id'][1]: a['asesora_id_count'] for a in asesora_data}
        _logger.info("Máquinas por asesora: %s", asesora_totales)

        # Total de reparaciones en `reparaciones.reparaciones`
        total_reparaciones = self.env['reparaciones.reparaciones'].search_count([])
        reparaciones_en_revision = self.env['reparaciones.reparaciones'].search_count([('estado_id', '=', 'en_revision')])
        _logger.info("Total de reparaciones: %s, Reparaciones en revisión: %s", total_reparaciones, reparaciones_en_revision)

        # Reparaciones diarias, mensuales, y anuales
        today = fields.Date.today()
        reparaciones_hoy = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', today)])
        start_month = today.replace(day=1)
        reparaciones_mes = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', start_month)])
        start_year = today.replace(month=1, day=1)
        reparaciones_ano = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', start_year)])
        _logger.info("Reparaciones - Hoy: %s, Mes: %s, Año: %s", reparaciones_hoy, reparaciones_mes, reparaciones_ano)

        # Reparaciones por técnico
        reparaciones_por_tecnico = self.env['reparaciones.reparaciones'].read_group(
            [('responsable_id', '!=', False)], 
            ['responsable_id'], 
            ['responsable_id']
        )
        tecnicos_totales = {r['responsable_id'][1]: r['responsable_id_count'] for r in reparaciones_por_tecnico}
        _logger.info("Reparaciones por técnico: %s", tecnicos_totales)

        # Total de tickets en `ticket.alquiler`
        total_tickets = self.env['ticket.alquiler'].search_count([])
        _logger.info("Total de tickets: %s", total_tickets)

        # Tickets por mes, año y día usando 'agenda'
        tickets_dia = self.env['ticket.alquiler'].search_count([('agenda', '>=', today)])
        tickets_mes = self.env['ticket.alquiler'].search_count([('agenda', '>=', start_month)])
        tickets_ano = self.env['ticket.alquiler'].search_count([('agenda', '>=', start_year)])
        _logger.info("Tickets - Día: %s, Mes: %s, Año: %s", tickets_dia, tickets_mes, tickets_ano)

        # Tickets por Técnico/Responsable
        tickets_por_tecnico = self.env['ticket.alquiler'].read_group(
            [('responsable', '!=', False)], 
            ['responsable'], 
            ['responsable']
        )
        tecnicos_totales_tickets = {t['responsable'][1]: t['responsable_count'] for t in tickets_por_tecnico}
        _logger.info("Tickets por técnico: %s", tecnicos_totales_tickets)

        # Tickets por Cliente
        tickets_por_cliente = self.env['ticket.alquiler'].read_group(
            [('partner_id', '!=', False)], 
            ['partner_id'], 
            ['partner_id']
        )
        clientes_totales_tickets = {c['partner_id'][1]: c['partner_id_count'] for c in tickets_por_cliente}
        _logger.info("Tickets por cliente: %s", clientes_totales_tickets)

        # Tickets por Máquina
        tickets_por_maquina = self.env['ticket.alquiler'].read_group(
            [('product_alquiler', '!=', False)], 
            ['product_alquiler'], 
            ['product_alquiler']
        )
        maquinas_totales_tickets = {m['product_alquiler'][1]: m['product_alquiler_count'] for m in tickets_por_maquina}
        _logger.info("Tickets por máquina: %s", maquinas_totales_tickets)

        # Tickets por mes en el año actual
        tickets_por_mes = {}
        for mes in range(1, 13):
            inicio_mes = date(today.year, mes, 1)
            if mes == 12:
                fin_mes = date(today.year + 1, 1, 1)
            else:
                fin_mes = date(today.year, mes + 1, 1)
            tickets_count_mes = self.env['ticket.alquiler'].search_count([
                ('agenda', '>=', inicio_mes),
                ('agenda', '<', fin_mes)
            ])
            tickets_por_mes[mes] = tickets_count_mes
        _logger.info("Tickets por mes: %s", tickets_por_mes)

        # Tickets por año en los últimos 5 años
        tickets_por_año = {}
        for i in range(5):
            año = today.year - i
            inicio_año = date(año, 1, 1)
            fin_año = date(año + 1, 1, 1)
            tickets_count_año = self.env['ticket.alquiler'].search_count([
                ('agenda', '>=', inicio_año),
                ('agenda', '<', fin_año)
            ])
            tickets_por_año[año] = tickets_count_año
        _logger.info("Tickets por año: %s", tickets_por_año)

        # Tickets por fecha
        tickets_por_fecha = {}
        ticket_groups = self.env['ticket.alquiler'].read_group(
            [],
            ['responsable', 'agenda:day'],
            ['agenda:day', 'responsable'],
            lazy=False
        )

        for group in ticket_groups:
            fecha = group['agenda:day']
            if fecha:
                if fecha not in tickets_por_fecha:
                    tickets_por_fecha[fecha] = []
                if group['responsable']:
                    tickets_por_fecha[fecha].append({
                        'tecnico': group['responsable'][0],
                        'tecnico_nombre': group['responsable'][1],
                    })


        # Crear el diccionario de retorno
        data = {
            'total_maquinas': total_maquinas,
            'maquinas_disponibles': maquinas_disponibles,
            'maquinas_separadas': maquinas_separadas,
            'maquinas_no_disponibles': maquinas_no_disponibles,
            'maquinas_sin_revisar': maquinas_sin_revisar,
            'maquinas_en_revision': maquinas_en_revision,
            'maquinas_finalizadas': maquinas_finalizadas,
            'maquinas_problemas': maquinas_problemas,
            'asesora_totales': asesora_totales,
            'total_reparaciones': total_reparaciones,
            'reparaciones_en_revision': reparaciones_en_revision,
            'reparaciones_hoy': reparaciones_hoy,
            'reparaciones_mes': reparaciones_mes,
            'reparaciones_ano': reparaciones_ano,
            'tecnicos_totales': tecnicos_totales,
            'total_tickets': total_tickets,
            'tickets_dia': tickets_dia,
            'tickets_mes': tickets_mes,
            'tickets_ano': tickets_ano,
            'tickets_por_fecha': tickets_por_fecha,
            'tecnicos_totales_tickets': tecnicos_totales_tickets,
            'clientes_totales_tickets': clientes_totales_tickets,
            'maquinas_totales_tickets': maquinas_totales_tickets,
            'tickets_por_mes': tickets_por_mes,
            'tickets_por_año': tickets_por_año,  # Añadido para el gráfico anual
        }

        # Imprimir el diccionario completo para verificar que contiene todos los datos
        _logger.info("Datos del dashboard: %s", data)

        return data

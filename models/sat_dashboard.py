from odoo import models, fields, api

class SatDashboard(models.Model):
    _name = 'sat.dashboard'
    _description = 'Dashboard de análisis'

    @api.model
    def get_dashboard_data(self):
        # Total de máquinas en `sat.sat`
        total_maquinas = self.env['sat.sat'].search_count([])

        # Maquinas por disponibilidad
        maquinas_disponibles = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'disponible')])
        maquinas_separadas = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'separada')])
        maquinas_no_disponibles = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'no_disponible')])

        # Maquinas por estado
        maquinas_sin_revisar = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'sin_revisar')])
        maquinas_en_revision = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'en_revision')])
        maquinas_finalizadas = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'finalizado')])
        maquinas_problemas = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'con_problemas')])
        # Puedes añadir más estados si es necesario.

        # Maquinas por asesora
        asesora_data = self.env['sat.sat'].read_group([('asesora_id', '!=', False)], ['asesora_id'], ['asesora_id'])
        asesora_totales = {a['asesora_id'][1]: a['asesora_id_count'] for a in asesora_data}

        # Total de reparaciones en `reparaciones.reparaciones`
        total_reparaciones = self.env['reparaciones.reparaciones'].search_count([])
        reparaciones_en_revision = self.env['reparaciones.reparaciones'].search_count([('estado_id', "=", 'en_revision')])

        # Reparaciones diarias, mensuales, y anuales
        today = fields.Date.today()
        reparaciones_hoy = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', today)])

        start_month = today.replace(day=1)
        reparaciones_mes = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', start_month)])

        start_year = today.replace(month=1, day=1)
        reparaciones_ano = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', start_year)])

        # Reparaciones por técnico
        reparaciones_por_tecnico = self.env['reparaciones.reparaciones'].read_group(
            [('responsable_id', '!=', False)], 
            ['responsable_id'], 
            ['responsable_id']
        )
        tecnicos_totales = {r['responsable_id'][1]: r['responsable_id_count'] for r in reparaciones_por_tecnico}

        # Devolver todos los datos en un diccionario para el dashboard
        return {
            # Datos de `sat.sat`
            'total_maquinas': total_maquinas,
            'maquinas_disponibles': maquinas_disponibles,
            'maquinas_separadas': maquinas_separadas,
            'maquinas_no_disponibles': maquinas_no_disponibles,
            'maquinas_sin_revisar': maquinas_sin_revisar,
            'maquinas_en_revision': maquinas_en_revision,
            'maquinas_finalizadas': maquinas_finalizadas,
            'maquinas_problemas': maquinas_problemas,
            'asesora_totales': asesora_totales,
            
            # Datos de `reparaciones.reparaciones`
            'total_reparaciones': total_reparaciones,
            'reparaciones_en_revision': reparaciones_en_revision,
            'reparaciones_hoy': reparaciones_hoy,
            'reparaciones_mes': reparaciones_mes,
            'reparaciones_ano': reparaciones_ano,
            'tecnicos_totales': tecnicos_totales,
        }

# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import timedelta

class ContadorAutomatico(models.Model):
    _inherit = 'contador.automatico'

    @api.model
    def get_dashboard_stats(self):
        """
        Devuelve un dict con estadísticas para el dashboard:
         - equipos_unicos_hoy: nº de series distintas procesadas hoy
         - equipos_unicos_semana: nº de series distintas procesadas últimos 7 días
         - total_equipos_sistema: nº total de equipos en 'alquiler'
         - total_registros_semana: nº de registros procesados últimos 7 días
         - eficiencia_sistema: % de registros procesados vs totales en últimos 7 días
         - estado_sistema: 'optimo'|'atencion'|'critico' según la eficiencia
        """
        hoy = fields.Date.today()
        hace_7 = hoy - timedelta(days=7)

        # Serie únicas procesadas hoy
        domain_hoy = [
            ('create_date', '>=', hoy),
            ('estado', '=', 'procesado'),
            ('serie_detectada', '!=', False),
        ]
        regs_hoy = self.search(domain_hoy)
        series_hoy = set(regs_hoy.mapped('serie_detectada'))

        # Serie únicas procesadas en últimos 7 días
        domain_sem = [
            ('create_date', '>=', hace_7),
            ('estado', '=', 'procesado'),
            ('serie_detectada', '!=', False),
        ]
        regs_sem = self.search(domain_sem)
        series_sem = set(regs_sem.mapped('serie_detectada'))

        # Total de equipos en el sistema
        total_equipos = self.env['alquiler'].search_count([])

        # Cálculo de eficiencia últimos 7 días
        tot_reg7 = self.search_count([('create_date', '>=', hace_7)])
        ok7      = self.search_count([('create_date', '>=', hace_7), ('estado', '=', 'procesado')])
        eficiencia = (ok7 / tot_reg7 * 100) if tot_reg7 else 0.0

        return {
            'equipos_unicos_hoy':    len(series_hoy),
            'equipos_unicos_semana': len(series_sem),
            'total_equipos_sistema': total_equipos,
            'total_registros_semana': len(regs_sem),
            'eficiencia_sistema':    round(eficiencia, 1),
            'estado_sistema':        'optimo' if eficiencia >= 90
                                     else 'atencion' if eficiencia >= 70
                                     else 'critico',
        }

    @api.model
    def get_dashboard_list(self, limit=100):
        """
        Devuelve una lista de dicts con el último registro procesado de cada serie:
         - id, serie, cliente, tipo, bn, color, total, fecha (ISO), estado.
        Se limita a `limit` elementos ordenados por fecha descendente.
        """
        domain = [
            ('estado', '=', 'procesado'),
            ('serie_detectada', '!=', False),
        ]
        all_regs = self.search(domain, order='create_date desc')
        unique = {}
        for rec in all_regs:
            if rec.serie_detectada not in unique:
                unique[rec.serie_detectada] = rec
            if len(unique) >= limit:
                break

        result = []
        for rec in unique.values():
            result.append({
                'id':      rec.id,
                'serie':   rec.serie_detectada,
                'cliente': rec.cliente_detectado or '—',
                'tipo':    rec.tipo_equipo_detectado,
                'bn':      rec.contador_bn_detectado or 0,
                'color':   rec.contador_color_detectado or 0,
                'total':   rec.contador_total_detectado or 0,
                'fecha':   rec.create_date.isoformat(),
                'estado':  rec.estado,
            })
        return result

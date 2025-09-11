# -*- coding: utf-8 -*-
from odoo import api, models
from datetime import datetime
import re

class ReportEstadoMaquinas(models.AbstractModel):
    _name = 'report.sat.reporte_estado_maquinas_pdf'  # report.<module>.<qweb_id>
    _description = 'Reporte PDF Estado de Máquinas (QWeb)'

    def _clean_html(self, html_text: str) -> str:
        if not html_text:
            return ''
        txt = re.sub(r'<br[^>]*>', '\n', html_text)
        txt = re.sub(r'</p>', '\n', txt)
        txt = re.sub(r'<.*?>', '', txt)
        txt = txt.replace('&nbsp;', ' ').replace('&amp;', '&')
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        txt = '\n'.join(lines)
        return (txt[:997] + '...') if len(txt) > 1000 else txt

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['reporte.estado.maquina'].browse(docids)

        # Labels para campos Selection
        estado_selection = dict(self.env['reporte.estado.maquina']._fields['estado_maquina'].selection)

        # Badges por estado
        estado_badges = {
            'lista': 'b-ok',
            'alquilada': 'b-ok',
            'revisada': 'b-info',
            'sin_revisar': 'b-warn',
            'con_problemas': 'b-warn',
            'partes': 'b-bad',
            'externo': 'b-info',
            'vendida': 'b-info',
        }

        # KPIs y distribución
        total = len(docs)
        by_state_map = {}
        operativos = 0
        problemas = 0
        sin_revisar = 0

        for r in docs:
            st = r.estado_maquina or 'sin_revisar'
            by = by_state_map.setdefault(st, {'qty': 0, 'contador_sum': 0})
            by['qty'] += 1
            by['contador_sum'] += r.contador_total or 0

            if st in ('lista', 'alquilada'):
                operativos += 1
            if st in ('con_problemas', 'partes'):
                problemas += 1
            if st == 'sin_revisar':
                sin_revisar += 1

        # Construir lista para tabla “Distribución por estados”
        by_state = []
        for st, agg in by_state_map.items():
            pct = (agg['qty'] / total * 100.0) if total else 0.0
            by_state.append({
                'key': st,
                'label': estado_selection.get(st, st),
                'qty': agg['qty'],
                'pct_str': f"{pct:.1f}%",
                'contador_sum': agg['contador_sum'],
            })
        # Ordenar por cantidad desc
        by_state.sort(key=lambda x: x['qty'], reverse=True)

        pct_operativos = (operativos / total * 100.0) if total else 0.0
        if pct_operativos >= 80:
            estado_global = 'excelente'
            badge_text = f"🟢 Excelente — {pct_operativos:.1f}% operativo"
        elif pct_operativos >= 60:
            estado_global = 'bueno'
            badge_text = f"🟡 Bueno — {pct_operativos:.1f}% operativo"
        elif pct_operativos >= 40:
            estado_global = 'regular'
            badge_text = f"🟠 Regular — {pct_operativos:.1f}% operativo"
        else:
            estado_global = 'critico'
            badge_text = f"🔴 Crítico — {pct_operativos:.1f}% operativo"

        # Mapas por id para acceso rápido en QWeb
        estado_labels = {r.id: estado_selection.get(r.estado_maquina, r.estado_maquina)
                         for r in docs}
        informes_limpios = {r.id: self._clean_html(r.informe_tecnico) for r in docs}

        kpis = {
            'total': total,
            'operativos': operativos,
            'problemas': problemas,
            'sin_revisar': sin_revisar,
            'pct_operativos_str': f"{pct_operativos:.1f}%",
            'estado_global': estado_global,
            'badge_text': badge_text,
        }

        values = {
            'doc_ids': docids,
            'doc_model': 'reporte.estado.maquina',
            'docs': docs,
            'data': data or {},
            'company': self.env.company,
            'date_print': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'kpis': kpis,
            'by_state': by_state,
            'estado_labels': estado_labels,
            'estado_badges': estado_badges,
            'informes_limpios': informes_limpios,
        }
        return values

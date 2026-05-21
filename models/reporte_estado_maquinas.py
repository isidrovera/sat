# -*- coding: utf-8 -*-

from odoo import api, models, fields
from datetime import datetime
import re


class ReportEstadoMaquinas(models.AbstractModel):
    _name = 'report.sat.reporte_estado_maquinas_pdf'
    _description = 'Reporte PDF Estado de Máquinas (QWeb)'

    # ==========================================================
    # Helpers
    # ==========================================================

    def _clean_html(self, html_text: str, limit=1000) -> str:
        """
        Limpia HTML simple para mostrarlo como texto plano en el PDF.

        Se usa para:
        - informe_tecnico
        - componentes_resumen
        - accesorios_resumen
        - intervenciones_resumen
        """
        if not html_text:
            return ''

        txt = str(html_text)

        txt = re.sub(r'<br\s*/?>', '\n', txt, flags=re.I)
        txt = re.sub(r'</p>', '\n', txt, flags=re.I)
        txt = re.sub(r'</div>', '\n', txt, flags=re.I)
        txt = re.sub(r'</li>', '\n', txt, flags=re.I)
        txt = re.sub(r'<li[^>]*>', '• ', txt, flags=re.I)
        txt = re.sub(r'<[^>]+>', '', txt)

        txt = (
            txt.replace('&nbsp;', ' ')
               .replace('&amp;', '&')
               .replace('&lt;', '<')
               .replace('&gt;', '>')
        )

        lines = [line.strip() for line in txt.splitlines() if line.strip()]
        txt = '\n'.join(lines)

        if limit and len(txt) > limit:
            return txt[:limit - 3] + '...'

        return txt

    def _fecha_nombre_pdf(self, docs):
        """
        Obtiene la fecha para nombre corto del PDF.

        Para varios registros:
        - usa la fecha_generacion máxima del conjunto.
        """
        if docs:
            fechas = docs.mapped('fecha_generacion')
            fecha = max(fechas) if fechas else fields.Date.context_today(self)
        else:
            fecha = fields.Date.context_today(self)

        return fecha

    # ==========================================================
    # Nombre corto del PDF
    # ==========================================================

    @api.model
    def _get_report_base_filename(self, docids, data=None):
        """
        Fuerza nombre corto para el archivo PDF.

        Esto ayuda cuando se imprimen varios registros desde:
        /report/pdf/sat.reporte_estado_maquinas_pdf/1,2,3,...

        Resultado esperado:
            Estado_Maq_20260521.pdf
        """
        docs = self.env['reporte.estado.maquina'].browse(docids)
        fecha = self._fecha_nombre_pdf(docs)

        return 'Estado_Maq_%s' % fecha.strftime('%Y%m%d')

    # ==========================================================
    # Valores del reporte QWeb
    # ==========================================================

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['reporte.estado.maquina'].browse(docids)

        estado_selection = dict(
            self.env['reporte.estado.maquina']._fields['estado_maquina'].selection
        )

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

        total = len(docs)
        by_state_map = {}
        operativos = 0
        problemas = 0
        sin_revisar = 0
        de_partes = 0
        alquiladas = 0
        revisadas = 0
        listas = 0

        partes_total = 0
        partes_otras_maquinas = 0
        partes_sat = 0

        for r in docs:
            estado = r.estado_maquina or 'sin_revisar'

            by = by_state_map.setdefault(estado, {
                'qty': 0,
                'contador_sum': 0,
            })

            by['qty'] += 1
            by['contador_sum'] += r.contador_total or 0

            if estado in ('lista', 'alquilada', 'revisada'):
                operativos += 1

            if estado in ('con_problemas', 'partes'):
                problemas += 1

            if estado == 'sin_revisar':
                sin_revisar += 1

            if estado == 'partes':
                de_partes += 1

            if estado == 'alquilada':
                alquiladas += 1

            if estado == 'revisada':
                revisadas += 1

            if estado == 'lista':
                listas += 1

            for parte in r.partes_retiradas_ids:
                partes_total += 1

                if parte.solicitud_partes_id:
                    partes_otras_maquinas += 1
                else:
                    partes_sat += 1

        by_state = []

        for estado, agg in by_state_map.items():
            pct = (agg['qty'] / total * 100.0) if total else 0.0

            by_state.append({
                'key': estado,
                'label': estado_selection.get(estado, estado),
                'qty': agg['qty'],
                'pct': pct,
                'pct_str': f"{pct:.1f}%",
                'contador_sum': agg['contador_sum'],
            })

        by_state.sort(key=lambda x: x['qty'], reverse=True)

        pct_operativos = (operativos / total * 100.0) if total else 0.0

        if pct_operativos >= 80:
            estado_global = 'excelente'
            badge_text = f"Excelente — {pct_operativos:.1f}% operativo"
        elif pct_operativos >= 60:
            estado_global = 'bueno'
            badge_text = f"Bueno — {pct_operativos:.1f}% operativo"
        elif pct_operativos >= 40:
            estado_global = 'regular'
            badge_text = f"Regular — {pct_operativos:.1f}% operativo"
        else:
            estado_global = 'critico'
            badge_text = f"Crítico — {pct_operativos:.1f}% operativo"

        estado_labels = {
            r.id: estado_selection.get(r.estado_maquina, r.estado_maquina)
            for r in docs
        }

        informes_limpios = {
            r.id: self._clean_html(r.informe_tecnico, limit=1000)
            for r in docs
        }

        componentes_limpios = {
            r.id: self._clean_html(r.componentes_resumen, limit=1200)
            for r in docs
        }

        accesorios_limpios = {
            r.id: self._clean_html(r.accesorios_resumen, limit=1200)
            for r in docs
        }

        intervenciones_limpias = {
            r.id: self._clean_html(r.intervenciones_resumen, limit=1200)
            for r in docs
        }

        kpis = {
            'total': total,
            'operativos': operativos,
            'problemas': problemas,
            'sin_revisar': sin_revisar,
            'de_partes': de_partes,
            'alquiladas': alquiladas,
            'revisadas': revisadas,
            'listas': listas,
            'pct_operativos': pct_operativos,
            'pct_operativos_str': f"{pct_operativos:.1f}%",
            'estado_global': estado_global,
            'badge_text': badge_text,
            'partes_total': partes_total,
            'partes_otras_maquinas': partes_otras_maquinas,
            'partes_sat': partes_sat,
        }

        return {
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
            'componentes_limpios': componentes_limpios,
            'accesorios_limpios': accesorios_limpios,
            'intervenciones_limpias': intervenciones_limpias,
        }
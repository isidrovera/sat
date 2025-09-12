# models/ticket_alquiler_informe.py
from odoo import models, api, fields, _
from collections import defaultdict

SCORE = {'cambio': 3, 'no': 3, 'desgaste': 2, 'si': 1, 'no_aplica': 0}

class TicketAlquiler(models.Model):
    _inherit = 'ticket.alquiler'

    def _get_checklist_state(self):
        """
        Lee todos los campos de checklist y devuelve una lista de dicts:
        [{'field':'adf_id','valor':'desgaste','tipo_id':..,'color':..,'label':'ADF','is_blocking':False}, ...]
        """
        self.ensure_one()
        Map = self.env['checklist.componente.map']
        result = []
        # 1) obtener todas las filas de mapa
        maps = Map.search([])
        map_by_field = {m.field_name: m for m in maps}

        # 2) iterar sobre campos reales existentes en este modelo
        for field_name, field in self._fields.items():
            if field_name in map_by_field and field.type == 'selection':
                val = getattr(self, field_name, False)
                if not val or val == 'no_aplica':
                    continue
                m = map_by_field[field_name]
                label = m.label or field.string or field_name
                result.append({
                    'field': field_name,
                    'valor': val,
                    'tipo_id': m.tipo_id.id,
                    'tipo_code': m.tipo_id.code,
                    'label': label,
                    'color': m.color or False,
                    'is_blocking': m.is_blocking or False,
                    'score': SCORE.get(val, 0),
                })
        return result

    def _decide_quality_and_state(self, findings):
        """
        Aplica la regla madre:
        - max score 3 -> mala, parcial/no_op si bloquea
        - max score 2 -> regular, operativo
        - max score 1 -> buena, operativo
        """
        if not findings:
            return ('buena', 'operativo')  # nada marcado: por defecto

        max_score = max(f['score'] for f in findings)
        any_blocking_3 = any(f['score'] == 3 and f['is_blocking'] for f in findings)

        if max_score >= 3:
            calidad = 'mala'
            estado = 'no_op' if any_blocking_3 else 'parcial'
        elif max_score == 2:
            calidad = 'regular'
            estado = 'operativo'
        else:
            calidad = 'buena'
            estado = 'operativo'
        return (calidad, estado)

    def _select_top_findings(self, findings, limit=3):
        """
        Ordena por score (desc), prioridad del componente (1/2/3) y secuencia.
        Usa la config del modelo para enriquecer prioridad.
        """
        self.ensure_one()
        # obtener prioridad por tipo/color desde modelo.maquina.componente
        prio_map = {}
        comp_lines = self.env['modelo.maquina.componente'].search([('modelo_id', '=', self.product_alquiler.name.id)])
        for l in comp_lines:
            key = (l.tipo_id.id, l.color or '')
            prio_map[key] = int(l.prioridad or '2')

        def key_fun(f):
            prio = prio_map.get((f['tipo_id'], f['color'] or ''), 2)
            return (-f['score'], prio)  # score alto primero, luego crítico (1) antes que 2/3

        ordered = sorted(findings, key=key_fun)
        return ordered[:limit]

    def _compose_text(self, calidad, estado_op, top_findings):
        """
        Arma 3–5 líneas usando reglas (informe.regla) y frases fallback.
        """
        Rule = self.env['informe.regla']

        # 1) Trabajo realizado (elige 1 por contexto simple)
        trabajo = "Limpieza de ruta y óptico; auto-gradación y pruebas."
        if any(f['tipo_code'] in ('RED',) for f in top_findings):
            trabajo = "Diagnóstico de red/driver; prueba de impresión interna."
        if any(f['tipo_code'] in ('ESCANER',) for f in top_findings):
            trabajo = "Verificación de credenciales y puertos de escaneo; prueba funcional."

        # 2) Hallazgos (frases desde reglas)
        frases_h = []
        recs = []

        for f in top_findings:
            rule = Rule.search([
                ('tipo_id', '=', f['tipo_id']),
                ('color', '=', f['color'] or False),
                ('estado_check', '=', f['valor'])
            ], limit=1)
            if rule:
                frases_h.append(rule.frase_hallazgo)
                recs.append(rule.frase_recomendacion)
            else:
                # Fallback breve
                if f['valor'] in ('cambio', 'no'):
                    frases_h.append(f"{f['label']} requiere intervención/cambio.")
                    recs.append(f"Cambio inmediato de {f['label']}.")
                elif f['valor'] == 'desgaste':
                    frases_h.append(f"{f['label']} con desgaste.")
                    recs.append(f"Programar servicio/kit en 30–45 días para {f['label']}.")

        # 3) Recomendación final (si hay “cambio/no” en los top → prioriza “Cambio inmediato”)
        prioridad_inmediata = any(v in ('cambio', 'no') for v in [f['valor'] for f in top_findings])
        recomendacion_final = "; ".join(recs) if recs else "Sin recomendaciones."

        # 4) Compose texto HTML corto
        estado_map = {
            'operativo': _("Operativo"),
            'parcial': _("Operativo parcial"),
            'no_op': _("No operativo"),
        }
        calidad_map = {'buena': 'Buena', 'regular': 'Regular', 'mala': 'Mala'}

        lineas = []
        lineas.append(f"<b>Trabajo realizado:</b> {trabajo}")
        lineas.append(f"<b>Estado actual:</b> <b>{estado_map.get(estado_op,'Operativo')}</b> · <b>Calidad: {calidad_map.get(calidad,'Regular')}</b>.")
        if frases_h:
            lineas.append(f"<b>Hallazgos:</b> " + "; ".join(frases_h) + ".")
        lineas.append(f"<b>Recomendación:</b> {recomendacion_final}")

        return "<br/>".join(lineas)

    def action_generar_informe(self):
        """
        Botón/acción para generar y escribir informe_id automáticamente.
        """
        for rec in self:
            findings = rec._get_checklist_state()
            calidad, estado_op = rec._decide_quality_and_state(findings)
            top_findings = rec._select_top_findings(findings, limit=3)
            html = rec._compose_text(calidad, estado_op, top_findings)
            rec.informe_id = html
        return True

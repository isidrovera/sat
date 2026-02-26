# -*- coding: utf-8 -*-
"""
Diagnóstico GPS Tracking — Traccar ↔ Odoo
==========================================
Wizard accesible desde un botón en Odoo.
Verifica toda la cadena sin necesidad de shell ni logs.

Archivo: models/tracking_diagnostico.py
"""
import logging
from datetime import date, timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class TrackingDiagnostico(models.TransientModel):
    _name = 'tracking.diagnostico'
    _description = 'Diagnóstico GPS Tracking'

    # ─── Input ────────────────────────────────────────────────────
    tecnico_id = fields.Many2one(
        'res.users', string='Técnico',
        help='Dejar vacío para diagnosticar todos',
    )
    simular_evento = fields.Selection([
        ('none', 'Solo diagnóstico'),
        ('deviceMoving', 'Simular: Técnico en movimiento'),
        ('geofenceEnter', 'Simular: Llegada al cliente'),
        ('geofenceExit', 'Simular: Salida del cliente'),
    ], string='Simular evento GPS', default='none')

    # ─── Output ───────────────────────────────────────────────────
    resultado = fields.Text(string='Resultado', readonly=True)
    tiene_errores = fields.Boolean(readonly=True)

    # ═══════════════════════════════════════════════════════════════
    #  DIAGNÓSTICO PRINCIPAL
    # ═══════════════════════════════════════════════════════════════

    def action_diagnosticar(self):
        self.ensure_one()
        lineas = []
        errores = False

        lineas.append("=" * 55)
        lineas.append("   DIAGNÓSTICO GPS TRACKING")
        lineas.append("=" * 55)

        # ── 1. Vínculos técnico ↔ Traccar ────────────────────────
        lineas.append("\n▶ 1. VÍNCULOS TÉCNICO ↔ TRACCAR")
        lineas.append("-" * 40)

        dominio_vinculos = [('activo', '=', True)]
        if self.tecnico_id:
            dominio_vinculos.append(('user_id', '=', self.tecnico_id.id))

        vinculos = self.env['tecnico.dispositivo.gps'].search(dominio_vinculos)

        if not vinculos:
            lineas.append("❌ SIN VÍNCULOS CONFIGURADOS")
            lineas.append("   → Ir a: Técnicos → Dispositivos GPS → Crear")
            errores = True
        else:
            for v in vinculos:
                lineas.append(
                    f"✅ {v.user_id.name} "
                    f"→ Traccar ID: {v.traccar_device_id} "
                    f"| Dispositivo: {v.nombre_dispositivo or 'sin nombre'}"
                )

        # ── 2. Tickets activos HOY ────────────────────────────────
        lineas.append("\n▶ 2. TICKETS ACTIVOS HOY")
        lineas.append("-" * 40)

        hoy_inicio, hoy_fin = self._get_rango_hoy()

        dominio_tickets = [
            ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
            ('agenda', '>=', hoy_inicio),
            ('agenda', '<=', hoy_fin),
        ]
        if self.tecnico_id:
            dominio_tickets.append(('responsable', '=', self.tecnico_id.id))

        tickets_hoy = self.env['ticket.alquiler'].search(
            dominio_tickets, order='responsable asc, agenda asc'
        )

        if not tickets_hoy:
            lineas.append("⚠️  SIN TICKETS CON AGENDA HOY")

            # Buscar tickets activos de otros días para diagnóstico
            dominio_otros = [
                ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
            ]
            if self.tecnico_id:
                dominio_otros.append(('responsable', '=', self.tecnico_id.id))

            tickets_otros = self.env['ticket.alquiler'].search(dominio_otros, limit=10)
            if tickets_otros:
                lineas.append("   Tickets activos con OTRA fecha (ignorados por GPS):")
                for t in tickets_otros:
                    lineas.append(
                        f"   ⚠️  {t.name} | {t.responsable.name} "
                        f"| Agenda: {t.agenda} | Estado: {t.estado}"
                    )
                lineas.append("   → CAUSA PROBABLE: agenda vacía o de otro día")
                errores = True
            else:
                lineas.append("   → No hay tickets activos en ninguna fecha")
                errores = True
        else:
            for t in tickets_hoy:
                desde_lima = self._fmt_hora(t.agenda)
                lineas.append(
                    f"✅ {t.name} | {t.responsable.name} "
                    f"| Agenda: {desde_lima} | Estado: {t.estado}"
                )

        # ── 3. Verificar tickets sin agenda ──────────────────────
        lineas.append("\n▶ 3. TICKETS SIN CAMPO AGENDA")
        lineas.append("-" * 40)

        dominio_sin_agenda = [
            ('estado', 'in', ['proceso', 'en_ruta']),
            ('agenda', '=', False),
        ]
        if self.tecnico_id:
            dominio_sin_agenda.append(('responsable', '=', self.tecnico_id.id))

        sin_agenda = self.env['ticket.alquiler'].search(dominio_sin_agenda, limit=10)
        if sin_agenda:
            lineas.append("❌ Tickets asignados SIN FECHA DE AGENDA:")
            for t in sin_agenda:
                lineas.append(f"   → {t.name} | {t.responsable.name}")
            lineas.append("   El GPS no puede procesar tickets sin agenda")
            errores = True
        else:
            lineas.append("✅ Todos los tickets tienen agenda configurada")

        # ── 4. Cruce: técnico tiene vínculo Y tickets hoy ────────
        lineas.append("\n▶ 4. CRUCE TÉCNICO ↔ TICKETS HOY")
        lineas.append("-" * 40)

        tecnicos_con_vinculo = vinculos.mapped('user_id')
        tecnicos_con_ticket = tickets_hoy.mapped('responsable')

        sin_ticket = tecnicos_con_vinculo - tecnicos_con_ticket
        sin_vinculo = tecnicos_con_ticket - tecnicos_con_vinculo

        if sin_ticket:
            for u in sin_ticket:
                lineas.append(f"⚠️  {u.name} tiene vínculo GPS pero SIN tickets hoy")

        if sin_vinculo:
            for u in sin_vinculo:
                lineas.append(
                    f"❌ {u.name} tiene tickets hoy pero SIN vínculo GPS "
                    f"→ el GPS no puede actualizar sus tickets"
                )
            errores = True

        if not sin_ticket and not sin_vinculo and vinculos and tickets_hoy:
            lineas.append("✅ Todos los técnicos con tickets tienen vínculo GPS")

        # ── 5. Verificar deviceNumber en vínculo ─────────────────
        lineas.append("\n▶ 5. VALIDACIÓN TRACCAR DEVICE ID")
        lineas.append("-" * 40)

        for v in vinculos:
            if not v.traccar_device_id:
                lineas.append(
                    f"❌ {v.user_id.name}: traccar_device_id está VACÍO "
                    f"→ el sistema no puede identificar el dispositivo"
                )
                errores = True
            elif v.traccar_device_id == 0:
                lineas.append(
                    f"❌ {v.user_id.name}: traccar_device_id = 0 (inválido)"
                )
                errores = True
            else:
                lineas.append(
                    f"✅ {v.user_id.name}: traccar_device_id = {v.traccar_device_id}"
                )

        # ── 6. Simulación de evento GPS ──────────────────────────
        if self.simular_evento != 'none' and vinculos:
            lineas.append(f"\n▶ 6. SIMULACIÓN: {self.simular_evento}")
            lineas.append("-" * 40)

            for v in vinculos:
                lineas.append(
                    f"Simulando '{self.simular_evento}' "
                    f"para {v.user_id.name} (device_id={v.traccar_device_id})..."
                )
                try:
                    resultado = self.env['ticket.alquiler'].api_actualizar_estado_gps(
                        v.traccar_device_id,
                        self.simular_evento,
                        {},
                    )
                    if resultado.get('success'):
                        actualizados = resultado.get('tickets_actualizados', [])
                        msg = resultado.get('message', '')
                        if actualizados:
                            lineas.append(f"✅ Tickets actualizados:")
                            for t in actualizados:
                                lineas.append(
                                    f"   → {t['name']} ahora en estado: {t['estado']}"
                                )
                        elif msg:
                            lineas.append(f"ℹ️  {msg}")
                        else:
                            lineas.append("ℹ️  Sin tickets que actualizar")
                    else:
                        lineas.append(f"❌ Error: {resultado.get('error')}")
                        errores = True
                except Exception as e:
                    lineas.append(f"❌ Excepción: {str(e)}")
                    errores = True

        # ── Resumen final ─────────────────────────────────────────
        lineas.append("\n" + "=" * 55)
        if errores:
            lineas.append("⚠️  HAY PROBLEMAS QUE CORREGIR (ver detalles arriba)")
        else:
            lineas.append("✅ TODO OK — la cadena GPS → Odoo está configurada correctamente")
        lineas.append("=" * 55)

        self.write({
            'resultado': '\n'.join(lineas),
            'tiene_errores': errores,
        })

        # Reabrir el wizard con el resultado
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tracking.diagnostico',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ═══════════════════════════════════════════════════════════════
    #  HELPERS
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _get_rango_hoy():
        from pytz import timezone as pytz_tz, UTC as pytz_UTC
        lima = pytz_tz('America/Lima')
        hoy_lima = date.today()
        inicio = lima.localize(
            fields.Datetime.from_string(f"{hoy_lima} 00:00:00")
        ).astimezone(pytz_UTC).replace(tzinfo=None)
        fin = lima.localize(
            fields.Datetime.from_string(f"{hoy_lima} 23:59:59")
        ).astimezone(pytz_UTC).replace(tzinfo=None)
        return inicio, fin

    @staticmethod
    def _fmt_hora(dt):
        if not dt:
            return 'Sin agenda'
        try:
            from pytz import timezone as pytz_tz, UTC
            return UTC.localize(dt).astimezone(
                pytz_tz('America/Lima')
            ).strftime('%d/%m/%Y %H:%M')
        except Exception:
            return str(dt)
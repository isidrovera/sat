# -*- coding: utf-8 -*-

import logging
from datetime import datetime

import pytz

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SatRevisionNotificaciones(models.Model):
    _inherit = 'sat.sat'

    # ==========================================================
    # WRITE: detectar cambio a PARA REVISIÓN
    # ==========================================================

    def write(self, vals):
        vals = dict(vals or {})

        estado_nuevo = vals.get('estado_ventas_id')
        debe_evaluar_para_revision = estado_nuevo == 'para_revision'

        estados_anteriores = {}
        if debe_evaluar_para_revision:
            for record in self:
                estados_anteriores[record.id] = record.estado_ventas_id

            # Si alguien cambia manualmente el estado desde statusbar/lista
            # y no viene fecha_para_revision, colocamos fecha actual.
            if not vals.get('fecha_para_revision'):
                vals['fecha_para_revision'] = fields.Datetime.now()

        result = super().write(vals)

        if debe_evaluar_para_revision:
            for record in self:
                estado_anterior = estados_anteriores.get(record.id)

                # Solo notificar si realmente entró a para_revision.
                if estado_anterior != 'para_revision' and record.estado_ventas_id == 'para_revision':
                    try:
                        record._sat_notificar_para_revision()
                    except Exception as e:
                        _logger.exception(
                            "[SAT NOTIF PARA_REVISION] Error notificando máquina ID %s: %s",
                            record.id,
                            e,
                        )
                        try:
                            record.message_post(
                                body=_(
                                    "⚠️ Error generando notificación de máquina para revisión:<br/>%s"
                                ) % str(e),
                                subtype_xmlid='mail.mt_note',
                            )
                        except Exception:
                            pass

        return result

    # ==========================================================
    # HELPERS FECHA / LIMA
    # ==========================================================

    def _sat_get_lima_tz(self):
        return pytz.timezone('America/Lima')

    def _sat_datetime_utc_to_lima(self, dt_value=False):
        if not dt_value:
            return False

        if isinstance(dt_value, str):
            dt_value = fields.Datetime.from_string(dt_value)

        if not dt_value:
            return False

        if dt_value.tzinfo is None:
            utc_dt = pytz.utc.localize(dt_value)
        else:
            utc_dt = dt_value.astimezone(pytz.utc)

        return utc_dt.astimezone(self._sat_get_lima_tz())

    def _sat_now_lima(self):
        utc_now = pytz.utc.localize(datetime.utcnow())
        return utc_now.astimezone(self._sat_get_lima_tz())

    def _sat_get_fecha_para_revision_lima(self):
        self.ensure_one()

        dt_value = self.fecha_para_revision or fields.Datetime.now()
        lima_dt = self._sat_datetime_utc_to_lima(dt_value)

        if not lima_dt:
            lima_dt = self._sat_now_lima()

        return lima_dt

    # ==========================================================
    # TELÉFONOS
    # ==========================================================

    def _sat_get_asesora_user(self):
        self.ensure_one()

        try:
            if self.cliente_id and self.cliente_id.asesora_id:
                return self.cliente_id.asesora_id
        except Exception:
            pass

        return False

    def _sat_get_asesora_phone(self):
        self.ensure_one()

        phone = ''

        # Primero usar el campo ya calculado en sat.sat
        if self.asesora_mobile_clean:
            phone = self.asesora_mobile_clean

        # Respaldo desde usuario asesora
        if not phone:
            asesora = self._sat_get_asesora_user()
            if asesora and asesora.partner_id:
                phone = asesora.partner_id.mobile or asesora.partner_id.phone or ''

        return phone or ''

    def _sat_get_copia_comercial_phone(self):
        ICP = self.env['ir.config_parameter'].sudo()

        phone = ICP.get_param(
            'sat.notificaciones_comerciales_copia_phone',
            '19373717674'
        )

        return phone or ''

    # ==========================================================
    # COLA DE REVISIÓN
    # ==========================================================

    def _sat_get_cola_revision_info(self):
        """
        Calcula:
        - pendientes antes de esta máquina
        - puesto en cola
        - cantidad actualmente en revisión

        Considera para_revision por fecha_para_revision asc, id asc.
        """
        self.ensure_one()

        Sat = self.env['sat.sat'].sudo()

        fecha_ref = self.fecha_para_revision or fields.Datetime.now()

        # Pendientes antes: máquinas en para_revision anteriores a esta.
        pendientes_antes_domain = [
            ('estado_ventas_id', '=', 'para_revision'),
            ('id', '!=', self.id),
            ('fecha_para_revision', '!=', False),
            '|',
                ('fecha_para_revision', '<', fecha_ref),
                '&',
                    ('fecha_para_revision', '=', fecha_ref),
                    ('id', '<', self.id),
        ]

        pendientes_antes = Sat.search_count(pendientes_antes_domain)

        # Si hay registros para_revision sin fecha, no los usamos para orden,
        # pero sí se puede revisar luego si se desea incluirlos.
        en_revision_count = Sat.search_count([
            ('estado_ventas_id', '=', 'en_revision'),
        ])

        puesto = pendientes_antes + 1

        return {
            'pendientes_antes': pendientes_antes,
            'puesto': puesto,
            'en_revision_count': en_revision_count,
        }

    # ==========================================================
    # MENSAJE
    # ==========================================================

    def _sat_build_msg_para_revision(self):
        self.ensure_one()

        cliente = self.cliente_id.name if self.cliente_id else 'NA'
        asesora_user = self._sat_get_asesora_user()
        asesora = asesora_user.name if asesora_user else (self.asesora_id or 'NA')
        modelo = self.name.name if self.name else 'NA'
        serie = self.serie_id or 'NA'

        lima_dt = self._sat_get_fecha_para_revision_lima()
        fecha_lima = lima_dt.strftime('%d/%m/%Y %H:%M')

        cola = self._sat_get_cola_revision_info()

        msg = f"""*Máquina colocada para revisión*

*Cliente:* {cliente}
*Asesora:* {asesora}
*Modelo:* {modelo}
*Serie:* {serie}

*Fecha:* {fecha_lima}
*Puesto en cola:* {cola.get('puesto')}
*Pendientes antes:* {cola.get('pendientes_antes')}
*En revisión:* {cola.get('en_revision_count')}

Se notificará cuando taller inicie la revisión.
"""

        return msg

    # ==========================================================
    # CREAR NOTIFICACIONES
    # ==========================================================

    def _sat_notificar_para_revision(self):
        """
        Crea notificaciones por log cuando la máquina entra a para_revision.

        Condición obligatoria para notificar a asesora y copia comercial:
        1. La máquina debe tener cliente.
        2. El cliente debe tener asesora.
        3. La asesora debe tener celular.

        Si falta cualquiera de esos datos, NO se notifica ni a asesora ni a copia comercial.
        """
        self.ensure_one()

        Log = self.env['sat.notificacion.log'].sudo()

        cliente = self.cliente_id if self.cliente_id else False
        asesora_user = self._sat_get_asesora_user()
        asesora_phone = self._sat_get_asesora_phone()
        copia_phone = self._sat_get_copia_comercial_phone()

        created_logs = self.env['sat.notificacion.log'].sudo().browse()

        # ------------------------------------------------------
        # VALIDACIONES OBLIGATORIAS
        # ------------------------------------------------------
        if not cliente:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Para revisión</b> "
                    "porque la máquina no tiene cliente asignado."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        if not asesora_user:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Para revisión</b> "
                    "porque el cliente no tiene asesora asignada."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        if not asesora_phone:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Para revisión</b> "
                    "porque la asesora no tiene celular configurado."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        msg = self._sat_build_msg_para_revision()

        fecha_key = ''
        if self.fecha_para_revision:
            fecha_key = fields.Datetime.to_string(self.fecha_para_revision)

        # ------------------------------------------------------
        # 1) Asesora
        # ------------------------------------------------------
        unique_key = "para_revision:maquina:%s:asesora:%s:%s" % (
            self.id,
            asesora_phone,
            fecha_key or self.write_date or self.id,
        )

        log = Log.create_notification(
            event_type='para_revision',
            phone=asesora_phone,
            message=msg,
            recipient_type='asesora',
            recipient_name=asesora_user.name,
            maquina=self,
            cliente=cliente,
            asesora_user=asesora_user,
            respect_business_hours=True,
            force_send=False,
            unique_key=unique_key,
            source_record=self,
            send_immediately=True,
            note='Notificación generada al colocar máquina para revisión.',
        )

        if log:
            created_logs |= log

        # ------------------------------------------------------
        # 2) Copia comercial
        # Solo se crea si también existe cliente + asesora + celular.
        # ------------------------------------------------------
        if copia_phone and copia_phone != asesora_phone:
            unique_key = "para_revision:maquina:%s:copia:%s:%s" % (
                self.id,
                copia_phone,
                fecha_key or self.write_date or self.id,
            )

            log = Log.create_notification(
                event_type='copia_comercial',
                phone=copia_phone,
                message=msg,
                recipient_type='copia_comercial',
                recipient_name='Copia comercial',
                maquina=self,
                cliente=cliente,
                asesora_user=asesora_user,
                respect_business_hours=True,
                force_send=False,
                unique_key=unique_key,
                source_record=self,
                send_immediately=True,
                note='Copia comercial de máquina colocada para revisión.',
            )

            if log:
                created_logs |= log

        # ------------------------------------------------------
        # Chatter resumen
        # ------------------------------------------------------
        try:
            body = _(
                "📲 <b>Notificaciones de Para revisión generadas</b><br/>"
                "<b>Máquina:</b> %(modelo)s<br/>"
                "<b>Serie:</b> %(serie)s<br/>"
                "<b>Cliente:</b> %(cliente)s<br/>"
                "<b>Asesora:</b> %(asesora_name)s<br/>"
                "<b>Celular asesora:</b> %(asesora_phone)s<br/>"
                "<b>Copia comercial:</b> %(copia)s<br/>"
                "<b>Registros creados:</b> %(count)s"
            ) % {
                'modelo': self.name.name if self.name else '',
                'serie': self.serie_id or '',
                'cliente': cliente.name if cliente else '',
                'asesora_name': asesora_user.name if asesora_user else '',
                'asesora_phone': asesora_phone or '',
                'copia': copia_phone or 'Sin número',
                'count': len(created_logs),
            }

            self.message_post(body=body, subtype_xmlid='mail.mt_note')

        except Exception as e:
            _logger.warning(
                "[SAT NOTIF PARA_REVISION] No se pudo publicar chatter máquina ID %s: %s",
                self.id,
                e,
            )

        return created_logs
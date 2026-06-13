# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ReparacionesNotificaciones(models.Model):
    _inherit = 'reparaciones.reparaciones'

    # ==========================================================
    # CREATE
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for record in records:
            try:
                if record.estado_id == 'en_revision':
                    record._sat_notificar_revision_iniciada()
            except Exception as e:
                _logger.exception(
                    "[SAT NOTIF REVISION_INICIADA] Error notificando desde create reparación ID %s: %s",
                    record.id,
                    e,
                )

        return records

    # ==========================================================
    # WRITE
    # ==========================================================

    def write(self, vals):
        vals = dict(vals or {})

        debe_evaluar_revision = vals.get('estado_id') == 'en_revision'

        estados_anteriores = {}
        if debe_evaluar_revision:
            for record in self:
                estados_anteriores[record.id] = record.estado_id

        result = super().write(vals)

        if debe_evaluar_revision:
            for record in self:
                estado_anterior = estados_anteriores.get(record.id)

                if estado_anterior != 'en_revision' and record.estado_id == 'en_revision':
                    try:
                        record._sat_notificar_revision_iniciada()
                    except Exception as e:
                        _logger.exception(
                            "[SAT NOTIF REVISION_INICIADA] Error notificando reparación ID %s: %s",
                            record.id,
                            e,
                        )
                        try:
                            record.message_post(
                                body=_(
                                    "⚠️ Error generando notificación de revisión iniciada:<br/>%s"
                                ) % str(e),
                                subtype_xmlid='mail.mt_note',
                            )
                        except Exception:
                            pass

        return result

    # ==========================================================
    # HELPERS GENERALES
    # ==========================================================

    def _sat_get_copia_comercial_phone_revision(self):
        ICP = self.env['ir.config_parameter'].sudo()

        phone = ICP.get_param(
            'sat.notificaciones_comerciales_copia_phone',
            '19373717674'
        )

        return phone or ''

    def _sat_get_asesora_user_revision(self):
        self.ensure_one()

        try:
            if self.maquina_id and self.maquina_id.cliente_id and self.maquina_id.cliente_id.asesora_id:
                return self.maquina_id.cliente_id.asesora_id
        except Exception:
            pass

        try:
            if self.cliente_id and self.cliente_id.asesora_id:
                return self.cliente_id.asesora_id
        except Exception:
            pass

        return False

    def _sat_get_asesora_phone_revision(self):
        self.ensure_one()

        phone = ''

        if getattr(self, 'asesora_mobile_clean', False):
            phone = self.asesora_mobile_clean

        if not phone and self.maquina_id and getattr(self.maquina_id, 'asesora_mobile_clean', False):
            phone = self.maquina_id.asesora_mobile_clean

        if not phone:
            asesora = self._sat_get_asesora_user_revision()
            if asesora and asesora.partner_id:
                phone = asesora.partner_id.mobile or asesora.partner_id.phone or ''

        return phone or ''

    def _sat_get_cliente_revision(self):
        self.ensure_one()

        if self.cliente_id:
            return self.cliente_id

        if self.maquina_id and self.maquina_id.cliente_id:
            return self.maquina_id.cliente_id

        return False

    def _sat_get_modelo_revision(self):
        self.ensure_one()

        if self.nombre_maquina:
            return self.nombre_maquina

        if self.maquina_id and self.maquina_id.name:
            return self.maquina_id.name.name

        return 'NA'

    def _sat_get_serie_revision(self):
        self.ensure_one()

        if self.serie_id:
            return self.serie_id

        if self.maquina_id and self.maquina_id.serie_id:
            return self.maquina_id.serie_id

        return 'NA'

    # ==========================================================
    # MENSAJE: REVISIÓN INICIADA
    # ==========================================================

    def _sat_build_msg_revision_iniciada(self):
        self.ensure_one()

        cliente = self._sat_get_cliente_revision()
        cliente_name = cliente.name if cliente else 'NA'
        asesora_user = self._sat_get_asesora_user_revision()
        asesora = asesora_user.name if asesora_user else 'NA'

        modelo = self._sat_get_modelo_revision()
        serie = self._sat_get_serie_revision()
        tecnico = self.responsable_id.name if self.responsable_id else 'NA'

        msg = f"""*Revisión iniciada*

*Cliente:* {cliente_name}
*Asesora:* {asesora}
*Modelo:* {modelo}
*Serie:* {serie}
*Técnico:* {tecnico}

El equipo ya fue tomado por taller y se encuentra en revisión.
"""

        return msg

    # ==========================================================
    # NOTIFICACIÓN: REVISIÓN INICIADA
    # ==========================================================

    def _sat_notificar_revision_iniciada(self):
        """
        Crea logs de notificación cuando la reparación entra en revisión.

        Condición obligatoria para notificar a asesora y copia comercial:
        1. La reparación/máquina debe tener cliente.
        2. El cliente debe tener asesora.
        3. La asesora debe tener celular.

        Si falta cualquiera de esos datos, NO se notifica ni a asesora ni a copia comercial.
        """
        self.ensure_one()

        Log = self.env['sat.notificacion.log'].sudo()

        maquina = self.maquina_id if self.maquina_id else False
        cliente = self._sat_get_cliente_revision()

        asesora_user = self._sat_get_asesora_user_revision()
        asesora_phone = self._sat_get_asesora_phone_revision()
        copia_phone = self._sat_get_copia_comercial_phone_revision()

        created_logs = self.env['sat.notificacion.log'].sudo().browse()

        # ------------------------------------------------------
        # VALIDACIONES OBLIGATORIAS
        # ------------------------------------------------------
        if not cliente:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Revisión iniciada</b> "
                    "porque la reparación no tiene cliente asignado."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        if not asesora_user:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Revisión iniciada</b> "
                    "porque el cliente no tiene asesora asignada."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        if not asesora_phone:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Revisión iniciada</b> "
                    "porque la asesora no tiene celular configurado."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        msg = self._sat_build_msg_revision_iniciada()

        # ------------------------------------------------------
        # 1) Asesora
        # ------------------------------------------------------
        unique_key = "revision_iniciada:reparacion:%s:asesora:%s" % (
            self.id,
            asesora_phone,
        )

        log = Log.create_notification(
            event_type='revision_iniciada',
            phone=asesora_phone,
            message=msg,
            recipient_type='asesora',
            recipient_name=asesora_user.name,
            maquina=maquina,
            reparacion=self,
            cliente=cliente,
            asesora_user=asesora_user,
            respect_business_hours=True,
            force_send=False,
            unique_key=unique_key,
            source_record=self,
            send_immediately=True,
            note='Notificación generada cuando la reparación entró en revisión.',
        )

        if log:
            created_logs |= log

        # ------------------------------------------------------
        # 2) Copia comercial
        # Solo se crea si también existe cliente + asesora + celular.
        # ------------------------------------------------------
        if copia_phone and copia_phone != asesora_phone:
            unique_key = "revision_iniciada:reparacion:%s:copia:%s" % (
                self.id,
                copia_phone,
            )

            log = Log.create_notification(
                event_type='copia_comercial',
                phone=copia_phone,
                message=msg,
                recipient_type='copia_comercial',
                recipient_name='Copia comercial',
                maquina=maquina,
                reparacion=self,
                cliente=cliente,
                asesora_user=asesora_user,
                respect_business_hours=True,
                force_send=False,
                unique_key=unique_key,
                source_record=self,
                send_immediately=True,
                note='Copia comercial de revisión iniciada.',
            )

            if log:
                created_logs |= log

        # ------------------------------------------------------
        # Chatter resumen
        # ------------------------------------------------------
        try:
            body = _(
                "📲 <b>Notificaciones de revisión iniciada generadas</b><br/>"
                "<b>Reparación:</b> %(rep)s<br/>"
                "<b>Cliente:</b> %(cliente)s<br/>"
                "<b>Modelo:</b> %(modelo)s<br/>"
                "<b>Serie:</b> %(serie)s<br/>"
                "<b>Técnico:</b> %(tecnico)s<br/>"
                "<b>Asesora:</b> %(asesora_name)s<br/>"
                "<b>Celular asesora:</b> %(asesora_phone)s<br/>"
                "<b>Copia comercial:</b> %(copia)s<br/>"
                "<b>Registros creados:</b> %(count)s"
            ) % {
                'rep': self.name or '',
                'cliente': cliente.name if cliente else '',
                'modelo': self._sat_get_modelo_revision(),
                'serie': self._sat_get_serie_revision(),
                'tecnico': self.responsable_id.name if self.responsable_id else '',
                'asesora_name': asesora_user.name if asesora_user else '',
                'asesora_phone': asesora_phone or '',
                'copia': copia_phone or 'Sin número',
                'count': len(created_logs),
            }

            self.message_post(body=body, subtype_xmlid='mail.mt_note')

        except Exception as e:
            _logger.warning(
                "[SAT NOTIF REVISION_INICIADA] No se pudo publicar chatter reparación ID %s: %s",
                self.id,
                e,
            )

        return created_logs

    # ==========================================================
    # MENSAJE: FINALIZACIÓN
    # ==========================================================

    def _sat_build_msg_finalizacion(self):
        self.ensure_one()

        cliente = self._sat_get_cliente_revision()
        cliente_name = cliente.name if cliente else 'NA'

        asesora_user = self._sat_get_asesora_user_revision()
        asesora = asesora_user.name if asesora_user else 'NA'

        modelo = self._sat_get_modelo_revision()
        serie = self._sat_get_serie_revision()
        tecnico = self.responsable_id.name if self.responsable_id else 'NA'

        pdf_url = ''
        gallery_url = ''

        try:
            if hasattr(self, 'generate_pdf_report_url'):
                pdf_url = self.generate_pdf_report_url() or ''
        except Exception as e:
            _logger.warning(
                "[SAT NOTIF FINALIZACION] No se pudo generar URL PDF reparación ID %s: %s",
                self.id,
                e,
            )

        try:
            if hasattr(self, '_get_gallery_url'):
                gallery_url = self._get_gallery_url() or ''
        except Exception as e:
            _logger.warning(
                "[SAT NOTIF FINALIZACION] No se pudo generar URL galería reparación ID %s: %s",
                self.id,
                e,
            )

        extra_urls = ""

        if pdf_url:
            extra_urls += "\n*Reporte PDF:*\n%s\n" % pdf_url

        if gallery_url:
            extra_urls += "\n*Galería de fotos:*\n%s\n" % gallery_url

        msg = f"""*Reparación finalizada*

    *Cliente:* {cliente_name}
    *Asesora:* {asesora}
    *Modelo:* {modelo}
    *Serie:* {serie}
    *Técnico:* {tecnico}

    El equipo fue finalizado por taller.
    {extra_urls}"""

        return msg

    # ==========================================================
    # NOTIFICACIÓN: FINALIZACIÓN
    # ==========================================================

    def _sat_notificar_finalizacion_reparacion(self):
        """
        Crea logs de finalización de reparación.

        Condición obligatoria para notificar a asesora y copia comercial:
        1. La reparación/máquina debe tener cliente.
        2. El cliente debe tener asesora.
        3. La asesora debe tener celular.

        Si falta cualquiera de esos datos, NO se notifica ni a asesora ni a copia comercial.
        """
        self.ensure_one()

        Log = self.env['sat.notificacion.log'].sudo()

        maquina = self.maquina_id if self.maquina_id else False
        cliente = self._sat_get_cliente_revision()

        asesora_user = self._sat_get_asesora_user_revision()
        asesora_phone = self._sat_get_asesora_phone_revision()
        copia_phone = self._sat_get_copia_comercial_phone_revision()

        created_logs = self.env['sat.notificacion.log'].sudo().browse()

        # ------------------------------------------------------
        # VALIDACIONES OBLIGATORIAS
        # ------------------------------------------------------
        if not cliente:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Finalización</b> "
                    "porque la reparación no tiene cliente asignado."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        if not asesora_user:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Finalización</b> "
                    "porque el cliente no tiene asesora asignada."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        if not asesora_phone:
            self.message_post(
                body=_(
                    "ℹ️ No se generó notificación de <b>Finalización</b> "
                    "porque la asesora no tiene celular configurado."
                ),
                subtype_xmlid='mail.mt_note',
            )
            return created_logs

        msg = self._sat_build_msg_finalizacion()

        # ------------------------------------------------------
        # 1) Asesora
        # ------------------------------------------------------
        unique_key = "finalizacion:reparacion:%s:asesora:%s" % (
            self.id,
            asesora_phone,
        )

        log = Log.create_notification(
            event_type='finalizacion',
            phone=asesora_phone,
            message=msg,
            recipient_type='asesora',
            recipient_name=asesora_user.name,
            maquina=maquina,
            reparacion=self,
            cliente=cliente,
            asesora_user=asesora_user,
            respect_business_hours=True,
            force_send=False,
            unique_key=unique_key,
            source_record=self,
            send_immediately=True,
            note='Notificación generada al finalizar reparación.',
        )

        if log:
            created_logs |= log

        # ------------------------------------------------------
        # 2) Copia comercial
        # Solo se crea si también existe cliente + asesora + celular.
        # ------------------------------------------------------
        if copia_phone and copia_phone != asesora_phone:
            unique_key = "finalizacion:reparacion:%s:copia:%s" % (
                self.id,
                copia_phone,
            )

            log = Log.create_notification(
                event_type='copia_comercial',
                phone=copia_phone,
                message=msg,
                recipient_type='copia_comercial',
                recipient_name='Copia comercial',
                maquina=maquina,
                reparacion=self,
                cliente=cliente,
                asesora_user=asesora_user,
                respect_business_hours=True,
                force_send=False,
                unique_key=unique_key,
                source_record=self,
                send_immediately=True,
                note='Copia comercial de finalización de reparación.',
            )

            if log:
                created_logs |= log

        # ------------------------------------------------------
        # Chatter resumen
        # ------------------------------------------------------
        try:
            body = _(
                "📲 <b>Notificaciones de finalización generadas</b><br/>"
                "<b>Reparación:</b> %(rep)s<br/>"
                "<b>Cliente:</b> %(cliente)s<br/>"
                "<b>Modelo:</b> %(modelo)s<br/>"
                "<b>Serie:</b> %(serie)s<br/>"
                "<b>Técnico:</b> %(tecnico)s<br/>"
                "<b>Asesora:</b> %(asesora_name)s<br/>"
                "<b>Celular asesora:</b> %(asesora_phone)s<br/>"
                "<b>Copia comercial:</b> %(copia)s<br/>"
                "<b>Registros creados:</b> %(count)s"
            ) % {
                'rep': self.name or '',
                'cliente': cliente.name if cliente else '',
                'modelo': self._sat_get_modelo_revision(),
                'serie': self._sat_get_serie_revision(),
                'tecnico': self.responsable_id.name if self.responsable_id else '',
                'asesora_name': asesora_user.name if asesora_user else '',
                'asesora_phone': asesora_phone or '',
                'copia': copia_phone or 'Sin número',
                'count': len(created_logs),
            }

            self.message_post(body=body, subtype_xmlid='mail.mt_note')

        except Exception as e:
            _logger.warning(
                "[SAT NOTIF FINALIZACION] No se pudo publicar chatter reparación ID %s: %s",
                self.id,
                e,
            )

        return created_logs
    # ==========================================================
    # OVERRIDE DEL MÉTODO EXISTENTE
    # ==========================================================

    def enviar_mensaje_finalizacion_asesora(self):
        """
        Reemplaza el envío directo anterior.

        Antes:
            enviaba WhatsApp directo a la asesora.

        Ahora:
            crea registros en sat.notificacion.log para que:
            - se registre todo,
            - se respete horario laboral,
            - se pueda reintentar,
            - se envíe copia comercial,
            - quede historial en máquina/reparación.
        """
        logs = self.env['sat.notificacion.log'].sudo().browse()

        for record in self:
            try:
                new_logs = record._sat_notificar_finalizacion_reparacion()
                if new_logs:
                    logs |= new_logs
            except Exception as e:
                _logger.exception(
                    "[SAT NOTIF FINALIZACION] Error notificando finalización reparación ID %s: %s",
                    record.id,
                    e,
                )

                try:
                    record.message_post(
                        body=_(
                            "⚠️ Error generando notificación de finalización:<br/>%s"
                        ) % str(e),
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception:
                    pass

        return logs
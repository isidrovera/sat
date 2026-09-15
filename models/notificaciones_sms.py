# -*- coding: utf-8 -*-

import logging
import re
import time
import uuid
from urllib.parse import urlsplit

import requests

from odoo import fields, models
from odoo.exceptions import AccessError, UserError


_logger = logging.getLogger(__name__)


class TicketNotificacionesSms(models.Model):
    _inherit = "ticket.alquiler"

    # ============================================================
    # CAMPOS OPCIONALES PARA PRUEBAS DESDE EL MISMO TICKET
    # ============================================================

    sms_prueba_usuario_id = fields.Many2one(
        "res.users",
        string="Usuario para prueba SMS",
        domain=[("share", "=", False)],
        groups="base.group_system",
        copy=False,
        help=(
            "Usuario destinatario del botón Probar SMS a usuario. "
            "No cambia el técnico responsable del servicio."
        ),
    )

    sms_prueba_mensaje = fields.Text(
        string="Mensaje de prueba SMS",
        groups="base.group_system",
        copy=False,
        help=(
            "Texto utilizado por los botones de prueba. "
            "Si está vacío, se genera un mensaje con el número del ticket."
        ),
    )

    # ============================================================
    # NORMALIZACIÓN DEL NÚMERO
    # ============================================================

    def _normalizar_numero_sms(self, phone):
        """
        Acepta:
        - Celular peruano de 9 dígitos.
        - Celular peruano con prefijo 51.
        - Número internacional con +.
        - Número internacional con prefijo 00.

        No acepta listas de números ni identificadores de WhatsApp.
        """
        numero = str(phone or "").strip()

        if not numero:
            return False

        if not re.fullmatch(r"\+?[0-9\s().-]+", numero):
            return False

        numero = re.sub(r"[\s().-]", "", numero)

        if numero.startswith("00"):
            numero = "+" + numero[2:]

        elif re.fullmatch(r"9[0-9]{8}", numero):
            numero = "+51" + numero

        elif re.fullmatch(r"519[0-9]{8}", numero):
            numero = "+" + numero

        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", numero):
            return False

        return numero

    # ============================================================
    # CONFIGURACIÓN DESDE PARÁMETROS DEL SISTEMA
    # ============================================================

    def _sms_configuracion(self):
        parametros = self.env["ir.config_parameter"].sudo()

        enabled = str(
            parametros.get_param("sat.sms_enabled", "False")
        ).strip().lower()

        url = (
            parametros.get_param("sat.sms_gateway_url") or ""
        ).strip()

        authorization = (
            parametros.get_param("sat.sms_gateway_authorization") or ""
        ).strip()

        habilitado = enabled in ("true", "1", "yes", "si")
        errores = []

        if not habilitado:
            errores.append(
                "El envío está deshabilitado. Configure "
                "sat.sms_enabled = True."
            )

        url_valida = False

        try:
            parsed = urlsplit(url)

            url_valida = bool(
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.fragment
            )

            # Detectar también puertos mal escritos.
            _ = parsed.port

        except ValueError:
            url_valida = False

        if not url_valida:
            errores.append(
                "Configure una URL HTTP/HTTPS válida en "
                "sat.sms_gateway_url."
            )

        if not authorization:
            errores.append(
                "Falta configurar sat.sms_gateway_authorization."
            )

        elif "\r" in authorization or "\n" in authorization:
            errores.append(
                "La autorización contiene saltos de línea."
            )

        return {
            "enabled": habilitado,
            "url": url,
            "authorization": authorization,
            "errors": errores,
        }

    # ============================================================
    # DIAGNÓSTICO SIN EXPONER DATOS SENSIBLES
    # ============================================================

    def _sms_detalle_seguro(
        self,
        value,
        authorization,
        numero,
        mensaje,
    ):
        texto = str(value or "")

        for sensible in (
            authorization,
            numero,
            numero.lstrip("+"),
            mensaje,
        ):
            if sensible:
                texto = texto.replace(sensible, "[oculto]")

        # Evitar mostrar URLs que pudieran contener credenciales.
        texto = re.sub(
            r"https?://\S+",
            "[URL oculta]",
            texto,
        )

        texto = re.sub(
            r"(?i)(authorization|api[_-]?key|token|password)"
            r"\s*[=:]\s*[^\s,;]+",
            r"\1=[oculto]",
            texto,
        )

        return re.sub(r"\s+", " ", texto).strip()[:600]

    # ============================================================
    # ENVÍO SMS POR TRACCAR
    # ============================================================

    def _enviar_sms(self, phone, message):
        """
        Envía una solicitud HTTP a Traccar SMS Gateway.

        success=True:
            La pasarela aceptó la solicitud HTTP.
            No confirma entrega al celular.

        status='unknown':
            El resultado es incierto.
            Revisar la pasarela antes de repetir.

        No realiza reintentos automáticos.
        No modifica estados del servicio ni envía WhatsApp.
        """
        referencia = uuid.uuid4().hex[:12]
        inicio = time.monotonic()

        numero = self._normalizar_numero_sms(phone)
        destino = "***" + numero[-4:] if numero else "inválido"

        _logger.info(
            "[SMS %s] Inicio | usuario=%s | tickets=%s | destino=%s",
            referencia,
            self.env.uid,
            self.ids,
            destino,
        )

        def terminar(
            estado,
            error=False,
            codigo_http=False,
            detalle=False,
        ):
            duracion = round(time.monotonic() - inicio, 3)
            success = estado == "accepted"

            resultado = {
                "success": success,
                "status": estado,
                "error": error,
                "status_code": codigo_http,
                "detail": detalle,
                "reference": referencia,
                "duration_seconds": duracion,
            }

            registrar = _logger.info if success else _logger.warning

            registrar(
                "[SMS %s] Resultado=%s | HTTP=%s | "
                "duración=%ss | destino=%s | motivo=%s",
                referencia,
                estado,
                codigo_http or "-",
                duracion,
                destino,
                error or "Solicitud aceptada por la pasarela",
            )

            return resultado

        config = self._sms_configuracion()

        if config["errors"]:
            return terminar(
                "configuration_error",
                " ".join(config["errors"]),
            )

        if not numero:
            return terminar(
                "invalid",
                "Número inválido. Use un celular peruano de "
                "9 dígitos o un número internacional con +.",
            )

        if not isinstance(message, str) or not message.strip():
            return terminar(
                "invalid",
                "El mensaje SMS no puede estar vacío.",
            )

        mensaje = message.strip()
        authorization = config["authorization"]

        _logger.info(
            "[SMS %s] Ejecutando POST | caracteres=%s | "
            "timeout conexión=10s | timeout lectura=30s",
            referencia,
            len(mensaje),
        )

        try:
            response = requests.post(
                config["url"],
                headers={
                    "Authorization": authorization,
                    "Content-Type": "application/json",
                },
                json={
                    "to": numero,
                    "message": mensaje,
                },
                timeout=(10, 30),
                allow_redirects=False,
            )

        except requests.exceptions.SSLError:
            return terminar(
                "error",
                "Error SSL. Revise el certificado HTTPS "
                "de la pasarela.",
            )

        except requests.exceptions.ConnectTimeout:
            return terminar(
                "unknown",
                "Tiempo de conexión agotado. Revise la red, "
                "la dirección y la disponibilidad de la pasarela "
                "antes de reenviar.",
            )

        except requests.exceptions.Timeout:
            return terminar(
                "unknown",
                "La pasarela no respondió a tiempo. El SMS podría "
                "haberse procesado. Compruebe antes de reenviar.",
            )

        except requests.exceptions.ConnectionError:
            return terminar(
                "unknown",
                "Error de conexión. Revise DNS, red, puerto y "
                "disponibilidad del teléfono. Compruebe la pasarela "
                "antes de reenviar.",
            )

        except requests.exceptions.RequestException:
            return terminar(
                "error",
                "No se pudo completar la solicitud HTTP. "
                "Revise la URL y la autorización configuradas.",
            )

        codigo_http = response.status_code

        try:
            data = response.json()
        except ValueError:
            data = None

        detalle = False

        if isinstance(data, dict):
            detalle_original = data.get("error") or data.get("message")

            if isinstance(detalle_original, str):
                detalle = self._sms_detalle_seguro(
                    detalle_original,
                    authorization,
                    numero,
                    mensaje,
                )

        if not 200 <= codigo_http < 300:
            errores_http = {
                400: (
                    "Solicitud rechazada. Revise el número y "
                    "el formato esperado por la pasarela."
                ),
                401: (
                    "Autorización rechazada. Revise el token "
                    "o la API key."
                ),
                403: "Acceso denegado por la pasarela.",
                404: (
                    "Ruta no encontrada. Revise la URL completa "
                    "configurada."
                ),
                405: (
                    "La dirección no admite solicitudes POST. "
                    "Revise el endpoint."
                ),
                429: (
                    "Límite de solicitudes alcanzado. "
                    "No se reintentó automáticamente."
                ),
            }

            error = errores_http.get(
                codigo_http,
                "La pasarela respondió HTTP %s." % codigo_http,
            )

            if 300 <= codigo_http < 400:
                error += (
                    " No se siguió la redirección. "
                    "Configure la URL final."
                )

            if codigo_http >= 500:
                error += (
                    " Resultado incierto. Compruebe la pasarela "
                    "antes de reenviar."
                )

            return terminar(
                "unknown" if codigo_http >= 500 else "rejected",
                error,
                codigo_http,
                detalle,
            )

        if isinstance(data, dict) and (
            data.get("success") is False or data.get("error")
        ):
            return terminar(
                "rejected",
                "La pasarela informó un error al procesar el SMS.",
                codigo_http,
                detalle,
            )

        return terminar(
            "accepted",
            codigo_http=codigo_http,
        )

    # ============================================================
    # SEGURIDAD DE LOS BOTONES DE PRUEBA
    # ============================================================

    def _sms_validar_acceso_prueba(self):
        self.ensure_one()

        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                "Solo los administradores de Ajustes pueden "
                "realizar pruebas de SMS."
            )

        self.check_access_rights("write")
        self.check_access_rule("write")

    # ============================================================
    # MENSAJE Y RESULTADO DE LAS PRUEBAS
    # ============================================================

    def _sms_obtener_mensaje_prueba(self):
        self.ensure_one()

        if (
            self.sms_prueba_mensaje
            and self.sms_prueba_mensaje.strip()
        ):
            return self.sms_prueba_mensaje.strip()

        return (
            "Copier: prueba de SMS del ticket %s. "
            "Por favor, confirme la recepcion."
        ) % (self.name or self.id)

    def _sms_mostrar_resultado(self, resultado, destinatario):
        self.ensure_one()

        estados = {
            "accepted": "Aceptado por la pasarela",
            "configuration_error": "Error de configuración",
            "invalid": "Datos inválidos",
            "unknown": "Resultado incierto",
            "rejected": "Solicitud rechazada",
            "error": "Error de envío",
        }

        lineas = [
            "Destinatario: %s" % destinatario,
            "Estado: %s" % estados.get(
                resultado.get("status"),
                resultado.get("status", "Desconocido"),
            ),
        ]

        if resultado.get("reference"):
            lineas.append(
                "Referencia en logs: %s" % resultado["reference"]
            )

        lineas.append(
            "HTTP: %s"
            % (
                resultado.get("status_code")
                or "Sin respuesta HTTP"
            )
        )

        if resultado.get("duration_seconds") is not None:
            lineas.append(
                "Duración: %s segundos"
                % resultado["duration_seconds"]
            )

        if resultado.get("success"):
            lineas.append(
                "La pasarela aceptó la solicitud. "
                "Confirme la recepción en el celular."
            )
        else:
            lineas.append(
                "Error: %s"
                % (
                    resultado.get("error")
                    or "No se pudo confirmar el envío."
                )
            )

        if resultado.get("detail"):
            lineas.append(
                "Detalle de la pasarela: %s"
                % resultado["detail"]
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Prueba SMS — %s" % (self.name or self.id),
                "message": "\n".join(lineas),
                "type": (
                    "success"
                    if resultado.get("success")
                    else "warning"
                ),
                "sticky": True,
            },
        }

    def _sms_ejecutar_prueba(self, numero, destinatario, tipo_prueba):
        self._sms_validar_acceso_prueba()

        _logger.info(
            "[SMS PRUEBA] tipo=%s | ticket_id=%s | operador=%s",
            tipo_prueba,
            self.id,
            self.env.uid,
        )

        resultado = self._enviar_sms(
            numero,
            self._sms_obtener_mensaje_prueba(),
        )

        return self._sms_mostrar_resultado(
            resultado,
            destinatario,
        )

    # ============================================================
    # BOTÓN: REVISAR CONFIGURACIÓN, SIN ENVIAR
    # ============================================================

    def action_verificar_configuracion_sms(self):
        self._sms_validar_acceso_prueba()

        config = self._sms_configuracion()
        errores = config["errors"]

        _logger.info(
            "[SMS CONFIG] ticket_id=%s | operador=%s | "
            "habilitado=%s | cantidad_errores=%s",
            self.id,
            self.env.uid,
            config["enabled"],
            len(errores),
        )

        if errores:
            mensaje = "\n".join(
                "- %s" % error
                for error in errores
            )
        else:
            mensaje = (
                "SMS habilitados.\n"
                "URL con formato válido.\n"
                "Token/API key configurado.\n\n"
                "Esta revisión es local: no verifica que la clave "
                "sea correcta ni que la pasarela sea accesible."
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Configuración SMS — sin envío",
                "message": mensaje,
                "type": "warning" if errores else "info",
                "sticky": True,
            },
        }

    # ============================================================
    # BOTÓN: PRUEBA AL TÉCNICO RESPONSABLE
    # Conserva el nombre del botón indicado anteriormente.
    # ============================================================

    def action_probar_sms(self):
        self._sms_validar_acceso_prueba()

        if not self.responsable:
            raise UserError(
                "Seleccione primero el técnico responsable "
                "del ticket."
            )

        numero = self.responsable_mobile_clean

        if not numero or numero == "NA":
            raise UserError(
                "El técnico responsable no tiene un celular válido. "
                "Revise su información de contacto."
            )

        return self._sms_ejecutar_prueba(
            numero,
            self.responsable.display_name,
            "tecnico_responsable",
        )

    # ============================================================
    # BOTÓN: PRUEBA AL CONTACTO DEL VISTO BUENO
    # ============================================================

    def action_probar_sms_conformidad(self):
        self._sms_validarceso_prueba() if False else None
        self._sms_validar_acceso_prueba()

        if not self.conformidad_registrada:
            raise UserError(
                "El ticket todavía no tiene un visto bueno completo."
            )

        if not self.conformidad_celular:
            raise UserError(
                "El visto bueno no tiene un celular registrado."
            )

        return self._sms_ejecutar_prueba(
            self.conformidad_celular,
            self.conformidad_nombre or "Contacto del visto bueno",
            "contacto_visto_bueno",
        )

    # ============================================================
    # BOTÓN: PRUEBA A UN USUARIO SELECCIONADO
    # ============================================================

    def action_probar_sms_usuario(self):
        self._sms_validar_acceso_prueba()

        usuario = self.sms_prueba_usuario_id

        if not usuario:
            raise UserError(
                "Seleccione un usuario en el campo "
                "'Usuario para prueba SMS'."
            )

        contacto = usuario.partner_id
        numero = contacto.mobile or contacto.phone

        if not numero:
            raise UserError(
                "El usuario seleccionado no tiene móvil ni teléfono "
                "en su contacto asociado."
            )

        return self._sms_ejecutar_prueba(
            numero,
            usuario.display_name,
            "usuario_seleccionado",
        )

# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date, datetime, timedelta, time
import logging

_logger = logging.getLogger(__name__)


class SatDashboard(models.Model):
    _name = "sat.dashboard"
    _description = "Dashboard de análisis"

    # =========================================================
    # UTILIDADES
    # =========================================================

    @api.model
    def _agrupar_registros(self, modelo, campo, domain=None):
        """
        Agrupa registros usando la API de Odoo 19.

        Devuelve un diccionario:
            {nombre: cantidad}

        Evita utilizar read_group(), obsoleto en Odoo 19.
        """
        domain = list(domain or [])
        domain.append((campo, "!=", False))

        grupos = self.env[modelo]._read_group(
            domain=domain,
            groupby=[campo],
            aggregates=["__count"],
        )

        resultado = {}

        for valor, cantidad in grupos:
            if not valor:
                continue

            if hasattr(valor, "display_name"):
                nombre = valor.display_name
            else:
                nombre = str(valor)

            resultado[nombre] = (
                resultado.get(nombre, 0) + cantidad
            )

        return resultado

    @api.model
    def _fecha_rango(self, fecha_inicio, fecha_fin):
        """
        Convierte fechas locales a límites UTC para consultar
        campos Datetime como create_date.
        """
        inicio_local = datetime.combine(
            fecha_inicio, time.min
        )
        fin_local = datetime.combine(
            fecha_fin, time.min
        )

        inicio_utc = fields.Datetime.to_string(
            fields.Datetime.context_timestamp(
                self.with_context(tz="UTC"),
                inicio_local
            )
        )

        # Los valores almacenados por Odoo se encuentran en UTC.
        # Para convertir correctamente fechas locales se utiliza
        # context_timestamp sobre los UTC candidatos.
        from datetime import timezone
        from zoneinfo import ZoneInfo

        tz_name = (
            self.env.context.get("tz")
            or self.env.user.tz
            or "America/Lima"
        )

        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("America/Lima")

        def convertir(fecha):
            local = fecha.replace(tzinfo=tz)
            utc = local.astimezone(timezone.utc)
            return fields.Datetime.to_string(
                utc.replace(tzinfo=None)
            )

        return convertir(inicio_local), convertir(fin_local)

    @api.model
    def _serializar_contacto(self, contacto):
        """Devuelve un valor JSON compatible."""
        if not contacto:
            return ""

        if hasattr(contacto, "display_name"):
            return contacto.display_name

        return str(contacto)

    @api.model
    def _etiqueta_bloqueo(self, equipo):
        """Obtiene la etiqueta del estado de bloqueo."""
        campo = equipo._fields.get("estado_bloqueo")

        if not campo:
            return equipo.estado_bloqueo or ""

        seleccion = campo._description_selection(
            equipo.env
        )

        return dict(seleccion).get(
            equipo.estado_bloqueo,
            equipo.estado_bloqueo or ""
        )

    @api.model
    def _serializar_equipo(self, equipo, detallado=False):
        """
        Convierte un equipo de alquiler a datos JSON.

        Conserva los campos utilizados por el dashboard.
        """
        fecha_bloqueo = ""

        if equipo.fecha_bloqueo:
            fecha_local = fields.Datetime.context_timestamp(
                equipo,
                equipo.fecha_bloqueo
            )
            fecha_bloqueo = fecha_local.strftime(
                "%d/%m/%Y %H:%M"
            )

        modelo = ""

        if equipo.name:
            if hasattr(equipo.name, "display_name"):
                modelo = equipo.name.display_name
            else:
                modelo = str(equipo.name)

        datos = {
            "id": equipo.id,
            "serie": equipo.serie or "",
            "cliente": (
                equipo.cliente_id.display_name
                if equipo.cliente_id else ""
            ),
            "modelo": modelo,
            "estado_bloqueo": (
                equipo.estado_bloqueo or ""
            ),
            "estado_label": self._etiqueta_bloqueo(
                equipo
            ),
            "motivo": equipo.motivo_bloqueo or "",
            "fecha_bloqueo": fecha_bloqueo,
            "direccion": equipo.direccion or "",
            "contacto": self._serializar_contacto(
                equipo.contacto_id
            ),
            "celular": equipo.celular or "",
        }

        if detallado:
            datos.update({
                "ip_equipo": (
                    equipo.ip_equipo or ""
                ),
                "acceso_remoto": bool(
                    equipo.acceso_remoto_disponible
                ),
                "puede_suspender": (
                    equipo.estado_bloqueo == "activo"
                ),
                "puede_bloquear": (
                    equipo.estado_bloqueo
                    in ["activo", "suspendido"]
                ),
                "puede_desbloquear": (
                    equipo.estado_bloqueo
                    in ["bloqueado", "suspendido"]
                ),
            })

        return datos

    # =========================================================
    # DASHBOARD PRINCIPAL
    # =========================================================

    @api.model
    def get_dashboard_data(self):

        Sat = self.env["sat.sat"]
        Alquiler = self.env["alquiler"]
        Reparaciones = self.env[
            "reparaciones.reparaciones"
        ]
        Tickets = self.env["ticket.alquiler"]

        hoy = fields.Date.context_today(self)

        inicio_mes = hoy.replace(day=1)
        inicio_ano = hoy.replace(
            month=1, day=1
        )

        manana = hoy + timedelta(days=1)

        if hoy.month == 12:
            siguiente_mes = date(
                hoy.year + 1, 1, 1
            )
        else:
            siguiente_mes = date(
                hoy.year, hoy.month + 1, 1
            )

        siguiente_ano = date(
            hoy.year + 1, 1, 1
        )

        # -----------------------------------------------------
        # MÁQUINAS SAT
        # -----------------------------------------------------

        total_maquinas = Sat.search_count([
            ("estado_ventas_id", "!=", "entregada")
        ])

        maquinas_disponibles = Sat.search_count([
            ("disponibilidad_id", "=", "disponible")
        ])

        maquinas_separadas = Sat.search_count([
            ("disponibilidad_id", "=", "separada")
        ])

        maquinas_no_disponibles = Sat.search_count([
            ("disponibilidad_id", "=", "no_disponible")
        ])

        maquinas_sin_revisar = Sat.search_count([
            ("estado_ventas_id", "=", "sin_revisar")
        ])

        maquinas_con_problemas = Sat.search_count([
            ("estado_ventas_id", "=", "con_problemas")
        ])

        maquinas_de_partes = Sat.search_count([
            ("estado_ventas_id", "=", "de_partes")
        ])

        maquinas_en_revision = Sat.search_count([
            ("estado_ventas_id", "=", "en_revision")
        ])

        maquinas_finalizadas = Sat.search_count([
            ("estado_ventas_id", "=", "finalizado")
        ])

        maquinas_para_revision = Sat.search_count([
            ("estado_ventas_id", "=", "para_revision")
        ])

        _logger.info(
            "[SAT DASHBOARD] Máquinas total=%s "
            "disponibles=%s separadas=%s "
            "no_disponibles=%s",
            total_maquinas,
            maquinas_disponibles,
            maquinas_separadas,
            maquinas_no_disponibles,
        )

        # -----------------------------------------------------
        # MÁQUINAS DE ALQUILER
        # -----------------------------------------------------

        # Excluir externos y vendidos simultáneamente.
        dominio_alquiler = [
            ("estado_alquiler_id", "!=", "externo"),
            ("estado_alquiler_id", "!=", "vendida"),
        ]

        total_maquinas_alquiler = (
            Alquiler.search_count(dominio_alquiler)
        )

        alquiler_sin_revisar = Alquiler.search_count([
            ("estado_alquiler_id", "=", "sin_revisar")
        ])

        alquiler_alquilada = Alquiler.search_count([
            ("estado_alquiler_id", "=", "alquilada")
        ])

        alquiler_revisada = Alquiler.search_count([
            ("estado_alquiler_id", "=", "revisada")
        ])

        alquiler_lista = Alquiler.search_count([
            ("estado_alquiler_id", "=", "lista")
        ])

        alquiler_con_problemas = Alquiler.search_count([
            ("estado_alquiler_id", "=", "con_problemas")
        ])

        _logger.info(
            "[SAT DASHBOARD] Alquiler total=%s "
            "sin_revisar=%s alquiladas=%s",
            total_maquinas_alquiler,
            alquiler_sin_revisar,
            alquiler_alquilada,
        )

        # -----------------------------------------------------
        # ALQUILER POR CLIENTE
        # -----------------------------------------------------

        grupos_cliente = Alquiler._read_group(
            domain=dominio_alquiler + [
                ("cliente_id", "!=", False)
            ],
            groupby=["cliente_id"],
            aggregates=["__count"],
        )

        alquiler_por_cliente = []
        clientes_totales_alquiler = {}

        for cliente, cantidad in grupos_cliente:
            if not cliente:
                continue

            nombre = cliente.display_name

            clientes_totales_alquiler[nombre] = (
                clientes_totales_alquiler.get(
                    nombre, 0
                ) + cantidad
            )

            # Mantener la estructura antigua para JS.
            alquiler_por_cliente.append({
                "cliente_id": [
                    cliente.id,
                    nombre
                ],
                "cliente_id_count": cantidad,
                "__count": cantidad,
            })

        # -----------------------------------------------------
        # MÁQUINAS POR ASESORA
        # -----------------------------------------------------

        asesora_totales = self._agrupar_registros(
            "sat.sat",
            "asesora_id"
        )

        # -----------------------------------------------------
        # REPARACIONES
        # -----------------------------------------------------

        total_reparaciones = (
            Reparaciones.search_count([])
        )

        reparaciones_en_revision = (
            Reparaciones.search_count([
                ("estado_id", "=", "en_revision")
            ])
        )

        reparaciones_finalizado = (
            Reparaciones.search_count([
                ("estado_id", "=", "finalizado")
            ])
        )

        # Rangos de create_date.
        inicio_hoy_utc, fin_hoy_utc = (
            self._fecha_rango(hoy, manana)
        )

        inicio_mes_utc, fin_mes_utc = (
            self._fecha_rango(
                inicio_mes, siguiente_mes
            )
        )

        inicio_ano_utc, fin_ano_utc = (
            self._fecha_rango(
                inicio_ano, siguiente_ano
            )
        )

        reparaciones_hoy = (
            Reparaciones.search_count([
                ("create_date", ">=", inicio_hoy_utc),
                ("create_date", "<", fin_hoy_utc),
            ])
        )

        reparaciones_mes = (
            Reparaciones.search_count([
                ("create_date", ">=", inicio_mes_utc),
                ("create_date", "<", fin_mes_utc),
            ])
        )

        reparaciones_ano = (
            Reparaciones.search_count([
                ("create_date", ">=", inicio_ano_utc),
                ("create_date", "<", fin_ano_utc),
            ])
        )

        tecnicos_totales = self._agrupar_registros(
            "reparaciones.reparaciones",
            "responsable_id"
        )

        _logger.info(
            "[SAT DASHBOARD] Reparaciones total=%s "
            "hoy=%s mes=%s año=%s",
            total_reparaciones,
            reparaciones_hoy,
            reparaciones_mes,
            reparaciones_ano,
        )

        # -----------------------------------------------------
        # TICKETS DE ALQUILER
        # -----------------------------------------------------

        total_tickets = Tickets.search_count([])

        tickets_nuevos = Tickets.search_count([
            ("estado", "=", "nuevo")
        ])

        tickets_proceso = Tickets.search_count([
            ("estado", "=", "proceso")
        ])

        tickets_en_ruta = Tickets.search_count([
            ("estado", "=", "en_ruta")
        ])

        tickets_en_sitio = Tickets.search_count([
            ("estado", "=", "en_sitio")
        ])

        tickets_en_revision = Tickets.search_count([
            ("estado", "=", "en_revision")
        ])

        tickets_finalizado = Tickets.search_count([
            ("estado", "=", "finalizado")
        ])

        # Fechas de agenda.
        tickets_dia = Tickets.search_count([
            ("agenda", ">=", hoy),
            ("agenda", "<", manana),
        ])

        tickets_mes = Tickets.search_count([
            ("agenda", ">=", inicio_mes),
            ("agenda", "<", siguiente_mes),
        ])

        tickets_ano = Tickets.search_count([
            ("agenda", ">=", inicio_ano),
            ("agenda", "<", siguiente_ano),
        ])

        _logger.info(
            "[SAT DASHBOARD] Tickets total=%s "
            "día=%s mes=%s año=%s",
            total_tickets,
            tickets_dia,
            tickets_mes,
            tickets_ano,
        )

        # -----------------------------------------------------
        # TICKETS AGRUPADOS
        # -----------------------------------------------------

        tecnicos_totales_tickets = (
            self._agrupar_registros(
                "ticket.alquiler",
                "responsable"
            )
        )

        clientes_totales_tickets = (
            self._agrupar_registros(
                "ticket.alquiler",
                "partner_id"
            )
        )

        maquinas_totales_tickets = (
            self._agrupar_registros(
                "ticket.alquiler",
                "product_alquiler"
            )
        )

        # -----------------------------------------------------
        # TICKETS POR MES
        # -----------------------------------------------------

        tickets_por_mes = {}

        for mes in range(1, 13):
            inicio = date(hoy.year, mes, 1)

            if mes == 12:
                fin = date(
                    hoy.year + 1, 1, 1
                )
            else:
                fin = date(
                    hoy.year, mes + 1, 1
                )

            tickets_por_mes[mes] = (
                Tickets.search_count([
                    ("agenda", ">=", inicio),
                    ("agenda", "<", fin),
                ])
            )

        # -----------------------------------------------------
        # TICKETS POR AÑO
        # -----------------------------------------------------

        tickets_por_año = {}

        for i in range(5):
            ano = hoy.year - i

            inicio = date(ano, 1, 1)
            fin = date(ano + 1, 1, 1)

            tickets_por_año[ano] = (
                Tickets.search_count([
                    ("agenda", ">=", inicio),
                    ("agenda", "<", fin),
                ])
            )

        # -----------------------------------------------------
        # TICKETS POR FECHA Y TÉCNICO
        # -----------------------------------------------------

        tickets_por_fecha = {}

        try:
            tickets = Tickets.search([
                ("agenda", "!=", False),
                ("responsable", "!=", False),
            ])

            for ticket in tickets:
                if not ticket.agenda:
                    continue

                fecha = fields.Date.to_string(
                    ticket.agenda
                )

                tickets_por_fecha.setdefault(
                    fecha, []
                )

                tickets_por_fecha[fecha].append({
                    "tecnico": ticket.responsable.id,
                    "tecnico_nombre": (
                        ticket.responsable.display_name
                    ),
                })

        except Exception:
            _logger.exception(
                "[SAT DASHBOARD] Error procesando "
                "tickets por fecha"
            )
            tickets_por_fecha = {}

        # -----------------------------------------------------
        # REPARACIONES POR FECHA
        # -----------------------------------------------------

        reparaciones_por_fecha = {}

        try:
            reparaciones = Reparaciones.search([
                ("create_date", "!=", False),
                ("responsable_id", "!=", False),
            ])

            for reparacion in reparaciones:
                if not reparacion.create_date:
                    continue

                fecha_local = (
                    fields.Datetime.context_timestamp(
                        reparacion,
                        reparacion.create_date
                    )
                )

                fecha = fecha_local.strftime(
                    "%Y-%m-%d"
                )

                reparaciones_por_fecha.setdefault(
                    fecha, []
                )

                reparaciones_por_fecha[fecha].append({
                    "tecnico": (
                        reparacion.responsable_id.id
                    ),
                    "tecnico_nombre": (
                        reparacion.responsable_id.display_name
                    ),
                })

        except Exception:
            _logger.exception(
                "[SAT DASHBOARD] Error procesando "
                "reparaciones por fecha"
            )
            reparaciones_por_fecha = {}

        # -----------------------------------------------------
        # SISTEMA DE BLOQUEO
        # -----------------------------------------------------

        dominio_alquilados = [
            ("estado_alquiler_id", "=", "alquilada")
        ]

        def contar_estado(estado):
            return Alquiler.search_count(
                dominio_alquilados + [
                    ("estado_bloqueo", "=", estado)
                ]
            )

        equipos_activos = contar_estado(
            "activo"
        )

        equipos_suspendidos = contar_estado(
            "suspendido"
        )

        equipos_bloqueados = contar_estado(
            "bloqueado"
        )

        equipos_no_accesibles = contar_estado(
            "no_accesible"
        )

        equipos_pendiente_bloqueo = contar_estado(
            "pendiente_bloqueo"
        )

        equipos_pendiente_desbloqueo = contar_estado(
            "pendiente_desbloqueo"
        )

        total_alquilados = Alquiler.search_count(
            dominio_alquilados
        )

        equipos_atencion = Alquiler.search(
            dominio_alquilados + [
                (
                    "estado_bloqueo",
                    "in",
                    [
                        "pendiente_bloqueo",
                        "pendiente_desbloqueo",
                        "no_accesible",
                    ],
                )
            ],
            limit=10,
            order="fecha_bloqueo desc",
        )

        equipos_atencion_data = [
            self._serializar_equipo(equipo)
            for equipo in equipos_atencion
        ]

        bloqueo_stats = {
            "activos": equipos_activos,
            "suspendidos": equipos_suspendidos,
            "bloqueados": equipos_bloqueados,
            "no_accesibles": equipos_no_accesibles,
            "pendiente_bloqueo": (
                equipos_pendiente_bloqueo
            ),
            "pendiente_desbloqueo": (
                equipos_pendiente_desbloqueo
            ),
            "total": total_alquilados,
        }

        # -----------------------------------------------------
        # RESPUESTA COMPLETA
        # -----------------------------------------------------

        data = {
            "total_maquinas": total_maquinas,
            "maquinas_disponibles": maquinas_disponibles,
            "maquinas_separadas": maquinas_separadas,
            "maquinas_no_disponibles": maquinas_no_disponibles,
            "maquinas_sin_revisar": maquinas_sin_revisar,
            "maquinas_para_revision": maquinas_para_revision,
            "maquinas_en_revision": maquinas_en_revision,
            "maquinas_finalizadas": maquinas_finalizadas,
            "maquinas_con_problemas": maquinas_con_problemas,
            "maquinas_de_partes": maquinas_de_partes,
            "asesora_totales": asesora_totales,

            "total_reparaciones": total_reparaciones,
            "reparaciones_en_revision": reparaciones_en_revision,
            "reparaciones_finalizado": reparaciones_finalizado,
            "reparaciones_hoy": reparaciones_hoy,
            "reparaciones_mes": reparaciones_mes,
            "reparaciones_ano": reparaciones_ano,
            "reparaciones_por_fecha": reparaciones_por_fecha,
            "tecnicos_totales": tecnicos_totales,

            "total_tickets": total_tickets,
            "tickets_nuevos": tickets_nuevos,
            "tickets_proceso": tickets_proceso,
            "tickets_en_ruta": tickets_en_ruta,
            "tickets_en_sitio": tickets_en_sitio,
            "tickets_en_revision": tickets_en_revision,
            "tickets_finalizado": tickets_finalizado,
            "tickets_dia": tickets_dia,
            "tickets_mes": tickets_mes,
            "tickets_ano": tickets_ano,
            "tickets_por_fecha": tickets_por_fecha,
            "tecnicos_totales_tickets": tecnicos_totales_tickets,
            "clientes_totales_tickets": clientes_totales_tickets,
            "maquinas_totales_tickets": maquinas_totales_tickets,
            "tickets_por_mes": tickets_por_mes,
            "tickets_por_año": tickets_por_año,

            "total_maquinas_alquiler": total_maquinas_alquiler,
            "clientes_totales_alquiler": clientes_totales_alquiler,
            "alquiler_por_cliente": alquiler_por_cliente,
            "alquiler_sin_revisar": alquiler_sin_revisar,
            "alquiler_alquilada": alquiler_alquilada,
            "alquiler_revisada": alquiler_revisada,
            "alquiler_lista": alquiler_lista,
            "alquiler_con_problemas": alquiler_con_problemas,

            "equipos_activos": equipos_activos,
            "equipos_suspendidos": equipos_suspendidos,
            "equipos_bloqueados": equipos_bloqueados,
            "equipos_no_accesibles": equipos_no_accesibles,
            "equipos_pendiente_bloqueo": equipos_pendiente_bloqueo,
            "equipos_pendiente_desbloqueo": equipos_pendiente_desbloqueo,
            "total_equipos_alquilados_activos": total_alquilados,
            "equipos_atencion": equipos_atencion_data,
            "bloqueo_stats": bloqueo_stats,
        }

        _logger.info(
            "[SAT DASHBOARD] Datos generados: "
            "máquinas=%s alquiler=%s "
            "reparaciones=%s tickets=%s",
            total_maquinas,
            total_maquinas_alquiler,
            total_reparaciones,
            total_tickets,
        )

        return data

    # =========================================================
    # DASHBOARD DE BLOQUEO
    # =========================================================

    @api.model
    def get_bloqueo_data(self):
        """
        Obtiene información independiente de bloqueo.
        """
        try:
            Alquiler = self.env["alquiler"]

            dashboard_data = (
                Alquiler.get_dashboard_data_alquilados()
            )

            equipos_criticos = Alquiler.search([
                (
                    "estado_alquiler_id",
                    "=",
                    "alquilada"
                ),
                (
                    "estado_bloqueo",
                    "in",
                    [
                        "pendiente_bloqueo",
                        "pendiente_desbloqueo",
                        "no_accesible",
                    ]
                ),
            ],
                limit=20,
                order="fecha_bloqueo desc",
            )

            equipos_criticos_data = [
                self._serializar_equipo(
                    equipo,
                    detallado=True
                )
                for equipo in equipos_criticos
            ]

            total_equipos = dashboard_data.get(
                "total_alquilados", 0
            )

            equipos_problemas = sum([
                dashboard_data.get(
                    "equipos_suspendidos", 0
                ),
                dashboard_data.get(
                    "equipos_bloqueados", 0
                ),
                dashboard_data.get(
                    "equipos_no_accesibles", 0
                ),
                dashboard_data.get(
                    "pendientes_bloqueo", 0
                ),
                dashboard_data.get(
                    "pendientes_desbloqueo", 0
                ),
            ])

            porcentaje_problemas = (
                equipos_problemas / total_equipos * 100
                if total_equipos > 0
                else 0
            )

            result = {
                "success": True,
                "dashboard_data": dashboard_data,
                "equipos_criticos": equipos_criticos_data,
                "resumen": {
                    "total_equipos": total_equipos,
                    "equipos_con_problemas": (
                        equipos_problemas
                    ),
                    "porcentaje_problemas": round(
                        porcentaje_problemas, 1
                    ),
                    "equipos_operativos": (
                        dashboard_data.get(
                            "equipos_activos", 0
                        )
                    ),
                },
                "timestamp": (
                    fields.Datetime.context_timestamp(
                        self,
                        fields.Datetime.now()
                    ).strftime("%d/%m/%Y %H:%M:%S")
                ),
            }

            _logger.info(
                "[SAT DASHBOARD][BLOQUEO] "
                "Datos obtenidos: %s equipos críticos",
                len(equipos_criticos_data),
            )

            return result

        except Exception as error:
            _logger.exception(
                "[SAT DASHBOARD][BLOQUEO] "
                "Error obteniendo datos"
            )

            return {
                "success": False,
                "error": str(error),
                "dashboard_data": {},
                "equipos_criticos": [],
                "timestamp": (
                    fields.Datetime.context_timestamp(
                        self,
                        fields.Datetime.now()
                    ).strftime("%d/%m/%Y %H:%M:%S")
                ),
            }

    # =========================================================
    # ACCIONES RÁPIDAS DE BLOQUEO
    # =========================================================

    @api.model
    def accion_bloqueo_rapida(
        self,
        equipo_id,
        accion,
        motivo=None
    ):
        """
        Ejecuta acciones desde el dashboard.

        Acciones:
            suspender
            bloquear
            desbloquear

        Conserva los métodos del módulo alquiler.
        """
        try:
            if accion not in (
                "suspender",
                "bloquear",
                "desbloquear"
            ):
                return {
                    "success": False,
                    "error": "Acción no válida",
                }

            equipo = self.env["alquiler"].browse(
                int(equipo_id)
            ).exists()

            if not equipo:
                return {
                    "success": False,
                    "error": "Equipo no encontrado",
                }

            usuario_id = self.env.user.id

            _logger.info(
                "[SAT DASHBOARD][ACCION] "
                "Equipo=%s acción=%s usuario=%s",
                equipo.id,
                accion,
                usuario_id,
            )

            if accion == "suspender":
                resultado = (
                    equipo.action_suspender_servicio(
                        motivo, usuario_id
                    )
                )

            elif accion == "bloquear":
                resultado = (
                    equipo.action_bloquear_equipo(
                        motivo, usuario_id
                    )
                )

            else:
                resultado = (
                    equipo.action_desbloquear_equipo(
                        motivo, usuario_id
                    )
                )

            if resultado:
                _logger.info(
                    "[SAT DASHBOARD][ACCION] "
                    "Acción %s ejecutada en equipo %s",
                    accion,
                    equipo.serie,
                )

                return {
                    "success": True,
                    "message": (
                        f"Acción {accion} "
                        "ejecutada exitosamente"
                    ),
                    "nuevo_estado": (
                        equipo.estado_bloqueo
                    ),
                }

            return {
                "success": False,
                "error": (
                    "Error al ejecutar la acción"
                ),
            }

        except Exception as error:
            _logger.exception(
                "[SAT DASHBOARD][ACCION] "
                "Error ejecutando %s en equipo %s",
                accion,
                equipo_id,
            )

            return {
                "success": False,
                "error": str(error),
            }

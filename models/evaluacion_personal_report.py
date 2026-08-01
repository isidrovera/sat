# -*- coding: utf-8 -*-

from odoo import models, api

import base64
import io
import logging

import matplotlib
matplotlib.use('Agg')

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


_logger = logging.getLogger(__name__)


class EvaluacionPersonalReport(models.AbstractModel):
    """
    Extiende el modelo evaluacion.personal para generar los gráficos
    correspondientes al reporte de productividad individual del taller.

    La productividad se calcula únicamente con las reparaciones realizadas
    por el técnico evaluado.

    Meta mensual individual del taller: 60 reparaciones por técnico.
    """

    _inherit = 'evaluacion.personal'

    META_MENSUAL_TALLER = 60

    # -------------------------------------------------------------------------
    # MÉTODOS AUXILIARES
    # -------------------------------------------------------------------------

    @api.model
    def _convertir_figura_base64(self, fig):
        """
        Convierte una figura de Matplotlib en una imagen PNG codificada
        en base64.

        Args:
            fig: Figura de Matplotlib.

        Returns:
            str: Imagen codificada en base64.
        """
        buffer = io.BytesIO()

        try:
            fig.savefig(
                buffer,
                format='png',
                bbox_inches='tight',
                dpi=150,
                facecolor='white',
                edgecolor='none',
            )

            buffer.seek(0)

            return base64.b64encode(
                buffer.read()
            ).decode('utf-8')

        finally:
            buffer.close()
            plt.close(fig)

    @api.model
    def _obtener_detalle_laboral(self, evaluacion):
        """
        Obtiene los detalles correspondientes únicamente a días laborales,
        ordenados por fecha.
        """
        return evaluacion.detalle_diario_ids.filtered(
            'es_dia_laboral'
        ).sorted(
            'fecha'
        )

    # -------------------------------------------------------------------------
    # GRÁFICO DE TENDENCIA DIARIA
    # -------------------------------------------------------------------------

    @api.model
    def _generar_grafico_tendencia_diaria(self, evaluacion):
        """
        Genera el gráfico de productividad diaria individual.

        Para el taller únicamente se consideran las reparaciones realizadas
        por el técnico evaluado. No se mezclan tickets, servicios ni trabajos
        realizados por otros técnicos.

        Returns:
            str | bool: Imagen codificada en base64 o False.
        """
        try:
            detalle_diario = self._obtener_detalle_laboral(
                evaluacion
            )

            if not detalle_diario:
                return False

            fechas = [
                detalle.fecha
                for detalle in detalle_diario
            ]

            reparaciones = [
                detalle.cantidad_reparaciones or 0
                for detalle in detalle_diario
            ]

            objetivos_diarios = [
                detalle.objetivo_dia or 0
                for detalle in detalle_diario
            ]

            plt.style.use('seaborn-v0_8-darkgrid')

            fig, ax = plt.subplots(
                figsize=(12, 5),
                dpi=150,
            )

            ax.plot(
                fechas,
                reparaciones,
                marker='o',
                linestyle='-',
                color='#2ecc71',
                linewidth=2.5,
                markersize=6,
                label='Reparaciones realizadas',
                zorder=3,
            )

            ax.plot(
                fechas,
                objetivos_diarios,
                linestyle=':',
                color='#7f8c8d',
                linewidth=2,
                label='Objetivo diario',
                alpha=0.90,
                zorder=2,
            )

            ax.fill_between(
                fechas,
                0,
                reparaciones,
                color='#2ecc71',
                alpha=0.12,
            )

            for fecha, cantidad in zip(
                fechas,
                reparaciones,
            ):
                if cantidad > 0:
                    ax.annotate(
                        str(int(cantidad)),
                        xy=(fecha, cantidad),
                        xytext=(0, 7),
                        textcoords='offset points',
                        ha='center',
                        va='bottom',
                        fontsize=8,
                        fontweight='bold',
                    )

            ax.set_xlabel(
                'Fecha',
                fontsize=11,
                fontweight='bold',
            )

            ax.set_ylabel(
                'Cantidad de reparaciones',
                fontsize=11,
                fontweight='bold',
            )

            ax.set_title(
                (
                    'Productividad diaria individual '
                    f'— Meta mensual: {self.META_MENSUAL_TALLER} reparaciones'
                ),
                fontsize=13,
                fontweight='bold',
                pad=15,
            )

            ax.xaxis.set_major_formatter(
                mdates.DateFormatter('%d/%m')
            )

            intervalo_fechas = max(
                1,
                len(fechas) // 10,
            )

            ax.xaxis.set_major_locator(
                mdates.DayLocator(
                    interval=intervalo_fechas
                )
            )

            ax.tick_params(
                axis='x',
                rotation=45,
            )

            ax.grid(
                True,
                alpha=0.30,
                linestyle='-',
                linewidth=0.5,
            )

            ax.legend(
                loc='upper left',
                framealpha=0.90,
                fontsize=9,
            )

            limite_superior = max(
                reparaciones + objetivos_diarios + [1]
            )

            ax.set_ylim(
                bottom=0,
                top=limite_superior * 1.20,
            )

            fig.tight_layout()

            return self._convertir_figura_base64(
                fig
            )

        except Exception:
            _logger.exception(
                'Error generando el gráfico de tendencia diaria '
                'para la evaluación %s.',
                evaluacion.id,
            )
            return False

    # -------------------------------------------------------------------------
    # GRÁFICO SEMANAL
    # -------------------------------------------------------------------------

    @api.model
    def _generar_grafico_barras_semanal(self, evaluacion):
        """
        Genera el gráfico semanal del técnico evaluado.

        Únicamente suma las reparaciones realizadas por el técnico.
        No incluye tickets ni trabajos de otros técnicos.

        Returns:
            str | bool: Imagen codificada en base64 o False.
        """
        try:
            detalle_diario = self._obtener_detalle_laboral(
                evaluacion
            )

            if not detalle_diario:
                return False

            semanas = {}

            for detalle in detalle_diario:
                numero_semana = detalle.fecha.isocalendar()[1]

                if numero_semana not in semanas:
                    semanas[numero_semana] = {
                        'reparaciones': 0,
                        'objetivo': 0,
                    }

                semanas[numero_semana]['reparaciones'] += (
                    detalle.cantidad_reparaciones or 0
                )

                semanas[numero_semana]['objetivo'] += (
                    detalle.objetivo_dia or 0
                )

            semanas_ordenadas = sorted(
                semanas.keys()
            )

            reparaciones = [
                semanas[semana]['reparaciones']
                for semana in semanas_ordenadas
            ]

            objetivos = [
                semanas[semana]['objetivo']
                for semana in semanas_ordenadas
            ]

            posiciones = np.arange(
                len(semanas_ordenadas)
            )

            ancho = 0.36

            fig, ax = plt.subplots(
                figsize=(10, 5),
                dpi=150,
            )

            barras_reparaciones = ax.bar(
                posiciones - ancho / 2,
                reparaciones,
                ancho,
                label='Reparaciones realizadas',
                color='#2ecc71',
                alpha=0.88,
            )

            barras_objetivo = ax.bar(
                posiciones + ancho / 2,
                objetivos,
                ancho,
                label='Objetivo semanal',
                color='#95a5a6',
                alpha=0.75,
            )

            for barras in (
                barras_reparaciones,
                barras_objetivo,
            ):
                for barra in barras:
                    cantidad = barra.get_height()

                    if cantidad > 0:
                        ax.text(
                            barra.get_x() + barra.get_width() / 2,
                            cantidad,
                            str(int(round(cantidad))),
                            ha='center',
                            va='bottom',
                            fontsize=9,
                            fontweight='bold',
                        )

            ax.set_xlabel(
                'Semana',
                fontsize=11,
                fontweight='bold',
            )

            ax.set_ylabel(
                'Cantidad de reparaciones',
                fontsize=11,
                fontweight='bold',
            )

            ax.set_title(
                'Reparaciones semanales del técnico',
                fontsize=13,
                fontweight='bold',
                pad=15,
            )

            ax.set_xticks(
                posiciones
            )

            ax.set_xticklabels([
                f'Semana {semana}'
                for semana in semanas_ordenadas
            ])

            ax.legend(
                framealpha=0.90
            )

            ax.grid(
                True,
                alpha=0.30,
                axis='y',
            )

            limite_superior = max(
                reparaciones + objetivos + [1]
            )

            ax.set_ylim(
                bottom=0,
                top=limite_superior * 1.20,
            )

            fig.tight_layout()

            return self._convertir_figura_base64(
                fig
            )

        except Exception:
            _logger.exception(
                'Error generando el gráfico semanal '
                'para la evaluación %s.',
                evaluacion.id,
            )
            return False

    # -------------------------------------------------------------------------
    # MAPA DE CALOR
    # -------------------------------------------------------------------------

    @api.model
    def _generar_heatmap_actividad(self, evaluacion):
        """
        Genera un mapa de calor de reparaciones realizadas por día.

        El mapa utiliza únicamente cantidad_reparaciones y no total_trabajos,
        porque total_trabajos podría incluir tickets u otras actividades.

        Returns:
            str | bool: Imagen codificada en base64 o False.
        """
        try:
            detalle_diario = evaluacion.detalle_diario_ids.sorted(
                'fecha'
            )

            if not detalle_diario:
                return False

            primer_dia = detalle_diario[0].fecha
            ultimo_dia = detalle_diario[-1].fecha

            dias_totales = (
                ultimo_dia - primer_dia
            ).days + 1

            cantidad_semanas = max(
                1,
                ((dias_totales - 1) // 7) + 1,
            )

            matriz = np.zeros(
                (7, cantidad_semanas)
            )

            for detalle in detalle_diario:
                dias_desde_inicio = (
                    detalle.fecha - primer_dia
                ).days

                numero_semana = (
                    dias_desde_inicio // 7
                )

                dia_semana = detalle.fecha.weekday()

                if numero_semana < cantidad_semanas:
                    matriz[
                        dia_semana,
                        numero_semana,
                    ] = detalle.cantidad_reparaciones or 0

            fig, ax = plt.subplots(
                figsize=(12, 3.5),
                dpi=150,
            )

            mapa_colores = plt.cm.YlGnBu

            imagen = ax.imshow(
                matriz,
                cmap=mapa_colores,
                aspect='auto',
                interpolation='nearest',
            )

            dias_semana = [
                'Lun',
                'Mar',
                'Mié',
                'Jue',
                'Vie',
                'Sáb',
                'Dom',
            ]

            ax.set_yticks(
                np.arange(7)
            )

            ax.set_yticklabels(
                dias_semana
            )

            ax.set_xticks(
                np.arange(cantidad_semanas)
            )

            ax.set_xticklabels([
                f'S{i + 1}'
                for i in range(cantidad_semanas)
            ])

            ax.set_title(
                'Mapa de actividad de reparaciones del técnico',
                fontsize=13,
                fontweight='bold',
                pad=15,
            )

            barra_color = plt.colorbar(
                imagen,
                ax=ax,
                orientation='horizontal',
                pad=0.15,
                aspect=30,
                shrink=0.80,
            )

            barra_color.set_label(
                'Reparaciones realizadas',
                fontsize=9,
            )

            valor_maximo = matriz.max() if matriz.size else 0

            for fila in range(7):
                for columna in range(cantidad_semanas):
                    cantidad = matriz[
                        fila,
                        columna,
                    ]

                    if cantidad > 0:
                        color_texto = (
                            'white'
                            if valor_maximo > 0
                            and cantidad >= valor_maximo * 0.60
                            else 'black'
                        )

                        ax.text(
                            columna,
                            fila,
                            str(int(cantidad)),
                            ha='center',
                            va='center',
                            color=color_texto,
                            fontsize=8,
                            fontweight='bold',
                        )

            fig.tight_layout()

            return self._convertir_figura_base64(
                fig
            )

        except Exception:
            _logger.exception(
                'Error generando el mapa de calor '
                'para la evaluación %s.',
                evaluacion.id,
            )
            return False

    # -------------------------------------------------------------------------
    # GRÁFICO DE CUMPLIMIENTO DE META
    # -------------------------------------------------------------------------

    @api.model
    def _generar_grafico_distribucion(self, evaluacion):
        """
        Genera un gráfico circular del cumplimiento de la meta mensual.

        La meta individual del taller es de 60 reparaciones por técnico.

        Ejemplo:
            38 reparaciones / 60 reparaciones = 63.33 %

        El gráfico diferencia:
        - Reparaciones realizadas.
        - Reparaciones pendientes para alcanzar la meta.

        Si el técnico supera la meta, el gráfico muestra la meta completa y
        el excedente se informa en el título.

        Returns:
            str | bool: Imagen codificada en base64 o False.
        """
        try:
            total_reparaciones = (
                evaluacion.cantidad_reparaciones or 0
            )

            meta_mensual = self.META_MENSUAL_TALLER

            reparaciones_para_meta = min(
                total_reparaciones,
                meta_mensual,
            )

            reparaciones_pendientes = max(
                meta_mensual - total_reparaciones,
                0,
            )

            reparaciones_excedentes = max(
                total_reparaciones - meta_mensual,
                0,
            )

            porcentaje_real = (
                total_reparaciones / meta_mensual
            ) * 100 if meta_mensual else 0

            etiquetas = [
                'Realizadas',
                'Pendientes',
            ]

            cantidades = [
                reparaciones_para_meta,
                reparaciones_pendientes,
            ]

            colores = [
                '#2ecc71',
                '#ecf0f1',
            ]

            separar = (
                0.04,
                0,
            )

            fig, ax = plt.subplots(
                figsize=(8, 6),
                dpi=150,
            )

            if sum(cantidades) <= 0:
                cantidades = [
                    0,
                    meta_mensual,
                ]

            def formato_porcentaje(porcentaje):
                if porcentaje <= 0:
                    return ''

                return f'{porcentaje:.1f}%'

            sectores, textos, porcentajes = ax.pie(
                cantidades,
                explode=separar,
                labels=etiquetas,
                colors=colores,
                autopct=formato_porcentaje,
                shadow=False,
                startangle=90,
                counterclock=False,
                wedgeprops={
                    'linewidth': 1,
                    'edgecolor': 'white',
                },
            )

            for texto in textos:
                texto.set_fontsize(11)
                texto.set_fontweight('bold')

            for texto_porcentaje in porcentajes:
                texto_porcentaje.set_fontsize(10)
                texto_porcentaje.set_fontweight('bold')

            titulo = (
                f'Cumplimiento de meta: '
                f'{total_reparaciones} de {meta_mensual} reparaciones '
                f'({porcentaje_real:.2f} %)'
            )

            if reparaciones_excedentes > 0:
                titulo += (
                    f'\nExcedente: '
                    f'{reparaciones_excedentes} reparaciones'
                )

            ax.set_title(
                titulo,
                fontsize=13,
                fontweight='bold',
                pad=20,
            )

            ax.text(
                0,
                0,
                (
                    f'{total_reparaciones}\n'
                    'reparaciones'
                ),
                ha='center',
                va='center',
                fontsize=14,
                fontweight='bold',
                color='#2c3e50',
            )

            circulo_central = plt.Circle(
                (0, 0),
                0.55,
                color='white',
            )

            ax.add_artist(
                circulo_central
            )

            ax.text(
                0,
                0,
                (
                    f'{porcentaje_real:.2f}%\n'
                    f'{total_reparaciones}/{meta_mensual}'
                ),
                ha='center',
                va='center',
                fontsize=13,
                fontweight='bold',
                color='#2c3e50',
                zorder=5,
            )

            fig.tight_layout()

            return self._convertir_figura_base64(
                fig
            )

        except Exception:
            _logger.exception(
                'Error generando el gráfico de cumplimiento '
                'para la evaluación %s.',
                evaluacion.id,
            )
            return False

    # -------------------------------------------------------------------------
    # PREPARACIÓN DE DATOS DEL REPORTE
    # -------------------------------------------------------------------------

    @api.model
    def _preparar_datos_reporte(self, evaluacion):
        """
        Prepara todos los datos y gráficos para el reporte individual.

        Returns:
            dict: Información procesada para la plantilla del reporte.
        """
        cantidad_reparaciones = (
            evaluacion.cantidad_reparaciones or 0
        )

        meta_mensual = self.META_MENSUAL_TALLER

        porcentaje_cumplimiento_reporte = (
            cantidad_reparaciones / meta_mensual
        ) * 100 if meta_mensual else 0

        reparaciones_pendientes = max(
            meta_mensual - cantidad_reparaciones,
            0,
        )

        reparaciones_excedentes = max(
            cantidad_reparaciones - meta_mensual,
            0,
        )

        datos = {
            'evaluacion': evaluacion,

            'meta_mensual_taller': meta_mensual,

            'cantidad_reparaciones_reporte': (
                cantidad_reparaciones
            ),

            'porcentaje_cumplimiento_reporte': (
                porcentaje_cumplimiento_reporte
            ),

            'reparaciones_pendientes': (
                reparaciones_pendientes
            ),

            'reparaciones_excedentes': (
                reparaciones_excedentes
            ),

            'grafico_tendencia': (
                self._generar_grafico_tendencia_diaria(
                    evaluacion
                )
            ),

            'grafico_semanal': (
                self._generar_grafico_barras_semanal(
                    evaluacion
                )
            ),

            'heatmap_actividad': (
                self._generar_heatmap_actividad(
                    evaluacion
                )
            ),

            'grafico_distribucion': (
                self._generar_grafico_distribucion(
                    evaluacion
                )
            ),
        }

        return datos
# -*- coding: utf-8 -*-
from odoo import models, api
import matplotlib
matplotlib.use('Agg')  # Backend sin GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import io
import base64
from datetime import datetime, timedelta
import numpy as np
import logging

_logger = logging.getLogger(__name__)


class EvaluacionPersonalReport(models.AbstractModel):
    """
    Modelo abstracto para extender la evaluación con métodos de generación de gráficos
    """
    _inherit = 'evaluacion.personal'

    @api.model
    def _generar_grafico_tendencia_diaria(self, evaluacion):
        """
        Genera un gráfico de líneas con la tendencia diaria de trabajos
        
        Returns:
            str: Imagen en base64
        """
        try:
            detalle_diario = evaluacion.detalle_diario_ids.filtered('es_dia_laboral').sorted('fecha')
            
            if not detalle_diario:
                return False
            
            # Configuración de estilo moderno con ALTA RESOLUCIÓN
            plt.style.use('seaborn-v0_8-darkgrid')
            fig, ax = plt.subplots(figsize=(12, 5), dpi=150)
            
            # Datos
            fechas = [d.fecha for d in detalle_diario]
            reparaciones = [d.cantidad_reparaciones for d in detalle_diario]
            tickets = [d.cantidad_tickets for d in detalle_diario]
            total = [d.total_trabajos for d in detalle_diario]
            objetivo = [d.objetivo_dia for d in detalle_diario]
            
            # Gráfico de líneas
            ax.plot(fechas, total, 'o-', color='#3498db', linewidth=2.5, 
                   markersize=6, label='Total Trabajos', zorder=3)
            ax.plot(fechas, reparaciones, 's--', color='#2ecc71', linewidth=1.5, 
                   markersize=4, label='Reparaciones', alpha=0.7)
            ax.plot(fechas, tickets, '^--', color='#e74c3c', linewidth=1.5, 
                   markersize=4, label='Tickets', alpha=0.7)
            ax.plot(fechas, objetivo, ':', color='#95a5a6', linewidth=2, 
                   label='Objetivo', alpha=0.8)
            
            # Área bajo la curva
            ax.fill_between(fechas, 0, total, alpha=0.1, color='#3498db')
            
            # Configuración de ejes
            ax.set_xlabel('Fecha', fontsize=11, fontweight='bold')
            ax.set_ylabel('Cantidad de Trabajos', fontsize=11, fontweight='bold')
            ax.set_title('Tendencia de Productividad Diaria', 
                        fontsize=13, fontweight='bold', pad=15)
            
            # Formato de fechas en eje X
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(fechas)//10)))
            plt.xticks(rotation=45, ha='right')
            
            # Grid y leyenda
            ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
            ax.legend(loc='upper left', framealpha=0.9, fontsize=9)
            
            # Ajuste automático
            plt.tight_layout()
            
            # Convertir a base64 con ALTA CALIDAD
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150, 
                       facecolor='white', edgecolor='none')
            buffer.seek(0)
            imagen_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)
            
            return imagen_base64
            
        except Exception as e:
            _logger.error(f"Error generando gráfico de tendencia: {str(e)}")
            return False

    @api.model
    def _generar_grafico_barras_semanal(self, evaluacion):
        """
        Genera un gráfico de barras agrupadas por semana
        
        Returns:
            str: Imagen en base64
        """
        try:
            detalle_diario = evaluacion.detalle_diario_ids.filtered('es_dia_laboral').sorted('fecha')
            
            if not detalle_diario:
                return False
            
            # Agrupar por semanas
            semanas = {}
            for detalle in detalle_diario:
                semana_num = detalle.fecha.isocalendar()[1]  # Número de semana
                if semana_num not in semanas:
                    semanas[semana_num] = {'reparaciones': 0, 'tickets': 0}
                semanas[semana_num]['reparaciones'] += detalle.cantidad_reparaciones
                semanas[semana_num]['tickets'] += detalle.cantidad_tickets
            
            # Preparar datos
            semanas_ordenadas = sorted(semanas.keys())
            reparaciones = [semanas[s]['reparaciones'] for s in semanas_ordenadas]
            tickets = [semanas[s]['tickets'] for s in semanas_ordenadas]
            
            # Crear gráfico con ALTA RESOLUCIÓN
            fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
            
            x = np.arange(len(semanas_ordenadas))
            width = 0.35
            
            # Barras
            bars1 = ax.bar(x - width/2, reparaciones, width, 
                          label='Reparaciones', color='#2ecc71', alpha=0.8)
            bars2 = ax.bar(x + width/2, tickets, width, 
                          label='Tickets', color='#e74c3c', alpha=0.8)
            
            # Etiquetas en las barras
            for bars in [bars1, bars2]:
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax.text(bar.get_x() + bar.get_width()/2., height,
                               f'{int(height)}',
                               ha='center', va='bottom', fontsize=9, fontweight='bold')
            
            # Configuración
            ax.set_xlabel('Semana del Mes', fontsize=11, fontweight='bold')
            ax.set_ylabel('Cantidad de Trabajos', fontsize=11, fontweight='bold')
            ax.set_title('Distribución Semanal de Trabajos', 
                        fontsize=13, fontweight='bold', pad=15)
            ax.set_xticks(x)
            ax.set_xticklabels([f'Semana {s}' for s in semanas_ordenadas])
            ax.legend(framealpha=0.9)
            ax.grid(True, alpha=0.3, axis='y')
            
            plt.tight_layout()
            
            # Convertir a base64 con ALTA CALIDAD
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150,
                       facecolor='white', edgecolor='none')
            buffer.seek(0)
            imagen_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)
            
            return imagen_base64
            
        except Exception as e:
            _logger.error(f"Error generando gráfico semanal: {str(e)}")
            return False

    @api.model
    def _generar_heatmap_actividad(self, evaluacion):
        """
        Genera un heatmap de actividad tipo GitHub
        
        Returns:
            str: Imagen en base64
        """
        try:
            detalle_diario = evaluacion.detalle_diario_ids.sorted('fecha')
            
            if not detalle_diario:
                return False
            
            # Preparar datos para heatmap (matriz semana x día)
            # Obtener todas las fechas del mes
            primer_dia = detalle_diario[0].fecha
            ultimo_dia = detalle_diario[-1].fecha
            
            # Calcular dimensiones
            dias_totales = (ultimo_dia - primer_dia).days + 1
            
            # Crear matriz (7 días x N semanas)
            semanas = (dias_totales // 7) + 1
            matriz = np.zeros((7, semanas))
            
            # Llenar matriz con datos
            for detalle in detalle_diario:
                dias_desde_inicio = (detalle.fecha - primer_dia).days
                semana = dias_desde_inicio // 7
                dia_semana = detalle.fecha.weekday()  # 0=Lun, 6=Dom
                
                if semana < semanas:
                    matriz[dia_semana][semana] = detalle.total_trabajos
            
            # Crear figura con ALTA RESOLUCIÓN
            fig, ax = plt.subplots(figsize=(12, 3), dpi=150)
            
            # Heatmap
            cmap = plt.cm.YlGnBu
            im = ax.imshow(matriz, cmap=cmap, aspect='auto', interpolation='nearest')
            
            # Etiquetas
            dias_semana = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
            ax.set_yticks(np.arange(7))
            ax.set_yticklabels(dias_semana)
            ax.set_xticks(np.arange(semanas))
            ax.set_xticklabels([f'S{i+1}' for i in range(semanas)])
            
            # Título
            ax.set_title('Mapa de Calor de Actividad Mensual', 
                        fontsize=13, fontweight='bold', pad=15)
            
            # Colorbar
            cbar = plt.colorbar(im, ax=ax, orientation='horizontal', 
                               pad=0.1, aspect=30, shrink=0.8)
            cbar.set_label('Trabajos realizados', fontsize=9)
            
            # Agregar números en las celdas
            for i in range(7):
                for j in range(semanas):
                    if matriz[i, j] > 0:
                        text = ax.text(j, i, int(matriz[i, j]),
                                     ha="center", va="center", 
                                     color="black" if matriz[i, j] < 5 else "white",
                                     fontsize=8, fontweight='bold')
            
            plt.tight_layout()
            
            # Convertir a base64 con ALTA CALIDAD
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150,
                       facecolor='white', edgecolor='none')
            buffer.seek(0)
            imagen_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)
            
            return imagen_base64
            
        except Exception as e:
            _logger.error(f"Error generando heatmap: {str(e)}")
            return False

    @api.model
    def _generar_grafico_distribucion(self, evaluacion):
        """
        Genera un gráfico de pastel con distribución de actividades
        
        Returns:
            str: Imagen en base64
        """
        try:
            total_reparaciones = evaluacion.cantidad_reparaciones
            total_tickets = evaluacion.cantidad_tickets
            dias_sin_actividad = evaluacion.total_dias_sin_actividad
            
            # Datos
            labels = ['Reparaciones', 'Tickets', 'Días sin Actividad']
            sizes = [total_reparaciones, total_tickets, dias_sin_actividad]
            colors = ['#2ecc71', '#e74c3c', '#95a5a6']
            explode = (0.05, 0.05, 0)
            
            # Crear figura con ALTA RESOLUCIÓN
            fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
            
            # Gráfico de pastel
            wedges, texts, autotexts = ax.pie(sizes, explode=explode, labels=labels,
                                              colors=colors, autopct='%1.1f%%',
                                              shadow=True, startangle=90)
            
            # Mejorar texto
            for text in texts:
                text.set_fontsize(11)
                text.set_fontweight('bold')
            
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(10)
                autotext.set_fontweight('bold')
            
            ax.set_title('Distribución de Actividades del Mes', 
                        fontsize=13, fontweight='bold', pad=20)
            
            plt.tight_layout()
            
            # Convertir a base64 con ALTA CALIDAD
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150,
                       facecolor='white', edgecolor='none')
            buffer.seek(0)
            imagen_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            plt.close(fig)
            
            return imagen_base64
            
        except Exception as e:
            _logger.error(f"Error generando gráfico de distribución: {str(e)}")
            return False

    @api.model
    def _preparar_datos_reporte(self, evaluacion):
        """
        Prepara todos los datos y gráficos para el reporte
        
        Returns:
            dict: Diccionario con todos los datos procesados
        """
        datos = {
            'evaluacion': evaluacion,
            'grafico_tendencia': self._generar_grafico_tendencia_diaria(evaluacion),
            'grafico_semanal': self._generar_grafico_barras_semanal(evaluacion),
            'heatmap_actividad': self._generar_heatmap_actividad(evaluacion),
            'grafico_distribucion': self._generar_grafico_distribucion(evaluacion),
        }
        
        return datos
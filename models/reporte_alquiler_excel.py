from odoo import models, fields, api, _
from odoo.exceptions import UserError
import xlwt
import base64
from io import BytesIO
import logging

_logger = logging.getLogger(__name__)


class ReporteEstadoMaquinaExcelExporter(models.TransientModel):
    _name = 'reporte.estado.maquina.excel.exporter'
    _description = 'Exportador Excel para Reporte Estado Máquinas'

    name = fields.Char(string='Nombre del Archivo', default='Reporte_Estado_Maquinas.xls')
    excel_file = fields.Binary(string='Archivo Excel')
    filename = fields.Char(string='Nombre de Archivo')
    state = fields.Selection([
        ('init', 'Inicial'),
        ('done', 'Completado')
    ], default='init')

    def generar_excel(self, reportes_ids):
        """
        Genera el archivo Excel con todos los reportes
        """
        if not reportes_ids:
            raise UserError(_('No hay reportes para exportar.'))
        
        # Obtener reportes
        reportes = self.env['reporte.estado.maquina'].browse(reportes_ids)
        
        # Crear workbook
        workbook = xlwt.Workbook(encoding='utf-8')
        
        # Crear hojas
        self._crear_hoja_resumen(workbook, reportes)
        self._crear_hoja_detalle(workbook, reportes)
        
        # Generar archivo
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        
        # Codificar en base64
        excel_data = base64.b64encode(output.read())
        
        # Generar nombre de archivo
        fecha_actual = fields.Date.context_today(self).strftime('%Y%m%d')
        filename = f'Reporte_Estado_Maquinas_{fecha_actual}.xls'
        
        # Actualizar registro
        self.write({
            'excel_file': excel_data,
            'filename': filename,
            'state': 'done'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Descargar Excel',
            'res_model': 'reporte.estado.maquina.excel.exporter',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'}
        }

    def _crear_hoja_resumen(self, workbook, reportes):
        """
        Crea hoja de resumen con estadísticas
        """
        worksheet = workbook.add_sheet('Resumen')
        
        # Estilos
        title_style = xlwt.easyxf('font: bold 1, height 320; align: horiz center')
        header_style = xlwt.easyxf('font: bold 1; align: horiz center; borders: all thin')
        data_style = xlwt.easyxf('borders: all thin; align: horiz center')
        number_style = xlwt.easyxf('borders: all thin; align: horiz right', num_format_str='#,##0')
        
        # Título
        worksheet.write_merge(0, 0, 0, 4, 'REPORTE DE ESTADO DE MÁQUINAS', title_style)
        worksheet.write_merge(1, 1, 0, 4, f'Fecha de Generación: {fields.Date.context_today(self)}', header_style)
        
        # Resumen por estado
        row = 3
        worksheet.write(row, 0, 'RESUMEN POR ESTADO', header_style)
        row += 1
        
        headers_resumen = ['Estado', 'Cantidad', 'Contador B/N Total', 'Contador Color Total', 'Contador Scanner Total']
        for col, header in enumerate(headers_resumen):
            worksheet.write(row, col, header, header_style)
        row += 1
        
        # Agrupar por estado
        estados_data = {}
        for reporte in reportes:
            estado = reporte.estado_maquina
            if estado not in estados_data:
                estados_data[estado] = {
                    'cantidad': 0,
                    'contador_bn': 0,
                    'contador_color': 0,
                    'contador_scanner': 0
                }
            estados_data[estado]['cantidad'] += 1
            estados_data[estado]['contador_bn'] += reporte.contador_bn or 0
            estados_data[estado]['contador_color'] += reporte.contador_color or 0
            estados_data[estado]['contador_scanner'] += reporte.contador_scanner or 0
        
        # Escribir datos del resumen
        for estado, data in estados_data.items():
            estado_label = dict(reportes._fields['estado_maquina'].selection).get(estado, estado)
            worksheet.write(row, 0, estado_label, data_style)
            worksheet.write(row, 1, data['cantidad'], number_style)
            worksheet.write(row, 2, data['contador_bn'], number_style)
            worksheet.write(row, 3, data['contador_color'], number_style)
            worksheet.write(row, 4, data['contador_scanner'], number_style)
            row += 1
        
        # Totales
        row += 1
        worksheet.write(row, 0, 'TOTAL GENERAL', header_style)
        worksheet.write(row, 1, len(reportes), number_style)
        worksheet.write(row, 2, sum(r.contador_bn or 0 for r in reportes), number_style)
        worksheet.write(row, 3, sum(r.contador_color or 0 for r in reportes), number_style)
        worksheet.write(row, 4, sum(r.contador_scanner or 0 for r in reportes), number_style)
        
        # Ajustar ancho de columnas
        for col in range(5):
            worksheet.col(col).width = 4000

    def _crear_hoja_detalle(self, workbook, reportes):
        """
        Crea hoja con detalles completos de cada máquina
        """
        worksheet = workbook.add_sheet('Detalles Completos')
        
        # Estilos
        header_style = xlwt.easyxf('font: bold 1; align: horiz center; borders: all thin')
        data_style = xlwt.easyxf('borders: all thin')
        date_style = xlwt.easyxf('borders: all thin', num_format_str='DD/MM/YYYY')
        number_style = xlwt.easyxf('borders: all thin; align: horiz right', num_format_str='#,##0')
        
        # Encabezados
        headers = [
            'Fecha Generación', 'Serie', 'Modelo', 'Marca', 'Tipo Máquina', 'Estado Máquina',
            'Ubicación Física', 'Contador B/N', 'Contador Color', 'Contador Total', 'Contador Scanner',
            'Último Ticket', 'Fecha Último Ticket', 'Tipo Servicio', 'Técnico Responsable',
            'Cliente Anterior', 'Dirección Anterior', 'Fecha Último Retiro',
            # Accesorios
            'Transformador', 'Estabilizador', 'ADF Simple', 'ADF Dual', 'Finalizador Interno',
            'Finalizador Externo', 'Mueble', 'Panel Smart', 'Panel Normal', 'Wi-Fi', 'Bluetooth',
            'Cable USB', 'Cable Red', 'Caseteras',
            # Check List - Funciones
            'Copia', 'Impresión', 'Impresión USB', 'Scanner SMB', 'Scanner USB', 'Scanner FTP', 'Scanner Mail',
            # Check List - Componentes
            'ADF Estado', 'Tray 1', 'Tray 2', 'Tray 3', 'Tray 4', 'Bypass', 'Finalizador Estado',
            # Check List - Partes Críticas
            'Tacho Estado', 'Fusora Estado', 'Transfer Estado', 'Óptico Estado',
            'Unidad Imagen Black', 'Unidad Imagen Magenta', 'Unidad Imagen Cyan', 'Unidad Imagen Yellow',
            # Toners
            'Toner Black', 'Toner Magenta', 'Toner Cyan', 'Toner Yellow'
        ]
        
        # Escribir encabezados
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_style)
        
        # Escribir datos
        row = 1
        for reporte in reportes:
            col = 0
            
            # Datos básicos
            worksheet.write(row, col, reporte.fecha_generacion or '', date_style); col += 1
            worksheet.write(row, col, reporte.serie or '', data_style); col += 1
            worksheet.write(row, col, reporte.modelo or '', data_style); col += 1
            worksheet.write(row, col, reporte.marca or '', data_style); col += 1
            worksheet.write(row, col, reporte.tipo_maquina or '', data_style); col += 1
            worksheet.write(row, col, dict(reporte._fields['estado_maquina'].selection).get(reporte.estado_maquina, ''), data_style); col += 1
            worksheet.write(row, col, dict(reporte._fields['ubicacion_fisica'].selection).get(reporte.ubicacion_fisica, '') if reporte.ubicacion_fisica else '', data_style); col += 1
            
            # Contómetros
            worksheet.write(row, col, reporte.contador_bn or 0, number_style); col += 1
            worksheet.write(row, col, reporte.contador_color or 0, number_style); col += 1
            worksheet.write(row, col, reporte.contador_total or 0, number_style); col += 1
            worksheet.write(row, col, reporte.contador_scanner or 0, number_style); col += 1
            
            # Último ticket
            worksheet.write(row, col, reporte.ultimo_ticket_id.name if reporte.ultimo_ticket_id else '', data_style); col += 1
            worksheet.write(row, col, reporte.ultimo_ticket_fecha or '', date_style); col += 1
            worksheet.write(row, col, reporte.ultimo_ticket_tipo or '', data_style); col += 1
            worksheet.write(row, col, reporte.tecnico_responsable or '', data_style); col += 1
            
            # Cliente anterior
            worksheet.write(row, col, reporte.cliente_anterior_id.name if reporte.cliente_anterior_id else '', data_style); col += 1
            worksheet.write(row, col, reporte.direccion_anterior or '', data_style); col += 1
            worksheet.write(row, col, reporte.fecha_ultimo_retiro or '', date_style); col += 1
            
            # Accesorios - convertir selections a texto
            accessories = [
                'transformador', 'estabilizador', 'adf_simple', 'adf_dual', 'finalizador_interno',
                'finalizador_externo', 'mueble', 'panel_smart', 'panel_normal', 'wifi', 'bluetooth',
                'cable_usb', 'cable_red'
            ]
            
            for acc in accessories:
                value = getattr(reporte, acc, '')
                if value:
                    selection_dict = dict(reporte._fields[acc].selection) if hasattr(reporte._fields.get(acc, {}), 'selection') else {}
                    display_value = selection_dict.get(value, value)
                else:
                    display_value = ''
                worksheet.write(row, col, display_value, data_style); col += 1
            
            # Caseteras
            worksheet.write(row, col, reporte.numero_caseteras or '', data_style); col += 1
            
            # Check List - Funciones
            funciones = [
                'copia_estado', 'impresion_estado', 'impresion_usb_estado', 'scanner_smb_estado',
                'scanner_usb_estado', 'scanner_ftp_estado', 'scanner_mail_estado'
            ]
            
            for func in funciones:
                value = getattr(reporte, func, '')
                if value:
                    selection_dict = dict(reporte._fields[func].selection) if hasattr(reporte._fields.get(func, {}), 'selection') else {}
                    display_value = selection_dict.get(value, value)
                else:
                    display_value = ''
                worksheet.write(row, col, display_value, data_style); col += 1
            
            # Check List - Componentes
            componentes = [
                'adf_estado', 'tray1_estado', 'tray2_estado', 'tray3_estado', 'tray4_estado',
                'bypass_estado', 'finalizador_estado'
            ]
            
            for comp in componentes:
                value = getattr(reporte, comp, '')
                if value:
                    selection_dict = dict(reporte._fields[comp].selection) if hasattr(reporte._fields.get(comp, {}), 'selection') else {}
                    display_value = selection_dict.get(value, value)
                else:
                    display_value = ''
                worksheet.write(row, col, display_value, data_style); col += 1
            
            # Check List - Partes Críticas
            partes = [
                'tacho_estado', 'fusora_estado', 'transfer_estado', 'optico_estado',
                'unidad_imagen_black_estado', 'unidad_imagen_magenta_estado',
                'unidad_imagen_cyan_estado', 'unidad_imagen_yellow_estado'
            ]
            
            for parte in partes:
                value = getattr(reporte, parte, '')
                if value:
                    selection_dict = dict(reporte._fields[parte].selection) if hasattr(reporte._fields.get(parte, {}), 'selection') else {}
                    display_value = selection_dict.get(value, value)
                else:
                    display_value = ''
                worksheet.write(row, col, display_value, data_style); col += 1
            
            # Toners
            toners = ['toner_black_nivel', 'toner_magenta_nivel', 'toner_cyan_nivel', 'toner_yellow_nivel']
            
            for toner in toners:
                value = getattr(reporte, toner, '')
                if value:
                    selection_dict = dict(reporte._fields[toner].selection) if hasattr(reporte._fields.get(toner, {}), 'selection') else {}
                    display_value = selection_dict.get(value, value)
                else:
                    display_value = ''
                worksheet.write(row, col, display_value, data_style); col += 1
            
            row += 1
        
        # Ajustar ancho de columnas
        for col in range(len(headers)):
            if col < 10:  # Primeras columnas más anchas
                worksheet.col(col).width = 3500
            else:
                worksheet.col(col).width = 2800

    def action_download_excel(self):
        """
        Acción para descargar el archivo Excel
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/reporte.estado.maquina.excel.exporter/{self.id}/excel_file/{self.filename}?download=true',
            'target': 'self',
        }
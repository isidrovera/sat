from odoo import models, fields, api
import logging
import re
from datetime import timedelta

_logger = logging.getLogger(__name__)

class PatronContador(models.Model):
    _name = 'patron.contador'
    _description = 'Patrones configurables para detectar contadores y series'
    _order = 'tipo, orden, name'
    
    # CAMPOS EXISTENTES
    name = fields.Char('Nombre del patrón', required=True, help="Nombre descriptivo del patrón")
    tipo = fields.Selection([
        ('serie', 'Número de Serie'),
        ('contador_bn', 'Contador B/N'),
        ('contador_color', 'Contador Color'),
        ('contador_scan', 'Contador Scan')
    ], string='Tipo', required=True, help="Tipo de dato que detecta este patrón")
    
    patron_regex = fields.Text('Expresión Regular', required=True, 
                              help="Expresión regular para detectar el patrón. Use () para capturar el valor.")
    
    descripcion = fields.Text('Descripción', help="Descripción de qué detecta este patrón")
    ejemplo = fields.Char('Ejemplo de texto', help="Ejemplo de texto que debería coincidir")
    
    activo = fields.Boolean('Activo', default=True, help="Si está desactivado, no se usará para detección")
    orden = fields.Integer('Orden de prioridad', default=10, 
                          help="Orden de evaluación (menor número = mayor prioridad)")
    
    # Estadísticas de uso existentes
    veces_usado = fields.Integer('Veces usado', default=0, readonly=True)
    ultima_deteccion = fields.Datetime('Última detección', readonly=True)
    
    # NUEVOS CAMPOS PARA SISTEMA INTELIGENTE
    auto_generado = fields.Boolean('Auto-generado', default=False, 
                                  help="Patrón creado automáticamente por el sistema")
    confianza_patron = fields.Float('Confianza del Patrón (%)', default=0.0, 
                                   help="Nivel de confianza del patrón auto-generado")
    idioma_patron = fields.Char('Idioma del Patrón', 
                               help="Idioma para el que fue creado este patrón")
    marca_patron = fields.Char('Marca del Patrón', 
                              help="Marca específica para la que fue creado")
    formato_origen = fields.Char('Formato de Origen', 
                                help="Formato del correo que generó este patrón")
    casos_detectados = fields.Integer('Casos Detectados', default=0, 
                                     help="Número de veces que este patrón ha detectado correctamente")
    casos_fallidos = fields.Integer('Casos Fallidos', default=0, 
                                   help="Número de veces que este patrón falló")
   
    validado_manualmente = fields.Boolean('Validado Manualmente', default=False, 
                                         help="Si el patrón fue validado por un usuario")
    
    # CAMPOS CALCULADOS
    tasa_exito = fields.Float('Tasa de Éxito (%)', compute='_compute_tasa_exito', store=True,
                             help="Porcentaje de éxito del patrón")
    estado_patron = fields.Selection([
        ('nuevo', 'Nuevo'),
        ('activo', 'Activo'),
        ('efectivo', 'Muy Efectivo'),
        ('problematico', 'Problemático'),
        ('obsoleto', 'Obsoleto')
    ], string='Estado del Patrón', compute='_compute_estado_patron', store=True)
    
    @api.depends('casos_detectados', 'casos_fallidos')
    def _compute_tasa_exito(self):
        """Calcula la tasa de éxito del patrón"""
        for patron in self:
            total_casos = patron.casos_detectados + patron.casos_fallidos
            if total_casos > 0:
                patron.tasa_exito = (patron.casos_detectados / total_casos) * 100
            else:
                patron.tasa_exito = 0.0
    
    @api.depends('tasa_exito', 'veces_usado', 'activo')
    def _compute_estado_patron(self):
        """Determina el estado del patrón basado en su rendimiento"""
        for patron in self:
            if not patron.activo:
                patron.estado_patron = 'obsoleto'
            elif patron.veces_usado == 0:
                patron.estado_patron = 'nuevo'
            elif patron.tasa_exito >= 90 and patron.veces_usado > 5:
                patron.estado_patron = 'efectivo'
            elif patron.tasa_exito < 30 and patron.veces_usado > 3:
                patron.estado_patron = 'problematico'
            else:
                patron.estado_patron = 'activo'

    @api.model
    def create_default_patterns(self):
        """
        Crea patrones por defecto si no existen (ACTUALIZADO)
        """
        patrones_default = [
            # PATRONES PARA SERIE - MEJORADOS
            {
                'name': 'Serie Bizhub - Corchetes',
                'tipo': 'serie',
                'patron_regex': r'\[Número de serie\],?\s*([A-Z0-9]{5,15})',
                'descripcion': 'Detecta serie en formato Bizhub con corchetes',
                'ejemplo': '[Número de serie], A5C4011011874',
                'orden': 1,
                'idioma_patron': 'bizhub_format',
                'marca_patron': 'Bizhub'
            },
            {
                'name': 'Serie Ricoh - Dos puntos',
                'tipo': 'serie',
                'patron_regex': r'N[ºo°]\s*de\s*serie\s*:?\s*([A-Z0-9]{5,15})',
                'descripcion': 'Detecta serie en formato Ricoh con dos puntos',
                'ejemplo': 'Nº de serie: 3359PB02667',
                'orden': 2,
                'idioma_patron': 'ricoh_format',
                'marca_patron': 'Ricoh'
            },
            {
                'name': 'Serie estándar genérica',
                'tipo': 'serie',
                'patron_regex': r'(?:serie|serial|s/?n)\s*:?\s*([A-Z0-9]{5,15})',
                'descripcion': 'Detecta serie en formato genérico',
                'ejemplo': 'Serie: A5C4011011874',
                'orden': 5,
                'idioma_patron': 'español'
            },
            
            # PATRONES PARA CONTADOR B/N - MEJORADOS
            {
                'name': 'BN Bizhub - Corchetes Negro',
                'tipo': 'contador_bn',
                'patron_regex': r'\[Contador de negro total\],?\s*(\d{1,9})',
                'descripcion': 'Detecta contador B/N en formato Bizhub',
                'ejemplo': '[Contador de negro total],00183098',
                'orden': 1,
                'idioma_patron': 'bizhub_format',
                'marca_patron': 'Bizhub'
            },
            {
                'name': 'BN Ricoh - T_TotalPrtPGS',
                'tipo': 'contador_bn',
                'patron_regex': r'T_TotalPrtPGS\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta contador B/N en formato Ricoh',
                'ejemplo': 'T_TotalPrtPGS:36089',
                'orden': 2,
                'idioma_patron': 'ricoh_format',
                'marca_patron': 'Ricoh'
            },
            {
                'name': 'BN genérico',
                'tipo': 'contador_bn',
                'patron_regex': r'(?:contador\s*)?(?:b/?n|negro|black|mono)\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta contador B/N genérico',
                'ejemplo': 'Contador BN: 183098',
                'orden': 5,
                'idioma_patron': 'español'
            },
            
            # PATRONES PARA CONTADOR COLOR - MEJORADOS
            {
                'name': 'Color Bizhub - Corchetes Color',
                'tipo': 'contador_color',
                'patron_regex': r'\[Contador de color total\],?\s*(\d{1,9})',
                'descripcion': 'Detecta contador color en formato Bizhub',
                'ejemplo': '[Contador de color total],00085643',
                'orden': 1,
                'idioma_patron': 'bizhub_format',
                'marca_patron': 'Bizhub'
            },
            {
                'name': 'Color Ricoh - T_ColorPrtPGS',
                'tipo': 'contador_color',
                'patron_regex': r'T_ColorPrtPGS\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta contador color en formato Ricoh',
                'ejemplo': 'T_ColorPrtPGS:15234',
                'orden': 2,
                'idioma_patron': 'ricoh_format',
                'marca_patron': 'Ricoh'
            },
            {
                'name': 'Color genérico',
                'tipo': 'contador_color',
                'patron_regex': r'(?:contador\s*)?color\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta contador color genérico',
                'ejemplo': 'Contador Color: 85643',
                'orden': 5,
                'idioma_patron': 'español'
            },
            
            # PATRONES PARA CONTADOR SCAN - MEJORADOS
            {
                'name': 'Total Bizhub - Corchetes Total',
                'tipo': 'contador_scan',
                'patron_regex': r'\[Contador total\],?\s*(\d{1,9})',
                'descripcion': 'Detecta contador total en formato Bizhub',
                'ejemplo': '[Contador total],00268741',
                'orden': 1,
                'idioma_patron': 'bizhub_format',
                'marca_patron': 'Bizhub'
            },
            {
                'name': 'Scan Ricoh - T_ScanPGS',
                'tipo': 'contador_scan',
                'patron_regex': r'T_ScanPGS\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta contador scan en formato Ricoh',
                'ejemplo': 'T_ScanPGS:5432',
                'orden': 2,
                'idioma_patron': 'ricoh_format',
                'marca_patron': 'Ricoh'
            },
            {
                'name': 'Scan genérico',
                'tipo': 'contador_scan',
                'patron_regex': r'(?:contador\s*)?(?:scan|escaneo|total)\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta contador scan genérico',
                'ejemplo': 'Contador Scan: 66775',
                'orden': 5,
                'idioma_patron': 'español'
            }
        ]
        
        for patron_data in patrones_default:
            # Solo crear si no existe un patrón similar
            existe = self.search([
                ('tipo', '=', patron_data['tipo']),
                ('name', '=', patron_data['name'])
            ])
            
            if not existe:
                self.create(patron_data)
                _logger.info(f"✅ Patrón creado: {patron_data['name']}")

    def probar_patron(self):
        """
        Prueba el patrón con el texto de ejemplo (MEJORADO)
        """
        self.ensure_one()
        
        if not self.ejemplo:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Agregue un texto de ejemplo para probar',
                    'type': 'warning'
                }
            }
        
        try:
            matches = re.finditer(self.patron_regex, self.ejemplo, re.IGNORECASE)
            resultados = []
            
            for match in matches:
                if match.groups():
                    valor = match.group(1)
                    resultados.append(valor)
            
            if resultados:
                mensaje = f"✅ Patrón funciona! Valores detectados: {', '.join(resultados)}"
                tipo = 'success'
                
                # Registrar caso exitoso
                self.casos_detectados += 1
                
            else:
                mensaje = "⚠️ El patrón no detectó ningún valor en el ejemplo"
                tipo = 'warning'
                
                # Registrar caso fallido
                self.casos_fallidos += 1
                
        except re.error as e:
            mensaje = f"❌ Error en expresión regular: {str(e)}"
            tipo = 'danger'
            
            # Registrar caso fallido
            self.casos_fallidos += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': mensaje,
                'type': tipo
            }
        }

    

    def marcar_deteccion_exitosa(self):
        """
        NUEVO: Marca una detección exitosa
        """
        self.ensure_one()
        self.sudo().write({
            'casos_detectados': self.casos_detectados + 1,
            'veces_usado': self.veces_usado + 1,
            'ultima_deteccion': fields.Datetime.now()
        })

   

    @api.model
    def buscar_por_tipo(self, tipo, texto):
        """
        Busca patrones de un tipo específico en el texto.
        Para 'serie', exige al menos una letra en el resultado.
        """
        patrones = self.search(
            [('tipo', '=', tipo), ('activo', '=', True)],
            order='orden'
        )
        for patron in patrones:
            try:
                for match in re.finditer(patron.patron_regex, texto, re.IGNORECASE):
                    if not match.groups():
                        continue
                    valor = match.group(1).strip()
                    if not valor:
                        continue

                    if tipo == 'serie':
                        val = valor.upper()
                        # longitud >=5, solo A–Z y 0–9, y al menos UNA letra
                        if (len(val) >= 5
                                and re.match(r'^[A-Z0-9]+$', val)
                                and re.search(r'[A-Z]', val)):
                            patron.marcar_deteccion_exitosa()
                            return val
                        # CAMBIO AQUÍ - reemplazar marcar_deteccion_fallida()
                        patron.sudo().write({
                            'casos_fallidos': patron.casos_fallidos + 1,
                            'veces_usado': patron.veces_usado + 1
                        })
                    else:
                        # contador: convertimos a entero y >0
                        numero = int(re.sub(r'[^0-9]', '', valor) or 0)
                        if numero > 0:
                            patron.marcar_deteccion_exitosa()
                            return numero
                        # CAMBIO AQUÍ - reemplazar marcar_deteccion_fallida()
                        patron.sudo().write({
                            'casos_fallidos': patron.casos_fallidos + 1,
                            'veces_usado': patron.veces_usado + 1
                        })
            except re.error:
                _logger.warning(f"Error en patrón {patron.name}: {patron.patron_regex}")
                # CAMBIO AQUÍ - reemplazar marcar_deteccion_fallida()
                patron.sudo().write({
                    'casos_fallidos': patron.casos_fallidos + 1,
                    'veces_usado': patron.veces_usado + 1
                })
        return None



    def validar_patron_manualmente(self):
        """
        NUEVO: Valida manualmente un patrón auto-generado
        """
        self.ensure_one()
        
        if not self.auto_generado:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Solo se pueden validar patrones auto-generados',
                    'type': 'warning'
                }
            }
        
        self.write({
            'validado_manualmente': True,
            'confianza_patron': min(100.0, self.confianza_patron + 20.0)  # Aumentar confianza
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Patrón "{self.name}" validado manualmente',
                'type': 'success'
            }
        }

    def desactivar_patron_inefectivo(self):
        """
        NUEVO: Desactiva patrones con baja efectividad
        """
        self.ensure_one()
        
        if self.tasa_exito < 20 and self.veces_usado > 5:
            self.write({'activo': False})
            _logger.info(f"⏸️ Patrón desactivado por baja efectividad: {self.name} ({self.tasa_exito:.1f}%)")
            return True
        
        return False

    @api.model
    def limpiar_patrones_obsoletos(self):
        """
        NUEVO: Limpia patrones obsoletos automáticamente
        """
        # Buscar patrones auto-generados con muy baja efectividad
        patrones_obsoletos = self.search([
            ('auto_generado', '=', True),
            ('activo', '=', True),
            ('veces_usado', '>', 10),
            ('tasa_exito', '<', 15)
        ])
        
        patrones_desactivados = 0
        for patron in patrones_obsoletos:
            patron.write({'activo': False})
            patrones_desactivados += 1
            _logger.info(f"🗑️ Patrón obsoleto desactivado: {patron.name}")
        
        # Buscar patrones nunca usados después de 30 días
        fecha_limite = fields.Datetime.now() - timedelta(days=30)
        patrones_no_usados = self.search([
            ('auto_generado', '=', True),
            ('veces_usado', '=', 0),
            ('create_date', '<', fecha_limite)
        ])
        
        for patron in patrones_no_usados:
            patron.unlink()
            patrones_desactivados += 1
            _logger.info(f"🗑️ Patrón no usado eliminado: {patron.name}")
        
        return patrones_desactivados

    @api.model
    def obtener_estadisticas_patrones(self):
        """
        NUEVO: Obtiene estadísticas completas de patrones
        """
        estadisticas = {
            'total_patrones': self.search_count([]),
            'patrones_activos': self.search_count([('activo', '=', True)]),
            'patrones_auto_generados': self.search_count([('auto_generado', '=', True)]),
            'patrones_validados': self.search_count([('validado_manualmente', '=', True)]),
            'patrones_efectivos': self.search_count([('estado_patron', '=', 'efectivo')]),
            'patrones_problematicos': self.search_count([('estado_patron', '=', 'problematico')])
        }
        
        # Top 5 patrones más usados
        top_patrones = self.search([
            ('veces_usado', '>', 0)
        ], order='veces_usado desc', limit=5)
        
        estadisticas['top_patrones'] = [
            {
                'nombre': p.name,
                'tipo': p.tipo,
                'veces_usado': p.veces_usado,
                'tasa_exito': p.tasa_exito
            }
            for p in top_patrones
        ]
        
        return estadisticas
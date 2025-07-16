from odoo import models, fields, api
import logging
import re

_logger = logging.getLogger(__name__)

class PatronContador(models.Model):
    _name = 'patron.contador'
    _description = 'Patrones configurables para detectar contadores y series'
    _order = 'tipo, orden, name'
    
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
    
    # Estadísticas de uso
    veces_usado = fields.Integer('Veces usado', default=0, readonly=True)
    ultima_deteccion = fields.Datetime('Última detección', readonly=True)
    
    @api.model
    def create_default_patterns(self):
        """
        Crea patrones por defecto si no existen
        """
        patrones_default = [
            # PATRONES PARA SERIE
            {
                'name': 'Serie estándar con dos puntos',
                'tipo': 'serie',
                'patron_regex': r'(?:serie|serial|s/?n)\s*:?\s*([A-Z0-9]{5,15})',
                'descripcion': 'Detecta: Serie: ABC123456',
                'ejemplo': 'Serie: A5C4011011874',
                'orden': 10
            },
            {
                'name': 'Serie entre corchetes',
                'tipo': 'serie',
                'patron_regex': r'\[Número de serie\]\s*,?\s*([A-Z0-9]{5,15})',
                'descripcion': 'Detecta: [Número de serie], ABC123456',
                'ejemplo': '[Número de serie], A5C4011011874',
                'orden': 5
            },
            {
                'name': 'Serie formato libre',
                'tipo': 'serie',
                'patron_regex': r'([A-Z]{2,4}\d{5,10})',
                'descripcion': 'Detecta formatos como AB12345678',
                'ejemplo': 'A5C4011011874',
                'orden': 20
            },
            
            # PATRONES PARA CONTADOR B/N
            {
                'name': 'Contador BN estándar',
                'tipo': 'contador_bn',
                'patron_regex': r'(?:contador|total)?\s*(?:b/?n|blanco?\s*y?\s*negro|black|mono)\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta: Contador BN: 123456',
                'ejemplo': 'Contador BN: 183098',
                'orden': 10
            },
            {
                'name': 'Contador negro entre corchetes',
                'tipo': 'contador_bn',
                'patron_regex': r'\[Contador de negro total\]\s*,?\s*(\d{1,9})',
                'descripcion': 'Detecta: [Contador de negro total],123456',
                'ejemplo': '[Contador de negro total],00183098',
                'orden': 5
            },
            
            # PATRONES PARA CONTADOR COLOR
            {
                'name': 'Contador color estándar',
                'tipo': 'contador_color',
                'patron_regex': r'(?:contador|total)?\s*(?:color|col)\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta: Contador Color: 123456',
                'ejemplo': 'Contador Color: 85643',
                'orden': 10
            },
            {
                'name': 'Contador color entre corchetes',
                'tipo': 'contador_color',
                'patron_regex': r'\[Contador de color total\]\s*,?\s*(\d{1,9})',
                'descripcion': 'Detecta: [Contador de color total],123456',
                'ejemplo': '[Contador de color total],00085643',
                'orden': 5
            },
            
            # PATRONES PARA CONTADOR SCAN
            {
                'name': 'Contador scan estándar',
                'tipo': 'contador_scan',
                'patron_regex': r'(?:contador|total)?\s*(?:scan|escaner|digitalizacion)\s*:?\s*(\d{1,9})',
                'descripcion': 'Detecta: Contador Scan: 123456',
                'ejemplo': 'Contador Scan: 66775',
                'orden': 10
            },
            {
                'name': 'Contador scan entre corchetes',
                'tipo': 'contador_scan',
                'patron_regex': r'\[Contador total de escaneo/?fax\]\s*,?\s*(\d{1,9})',
                'descripcion': 'Detecta: [Contador total de escaneo/fax],123456',
                'ejemplo': '[Contador total de escaneo/fax],00066775',
                'orden': 5
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
        Prueba el patrón con el texto de ejemplo
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
            else:
                mensaje = "⚠️ El patrón no detectó ningún valor en el ejemplo"
                tipo = 'warning'
                
        except re.error as e:
            mensaje = f"❌ Error en expresión regular: {str(e)}"
            tipo = 'danger'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': mensaje,
                'type': tipo
            }
        }

    def marcar_uso(self):
        """
        Marca que el patrón fue usado (para estadísticas)
        """
        self.ensure_one()
        self.sudo().write({
            'veces_usado': self.veces_usado + 1,
            'ultima_deteccion': fields.Datetime.now()
        })

    @api.model
    def buscar_por_tipo(self, tipo, texto):
        """
        Busca patrones de un tipo específico en el texto
        """
        patrones = self.search([
            ('tipo', '=', tipo),
            ('activo', '=', True)
        ], order='orden')
        
        for patron in patrones:
            try:
                matches = re.finditer(patron.patron_regex, texto, re.IGNORECASE)
                for match in matches:
                    if match.groups():
                        valor = match.group(1).strip()
                        if valor:
                            # Si es serie, validar formato
                            if tipo == 'serie':
                                if len(valor) >= 5 and re.match(r'^[A-Z0-9]+$', valor.upper()):
                                    patron.marcar_uso()
                                    return valor.upper()
                            else:
                                # Si es contador, validar que sea número
                                try:
                                    numero = int(re.sub(r'[^0-9]', '', valor))
                                    if numero > 0:
                                        patron.marcar_uso()
                                        return numero
                                except:
                                    continue
            except re.error:
                _logger.warning(f"Error en patrón {patron.name}: {patron.patron_regex}")
                continue
        
        return None
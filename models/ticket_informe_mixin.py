# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime
import random
import logging

_logger = logging.getLogger(__name__)


class TicketInformeMixin(models.AbstractModel):
    """
    Mixin para generación automática de informes técnicos con lenguaje natural.
    
    Hereda este mixin en cualquier modelo que necesite generar informes técnicos
    basados en checklists de servicio.
    
    Campos requeridos en el modelo que herede:
    - informe_id: fields.Html()
    - calidad_id: fields.Selection()
    - tipo_servicio_id: fields.Selection()
    - tipo_id: fields.Selection() para equipos color/monocromo
    - description: fields.Text() problema reportado
    - responsable: fields.Many2one('res.users')
    - agenda: fields.Datetime()
    - direccion_id_r: fields.Char()
    - Campos del checklist (copia_id, impresion_id, etc.)
    - Campos de tóner (toner_black_id, etc.)
    - Campos de contadores (contometrok_id, contometroc_id, contometros_id)
    """
    
    _name = 'ticket.informe.mixin'
    _description = 'Mixin para Generación de Informes Técnicos'

    # ===========================
    #  DATOS Y CONFIGURACIÓN
    # ===========================

    # (1) Vocabulario y variaciones para generar texto natural
    _VARIACIONES_INTRODUCCION = {
        'instalacion': [
            "Se realizó la instalación completa del equipo en las instalaciones del cliente",
            "Hemos completado exitosamente la instalación del equipo multifuncional",
            "Se efectuó el proceso de instalación y puesta en marcha del equipo",
        ],
        'retiro': [
            "Se procedió con el retiro del equipo de las instalaciones del cliente",
            "Hemos completado el proceso de desinstalación y retiro del equipo",
            "Se efectuó el desmontaje y retiro del equipo multifuncional",
        ],
        'mantenimiento_preventivo': [
            "Se ejecutó el mantenimiento preventivo programado del equipo",
            "Hemos realizado el servicio de mantenimiento preventivo integral",
            "Se completó la rutina de mantenimiento preventivo del equipo multifuncional",
        ],
        'mantenimiento_correctivo': [
            "Se atendió el reporte de falla realizando el mantenimiento correctivo necesario",
            "Hemos intervenido el equipo para solucionar las fallas reportadas",
            "Se ejecutó el mantenimiento correctivo según el problema identificado",
        ],
        'cambio_repuestos': [
            "Se procedió con el reemplazo de los repuestos según lo programado",
            "Hemos completado el cambio de componentes del equipo",
            "Se realizó la sustitución de repuestos para restaurar el funcionamiento óptimo",
        ],
        'remoto': [
            "Se brindó asistencia técnica remota para resolver la incidencia reportada",
            "Hemos atendido el caso mediante soporte técnico remoto",
            "Se solucionó el problema reportado a través de asistencia remota",
        ],
        'revision': [
            "Se efectuó la revisión técnica general del equipo",
            "Hemos completado la inspección y diagnóstico del estado del equipo",
            "Se realizó una evaluación completa del funcionamiento del equipo",
        ],
        'alquiler': [
            "Se preparó el equipo para su entrega en condiciones óptimas de alquiler",
            "Hemos acondicionado el equipo cumpliendo los estándares de alquiler",
            "Se completó la preparación del equipo para su operación en modalidad de alquiler",
        ],
    }

    _CONECTORES_TRABAJO = [
        "Durante la intervención",
        "En el transcurso del servicio",
        "Como parte del proceso",
        "Al realizar la inspección",
        "Durante la revisión técnica",
    ]

    _FRASES_HALLAZGO = {
        'positivo': [
            "el equipo mostró un funcionamiento adecuado",
            "se verificó que el equipo opera correctamente",
            "el equipo presentó condiciones óptimas de operación",
            "se comprobó el correcto desempeño del equipo",
        ],
        'neutro': [
            "se identificaron algunos puntos que requieren atención",
            "se detectaron aspectos que necesitan seguimiento",
            "se observaron detalles que ameritan monitoreo",
        ],
        'negativo': [
            "se identificaron fallas que requieren atención inmediata",
            "se detectaron problemas críticos que afectan el funcionamiento",
            "se encontraron deficiencias que comprometen la operatividad",
        ],
    }

    # (2) Mapa completo del checklist con contexto
    _CHECKLIST_DETALLADO = {
        # Funcionalidades principales
        'copia_id': {
            'nombre': 'función de copia',
            'critico': True,
            'msg_falla': 'El módulo de copiado no responde, requiere diagnóstico profundo',
            'msg_ok': 'copiado operativo',
        },
        'impresion_id': {
            'nombre': 'función de impresión',
            'critico': True,
            'msg_falla': 'La función de impresión presenta fallos, necesita revisión urgente',
            'msg_ok': 'impresión funcionando correctamente',
        },
        'impresion_usb_id': {
            'nombre': 'impresión USB',
            'critico': False,
            'msg_falla': 'El puerto USB para impresión no está operativo',
            'msg_ok': 'impresión USB habilitada',
        },
        'scaner_smb_id': {
            'nombre': 'escaneo SMB',
            'critico': False,
            'msg_falla': 'La función de escaneo a red (SMB) requiere configuración',
            'msg_ok': 'escaneo SMB configurado',
        },
        'scaner_usb_id': {
            'nombre': 'escaneo USB',
            'critico': False,
            'msg_falla': 'El escaneo vía USB no está disponible',
            'msg_ok': 'escaneo USB operativo',
        },
        'scaner_ftp_id': {
            'nombre': 'escaneo FTP',
            'critico': False,
            'msg_falla': 'La configuración FTP para escaneo necesita ajustes',
            'msg_ok': 'escaneo FTP configurado',
        },
        'scaner_mail_id': {
            'nombre': 'escaneo a email',
            'critico': False,
            'msg_falla': 'El escaneo directo a correo electrónico no está funcional',
            'msg_ok': 'escaneo a email habilitado',
        },
        
        # Módulos de transporte de papel
        'adf_id': {
            'nombre': 'alimentador automático de documentos (ADF)',
            'critico': True,
            'msg_falla': 'El ADF presenta fallas en el arrastre de papel',
            'msg_desgaste': 'Los rodillos del ADF muestran desgaste y requieren reemplazo preventivo',
            'msg_cambio': 'El ADF debe ser reemplazado por falla estructural',
            'msg_ok': 'ADF operando sin inconvenientes',
        },
        'bypass_id': {
            'nombre': 'bandeja bypass',
            'critico': False,
            'msg_falla': 'La bandeja bypass no alimenta papel correctamente',
            'msg_desgaste': 'El mecanismo del bypass presenta desgaste moderado',
            'msg_cambio': 'Se requiere reemplazo del conjunto bypass',
            'msg_ok': 'bypass funcionando normalmente',
        },
        'tray1_id': {
            'nombre': 'bandeja 1',
            'critico': True,
            'msg_falla': 'La bandeja 1 no alimenta papel, requiere ajuste urgente',
            'msg_desgaste': 'Los rodillos de la bandeja 1 muestran desgaste',
            'msg_cambio': 'Es necesario reemplazar el conjunto de la bandeja 1',
            'msg_ok': 'bandeja 1 operativa',
        },
        'tray2_id': {
            'nombre': 'bandeja 2',
            'critico': False,
            'msg_falla': 'La bandeja 2 presenta problemas de alimentación',
            'msg_desgaste': 'Rodillos de la bandeja 2 con desgaste visible',
            'msg_cambio': 'Se recomienda cambio del módulo de bandeja 2',
            'msg_ok': 'bandeja 2 funcionando',
        },
        'tray3_id': {
            'nombre': 'bandeja 3',
            'critico': False,
            'msg_falla': 'La bandeja 3 no está alimentando correctamente',
            'msg_desgaste': 'Componentes de bandeja 3 con desgaste',
            'msg_cambio': 'Requiere reemplazo de bandeja 3',
            'msg_ok': 'bandeja 3 operativa',
        },
        'tray4_id': {
            'nombre': 'bandeja 4',
            'critico': False,
            'msg_falla': 'La bandeja 4 presenta fallas de alimentación',
            'msg_desgaste': 'Bandeja 4 con desgaste en componentes',
            'msg_cambio': 'Se debe reemplazar bandeja 4',
            'msg_ok': 'bandeja 4 funcionando',
        },
        'finalizador_id': {
            'nombre': 'finalizador',
            'critico': False,
            'msg_falla': 'El finalizador no está operando, necesita revisión',
            'msg_desgaste': 'El finalizador muestra desgaste en su mecanismo',
            'msg_cambio': 'Es necesario reemplazar el módulo finalizador',
            'msg_ok': 'finalizador operativo',
        },
        
        # Componentes del proceso de impresión
        'tacho_id': {
            'nombre': 'depósito de tóner residual',
            'critico': True,
            'msg_falla': 'El tacho residual está lleno, debe ser vaciado inmediatamente',
            'msg_desgaste': 'El tacho residual está llegando a su capacidad máxima',
            'msg_cambio': 'Se requiere reemplazo del tacho de residuos',
            'msg_ok': 'nivel de residuos normal',
        },
        'fusora_id': {
            'nombre': 'unidad fusora',
            'critico': True,
            'msg_falla': 'La fusora no está alcanzando temperatura, equipo inoperativo',
            'msg_desgaste': 'La fusora muestra signos de desgaste, planificar su reemplazo',
            'msg_cambio': 'Es urgente el reemplazo de la unidad fusora',
            'msg_ok': 'fusora operando a temperatura correcta',
        },
        'transfer_id': {
            'nombre': 'faja de transferencia',
            'critico': True,
            'msg_falla': 'La faja de transferencia presenta fallas, afecta calidad de impresión',
            'msg_desgaste': 'La faja de transferencia muestra desgaste, considerar reemplazo',
            'msg_cambio': 'Se debe reemplazar la faja de transferencia de inmediato',
            'msg_ok': 'faja de transferencia en buen estado',
        },
        'optico_id': {
            'nombre': 'unidad óptica/láser',
            'critico': True,
            'msg_falla': 'La unidad óptica no está funcionando, impide la impresión',
            'msg_desgaste': 'El sistema óptico requiere limpieza profunda o reemplazo preventivo',
            'msg_cambio': 'Es necesario reemplazar la unidad óptica',
            'msg_ok': 'unidad óptica operativa',
        },
        'black_id': {
            'nombre': 'unidad de imagen negro',
            'critico': True,
            'msg_falla': 'El drum negro está dañado, genera defectos en la impresión',
            'msg_desgaste': 'El drum negro muestra desgaste, programar su reemplazo',
            'msg_cambio': 'Se requiere cambio inmediato del drum negro',
            'msg_ok': 'drum negro en condiciones óptimas',
        },
        'magenta_id': {
            'nombre': 'unidad de imagen magenta',
            'critico': False,
            'msg_falla': 'El drum magenta presenta fallas',
            'msg_desgaste': 'Drum magenta con desgaste visible',
            'msg_cambio': 'Requiere reemplazo del drum magenta',
            'msg_ok': 'drum magenta operativo',
        },
        'cyan_id': {
            'nombre': 'unidad de imagen cian',
            'critico': False,
            'msg_falla': 'El drum cian no está operando correctamente',
            'msg_desgaste': 'Drum cian con desgaste',
            'msg_cambio': 'Necesario cambiar drum cian',
            'msg_ok': 'drum cian en buen estado',
        },
        'yellow_id': {
            'nombre': 'unidad de imagen amarillo',
            'critico': False,
            'msg_falla': 'El drum amarillo presenta defectos',
            'msg_desgaste': 'Drum amarillo con desgaste',
            'msg_cambio': 'Se debe reemplazar drum amarillo',
            'msg_ok': 'drum amarillo operativo',
        },
    }

    _TONER_INFO = {
        'toner_black_id': {
            'nombre': 'tóner negro',
            'msg_vacio': 'El tóner negro está vacío y debe ser reemplazado de inmediato',
            'msg_medio': 'El tóner negro se encuentra al 50% aproximadamente',
            'msg_lleno': 'tóner negro con nivel óptimo',
            'msg_sin_botella': 'No se detecta botella de tóner negro instalada',
        },
        'toner_cyan_id': {
            'nombre': 'tóner cian',
            'msg_vacio': 'El tóner cian está vacío, requiere reemplazo',
            'msg_medio': 'Tóner cian con nivel medio (aproximadamente 50%)',
            'msg_lleno': 'tóner cian con nivel adecuado',
            'msg_sin_botella': 'Falta instalar botella de tóner cian',
        },
        'toner_magenta_id': {
            'nombre': 'tóner magenta',
            'msg_vacio': 'El tóner magenta está vacío y debe reemplazarse',
            'msg_medio': 'Tóner magenta con nivel medio',
            'msg_lleno': 'tóner magenta en nivel óptimo',
            'msg_sin_botella': 'No hay botella de tóner magenta instalada',
        },
        'toner_yellow_id': {
            'nombre': 'tóner amarillo',
            'msg_vacio': 'El tóner amarillo está agotado, necesita reemplazo',
            'msg_medio': 'Tóner amarillo con nivel medio',
            'msg_lleno': 'tóner amarillo con carga suficiente',
            'msg_sin_botella': 'Falta botella de tóner amarillo',
        },
    }

    # ===========================
    #  MÉTODOS AUXILIARES
    # ===========================

    def _pick_random(self, lista):
        """Selecciona aleatoriamente un elemento de una lista"""
        return random.choice(lista) if lista else ""

    def _is_autogen_informe(self):
        """Verifica si el informe actual fue autogenerado"""
        html = (self.informe_id or '').lower()
        return 'data-autogen="1"' in html

    # ===========================
    #  MÉTODOS DE GENERACIÓN
    # ===========================

    def _generar_intro_servicio(self):
        """Genera introducción variable según tipo de servicio"""
        tipo = self.tipo_servicio_id or 'revision'
        variaciones = self._VARIACIONES_INTRODUCCION.get(tipo, self._VARIACIONES_INTRODUCCION['revision'])
        intro = self._pick_random(variaciones)
        
        # Agregar contexto de lugar si es relevante
        if hasattr(self, 'direccion_id_r') and self.direccion_id_r and tipo in ['instalacion', 'retiro', 'mantenimiento_preventivo', 'mantenimiento_correctivo']:
            return f"{intro}. El servicio se realizó en {self.direccion_id_r}."
        
        return f"{intro}."

    def _analizar_checklist_completo(self):
        """
        Analiza todo el checklist y retorna datos estructurados
        """
        resultado = {
            'funciones_criticas_fallando': [],
            'funciones_secundarias_fallando': [],
            'componentes_criticos_falla': [],
            'componentes_desgaste': [],
            'componentes_cambio_urgente': [],
            'componentes_ok': [],
            'toners_criticos': [],
            'toners_medios': [],
            'toners_ok': [],
            'score_gravedad': 0,
            'tiene_problemas_graves': False,
        }

        # Analizar funciones y componentes
        for field_name, info in self._CHECKLIST_DETALLADO.items():
            if field_name not in self._fields:
                continue
                
            valor = getattr(self, field_name, False)
            if not valor or valor == 'no_aplica':
                continue

            if valor == 'si':
                resultado['componentes_ok'].append(info['msg_ok'])
                continue

            # Detectar fallas
            if valor == 'no':
                if field_name in ['copia_id', 'impresion_id', 'scaner_smb_id', 'scaner_usb_id', 'scaner_ftp_id', 'scaner_mail_id', 'impresion_usb_id']:
                    if info.get('critico'):
                        resultado['funciones_criticas_fallando'].append(info['msg_falla'])
                        resultado['score_gravedad'] += 15
                        resultado['tiene_problemas_graves'] = True
                    else:
                        resultado['funciones_secundarias_fallando'].append(info['msg_falla'])
                        resultado['score_gravedad'] += 8
                else:
                    if info.get('critico'):
                        resultado['componentes_criticos_falla'].append(info['msg_falla'])
                        resultado['score_gravedad'] += 12
                        resultado['tiene_problemas_graves'] = True
                    else:
                        resultado['componentes_desgaste'].append(info['msg_falla'])
                        resultado['score_gravedad'] += 6

            elif valor == 'desgaste':
                resultado['componentes_desgaste'].append(info.get('msg_desgaste', f"{info['nombre']} con desgaste"))
                resultado['score_gravedad'] += 5

            elif valor == 'cambio':
                resultado['componentes_cambio_urgente'].append(info.get('msg_cambio', f"{info['nombre']} requiere reemplazo"))
                resultado['score_gravedad'] += 10
                resultado['tiene_problemas_graves'] = True

        # Analizar tóners
        for field_name, info in self._TONER_INFO.items():
            if field_name not in self._fields:
                continue
            
            # Solo analizar tóner color si el equipo es a color
            if hasattr(self, 'tipo_id') and self.tipo_id != 'color' and field_name != 'toner_black_id':
                continue

            valor = getattr(self, field_name, False)
            if not valor or valor == 'no_aplica':
                continue

            if valor == 'vacio':
                resultado['toners_criticos'].append(info['msg_vacio'])
                resultado['score_gravedad'] += 3
            elif valor == 'sin_botella':
                resultado['toners_criticos'].append(info['msg_sin_botella'])
                resultado['score_gravedad'] += 4
            elif valor == 'medio':
                resultado['toners_medios'].append(info['msg_medio'])
            elif valor == 'lleno':
                resultado['toners_ok'].append(info['msg_lleno'])

        return resultado

    def _generar_seccion_hallazgos(self, analisis):
        """Genera la sección de hallazgos con lenguaje natural"""
        parrafos = []
        conector = self._pick_random(self._CONECTORES_TRABAJO)

        # 1. Funciones críticas fallando
        if analisis['funciones_criticas_fallando']:
            parrafos.append(
                f"{conector}, se identificaron problemas críticos en las funciones principales del equipo:"
            )
            parrafos.append("<ul>")
            for msg in analisis['funciones_criticas_fallando']:
                parrafos.append(f"<li>{msg}.</li>")
            parrafos.append("</ul>")
            parrafos.append("<p><strong>⚠️ Estos problemas impiden el uso normal del equipo y requieren atención inmediata.</strong></p>")

        # 2. Componentes críticos con falla
        if analisis['componentes_criticos_falla']:
            if not analisis['funciones_criticas_fallando']:
                parrafos.append(f"{conector}, se detectaron fallas en componentes críticos:")
            else:
                parrafos.append("<p>Adicionalmente, se encontraron fallas en componentes esenciales:</p>")
            
            parrafos.append("<ul>")
            for msg in analisis['componentes_criticos_falla']:
                parrafos.append(f"<li>{msg}.</li>")
            parrafos.append("</ul>")

        # 3. Componentes que requieren cambio urgente
        if analisis['componentes_cambio_urgente']:
            parrafos.append("<p><strong>Componentes que requieren reemplazo inmediato:</strong></p>")
            parrafos.append("<ul>")
            for msg in analisis['componentes_cambio_urgente']:
                parrafos.append(f"<li>{msg}.</li>")
            parrafos.append("</ul>")

        # 4. Componentes con desgaste
        if analisis['componentes_desgaste']:
            parrafos.append("<p><strong>Componentes con desgaste (programar reemplazo preventivo):</strong></p>")
            parrafos.append("<ul>")
            for msg in analisis['componentes_desgaste']:
                parrafos.append(f"<li>{msg}.</li>")
            parrafos.append("</ul>")

        # 5. Funciones secundarias con problemas
        if analisis['funciones_secundarias_fallando']:
            parrafos.append("<p><strong>Funciones adicionales que requieren atención:</strong></p>")
            parrafos.append("<ul>")
            for msg in analisis['funciones_secundarias_fallando']:
                parrafos.append(f"<li>{msg}.</li>")
            parrafos.append("</ul>")

        # 6. Estado de consumibles
        if analisis['toners_criticos']:
            parrafos.append("<p><strong>Consumibles que requieren reposición:</strong></p>")
            parrafos.append("<ul>")
            for msg in analisis['toners_criticos']:
                parrafos.append(f"<li>{msg}.</li>")
            parrafos.append("</ul>")
        elif analisis['toners_medios']:
            parrafos.append("<p><strong>Estado de consumibles:</strong></p>")
            parrafos.append("<ul>")
            for msg in analisis['toners_medios']:
                parrafos.append(f"<li>{msg}.</li>")
            parrafos.append("</ul>")
            parrafos.append("<p>Se recomienda tener repuestos disponibles para evitar interrupciones.</p>")

        # 7. Si TODO está OK
        if not parrafos:
            frase_positiva = self._pick_random(self._FRASES_HALLAZGO['positivo'])
            parrafos.append(f"<p>{conector}, {frase_positiva}. Todas las funciones y componentes revisados operan dentro de los parámetros normales.</p>")
            
            if analisis['toners_ok']:
                parrafos.append(f"<p>Los consumibles se encuentran en niveles adecuados: {', '.join(analisis['toners_ok'])}.</p>")

        return '\n'.join(parrafos)

    def _generar_conclusiones_personalizadas(self, analisis):
        """Genera conclusiones y recomendaciones específicas"""
        parrafos = []
        score = analisis['score_gravedad']

        # Determinar tono de la conclusión
        if score >= 50:
            parrafos.append(
                "<p><strong style='color:#d32f2f;'>⚠️ ESTADO CRÍTICO:</strong> "
                "El equipo presenta fallas graves que impiden su operación normal. "
                "Se requiere intervención técnica urgente y probable reemplazo de componentes mayores.</p>"
            )
            
            if analisis['componentes_cambio_urgente']:
                parrafos.append(
                    "<p><strong>Acción inmediata requerida:</strong> Programar el reemplazo de los componentes indicados "
                    "en un plazo máximo de 48 horas para evitar daños adicionales al equipo.</p>"
                )
            
            if analisis['funciones_criticas_fallando']:
                parrafos.append(
                    "<p><strong>Impacto operativo:</strong> El equipo no puede cumplir con sus funciones básicas. "
                    "Se recomienda considerar un equipo de respaldo mientras se completan las reparaciones.</p>"
                )
                
        elif score >= 25:
            parrafos.append(
                "<p><strong style='color:#f57c00;'>⚠️ REQUIERE ATENCIÓN:</strong> "
                "El equipo presenta problemas moderados que afectan su rendimiento. "
                "Se recomienda programar el mantenimiento correctivo en los próximos 7 días.</p>"
            )
            
            if analisis['componentes_desgaste']:
                parrafos.append(
                    "<p><strong>Mantenimiento preventivo:</strong> Los componentes con desgaste deben ser reemplazados "
                    "en las próximas semanas para evitar fallas mayores.</p>"
                )
                
        elif score >= 10:
            parrafos.append(
                "<p><strong style='color:#fbc02d;'>✓ ESTADO ACEPTABLE:</strong> "
                "El equipo funciona correctamente, pero se identificaron aspectos que requieren seguimiento. "
                "Se recomienda programar un mantenimiento preventivo dentro de los próximos 15-30 días.</p>"
            )
            
        else:
            opciones_buenas = [
                "El equipo se encuentra en excelentes condiciones operativas. Todos los sistemas evaluados funcionan correctamente.",
                "El equipo opera de manera óptima. La evaluación técnica no reveló anomalías significativas.",
                "El equipo presenta un estado general excelente. Todos los componentes revisados están operativos.",
            ]
            parrafos.append(f"<p><strong style='color:#388e3c;'>✓ ESTADO ÓPTIMO:</strong> {self._pick_random(opciones_buenas)}</p>")

        # Recomendaciones generales
        parrafos.append("<p><strong>Recomendaciones:</strong></p>")
        parrafos.append("<ul>")
        
        if analisis['toners_medios'] or analisis['toners_criticos']:
            parrafos.append("<li>Mantener stock de consumibles (tóner) para evitar interrupciones.</li>")
        
        if analisis['componentes_desgaste']:
            parrafos.append("<li>Programar el reemplazo preventivo de componentes con desgaste identificado.</li>")
        
        if score < 25:
            parrafos.append("<li>Continuar con el programa de mantenimientos preventivos cada 3 meses.</li>")
            parrafos.append("<li>Mantener el equipo en ambientes con temperatura controlada y libre de polvo.</li>")
        
        if analisis['tiene_problemas_graves']:
            parrafos.append("<li>Evaluar la relación costo-beneficio de reparación vs. reemplazo del equipo.</li>")
            parrafos.append("<li>Solicitar cotización formal para los trabajos de reparación identificados.</li>")
        
        parrafos.append("</ul>")

        # Próximos pasos
        if score >= 25:
            parrafos.append(
                "<p><strong>Próximos pasos:</strong> "
                "Nuestro equipo de coordinación se pondrá en contacto para programar "
                "las intervenciones necesarias según lo indicado en este informe.</p>"
            )

        return '\n'.join(parrafos)

    def _generar_contadores_info(self):
        """Genera información de contadores si están disponibles"""
        if not hasattr(self, 'contometrok_id'):
            return ""
            
        if not any([self.contometrok_id, getattr(self, 'contometroc_id', None), getattr(self, 'contometros_id', None)]):
            return ""
        
        parrafos = ["<p><strong>Lecturas de contadores al finalizar el servicio:</strong></p>", "<ul>"]
        
        if self.contometrok_id:
            try:
                valor_k = "{:,}".format(int(str(self.contometrok_id).replace(',', '')))
                parrafos.append(f"<li>Impresiones monocromo: {valor_k}</li>")
            except:
                parrafos.append(f"<li>Impresiones monocromo: {self.contometrok_id}</li>")
        
        if hasattr(self, 'contometroc_id') and self.contometroc_id and hasattr(self, 'tipo_id') and self.tipo_id == 'color':
            try:
                valor_c = "{:,}".format(int(str(self.contometroc_id).replace(',', '')))
                parrafos.append(f"<li>Impresiones a color: {valor_c}</li>")
            except:
                parrafos.append(f"<li>Impresiones a color: {self.contometroc_id}</li>")
        
        if hasattr(self, 'contometros_id') and self.contometros_id:
            try:
                valor_s = "{:,}".format(int(str(self.contometros_id).replace(',', '')))
                parrafos.append(f"<li>Escaneos realizados: {valor_s}</li>")
            except:
                parrafos.append(f"<li>Escaneos realizados: {self.contometros_id}</li>")
        
        parrafos.append("</ul>")
        return '\n'.join(parrafos)

    # ===========================
    #  MÉTODO PRINCIPAL DE GENERACIÓN
    # ===========================

    def _build_informe_html_mejorado(self):
        """
        Genera un informe técnico resumido y natural (estilo humano)
        Solo conclusiones, sin listas ni checklist detallado
        
        Returns:
            tuple: (html_completo, calidad)
        """
        # 1. Análisis completo del checklist
        analisis = self._analizar_checklist_completo()
        
        # 2. Determinar calidad automática
        if analisis['score_gravedad'] >= 50:
            calidad = 'mala'
            estado_texto = 'CRÍTICO'
        elif analisis['score_gravedad'] >= 25:
            calidad = 'regular'
            estado_texto = 'REGULAR'
        elif analisis['score_gravedad'] >= 10:
            calidad = 'buena'
            estado_texto = 'BUENO'
        else:
            calidad = 'buena'
            estado_texto = 'ÓPTIMO'
        
        # 3. Construir el informe como texto natural
        frases = []
        
        # FRASE 1: Tipo de servicio completado
        tipos_servicio_texto = {
            'instalacion': 'Instalación completada',
            'retiro': 'Retiro de equipo completado',
            'mantenimiento_preventivo': 'Mantenimiento preventivo completado',
            'mantenimiento_correctivo': 'Mantenimiento correctivo realizado',
            'cambio_repuestos': 'Cambio de repuestos completado',
            'remoto': 'Asistencia remota realizada',
            'revision': 'Revisión técnica completada',
            'alquiler': 'Equipo preparado para alquiler',
        }
        
        tipo_servicio = self.tipo_servicio_id if hasattr(self, 'tipo_servicio_id') else 'revision'
        frases.append(tipos_servicio_texto.get(tipo_servicio, 'Servicio técnico completado'))
        
        # FRASE 2: Estado general
        frases.append(f"Estado general: {estado_texto}.")
        
        # FRASE 3: Resumen de funciones o problemas críticos
        if analisis['tiene_problemas_graves']:
            # Si hay problemas graves, mencionarlos
            problemas = []
            
            if analisis['funciones_criticas_fallando']:
                if any('impresión' in str(f).lower() for f in analisis['funciones_criticas_fallando']):
                    problemas.append('impresión inoperativa')
                if any('copia' in str(f).lower() or 'copiado' in str(f).lower() for f in analisis['funciones_criticas_fallando']):
                    problemas.append('función de copia inoperativa')
                if any('escaneo' in str(f).lower() or 'scanner' in str(f).lower() for f in analisis['funciones_criticas_fallando']):
                    problemas.append('escaneo inoperativo')
            
            if analisis['componentes_criticos_falla']:
                if any('fusora' in str(f).lower() for f in analisis['componentes_criticos_falla']):
                    problemas.append('fusora dañada')
                if any('adf' in str(f).lower() for f in analisis['componentes_criticos_falla']):
                    problemas.append('ADF inoperativo')
            
            if analisis['componentes_cambio_urgente']:
                if any('fusora' in str(f).lower() for f in analisis['componentes_cambio_urgente']):
                    if 'fusora dañada' not in problemas:
                        problemas.append('fusora requiere cambio urgente')
                if any('drum' in str(f).lower() or 'imagen' in str(f).lower() for f in analisis['componentes_cambio_urgente']):
                    problemas.append('unidad de imagen requiere reemplazo')
            
            if problemas:
                frases.append(' '.join(problemas).capitalize() + '.')
            else:
                frases.append('Equipo presenta fallas que requieren atención.')
        
        elif analisis['componentes_desgaste'] or analisis['funciones_secundarias_fallando']:
            # Si hay desgaste pero no es crítico
            desgastes = []
            
            if any('fusora' in str(f).lower() for f in analisis['componentes_desgaste']):
                desgastes.append('fusora con desgaste')
            if any('adf' in str(f).lower() for f in analisis['componentes_desgaste']):
                desgastes.append('ADF con desgaste')
            if any('drum' in str(f).lower() or 'imagen' in str(f).lower() for f in analisis['componentes_desgaste']):
                desgastes.append('unidades de imagen con desgaste')
            
            if desgastes:
                frases.append(f"Se detectó {', '.join(desgastes)}.")
            
            # Mencionar funciones operativas
            frases.append('Funciones principales operativas.')
        
        else:
            # Todo OK
            funciones_ok = []
            if hasattr(self, 'copia_id') and self.copia_id == 'si':
                funciones_ok.append('copia')
            if hasattr(self, 'impresion_id') and self.impresion_id == 'si':
                funciones_ok.append('impresión')
            if hasattr(self, 'scaner_smb_id') and self.scaner_smb_id == 'si':
                funciones_ok.append('escaneo')
            
            if funciones_ok:
                frases.append(f"Funciones principales operativas ({'/'.join(funciones_ok)}).")
            else:
                frases.append('Funciones principales operativas.')
        
        # FRASE 4: Estado de consumibles
        if analisis['toners_criticos']:
            if any('negro' in str(t).lower() or 'black' in str(t).lower() for t in analisis['toners_criticos']):
                if any('vacío' in str(t) or 'vacio' in str(t) for t in analisis['toners_criticos']):
                    frases.append('Tóner negro vacío.')
                else:
                    frases.append('Tóner negro sin botella instalada.')
            
            # Para equipos color
            if hasattr(self, 'tipo_id') and self.tipo_id == 'color':
                colores_vacios = []
                for t in analisis['toners_criticos']:
                    if 'cyan' in str(t).lower() or 'cian' in str(t).lower():
                        colores_vacios.append('cyan')
                    elif 'magenta' in str(t).lower():
                        colores_vacios.append('magenta')
                    elif 'yellow' in str(t).lower() or 'amarillo' in str(t).lower():
                        colores_vacios.append('amarillo')
                
                if colores_vacios:
                    frases.append(f"Tóner {'/'.join(colores_vacios)} vacío.")
        
        elif analisis['toners_medios']:
            niveles = []
            if any('negro' in str(t).lower() or 'black' in str(t).lower() for t in analisis['toners_medios']):
                niveles.append('negro al 50%')
            
            if niveles:
                frases.append(f"Tóner {', '.join(niveles)}.")
            else:
                frases.append('Consumibles en nivel medio.')
        
        else:
            frases.append('Consumibles OK.')
        
        # FRASE 5: Hallazgos y recomendaciones
        if analisis['tiene_problemas_graves']:
            if tipo_servicio == 'mantenimiento_correctivo':
                frases.append('Se requiere cotización para reparación.')
            else:
                frases.append('Equipo requiere intervención urgente.')
        
        elif analisis['componentes_desgaste']:
            frases.append('Programar reemplazo preventivo de componentes con desgaste.')
        
        elif not analisis['toners_criticos'] and not analisis['componentes_desgaste']:
            frases.append('Sin hallazgos críticos.')
        
        # Unir todas las frases
        informe_texto = ' '.join(frases)
        
        # Generar HTML simple
        html_completo = f"""
    <div data-autogen="1" style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <p>{informe_texto}</p>
    </div>
    """
        
        return html_completo, calidad

    # ===========================
    #  MÉTODOS PÚBLICOS
    # ===========================

    def _autofill_informe_si_corresponde(self):
        """
        Genera/actualiza el informe automáticamente si:
        - está vacío, o
        - el informe actual fue autogenerado
        Respeta la edición manual del técnico.
        """
        if not hasattr(self, 'informe_id'):
            return
            
        if self.informe_id and not self._is_autogen_informe():
            _logger.info(f"🔒 Informe del registro {self._name}[{self.id}] fue editado manualmente, no se regenerará")
            return
        
        _logger.info(f"🤖 Generando informe automático para {self._name}[{self.id}]")
        html, calidad = self._build_informe_html_mejorado()
        
        valores = {'informe_id': html}
        if hasattr(self, 'calidad_id'):
            valores['calidad_id'] = calidad
            
        self.update(valores)

    def action_regenerar_informe(self):
        """Botón manual para regenerar el informe técnico"""
        self.ensure_one()
        
        if not hasattr(self, 'informe_id'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Error'),
                    'message': _('Este modelo no tiene campo informe_id'),
                    'type': 'danger',
                }
            }
        
        # Generar informe sin validaciones previas
        _logger.info(f"🤖 Generando informe manual para {self._name}[{self.id}]")
        html, calidad = self._build_informe_html_mejorado()
        
        valores = {'informe_id': html}
        if hasattr(self, 'calidad_id'):
            valores['calidad_id'] = calidad
            
        self.write(valores)
        
        calidad_texto = dict(self._fields['calidad_id'].selection).get(calidad, calidad).upper() if hasattr(self, 'calidad_id') else 'N/A'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✅ Informe Generado'),
                'message': _(
                    f'El informe técnico ha sido generado exitosamente.\n'
                    f'Estado del equipo: {calidad_texto}'
                ),
                'type': 'success',
            }
        }

    def action_limpiar_informe(self):
        """Botón para limpiar el informe y permitir regeneración"""
        self.ensure_one()
        
        if not hasattr(self, 'informe_id'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Error'),
                    'message': _('Este modelo no tiene campo informe_id'),
                    'type': 'danger',
                }
            }
        
        valores = {'informe_id': False}
        if hasattr(self, 'calidad_id'):
            valores['calidad_id'] = False
            
        self.write(valores)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('🗑️ Informe Limpiado'),
                'message': _(
                    'El informe ha sido eliminado. '
                    'Complete el checklist y el informe se generará automáticamente.'
                ),
                'type': 'info',
            }
        }
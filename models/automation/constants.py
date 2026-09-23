# -*- coding: utf-8 -*-

SOURCE_SELECTION = [
    ("email", "Correo"),
    ("printtracker", "PrintTracker"),
    ("mobile_app", "Aplicación móvil"),
    ("api", "API externa"),
    ("manual", "Manual"),
    ("system", "Sistema"),
    ("other", "Otro"),
]

EVENT_TYPE_SELECTION = [
    ("unknown", "No identificado"),
    ("meter_reading", "Lectura de contador"),
    ("meter_anomaly", "Anomalía de contador"),
    ("toner_request", "Solicitud de tóner"),
    ("toner_low", "Tóner bajo"),
    ("toner_critical", "Tóner crítico"),
    ("toner_empty", "Tóner agotado"),
    ("toner_replaced", "Tóner reemplazado"),
    ("technical_issue", "Incidencia técnica"),
    ("paper_jam", "Atasco de papel"),
    ("device_error", "Error de equipo"),
    ("connectivity_issue", "Problema de conectividad"),
    ("maintenance", "Mantenimiento"),
    ("replacement_request", "Solicitud de reposición"),
    ("equipment_offline", "Equipo sin conexión"),
    ("customer_request", "Solicitud del cliente"),
    ("notification", "Notificación"),
    ("other", "Otro"),
]

EVENT_STATE_SELECTION = [
    ("new", "Nuevo"),
    ("classified", "Clasificado"),
    ("processing", "Procesando"),
    ("done", "Procesado"),
    ("review", "Revisión manual"),
    ("ignored", "Ignorado"),
    ("error", "Error"),
    ("cancelled", "Cancelado"),
]

ACTION_TYPE_SELECTION = [
    ("none", "Sin acción"),
    ("register_meter", "Registrar contador"),
    ("create_toner_request", "Crear solicitud de tóner"),
    ("create_ticket", "Crear ticket"),
    ("create_replacement", "Crear reposición"),
    ("update_record", "Actualizar registro"),
    ("notify", "Notificar"),
    ("review", "Enviar a revisión"),
    ("ignore", "Ignorar"),
    ("custom", "Acción configurable"),
]

PATTERN_STATE_SELECTION = [
    ("candidate", "Candidato"),
    ("testing", "En prueba"),
    ("validated", "Validado"),
    ("active", "Activo"),
    ("rejected", "Rechazado"),
    ("obsolete", "Obsoleto"),
]

VALUE_TYPE_SELECTION = [
    ("char", "Texto"),
    ("integer", "Entero"),
    ("float", "Decimal"),
    ("boolean", "Booleano"),
]

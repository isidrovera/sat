# -*- coding: utf-8 -*-
{
    'name': "Sistema de Administración de Taller",
    'version': '1.0',
    'summary': "Administra las operaciones de un taller de fotocopiadoras",
    'sequence': -100,
    'description': """Gestiona reparaciones, mantenimientos y más.""",
    'author': "Isidro vera polo",
    'website': "https://copiercompanysac.com",
    'category': 'Services',
    
    'depends': [
        'base',
        'mail',
        'contacts',
        'sale_management',
        'portal',
        'web',
        'stock',
        'crm',
        'purchase',
        'project',
        'hr_holidays',
        'calendar',
        'im_livechat',
        'survey',
        'hr_attendance',
        'hr',
        'website',
        'bus'
    ],
    
    'data': [
        'security/acceso.xml',
        'security/ir.model.access.csv',
        'data/ir_secuense.xml',
        'data/ir_secuense_ticket.xml',
        'data/ir.secuense_info.xml',
        'data/ir_secuense_ev.xml',
        'data/print.xml',
        'data/cron_data.xml',
        'data/cron_evaluador_diario.xml',
        'data/ir.secuence_incidencia.xml',
        'data/plantillas_correo.xml',
        'report/reparacion_enlace.xml',
        'report/report_reparaciones_ventas.xml',
        'report/ticket_enlace.xml',
        'report/ticket_reporte.xml',
        'report/informes.xml',
        'report/evaluacion.xml',
        'report/report_qr_codes_reparaciones.xml',
        'report/report_qr_enlace.xml',
        'report/qr_alquiler.xml',
        'views/sat_dashboard_menu.xml',
        'views/ventas.xml',
        'views/templates.xml',
        'views/modelos.xml',
        'views/repuestos_alquiler.xml',
        'views/marcas.xml',
        'views/informes.xml',
        'views/fallas.xml',
        'views/reporte_cotizacion.xml',
        'views/reparaciones.xml',
        'views/opciones_cliente.xml',
        'views/alquiler.xml',
        'views/opciones_product.xml',
        'views/sale_order_.xml',
        'views/linea_pedido.xml',
        'views/mail_maquinas.xml',
        'views/evaluacion.xml',
        'views/crear_ticket_portal.xml',
        'views/incidencias.xml',
        'views/soporte.alquiler.xml',
        'views/template_formulario_ticket.xml',
        'views/pagina_con_opciones.xml',
        'views/reportar_incidencia_form.xml',
        'views/pagina_confirmacion.xml',
        'views/solicitar_toner_form_template.xml',
        'views/pagina_confirmacion_toner.xml',
        'views/repuestos_alquiler_list.xml',
        'views/soporte_dashboard.xml',
        'views/transportistas.xml',
        'views/graficos.xml',
        'views/customer_records_page.xml',
        'views/importacionexcel.xml',
        'views/reparacion_autenticacion_wizard_view.xml',
        'views/fotos_reparaciones.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            
            
            # CSS Files
            'sat/static/src/css/dashboard.css',
            'sat/static/src/css/style.css',
            
            

            #SCSS
            
            #XML
            'sat/static/src/xml/dashboard.xml',
            'sat/static/src/xml/photo_gallery_template.xml',
            
            
            # JS Files
            'sat/static/src/js/dashboard.js',
            'sat/static/src/js/estilo_dashboard.js',
            'sat/static/src/js/gallery_widget.js',
            
            
            
            

            
            
            # External Libraries
            'https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js',
        ],
        
        'web.assets_frontend': [
            'sat/static/src/js/searchFilter.js',
        ],
        
        'web.assets_qweb': [
            
        ],
    },
    
    'demo': [
        'demo/demo_data.xml',
    ],
    
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
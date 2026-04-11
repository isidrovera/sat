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
    'external_dependencies': {
        'python': ['matplotlib', 'numpy'],
    },
    
    'data': [
        'security/acceso.xml',
        'security/ir.model.access.csv',
        'views/00_root_menu.xml',        
        'views/sat_prueba_maquina.xml',
        'data/ir_secuense_ticket.xml',
        'data/ir.secuense_info.xml',
        'data/ir_secuense_ev.xml',
        'data/print.xml',
        'data/cron_data.xml',        
        'data/cron_evaluador_diario.xml',
        'data/cron_tickets.xml',
        'data/ir.secuence_incidencia.xml',      
        'report/report_reparaciones_ventas.xml',
        'report/ticket_enlace.xml',
        'report/ticket_reporte.xml',
        'report/informes.xml',
        'report/evaluacion.xml',
        'report/evaluacion_enlace.xml',
        'report/report_qr_codes_reparaciones.xml',
        'report/reporte_estado_maquinas_report.xml',
        #'views/acciones_menus.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            # Chart.js y Font Awesome existentes
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
            
            # Bootstrap 5
            'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
            'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
            
            # Animate.css para animaciones
            'https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css',
            
            # AOS (Animate On Scroll)
            'https://unpkg.com/aos@2.3.1/dist/aos.css',
            'https://unpkg.com/aos@2.3.1/dist/aos.js',
            
            # Tailwind CSS
            'https://cdn.tailwindcss.com',
            
            # Lucide Icons
            'https://unpkg.com/lucide@latest/dist/umd/lucide.js',
            
            # Particles.js
            'https://cdn.jsdelivr.net/particles.js/2.0.0/particles.min.js',
            
            # Typed.js
            'https://cdn.jsdelivr.net/npm/typed.js@2.0.12',
            
            # CSS Files existentes
            'sat/static/src/css/dashboard.css',
            'sat/static/src/css/style.css',
            'sat/static/src/css/tree_dashboard.css',
            'sat/static/src/css/evaluation_form.css',
            'sat/static/src/css/parts_request_message.css',
            'sat/static/src/css/image-viewer.css',
            'sat/static/src/css/sat_table_styles.css',
            'sat/static/src/css/gallery.css',
            'sat/static/src/css/geo_map_widget.css',
            #'sat/static/src/css/contadores_dashboard.css',
            
            # SCSS existente
            '/sat/static/src/scss/list_dashboard.scss',
            'sat/static/src/scss/sat_dashboard.scss',
            'sat/static/src/scss/alquiler_dashboard.scss',
            'sat/static/src/scss/gallery_widget.scss',
      
            
            
            # XML existente
            'sat/static/src/xml/dashboard.xml',
            'sat/static/src/xml/photo_gallery_template.xml',
            'sat/static/src/xml/list_view.xml',
            'sat/static/src/xml/selection_subparts_template.xml',
            'sat/static/src/xml/sat_dashboard.xml',
            'sat/static/src/xml/alquiler_dashboard.xml',
            'sat/static/src/xml/geo_map_widget.xml',
            
            # JS Files existentes
            'sat/static/src/js/selection_subparts.js',
            'sat/static/src/js/gallery_widget.js',
            'sat/static/src/js/**/*',
          
            
            # External Libraries existentes
            'https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css',
            'https://cdnjs.cloudflare.com/ajax/libs/lottie-web/5.12.2/lottie.min.js',
            'https://cdn.jsdelivr.net/npm/remixicon@3.5.0/fonts/remixicon.css',
            'https://unicons.iconscout.com/release/v4.0.8/css/line.css',
            'https://cdn.lordicon.com/lordicon.js'
        ],
        
        'web.assets_frontend': [
            'sat/static/src/js/searchFilter.js',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
            
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
// ========== SAT MODERN ANIMATIONS JS ==========

odoo.define('sat.modern_animations', function (require) {
    'use strict';

    /**
     * Clase para manejar animaciones modernas
     */
    class SatAnimations {
        
        constructor() {
            this.isReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            this.init();
        }

        /**
         * Inicializar todas las animaciones
         */
        init() {
            if (this.isReducedMotion) {
                console.log('🔇 Reduced motion detected - animations disabled');
                return;
            }

            this.setupIntersectionObserver();
            this.initParticles();
            this.setupHoverEffects();
            this.initCounterAnimations();
            this.setupPageTransitions();
            this.initLoadingAnimations();
        }

        /**
         * Configurar Intersection Observer para animaciones on-scroll
         */
        setupIntersectionObserver() {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        this.animateElement(entry.target);
                    }
                });
            }, {
                threshold: 0.1,
                rootMargin: '0px 0px -50px 0px'
            });

            // Observar elementos con data-animate
            document.querySelectorAll('[data-animate]').forEach(el => {
                observer.observe(el);
            });

            // Observar filas de tabla
            document.querySelectorAll('.modern-sat-table tbody tr').forEach(el => {
                observer.observe(el);
            });
        }

        /**
         * Animar elemento cuando entra en vista
         */
        animateElement(element) {
            const animationType = element.dataset.animate || 'fadeInUp';
            const delay = element.dataset.delay || 0;

            setTimeout(() => {
                element.classList.add('animate__animated', `animate__${animationType}`);
                
                // Remover clases después de la animación
                element.addEventListener('animationend', () => {
                    element.classList.remove('animate__animated', `animate__${animationType}`);
                }, { once: true });
            }, delay);
        }

        /**
         * Inicializar efectos de partículas
         */
        initParticles() {
            if (typeof particlesJS === 'undefined') return;

            // Crear contenedor de partículas si no existe
            if (!document.querySelector('#particles-js')) {
                const particlesContainer = document.createElement('div');
                particlesContainer.id = 'particles-js';
                particlesContainer.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    z-index: -1;
                    opacity: 0.3;
                `;
                document.body.appendChild(particlesContainer);
            }

            particlesJS('particles-js', {
                particles: {
                    number: { value: 50, density: { enable: true, value_area: 800 } },
                    color: { value: "#667eea" },
                    shape: { type: "circle" },
                    opacity: { value: 0.3, random: true },
                    size: { value: 3, random: true },
                    line_linked: {
                        enable: true,
                        distance: 150,
                        color: "#667eea",
                        opacity: 0.2,
                        width: 1
                    },
                    move: {
                        enable: true,
                        speed: 2,
                        direction: "none",
                        random: true,
                        straight: false,
                        out_mode: "out",
                        bounce: false
                    }
                },
                interactivity: {
                    detect_on: "canvas",
                    events: {
                        onhover: { enable: true, mode: "repulse" },
                        onclick: { enable: true, mode: "push" },
                        resize: true
                    }
                },
                retina_detect: true
            });
        }

        /**
         * Configurar efectos hover modernos
         */
        setupHoverEffects() {
            // Efecto de ondas en botones
            document.addEventListener('click', (e) => {
                if (e.target.classList.contains('btn-modern')) {
                    this.createRippleEffect(e);
                }
            });

            // Efecto parallax en elementos
            document.addEventListener('mousemove', (e) => {
                this.handleParallaxEffect(e);
            });

            // Efecto de inclinación en tarjetas
            document.querySelectorAll('.card, .modern-sat-table tbody tr').forEach(card => {
                card.addEventListener('mouseenter', (e) => {
                    this.addTiltEffect(e.target);
                });
                
                card.addEventListener('mouseleave', (e) => {
                    this.removeTiltEffect(e.target);
                });
            });
        }

        /**
         * Crear efecto de ondas (ripple)
         */
        createRippleEffect(e) {
            const button = e.target.closest('.btn-modern');
            if (!button) return;

            const rect = button.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;

            const ripple = document.createElement('span');
            ripple.className = 'ripple-effect';
            ripple.style.cssText = `
                position: absolute;
                width: ${size}px;
                height: ${size}px;
                left: ${x}px;
                top: ${y}px;
                background: rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                transform: scale(0);
                animation: ripple-animation 0.6s linear;
                pointer-events: none;
                z-index: 1;
            `;

            // Agregar keyframes para la animación si no existen
            if (!document.querySelector('#ripple-keyframes')) {
                const style = document.createElement('style');
                style.id = 'ripple-keyframes';
                style.textContent = `
                    @keyframes ripple-animation {
                        to {
                            transform: scale(4);
                            opacity: 0;
                        }
                    }
                `;
                document.head.appendChild(style);
            }

            button.style.position = 'relative';
            button.style.overflow = 'hidden';
            button.appendChild(ripple);

            ripple.addEventListener('animationend', () => {
                ripple.remove();
            });
        }

        /**
         * Manejar efecto parallax
         */
        handleParallaxEffect(e) {
            const parallaxElements = document.querySelectorAll('[data-parallax]');
            
            parallaxElements.forEach(element => {
                const speed = element.dataset.parallax || 0.5;
                const x = (window.innerWidth - e.pageX * speed) / 100;
                const y = (window.innerHeight - e.pageY * speed) / 100;
                
                element.style.transform = `translateX(${x}px) translateY(${y}px)`;
            });
        }

        /**
         * Agregar efecto de inclinación
         */
        addTiltEffect(element) {
            element.style.transition = 'transform 0.3s ease';
            element.style.transform = 'perspective(1000px) rotateX(5deg) rotateY(5deg) scale(1.02)';
        }

        /**
         * Remover efecto de inclinación
         */
        removeTiltEffect(element) {
            element.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale(1)';
        }

        /**
         * Inicializar animaciones de contadores
         */
        initCounterAnimations() {
            const counters = document.querySelectorAll('[data-counter]');
            
            const counterObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        this.animateCounter(entry.target);
                        counterObserver.unobserve(entry.target);
                    }
                });
            });

            counters.forEach(counter => {
                counterObserver.observe(counter);
            });
        }

        /**
         * Animar contador
         */
        animateCounter(element) {
            const target = parseInt(element.dataset.counter) || parseInt(element.textContent) || 0;
            const duration = parseInt(element.dataset.duration) || 2000;
            const startTime = performance.now();

            const updateCounter = (currentTime) => {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                
                // Easing function (easeOutCubic)
                const easedProgress = 1 - Math.pow(1 - progress, 3);
                
                const current = Math.floor(target * easedProgress);
                element.textContent = current.toLocaleString();

                if (progress < 1) {
                    requestAnimationFrame(updateCounter);
                }
            };

            requestAnimationFrame(updateCounter);
        }

        /**
         * Configurar transiciones de página
         */
        setupPageTransitions() {
            // Animación de carga de página
            window.addEventListener('load', () => {
                document.body.classList.add('page-loaded');
            });

            // Animaciones para cambios de vista
            const observer = new MutationObserver((mutations) => {
                mutations.forEach(mutation => {
                    if (mutation.type === 'childList') {
                        mutation.addedNodes.forEach(node => {
                            if (node.nodeType === 1 && node.classList.contains('o_content')) {
                                this.animatePageTransition(node);
                            }
                        });
                    }
                });
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }

        /**
         * Animar transición de página
         */
        animatePageTransition(element) {
            element.style.opacity = '0';
            element.style.transform = 'translateY(20px)';
            
            requestAnimationFrame(() => {
                element.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                element.style.opacity = '1';
                element.style.transform = 'translateY(0)';
            });
        }

        /**
         * Inicializar animaciones de carga
         */
        initLoadingAnimations() {
            // Skeleton loading para tablas
            this.createSkeletonLoader();
            
            // Morphing loader para botones
            this.setupMorphingLoaders();
            
            // Progress bars animadas
            this.animateProgressBars();
        }

        /**
         * Crear skeleton loader
         */
        createSkeletonLoader() {
            const tables = document.querySelectorAll('.modern-sat-table');
            
            tables.forEach(table => {
                const tbody = table.querySelector('tbody');
                if (!tbody || tbody.children.length > 0) return;

                // Crear filas skeleton
                for (let i = 0; i < 5; i++) {
                    const skeletonRow = document.createElement('tr');
                    skeletonRow.className = 'skeleton-row';
                    
                    for (let j = 0; j < 8; j++) {
                        const skeletonCell = document.createElement('td');
                        skeletonCell.innerHTML = '<div class="skeleton-content" style="height: 20px; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; animation: skeleton-loading 1.5s infinite;"></div>';
                        skeletonRow.appendChild(skeletonCell);
                    }
                    
                    tbody.appendChild(skeletonRow);
                }

                // Remover skeleton después de 2 segundos
                setTimeout(() => {
                    const skeletonRows = tbody.querySelectorAll('.skeleton-row');
                    skeletonRows.forEach(row => {
                        row.style.opacity = '0';
                        setTimeout(() => row.remove(), 300);
                    });
                }, 2000);
            });
        }

        /**
         * Configurar morphing loaders
         */
        setupMorphingLoaders() {
            document.addEventListener('click', (e) => {
                if (e.target.classList.contains('btn-modern')) {
                    const button = e.target;
                    const originalText = button.innerHTML;
                    
                    button.innerHTML = '<div class="morph-loader"></div>';
                    button.disabled = true;
                    
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            });
        }

        /**
         * Animar barras de progreso
         */
        animateProgressBars() {
            const progressBars = document.querySelectorAll('.progress-bar[data-width]');
            
            const progressObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const bar = entry.target;
                        const targetWidth = bar.dataset.width;
                        
                        bar.style.width = '0%';
                        bar.style.transition = 'width 1.5s ease-in-out';
                        
                        setTimeout(() => {
                            bar.style.width = targetWidth + '%';
                        }, 100);
                        
                        progressObserver.unobserve(bar);
                    }
                });
            });

            progressBars.forEach(bar => {
                progressObserver.observe(bar);
            });
        }

        /**
         * Crear animación de escritura (typing effect)
         */
        createTypingEffect(element, text, speed = 50) {
            element.textContent = '';
            let i = 0;
            
            const typeWriter = () => {
                if (i < text.length) {
                    element.textContent += text.charAt(i);
                    i++;
                    setTimeout(typeWriter, speed);
                }
            };
            
            typeWriter();
        }

        /**
         * Crear efecto de lluvia de confeti
         */
        createConfetti() {
            const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe'];
            const confettiContainer = document.createElement('div');
            confettiContainer.className = 'confetti-container';
            confettiContainer.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 9999;
            `;
            
            document.body.appendChild(confettiContainer);

            for (let i = 0; i < 100; i++) {
                const confetti = document.createElement('div');
                confetti.className = 'confetti-piece';
                confetti.style.cssText = `
                    position: absolute;
                    width: 10px;
                    height: 10px;
                    background: ${colors[Math.floor(Math.random() * colors.length)]};
                    left: ${Math.random() * 100}%;
                    animation: confetti-fall ${Math.random() * 3 + 2}s linear forwards;
                    opacity: ${Math.random()};
                    transform: rotate(${Math.random() * 360}deg);
                `;
                
                confettiContainer.appendChild(confetti);
            }

            // Agregar keyframes para confetti
            if (!document.querySelector('#confetti-keyframes')) {
                const style = document.createElement('style');
                style.id = 'confetti-keyframes';
                style.textContent = `
                    @keyframes confetti-fall {
                        to {
                            transform: translateY(100vh) rotate(360deg);
                        }
                    }
                `;
                document.head.appendChild(style);
            }

            // Remover confetti después de 5 segundos
            setTimeout(() => {
                confettiContainer.remove();
            }, 5000);
        }

        /**
         * Crear efecto de texto brillante
         */
        createShimmyText(element) {
            element.style.background = 'linear-gradient(90deg, #667eea, #764ba2, #667eea)';
            element.style.backgroundSize = '200% 100%';
            element.style.webkitBackgroundClip = 'text';
            element.style.webkitTextFillColor = 'transparent';
            element.style.animation = 'shimmy-text 2s ease-in-out infinite';

            // Agregar keyframes para shimmy
            if (!document.querySelector('#shimmy-keyframes')) {
                const style = document.createElement('style');
                style.id = 'shimmy-keyframes';
                style.textContent = `
                    @keyframes shimmy-text {
                        0% { background-position: 0% 50%; }
                        50% { background-position: 100% 50%; }
                        100% { background-position: 0% 50%; }
                    }
                `;
                document.head.appendChild(style);
            }
        }
    }

    // Funciones utilitarias globales
    window.satAnimations = {
        /**
         * Animar elemento con bounce
         */
        bounce: function(element) {
            element.classList.add('animate__animated', 'animate__bounce');
            element.addEventListener('animationend', () => {
                element.classList.remove('animate__animated', 'animate__bounce');
            }, { once: true });
        },

        /**
         * Animar elemento con shake
         */
        shake: function(element) {
            element.classList.add('animate__animated', 'animate__shakeX');
            element.addEventListener('animationend', () => {
                element.classList.remove('animate__animated', 'animate__shakeX');
            }, { once: true });
        },

        /**
         * Animar elemento con pulse
         */
        pulse: function(element) {
            element.classList.add('animate__animated', 'animate__pulse');
            element.addEventListener('animationend', () => {
                element.classList.remove('animate__animated', 'animate__pulse');
            }, { once: true });
        },

        /**
         * Crear loading spinner personalizado
         */
        showLoader: function(container) {
            const loader = document.createElement('div');
            loader.className = 'sat-custom-loader';
            loader.innerHTML = `
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Cargando...</span>
                </div>
            `;
            container.appendChild(loader);
            return loader;
        },

        /**
         * Remover loader
         */
        hideLoader: function(loader) {
            if (loader && loader.parentElement) {
                loader.classList.add('animate__animated', 'animate__fadeOut');
                loader.addEventListener('animationend', () => {
                    loader.remove();
                });
            }
        }
    };

    // Inicializar cuando el DOM esté listo
    document.addEventListener('DOMContentLoaded', () => {
        new SatAnimations();
        console.log('✨ SAT Modern Animations initialized');
    });

    return SatAnimations;
});
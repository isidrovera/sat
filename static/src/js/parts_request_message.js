/** @odoo-module **/

export function startCountdown() {
    let timeLeft = 10;
    const countdownEl = document.getElementById('countdown');
    
    const timer = setInterval(() => {
        timeLeft--;
        if (countdownEl) {
            countdownEl.textContent = `Esta ventana se cerrará en ${timeLeft} segundos`;
        }
        
        if (timeLeft <= 0) {
            clearInterval(timer);
            window.close();
        }
    }, 1000);
}
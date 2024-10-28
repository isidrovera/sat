function toggleChart(button) {
    const container = button.closest('.chart-wrapper').querySelector('.chart-container');
    const icon = button.querySelector('i');

    container.classList.toggle('expanded');

    if (container.classList.contains('expanded')) {
        icon.classList.remove('fa-expand');
        icon.classList.add('fa-compress');
    } else {
        icon.classList.remove('fa-compress');
        icon.classList.add('fa-expand');
    }

    // Actualizar el gráfico después de la transición
    setTimeout(() => {
        const chartId = container.querySelector('canvas').id;
        const chart = Chart.getChart(chartId);
        if (chart) {
            chart.resize();
        }
    }, 300);
}

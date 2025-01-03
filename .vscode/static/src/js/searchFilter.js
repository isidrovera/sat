function filterTable() {
    var input, filter, table, tr, tdModel, tdSerie, tdArea, txtValueModel, txtValueSerie, txtValueArea;
    
    // Obtener el valor de búsqueda
    input = document.getElementById("searchInput");
    filter = input.value.toLowerCase();

    console.log("Valor ingresado en el campo de búsqueda:", filter);

    // Manejamos la vista de tabla (pantallas grandes)
    table = document.getElementById("recordsTable");
    if (table) {
        tr = table.getElementsByTagName("tr");

        // Empezamos desde i = 1 para ignorar la cabecera
        for (var i = 1; i < tr.length; i++) {
            tdModel = tr[i].getElementsByTagName("td")[0]; // Modelo
            tdSerie = tr[i].getElementsByTagName("td")[1]; // Serie
            tdArea = tr[i].getElementsByTagName("td")[2];  // Área

            if (tdModel || tdSerie || tdArea) {
                txtValueModel = tdModel ? (tdModel.textContent || tdModel.innerText).toLowerCase() : '';
                txtValueSerie = tdSerie ? (tdSerie.textContent || tdSerie.innerText).toLowerCase() : '';
                txtValueArea = tdArea ? (tdArea.textContent || tdArea.innerText).toLowerCase() : '';

                if (txtValueModel.indexOf(filter) > -1 || txtValueSerie.indexOf(filter) > -1 || txtValueArea.indexOf(filter) > -1) {
                    tr[i].style.display = "";  // Mostrar la fila
                } else {
                    tr[i].style.display = "none";  // Ocultar la fila
                }
            }
        }
    }

    // Manejamos la vista de tarjetas "Kanban" (pantallas pequeñas)
    var kanbanCards = document.getElementsByClassName("card");
    if (kanbanCards.length > 0) {
        for (var j = 0; j < kanbanCards.length; j++) {
            var cardModel = kanbanCards[j].getElementsByClassName("card-title")[0]; // Modelo
            var cardSerie = kanbanCards[j].getElementsByClassName("card-text")[0]; // Serie
            var cardArea = kanbanCards[j].getElementsByClassName("card-text")[1]; // Área (si aplica)

            var cardValueModel = cardModel ? (cardModel.textContent || cardModel.innerText).toLowerCase() : '';
            var cardValueSerie = cardSerie ? (cardSerie.textContent || cardSerie.innerText).toLowerCase() : '';
            var cardValueArea = cardArea ? (cardArea.textContent || cardArea.innerText).toLowerCase() : '';

            if (cardValueModel.indexOf(filter) > -1 || cardValueSerie.indexOf(filter) > -1 || cardValueArea.indexOf(filter) > -1) {
                kanbanCards[j].style.display = "";  // Mostrar la tarjeta
            } else {
                kanbanCards[j].style.display = "none";  // Ocultar la tarjeta
            }
        }
    }
}

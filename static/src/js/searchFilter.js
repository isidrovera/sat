function filterTable() {
    var input, filter, table, tr, tdModel, tdSerie, tdArea, txtValueModel, txtValueSerie, txtValueArea;

    input = document.getElementById("searchInput");
    filter = input.value.toLowerCase();

    console.log("Valor ingresado en el campo de búsqueda:", filter);

    table = document.getElementById("recordsTable");
    tr = table.getElementsByTagName("tr");

    for (var i = 0; i < tr.length; i++) {
        tdModel = tr[i].getElementsByTagName("td")[0]; // Modelo
        tdSerie = tr[i].getElementsByTagName("td")[1]; // Serie
        tdArea = tr[i].getElementsByTagName("td")[2];  // Área

        // Verificar que las celdas existan
        if (tdModel || tdSerie || tdArea) {
            txtValueModel = tdModel ? (tdModel.textContent || tdModel.innerText).toLowerCase() : '';
            txtValueSerie = tdSerie ? (tdSerie.textContent || tdSerie.innerText).toLowerCase() : '';
            txtValueArea = tdArea ? (tdArea.textContent || tdArea.innerText).toLowerCase() : '';

            // Verifica si el texto ingresado coincide con cualquiera de los tres valores
            if (txtValueModel.indexOf(filter) > -1 || txtValueSerie.indexOf(filter) > -1 || txtValueArea.indexOf(filter) > -1) {
                console.log("Coincidencia encontrada en la fila", i);
                tr[i].style.display = "";  // Mostrar la fila
            } else {
                console.log("No coincide, ocultando la fila", i);
                tr[i].style.display = "none";  // Ocultar la fila
            }
        }
    }
}

// static/src/js/searchFilter.js
function filterTable() {
    var input, filter, table, tr, tdModel, tdSerie, tdArea, txtValueModel, txtValueSerie, txtValueArea;
    
    // Obtener el valor del campo de búsqueda
    input = document.getElementById("searchInput");
    filter = input.value.toLowerCase();
    
    console.log("Valor ingresado en el campo de búsqueda:", filter);  // Log del valor ingresado
    
    // Obtener la tabla y las filas
    table = document.getElementById("recordsTable");
    tr = table.getElementsByTagName("tr");

    // Bucle para recorrer todas las filas
    for (var i = 0; i < tr.length; i++) {
        tdModel = tr[i].getElementsByTagName("td")[0]; // Modelo
        tdSerie = tr[i].getElementsByTagName("td")[1]; // Serie
        tdArea = tr[i].getElementsByTagName("td")[2];  // Área
        
        // Verificar que los campos existan
        if (tdModel || tdSerie || tdArea) {
            txtValueModel = tdModel.textContent || tdModel.innerText;
            txtValueSerie = tdSerie.textContent || tdSerie.innerText;
            txtValueArea = tdArea.textContent || tdArea.innerText;

            console.log("Fila " + i + ":");
            console.log("Modelo:", txtValueModel);
            console.log("Serie:", txtValueSerie);
            console.log("Área:", txtValueArea);
            
            // Comparar los valores con el filtro
            if (txtValueModel.toLowerCase().indexOf(filter) > -1 || 
                txtValueSerie.toLowerCase().indexOf(filter) > -1 || 
                txtValueArea.toLowerCase().indexOf(filter) > -1) {
                console.log("Coincidencia encontrada en la fila", i);
                tr[i].style.display = "";  // Mostrar la fila
            } else {
                console.log("No coincide, ocultando la fila", i);
                tr[i].style.display = "none";  // Ocultar la fila
            }
        }
    }
}

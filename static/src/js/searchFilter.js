// static/src/js/searchFilter.js
function filterTable() {
    var input, filter, table, tr, td, i, txtValue;
    input = document.getElementById("searchInput");
    filter = input.value.toLowerCase();
    table = document.getElementById("recordsTable");
    tr = table.getElementsByTagName("tr");

    // Loop through all table rows, and hide those who don't match the search query
    for (i = 0; i < tr.length; i++) {
        tdModel = tr[i].getElementsByTagName("td")[0]; // Modelo
        tdSerie = tr[i].getElementsByTagName("td")[1]; // Serie
        tdArea = tr[i].getElementsByTagName("td")[2];  // Área
        if (tdModel || tdSerie || tdArea) {
            txtValueModel = tdModel.textContent || tdModel.innerText;
            txtValueSerie = tdSerie.textContent || tdSerie.innerText;
            txtValueArea = tdArea.textContent || tdArea.innerText;
            if (txtValueModel.toLowerCase().indexOf(filter) > -1 || 
                txtValueSerie.toLowerCase().indexOf(filter) > -1 || 
                txtValueArea.toLowerCase().indexOf(filter) > -1) {
                tr[i].style.display = "";
            } else {
                tr[i].style.display = "none";
            }
        }
    }
}

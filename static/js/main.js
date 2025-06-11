function fetchData() {
    $.getJSON('/api/data', function(data) {
        $('#data').text(JSON.stringify(data, null, 2));
    });
}

setInterval(fetchData, 5000);
fetchData();

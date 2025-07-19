$(function() {
    function update() {
        $.getJSON('/api/taxameter/status', function(data) {
            if (!data.active) {
                $('#start-btn').prop('disabled', false);
                $('#stop-btn').prop('disabled', true);
            } else {
                $('#start-btn').prop('disabled', true);
                $('#stop-btn').prop('disabled', false);
                $('#dist').text(data.distance.toFixed(2));
                $('#price').text(data.price.toFixed(2));
                $('#time').text(Math.round(data.duration));
            }
        });
    }

    $('#start-btn').click(function() {
        $.post('/api/taxameter/start', update);
    });

    $('#stop-btn').click(function() {
        $.post('/api/taxameter/stop', update);
    });

    update();
    setInterval(update, 5000);
});

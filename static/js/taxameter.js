$(function() {
    function update() {
        $.getJSON('/api/taxameter/status', function(data) {
            if (data.price !== undefined) {
                $('#price').text(Number(data.price).toFixed(2));
            }
            if (data.distance !== undefined) {
                $('#dist').text(Number(data.distance).toFixed(2));
            }
            if (data.duration !== undefined) {
                $('#time').text(Math.round(data.duration));
            }
            if (!data.active) {
                $('#start-btn').prop('disabled', false);
                $('#stop-btn').prop('disabled', true);
                $('#reset-btn').prop('disabled', !('price' in data));
            } else {
                $('#start-btn').prop('disabled', true);
                $('#stop-btn').prop('disabled', false);
                $('#reset-btn').prop('disabled', true);
            }
        });
    }

    $('#start-btn').click(function() {
        $.post('/api/taxameter/start', update, 'json');
    });

    $('#stop-btn').click(function() {
        $.post('/api/taxameter/stop', function(data) {
            if (data.price !== undefined) {
                $('#price').text(Number(data.price).toFixed(2));
                $('#dist').text(Number(data.distance).toFixed(2));
                $('#time').text(Math.round(data.duration));
            }
            update();
        }, 'json');
    });

    $('#reset-btn').click(function() {
        $.post('/api/taxameter/reset', update);
        $('#price').text('0.00');
        $('#dist').text('0.00');
        $('#time').text('0');
    });

    update();
    setInterval(update, 5000);
});

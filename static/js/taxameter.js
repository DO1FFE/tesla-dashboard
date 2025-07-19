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
            if (data.waiting) {
                $('#wait-icon').show();
            } else {
                $('#wait-icon').hide();
            }

            if (!data.active && !data.paused && data.ride_id !== undefined) {
                var qr = '/receipts/' + data.ride_id + '.png';
                showReceipt(data.breakdown, TAXI_COMPANY, data.distance, qr);
            }

            if (data.active) {
                $('#start-btn').prop('disabled', true).removeClass('active-btn');
                $('#pause-btn').prop('disabled', false);
                $('#stop-btn').prop('disabled', false);
                $('#reset-btn').prop('disabled', true);
                $('#start-btn').addClass('active-btn');
                $('#pause-btn').removeClass('active-btn');
                $('#stop-btn').removeClass('active-btn');
            } else if (data.paused) {
                $('#start-btn').prop('disabled', false);
                $('#pause-btn').prop('disabled', true).removeClass('active-btn');
                $('#stop-btn').prop('disabled', false);
                $('#reset-btn').prop('disabled', true);
                $('#pause-btn').addClass('active-btn');
                $('#start-btn').removeClass('active-btn');
                $('#stop-btn').removeClass('active-btn');
            } else {
                $('#start-btn').prop('disabled', false);
                $('#pause-btn').prop('disabled', true).removeClass('active-btn');
                $('#stop-btn').prop('disabled', true).removeClass('active-btn');
                $('#reset-btn').prop('disabled', !('price' in data));
                $('#start-btn').removeClass('active-btn');
                $('#pause-btn').removeClass('active-btn');
                $('#stop-btn').removeClass('active-btn');
            }
        });
    }

    function showReceipt(breakdown, company, distance, qr_path) {
        if (!breakdown) {
            return;
        }
        function fmt(value) {
            return value.toFixed(2).padStart(7);
        }
        var lines = [];
        lines.push('Grundpreis:' + fmt(breakdown.base) + ' €');
        if (breakdown.km_1_2 > 0) {
            lines.push(breakdown.km_1_2.toFixed(2) + ' km x ' +
                breakdown.rate_1_2.toFixed(2) + ' € =' + fmt(breakdown.cost_1_2) + ' €');
        }
        if (breakdown.km_3_4 > 0) {
            lines.push(breakdown.km_3_4.toFixed(2) + ' km x ' +
                breakdown.rate_3_4.toFixed(2) + ' € =' + fmt(breakdown.cost_3_4) + ' €');
        }
        if (breakdown.km_5_plus > 0) {
            lines.push(breakdown.km_5_plus.toFixed(2) + ' km x ' +
                breakdown.rate_5_plus.toFixed(2) + ' € =' + fmt(breakdown.cost_5_plus) + ' €');
        }
        if (breakdown.wait_cost > 0) {
            lines.push('Standzeit ' + Math.round(breakdown.wait_time) + 's =' + fmt(breakdown.wait_cost) + ' €');
        }
        lines.push('--------------------');
        lines.push('Gesamt:' + fmt(breakdown.total) + ' €');
        lines.push('Fahrstrecke: ' + distance.toFixed(2) + ' km');
        $('#receipt-text').text(lines.join('\n'));
        $('#receipt-company').empty();
        if (company) {
            $('#receipt-company').append('<div class="company-name">' + company + '</div>');
            if (typeof TAXI_SLOGAN !== 'undefined' && TAXI_SLOGAN) {
                $('#receipt-company').append('<div class="company-slogan">' + TAXI_SLOGAN + '</div>');
            }
        }
        $('#receipt-qr').empty();
        if (qr_path) {
            $('#receipt-qr').append('<img src="' + qr_path + '" alt="QR" style="width:50%">');
        }
        $('#taximeter-receipt').show();
    }

    $('#start-btn').click(function() {
        $('#taximeter-receipt').hide();
        $('.active-btn').removeClass('active-btn');
        $(this).addClass('active-btn');
        $.post('/api/taxameter/start', update, 'json');
    });

    $('#pause-btn').click(function() {
        $('.active-btn').removeClass('active-btn');
        $(this).addClass('active-btn');
        $.post('/api/taxameter/pause', update, 'json');
    });

    $('#stop-btn').click(function() {
        $('.active-btn').removeClass('active-btn');
        $(this).addClass('active-btn');
        $.post('/api/taxameter/stop', function(data) {
            if (data.price !== undefined) {
                $('#price').text(Number(data.price).toFixed(2));
                $('#dist').text(Number(data.distance).toFixed(2));
                $('#time').text(Math.round(data.duration));
                showReceipt(data.breakdown, TAXI_COMPANY, data.distance, data.qr_code);
            }
            update();
        }, 'json');
    });

    $('#reset-btn').click(function() {
        $('.active-btn').removeClass('active-btn');
        $.post('/api/taxameter/reset', update);
        $('#price').text('0.00');
        $('#dist').text('0.00');
        $('#time').text('0');
        $('#taximeter-receipt').hide();
    });

    update();
    setInterval(update, 2000);
});

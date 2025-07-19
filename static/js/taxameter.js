$(function() {
    function update() {
        $.getJSON('/api/taxameter/status?vehicle_id=' + encodeURIComponent(VEHICLE_ID), function(data) {
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
                $('#start-btn').prop('disabled', true);
                $('#pause-btn').prop('disabled', false);
                $('#stop-btn').prop('disabled', false);
                $('#reset-btn').prop('disabled', true);
                $('#taximeter-buttons button').removeClass('active-btn');
                $('#start-btn').addClass('active-btn');
            } else if (data.paused) {
                $('#start-btn').prop('disabled', false);
                $('#pause-btn').prop('disabled', true);
                $('#stop-btn').prop('disabled', false);
                $('#reset-btn').prop('disabled', true);
                $('#taximeter-buttons button').removeClass('active-btn');
                $('#pause-btn').addClass('active-btn');
            } else {
                $('#start-btn').prop('disabled', false);
                $('#pause-btn').prop('disabled', true);
                var hasResult = ('price' in data);
                $('#stop-btn').prop('disabled', !hasResult);
                $('#reset-btn').prop('disabled', !hasResult);
                $('#taximeter-buttons button').removeClass('active-btn');
                if (hasResult) {
                    $('#stop-btn').addClass('active-btn');
                }
            }
        });
    }

    function showReceipt(breakdown, company, distance, qr_path) {
        if (!breakdown) {
            return;
        }
        function fmt(value) {
            return value.toFixed(2);
        }
        var html = '';
        html += '<tr><td>Grundpreis:</td><td class="num">' + fmt(breakdown.base) + ' €</td></tr>';
        if (breakdown.km_1_2 > 0) {
            html += '<tr><td>' + breakdown.km_1_2.toFixed(2) + ' km x ' +
                breakdown.rate_1_2.toFixed(2) + ' €</td><td class="num">' + fmt(breakdown.cost_1_2) + ' €</td></tr>';
        }
        if (breakdown.km_3_4 > 0) {
            html += '<tr><td>' + breakdown.km_3_4.toFixed(2) + ' km x ' +
                breakdown.rate_3_4.toFixed(2) + ' €</td><td class="num">' + fmt(breakdown.cost_3_4) + ' €</td></tr>';
        }
        if (breakdown.km_5_plus > 0) {
            html += '<tr><td>' + breakdown.km_5_plus.toFixed(2) + ' km x ' +
                breakdown.rate_5_plus.toFixed(2) + ' €</td><td class="num">' + fmt(breakdown.cost_5_plus) + ' €</td></tr>';
        }
        if (breakdown.wait_cost > 0) {
            html += '<tr><td>Standzeit ' + Math.round(breakdown.wait_time) + 's</td><td class="num">' + fmt(breakdown.wait_cost) + ' €</td></tr>';
        }
        html += '<tr><td colspan="2"><hr></td></tr>';
        html += '<tr><td>Gesamt:</td><td class="num">' + fmt(breakdown.total) + ' €</td></tr>';
        html += '<tr><td colspan="2" style="text-align:center">Fahrstrecke: ' + distance.toFixed(2) + ' km</td></tr>';
        $('#receipt-table').html(html);
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
        $.post('/api/taxameter/start', {vehicle_id: VEHICLE_ID}, update, 'json');
    });

    $('#pause-btn').click(function() {
        $('.active-btn').removeClass('active-btn');
        $(this).addClass('active-btn');
        $.post('/api/taxameter/pause', {vehicle_id: VEHICLE_ID}, update, 'json');
    });

    $('#stop-btn').click(function() {
        $('.active-btn').removeClass('active-btn');
        $(this).addClass('active-btn');
        $.post('/api/taxameter/stop', {vehicle_id: VEHICLE_ID}, function(data) {
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
        $.post('/api/taxameter/reset', {vehicle_id: VEHICLE_ID}, update);
        $('#price').text('0.00');
        $('#dist').text('0.00');
        $('#time').text('0');
        $('#taximeter-receipt').hide();
    });

    $('#trip-receipt-btn').click(function() {
        var file = $('#trip-select').val();
        if (file) {
            window.open('/taxameter/trip_receipt?file=' + encodeURIComponent(file), '_blank');
        }
    });

    update();
    setInterval(update, 2000);
});

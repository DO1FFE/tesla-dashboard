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

    function showReceipt(breakdown, company, distance, qr_path) {
        if (!breakdown) {
            return;
        }
        var lines = [];
        lines.push('Grundpreis: ' + breakdown.base.toFixed(2) + ' €');
        if (breakdown.km_1_2 > 0) {
            lines.push(breakdown.km_1_2.toFixed(2) + ' km x ' +
                breakdown.rate_1_2.toFixed(2) + ' € = ' +
                breakdown.cost_1_2.toFixed(2) + ' €');
        }
        if (breakdown.km_3_4 > 0) {
            lines.push(breakdown.km_3_4.toFixed(2) + ' km x ' +
                breakdown.rate_3_4.toFixed(2) + ' € = ' +
                breakdown.cost_3_4.toFixed(2) + ' €');
        }
        if (breakdown.km_5_plus > 0) {
            lines.push(breakdown.km_5_plus.toFixed(2) + ' km x ' +
                breakdown.rate_5_plus.toFixed(2) + ' € = ' +
                breakdown.cost_5_plus.toFixed(2) + ' €');
        }
        lines.push('--------------------');
        lines.push('Fahrstrecke: ' + distance.toFixed(2) + ' km');
        lines.push('Gesamt: ' + breakdown.total.toFixed(2) + ' €');
        $('#receipt-text').text(lines.join('\n'));
        $('#receipt-company').empty();
        if (company) {
            $('#receipt-company').append('<div class="company-name">' + company + '</div>');
            $('#receipt-company').append('<div class="company-slogan">Wir lassen Sie nicht im Regen stehen.</div>');
        }
        $('#receipt-qr').empty();
        if (qr_path) {
            $('#receipt-qr').append('<img src="' + qr_path + '" alt="QR">');
        }
        $('#taximeter-receipt').show();
    }

    $('#start-btn').click(function() {
        $('#taximeter-receipt').hide();
        $.post('/api/taxameter/start', update, 'json');
    });

    $('#stop-btn').click(function() {
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
        $.post('/api/taxameter/reset', update);
        $('#price').text('0.00');
        $('#dist').text('0.00');
        $('#time').text('0');
        $('#taximeter-receipt').hide();
    });

    update();
    setInterval(update, 2000);
});

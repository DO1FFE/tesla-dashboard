function formatiereClientDauer(sekunden) {
    const gesamt = Math.max(0, Math.floor(Number(sekunden) || 0));
    const tage = Math.floor(gesamt / 86400);
    const rest = gesamt % 86400;
    const stunden = Math.floor(rest / 3600);
    const minuten = Math.floor((rest % 3600) / 60);
    const sek = rest % 60;
    const pad = function(wert) {
        return String(wert).padStart(2, '0');
    };
    return pad(tage) + ' Tage, ' + pad(stunden) + ':' + pad(minuten) + ':' + pad(sek);
}

function aktualisiereClientDauer() {
    const jetzt = Date.now();
    document.querySelectorAll('.client-duration[data-first-seen]').forEach(function(zelle) {
        const start = Number(zelle.dataset.firstSeen);
        if (!Number.isFinite(start) || start <= 0) {
            return;
        }
        zelle.textContent = formatiereClientDauer((jetzt - start) / 1000);
    });
}

async function fetchClients() {
    try {
        const response = await fetch('/api/clients/details');
        if (!response.ok) {
            return;
        }
        const data = await response.json();
        const tbody = document.getElementById('clients-body');
        if (!tbody || !data.clients) {
            return;
        }
        tbody.innerHTML = '';
        data.clients.forEach(function(c) {
            const tr = document.createElement('tr');
            ['ip', 'hostname', 'location', 'provider', 'browser', 'os', 'user_agent', 'pages', 'duration'].forEach(function(key) {
                const td = document.createElement('td');
                let value = c[key];
                if (key === 'pages' && Array.isArray(value)) {
                    value = value.join(', ');
                }
                if (key === 'duration') {
                    td.className = 'client-duration';
                    if (c.first_seen_ms) {
                        td.dataset.firstSeen = String(c.first_seen_ms);
                        value = formatiereClientDauer((Date.now() - c.first_seen_ms) / 1000);
                    }
                }
                td.textContent = value || '';
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        aktualisiereClientDauer();
    } catch (err) {
        console.error('Failed to fetch clients', err);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    fetchClients();
    aktualisiereClientDauer();
    setInterval(fetchClients, 5000);
    setInterval(aktualisiereClientDauer, 1000);
});

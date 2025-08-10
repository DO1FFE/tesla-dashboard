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
            ['ip', 'hostname', 'location', 'browser', 'os', 'user_agent', 'duration'].forEach(function(key) {
                const td = document.createElement('td');
                td.textContent = c[key] || '';
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Failed to fetch clients', err);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    fetchClients();
    setInterval(fetchClients, 5000);
});

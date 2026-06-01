// Global graph configurations
let maxDataPoints = 10;
let cpuChart;

// Initialize Chart.js engine
const ctx = document.getElementById('cpuChart').getContext('2d');
cpuChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: Array(maxDataPoints).fill(''),
        datasets: [{
            label: 'CPU %',
            data: Array(maxDataPoints).fill(0),
            borderColor: '#00adb5',
            backgroundColor: 'rgba(0, 173, 181, 0.1)',
            tension: 0.3,
            fill: true
        }]
    },
    options: {
        scales: { y: { min: 0, max: 100 } },
        responsive: true,
        maintainAspectRatio: false,
        animation: false
    }
});

// Fetch static hardware properties once
async function fetchSystemSpecs() {
    try {
        const response = await fetch('/api/specs');
        const specs = await response.json();
        document.getElementById('cpu-model').innerText = specs.cpu_model;
        document.getElementById('gpu-model').innerText = specs.gpu_model;
        document.getElementById('ram-spec').innerText = 'Total Installed: ' + specs.total_ram;
        document.getElementById('disk-spec').innerText = 'Total Capacity: ' + specs.total_disk;
    } catch (error) {
        console.error("Error fetching specifications:", error);
    }
}

// Stream and plot live usage updates continuously from Flask API
async function updateDashboard() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();

        // Standard string concatenation to destroy rendering bugs
        document.getElementById('cpu-text').innerText = data.cpu + '%';
        document.getElementById('gpu-text').innerText = data.gpu + '%';
        document.getElementById('ram-text').innerText = data.ram + '%';
        document.getElementById('disk-text').innerText = data.disk + '%';

        toggleAlert('cpu-card', data.cpu);
        toggleAlert('gpu-card', data.gpu);
        toggleAlert('ram-card', data.ram);

        let htmlBuilder = '';
        data.processes.forEach(p => {
            htmlBuilder += '<li><strong>' + p.name + '</strong> (PID: ' + p.pid + ') — ' + p.memory + '% RAM</li>';
        });
        document.getElementById('process-list').innerHTML = htmlBuilder;

        cpuChart.data.datasets[0].data.push(data.cpu);
        cpuChart.data.datasets[0].data.shift();
        cpuChart.update();

    } catch (error) {
        console.error("Error retrieving stats:", error);
    }
}

function toggleAlert(cardId, val) {
    const el = document.getElementById(cardId);
    if (val > 85) {
        el.classList.add('alert');
    } else {
        el.classList.remove('alert');
    }
}

document.getElementById('ping-btn').addEventListener('click', async () => {
    const txt = document.getElementById('ping-text');
    txt.innerText = "Pinging...";
    try {
        const response = await fetch('/api/ping');
        const data = await response.json();
        txt.innerText = data.ping;
    } catch (error) {
        txt.innerText = "Error";
        console.error("Ping operation failed:", error);
    }
});

// Explicit non-blocking initialization engine
async function startDashboardEngine() {
    try {
        await fetchSystemSpecs();
    } catch (err) {
        console.error("Specs boot synchronization failed:", err);
    }

    async function statLoop() {
        await updateDashboard();
        setTimeout(statLoop, 1000);
    }
    statLoop();
}

startDashboardEngine();
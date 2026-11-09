const modal = document.getElementById('modal');
const addStockBtn = document.getElementById('addStockBtn');
const cancelBtn = document.getElementById('cancelBtn');
const form = document.getElementById('addStockForm');
const grid = document.getElementById('stockGrid');

addStockBtn.onclick = () => modal.classList.remove('hidden');
cancelBtn.onclick = () => modal.classList.add('hidden');

const stockNames = {
    "SBIN.NS": "SBI",
    "HDFCBANK.NS": "HDFC Bank",
    "RELIANCE.NS": "Reliance",
    "INFY.NS": "Infosys",
    "TCS.NS": "TCS"
};

async function loadDashboard() {
    try {
        const res = await fetch('/api/data');
        const data = await res.json();
        renderGrid(data);
    } catch (e) {
        console.error("Dashboard error:", e);
    }
}

function renderGrid(data) {
    grid.innerHTML = '';
    
    if(!data.stocks || data.stocks.length === 0) {
        grid.innerHTML = '<p style="color:var(--text-muted); grid-column: 1/-1; text-align:center; font-size:1.1rem; margin-top:2rem;">No stocks currently being monitored. Add one to get started!</p>';
        return;
    }

    data.stocks.forEach((stock, idx) => {
        const price = data.prices[stock.symbol] || '--';
        const stateKey = `${stock.symbol}|${stock.alert_type}|${stock.target_price}`;
        const isTriggered = data.alert_states[stateKey];
        const displayName = stockNames[stock.symbol] || stock.symbol;
        
        const card = document.createElement('div');
        card.className = 'stock-card';
        card.innerHTML = `
            <div class="status-indicator ${isTriggered ? 'active' : ''}"></div>
            <div class="card-header">
                <div class="symbol">${displayName}</div>
                <button class="delete-btn" onclick="deleteStock(${idx})">×</button>
            </div>
            <div class="price-section">
                <div class="current-price">₹${price !== '--' ? price.toFixed(2) : '--'}</div>
                <div class="target-price">${stock.alert_type === 'above' ? '≥' : '≤'} ₹${stock.target_price.toFixed(2)}</div>
            </div>
        `;
        grid.appendChild(card);
    });
}

window.deleteStock = async (index) => {
    if(!confirm('Stop tracking this stock?')) return;
    await fetch('/api/remove/' + index, { method: 'POST' });
    loadDashboard();
};

form.onsubmit = async (e) => {
    e.preventDefault();
    const payload = {
        symbol: document.querySelector('input[name="stockSymbol"]:checked').value,
        target_price: parseFloat(document.getElementById('priceInp').value),
        alert_type: document.getElementById('typeInp').value
    };
    
    await fetch('/api/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    
    form.reset();
    modal.classList.add('hidden');
    loadDashboard();
};

setInterval(loadDashboard, 5000);
loadDashboard();

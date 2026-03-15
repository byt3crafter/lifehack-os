/**
 * Misc - Wishlist, Deep Work, Replacements
 */

// ============== WISHLIST ==============
async function loadWishlist() {
    const items = await api('/wishlist');
    
    const listEl = $('#wishlist-list');
    if (listEl && items) {
        listEl.innerHTML = items.map(w => `
            <div class="card rounded-lg p-3 mb-2">
                <div class="font-medium text-sm">${w.title}</div>
                <div class="text-xs text-gray-500">${w.location || ''} ${w.category ? `• ${w.category}` : ''}</div>
                ${w.description ? `<div class="text-xs text-gray-400 mt-1">${w.description}</div>` : ''}
            </div>
        `).join('') || '<div class="text-gray-500">No wishlist items</div>';
    }
}

function addWishlistModal() {
    showModal('Add to Wishlist', `
        <input id="nw-title" type="text" class="w-full p-2 rounded border text-sm mb-2" placeholder="Title">
        <input id="nw-location" type="text" class="w-full p-2 rounded border text-sm mb-2" placeholder="Location (optional)">
        <select id="nw-category" class="w-full p-2 rounded border text-sm mb-2">
            <option value="place">📍 Place to visit</option>
            <option value="food">🍽️ Food to try</option>
            <option value="activity">🎯 Activity</option>
            <option value="buy">🛒 Thing to buy</option>
        </select>
        <textarea id="nw-desc" class="w-full p-2 rounded border text-sm mb-3" rows="2" placeholder="Notes"></textarea>
        <div class="flex gap-2">
            <button onclick="hideModal()" class="flex-1 py-2 rounded border border-gray-600 text-sm">Cancel</button>
            <button onclick="saveWishlist()" class="flex-1 py-2 rounded bg-accent text-sm">Add</button>
        </div>
    `);
}

async function saveWishlist() {
    const title = $('#nw-title').value.trim();
    if (!title) return alert('Enter a title');
    
    const data = {
        title,
        location: $('#nw-location')?.value || '',
        category: $('#nw-category')?.value || 'place',
        description: $('#nw-desc')?.value || ''
    };
    
    const result = await api('/wishlist', 'POST', data);
    if (result && result.success) {
        hideModal();
        loadWishlist();
    }
}

// ============== DEEP WORK ==============
let dwInterval;

async function loadDeepWork() {
    const dw = await api('/deepwork/status');
    const projects = await api('/projects');
    if (!dw) return;
    
    if (projects) {
        const select = $('#dw-project');
        if (select) {
            select.innerHTML = '<option value="">General Focus</option>' + 
                projects.map(p => `<option value="${p.id}">${p.title || p.name}</option>`).join('');
        }
    }
    
    clearInterval(dwInterval);
    
    const activeCard = $('#dw-active-card');
    const startCard = $('#dw-start-card');
    
    if (dw.active) {
        if (activeCard) activeCard.classList.remove('hidden');
        if (startCard) startCard.classList.add('hidden');
        
        const startTime = new Date(dw.active.started_at);
        
        function updateDwTimer() {
            const now = new Date();
            const elapsed = Math.floor((now - startTime) / 1000 / 60); // minutes
            
            const timerEl = $('#dw-timer');
            if (timerEl) {
                timerEl.textContent = `${elapsed} min`;
            }
        }
        
        updateDwTimer();
        dwInterval = setInterval(updateDwTimer, 60000);
    } else {
        if (activeCard) activeCard.classList.add('hidden');
        if (startCard) startCard.classList.remove('hidden');
    }
    
    // History
    const historyEl = $('#dw-history');
    if (historyEl && dw.history) {
        historyEl.innerHTML = dw.history.map(s => `
            <div class="card rounded-lg p-3 mb-2">
                <div class="flex justify-between">
                    <div class="text-sm">${s.project_name || 'General'}</div>
                    <div class="text-success text-sm">${s.duration_minutes} min • +${s.points_earned} XP</div>
                </div>
            </div>
        `).join('') || '<div class="text-gray-500 text-sm">No sessions yet</div>';
    }
}

async function startDeepWork() {
    const projectId = $('#dw-project')?.value || null;
    const result = await api('/deepwork/start', 'POST', { project_id: projectId });
    if (result && result.success) {
        loadDeepWork();
    }
}

async function endDeepWork() {
    const result = await api('/deepwork/end', 'POST');
    if (result && result.success) {
        alert(`Session ended! ${result.duration} min • +${result.points} XP`);
        loadDeepWork();
    }
}

// ============== REPLACEMENTS ==============
async function loadReplace() {
    const data = await api('/replacements');
    if (!data) return;
    
    const actionsEl = $('#replace-actions');
    if (actionsEl && data.actions) {
        actionsEl.innerHTML = data.actions.map(a => `
            <button onclick="logReplacement(${a.id})" class="card rounded-lg p-3 text-left hover:border-accent transition">
                <div class="text-sm">${a.name}</div>
                <div class="text-xs text-gray-500">${a.points} XP</div>
            </button>
        `).join('');
    }
    
    const logsEl = $('#replace-logs');
    if (logsEl && data.logs) {
        logsEl.innerHTML = data.logs.map(l => `
            <div class="text-sm text-gray-400">
                ${formatDate(l.date)} • ${l.action_name} • +${l.points} XP
            </div>
        `).join('') || '<div class="text-gray-500">No redirects logged</div>';
    }
}

async function logReplacement(actionId) {
    const urgeLevel = prompt('Urge level (1-5)?', '3');
    if (!urgeLevel) return;
    
    const result = await api('/replacements', 'POST', {
        action_id: actionId,
        urge_level: parseInt(urgeLevel)
    });
    
    if (result && result.success) {
        alert(`Urge redirected! +${result.points} XP`);
        loadReplace();
    }
}

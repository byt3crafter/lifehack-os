/**
 * Walks - Movement tracking
 */
async function loadWalks() {
    const data = await api('/walks');
    if (!data) return;
    
    const statsEl = $('#walks-stats');
    if (statsEl && data.stats) {
        statsEl.innerHTML = `
            <div class="text-center">
                <div class="text-2xl font-bold">${data.stats.this_week || 0}</div>
                <div class="text-xs text-gray-400">This Week</div>
            </div>
            <div class="text-center">
                <div class="text-2xl font-bold">${(data.stats.total_km || 0).toFixed(1)}</div>
                <div class="text-xs text-gray-400">Total KM</div>
            </div>
        `;
    }
    
    const listEl = $('#walks-list');
    if (listEl && data.walks) {
        listEl.innerHTML = data.walks.map(w => `
            <div class="card rounded-lg p-3 mb-2">
                <div class="flex justify-between items-center">
                    <div>
                        <div class="text-sm">${w.location || 'Walk'}</div>
                        <div class="text-xs text-gray-500">${formatDate(w.date)} • ${w.duration_minutes} min • ${w.distance_km} km</div>
                    </div>
                    <div class="text-success text-sm">+${w.points} XP</div>
                </div>
            </div>
        `).join('') || '<div class="text-gray-500">No walks logged yet</div>';
    }
}

function addWalkModal() {
    showModal('Log Movement', `
        <select id="nw-type" class="w-full p-2 rounded border text-sm mb-2">
            <option value="exercise">🏃 Exercise</option>
            <option value="commute">🚶 Commute</option>
            <option value="errand">🛒 Errand</option>
        </select>
        <input id="nw-location" type="text" class="w-full p-2 rounded border text-sm mb-2" placeholder="Location (optional)">
        <div class="grid grid-cols-2 gap-2 mb-2">
            <input id="nw-duration" type="number" class="p-2 rounded border text-sm" placeholder="Duration (min)">
            <input id="nw-distance" type="number" step="0.1" class="p-2 rounded border text-sm" placeholder="Distance (km)">
        </div>
        <div class="grid grid-cols-2 gap-2 mb-3">
            <div>
                <label class="text-xs text-gray-400">Mood Before</label>
                <input id="nw-mood-before" type="range" min="1" max="5" value="3" class="w-full">
            </div>
            <div>
                <label class="text-xs text-gray-400">Mood After</label>
                <input id="nw-mood-after" type="range" min="1" max="5" value="3" class="w-full">
            </div>
        </div>
        <div class="flex gap-2">
            <button onclick="hideModal()" class="flex-1 py-2 rounded border border-gray-600 text-sm">Cancel</button>
            <button onclick="saveWalk()" class="flex-1 py-2 rounded bg-accent text-sm">Log</button>
        </div>
    `);
}

async function saveWalk() {
    const data = {
        movement_type: $('#nw-type')?.value || 'exercise',
        location: $('#nw-location')?.value || '',
        duration_minutes: parseInt($('#nw-duration')?.value || 0),
        distance_km: parseFloat($('#nw-distance')?.value || 0),
        mood_before: parseInt($('#nw-mood-before')?.value || 3),
        mood_after: parseInt($('#nw-mood-after')?.value || 3)
    };
    
    if (!data.duration_minutes && !data.distance_km) {
        return alert('Enter duration or distance');
    }
    
    const result = await api('/walks', 'POST', data);
    if (result && result.success) {
        hideModal();
        alert(`Logged! +${result.points} XP`);
        loadWalks();
    }
}

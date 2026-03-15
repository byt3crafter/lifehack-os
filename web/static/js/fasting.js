/**
 * Fasting - Intermittent fasting tracker
 */
let fastingInterval;

async function loadFasting() {
    const data = await api('/fasting/status');
    if (!data) return;
    
    clearInterval(fastingInterval);
    
    const activeCard = $('#fasting-active');
    const startCard = $('#fasting-start');
    
    if (data.active) {
        if (activeCard) activeCard.classList.remove('hidden');
        if (startCard) startCard.classList.add('hidden');
        
        const startTime = new Date(data.active.start_at);
        const targetHours = data.active.target_hours || 16;
        
        function updateTimer() {
            const now = new Date();
            const elapsed = (now - startTime) / 1000 / 3600; // hours
            const remaining = targetHours - elapsed;
            
            const timerEl = $('#fasting-timer');
            if (timerEl) {
                const hours = Math.floor(elapsed);
                const minutes = Math.floor((elapsed - hours) * 60);
                timerEl.textContent = `${hours}h ${minutes}m`;
            }
            
            const progressEl = $('#fasting-progress');
            if (progressEl) {
                progressEl.style.width = `${Math.min(100, (elapsed / targetHours) * 100)}%`;
            }
            
            const remainingEl = $('#fasting-remaining');
            if (remainingEl) {
                if (remaining > 0) {
                    remainingEl.textContent = `${Math.floor(remaining)}h ${Math.floor((remaining % 1) * 60)}m to go`;
                } else {
                    remainingEl.textContent = '🎉 Target reached!';
                }
            }
        }
        
        updateTimer();
        fastingInterval = setInterval(updateTimer, 60000);
    } else {
        if (activeCard) activeCard.classList.add('hidden');
        if (startCard) startCard.classList.remove('hidden');
    }
    
    // History
    const historyEl = $('#fasting-history');
    if (historyEl && data.history) {
        historyEl.innerHTML = data.history.map(f => `
            <div class="card rounded-lg p-3 mb-2">
                <div class="flex justify-between">
                    <div class="text-sm">${formatDate(f.start_at)}</div>
                    <div class="text-success text-sm">${f.duration_hours || '?'}h</div>
                </div>
            </div>
        `).join('') || '<div class="text-gray-500 text-sm">No fasting history</div>';
    }
}

async function startFast(targetHours) {
    const target = targetHours || $('#fast-target')?.value || 16;
    const result = await api('/fasting/start', 'POST', { target: parseInt(target) });
    if (result && result.success) {
        loadFasting();
    }
}

// Alias for HTML compatibility
function endFastModal() {
    showModal('End Fast', `
        <div class="mb-3">
            <label class="text-xs text-gray-400">How do you feel?</label>
            <input type="range" id="end-fast-mood" min="1" max="5" value="3" class="w-full">
        </div>
        <div class="flex gap-2">
            <button onclick="hideModal()" class="flex-1 py-2 rounded border border-gray-600 text-sm">Cancel</button>
            <button onclick="endFast()" class="flex-1 py-2 rounded bg-danger text-sm">End Fast</button>
        </div>
    `);
}

async function endFast() {
    const mood = $('#fast-mood-end')?.value || 3;
    const result = await api('/fasting/end', 'POST', { mood: parseInt(mood) });
    if (result && result.success) {
        alert(`Fast completed! ${result.hours}h • +${result.points} XP`);
        loadFasting();
    }
}

/**
 * Habits - Habit tracking and management
 */
async function loadHabits() {
    const [habits, categories] = await Promise.all([
        api('/habits'),
        api('/categories')
    ]);
    
    if (!habits) return;
    cats = categories || {};
    
    const container = $('#habits-list');
    if (!container) return;
    
    // Group by category
    const grouped = {};
    habits.forEach(h => {
        if (!grouped[h.category]) grouped[h.category] = [];
        grouped[h.category].push(h);
    });
    
    container.innerHTML = Object.entries(grouped).map(([cat, items]) => {
        const catInfo = cats[cat] || { name: cat, color: '#6B7280' };
        return `
            <div class="mb-4">
                <div class="text-xs text-gray-400 mb-2 uppercase tracking-wide">${catInfo.name}</div>
                ${items.map(h => `
                    <div class="card rounded-lg p-3 mb-2 flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <button onclick="toggleHabit(${h.id}, ${h.completed})" 
                                class="w-6 h-6 rounded-full border-2 flex items-center justify-center ${h.completed ? 'bg-success border-success' : 'border-gray-600'}">
                                ${h.completed ? '✓' : ''}
                            </button>
                            <div>
                                <div class="text-sm ${h.completed ? 'line-through text-gray-500' : ''}">${h.name}</div>
                                <div class="text-xs text-gray-500">${h.streak > 0 ? `🔥 ${h.streak} day streak` : ''}</div>
                            </div>
                        </div>
                        <div class="text-xs text-gray-500">${h.points} XP</div>
                    </div>
                `).join('')}
            </div>
        `;
    }).join('');
}

async function toggleHabit(id, isCompleted) {
    if (isCompleted) {
        await api(`/habits/${id}/uncomplete`, 'POST');
    } else {
        await api(`/habits/${id}/complete`, 'POST');
    }
    loadHabits();
    loadDash();
}

function addHabitModal() {
    showModal('New Habit', `
        <input id="nh-name" type="text" class="w-full p-2 rounded border text-sm mb-2" placeholder="Habit name">
        <select id="nh-cat" class="w-full p-2 rounded border text-sm mb-3">
            ${Object.entries(cats).map(([k, v]) => `<option value="${k}">${v.name}</option>`).join('')}
        </select>
        <div class="flex gap-2">
            <button onclick="hideModal()" class="flex-1 py-2 rounded border border-gray-600 text-sm">Cancel</button>
            <button onclick="saveNewHabit()" class="flex-1 py-2 rounded bg-accent text-sm">Create</button>
        </div>
    `);
}

async function saveNewHabit() {
    const name = $('#nh-name').value.trim();
    const category = $('#nh-cat').value;
    if (!name) return alert('Enter habit name');
    
    await api('/habits', 'POST', { name, category });
    hideModal();
    loadHabits();
}

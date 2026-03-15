/**
 * Food - Nutrition logging
 */
async function loadFood() {
    const data = await api('/food');
    if (!data) return;
    
    const statsEl = $('#food-stats');
    if (statsEl) {
        statsEl.innerHTML = `
            <div class="text-center">
                <div class="text-2xl font-bold">${data.today_calories || 0}</div>
                <div class="text-xs text-gray-400">Today's Calories</div>
            </div>
        `;
    }
    
    const listEl = $('#food-list');
    if (listEl && data.logs) {
        listEl.innerHTML = data.logs.map(f => `
            <div class="card rounded-lg p-3 mb-2">
                <div class="flex justify-between items-start">
                    <div>
                        <div class="text-sm">${getMealEmoji(f.meal_type)} ${f.description}</div>
                        <div class="text-xs text-gray-500">
                            ${formatDate(f.logged_at)} • ${f.calories || '?'} cal
                            ${f.protein_g ? ` • ${f.protein_g}g protein` : ''}
                        </div>
                    </div>
                    <button onclick="deleteFood(${f.id})" class="text-gray-500 hover:text-danger text-xs">×</button>
                </div>
            </div>
        `).join('') || '<div class="text-gray-500">No meals logged yet</div>';
    }
}

function getMealEmoji(type) {
    const emojis = { breakfast: '🌅', lunch: '☀️', dinner: '🌙', snack: '🍿' };
    return emojis[type] || '🍽️';
}

function addFoodModal() {
    showModal('Log Meal', `
        <select id="nf-type" class="w-full p-2 rounded border text-sm mb-2">
            <option value="breakfast">🌅 Breakfast</option>
            <option value="lunch">☀️ Lunch</option>
            <option value="dinner">🌙 Dinner</option>
            <option value="snack">🍿 Snack</option>
        </select>
        <textarea id="nf-desc" class="w-full p-2 rounded border text-sm mb-2" rows="2" placeholder="What did you eat?"></textarea>
        <div class="grid grid-cols-2 gap-2 mb-3">
            <input id="nf-cal" type="number" class="p-2 rounded border text-sm" placeholder="Calories (optional)">
            <input id="nf-protein" type="number" class="p-2 rounded border text-sm" placeholder="Protein g">
        </div>
        <div class="flex gap-2">
            <button onclick="hideModal()" class="flex-1 py-2 rounded border border-gray-600 text-sm">Cancel</button>
            <button onclick="saveFoodLog()" class="flex-1 py-2 rounded bg-accent text-sm">Log</button>
        </div>
    `);
}

async function saveFoodLog() {
    const desc = $('#nf-desc').value.trim();
    if (!desc) return alert('Describe what you ate');
    
    const data = {
        meal_type: $('#nf-type')?.value || 'meal',
        description: desc,
        calories: parseInt($('#nf-cal')?.value) || null,
        protein_g: parseInt($('#nf-protein')?.value) || null
    };
    
    const result = await api('/food', 'POST', data);
    if (result && result.success) {
        hideModal();
        loadFood();
    }
}

async function deleteFood(id) {
    if (!confirm('Delete this entry?')) return;
    await api(`/food/${id}`, 'DELETE');
    loadFood();
}

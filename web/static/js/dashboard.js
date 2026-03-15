/**
 * Dashboard - Main dashboard view
 */
async function loadDash() {
    const [stats, daily, insights, habits] = await Promise.all([
        api('/stats'),
        api('/daily'),
        api('/insights'),
        api('/habits')
    ]);
    
    if (!stats || !daily) return;
    
    // Update XP displays
    $$('#mobile-xp, #nav-xp, #desk-xp').forEach(el => {
        if (el) el.textContent = `${stats.total_xp} XP`;
    });
    $$('#nav-level, #desk-level').forEach(el => {
        if (el) el.textContent = `Level ${stats.level} • ${stats.level_name}`;
    });
    
    // Update stats cards
    const xpCard = $('#stat-xp');
    if (xpCard) xpCard.textContent = stats.total_xp;
    
    const levelCard = $('#stat-level');
    if (levelCard) levelCard.textContent = stats.level;
    
    const sobrietyCard = $('#stat-sobriety');
    if (sobrietyCard) sobrietyCard.textContent = stats.sobriety_days;
    
    // Daily score
    const scoreCard = $('#daily-score');
    if (scoreCard && daily.today) {
        scoreCard.textContent = daily.today.score + '%';
    }
    
    // Habits progress
    const habitsProgress = $('#habits-progress');
    if (habitsProgress && daily.today) {
        habitsProgress.textContent = `${daily.today.habits_completed}/${daily.today.habits_total}`;
    }
    
    // Tips
    const tipsEl = $('#daily-tips');
    if (tipsEl && daily.tips) {
        tipsEl.innerHTML = daily.tips.map(t => `<div class="text-sm text-gray-400">• ${t}</div>`).join('');
    }
    
    // AI Insights
    const insightsEl = $('#ai-insights');
    if (insightsEl && insights && insights.length > 0) {
        insightsEl.innerHTML = insights.map(i => `
            <div class="insight-card rounded-lg p-3 mb-2">
                <div class="flex justify-between items-start">
                    <div>
                        <div class="text-sm font-medium text-ai">${i.title}</div>
                        <div class="text-xs text-gray-400 mt-1">${i.content}</div>
                    </div>
                    <button onclick="dismissInsight(${i.id})" class="text-gray-500 hover:text-white">×</button>
                </div>
            </div>
        `).join('');
    }
    
    // Quick habits
    const quickHabits = $('#quick-habits');
    if (quickHabits && habits) {
        const pending = habits.filter(h => !h.completed).slice(0, 4);
        quickHabits.innerHTML = pending.map(h => `
            <button onclick="quickComplete(${h.id})" class="flex items-center gap-2 p-2 rounded hover:bg-white/5">
                <span class="w-5 h-5 rounded border border-gray-600"></span>
                <span class="text-sm">${h.name}</span>
            </button>
        `).join('') || '<div class="text-sm text-gray-500">All done! 🎉</div>';
    }
}

async function dismissInsight(id) {
    await api(`/insights/${id}/dismiss`, 'POST');
    loadDash();
}

async function quickComplete(habitId) {
    await api(`/habits/${habitId}/complete`, 'POST');
    loadDash();
}

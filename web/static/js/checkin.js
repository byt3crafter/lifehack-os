/**
 * Check-in - Daily check-in form
 */
async function loadCheckin() {
    const checkin = await api('/checkin');
    
    if (checkin) {
        // Populate form with existing data
        const completedEl = $('#ci-completed');
        if (completedEl) completedEl.value = checkin.completed_today || '';
        
        const alcoholEl = $('#ci-alcohol');
        if (alcoholEl) alcoholEl.checked = checkin.avoided_alcohol;
        
        const futureEl = $('#ci-future');
        if (futureEl) futureEl.checked = checkin.worked_on_future;
        
        const moodEl = $('#ci-mood');
        if (moodEl) moodEl.value = checkin.mood || 3;
        
        const energyEl = $('#ci-energy');
        if (energyEl) energyEl.value = checkin.energy || 3;
        
        const noteEl = $('#ci-note');
        if (noteEl) noteEl.value = checkin.improvement_note || '';
    }
}

async function saveCheckin() {
    const data = {
        completed_today: $('#ci-completed')?.value || '',
        avoided_alcohol: $('#ci-alcohol')?.checked || false,
        worked_on_future: $('#ci-future')?.checked || false,
        mood: parseInt($('#ci-mood')?.value || 3),
        energy: parseInt($('#ci-energy')?.value || 3),
        improvement_note: $('#ci-note')?.value || ''
    };
    
    const result = await api('/checkin', 'POST', data);
    if (result && result.success) {
        alert(`Check-in saved! +${result.points} XP`);
        loadDash();
    }
}

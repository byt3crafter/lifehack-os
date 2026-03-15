/**
 * Settings - Integrations and app settings
 */
async function loadSettings() {
    const integrations = await api('/integrations');
    if (!integrations) return;
    
    // Vikunja
    const vikunjaStatus = $('#vikunja-status');
    if (vikunjaStatus) {
        vikunjaStatus.innerHTML = integrations.vikunja?.enabled 
            ? '<span class="text-success">✓ Connected</span>'
            : '<span class="text-gray-500">Not connected</span>';
    }
    
    // Google Calendar
    const calStatus = $('#gcal-status');
    if (calStatus) {
        calStatus.innerHTML = integrations.google_calendar?.enabled
            ? '<span class="text-success">✓ Connected</span>'
            : '<span class="text-gray-500">Not connected</span>';
    }
    
    // Firefly
    const fireflyStatus = $('#firefly-status');
    if (fireflyStatus) {
        fireflyStatus.innerHTML = integrations.firefly?.enabled
            ? '<span class="text-success">✓ Connected</span>'
            : '<span class="text-gray-500">Not connected</span>';
    }
}

function vikunjaModal() {
    showModal('Connect Vikunja', `
        <input id="vik-url" type="text" class="w-full p-2 rounded border text-sm mb-2" value="https://tasks.micinthe.com/api/v1" placeholder="API URL">
        <input id="vik-user" type="text" class="w-full p-2 rounded border text-sm mb-2" placeholder="Username">
        <input id="vik-pass" type="password" class="w-full p-2 rounded border text-sm mb-3" placeholder="Password">
        <div class="flex gap-2">
            <button onclick="hideModal()" class="flex-1 py-2 rounded border border-gray-600 text-sm">Cancel</button>
            <button onclick="connectVikunja()" class="flex-1 py-2 rounded bg-accent text-sm">Connect</button>
        </div>
    `);
}

async function connectVikunja() {
    const data = {
        enabled: true,
        api_url: $('#vik-url')?.value,
        username: $('#vik-user')?.value,
        password: $('#vik-pass')?.value
    };
    
    const result = await api('/integrations/vikunja', 'POST', data);
    if (result && result.success) {
        hideModal();
        loadSettings();
        alert('Vikunja connected!');
    } else {
        alert('Connection failed: ' + (result?.error || 'Unknown error'));
    }
}

async function connectGoogleCalendar() {
    const result = await api('/integrations/google_calendar', 'POST', { enabled: true });
    if (result && result.success) {
        loadSettings();
        alert('Google Calendar connected!');
    } else {
        alert('Connection failed: ' + (result?.error || 'Unknown error'));
    }
}

async function connectFirefly() {
    const result = await api('/integrations/firefly', 'POST', { enabled: true });
    if (result && result.success) {
        loadSettings();
        alert('Firefly connected!');
    } else {
        alert('Connection failed: ' + (result?.error || 'Unknown error'));
    }
}

async function resetEverything() {
    if (!confirm('Reset ALL data? This clears habits, check-ins, stats, and learned patterns. Cannot be undone.')) return;
    if (!confirm('Are you REALLY sure?')) return;
    
    // Reset patterns
    await api('/patterns/reset', 'POST');
    
    alert('Data reset. Refresh the page.');
    location.reload();
}

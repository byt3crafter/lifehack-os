/**
 * Navigation - Sidebar and view switching
 */
function toggleNav() {
    const nav = $('#mobile-nav');
    const overlay = $('#nav-overlay');
    nav.classList.toggle('-translate-x-full');
    overlay.classList.toggle('hidden');
}

function nav(view) {
    // Close mobile menu
    toggleNav();
    
    // Hide all views
    $$('.view').forEach(v => v.classList.add('hidden'));
    
    // Remove active from all nav buttons
    $$('.nav-btn').forEach(btn => btn.classList.remove('active'));
    
    // Show selected view
    const viewEl = $(`#v-${view}`);
    if (viewEl) {
        viewEl.classList.remove('hidden');
    }
    
    // Mark nav buttons as active
    $$(`[data-v="${view}"]`).forEach(btn => btn.classList.add('active'));
    
    // Load view data
    loadView(view);
}

async function loadView(view) {
    switch (view) {
        case 'dashboard': await loadDash(); break;
        case 'habits': await loadHabits(); break;
        case 'projects': await loadProjects(); break;
        case 'checkin': await loadCheckin(); break;
        case 'walks': await loadWalks(); break;
        case 'replace': await loadReplace(); break;
        case 'food': await loadFood(); break;
        case 'fasting': await loadFasting(); break;
        case 'wishlist': await loadWishlist(); break;
        case 'deepwork': await loadDeepWork(); break;
        case 'settings': await loadSettings(); break;
    }
}

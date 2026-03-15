/**
 * Init - App initialization
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Load categories first
    cats = await api('/categories') || {};
    
    // Load dashboard
    await loadDash();
    
    // Mark dashboard as active
    $$('[data-v="dashboard"]').forEach(btn => btn.classList.add('active'));
});

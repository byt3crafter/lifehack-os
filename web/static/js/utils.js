/**
 * Utils - Core utilities and API helpers
 */
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let cats = {};

async function api(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin'
    };
    if (data) options.body = JSON.stringify(data);
    
    const response = await fetch('/api' + endpoint, options);
    if (response.status === 401) {
        location.href = '/login';
        return null;
    }
    return response.json();
}

function showModal(title, content) {
    const modal = $('#modal');
    $('#modal-title').textContent = title;
    $('#modal-body').innerHTML = content;
    modal.classList.remove('hidden');
}

function hideModal() {
    $('#modal').classList.add('hidden');
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function formatTime(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

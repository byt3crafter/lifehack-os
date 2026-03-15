/**
 * Projects - Project and task management
 */
async function loadProjects() {
    const [projects, tasks] = await Promise.all([
        api('/projects'),
        api('/tasks')
    ]);
    
    const container = $('#projects-list');
    if (!container || !projects) return;
    
    container.innerHTML = projects.map(p => {
        const projectTasks = tasks ? tasks.filter(t => t.project_id == p.id) : [];
        const pending = projectTasks.filter(t => !t.done);
        
        return `
            <div class="card rounded-lg p-4 mb-3">
                <div class="flex justify-between items-start mb-2">
                    <div>
                        <div class="font-medium">${p.title || p.name}</div>
                        <div class="text-xs text-gray-500">${p.description || ''}</div>
                    </div>
                    <span class="text-xs px-2 py-1 rounded bg-white/10">${p.provider || 'native'}</span>
                </div>
                <div class="flex items-center gap-2 mb-3">
                    <div class="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                        <div class="h-full bg-accent" style="width: ${p.progress || 0}%"></div>
                    </div>
                    <span class="text-xs text-gray-400">${p.progress || 0}%</span>
                </div>
                <div class="space-y-2">
                    ${pending.slice(0, 5).map(t => `
                        <div class="flex items-center gap-2 text-sm">
                            <button onclick="completeTask('${t.id}')" class="w-4 h-4 rounded border border-gray-600 hover:border-accent"></button>
                            <span class="${t.done ? 'line-through text-gray-500' : ''}">${t.title}</span>
                        </div>
                    `).join('')}
                    ${pending.length > 5 ? `<div class="text-xs text-gray-500">+${pending.length - 5} more</div>` : ''}
                </div>
            </div>
        `;
    }).join('') || '<div class="text-gray-500">No projects yet</div>';
}

async function completeTask(taskId) {
    await api(`/tasks/${taskId}/complete`, 'POST');
    loadProjects();
}

function addTaskModal() {
    // TODO: Implement task creation modal
    showModal('New Task', `
        <p class="text-gray-400 text-sm">Task creation coming soon. Use Vikunja for now.</p>
        <button onclick="hideModal()" class="w-full mt-4 py-2 rounded border border-gray-600 text-sm">Close</button>
    `);
}

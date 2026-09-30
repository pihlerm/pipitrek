 // Task types available in the task builder, mirroring the classes in telescope_task.py.
    // Each field becomes an input in the task's div; its name is used as the JSON key sent to the backend.
    const TASK_TYPES = {
        'Slew': {
            fields: [
                { name: 'target_ra', label: 'Target RA', placeholder: '+HH:MM:SS' },
                { name: 'target_dec', label: 'Target DEC', placeholder: '+DD*MM:SS' },
            ]
        },
        'Imaging': {
            fields: [
                { name: 'exposure_time', label: 'Exposure (s)', type: 'number' },
                { name: 'exposure_count', label: 'Shots', type: 'number' },
            ]
        },
        'MeridianFlip': { fields: [] },
        'InitializePosition': { fields: [] },
        'StartAutoguider': { fields: [{ name: 'calibrate_axis', label: 'Calibrate axis', type: 'checkbox' }] },
        'StopAutoguider': { fields: [] },
        'Park': { fields: [] },
    };

    let taskIdCounter = 10000;  // client-side task IDBObjectStore. server will assign task id's
    let taskStatusPollTimer = null;

    // Populate the task type <select> once the DOM is ready.
    document.addEventListener('DOMContentLoaded', () => {
        const select = document.getElementById('task_type_select');
        if (!select) return;
        Object.keys(TASK_TYPES).forEach(type => {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type;
            select.appendChild(option);
        });
        taskStatusPollTimer = setInterval(pollTaskListStatus, 1000);
        getTaskList();
    });

    
    
    function addTask(type, initialValues) {
        const taskDef = TASK_TYPES[type];
        if (!taskDef) return;

        let id = null;
        let taskid;
        
        if(initialValues && initialValues['id'] !== undefined) {
            id = `task_${initialValues['id']}`;
            taskid = initialValues['id'];
        } else {
            id = `task_${taskIdCounter++}`;
            taskid = "[]";
        }

        const div = document.createElement('div');
        div.className = 'task-item';
        div.id = id;
        div.dataset.type = type;

        // start_time/end_time come from the backend as Python time.time() epoch seconds.
        let start_time = initialValues && initialValues['start_time'] ? new Date(initialValues['start_time'] * 1000).toLocaleString() : 'N/A';
        let end_time = initialValues && initialValues['end_time'] ? new Date(initialValues['end_time'] * 1000).toLocaleString() : 'N/A';

        // Stash the result on the div so the status icon can show it on click, without re-escaping it into HTML attributes.
        if (initialValues && initialValues['result'] !== undefined) {
            div.dataset.result = JSON.stringify(initialValues['result']);
        }

        let html = `<div class="task-item-header"><span class="task-status-icon" id="${id}_status" onclick="showTaskResult('${id}', event)"></span><span class="task-status-id">${taskid}</span>`
        html += `<b class="task-status-type">${type}</b>`
        html += `<span class="mini-button" id="${id}_progress"></span>`
        html += `<span class="task-status-time">Start: ${start_time}</span>`;
        html += `<span class="task-status-time">Finish: ${end_time}</span>`;
        html += `<button class="mini-button" onclick="removeTask('${id}')" title="Remove task">X</button></div>`;
        html += `<div class="task-item-field">`;
        taskDef.fields.forEach(field => {
            const value = (initialValues && initialValues[field.name] !== undefined) ? initialValues[field.name] : '';
            //html += `<div class="task-item-field">
            html += `<label for="${id}_${field.name}">${field.label}</label><input class="two_buttons_input" type="${field.type || 'text'}" id="${id}_${field.name}" placeholder="${field.placeholder || ''}" value="${value}">`;
        });
        html += `</div>`;
        div.innerHTML = html;
        document.getElementById('task_list').appendChild(div);
    }

    // Adds a Slew task pre-filled with the current GOTO target RA/DEC input values.
    function addGotoTask() {
        const target_ra = document.getElementById('ra-input').value.trim();
        const target_dec = document.getElementById('dec-input').value.trim();
        addTask('Slew', { target_ra, target_dec });
        showPanel('tasks_panel');
    }

    // Removes a task locally, and if it was already sent to the backend (numeric server id,
    // as opposed to the client-side placeholder ids starting at 10000), asks the backend to
    // remove it too. The backend refuses if the task is already running or completed.
    function removeTask(id) {
        const el = document.getElementById(id);
        if (!el) return;

        const numericId = parseInt(id.replace('task_', ''), 10);
        if (!isNaN(numericId) && numericId < 10000) {
            fetch(`/remove_task/${numericId}`, { method: 'DELETE' })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'ok') {
                    el.remove();
                } else {
                    alert(data.message || 'Could not remove task.');
                }
            })
            .catch(error => {
                addMessage('Error: ' + error);
            });
        } else {
            el.remove();
        }
    }


    // Builds the JSON array of tasks from the task_list divs, e.g. [{"type":"Slew","target_ra":"...", ...}, ...]
    function buildTaskListJSON() {
        const tasks = [];
        document.querySelectorAll('#task_list .task-item').forEach(div => {
            const type = div.dataset.type;
            const taskDef = TASK_TYPES[type];
            const task = { type };
            taskDef.fields.forEach(field => {
                const input = document.getElementById(`${div.id}_${field.name}`);
                if (!input) return;
                task[field.name] = field.type === 'number' ?
                                 parseFloat(input.value) : 
                                 field.type === 'checkbox' ? input.checked : input.value;
            });
            const numericId = parseInt(div.id.replace('task_', ''), 10);
            if (!isNaN(numericId) && numericId < 10000) {
                task.id = numericId;
            }
            tasks.push(task);
        });
        return tasks;
    }

    // Clears the local task list and rebuilds it from the JSON array returned by the backend.
    function buildTasksFromJSON(tasks) {
        
        clearTaskList();
        if (!Array.isArray(tasks)) return;
        taskRunIds = [];

        tasks.forEach(task => {
            const { type, ...values } = task;
            addTask(type, values);
            taskRunIds.push(`task_${task.id}`);
        });
    }

    function getTaskList() {
        fetch('/get_task_list')
        .then(response => response.json())
        .then(data => {
            addMessage(JSON.stringify(data, null, 2));            
            buildTasksFromJSON(data);
            clearInterval(taskStatusPollTimer);
            taskStatusPollTimer = setInterval(pollTaskListStatus, 1000);
        })
        .catch(error => {
            addMessage('Error: ' + error);
        });
    }

    function clearTaskList() {
        document.querySelectorAll('#task_list .task-item').forEach(div => div.remove());
        taskRunIds = [];
        clearTaskStatusIcons();
    }

    let taskRunIds = []; // ids of the task-item divs, in the order they were sent to the backend

    // call server to add new tasks to the existing task list
    // only select tasks with missing id
    function addToTaskList() {
        const tasks = buildTaskListJSON();
        if (tasks.length === 0) {
            alert('Task list is empty.');
            return;
        }
        // Filter out tasks that already have an id
        const newTasks = tasks.filter(task => !task.id);

        console.log('New tasks to add:', newTasks);

        fetch('/add_tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newTasks)
        })
        .then(response => response.json())
        .then(data => {
            addMessage(JSON.stringify(data, null, 2));
            getTaskList();  // refresh actual list from server
        })
        .catch(error => {
            addMessage('Error: ' + error);
        });
    }

    function clearTaskStatusIcons() {
        taskRunIds.forEach(id => {
            const icon = document.getElementById(`${id}_status`);
            if (icon) {
                icon.textContent = '';
                icon.classList.remove('task-status-running');
            }
        });
    }

    // Shows the stashed result (from initialValues.result, e.g. server task history) for a task, if any.
    // Falls back to fetching the task from the backend when no result has been cached client-side yet.
    function showTaskResult(id, event) {
        const div = document.getElementById(id);
        if (!div) return;
        const anchor = (event && event.currentTarget) || document.getElementById(`${id}_status`);

        if (div.dataset.result !== undefined) {
            showResultBalloon(anchor, div.dataset.result);
            return;
        }

        const numericId = parseInt(id.replace('task_', ''), 10);
        if (isNaN(numericId)) return;

        fetch(`/get_task/${numericId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok' && data.task && data.task.result !== undefined) {
                div.dataset.result = JSON.stringify(data.task.result);
                showResultBalloon(anchor, div.dataset.result);
            } else {
                showResultBalloon(anchor, data.message || 'No result available.');
            }
        })
        .catch(error => {
            showResultBalloon(anchor, 'Error: ' + error);
        });
    }

    // Renders a small popup balloon near `anchor` with `text`, dismissed on the next outside click.
    function showResultBalloon(anchor, text) {
        closeResultBalloon();

        const balloon = document.createElement('div');
        balloon.className = 'task-result-balloon';
        balloon.textContent = text;
        document.body.appendChild(balloon);

        const rect = anchor.getBoundingClientRect();
        const top = Math.min(rect.bottom + 4, window.innerHeight - balloon.offsetHeight - 4);
        const left = Math.min(rect.left, window.innerWidth - balloon.offsetWidth - 4);
        balloon.style.top = `${Math.max(top, 4)}px`;
        balloon.style.left = `${Math.max(left, 4)}px`;

        // Defer listener registration so the click that opened the balloon doesn't immediately close it.
        setTimeout(() => document.addEventListener('click', closeResultBalloonOnOutsideClick), 0);
    }

    function closeResultBalloon() {
        document.querySelectorAll('.task-result-balloon').forEach(el => el.remove());
        document.removeEventListener('click', closeResultBalloonOnOutsideClick);
    }

    function closeResultBalloonOnOutsideClick(event) {
        if (!event.target.closest('.task-result-balloon')) {
            closeResultBalloon();
        }
    }

    // Reflects /task_list_status onto each task's status icon: hourglass while running,
    // checkmark once completed successfully, red X on failure.
    function updateTaskStatusIcons(data) {
        taskRunIds.forEach((id, index) => {
            const icon = document.getElementById(`${id}_status`);
            const progress = document.getElementById(`${id}_progress`);
            if (!icon || !progress) return;

            if (data.task_status && index < data.task_status.length) {
                const result = data.task_status[index];
                const pending = !result || result === 'pending';
                const failed = result && result === 'error';
                const running = result && result === 'running';
                if (running) {
                    icon.textContent = '🔄';
                    icon.title = 'Running'+ (data.current_task_progress !== undefined ? 100-data.current_task_progress + '%' : '');
                    icon.classList.add('task-status-running');
                    progress.textContent = ''+ (data.current_task_progress !== undefined ? 100-data.current_task_progress + '%' : '');
                }
                else if (pending) {
                    icon.textContent = '⌛';
                    icon.title = 'Waiting';
                    icon.classList.remove('task-status-running');
                    progress.textContent = '';
                }
                else {
                    icon.textContent = failed ? '❌' : '✅';
                    icon.title = failed ? (result.message || 'Failed') : 'Completed';
                    icon.classList.remove('task-status-running');
                    progress.textContent = '';
                }

            
            } else {
                icon.textContent = '';
                icon.title = '';
                icon.classList.remove('task-status-running');
            }
        });
    }

    function pollTaskListStatus() {
        if(!isPanelVisible('tasks_panel')) return;

        fetch('/task_list_status')
        .then(response => response.json())
        .then(data => {
            //addMessage(JSON.stringify(data, null, 2));
            updateTaskStatusIcons(data);
            if (!data.running) {
                document.getElementById('start_scheduler_button').textContent = 'Start';
                document.getElementById('start_scheduler_button').title = 'Start task scheduler';
                document.getElementById('scheduler_status').textContent = 'stopped';
            } else {
                document.getElementById('start_scheduler_button').textContent = 'Stop';
                document.getElementById('start_scheduler_button').title = 'Stop task scheduler';
                document.getElementById('scheduler_status').textContent = 'running';
            }
        })
        .catch(error => {
            addMessage('Error: ' + error);
        });
    }


    function schedulerControl(){
        const schedulerStatus = document.getElementById('scheduler_status').textContent;
        if (schedulerStatus === 'running') {
            stopScheduler();
        } else {
            startScheduler();
        }
    }

    function startScheduler() {

        fetch('/start_scheduler', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            addMessage(JSON.stringify(data, null, 2));
            pollTaskListStatus();
        }) // Close the .then(data => { ... }) block
        .catch(error => {
            addMessage('Error: ' + error);
        });
    }
    function stopScheduler() {

        fetch('/stop_scheduler', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            addMessage(JSON.stringify(data, null, 2));
            pollTaskListStatus();
        }) // Close the .then(data => { ... }) block
        .catch(error => {
            addMessage('Error: ' + error);
        });
    }
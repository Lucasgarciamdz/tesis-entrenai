document.addEventListener('DOMContentLoaded', () => {
    const courseNamePlaceholder = document.getElementById('course-name-placeholder');
    const statusMessagesManage = document.getElementById('status-messages-manage');
    const refreshMoodleFilesButton = document.getElementById('refresh-moodle-files-button');
    const indexedFilesList = document.getElementById('indexed-files-list');
    const processingFilesList = document.getElementById('processing-files-list');

    const API_BASE_URL = 'http://localhost:8000/api/v1'; // Adjust if necessary
    let courseId;
    let activeTasks = {}; // To keep track of intervals for tasks

    // Verifica que los elementos existen antes de usarlos
    if (!courseNamePlaceholder || !statusMessagesManage || !refreshMoodleFilesButton || !indexedFilesList || !processingFilesList) {
        console.error('Faltan elementos del DOM requeridos en manage_files.html. Revisa el HTML.');
        return;
    }

    // --- Initialization ---
    function initializePage() {
        const params = new URLSearchParams(window.location.search);
        courseId = params.get('course_id');

        if (!courseId) {
            updateStatusManage('Error: No se ha especificado un ID de curso en la URL.', 'error');
            disableAllControls();
            return;
        }

        // For now, just display the ID. A future improvement could be to fetch course name.
        if (courseNamePlaceholder) {
            courseNamePlaceholder.textContent = `ID ${courseId}`;
        }
        
        loadIndexedFiles(courseId);
        setupEventListeners();
    }

    function disableAllControls() {
        if (refreshMoodleFilesButton) refreshMoodleFilesButton.disabled = true;
        // Further disabling of other controls can be added if necessary
    }

    function setupEventListeners() {
        if (refreshMoodleFilesButton) {
            refreshMoodleFilesButton.addEventListener('click', () => handleRefreshFiles(courseId));
        }
    }

    // --- Status Updates ---
    function updateStatusManage(message, type = 'info', targetElement = statusMessagesManage) {
        if (!targetElement) return;
        const p = document.createElement('p');
        p.className = type; // Assumes CSS classes 'info', 'success', 'warning', 'error' exist
        p.textContent = message;
        
        // Prepend new message
        if (targetElement.firstChild) {
            targetElement.insertBefore(p, targetElement.firstChild);
        } else {
            targetElement.appendChild(p);
        }

        // Limit number of messages
        while (targetElement.children.length > 8) {
            targetElement.removeChild(targetElement.lastChild);
        }
    }

    // --- Load Indexed Files ---
    async function loadIndexedFiles(currentCourseId) {
        if (!indexedFilesList) return;
        updateStatusManage(`Cargando archivos indexados para el curso ID ${currentCourseId}...`, 'info');
        indexedFilesList.innerHTML = '<li>Cargando...</li>'; // Clear previous and show loading

        try {
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/indexed-files`);
            if (!response.ok) {
                if (response.status === 404) {
                    updateStatusManage(`No se encontraron archivos indexados para el curso ID ${currentCourseId}. Puede que necesites procesar algunos primero.`, 'warning');
                    indexedFilesList.innerHTML = '<li>No hay archivos indexados.</li>';
                } else {
                    const errorData = await response.json().catch(() => null);
                    throw new Error(`Error ${response.status}: ${errorData?.detail || 'No se pudieron cargar los archivos indexados.'}`);
                }
                return;
            }
            const files = await response.json();
            if (!Array.isArray(files)) {
                throw new Error("Respuesta inesperada del servidor al cargar archivos indexados.");
            }

            if (files.length === 0) {
                indexedFilesList.innerHTML = '<li>No hay archivos indexados.</li>';
                updateStatusManage('Lista de archivos indexados cargada. No se encontraron archivos.', 'info');
                return;
            }

            indexedFilesList.innerHTML = ''; // Clear loading/previous
            files.forEach(file => {
                const li = document.createElement('li');
                li.dataset.filename = file.filename; // Store filename for deletion
                
                const fileNameSpan = document.createElement('span');
                fileNameSpan.textContent = `${file.filename} (Modificado Moodle: ${new Date(file.last_modified_moodle * 1000).toLocaleString()})`;
                li.appendChild(fileNameSpan);

                const deleteButton = document.createElement('button');
                deleteButton.textContent = 'Eliminar';
                deleteButton.classList.add('delete-btn'); // For styling
                deleteButton.addEventListener('click', () => handleDeleteFile(currentCourseId, file.filename, li));
                li.appendChild(deleteButton);
                
                indexedFilesList.appendChild(li);
            });
            updateStatusManage(`Lista de archivos indexados cargada para el curso ID ${currentCourseId}.`, 'success');

        } catch (error) {
            console.error('Error loading indexed files:', error);
            updateStatusManage(`Error al cargar archivos indexados: ${error.message}`, 'error');
            if (indexedFilesList) indexedFilesList.innerHTML = '<li>Error al cargar archivos.</li>';
        }
    }

    // --- Delete File ---
    async function handleDeleteFile(currentCourseId, filename, listItemElement) {
        if (!confirm(`¿Estás seguro de que quieres eliminar el archivo "${filename}" y todos sus datos procesados? Esta acción no se puede deshacer.`)) {
            return;
        }
        updateStatusManage(`Eliminando archivo "${filename}"...`, 'info');
        try {
            const encodedFilename = encodeURIComponent(filename);
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/indexed-files/${encodedFilename}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => null);
                throw new Error(`Error ${response.status}: ${errorData?.detail || 'No se pudo eliminar el archivo.'}`);
            }
            
            // const result = await response.json(); // If backend sends a JSON response
            updateStatusManage(`Archivo "${filename}" eliminado exitosamente.`, 'success');
            if (listItemElement) {
                listItemElement.remove();
            }
            // If the list becomes empty after deletion
            if (indexedFilesList && indexedFilesList.children.length === 0) {
                indexedFilesList.innerHTML = '<li>No hay archivos indexados.</li>';
            }

        } catch (error) {
            console.error('Error deleting file:', error);
            updateStatusManage(`Error al eliminar "${filename}": ${error.message}`, 'error');
        }
    }

    // --- Refresh Files from Moodle & Task Tracking ---
    async function handleRefreshFiles(currentCourseId) {
        if (!refreshMoodleFilesButton) return;
        updateStatusManage('Solicitando actualización de archivos desde Moodle...', 'info');
        refreshMoodleFilesButton.disabled = true;

        try {
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/refresh-files`);
            if (!response.ok) {
                const errorData = await response.json().catch(() => null);
                throw new Error(`Error ${response.status}: ${errorData?.detail || 'No se pudo iniciar la actualización de archivos.'}`);
            }
            const result = await response.json();
            
            updateStatusManage(result.message || 'Proceso de actualización iniciado.', 'success');

            if (result.task_ids && result.task_ids.length > 0) {
                if (processingFilesList && processingFilesList.innerHTML.includes('No hay archivos procesándose actualmente')) {
                    processingFilesList.innerHTML = ''; // Clear "no files" message
                }
                result.task_ids.forEach(taskId => {
                    // We don't have individual filenames here, so use task ID or a generic name
                    const taskDisplayName = `Tarea de procesamiento ${taskId.substring(0,8)}`; 
                    addOrUpdateProcessingFileStatus(taskId, taskDisplayName, 'PENDIENTE');
                    trackTaskProgress(currentCourseId, taskId, taskDisplayName);
                });
            } else if (result.files_identified_for_processing === 0) {
                updateStatusManage('No se identificaron archivos nuevos o modificados para procesar.', 'info');
            }

        } catch (error) {
            console.error('Error refreshing files:', error);
            updateStatusManage(`Error al actualizar archivos: ${error.message}`, 'error');
        } finally {
            if (refreshMoodleFilesButton) refreshMoodleFilesButton.disabled = false;
        }
    }
    
    function addOrUpdateProcessingFileStatus(taskId, displayName, statusText) {
        if (!processingFilesList) return;
        let taskItem = processingFilesList.querySelector(`li[data-task-id="${taskId}"]`);
        if (!taskItem) {
            taskItem = document.createElement('li');
            taskItem.dataset.taskId = taskId;
            if (processingFilesList.firstChild && processingFilesList.firstChild.textContent === 'No hay archivos procesándose actualmente.') {
                processingFilesList.innerHTML = ''; // Clear "No hay archivos"
            }
            processingFilesList.appendChild(taskItem);
        }
        taskItem.textContent = `${displayName}: ${statusText}`;
    }

    function trackTaskProgress(currentCourseId, taskId, displayName) {
        if (activeTasks[taskId]) {
            clearInterval(activeTasks[taskId]); // Clear existing interval if any
        }

        activeTasks[taskId] = setInterval(async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/task/${taskId}/status`);
                if (!response.ok) {
                    // If task status endpoint itself fails, log and stop, but don't assume task failed
                    console.warn(`Advertencia: No se pudo obtener el estado de la tarea ${taskId} (HTTP ${response.status}). Se reintentará.`);
                    addOrUpdateProcessingFileStatus(taskId, displayName, `Error al obtener estado (HTTP ${response.status})`);
                    // Consider stopping after several failed attempts to get status
                    return; 
                }
                const task = await response.json();

                addOrUpdateProcessingFileStatus(taskId, displayName, task.status);

                if (task.status === 'SUCCESS') {
                    clearInterval(activeTasks[taskId]);
                    delete activeTasks[taskId];
                    updateStatusManage(`Procesamiento de '${displayName}' (Tarea ${taskId.substring(0,8)}) completado exitosamente.`, 'success');
                    const taskItem = processingFilesList.querySelector(`li[data-task-id="${taskId}"]`);
                    if (taskItem) taskItem.remove();
                    if (processingFilesList.children.length === 0) {
                        processingFilesList.innerHTML = '<li>No hay archivos procesándose actualmente.</li>';
                    }
                    loadIndexedFiles(currentCourseId); // Refresh indexed files list
                } else if (task.status === 'FAILURE') {
                    clearInterval(activeTasks[taskId]);
                    delete activeTasks[taskId];
                    const errorMessage = task.result || 'Error desconocido.';
                    updateStatusManage(`Error en el procesamiento de '${displayName}' (Tarea ${taskId.substring(0,8)}): ${errorMessage}`, 'error');
                    addOrUpdateProcessingFileStatus(taskId, displayName, `ERROR: ${errorMessage}`);
                    // Keep it in the list with error status, or remove it
                    // const taskItem = processingFilesList.querySelector(`li[data-task-id="${taskId}"]`);
                    // if (taskItem) taskItem.classList.add('error-task'); // Add class for styling
                }
                // Other statuses (PENDING, STARTED, RETRY) will just update the text via addOrUpdateProcessingFileStatus
            } catch (error) {
                console.error(`Error tracking task ${taskId}:`, error);
                // Don't clear interval due to network error, allow retries
                addOrUpdateProcessingFileStatus(taskId, displayName, 'Error de red al verificar estado.');
            }
        }, 3000); // Poll every 3 seconds
    }

    // --- Start ---
    initializePage();
});

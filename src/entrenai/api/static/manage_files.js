document.addEventListener('DOMContentLoaded', async () => {
    const courseNamePlaceholder = document.getElementById('course-name-placeholder');
    const statusMessagesManage = document.getElementById('status-messages-manage');
    const refreshMoodleFilesButton = document.getElementById('refresh-moodle-files-button');
    const indexedFilesList = document.getElementById('indexed-files-list');
    const processingFilesList = document.getElementById('processing-files-list');

    const API_BASE_URL = 'http://localhost:8000/api/v1'; // Adjust if necessary
    let courseId; // Stores the current course ID from URL parameters.
    let activeTasks = {}; // Keeps track of active polling intervals for task progress.

    // Ensure essential DOM elements are present before proceeding.
    if (!courseNamePlaceholder || !statusMessagesManage || !refreshMoodleFilesButton || !indexedFilesList || !processingFilesList) {
        console.error('Error crítico: Faltan elementos del DOM requeridos en manage_files.html. La aplicación no puede iniciarse correctamente.');
        if (statusMessagesManage) { // Attempt to show an error if the status element itself exists
            updateStatusManage('Error de inicialización: Faltan componentes de la página.', 'error');
        }
        return;
    }

    // --- Initialization ---

    /**
     * Initializes the page: retrieves course ID from URL, loads initial data,
     * and sets up event listeners.
     */
    async function initializePage() {
        const params = new URLSearchParams(window.location.search);
        courseId = params.get('course_id');

        if (!courseId) {
            updateStatusManage('Error: No se ha especificado un ID de curso en la URL. Por favor, vuelve a la página principal e inténtalo de nuevo.', 'error');
            disableAllControls();
            return;
        }

        // Display the course ID. Future enhancement: fetch and display course name.
        courseNamePlaceholder.textContent = `ID ${courseId}`;
        
        await loadIndexedFiles(courseId);
        setupEventListeners();
    }

    /**
     * Disables all interactive controls on the page, typically used when a critical error occurs.
     */
    function disableAllControls() {
        if (refreshMoodleFilesButton) refreshMoodleFilesButton.disabled = true;
        // Consider disabling other controls if they are added in the future.
    }

    /**
     * Sets up event listeners for interactive elements on the page.
     */
    function setupEventListeners() {
        if (refreshMoodleFilesButton) {
            refreshMoodleFilesButton.addEventListener('click', () => handleRefreshFiles(courseId));
        }
    }

    // --- Status Updates ---

    /**
     * Displays a status message to the user in the designated status area.
     * @param {string} message - The message to display.
     * @param {string} type - The type of message ('info', 'success', 'warning', 'error').
     * @param {HTMLElement} targetElement - The DOM element where the message should be appended.
     */
    function updateStatusManage(message, type = 'info', targetElement = statusMessagesManage) {
        if (!targetElement) {
            console.error("Target element for status message not found:", message);
            return;
        }
        const p = document.createElement('p');
        p.className = type; // Assumes CSS classes 'info', 'success', 'warning', 'error' are defined.
        p.textContent = message;
        
        // Prepend new message so latest is always at the top.
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
        indexedFilesList.innerHTML = '<li><span class="status-icon spinner"></span>Cargando archivos indexados...</li>';

        try {
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/indexed-files`);
            
            if (!response.ok) {
                if (response.status === 404) {
                    updateStatusManage(`No se encontraron archivos indexados para el curso ${currentCourseId}.`, 'warning');
                    indexedFilesList.innerHTML = '<li>No hay archivos indexados actualmente.</li>';
                } else {
                    let errorDetail = 'No se pudieron cargar los archivos indexados.';
                    try {
                        const errorData = await response.json();
                        errorDetail = errorData.detail || errorDetail;
                    } catch (e) { console.warn('Could not parse error response as JSON:', e); }
                    updateStatusManage(`Error ${response.status}: ${errorDetail}`, 'error');
                    indexedFilesList.innerHTML = '<li>Error al cargar la lista de archivos.</li>';
                }
                return;
            }

            const files = await response.json();
            if (!Array.isArray(files)) {
                console.error("Respuesta inesperada del servidor: la lista de archivos indexados no es un array.", files);
                updateStatusManage("Error: Formato de respuesta incorrecto al cargar archivos indexados.", 'error');
                indexedFilesList.innerHTML = '<li>Error al procesar la lista de archivos.</li>';
                return;
            }

            if (files.length === 0) {
                indexedFilesList.innerHTML = '<li>No hay archivos indexados actualmente.</li>';
                updateStatusManage('No se encontraron archivos procesados para este curso.', 'info');
                return;
            }

            indexedFilesList.innerHTML = ''; // Clear loading/previous messages.
            files.forEach(file => {
                const li = document.createElement('li');
                li.dataset.filename = file.filename; 
                
                const fileNameSpan = document.createElement('span');
                // Format the last_modified_moodle timestamp (assuming it's in seconds).
                const lastModifiedDate = new Date(file.last_modified_moodle * 1000).toLocaleString();
                fileNameSpan.textContent = `${file.filename} (Modificado en Moodle: ${lastModifiedDate})`;
                li.appendChild(fileNameSpan);

                const deleteButton = document.createElement('button');
                deleteButton.textContent = 'Eliminar';
                deleteButton.classList.add('delete-btn');
                deleteButton.addEventListener('click', () => handleDeleteFile(currentCourseId, file.filename, li));
                li.appendChild(deleteButton);
                
                indexedFilesList.appendChild(li);
            });
            updateStatusManage(`Archivos indexados cargados correctamente para el curso ${currentCourseId}.`, 'success');

        } catch (networkError) {
            console.error('Error de red al cargar archivos indexados:', networkError);
            updateStatusManage('Error de red al cargar archivos. Verifica tu conexión e inténtalo de nuevo.', 'error');
            if (indexedFilesList) indexedFilesList.innerHTML = '<li>Error de red al cargar archivos.</li>';
        }
    }

    // --- Delete File ---

    /**
     * Handles the deletion of an indexed file for a given course.
     * Prompts the user for confirmation before proceeding.
     * @param {string} currentCourseId - The ID of the course.
     * @param {string} filename - The name of the file to delete.
     * @param {HTMLElement} listItemElement - The list item element in the DOM to remove on success.
     */
    async function handleDeleteFile(currentCourseId, filename, listItemElement) {
        if (!confirm(`¿Estás seguro de que quieres eliminar el archivo "${filename}" de la IA? Esta acción no se puede deshacer.`)) {
            return;
        }
        updateStatusManage(`Eliminando el archivo "${filename}"...`, 'info');
        try {
            const encodedFilename = encodeURIComponent(filename);
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/indexed-files/${encodedFilename}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                let errorDetail = 'No se pudo eliminar el archivo.';
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch (e) { console.warn('Could not parse error response as JSON for delete operation:', e); }
                updateStatusManage(`Error ${response.status} al eliminar "${filename}": ${errorDetail}`, 'error');
                return;
            }
            
            updateStatusManage(`Archivo "${filename}" eliminado exitosamente de la IA.`, 'success');
            if (listItemElement) {
                listItemElement.remove();
            }
            if (indexedFilesList && indexedFilesList.children.length === 0) {
                indexedFilesList.innerHTML = '<li>No hay archivos indexados actualmente.</li>';
            }

        } catch (networkError) {
            console.error('Error de red al eliminar archivo:', networkError);
            updateStatusManage(`Error de red al eliminar "${filename}". Verifica tu conexión e inténtalo de nuevo.`, 'error');
        }
    }

    // --- Refresh Files from Moodle & Task Tracking ---

    /**
     * Initiates a request to the backend to refresh the list of files from Moodle for the current course.
     * If new files are identified for processing, it starts tracking their progress.
     * @param {string} currentCourseId - The ID of the course.
     */
    async function handleRefreshFiles(currentCourseId) {
        if (!refreshMoodleFilesButton) return;
        
        const originalButtonHTML = refreshMoodleFilesButton.innerHTML; // Store full HTML content
        refreshMoodleFilesButton.disabled = true;
        refreshMoodleFilesButton.innerHTML = '<span class="btn-spinner"></span>Actualizando desde Moodle...';
        updateStatusManage('Solicitando revisión de archivos en Moodle...', 'info');

        try {
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/refresh-files`);
            let result;
            try {
                 result = await response.json();
            } catch (e) {
                console.error('Could not parse refresh-files response as JSON:', e);
                updateStatusManage(`Error inesperado del servidor (código ${response.status}) al revisar archivos.`, 'error');
                // Don't re-enable button immediately if response is totally unparsable, state is unknown
                return;
            }

            if (!response.ok) {
                const errorMessage = `Error ${response.status}: ${result?.detail || 'No se pudo iniciar la actualización de archivos desde Moodle.'}`;
                updateStatusManage(errorMessage, 'error');
                // Consider re-enabling button here if the error is definitive and not a temporary server issue
                // For now, keeping it disabled on API error to prevent repeated failed calls.
                return; 
            }
            
            updateStatusManage(result.message || 'Solicitud de actualización de archivos completada.', 'success');

            if (result.task_ids && result.task_ids.length > 0) {
                // Clear "No hay archivos procesándose" message if it exists and is the only child
                if (processingFilesList && processingFilesList.children.length === 1 && processingFilesList.firstChild.textContent === 'No hay archivos procesándose actualmente.') {
                    processingFilesList.innerHTML = ''; 
                }
                result.task_ids.forEach(taskId => {
                    const taskDisplayName = result.filenames_by_task_id?.[taskId] || `Tarea de procesamiento ${taskId.substring(0,8)}`;
                    addOrUpdateProcessingFileStatus(taskId, taskDisplayName, 'PENDING');
                    trackTaskProgress(currentCourseId, taskId, taskDisplayName);
                });
            } else if (result.files_identified_for_processing === 0) {
                updateStatusManage('No se encontraron archivos nuevos o modificados en Moodle para procesar.', 'info');
            }

        } catch (networkError) {
            console.error('Error de red al solicitar actualización de archivos:', networkError);
            updateStatusManage('Error de red al actualizar archivos. Verifica tu conexión e inténtalo de nuevo.', 'error');
        } finally {
            // Always re-enable the button unless there was a severe, unrecoverable error.
            if (refreshMoodleFilesButton) {
                refreshMoodleFilesButton.disabled = false;
                refreshMoodleFilesButton.innerHTML = originalButtonHTML;
            }
        }
    }
    
    /**
     * Adds or updates a list item in the "Archivos en Procesamiento" list to reflect
     * the status of a file processing task.
     * @param {string} taskId - The ID of the task.
     * @param {string} displayName - The name of the file or task to display.
     * @param {string} status - The current status of the task (e.g., PENDING, PROCESSING, SUCCESS, FAILURE).
     * @param {string|null} resultMessage - An optional message associated with the status (e.g., error details).
     */
    function addOrUpdateProcessingFileStatus(taskId, displayName, status, resultMessage = null) {
        if (!processingFilesList) return;
        let taskItem = processingFilesList.querySelector(`li[data-task-id="${taskId}"]`);
        if (!taskItem) {
            taskItem = document.createElement('li');
            taskItem.dataset.taskId = taskId;
            // Clear "No hay archivos" message if it's the only item
            if (processingFilesList.children.length === 1 && processingFilesList.firstChild.textContent === 'No hay archivos procesándose actualmente.') {
                processingFilesList.innerHTML = '';
            }
            processingFilesList.appendChild(taskItem);
        }

        taskItem.className = ''; // Reset classes for accurate status styling.
        let iconHtml = '<span class="status-icon"></span>'; // Default icon placeholder.
        let statusText = status; // Default to showing the raw status.

        switch (status.toUpperCase()) {
            case 'PENDING':
                taskItem.classList.add('status-pending');
                statusText = 'Pendiente de procesamiento';
                break;
            case 'STARTED': // Often used by Celery
            case 'PROCESSING':
                taskItem.classList.add('status-processing');
                iconHtml = '<span class="status-icon spinner"></span>'; // Visual spinner for active processing.
                statusText = 'Procesando...';
                break;
            case 'SUCCESS':
                // SUCCESS items are typically removed by trackTaskProgress, but this provides a fallback.
                taskItem.classList.add('status-success'); // You might want a temporary success style.
                statusText = 'Completado exitosamente';
                break;
            case 'FAILURE':
                taskItem.classList.add('status-failure');
                statusText = `Error en procesamiento${resultMessage ? `: ${resultMessage}` : ''}`;
                break;
            case 'ERROR_CHECK': // Custom status for when checking task status fails
                 taskItem.classList.add('status-warning'); // Or a specific 'error-check' style
                 statusText = `Advertencia: No se pudo verificar estado (${resultMessage || 'detalle no disponible'})`;
                 break;
            case 'ERROR_NETWORK': // Custom status for network errors during polling
                taskItem.classList.add('status-warning'); // Or a specific 'error-network' style
                statusText = `Advertencia: Error de red al verificar estado (${resultMessage || 'reintentando'})`;
                break;

        }
        taskItem.innerHTML = `${iconHtml}<span class="status-text">${displayName}: ${statusText}</span>`;
    }

    /**
     * Periodically polls the backend for the status of a given task.
     * Updates the task's display in the processing list and handles completion or failure.
     * @param {string} currentCourseId - The ID of the course (for reloading indexed files on success).
     * @param {string} taskId - The ID of the task to track.
     * @param {string} displayName - The display name for the task/file.
     */
    function trackTaskProgress(currentCourseId, taskId, displayName) {
        if (activeTasks[taskId]) { // Clear any existing interval for this task ID.
            clearInterval(activeTasks[taskId]);
        }

        activeTasks[taskId] = setInterval(async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/task/${taskId}/status`);
                let task; 
                try {
                    task = await response.json();
                } catch (e) {
                    // Handle cases where the status endpoint returns non-JSON (e.g. server error page)
                    console.warn(`Respuesta no JSON al obtener estado de tarea ${taskId} (HTTP ${response.status}).`, e);
                    addOrUpdateProcessingFileStatus(taskId, displayName, 'ERROR_CHECK', `Respuesta inesperada del servidor (HTTP ${response.status})`);
                    // Consider stopping polling if this happens repeatedly. For now, it will retry.
                    return;
                }

                if (!response.ok) {
                    const errorDetail = task?.detail || `Error HTTP ${response.status}`;
                    console.warn(`No se pudo obtener el estado de la tarea ${taskId} (${errorDetail}). Se reintentará.`);
                    addOrUpdateProcessingFileStatus(taskId, displayName, 'ERROR_CHECK', errorDetail);
                    return;
                }
                
                // Update the UI with the fetched status.
                addOrUpdateProcessingFileStatus(taskId, displayName, task.status, task.result);

                if (task.status === 'SUCCESS') {
                    clearInterval(activeTasks[taskId]); // Stop polling.
                    delete activeTasks[taskId];
                    updateStatusManage(`Procesamiento de '${displayName}' (Tarea ${taskId.substring(0,8)}) completado.`, 'success');
                    const taskItem = processingFilesList.querySelector(`li[data-task-id="${taskId}"]`);
                    if (taskItem) taskItem.remove(); // Remove from "processing" list.
                    
                    if (processingFilesList.children.length === 0) {
                        processingFilesList.innerHTML = '<li>No hay archivos procesándose actualmente.</li>';
                    }
                    await loadIndexedFiles(currentCourseId); // Refresh the list of indexed files.
                } else if (task.status === 'FAILURE') {
                    clearInterval(activeTasks[taskId]); // Stop polling.
                    delete activeTasks[taskId];
                    const errorMessage = task.result || 'Causa desconocida';
                    updateStatusManage(`Error al procesar '${displayName}' (Tarea ${taskId.substring(0,8)}): ${errorMessage}`, 'error');
                    // The item remains in the processing list with "Fallido" status due to addOrUpdateProcessingFileStatus.
                }
                // For PENDING, STARTED, RETRY statuses, the UI is updated by addOrUpdateProcessingFileStatus, and polling continues.
            } catch (networkError) { // Catch network errors related to the fetch itself.
                console.error(`Error de red al rastrear tarea ${taskId}:`, networkError);
                addOrUpdateProcessingFileStatus(taskId, displayName, 'ERROR_NETWORK', 'Error de conexión');
                // Polling continues, as network issues might be temporary.
            }
        }, 3000); // Poll for status every 3 seconds.
    }

    // --- Start ---
    // Initialize the page as soon as the DOM is fully loaded.
    initializePage().catch(error => {
        console.error("Error crítico durante la inicialización de la página de gestión de archivos:", error);
        updateStatusManage("Ocurrió un error grave al cargar la página. Por favor, recarga.", "error");
    });
});

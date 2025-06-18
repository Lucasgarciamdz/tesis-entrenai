document.addEventListener('DOMContentLoaded', async () => {
    const courseNamePlaceholder = document.getElementById('course-name-placeholder');
    // El contenedor de mensajes ahora es #status-messages-manage-container
    const statusMessagesContainer = document.getElementById('status-messages-manage-container'); 
    const refreshMoodleFilesButton = document.getElementById('refresh-moodle-files-button');
    const refreshButtonSpinner = refreshMoodleFilesButton ? refreshMoodleFilesButton.querySelector('.btn-spinner') : null;
    
    // Elementos de la nueva tabla
    const filesTableBody = document.getElementById('files-table-body');
    const noFilesMessage = document.getElementById('no-files-message');


    const API_BASE_URL = 'http://localhost:8000/api/v1'; // Adjust if necessary
    let courseId; // Stores the current course ID from URL parameters.
    let courseDisplayName = ''; // Para guardar el nombre del curso
    // activeTasks almacenará objetos con: { pollIntervalId, animationFrameId, simulatedProgress, realStatus, filename }
    let activeTasks = {}; 
    let taskQueue = []; // Cola para taskIds que se procesarán secuencialmente
    let isCurrentlyProcessing = false; // Flag para evitar múltiples procesamientos simultáneos desde la cola
    let isPageVisible = true; // Flag para controlar polling cuando la página no está visible

    // Ensure essential DOM elements are present before proceeding.
    if (!courseNamePlaceholder || !statusMessagesContainer || !refreshMoodleFilesButton || !filesTableBody || !noFilesMessage) {
        console.error('Error crítico: Faltan elementos del DOM requeridos en manage_files.html. La aplicación no puede iniciarse correctamente.');
        if (statusMessagesContainer) { 
            updateStatusManage('Error de inicialización: Faltan componentes clave de la página.', 'error');
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
            updateStatusManage('Error: No se ha especificado un ID de curso. Vuelve al Panel de Control.', 'danger');
            disableAllControls();
            if (filesTableBody) filesTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">ID de curso no especificado.</td></tr>`;
            if (noFilesMessage) noFilesMessage.classList.remove('d-none');
            return;
        }
        
        // Intentar obtener y mostrar el nombre del curso
        await fetchCourseDetails(courseId); 
        
        await loadAndDisplayFiles(courseId); // Carga combinada de archivos indexados y en proceso
        setupEventListeners();
    }

    async function fetchCourseDetails(currentCourseId) {
        try {
            // Asumimos que tienes un endpoint para obtener detalles del curso, incluyendo el nombre.
            // Si no, al menos mantenemos el ID.
            // Este es un ejemplo, ajusta el endpoint según tu API.
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}`); // O un endpoint general de cursos y filtrar
            if (response.ok) {
                const courseData = await response.json(); // Suponiendo que devuelve { id, displayname, ... }
                // Si es un array de cursos, busca el específico
                let foundCourse = Array.isArray(courseData) ? courseData.find(c => c.id == currentCourseId) : courseData;

                if (foundCourse && (foundCourse.displayname || foundCourse.fullname)) {
                    courseDisplayName = foundCourse.displayname || foundCourse.fullname;
                    courseNamePlaceholder.textContent = courseDisplayName;
                } else {
                    courseNamePlaceholder.textContent = `ID ${currentCourseId}`;
                }
            } else {
                console.warn(`No se pudo obtener el nombre del curso ${currentCourseId}. Mostrando ID.`);
                courseNamePlaceholder.textContent = `ID ${currentCourseId}`;
            }
        } catch (error) {
            console.error('Error al obtener detalles del curso:', error);
            courseNamePlaceholder.textContent = `ID ${currentCourseId}`;
        }
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
    function updateStatusManage(message, type = 'info') {
        if (!statusMessagesContainer) return;
        const alertType = type === 'error' ? 'danger' : type; // Map to Bootstrap alert class

        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${alertType} alert-dismissible fade show`;
        alertDiv.setAttribute('role', 'alert');
        
        let iconClass = '';
        if (alertType === 'success') iconClass = '✅ ';
        else if (alertType === 'danger') iconClass = '❗ ';
        else if (alertType === 'warning') iconClass = '⚠️ ';
        else if (alertType === 'info') iconClass = 'ℹ️ ';

        alertDiv.innerHTML = `
            <span class="alert-icon">${iconClass}</span>
            ${message}
            <button type="button" class="btn-close" style="background: none; border: none; font-size: 1.2rem; float: right; cursor: pointer; line-height: 1;" aria-label="Close">&times;</button>
        `;
        
        statusMessagesContainer.prepend(alertDiv);

        const autoDismissTimer = setTimeout(() => {
            alertDiv.style.transition = 'opacity 0.5s ease';
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 500);
        }, 7000); // Longer display for manage page

        alertDiv.querySelector('.btn-close').addEventListener('click', () => {
            clearTimeout(autoDismissTimer);
            alertDiv.style.transition = 'opacity 0.5s ease';
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 500);
        });

        while (statusMessagesContainer.children.length > 5) {
            statusMessagesContainer.removeChild(statusMessagesContainer.lastChild);
        }
    }

    // --- Load and Display Files (Combined Logic) ---
    async function loadAndDisplayFiles(currentCourseId) {
        if (!filesTableBody || !noFilesMessage) return;
        
        updateStatusManage(`Cargando archivos para el curso ID ${currentCourseId}...`, 'info');
        filesTableBody.innerHTML = `<tr><td colspan="5" class="text-center p-3"><span class="btn-spinner"></span> Cargando...</td></tr>`;
        noFilesMessage.classList.add('d-none');

        try {
            // Fetch indexed files
            const indexedResponse = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/indexed-files`);
            let indexedFiles = [];
            if (indexedResponse.ok) {
                indexedFiles = await indexedResponse.json();
                if (!Array.isArray(indexedFiles)) indexedFiles = [];
            } else if (indexedResponse.status !== 404) { // 404 is fine (no files), other errors are not
                const errorData = await indexedResponse.json().catch(() => ({}));
                updateStatusManage(`Error ${indexedResponse.status} al cargar archivos indexados: ${errorData.detail || 'Error desconocido'}`, 'danger');
            }
            
            // Fetch processing tasks (if your backend provides such an endpoint)
            // For now, we'll rely on refresh-files to populate processing tasks.
            // Or, if tasks are stored and can be queried by course_id:
            // const processingResponse = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/processing-tasks`);
            // let processingTasks = []; // Populate this if you have an endpoint

            renderFilesTable(indexedFiles, []); // Pass empty array for processing tasks for now

            if (indexedFiles.length === 0 /* && processingTasks.length === 0 */) {
                noFilesMessage.classList.remove('d-none');
                filesTableBody.innerHTML = ''; // Clear loading spinner
                updateStatusManage('No se encontraron archivos para este curso.', 'info');
            } else {
                updateStatusManage(`Archivos cargados para el curso ${currentCourseId}.`, 'success');
            }

        } catch (networkError) {
            console.error('Error de red al cargar archivos:', networkError);
            updateStatusManage('Error de red al cargar archivos. Verifica tu conexión.', 'danger');
            filesTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error de red al cargar archivos.</td></tr>`;
            noFilesMessage.classList.remove('d-none');
        }
    }
    
    function renderFilesTable(indexedFiles, processingTasks) {
        if (!filesTableBody || !noFilesMessage) return;
        filesTableBody.innerHTML = ''; // Clear previous content or loading message
        noFilesMessage.classList.add('d-none');

        let allFileEntries = [];

        indexedFiles.forEach(file => {
            allFileEntries.push({
                name: file.filename,
                status: 'Indexado',
                progress: 100,
                lastModified: file.last_modified_moodle ? new Date(file.last_modified_moodle * 1000).toLocaleString() : 'N/A',
                rawLastModified: file.last_modified_moodle,
                actions: [{ type: 'delete', filename: file.filename }]
            });
        });

        processingTasks.forEach(task => {
            // This part assumes `task` object structure from your backend
            // e.g., { taskId, filename, status ('PENDING', 'PROCESSING'), progressPercent }
            allFileEntries.push({
                name: task.filename || `Tarea ${task.taskId.substring(0,8)}`,
                status: task.status, // PENDING, PROCESSING, etc.
                progress: task.progressPercent || (task.status === 'PROCESSING' ? null : 0), // null for indeterminate progress bar
                lastModified: 'N/A', // Or task creation time
                actions: [], // No actions while processing, or maybe "cancel"
                taskId: task.taskId
            });
        });
        
        if (allFileEntries.length === 0) {
            noFilesMessage.classList.remove('d-none');
            return;
        }

        // Sort files: by status (processing first), then by name or date
        allFileEntries.sort((a, b) => {
            const statusOrder = { 'PROCESSING': 0, 'PENDING': 1, 'Indexado': 2, 'FAILURE': 3 };
            const statusA = statusOrder[a.status] ?? 99;
            const statusB = statusOrder[b.status] ?? 99;
            if (statusA !== statusB) return statusA - statusB;
            return (b.rawLastModified || 0) - (a.rawLastModified || 0); // Newest first for indexed
        });


        allFileEntries.forEach(entry => {
            const row = filesTableBody.insertRow();
            row.dataset.fileName = entry.name; // For easier selection if needed
            if (entry.taskId) row.dataset.taskId = entry.taskId;

            row.insertCell().textContent = entry.name;
            
            const statusCell = row.insertCell();
            renderStatusIndicator(statusCell, entry.status, entry.taskId);

            const progressCell = row.insertCell();
            renderProgressBar(progressCell, entry.status, entry.progress);
            
            row.insertCell().textContent = entry.lastModified;
            
            const actionsCell = row.insertCell();
            entry.actions.forEach(action => {
                if (action.type === 'delete') {
                    const deleteButton = document.createElement('button');
                    deleteButton.textContent = 'Eliminar';
                    deleteButton.classList.add('btn', 'btn-sm', 'btn-danger');
                    deleteButton.addEventListener('click', () => handleDeleteFile(courseId, action.filename, row));
                    actionsCell.appendChild(deleteButton);
                }
                // Add other actions here if needed
            });
        });
    }

    function renderStatusIndicator(cell, status, taskId = null) {
        let statusText = status;
        let statusClass = '';
        let icon = '';

        switch (status.toUpperCase()) {
            case 'INDEXADO': statusText = 'Indexado'; statusClass = 'status-success'; icon = '✅'; break;
            case 'PENDING': statusText = 'Pendiente'; statusClass = 'status-warning'; icon = '🕒'; break;
            case 'STARTED':
            case 'PROCESSING': 
                statusText = 'Procesando'; statusClass = 'status-processing'; 
                // Spinner will be handled by progress bar or a dedicated class
                break;
            case 'FAILURE': statusText = 'Error'; statusClass = 'status-danger'; icon = '❌'; break;
            default: statusText = status; statusClass = 'status-info'; icon = 'ℹ️'; break;
        }
        
        cell.innerHTML = `<span class="status-indicator ${statusClass}">
                            ${status.toUpperCase() === 'PROCESSING' && !taskId ? '<span class="btn-spinner" style="width:0.8em; height:0.8em; border-width:1.5px; margin-right: 0.3em;"></span>' : `<span class="status-indicator-icon">${icon}</span>`}
                            ${statusText}
                          </span>`;
    }

    function renderProgressBar(cell, status, progressPercent) {
        const upperStatus = status.toUpperCase();
        
        if (upperStatus === 'PROCESSING' || upperStatus === 'STARTED' || upperStatus === 'PENDING') {
            // Usar progressPercent para la simulación, si está disponible y es un número
            const displayPercent = (typeof progressPercent === 'number' && progressPercent >= 0 && progressPercent <= 100) ? progressPercent : 0;
            // Si es una simulación activa (no 0 y no 100), o si es indeterminado (progressPercent es null)
            const isSimulating = (displayPercent > 0 && displayPercent < 99); 
                                    // O si queremos que la barra indeterminada sea 100% width con animación:
                                    // const barWidth = (progressPercent === null || progressPercent === undefined) ? 100 : displayPercent;
            const barWidth = displayPercent;


            cell.innerHTML = `
                <div class="progress" style="height: 1.2em;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: ${barWidth}%" aria-valuenow="${barWidth}" aria-valuemin="0" aria-valuemax="100">${isSimulating ? barWidth + '%' : ''}</div>
                </div>`;
        } else if (upperStatus === 'INDEXADO' || upperStatus === 'SUCCESS') {
             cell.innerHTML = `
                <div class="progress" style="height: 1.2em;">
                    <div class="progress-bar bg-success" role="progressbar" style="width: 100%" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100"></div>
                </div>`;
        } else if (upperStatus === 'FAILURE') {
            cell.innerHTML = `
                <div class="progress" style="height: 1.2em;">
                    <div class="progress-bar bg-danger" role="progressbar" style="width: 100%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                </div>`;
        } else {
            cell.textContent = 'N/A';
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
    async function handleDeleteFile(currentCourseId, filename, tableRowElement) {
        if (!confirm(`¿Estás seguro de que quieres eliminar el archivo "${filename}" de la IA? Esta acción no se puede deshacer.`)) {
            return;
        }
        updateStatusManage(`Eliminando el archivo "${filename}"...`, 'info');
        // Optionally, disable the delete button on the row
        const deleteButton = tableRowElement.querySelector('.btn-danger');
        if (deleteButton) deleteButton.disabled = true;
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
            if (tableRowElement) {
                tableRowElement.remove();
            }
            if (filesTableBody && filesTableBody.rows.length === 0) {
                noFilesMessage.classList.remove('d-none');
            }
            // TODO: Potentially update dashboard stats if they are displayed on this page or fetched globally

        } catch (networkError) {
            console.error('Error de red al eliminar archivo:', networkError);
            updateStatusManage(`Error de red al eliminar "${filename}". Verifica tu conexión e inténtalo de nuevo.`, 'danger');
            if (deleteButton) deleteButton.disabled = false; // Re-enable on error
        }
    }

    // --- Refresh Files from Moodle & Task Tracking ---

    async function handleRefreshFiles(currentCourseId) {
        if (!refreshMoodleFilesButton || !refreshButtonSpinner) return;
        
        refreshMoodleFilesButton.disabled = true;
        refreshButtonSpinner.classList.remove('d-none');
        updateStatusManage('Solicitando revisión de archivos en Moodle...', 'info');

        try {
            const response = await fetch(`${API_BASE_URL}/courses/${currentCourseId}/refresh-files`);
            let result;
            try {
                 result = await response.json();
            } catch (e) {
                console.error('Could not parse refresh-files response as JSON:', e);
                updateStatusManage(`Error inesperado del servidor (código ${response.status}) al revisar archivos.`, 'danger');
                return; // Keep button disabled, state is unknown
            }

            if (!response.ok) {
                const errorMessage = `Error ${response.status}: ${result?.detail || 'No se pudo iniciar la actualización de archivos.'}`;
                updateStatusManage(errorMessage, 'danger');
                return; // Keep button disabled on API error
            }
            
            updateStatusManage(result.message || 'Solicitud de actualización de archivos completada.', 'success');

            if (result.task_ids && result.task_ids.length > 0) {
                noFilesMessage.classList.add('d-none'); // Hide "no files" message
                
                result.task_ids.forEach(taskId => {
                    const taskFilename = result.filenames_by_task_id?.[taskId] || `Tarea ${taskId.substring(0,8)}`;
                    if (!taskQueue.find(t => t.taskId === taskId) && !activeTasks[taskId]) {
                        taskQueue.push({ taskId, filename: taskFilename });
                        // Añadir a la tabla con estado 'En Cola' o 'Pendiente'
                        addOrUpdateFileInTable(taskId, taskFilename, 'PENDING', 0); 
                    }
                });
                processNextInQueue(currentCourseId); // Intenta procesar la siguiente tarea de la cola
            } else if (result.files_identified_for_processing === 0) {
                updateStatusManage('No se encontraron archivos nuevos o modificados en Moodle para procesar.', 'info');
            }

        } catch (networkError) {
            console.error('Error de red al solicitar actualización de archivos:', networkError);
            updateStatusManage('Error de red al actualizar archivos. Verifica tu conexión.', 'danger');
        } finally {
            if (refreshMoodleFilesButton && refreshButtonSpinner) {
                refreshMoodleFilesButton.disabled = false;
                refreshButtonSpinner.classList.add('d-none');
            }
        }
    }
    
    function addOrUpdateFileInTable(taskId, filename, status, progressPercent, resultMessage = null, lastModified = 'N/A') {
        if (!filesTableBody) return;
        let row = filesTableBody.querySelector(`tr[data-task-id="${taskId}"]`);
        
        if (!row) { // If task row doesn't exist, create it
            // Check if a row for this filename (as an indexed file) exists
            let existingFileRow = filesTableBody.querySelector(`tr[data-file-name="${filename}"]`);
            if (existingFileRow && status.toUpperCase() !== 'INDEXADO') {
                // If an indexed file is now being re-processed, update its row
                row = existingFileRow;
                row.dataset.taskId = taskId; // Add taskId to it
            } else if (existingFileRow && status.toUpperCase() === 'INDEXADO') {
                // If we are trying to add an indexed file that's already there, just update it
                row = existingFileRow;
            }
            else {
                row = filesTableBody.insertRow(0); // Insert new tasks at the top
                row.dataset.taskId = taskId;
                row.dataset.fileName = filename; // Also store filename for consistency
                row.insertCell(); // Filename
                row.insertCell(); // Status
                row.insertCell(); // Progress
                row.insertCell(); // Last Modified
                row.insertCell(); // Actions
            }
        }

        row.cells[0].textContent = filename;
        renderStatusIndicator(row.cells[1], status, taskId);
        renderProgressBar(row.cells[2], status, progressPercent);
        row.cells[3].textContent = (status.toUpperCase() === 'INDEXADO' && lastModified !== 'N/A') ? lastModified : (row.cells[3].textContent || 'N/A'); // Keep existing if not indexed

        // Clear and set actions
        row.cells[4].innerHTML = '';
        if (status.toUpperCase() === 'INDEXADO') {
            const deleteButton = document.createElement('button');
            deleteButton.textContent = 'Eliminar';
            deleteButton.classList.add('btn', 'btn-sm', 'btn-danger');
            deleteButton.addEventListener('click', () => handleDeleteFile(courseId, filename, row));
            row.cells[4].appendChild(deleteButton);
        } else if (status.toUpperCase() === 'FAILURE') {
            // Optionally add a "Retry" button or "View Log"
            const errorText = document.createElement('span');
            errorText.textContent = resultMessage || 'Fallo';
            errorText.className = 'text-danger';
            row.cells[4].appendChild(errorText);
        }
        
        // If it was a "no files" message row, remove it
        if (noFilesMessage && !noFilesMessage.classList.contains('d-none')) {
            noFilesMessage.classList.add('d-none');
        }
         if (filesTableBody.rows.length === 1 && filesTableBody.rows[0].cells[0].colSpan === 5) { // Is loading row
            filesTableBody.innerHTML = ''; // Clear loading row before adding actual data
            // Re-add the current row as it was cleared
            filesTableBody.appendChild(row);
        }
    }

    function trackTaskProgress(currentCourseId, taskId, filename) {
        // Inicializar la tarea sin polling
        activeTasks[taskId] = {
            filename: filename,
            realStatus: 'PROCESSING'
        };

        // Mostrar estado de procesamiento inicial
        addOrUpdateFileInTable(taskId, filename, 'PROCESSING', 25);

        // Primera consulta después de 30 segundos
        setTimeout(async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/task/${taskId}/status`);
                const data = await response.json();
                
                if (response.ok) {
                    const displayFilename = data.filename || filename;
                    
                    if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
                        handleTaskCompletion(taskId, displayFilename, data, currentCourseId);
                    } else {
                        // Si aún está procesando, actualizar progreso y hacer una consulta final
                        addOrUpdateFileInTable(taskId, displayFilename, 'PROCESSING', 50);
                        
                        // Consulta final después de 90 segundos
                        setTimeout(async () => {
                            try {
                                const finalResponse = await fetch(`${API_BASE_URL}/task/${taskId}/status`);
                                const finalData = await finalResponse.json();
                                
                                if (finalResponse.ok) {
                                    const finalDisplayFilename = finalData.filename || filename;
                                    handleTaskCompletion(taskId, finalDisplayFilename, finalData, currentCourseId);
                                }
                            } catch (error) {
                                console.error(`Error en consulta final de tarea ${taskId}:`, error);
                                handleTaskCompletion(taskId, filename, { status: 'FAILURE', result: 'Error de conexión' }, currentCourseId);
                            }
                        }, 60000); // 60 segundos más (total 90 segundos)
                    }
                }
            } catch (error) {
                console.error(`Error consultando tarea ${taskId}:`, error);
                handleTaskCompletion(taskId, filename, { status: 'FAILURE', result: 'Error de conexión' }, currentCourseId);
            }
        }, 30000); // Primera consulta a los 30 segundos
    }

    function handleTaskCompletion(taskId, displayFilename, data, currentCourseId) {
        const progress = data.status === 'SUCCESS' ? 100 : 0;
        addOrUpdateFileInTable(taskId, displayFilename, data.status, progress, data.result);
        
        if (data.status === 'SUCCESS') {
            updateStatusManage(`Procesamiento de '${displayFilename}' completado.`, 'success');
            setTimeout(() => {
                addOrUpdateFileInTable(taskId, displayFilename, 'INDEXADO', 100, null, new Date().toLocaleString());
            }, 1000);
        } else {
            updateStatusManage(`Error al procesar '${displayFilename}': ${data.result || 'Error desconocido'}`, 'danger');
        }
        
        delete activeTasks[taskId];
        isCurrentlyProcessing = false;
        processNextInQueue(currentCourseId);
    }

    function startProgressSimulation(taskId, filename) {
        // Simplificado: solo mostrar estado de procesamiento
        if (!activeTasks[taskId]) {
            activeTasks[taskId] = { 
                realStatus: 'PROCESSING', 
                filename: filename
            };
        }
        
        // Mostrar progreso fijo del 50%
        addOrUpdateFileInTable(taskId, filename, 'PROCESSING', 50);
    }

    function processNextInQueue(currentCourseId) {
        if (isCurrentlyProcessing || taskQueue.length === 0) {
            return; // No procesar si ya hay algo o la cola está vacía
        }

        isCurrentlyProcessing = true;
        const nextTask = taskQueue.shift(); // Tomar el primer elemento
        
        if (nextTask) {
            const { taskId, filename } = nextTask;
            // Asegurar que la tarea no esté ya activa de alguna forma (aunque isCurrentlyProcessing debería prevenirlo)
            if (activeTasks[taskId]) {
                console.warn(`Intento de procesar tarea ${taskId} que ya está en activeTasks.`);
                isCurrentlyProcessing = false; 
                processNextInQueue(currentCourseId); // Intentar con la siguiente
                return;
            }

            updateStatusManage(`Iniciando procesamiento para: ${filename}`, 'info');
            // Marcar como 'PROCESSING' en la tabla y comenzar simulación y polling
            addOrUpdateFileInTable(taskId, filename, 'PROCESSING', 0); // Inicia progreso en 0
            startProgressSimulation(taskId, filename);
            trackTaskProgress(currentCourseId, taskId, filename);
        } else {
            isCurrentlyProcessing = false; // No había nada que procesar
        }
    }

    // --- Gestión de visibilidad de página (simplificada) ---
    document.addEventListener('visibilitychange', () => {
        isPageVisible = !document.hidden;
        console.log(isPageVisible ? 'Página visible' : 'Página oculta');
    });

    // --- Start ---
    initializePage().catch(error => {
        console.error("Error crítico durante la inicialización de la página de gestión de archivos:", error);
        updateStatusManage("Ocurrió un error grave al cargar la página. Por favor, recarga.", "error");
    });
});

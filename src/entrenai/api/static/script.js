document.addEventListener('DOMContentLoaded', () => {
    const courseSelect = document.getElementById('course-select');
    const setupAiButton = document.getElementById('setup-ai-button');
    // El contenedor de mensajes de estado ahora es #status-messages-container
    const statusMessagesContainer = document.getElementById('status-messages-container'); 
    const manageFilesButton = document.getElementById('manage-files-button'); // Get the button
    const setupAiButtonSpinner = setupAiButton ? setupAiButton.querySelector('.btn-spinner') : null;

    let allCourses = []; // Para guardar la lista completa de cursos

    // URL base de tu API FastAPI (ajusta si es necesario)
    // Si FastAPI sirve este HTML, una ruta relativa podría funcionar: '/api/v1'
    // Si se abre como file:// o desde otro servidor, se necesita la URL completa y CORS.
    const API_BASE_URL = 'http://localhost:8000';

    // Get additional DOM elements for manual input
    const manualCourseInput = document.getElementById('manual-course-input');
    const manualCourseId = document.getElementById('manual-course-id');
    const toggleManualButton = document.getElementById('toggle-manual-input');

    // Ensure essential DOM elements are present before proceeding.
    if (!courseSelect || !setupAiButton || !statusMessagesContainer || !manageFilesButton) {
        console.error('Error crítico: Faltan elementos del DOM requeridos en index.html. La aplicación no puede iniciarse correctamente.');
        if (statusMessagesContainer) { // Usar el nuevo contenedor
            updateStatus('Error de inicialización: Faltan componentes de la página.', 'error');
        }
        return;
    }

    /**
     * Tests API connectivity before attempting to load courses
     */
    async function testApiConnectivity() {
        try {
            const response = await fetch(`${API_BASE_URL}/health`, {
                method: 'GET',
                timeout: 5000
            });
            return response.ok;
        } catch (error) {
            console.warn('API connectivity test failed:', error);
            return false;
        }
    }

    /**
     * Fetches the list of courses from the Moodle API.
     * Populates the course selection dropdown upon successful retrieval.
     */
    async function fetchCourses() {
        updateStatus('Cargando cursos disponibles desde Moodle...', 'info');
        // Actualizar estadísticas (ejemplo, podrías tener endpoints específicos para esto)
        document.getElementById('stat-cursos-configurados').textContent = '...';
        document.getElementById('stat-archivos-procesados').textContent = '...';
        document.getElementById('stat-archivos-en-proceso').textContent = '...';
        document.getElementById('stat-estado-moodle').textContent = 'Verificando...';

        // Create an AbortController to handle timeouts
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

        try {
            // This endpoint typically uses a default Moodle teacher ID if `moodle_user_id` is not provided.
            const response = await fetch(`${API_BASE_URL}/api/v1/courses`, {
                signal: controller.signal
            });
            
            clearTimeout(timeoutId); // Clear timeout if request succeeds

            if (!response.ok) {
                let errorDetail = `Error ${response.status}: No se pudieron cargar los cursos.`;
                try {
                    // Attempt to get more specific error detail from the response body.
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch (e) {
                    // If the error response isn't JSON, use the generic HTTP error.
                    console.warn('Could not parse error response as JSON:', e);
                }
                updateStatus(errorDetail, 'error');
                courseSelect.innerHTML = '<option value="">Error al cargar cursos</option>'; // Provide feedback in select
                return;
            }

            const coursesData = await response.json();
            if (!Array.isArray(coursesData)) {
                console.error("Respuesta inesperada del servidor: la lista de cursos no es un array.", coursesData);
                allCourses = []; // Reset to prevent errors with non-array data.
                updateStatus("Error: Formato de respuesta de cursos incorrecto.", 'error');
                courseSelect.innerHTML = '<option value="">Error al procesar cursos</option>';
                return;
            }
            
            allCourses = coursesData; // Store for later use (e.g., getting course name).
            populateCourseSelect(allCourses);

            if (allCourses.length > 0) {
                updateStatus('Cursos cargados exitosamente. Por favor, selecciona un curso para continuar.', 'success');
                // Simulación de actualización de estadísticas
                document.getElementById('stat-cursos-configurados').textContent = allCourses.filter(c => c.is_ai_configured).length; // Suponiendo que tienes esta info
                document.getElementById('stat-estado-moodle').textContent = 'Conectado'; // O basado en la respuesta
            } else {
                updateStatus('No se encontraron cursos disponibles para el usuario configurado en Moodle.', 'warning');
                document.getElementById('stat-estado-moodle').textContent = 'Sin cursos';
            }
        } catch (networkError) {
            clearTimeout(timeoutId); // Clear timeout if request fails
            console.error('Error de red al cargar cursos:', networkError);
            
            let errorMessage = 'Error de red al cargar cursos. Verifica tu conexión e inténtalo de nuevo.';
            let statusText = 'Error de Red';
            
            if (networkError.name === 'AbortError') {
                errorMessage = 'Timeout al cargar cursos. El servidor de Moodle puede estar inaccesible. Puedes usar el modo manual para continuar.';
                statusText = 'Timeout';
            }
            
            updateStatus(errorMessage, 'error');
            courseSelect.innerHTML = '<option value="">Error al cargar cursos</option>';
            document.getElementById('stat-estado-moodle').textContent = statusText;
            
            // Show a suggestion to use manual mode
            setTimeout(() => {
                updateStatus('💡 Sugerencia: Usa el botón "Usar ID de curso manual" si conoces el ID del curso.', 'info');
            }, 3000);
        }
    }

    /**
     * Populates the course select dropdown with the given list of courses.
     * @param {Array} courses - An array of course objects from the API.
     */
    function populateCourseSelect(courses) {
        courseSelect.innerHTML = ''; // Clear previous options, including any error messages.
        if (courses.length === 0) {
            courseSelect.innerHTML = '<option value="">No hay cursos disponibles</option>';
            return;
        }
        
        const defaultOption = document.createElement('option');
        defaultOption.value = "";
        defaultOption.textContent = "-- Selecciona un curso --";
        courseSelect.appendChild(defaultOption);

        courses.forEach(course => {
            const option = document.createElement('option');
            option.value = course.id;
            // Usar displayname si está disponible, sino fullname
            const displayName = course.displayname || course.fullname;
            option.textContent = `${displayName} (ID: ${course.id})`;
            courseSelect.appendChild(option);
        });
    }

    // The orphaned courseSearchInput.addEventListener block has been removed.

    if (courseSelect) {
        courseSelect.addEventListener('change', () => {
            if (courseSelect.value && manageFilesButton) {
                manageFilesButton.style.display = 'block'; // Show the button
            } else if (manageFilesButton) {
                manageFilesButton.style.display = 'none'; // Hide the button
            }
        });
    }
    
    // Also listen for manual input changes
    if (manualCourseId && manageFilesButton) {
        manualCourseId.addEventListener('input', () => {
            if (manualCourseId.value && manageFilesButton) {
                manageFilesButton.style.display = 'block'; // Show the button
            } else if (manageFilesButton) {
                manageFilesButton.style.display = 'none'; // Hide the button
            }
        });
    }

    if (manageFilesButton) {
      manageFilesButton.addEventListener('click', () => {
        const selectedCourseId = getSelectedCourseId();
        if (selectedCourseId) {
          // Navigate to the manage_files.html page with the course_id as a query parameter
          window.location.href = `/ui/manage_files.html?course_id=${selectedCourseId}`;
        } else {
          updateStatus('Por favor, selecciona un curso primero antes de gestionar archivos.', 'warning');
        }
      });
    }

    setupAiButton.addEventListener('click', async () => {
        const selectedCourseId = getSelectedCourseId();
        if (!selectedCourseId) {
            updateStatus('Por favor, selecciona un curso primero.', 'warning');
            return;
        }

        const selectedCourse = getSelectedCourse();
        if (!selectedCourse) {
            updateStatus('El curso seleccionado no es válido o no se encontró en la lista.', 'error');
            return;
        }
        
        const courseDisplayName = selectedCourse.displayname || selectedCourse.fullname;
        updateStatus(`Iniciando configuración de IA para el curso: "${courseDisplayName}" (ID: ${selectedCourseId})... Esto puede tardar unos minutos. Por favor, espera.`, 'info');
        
        // Disable controls and show spinner
        setupAiButton.disabled = true;
        if (setupAiButtonSpinner) setupAiButtonSpinner.classList.remove('d-none');
        courseSelect.disabled = true;
        if(manageFilesButton) manageFilesButton.disabled = true;


        try {
            // Add timeout to setup-ia request as it can take a long time
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 120000); // 2 minute timeout

            // The backend endpoint expects 'courseName' as a query parameter, used as an alias for 'course_name_query'.
            const response = await fetch(`${API_BASE_URL}/api/v1/courses/${selectedCourseId}/setup-ia?courseName=${encodeURIComponent(courseDisplayName)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json' // Though body is not sent, this header is good practice for POST.
                },
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            let result;
            try {
                result = await response.json();
            } catch (e) {
                // If response is not JSON (e.g. plain text error from a proxy or server error page)
                console.error('Could not parse setup AI response as JSON:', e);
                updateStatus(`Error inesperado del servidor durante la configuración. Código: ${response.status}`, 'error');
                return; // Exit early
            }

            if (!response.ok) {
                // Use the detail from JSON if available, otherwise provide a generic error.
                updateStatus(result.detail || `Error ${response.status}: Falló la configuración de la IA para "${courseDisplayName}".`, 'error');
                return;
            }
            
            updateStatus(`Configuración de IA para "${courseDisplayName}" completada exitosamente: ${result.message}`, 'success');
        } catch (networkError) {
            clearTimeout(timeoutId); // Clear timeout if request fails
            console.error('Error de red durante la configuración de IA:', networkError);
            
            let errorMessage = `Error de red al configurar IA para "${courseDisplayName}". Verifica tu conexión e inténtalo de nuevo.`;
            if (networkError.name === 'AbortError') {
                errorMessage = `Timeout al configurar IA para "${courseDisplayName}". La operación está tomando demasiado tiempo.`;
            }
            
            updateStatus(errorMessage, 'error');
        } finally {
            // Re-enable controls and hide spinner
            setupAiButton.disabled = false;
            if (setupAiButtonSpinner) setupAiButtonSpinner.classList.add('d-none');
            courseSelect.disabled = false;
            if(manageFilesButton) manageFilesButton.disabled = false;
        }
    });

    // Toggle manual input mode
    if (toggleManualButton && manualCourseInput) {
        toggleManualButton.addEventListener('click', () => {
            const isHidden = manualCourseInput.style.display === 'none';
            manualCourseInput.style.display = isHidden ? 'block' : 'none';
            toggleManualButton.textContent = isHidden ? 'Usar lista de cursos' : 'Usar ID de curso manual';
            
            if (isHidden) {
                // Hide the course select when using manual input
                courseSelect.parentElement.style.display = 'none';
            } else {
                // Show the course select when not using manual input
                courseSelect.parentElement.style.display = 'block';
            }
        });
    }

    // Helper function to get selected course ID (from dropdown or manual input)
    function getSelectedCourseId() {
        if (manualCourseInput && manualCourseInput.style.display !== 'none') {
            return manualCourseId ? manualCourseId.value : null;
        }
        return courseSelect.value;
    }

    // Helper function to get selected course info
    function getSelectedCourse() {
        const selectedId = getSelectedCourseId();
        if (!selectedId) return null;
        
        if (manualCourseInput && manualCourseInput.style.display !== 'none') {
            // Return a fake course object for manual input
            return { id: parseInt(selectedId), fullname: `Curso ${selectedId}` };
        }
        
        return allCourses.find(c => c.id == selectedId);
    }

    /**
     * Displays a status message to the user using the new alert-style messages.
     * @param {string} message - The message to display.
     * @param {string} type - The type of message ('info', 'success', 'warning', 'danger' for error).
     */
    function updateStatus(message, type = 'info') {
        if (!statusMessagesContainer) return;

        // Map old types to new alert types if necessary (e.g., 'error' to 'danger')
        const alertType = type === 'error' ? 'danger' : type;

        const alertDiv = document.createElement('div');
        // Basic alert classes + specific type. Add dismissible for a close button.
        alertDiv.className = `alert alert-${alertType} alert-dismissible fade show`; 
        alertDiv.setAttribute('role', 'alert');
        
        // Icon mapping (optional, could be done with CSS ::before too)
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
        
        statusMessagesContainer.prepend(alertDiv); // Add new message at the top

        // Auto-dismiss after 5 seconds
        const autoDismissTimer = setTimeout(() => {
            alertDiv.style.transition = 'opacity 0.5s ease';
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 500);
        }, 5000);

        // Manual dismiss
        alertDiv.querySelector('.btn-close').addEventListener('click', () => {
            clearTimeout(autoDismissTimer); // Clear auto-dismiss if manually closed
            alertDiv.style.transition = 'opacity 0.5s ease';
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 500);
        });

        // Limit number of messages
        while (statusMessagesContainer.children.length > 5) {
            statusMessagesContainer.removeChild(statusMessagesContainer.lastChild);
        }
    }

    /**
     * Initialize the application
     */
    async function initializeApp() {
        // First test if the API is reachable
        updateStatus('Verificando conectividad con el servidor...', 'info');
        
        const apiReachable = await testApiConnectivity();
        if (!apiReachable) {
            updateStatus('⚠️ No se puede conectar con el servidor. Puedes usar el modo manual para continuar.', 'warning');
            document.getElementById('stat-estado-moodle').textContent = 'Sin conexión';
            setTimeout(() => {
                updateStatus('💡 Haz clic en "Usar ID de curso manual" si conoces el ID del curso.', 'info');
            }, 2000);
            return;
        }
        
        // If API is reachable, try to load courses
        await fetchCourses();
    }

    // Initial action: fetch courses when the page loads.
    initializeApp().catch(error => {
        // This catch is for unhandled promise rejections from fetchCourses itself,
        // though fetchCourses has its own internal error handling.
        console.error('Error crítico durante la carga inicial de cursos:', error);
        updateStatus('Ocurrió un error grave al cargar los cursos. Por favor, recarga la página.', 'error');
    });
});

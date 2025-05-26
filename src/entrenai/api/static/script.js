document.addEventListener('DOMContentLoaded', () => {
    // const courseSearchInput = document.getElementById('course-search'); // Removed
    const courseSelect = document.getElementById('course-select');
    const setupAiButton = document.getElementById('setup-ai-button');
    const statusMessages = document.getElementById('status-messages');
    const manageFilesButton = document.getElementById('manage-files-button'); // Get the button

    let allCourses = []; // Para guardar la lista completa de cursos

    // URL base de tu API FastAPI (ajusta si es necesario)
    // Si FastAPI sirve este HTML, una ruta relativa podría funcionar: '/api/v1'
    // Si se abre como file:// o desde otro servidor, se necesita la URL completa y CORS.
    const API_BASE_URL = 'http://localhost:8000/api/v1';

    // Ensure essential DOM elements are present before proceeding.
    if (!courseSelect || !setupAiButton || !statusMessages || !manageFilesButton) {
        console.error('Error crítico: Faltan elementos del DOM requeridos en index.html. La aplicación no puede iniciarse correctamente.');
        // Optionally, display a message to the user in a more visible way if possible,
        // though `statusMessages` might be one of the missing elements.
        if (statusMessages) {
            updateStatus('Error de inicialización: Faltan componentes de la página.', 'error');
        }
        return;
    }

    /**
     * Fetches the list of courses from the Moodle API.
     * Populates the course selection dropdown upon successful retrieval.
     */
    async function fetchCourses() {
        updateStatus('Cargando cursos disponibles desde Moodle...', 'info');
        try {
            // This endpoint typically uses a default Moodle teacher ID if `moodle_user_id` is not provided.
            const response = await fetch(`${API_BASE_URL}/courses`);
            
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
            } else {
                updateStatus('No se encontraron cursos disponibles para el usuario configurado en Moodle.', 'warning');
            }
        } catch (networkError) {
            console.error('Error de red al cargar cursos:', networkError);
            updateStatus('Error de red al cargar cursos. Verifica tu conexión e inténtalo de nuevo.', 'error');
            courseSelect.innerHTML = '<option value="">Error de red al cargar</option>';
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

    if (manageFilesButton) {
      manageFilesButton.addEventListener('click', () => {
        const selectedCourseId = courseSelect.value;
        if (selectedCourseId) {
          // Navigate to the manage_files.html page with the course_id as a query parameter
          window.location.href = `/ui/manage_files.html?course_id=${selectedCourseId}`;
        } else {
          updateStatus('Por favor, selecciona un curso primero antes de gestionar archivos.', 'warning');
        }
      });
    }

    setupAiButton.addEventListener('click', async () => {
        const selectedCourseId = courseSelect.value;
        if (!selectedCourseId) {
            updateStatus('Por favor, selecciona un curso primero.', 'warning');
            return;
        }

        // Use type coercion (==) for selectedCourseId as it comes from element value (string)
        // and course.id might be a number.
        const selectedCourse = allCourses.find(c => c.id == selectedCourseId); 
        if (!selectedCourse) {
             updateStatus('El curso seleccionado no es válido o no se encontró en la lista.', 'error');
            return;
        }
        
        const courseDisplayName = selectedCourse.displayname || selectedCourse.fullname;
        updateStatus(`Iniciando configuración de IA para el curso: "${courseDisplayName}" (ID: ${selectedCourseId})... Esto puede tardar unos minutos. Por favor, espera.`, 'info');
        
        // Disable controls during AI setup
        setupAiButton.disabled = true;
        courseSelect.disabled = true;
        if(manageFilesButton) manageFilesButton.disabled = true;


        try {
            // The backend endpoint expects 'courseName' as a query parameter, used as an alias for 'course_name_query'.
            const response = await fetch(`${API_BASE_URL}/courses/${selectedCourseId}/setup-ia?courseName=${encodeURIComponent(courseDisplayName)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json' // Though body is not sent, this header is good practice for POST.
                }
            });
            
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
            console.error('Error de red durante la configuración de IA:', networkError);
            updateStatus(`Error de red al configurar IA para "${courseDisplayName}". Verifica tu conexión e inténtalo de nuevo.`, 'error');
        } finally {
            // Re-enable controls after the operation is complete (success or failure).
            setupAiButton.disabled = false;
            courseSelect.disabled = false;
            if(manageFilesButton) manageFilesButton.disabled = false;
        }
    });

    /**
     * Displays a status message to the user.
     * Prepends the new message to the status area and limits the number of messages shown.
     * @param {string} message - The message to display.
     * @param {string} type - The type of message ('info', 'success', 'warning', 'error').
     */
    function updateStatus(message, type = 'info') {
        if (!statusMessages) return; // Guard clause if statusMessages is not found
        const p = document.createElement('p');
        p.className = type; // CSS classes like 'info', 'success', etc., should be defined in style.css
        p.textContent = message;
        
        statusMessages.prepend(p); // Add the new message at the beginning of the status container.
        
        // Limit the number of status messages displayed to avoid clutter.
        while (statusMessages.children.length > 5) { // Keep the 5 most recent messages.
            statusMessages.removeChild(statusMessages.lastChild);
        }
    }

    // Initial action: fetch courses when the page loads.
    fetchCourses().catch(error => {
        // This catch is for unhandled promise rejections from fetchCourses itself,
        // though fetchCourses has its own internal error handling.
        console.error('Error crítico durante la carga inicial de cursos:', error);
        updateStatus('Ocurrió un error grave al cargar los cursos. Por favor, recarga la página.', 'error');
    });
});

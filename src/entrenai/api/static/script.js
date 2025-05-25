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

    // Verifica que los elementos existen antes de usarlos
    if (!courseSelect || !setupAiButton || !statusMessages || !manageFilesButton) {
        console.error('Faltan elementos del DOM requeridos. Revisa el HTML.');
        return;
    }

    async function fetchCourses() {
        updateStatus('Cargando cursos desde Moodle...', 'info');
        try {
            // El endpoint /api/v1/courses usa MOODLE_DEFAULT_TEACHER_ID si no se pasa moodle_user_id
            const response = await fetch(`${API_BASE_URL}/courses`);
            if (!response.ok) {
                let errorDetail = `Error ${response.status}: No se pudieron cargar los cursos.`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch (e) { /* No hacer nada si el cuerpo del error no es JSON */ }
                updateStatus(errorDetail, 'error');
                return;
            }
            allCourses = await response.json();
            if (!Array.isArray(allCourses)) {
                console.error("La respuesta de cursos no es un array:", allCourses);
                allCourses = []; // Evitar errores posteriores
                updateStatus("Formato de respuesta de cursos inesperado.", 'error');
                return;
            }
            populateCourseSelect(allCourses);
            if (allCourses.length > 0) {
                updateStatus('Cursos cargados. Por favor, selecciona uno.', 'success');
            } else {
                updateStatus('No se encontraron cursos para el profesor configurado.', 'warning');
            }
        } catch (error) {
            console.error('Error fetching courses:', error);
            updateStatus(`Error al cargar cursos: ${error.message}`, 'error');
            courseSelect.innerHTML = '<option value="">Error al cargar cursos</option>';
        }
    }

    function populateCourseSelect(courses) {
        courseSelect.innerHTML = ''; // Limpiar opciones previas
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
          window.location.href = `/static/manage_files.html?course_id=${selectedCourseId}`;
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

        const selectedCourse = allCourses.find(c => c.id === selectedCourseId); // Comparación estricta
        if (!selectedCourse) {
             updateStatus('Curso seleccionado no válido.', 'error');
            return;
        }
        
        const courseDisplayName = selectedCourse.displayname || selectedCourse.fullname;
        updateStatus(`Iniciando configuración de IA para el curso: "${courseDisplayName}" (ID: ${selectedCourseId})... Esto puede tardar unos minutos.`, 'info');
        setupAiButton.disabled = true;
        // courseSearchInput.disabled = true; // Removed
        courseSelect.disabled = true;

        try {
            // Backend expects 'courseName' as alias for course_name_query
            const response = await fetch(`${API_BASE_URL}/courses/${selectedCourseId}/setup-ia?courseName=${encodeURIComponent(courseDisplayName)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();

            if (!response.ok) {
                updateStatus(result.detail || `Error ${response.status}: Falló la configuración de la IA.`, 'error');
                return;
            }
            
            updateStatus(`Configuración para "${courseDisplayName}" completada: ${result.message}`, 'success');
        } catch (error) {
            console.error('Error setting up AI:', error);
            updateStatus(`Error en la configuración para "${courseDisplayName}": ${error.message}`, 'error');
        } finally {
            setupAiButton.disabled = false;
            // courseSearchInput.disabled = false; // Removed
            courseSelect.disabled = false;
        }
    });

    function updateStatus(message, type = 'info') { 
        const p = document.createElement('p');
        p.className = type;
        p.textContent = message;
        // statusMessages.innerHTML = ''; // Limpiar mensajes anteriores
        statusMessages.prepend(p); // Añadir nuevo mensaje al principio
        // Limitar el número de mensajes mostrados si se desea
        while (statusMessages.children.length > 5) {
            statusMessages.removeChild(statusMessages.lastChild);
        }
    }

    fetchCourses().catch(error => {
        console.error('Error inicial al cargar cursos:', error);
        updateStatus('Error al cargar cursos inicialmente', 'error');
    });
});

document.addEventListener('DOMContentLoaded', () => {
    const courseSearchInput = document.getElementById('course-search');
    const courseSelect = document.getElementById('course-select');
    const setupAiButton = document.getElementById('setup-ai-button');
    const statusMessages = document.getElementById('status-messages');
    
    let allCourses = []; // Para guardar la lista completa de cursos

    // URL base de tu API FastAPI (ajusta si es necesario)
    // Si FastAPI sirve este HTML, una ruta relativa podría funcionar: '/api/v1'
    // Si se abre como file:// o desde otro servidor, se necesita la URL completa y CORS.
    const API_BASE_URL = 'http://localhost:8000/api/v1'; 

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
                throw new Error(errorDetail);
            }
            allCourses = await response.json();
            if (!Array.isArray(allCourses)) {
                console.error("La respuesta de cursos no es un array:", allCourses);
                allCourses = []; // Evitar errores posteriores
                throw new Error("Formato de respuesta de cursos inesperado.");
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

    courseSearchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase().trim();
        if (!allCourses || allCourses.length === 0) return;

        const filteredCourses = allCourses.filter(course => {
            const fullName = (course.fullname || "").toLowerCase();
            const shortName = (course.shortname || "").toLowerCase();
            const displayName = (course.displayname || "").toLowerCase();
            return fullName.includes(searchTerm) || 
                   shortName.includes(searchTerm) || 
                   displayName.includes(searchTerm);
        });
        populateCourseSelect(filteredCourses);
    });

    setupAiButton.addEventListener('click', async () => {
        const selectedCourseId = courseSelect.value;
        if (!selectedCourseId) {
            updateStatus('Por favor, selecciona un curso primero.', 'warning');
            return;
        }

        const selectedCourse = allCourses.find(c => c.id == selectedCourseId); // Comparación no estricta por si acaso
        if (!selectedCourse) {
             updateStatus('Curso seleccionado no válido.', 'error');
            return;
        }
        
        const courseDisplayName = selectedCourse.displayname || selectedCourse.fullname;
        updateStatus(`Iniciando configuración de IA para el curso: "${courseDisplayName}" (ID: ${selectedCourseId})... Esto puede tardar unos minutos.`, 'info');
        setupAiButton.disabled = true;
        courseSearchInput.disabled = true;
        courseSelect.disabled = true;

        try {
            const response = await fetch(`${API_BASE_URL}/courses/${selectedCourseId}/setup-ia`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || `Error ${response.status}: Falló la configuración de la IA.`);
            }
            
            updateStatus(`Configuración para "${courseDisplayName}" completada: ${result.message}`, 'success');
        } catch (error) {
            console.error('Error setting up AI:', error);
            updateStatus(`Error en la configuración para "${courseDisplayName}": ${error.message}`, 'error');
        } finally {
            setupAiButton.disabled = false;
            courseSearchInput.disabled = false;
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

    fetchCourses();
});

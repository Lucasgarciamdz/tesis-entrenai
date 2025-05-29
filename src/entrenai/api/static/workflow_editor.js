document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const courseId = urlParams.get('course_id');

    const loadingMessage = document.getElementById('loading-message');
    const workflowConfigForm = document.getElementById('workflow-config-form');
    const responseMessage = document.getElementById('response-message');

    const initialMessagesInput = document.getElementById('initialMessages');
    const systemMessageInput = document.getElementById('systemMessage');
    const inputPlaceholderInput = document.getElementById('inputPlaceholder');
    const chatTitleInput = document.getElementById('chatTitle');

    if (!courseId) {
        loadingMessage.textContent = 'Error: ID de curso no proporcionado en la URL.';
        loadingMessage.style.color = 'red';
        return;
    }

    async function fetchWorkflowConfig() {
        try {
            const response = await fetch(`/api/v1/courses/${courseId}/n8n-workflow-config`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Error al cargar la configuración del workflow.');
            }
            const config = await response.json();
            
            initialMessagesInput.value = config.initialMessages || '';
            systemMessageInput.value = config.systemMessage || '';
            inputPlaceholderInput.value = config.inputPlaceholder || '';
            chatTitleInput.value = config.chatTitle || '';

            loadingMessage.style.display = 'none';
            workflowConfigForm.style.display = 'block';

        } catch (error) {
            loadingMessage.textContent = `Error al cargar la configuración: ${error.message}`;
            loadingMessage.style.color = 'red';
            console.error('Error fetching workflow config:', error);
        }
    }

    async function saveWorkflowConfig(event) {
        event.preventDefault();
        responseMessage.style.display = 'none';
        responseMessage.className = 'message';

        const payload = {
            initialMessages: initialMessagesInput.value,
            systemMessage: systemMessageInput.value,
            inputPlaceholder: inputPlaceholderInput.value,
            chatTitle: chatTitleInput.value
        };

        try {
            const response = await fetch(`/api/v1/courses/${courseId}/setup-ia`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Error al guardar la configuración.');
            }

            responseMessage.textContent = data.message || 'Configuración guardada exitosamente.';
            responseMessage.classList.add('success');
            responseMessage.style.display = 'block';

            // Opcional: Recargar la configuración para asegurar que se muestren los valores actualizados
            // await fetchWorkflowConfig(); 

        } catch (error) {
            responseMessage.textContent = `Error al guardar: ${error.message}`;
            responseMessage.classList.add('error');
            responseMessage.style.display = 'block';
            console.error('Error saving workflow config:', error);
        }
    }

    fetchWorkflowConfig();
    workflowConfigForm.addEventListener('submit', saveWorkflowConfig);
});

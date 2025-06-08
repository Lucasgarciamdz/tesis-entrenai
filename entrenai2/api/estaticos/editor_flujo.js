document.addEventListener('DOMContentLoaded', () => {
    const paramsUrl = new URLSearchParams(window.location.search);
    const idCurso = paramsUrl.get('id_curso');

    const mensajeCarga = document.getElementById('mensaje-carga');
    const formularioConfiguracionFlujo = document.getElementById('formulario-configuracion-flujo');
    const mensajeRespuesta = document.getElementById('mensaje-respuesta');

    const entradaMensajesIniciales = document.getElementById('mensajesIniciales');
    const entradaMensajeSistema = document.getElementById('mensajeSistema');
    const entradaMarcadorPosicion = document.getElementById('marcadorPosicionEntrada');
    const entradaTituloChat = document.getElementById('tituloChat');

    if (!idCurso) {
        mensajeCarga.textContent = 'Error: ID de curso no proporcionado en la URL.';
        mensajeCarga.style.color = 'red';
        return;
    }

    async function obtenerConfiguracionFlujo() {
        try {
            const respuesta = await fetch(`/api/v1/cursos/${idCurso}/configuracion-flujo-n8n`);
            if (!respuesta.ok) {
                const datosError = await respuesta.json();
                throw new Error(datosError.detail || 'Error al cargar la configuración del flujo de trabajo.');
            }
            const config = await respuesta.json();
            
            entradaMensajesIniciales.value = config.mensajesIniciales || '';
            entradaMensajeSistema.value = config.mensajeSistema || '';
            entradaMarcadorPosicion.value = config.marcadorPosicionEntrada || '';
            entradaTituloChat.value = config.tituloChat || '';

            mensajeCarga.style.display = 'none';
            formularioConfiguracionFlujo.style.display = 'block';

        } catch (error) {
            mensajeCarga.textContent = `Error al cargar la configuración: ${error.message}`;
            mensajeCarga.style.color = 'red';
            console.error('Error obteniendo la configuración del flujo de trabajo:', error);
        }
    }

    async function guardarConfiguracionFlujo(evento) {
        evento.preventDefault();
        mensajeRespuesta.style.display = 'none';
        mensajeRespuesta.className = 'message';

        const carga = {
            mensajesIniciales: entradaMensajesIniciales.value,
            mensajeSistema: entradaMensajeSistema.value,
            marcadorPosicionEntrada: entradaMarcadorPosicion.value,
            tituloChat: entradaTituloChat.value
        };

        try {
            const respuesta = await fetch(`/api/v1/cursos/${idCurso}/configurar-ia`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(carga)
            });

            const datos = await respuesta.json();

            if (!respuesta.ok) {
                throw new Error(datos.detail || 'Error al guardar la configuración.');
            }

            mensajeRespuesta.textContent = datos.mensaje || 'Configuración guardada exitosamente.';
            mensajeRespuesta.classList.add('success');
            mensajeRespuesta.style.display = 'block';

        } catch (error) {
            mensajeRespuesta.textContent = `Error al guardar: ${error.message}`;
            mensajeRespuesta.classList.add('error');
            mensajeRespuesta.style.display = 'block';
            console.error('Error guardando la configuración del flujo de trabajo:', error);
        }
    }

    obtenerConfiguracionFlujo();
    formularioConfiguracionFlujo.addEventListener('submit', guardarConfiguracionFlujo);
});

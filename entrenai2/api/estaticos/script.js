document.addEventListener('DOMContentLoaded', () => {
    const selectorCurso = document.getElementById('selector-curso');
    const botonConfigurarIa = document.getElementById('boton-configurar-ia');
    const contenedorMensajesEstado = document.getElementById('contenedor-mensajes-estado');
    const botonGestionarArchivos = document.getElementById('boton-gestionar-archivos');
    const spinnerBotonConfigurarIa = botonConfigurarIa ? botonConfigurarIa.querySelector('.btn-spinner') : null;

    let todosLosCursos = [];

    const URL_BASE_API = 'http://localhost:8000';

    const entradaManualCurso = document.getElementById('entrada-manual-curso');
    const idCursoManual = document.getElementById('id-curso-manual');
    const botonAlternarEntradaManual = document.getElementById('alternar-entrada-manual');

    if (!selectorCurso || !botonConfigurarIa || !contenedorMensajesEstado || !botonGestionarArchivos) {
        console.error('Error crítico: Faltan elementos del DOM requeridos en index.html. La aplicación no puede iniciarse correctamente.');
        if (contenedorMensajesEstado) {
            actualizarEstado('Error de inicialización: Faltan componentes de la página.', 'error');
        }
        return;
    }

    async function probarConectividadApi() {
        try {
            const respuesta = await fetch(`${URL_BASE_API}/salud`, {
                method: 'GET',
                timeout: 5000
            });
            return respuesta.ok;
        } catch (error) {
            console.warn('La prueba de conectividad de la API falló:', error);
            return false;
        }
    }

    async function obtenerCursos() {
        actualizarEstado('Cargando cursos disponibles desde Moodle...', 'info');
        document.getElementById('stat-cursos-configurados').textContent = '...';
        document.getElementById('stat-archivos-procesados').textContent = '...';
        document.getElementById('stat-archivos-en-proceso').textContent = '...';
        document.getElementById('stat-estado-moodle').textContent = 'Verificando...';

        const controlador = new AbortController();
        const idTimeout = setTimeout(() => controlador.abort(), 30000);

        try {
            const respuesta = await fetch(`${URL_BASE_API}/api/v1/cursos`, {
                signal: controlador.signal
            });
            
            clearTimeout(idTimeout);

            if (!respuesta.ok) {
                let detalleError = `Error ${respuesta.status}: No se pudieron cargar los cursos.`;
                try {
                    const datosError = await respuesta.json();
                    detalleError = datosError.detail || detalleError;
                } catch (e) {
                    console.warn('No se pudo parsear la respuesta de error como JSON:', e);
                }
                actualizarEstado(detalleError, 'error');
                selectorCurso.innerHTML = '<option value="">Error al cargar cursos</option>';
                return;
            }

            const datosCursos = await respuesta.json();
            if (!Array.isArray(datosCursos)) {
                console.error("Respuesta inesperada del servidor: la lista de cursos no es un array.", datosCursos);
                todosLosCursos = [];
                actualizarEstado("Error: Formato de respuesta de cursos incorrecto.", 'error');
                selectorCurso.innerHTML = '<option value="">Error al procesar cursos</option>';
                return;
            }
            
            todosLosCursos = datosCursos;
            poblarSelectorCursos(todosLosCursos);

            if (todosLosCursos.length > 0) {
                actualizarEstado('Cursos cargados exitosamente. Por favor, selecciona un curso para continuar.', 'success');
                document.getElementById('stat-cursos-configurados').textContent = todosLosCursos.filter(c => c.is_ai_configured).length;
                document.getElementById('stat-estado-moodle').textContent = 'Conectado';
            } else {
                actualizarEstado('No se encontraron cursos disponibles para el usuario configurado en Moodle.', 'warning');
                document.getElementById('stat-estado-moodle').textContent = 'Sin cursos';
            }
        } catch (errorRed) {
            clearTimeout(idTimeout);
            console.error('Error de red al cargar cursos:', errorRed);
            
            let mensajeError = 'Error de red al cargar cursos. Verifica tu conexión e inténtalo de nuevo.';
            let textoEstado = 'Error de Red';
            
            if (errorRed.name === 'AbortError') {
                mensajeError = 'Timeout al cargar cursos. El servidor de Moodle puede estar inaccesible. Puedes usar el modo manual para continuar.';
                textoEstado = 'Timeout';
            }
            
            actualizarEstado(mensajeError, 'error');
            selectorCurso.innerHTML = '<option value="">Error al cargar cursos</option>';
            document.getElementById('stat-estado-moodle').textContent = textoEstado;
            
            setTimeout(() => {
                actualizarEstado('💡 Sugerencia: Usa el botón "Usar ID de curso manual" si conoces el ID del curso.', 'info');
            }, 3000);
        }
    }

    function poblarSelectorCursos(cursos) {
        selectorCurso.innerHTML = '';
        if (cursos.length === 0) {
            selectorCurso.innerHTML = '<option value="">No hay cursos disponibles</option>';
            return;
        }
        
        const opcionPorDefecto = document.createElement('option');
        opcionPorDefecto.value = "";
        opcionPorDefecto.textContent = "-- Selecciona un curso --";
        selectorCurso.appendChild(opcionPorDefecto);

        cursos.forEach(curso => {
            const opcion = document.createElement('option');
            opcion.value = curso.id;
            const nombreMostrar = curso.displayname || curso.fullname;
            opcion.textContent = `${nombreMostrar} (ID: ${curso.id})`;
            selectorCurso.appendChild(opcion);
        });
    }

    if (selectorCurso) {
        selectorCurso.addEventListener('change', () => {
            if (selectorCurso.value && botonGestionarArchivos) {
                botonGestionarArchivos.style.display = 'block';
            } else if (botonGestionarArchivos) {
                botonGestionarArchivos.style.display = 'none';
            }
        });
    }
    
    if (idCursoManual && botonGestionarArchivos) {
        idCursoManual.addEventListener('input', () => {
            if (idCursoManual.value && botonGestionarArchivos) {
                botonGestionarArchivos.style.display = 'block';
            } else if (botonGestionarArchivos) {
                botonGestionarArchivos.style.display = 'none';
            }
        });
    }

    if (botonGestionarArchivos) {
      botonGestionarArchivos.addEventListener('click', () => {
        const idCursoSeleccionado = obtenerIdCursoSeleccionado();
        if (idCursoSeleccionado) {
          window.location.href = `/ui/gestionar_archivos.html?id_curso=${idCursoSeleccionado}`;
        } else {
          actualizarEstado('Por favor, selecciona un curso primero antes de gestionar archivos.', 'warning');
        }
      });
    }

    botonConfigurarIa.addEventListener('click', async () => {
        const idCursoSeleccionado = obtenerIdCursoSeleccionado();
        if (!idCursoSeleccionado) {
            actualizarEstado('Por favor, selecciona un curso primero.', 'warning');
            return;
        }

        const cursoSeleccionado = obtenerCursoSeleccionado();
        if (!cursoSeleccionado) {
            actualizarEstado('El curso seleccionado no es válido o no se encontró en la lista.', 'error');
            return;
        }
        
        const nombreMostrarCurso = cursoSeleccionado.displayname || cursoSeleccionado.fullname;
        actualizarEstado(`Iniciando configuración de IA para el curso: "${nombreMostrarCurso}" (ID: ${idCursoSeleccionado})... Esto puede tardar unos minutos. Por favor, espera.`, 'info');
        
        botonConfigurarIa.disabled = true;
        if (spinnerBotonConfigurarIa) spinnerBotonConfigurarIa.classList.remove('d-none');
        selectorCurso.disabled = true;
        if(botonGestionarArchivos) botonGestionarArchivos.disabled = true;

        try {
            const controlador = new AbortController();
            const idTimeout = setTimeout(() => controlador.abort(), 120000);

            const respuesta = await fetch(`${URL_BASE_API}/api/v1/cursos/${idCursoSeleccionado}/configurar-ia?nombreCurso=${encodeURIComponent(nombreMostrarCurso)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                signal: controlador.signal
            });
            
            clearTimeout(idTimeout);
            
            let resultado;
            try {
                resultado = await respuesta.json();
            } catch (e) {
                console.error('No se pudo parsear la respuesta de configurar IA como JSON:', e);
                actualizarEstado(`Error inesperado del servidor durante la configuración. Código: ${respuesta.status}`, 'error');
                return;
            }

            if (!respuesta.ok) {
                actualizarEstado(resultado.detail || `Error ${respuesta.status}: Falló la configuración de la IA para "${nombreMostrarCurso}".`, 'error');
                return;
            }
            
            actualizarEstado(`Configuración de IA para "${nombreMostrarCurso}" completada exitosamente: ${resultado.mensaje}`, 'success');
        } catch (errorRed) {
            clearTimeout(idTimeout);
            console.error('Error de red durante la configuración de IA:', errorRed);
            
            let mensajeError = `Error de red al configurar IA para "${nombreMostrarCurso}". Verifica tu conexión e inténtalo de nuevo.`;
            if (errorRed.name === 'AbortError') {
                mensajeError = `Timeout al configurar IA para "${nombreMostrarCurso}". La operación está tomando demasiado tiempo.`;
            }
            
            actualizarEstado(mensajeError, 'error');
        } finally {
            botonConfigurarIa.disabled = false;
            if (spinnerBotonConfigurarIa) spinnerBotonConfigurarIa.classList.add('d-none');
            selectorCurso.disabled = false;
            if(botonGestionarArchivos) botonGestionarArchivos.disabled = false;
        }
    });

    if (botonAlternarEntradaManual && entradaManualCurso) {
        botonAlternarEntradaManual.addEventListener('click', () => {
            const estaOculto = entradaManualCurso.style.display === 'none';
            entradaManualCurso.style.display = estaOculto ? 'block' : 'none';
            botonAlternarEntradaManual.textContent = estaOculto ? 'Usar lista de cursos' : 'Usar ID de curso manual';
            
            if (estaOculto) {
                selectorCurso.parentElement.style.display = 'none';
            } else {
                selectorCurso.parentElement.style.display = 'block';
            }
        });
    }

    function obtenerIdCursoSeleccionado() {
        if (entradaManualCurso && entradaManualCurso.style.display !== 'none') {
            return idCursoManual ? idCursoManual.value : null;
        }
        return selectorCurso.value;
    }

    function obtenerCursoSeleccionado() {
        const idSeleccionado = obtenerIdCursoSeleccionado();
        if (!idSeleccionado) return null;
        
        if (entradaManualCurso && entradaManualCurso.style.display !== 'none') {
            return { id: parseInt(idSeleccionado), fullname: `Curso ${idSeleccionado}` };
        }
        
        return todosLosCursos.find(c => c.id == idSeleccionado);
    }

    function actualizarEstado(mensaje, tipo = 'info') {
        if (!contenedorMensajesEstado) return;

        const tipoAlerta = tipo === 'error' ? 'danger' : tipo;

        const divAlerta = document.createElement('div');
        divAlerta.className = `alert alert-${tipoAlerta} alert-dismissible fade show`; 
        divAlerta.setAttribute('role', 'alert');
        
        let iconoClase = '';
        if (tipoAlerta === 'success') iconoClase = '✅ ';
        else if (tipoAlerta === 'danger') iconoClase = '❗ ';
        else if (tipoAlerta === 'warning') iconoClase = '⚠️ ';
        else if (tipoAlerta === 'info') iconoClase = 'ℹ️ ';

        divAlerta.innerHTML = `
            <span class="alert-icon">${iconoClase}</span>
            ${mensaje}
            <button type="button" class="btn-close" style="background: none; border: none; font-size: 1.2rem; float: right; cursor: pointer; line-height: 1;" aria-label="Cerrar">&times;</button>
        `;
        
        contenedorMensajesEstado.prepend(divAlerta);

        const temporizadorAutoCierre = setTimeout(() => {
            divAlerta.style.transition = 'opacity 0.5s ease';
            divAlerta.style.opacity = '0';
            setTimeout(() => divAlerta.remove(), 500);
        }, 5000);

        divAlerta.querySelector('.btn-close').addEventListener('click', () => {
            clearTimeout(temporizadorAutoCierre);
            divAlerta.style.transition = 'opacity 0.5s ease';
            divAlerta.style.opacity = '0';
            setTimeout(() => divAlerta.remove(), 500);
        });

        while (contenedorMensajesEstado.children.length > 5) {
            contenedorMensajesEstado.removeChild(contenedorMensajesEstado.lastChild);
        }
    }

    async function inicializarAplicacion() {
        actualizarEstado('Verificando conectividad con el servidor...', 'info');
        
        const apiAlcanzable = await probarConectividadApi();
        if (!apiAlcanzable) {
            actualizarEstado('⚠️ No se puede conectar con el servidor. Puedes usar el modo manual para continuar.', 'warning');
            document.getElementById('stat-estado-moodle').textContent = 'Sin conexión';
            setTimeout(() => {
                actualizarEstado('💡 Haz clic en "Usar ID de curso manual" si conoces el ID del curso.', 'info');
            }, 2000);
            return;
        }
        
        await obtenerCursos();
    }

    inicializarAplicacion().catch(error => {
        console.error('Error crítico durante la carga inicial de cursos:', error);
        actualizarEstado('Ocurrió un error grave al cargar los cursos. Por favor, recarga la página.', 'error');
    });
});

document.addEventListener('DOMContentLoaded', async () => {
    const placeholderNombreCurso = document.getElementById('nombre-curso-placeholder');
    const contenedorMensajesGestion = document.getElementById('contenedor-mensajes-gestion');
    const botonRefrescarArchivosMoodle = document.getElementById('boton-refrescar-archivos-moodle');
    const spinnerBotonRefrescar = botonRefrescarArchivosMoodle ? botonRefrescarArchivosMoodle.querySelector('.btn-spinner') : null;
    
    const cuerpoTablaArchivos = document.getElementById('cuerpo-tabla-archivos');
    const mensajeSinArchivos = document.getElementById('mensaje-sin-archivos');

    const URL_BASE_API = 'http://localhost:8000/api/v1';
    let idCurso;
    let nombreMostrarCurso = '';
    let tareasActivas = {};
    let colaTareas = [];
    let procesandoActualmente = false;

    if (!placeholderNombreCurso || !contenedorMensajesGestion || !botonRefrescarArchivosMoodle || !cuerpoTablaArchivos || !mensajeSinArchivos) {
        console.error('Error crítico: Faltan elementos del DOM requeridos en gestionar_archivos.html.');
        if (contenedorMensajesGestion) { 
            actualizarEstadoGestion('Error de inicialización: Faltan componentes clave de la página.', 'error');
        }
        return;
    }

    async function inicializarPagina() {
        const params = new URLSearchParams(window.location.search);
        idCurso = params.get('id_curso');

        if (!idCurso) {
            actualizarEstadoGestion('Error: No se ha especificado un ID de curso. Vuelve al Panel de Control.', 'danger');
            deshabilitarTodosLosControles();
            if (cuerpoTablaArchivos) cuerpoTablaArchivos.innerHTML = `<tr><td colspan="5" class="text-center text-danger">ID de curso no especificado.</td></tr>`;
            if (mensajeSinArchivos) mensajeSinArchivos.classList.remove('d-none');
            return;
        }
        
        await obtenerDetallesCurso(idCurso); 
        
        await cargarYMostrarArchivos(idCurso);
        configurarEventListeners();
    }

    async function obtenerDetallesCurso(idCursoActual) {
        try {
            const respuesta = await fetch(`${URL_BASE_API}/cursos/${idCursoActual}`);
            if (respuesta.ok) {
                const datosCurso = await respuesta.json();
                let cursoEncontrado = Array.isArray(datosCurso) ? datosCurso.find(c => c.id == idCursoActual) : datosCurso;

                if (cursoEncontrado && (cursoEncontrado.displayname || cursoEncontrado.fullname)) {
                    nombreMostrarCurso = cursoEncontrado.displayname || cursoEncontrado.fullname;
                    placeholderNombreCurso.textContent = nombreMostrarCurso;
                } else {
                    placeholderNombreCurso.textContent = `ID ${idCursoActual}`;
                }
            } else {
                console.warn(`No se pudo obtener el nombre del curso ${idCursoActual}. Mostrando ID.`);
                placeholderNombreCurso.textContent = `ID ${idCursoActual}`;
            }
        } catch (error) {
            console.error('Error al obtener detalles del curso:', error);
            placeholderNombreCurso.textContent = `ID ${idCursoActual}`;
        }
    }

    function deshabilitarTodosLosControles() {
        if (botonRefrescarArchivosMoodle) botonRefrescarArchivosMoodle.disabled = true;
    }

    function configurarEventListeners() {
        if (botonRefrescarArchivosMoodle) {
            botonRefrescarArchivosMoodle.addEventListener('click', () => manejarRefrescoArchivos(idCurso));
        }
    }

    function actualizarEstadoGestion(mensaje, tipo = 'info') {
        if (!contenedorMensajesGestion) return;
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
        
        contenedorMensajesGestion.prepend(divAlerta);

        const temporizadorAutoCierre = setTimeout(() => {
            divAlerta.style.transition = 'opacity 0.5s ease';
            divAlerta.style.opacity = '0';
            setTimeout(() => divAlerta.remove(), 500);
        }, 7000);

        divAlerta.querySelector('.btn-close').addEventListener('click', () => {
            clearTimeout(temporizadorAutoCierre);
            divAlerta.style.transition = 'opacity 0.5s ease';
            divAlerta.style.opacity = '0';
            setTimeout(() => divAlerta.remove(), 500);
        });

        while (contenedorMensajesGestion.children.length > 5) {
            contenedorMensajesGestion.removeChild(contenedorMensajesGestion.lastChild);
        }
    }

    async function cargarYMostrarArchivos(idCursoActual) {
        if (!cuerpoTablaArchivos || !mensajeSinArchivos) return;
        
        actualizarEstadoGestion(`Cargando archivos para el curso ID ${idCursoActual}...`, 'info');
        cuerpoTablaArchivos.innerHTML = `<tr><td colspan="5" class="text-center p-3"><span class="btn-spinner"></span> Cargando...</td></tr>`;
        mensajeSinArchivos.classList.add('d-none');

        try {
            const respuestaIndexados = await fetch(`${URL_BASE_API}/cursos/${idCursoActual}/archivos-indexados`);
            let archivosIndexados = [];
            if (respuestaIndexados.ok) {
                archivosIndexados = await respuestaIndexados.json();
                if (!Array.isArray(archivosIndexados)) archivosIndexados = [];
            } else if (respuestaIndexados.status !== 404) {
                const datosError = await respuestaIndexados.json().catch(() => ({}));
                actualizarEstadoGestion(`Error ${respuestaIndexados.status} al cargar archivos indexados: ${datosError.detail || 'Error desconocido'}`, 'danger');
            }
            
            renderizarTablaArchivos(archivosIndexados, []);

            if (archivosIndexados.length === 0) {
                mensajeSinArchivos.classList.remove('d-none');
                cuerpoTablaArchivos.innerHTML = '';
                actualizarEstadoGestion('No se encontraron archivos para este curso.', 'info');
            } else {
                actualizarEstadoGestion(`Archivos cargados para el curso ${idCursoActual}.`, 'success');
            }

        } catch (errorRed) {
            console.error('Error de red al cargar archivos:', errorRed);
            actualizarEstadoGestion('Error de red al cargar archivos. Verifica tu conexión.', 'danger');
            cuerpoTablaArchivos.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error de red al cargar archivos.</td></tr>`;
            mensajeSinArchivos.classList.remove('d-none');
        }
    }
    
    function renderizarTablaArchivos(archivosIndexados, tareasEnProceso) {
        if (!cuerpoTablaArchivos || !mensajeSinArchivos) return;
        cuerpoTablaArchivos.innerHTML = '';
        mensajeSinArchivos.classList.add('d-none');

        let todasLasEntradas = [];

        archivosIndexados.forEach(archivo => {
            todasLasEntradas.push({
                nombre: archivo.nombre_archivo,
                estado: 'Indexado',
                progreso: 100,
                ultimaModificacion: archivo.ultima_modificacion_moodle ? new Date(archivo.ultima_modificacion_moodle * 1000).toLocaleString() : 'N/A',
                ultimaModificacionRaw: archivo.ultima_modificacion_moodle,
                acciones: [{ tipo: 'eliminar', nombre_archivo: archivo.nombre_archivo }]
            });
        });

        tareasEnProceso.forEach(tarea => {
            todasLasEntradas.push({
                nombre: tarea.nombre_archivo || `Tarea ${tarea.id_tarea.substring(0,8)}`,
                estado: tarea.estado,
                progreso: tarea.porcentaje_progreso || (tarea.estado === 'PROCESANDO' ? null : 0),
                ultimaModificacion: 'N/A',
                acciones: [],
                id_tarea: tarea.id_tarea
            });
        });
        
        if (todasLasEntradas.length === 0) {
            mensajeSinArchivos.classList.remove('d-none');
            return;
        }

        todasLasEntradas.sort((a, b) => {
            const ordenEstado = { 'PROCESANDO': 0, 'PENDIENTE': 1, 'Indexado': 2, 'FALLIDO': 3 };
            const estadoA = ordenEstado[a.estado] ?? 99;
            const estadoB = ordenEstado[b.estado] ?? 99;
            if (estadoA !== estadoB) return estadoA - estadoB;
            return (b.ultimaModificacionRaw || 0) - (a.ultimaModificacionRaw || 0);
        });

        todasLasEntradas.forEach(entrada => {
            const fila = cuerpoTablaArchivos.insertRow();
            fila.dataset.fileName = entrada.nombre;
            if (entrada.id_tarea) fila.dataset.taskId = entrada.id_tarea;

            fila.insertCell().textContent = entrada.nombre;
            
            const celdaEstado = fila.insertCell();
            renderizarIndicadorEstado(celdaEstado, entrada.estado, entrada.id_tarea);

            const celdaProgreso = fila.insertCell();
            renderizarBarraProgreso(celdaProgreso, entrada.estado, entrada.progreso);
            
            fila.insertCell().textContent = entrada.ultimaModificacion;
            
            const celdaAcciones = fila.insertCell();
            entrada.acciones.forEach(accion => {
                if (accion.tipo === 'eliminar') {
                    const botonEliminar = document.createElement('button');
                    botonEliminar.textContent = 'Eliminar';
                    botonEliminar.classList.add('btn', 'btn-sm', 'btn-danger');
                    botonEliminar.addEventListener('click', () => manejarEliminacionArchivo(idCurso, accion.nombre_archivo, fila));
                    celdaAcciones.appendChild(botonEliminar);
                }
            });
        });
    }

    function renderizarIndicadorEstado(celda, estado, id_tarea = null) {
        let textoEstado = estado;
        let claseEstado = '';
        let icono = '';

        switch (estado.toUpperCase()) {
            case 'INDEXADO': textoEstado = 'Indexado'; claseEstado = 'status-success'; icono = '✅'; break;
            case 'PENDIENTE': textoEstado = 'Pendiente'; claseEstado = 'status-warning'; icono = '🕒'; break;
            case 'INICIADO':
            case 'PROCESANDO': 
                textoEstado = 'Procesando'; claseEstado = 'status-processing'; 
                break;
            case 'FALLIDO': textoEstado = 'Error'; claseEstado = 'status-danger'; icono = '❌'; break;
            default: textoEstado = estado; claseEstado = 'status-info'; icono = 'ℹ️'; break;
        }
        
        celda.innerHTML = `<span class="status-indicator ${claseEstado}">
                            ${estado.toUpperCase() === 'PROCESANDO' && !id_tarea ? '<span class="btn-spinner" style="width:0.8em; height:0.8em; border-width:1.5px; margin-right: 0.3em;"></span>' : `<span class="status-indicator-icon">${icono}</span>`}
                            ${textoEstado}
                          </span>`;
    }

    function renderizarBarraProgreso(celda, estado, porcentajeProgreso) {
        const estadoMayusculas = estado.toUpperCase();
        
        if (estadoMayusculas === 'PROCESANDO' || estadoMayusculas === 'INICIADO' || estadoMayusculas === 'PENDIENTE') {
            const porcentajeMostrar = (typeof porcentajeProgreso === 'number' && porcentajeProgreso >= 0 && porcentajeProgreso <= 100) ? porcentajeProgreso : 0;
            const estaSimulando = (porcentajeMostrar > 0 && porcentajeMostrar < 99); 
            const anchoBarra = porcentajeMostrar;

            celda.innerHTML = `
                <div class="progress" style="height: 1.2em;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: ${anchoBarra}%" aria-valuenow="${anchoBarra}" aria-valuemin="0" aria-valuemax="100">${estaSimulando ? anchoBarra + '%' : ''}</div>
                </div>`;
        } else if (estadoMayusculas === 'INDEXADO' || estadoMayusculas === 'SUCCESS') {
             celda.innerHTML = `
                <div class="progress" style="height: 1.2em;">
                    <div class="progress-bar bg-success" role="progressbar" style="width: 100%" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100"></div>
                </div>`;
        } else if (estadoMayusculas === 'FAILURE') {
            celda.innerHTML = `
                <div class="progress" style="height: 1.2em;">
                    <div class="progress-bar bg-danger" role="progressbar" style="width: 100%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                </div>`;
        } else {
            celda.textContent = 'N/A';
        }
    }

    async function manejarEliminacionArchivo(idCursoActual, nombreArchivo, elementoFila) {
        if (!confirm(`¿Estás seguro de que quieres eliminar el archivo "${nombreArchivo}" de la IA? Esta acción no se puede deshacer.`)) {
            return;
        }
        actualizarEstadoGestion(`Eliminando el archivo "${nombreArchivo}"...`, 'info');
        const botonEliminar = elementoFila.querySelector('.btn-danger');
        if (botonEliminar) botonEliminar.disabled = true;
        try {
            const nombreArchivoCodificado = encodeURIComponent(nombreArchivo);
            const respuesta = await fetch(`${URL_BASE_API}/cursos/${idCursoActual}/archivos-indexados/${nombreArchivoCodificado}`, {
                method: 'DELETE'
            });

            if (!respuesta.ok) {
                let detalleError = 'No se pudo eliminar el archivo.';
                try {
                    const datosError = await respuesta.json();
                    detalleError = datosError.detail || detalleError;
                } catch (e) { console.warn('No se pudo parsear la respuesta de error como JSON para la operación de eliminación:', e); }
                actualizarEstadoGestion(`Error ${respuesta.status} al eliminar "${nombreArchivo}": ${detalleError}`, 'error');
                return;
            }
            
            actualizarEstadoGestion(`Archivo "${nombreArchivo}" eliminado exitosamente de la IA.`, 'success');
            if (elementoFila) {
                elementoFila.remove();
            }
            if (cuerpoTablaArchivos && cuerpoTablaArchivos.rows.length === 0) {
                mensajeSinArchivos.classList.remove('d-none');
            }

        } catch (errorRed) {
            console.error('Error de red al eliminar archivo:', errorRed);
            actualizarEstadoGestion(`Error de red al eliminar "${nombreArchivo}". Verifica tu conexión e inténtalo de nuevo.`, 'danger');
            if (botonEliminar) botonEliminar.disabled = false;
        }
    }

    async function manejarRefrescoArchivos(idCursoActual) {
        if (!botonRefrescarArchivosMoodle || !spinnerBotonRefrescar) return;
        
        botonRefrescarArchivosMoodle.disabled = true;
        spinnerBotonRefrescar.classList.remove('d-none');
        actualizarEstadoGestion('Solicitando revisión de archivos en Moodle...', 'info');

        try {
            const respuesta = await fetch(`${URL_BASE_API}/cursos/${idCursoActual}/refrescar-archivos`);
            let resultado;
            try {
                 resultado = await respuesta.json();
            } catch (e) {
                console.error('No se pudo parsear la respuesta de refrescar-archivos como JSON:', e);
                actualizarEstadoGestion(`Error inesperado del servidor (código ${respuesta.status}) al revisar archivos.`, 'danger');
                return;
            }

            if (!respuesta.ok) {
                const mensajeError = `Error ${respuesta.status}: ${resultado?.detail || 'No se pudo iniciar la actualización de archivos.'}`;
                actualizarEstadoGestion(mensajeError, 'danger');
                return;
            }
            
            actualizarEstadoGestion(resultado.mensaje || 'Solicitud de actualización de archivos completada.', 'success');

            if (resultado.ids_tarea && resultado.ids_tarea.length > 0) {
                mensajeSinArchivos.classList.add('d-none');
                
                resultado.ids_tarea.forEach(id_tarea => {
                    const nombreArchivoTarea = resultado.nombres_archivo_por_tarea?.[id_tarea] || `Tarea ${id_tarea.substring(0,8)}`;
                    if (!colaTareas.find(t => t.id_tarea === id_tarea) && !tareasActivas[id_tarea]) {
                        colaTareas.push({ id_tarea, nombre_archivo: nombreArchivoTarea });
                        agregarOActualizarArchivoEnTabla(id_tarea, nombreArchivoTarea, 'PENDIENTE', 0); 
                    }
                });
                procesarSiguienteEnCola(idCursoActual);
            } else if (resultado.archivos_identificados_para_procesamiento === 0) {
                actualizarEstadoGestion('No se encontraron archivos nuevos o modificados en Moodle para procesar.', 'info');
            }

        } catch (errorRed) {
            console.error('Error de red al solicitar actualización de archivos:', errorRed);
            actualizarEstadoGestion('Error de red al actualizar archivos. Verifica tu conexión.', 'danger');
        } finally {
            if (botonRefrescarArchivosMoodle && spinnerBotonRefrescar) {
                botonRefrescarArchivosMoodle.disabled = false;
                spinnerBotonRefrescar.classList.add('d-none');
            }
        }
    }
    
    function agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, estado, porcentajeProgreso, mensajeResultado = null, ultimaModificacion = 'N/A') {
        if (!cuerpoTablaArchivos) return;
        let fila = cuerpoTablaArchivos.querySelector(`tr[data-task-id="${id_tarea}"]`);
        
        if (!fila) {
            let filaArchivoExistente = cuerpoTablaArchivos.querySelector(`tr[data-file-name="${nombre_archivo}"]`);
            if (filaArchivoExistente && estado.toUpperCase() !== 'INDEXADO') {
                fila = filaArchivoExistente;
                fila.dataset.taskId = id_tarea;
            } else if (filaArchivoExistente && estado.toUpperCase() === 'INDEXADO') {
                fila = filaArchivoExistente;
            }
            else {
                fila = cuerpoTablaArchivos.insertRow(0);
                fila.dataset.taskId = id_tarea;
                fila.dataset.fileName = nombre_archivo;
                fila.insertCell();
                fila.insertCell();
                fila.insertCell();
                fila.insertCell();
                fila.insertCell();
            }
        }

        fila.cells[0].textContent = nombre_archivo;
        renderizarIndicadorEstado(fila.cells[1], estado, id_tarea);
        renderizarBarraProgreso(fila.cells[2], estado, porcentajeProgreso);
        fila.cells[3].textContent = (estado.toUpperCase() === 'INDEXADO' && ultimaModificacion !== 'N/A') ? ultimaModificacion : (fila.cells[3].textContent || 'N/A');

        fila.cells[4].innerHTML = '';
        if (estado.toUpperCase() === 'INDEXADO') {
            const botonEliminar = document.createElement('button');
            botonEliminar.textContent = 'Eliminar';
            botonEliminar.classList.add('btn', 'btn-sm', 'btn-danger');
            botonEliminar.addEventListener('click', () => manejarEliminacionArchivo(idCurso, nombre_archivo, fila));
            fila.cells[4].appendChild(botonEliminar);
        } else if (estado.toUpperCase() === 'FAILURE') {
            const textoError = document.createElement('span');
            textoError.textContent = mensajeResultado || 'Fallo';
            textoError.className = 'text-danger';
            fila.cells[4].appendChild(textoError);
        }
        
        if (mensajeSinArchivos && !mensajeSinArchivos.classList.contains('d-none')) {
            mensajeSinArchivos.classList.add('d-none');
        }
         if (cuerpoTablaArchivos.rows.length === 1 && cuerpoTablaArchivos.rows[0].cells[0].colSpan === 5) {
            cuerpoTablaArchivos.innerHTML = '';
            cuerpoTablaArchivos.appendChild(fila);
        }
    }

    function rastrearProgresoTarea(idCursoActual, id_tarea, nombre_archivo) {
        if (tareasActivas[id_tarea] && tareasActivas[id_tarea].idIntervaloSondeo) {
            clearInterval(tareasActivas[id_tarea].idIntervaloSondeo);
        }

        tareasActivas[id_tarea] = {
            ...tareasActivas[id_tarea],
            idIntervaloSondeo: null,
            estadoReal: tareasActivas[id_tarea]?.estadoReal || 'PENDIENTE',
            nombre_archivo: nombre_archivo
        };
        
        tareasActivas[id_tarea].idIntervaloSondeo = setInterval(async () => {
            if (!tareasActivas[id_tarea]) {
                const idIntervalo = tareasActivas[id_tarea]?.idIntervaloSondeo;
                if (idIntervalo) clearInterval(idIntervalo);
                return;
            }
            try {
                const respuesta = await fetch(`${URL_BASE_API}/tarea/${id_tarea}/estado`);
                let datosTarea;
                try {
                    datosTarea = await respuesta.json();
                } catch (e) {
                    console.warn(`Respuesta no JSON para tarea ${id_tarea} (HTTP ${respuesta.status}).`, e);
                    if (tareasActivas[id_tarea]) tareasActivas[id_tarea].estadoReal = 'ERROR_VERIFICACION';
                    agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, 'ERROR_VERIFICACION', tareasActivas[id_tarea]?.progresoSimulado || 0, `Respuesta inesperada (HTTP ${respuesta.status})`);
                    return;
                }

                if (!respuesta.ok) {
                    const detalleError = datosTarea?.detail || `Error HTTP ${respuesta.status}`;
                    console.warn(`No se pudo obtener estado de tarea ${id_tarea} (${detalleError}).`);
                    if (tareasActivas[id_tarea]) tareasActivas[id_tarea].estadoReal = 'ERROR_VERIFICACION';
                    agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, 'ERROR_VERIFICACION', tareasActivas[id_tarea]?.progresoSimulado || 0, detalleError);
                    return;
                }
                
                if (tareasActivas[id_tarea]) tareasActivas[id_tarea].estadoReal = datosTarea.estado;
                let progresoMostrar = tareasActivas[id_tarea]?.progresoSimulado || 0;

                if (datosTarea.estado === 'SUCCESS' || datosTarea.estado === 'FAILURE') {
                    if (tareasActivas[id_tarea]?.idFrameAnimacion) {
                        cancelAnimationFrame(tareasActivas[id_tarea].idFrameAnimacion);
                    }
                    if (tareasActivas[id_tarea]?.idIntervaloSondeo) {
                        clearInterval(tareasActivas[id_tarea].idIntervaloSondeo);
                    }
                    
                    progresoMostrar = (datosTarea.estado === 'SUCCESS') ? 100 : 0;
                    agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, datosTarea.estado, progresoMostrar, datosTarea.resultado);
                    
                    if (datosTarea.estado === 'SUCCESS') {
                        actualizarEstadoGestion(`Procesamiento de '${nombre_archivo}' completado.`, 'success');
                        const filaArchivoIndexado = cuerpoTablaArchivos.querySelector(`tr[data-task-id="${id_tarea}"]`);
                        if(filaArchivoIndexado) {
                           const fechaMod = filaArchivoIndexado.cells[3].textContent !== 'N/A' ? filaArchivoIndexado.cells[3].textContent : new Date().toLocaleString();
                           agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, 'INDEXADO', 100, null, fechaMod);
                        }
                    } else {
                        actualizarEstadoGestion(`Error al procesar '${nombre_archivo}': ${datosTarea.resultado || 'Causa desconocida'}`, 'danger');
                    }
                    delete tareasActivas[id_tarea]; 
                    procesandoActualmente = false;
                    procesarSiguienteEnCola(idCursoActual);
                } else {
                    agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, datosTarea.estado, progresoMostrar, datosTarea.resultado);
                }
            } catch (errorRed) { 
                console.error(`Error de red al rastrear tarea ${id_tarea}:`, errorRed);
                if (tareasActivas[id_tarea]) tareasActivas[id_tarea].estadoReal = 'ERROR_RED';
                agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, 'ERROR_RED', tareasActivas[id_tarea]?.progresoSimulado || 0, 'Error de conexión');
            }
        }, 5000); 
    }

    function iniciarSimulacionProgreso(id_tarea, nombre_archivo) {
        if (!tareasActivas[id_tarea]) {
             tareasActivas[id_tarea] = { idIntervaloSondeo: null, idFrameAnimacion: null, progresoSimulado: 0, estadoReal: 'PROCESANDO', nombre_archivo };
        }
        tareasActivas[id_tarea].progresoSimulado = 0;
        tareasActivas[id_tarea].estadoReal = 'PROCESANDO';

        let tiempoInicio = null;
        const duracionHasta90 = 20000;
        const duracionHasta99 = 30000;
        const objetivoRalentizacion = 90; 
        const maximoSimuladoAbsoluto = 99; 

        function animar(timestamp) {
            if (!tareasActivas[id_tarea] || tareasActivas[id_tarea].estadoReal === 'SUCCESS' || tareasActivas[id_tarea].estadoReal === 'FAILURE') {
                if(tareasActivas[id_tarea] && tareasActivas[id_tarea].idFrameAnimacion) {
                    cancelAnimationFrame(tareasActivas[id_tarea].idFrameAnimacion);
                    tareasActivas[id_tarea].idFrameAnimacion = null;
                }
                return;
            }

            if (!tiempoInicio) tiempoInicio = timestamp;
            const transcurrido = timestamp - tiempoInicio;
            let progresoSimuladoActual;

            if (tareasActivas[id_tarea].progresoSimulado < objetivoRalentizacion) {
                const ratioProgreso = Math.min(transcurrido / duracionHasta90, 1);
                progresoSimuladoActual = Math.floor(ratioProgreso * objetivoRalentizacion);
            } else {
                const transcurridoFaseLenta = Math.max(0, transcurrido - duracionHasta90);
                const ratioProgresoFaseLenta = Math.min(transcurridoFaseLenta / duracionHasta99, 1);
                progresoSimuladoActual = objetivoRalentizacion + Math.floor(ratioProgresoFaseLenta * (maximoSimuladoAbsoluto - objetivoRalentizacion));
            }
            
            tareasActivas[id_tarea].progresoSimulado = Math.min(progresoSimuladoActual, maximoSimuladoAbsoluto);
            agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, tareasActivas[id_tarea].estadoReal, tareasActivas[id_tarea].progresoSimulado);

            if (tareasActivas[id_tarea].progresoSimulado < maximoSimuladoAbsoluto && 
                (tareasActivas[id_tarea].estadoReal === 'PROCESANDO' || tareasActivas[id_tarea].estadoReal === 'PENDIENTE' || tareasActivas[id_tarea].estadoReal === 'INICIADO') ) {
                tareasActivas[id_tarea].idFrameAnimacion = requestAnimationFrame(animar);
            } else {
                 if(tareasActivas[id_tarea]) tareasActivas[id_tarea].idFrameAnimacion = null;
            }
        }
        if (tareasActivas[id_tarea].idFrameAnimacion) {
            cancelAnimationFrame(tareasActivas[id_tarea].idFrameAnimacion);
        }
        tareasActivas[id_tarea].idFrameAnimacion = requestAnimationFrame(animar);
    }

    function procesarSiguienteEnCola(idCursoActual) {
        if (procesandoActualmente || colaTareas.length === 0) {
            return;
        }

        procesandoActualmente = true;
        const siguienteTarea = colaTareas.shift();
        
        if (siguienteTarea) {
            const { id_tarea, nombre_archivo } = siguienteTarea;
            if (tareasActivas[id_tarea]) {
                console.warn(`Intento de procesar tarea ${id_tarea} que ya está en tareasActivas.`);
                procesandoActualmente = false; 
                procesarSiguienteEnCola(idCursoActual);
                return;
            }

            actualizarEstadoGestion(`Iniciando procesamiento para: ${nombre_archivo}`, 'info');
            agregarOActualizarArchivoEnTabla(id_tarea, nombre_archivo, 'PROCESANDO', 0);
            iniciarSimulacionProgreso(id_tarea, nombre_archivo);
            rastrearProgresoTarea(idCursoActual, id_tarea, nombre_archivo);
        } else {
            procesandoActualmente = false;
        }
    }

    inicializarPagina().catch(error => {
        console.error("Error crítico durante la inicialización de la página de gestión de archivos:", error);
        actualizarEstadoGestion("Ocurrió un error grave al cargar la página. Por favor, recarga.", "error");
    });
});

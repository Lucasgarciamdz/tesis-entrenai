-- Script de inicialización para la base de datos PostgreSQL con PGVector.

-- Asegura que la extensión 'vector' esté habilitada en la base de datos.
-- Esta extensión es fundamental para poder almacenar y buscar vectores de embeddings.
CREATE EXTENSION IF NOT EXISTS vector;

-- NOTA: La creación de tablas específicas para los cursos (ej. 'entrenai_curso_xxxx')
-- y la tabla de seguimiento de archivos ('seguimiento_archivos_procesados')
-- es manejada dinámicamente por la aplicación (EnvoltorioPgVector).
-- Por lo tanto, no se incluyen aquí para evitar conflictos o duplicaciones.
-- Si se necesitaran tablas globales o roles específicos, podrían añadirse aquí.

-- Ejemplo de verificación (opcional, para logs de Docker):
-- SELECT installed_version FROM pg_available_extensions WHERE name = 'vector';

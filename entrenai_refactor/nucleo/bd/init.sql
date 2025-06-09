-- Script de inicialización para la base de datos PostgreSQL con la extensión PGVector.

-- Asegura que la extensión 'vector' esté habilitada en la base de datos.
-- Esta extensión es fundamental para poder almacenar y realizar búsquedas semánticas
-- con vectores de embeddings generados por modelos de inteligencia artificial.
CREATE EXTENSION IF NOT EXISTS vector;

-- NOTA IMPORTANTE:
-- La creación de tablas específicas para los cursos (ej. aquellas con prefijo 'entrenai_vectores_curso_')
-- y la tabla de seguimiento de archivos procesados (ej. 'seguimiento_archivos_procesados')
-- es gestionada dinámicamente por la aplicación Python a través de la clase 'EnvoltorioPgVector'.
-- Por lo tanto, no se incluyen comandos CREATE TABLE para estas tablas aquí para evitar conflictos
-- o gestión duplicada del esquema.
--
-- Si se necesitaran tablas globales adicionales, roles de usuario específicos para la base de datos,
-- o configuraciones iniciales a nivel de base de datos que no sean manejadas por la aplicación,
-- podrían añadirse en este script.

-- Ejemplo de comando para verificar la instalación de la extensión (opcional, útil para depuración o logs de Docker):
-- SELECT installed_version FROM pg_available_extensions WHERE name = 'vector';
-- Esto mostrará la versión de pgvector instalada si la extensión está activa.

-- Consideraciones Adicionales (para administradores de BD):
-- 1. Roles y Permisos: Asegúrese de que el usuario de la base de datos configurado en la aplicación
--    tenga los permisos necesarios (CONNECT, CREATE, SELECT, INSERT, UPDATE, DELETE) sobre la base
--    de datos y las tablas que la aplicación gestionará.
-- 2. Configuración de PostgreSQL: Para un rendimiento óptimo con pgvector, especialmente con grandes
--    volúmenes de datos y búsquedas frecuentes, revise la configuración de PostgreSQL
--    (ej. 'shared_buffers', 'work_mem', 'maintenance_work_mem', 'max_parallel_workers_per_gather').
--    Consulte la documentación oficial de PostgreSQL y pgvector para recomendaciones.
-- 3. Backups: Implemente una estrategia de backup robusta para la base de datos.

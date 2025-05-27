# Performance Tuning for Entrenai pgvector Implementation

This document provides recommendations for tuning PostgreSQL and pgvector to achieve optimal performance with the Entrenai application.

## 1. PostgreSQL Server Configuration

These settings are typically configured in the `postgresql.conf` file or can be passed as environment variables or command-line arguments to the PostgreSQL Docker container. For the `entrenai_pgvector_db` service in `docker-compose.yml`, you can add them under the `environment` section or by modifying the `command`.

-   **`shared_buffers`**:
    -   **Recommendation**: Set to about 25% of your total system RAM. For example, if your server has 16GB RAM, set it to `4GB`.
    -   **Purpose**: Allocates memory PostgreSQL uses for caching data.
    -   **Docker Example (`docker-compose.yml`):**
        ```yaml
        services:
          pgvector_db:
            # ... other settings
            command: postgres -c shared_buffers=4GB # Example
        ```
        (Note: Modifying the command might override the default command from the image. A better way for official Postgres images is often through a custom config file or `POSTGRES_OPTIONS` if supported by the entrypoint script. For `pgvector/pgvector` specifically, check its documentation for preferred ways to pass settings. A common fallback is mounting a custom `postgresql.conf`.)

-   **`maintenance_work_mem`**:
    -   **Recommendation**: Increase significantly during large data loads and HNSW index creation. Values like `1GB` to `8GB` (or more, depending on available RAM and dataset size) are common. Can be set lower for normal operations if memory is constrained.
    -   **Purpose**: Memory used for maintenance tasks like `VACUUM`, `CREATE INDEX`, and `ALTER TABLE`. Crucial for HNSW index build performance. pgvector docs state: "Indexes build significantly faster when the graph fits into `maintenance_work_mem`".
    -   **Docker Example (`docker-compose.yml`):**
        ```yaml
        services:
          pgvector_db:
            # ... other settings
            command: postgres -c maintenance_work_mem=2GB # Example for index builds
        ```
    -   **Note**: Can also be set per session: `SET maintenance_work_mem = '2GB';` before running `CREATE INDEX`.

-   **`effective_cache_size`**:
    -   **Recommendation**: Set to about 50-75% of total system RAM.
    -   **Purpose**: Helps PostgreSQL's query planner estimate the amount of memory available for caching data by the OS and within PostgreSQL itself.

-   **PgTune**:
    -   For a good set of initial baseline parameters, consider using a tool like [PgTune](https://pgtune.leopard.in.ua/).

## 2. pgvector HNSW Indexing Parameters

These parameters are set during index creation (`CREATE INDEX ... USING hnsw (...) WITH (...)`). The current application code creates HNSW indexes with default parameters. If you need to fine-tune for specific datasets (e.g., by dropping and recreating the index manually or modifying the `ensure_table` method):

-   **`m`**:
    -   **Default**: 16
    -   **Purpose**: The maximum number of connections per layer in the HNSW graph.
    -   **Impact**: Higher `m` values can improve recall and query speed for high-dimensional data but increase index build time, memory usage, and index size.

-   **`ef_construction`**:
    -   **Default**: 64
    -   **Purpose**: The size of the dynamic candidate list used during index construction.
    -   **Impact**: Higher `ef_construction` values lead to better quality indexes (higher recall) but significantly increase index build time.

## 3. pgvector HNSW Query Parameters

-   **`hnsw.ef_search`**:
    -   **Default**: 40
    -   **Purpose**: The size of the dynamic candidate list used during a search.
    -   **Impact**: Higher `ef_search` values improve recall (finding more accurate nearest neighbors) at the cost of query speed. Lower values are faster but may miss some relevant results.
    -   **Tuning**: The Entrenai application's `search_chunks` method now accepts an `ef_search_value` parameter, allowing this to be tuned per query. Experiment with different values based on your recall and latency requirements.
        ```sql
        -- Example of setting it for a session
        SET hnsw.ef_search = 100; 
        -- The application uses SET LOCAL for per-query tuning.
        ```

## 4. Data Ingestion

-   **Batch Upserts**: The application's `PgvectorWrapper` now uses `psycopg2.extras.execute_values` for `upsert_chunks`, which is more efficient for inserting multiple rows than individual `INSERT` statements.
-   **Initial Bulk Loading**: For extremely large initial datasets (millions of vectors), pgvector documentation recommends using the `COPY` command for the best performance. This would typically be done via a separate script before the application starts managing the data.

## 5. Vacuuming and Maintenance

Regular database maintenance is crucial for performance.

-   **`VACUUM` and `ANALYZE`**:
    -   Run `VACUUM` regularly to reclaim storage occupied by dead tuples.
    -   Run `ANALYZE` to update statistics for the query planner.
    -   PostgreSQL's autovacuum daemon handles this automatically, but its settings might need tuning for write-heavy workloads.
-   **HNSW Index Vacuuming**:
    -   pgvector documentation notes that vacuuming HNSW indexes can be slow.
    -   **Recommendation**: To speed up vacuuming for tables with HNSW indexes, reindex the index concurrently before vacuuming:
        ```sql
        REINDEX INDEX CONCURRENTLY your_hnsw_index_name;
        VACUUM your_table_name;
        ```
    -   `CREATE INDEX CONCURRENTLY` should be used in production to avoid blocking writes when initially creating indexes on tables with existing data.

Remember to monitor your database performance and adjust these settings based on your specific workload and available resources.

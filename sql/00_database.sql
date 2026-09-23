-- Ejecutar conectado como usuario administrador de PostgreSQL, por ejemplo:
-- psql -U postgres -d postgres -f sql/00_database.sql
--
-- Cambia app_password antes de usar este archivo fuera de desarrollo local.

\set ON_ERROR_STOP on
\set db_name 'kpi_command_center'
\set app_user 'kpi_user'
\set app_password 'change_me_strong_password'

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname = :'app_user'
);
\gexec

SELECT format(
    'CREATE DATABASE %I OWNER %I ENCODING %L TEMPLATE template0',
    :'db_name',
    :'app_user',
    'UTF8'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_database
    WHERE datname = :'db_name'
);
\gexec

\connect :db_name

GRANT CONNECT ON DATABASE :db_name TO :app_user;
GRANT USAGE, CREATE ON SCHEMA public TO :app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO :app_user;

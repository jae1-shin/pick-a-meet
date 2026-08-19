\set ON_ERROR_STOP on

\if :{?app_database}
\else
  \set app_database pick_a_meet
\endif

\if :{?app_user}
\else
  \set app_user pick_a_meet_app
\endif

\if :{?app_password}
\else
  \prompt 'Password for the Pick a Meet database role: ' app_password
\endif

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L',
    :'app_user',
    :'app_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'app_user'
) \gexec

SELECT format(
    'ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'app_user',
    :'app_password'
) \gexec

SELECT format(
    'CREATE DATABASE %I OWNER %I',
    :'app_database',
    :'app_user'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = :'app_database'
) \gexec

SELECT format(
    'ALTER DATABASE %I OWNER TO %I',
    :'app_database',
    :'app_user'
) \gexec

\connect :app_database

SELECT format('ALTER SCHEMA public OWNER TO %I', :'app_user') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'app_user') \gexec

\echo 'Database and application role are ready. Run: alembic upgrade head'

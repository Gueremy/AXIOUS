CREATE DATABASE salmonera_db;
CREATE USER salmonera_user WITH PASSWORD 'salmonera2026';
GRANT ALL PRIVILEGES ON DATABASE salmonera_db TO salmonera_user;
\c salmonera_db
GRANT ALL ON SCHEMA public TO salmonera_user;

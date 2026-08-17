SELECT 'CREATE DATABASE colacci_test OWNER colacci_demo'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'colacci_test')\gexec

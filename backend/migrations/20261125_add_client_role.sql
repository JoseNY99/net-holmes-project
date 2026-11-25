ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_rol;
ALTER TABLE users
  ADD CONSTRAINT ck_users_rol
  CHECK (rol IN ('sup_admin', 'admin', 'analista', 'cliente'));

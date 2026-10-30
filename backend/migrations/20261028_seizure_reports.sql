-- Migración aditiva del módulo Informes de Allanamiento.
-- Compatible con PostgreSQL. No elimina ni modifica tablas existentes.
BEGIN;

ALTER TABLE reportes_brand_defense ADD COLUMN IF NOT EXISTS codigo_interno VARCHAR(100);
ALTER TABLE reportes_brand_defense ADD COLUMN IF NOT EXISTS tipo_informe VARCHAR(30) NOT NULL DEFAULT 'INTELIGENCIA';
ALTER TABLE reportes_brand_defense ADD COLUMN IF NOT EXISTS numero_caso_cliente VARCHAR(100);
ALTER TABLE reportes_brand_defense ADD COLUMN IF NOT EXISTS codigo_marca VARCHAR(10);
CREATE UNIQUE INDEX IF NOT EXISTS ux_reportes_brand_defense_codigo_interno
  ON reportes_brand_defense(codigo_interno) WHERE codigo_interno IS NOT NULL;

CREATE TABLE IF NOT EXISTS seizure_reports (
  id SERIAL PRIMARY KEY, internal_reference VARCHAR(30) UNIQUE,
  client_case_number VARCHAR(100), status VARCHAR(40) NOT NULL DEFAULT 'BORRADOR',
  country VARCHAR(100) NOT NULL DEFAULT 'Argentina', province VARCHAR(120), city VARCHAR(120),
  operation_date DATE, case_origin VARCHAR(200), action_type VARCHAR(120), report_type VARCHAR(30) NOT NULL DEFAULT 'ALLANAMIENTO', client_name VARCHAR(200),
  brand_id INTEGER REFERENCES brands(id), brand_name VARCHAR(200), brand_code VARCHAR(10),
  investigator VARCHAR(200), general_notes TEXT, police_agency TEXT, police_unit TEXT,
  court TEXT, judge TEXT, prosecution TEXT, prosecutor TEXT,
  court_case_number VARCHAR(100), authorities_notes TEXT, media_impact TEXT, political_impact TEXT,
  proposed_fees VARCHAR(100), currency VARCHAR(10) DEFAULT 'USD', internal_comments TEXT,
  background TEXT, operation_summary TEXT, seized_goods_total INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE seizure_reports ADD COLUMN IF NOT EXISTS report_type VARCHAR(30) NOT NULL DEFAULT 'ALLANAMIENTO';
ALTER TABLE seizure_reports ALTER COLUMN police_agency TYPE TEXT;
ALTER TABLE seizure_reports ALTER COLUMN police_unit TYPE TEXT;
ALTER TABLE seizure_reports ALTER COLUMN court TYPE TEXT;
ALTER TABLE seizure_reports ALTER COLUMN judge TYPE TEXT;
ALTER TABLE seizure_reports ALTER COLUMN prosecution TYPE TEXT;
ALTER TABLE seizure_reports ALTER COLUMN prosecutor TYPE TEXT;
CREATE INDEX IF NOT EXISTS ix_seizure_reports_reference ON seizure_reports(internal_reference);
CREATE INDEX IF NOT EXISTS ix_seizure_reports_status ON seizure_reports(status);
CREATE INDEX IF NOT EXISTS ix_seizure_reports_brand_id ON seizure_reports(brand_id);
CREATE INDEX IF NOT EXISTS ix_seizure_reports_report_type ON seizure_reports(report_type);

CREATE TABLE IF NOT EXISTS seizure_targets (
  id SERIAL PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES seizure_reports(id) ON DELETE CASCADE,
  establishment_name VARCHAR(250), address VARCHAR(350) NOT NULL, city VARCHAR(120), province VARCHAR(120),
  country VARCHAR(100), description TEXT, investigated_party TEXT, notes TEXT
);
ALTER TABLE seizure_targets ALTER COLUMN investigated_party TYPE TEXT;
CREATE INDEX IF NOT EXISTS ix_seizure_targets_report_id ON seizure_targets(report_id);

CREATE TABLE IF NOT EXISTS seizure_products (
  id SERIAL PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES seizure_reports(id) ON DELETE CASCADE,
  brand_name VARCHAR(200) NOT NULL, client_name VARCHAR(200), category VARCHAR(150), description TEXT,
  quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0), unit VARCHAR(50) NOT NULL DEFAULT 'unidades',
  establishment VARCHAR(250), notes TEXT
);
CREATE INDEX IF NOT EXISTS ix_seizure_products_report_id ON seizure_products(report_id);

CREATE TABLE IF NOT EXISTS seizure_files (
  id SERIAL PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES seizure_reports(id) ON DELETE CASCADE,
  kind VARCHAR(30) NOT NULL, document_type VARCHAR(80), original_name VARCHAR(255) NOT NULL,
  stored_name VARCHAR(255) NOT NULL UNIQUE, mime_type VARCHAR(100) NOT NULL, size_bytes INTEGER NOT NULL,
  position INTEGER NOT NULL DEFAULT 0, caption TEXT, brand_name VARCHAR(200), establishment VARCHAR(250),
  include_in_report BOOLEAN NOT NULL DEFAULT TRUE, uploaded_by INTEGER NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_seizure_files_report_id ON seizure_files(report_id);

CREATE TABLE IF NOT EXISTS seizure_history (
  id SERIAL PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES seizure_reports(id) ON DELETE CASCADE,
  from_status VARCHAR(40), to_status VARCHAR(40) NOT NULL, comment TEXT,
  user_id INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_seizure_history_report_id ON seizure_history(report_id);

CREATE TABLE IF NOT EXISTS seizure_sequences (
  id SERIAL PRIMARY KEY, scope VARCHAR(30) NOT NULL UNIQUE, last_value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS seizure_document_versions (
  id SERIAL PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES seizure_reports(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, format VARCHAR(10) NOT NULL, stored_name VARCHAR(255) NOT NULL,
  generated_by INTEGER NOT NULL REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_seizure_version_format UNIQUE(report_id, version, format)
);
CREATE INDEX IF NOT EXISTS ix_seizure_versions_report_id ON seizure_document_versions(report_id);

CREATE TABLE IF NOT EXISTS seizure_audit_events (
  id SERIAL PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES seizure_reports(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id), action VARCHAR(60) NOT NULL,
  entity_type VARCHAR(60) NOT NULL DEFAULT 'report', entity_id INTEGER, details TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_seizure_audit_report_id ON seizure_audit_events(report_id);
CREATE INDEX IF NOT EXISTS ix_seizure_audit_user_id ON seizure_audit_events(user_id);
CREATE INDEX IF NOT EXISTS ix_seizure_audit_action ON seizure_audit_events(action);
CREATE INDEX IF NOT EXISTS ix_seizure_audit_created_at ON seizure_audit_events(created_at);

COMMIT;

-- Rollback seguro recomendado: retirar el router y conservar las tablas.
-- No se incluyen DROP TABLE para evitar pérdida accidental de informes y evidencias.

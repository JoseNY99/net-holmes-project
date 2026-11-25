BEGIN;

ALTER TABLE reporte_facebook_data
  ALTER COLUMN item_condition TYPE TEXT;

ALTER TABLE reporte_mercadolibre_data
  ALTER COLUMN item_condition TYPE TEXT;

COMMIT;

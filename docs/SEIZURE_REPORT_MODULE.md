# Informes de Allanamiento / Seizure Report

El módulo se integra al FastAPI, React, JWT, PostgreSQL y almacenamiento persistente actuales. No modifica scrapers ni reportes de Brand Defense.

## Componentes

- API: `/api/seizure-reports`
- Modelos: `backend/models/seizure_report.py`
- Servicio documental y almacenamiento: `backend/services/seizure_report_service.py`
- Interfaz: `/seizure-reports`
- Archivos persistentes: `backend/assets/seizure_reports`, montado como `/app/assets` por Docker Compose
- Migración SQL: `backend/migrations/20261028_seizure_reports.sql`

La interfaz permite crear y editar borradores, registrar domicilios y productos, adjuntar documentos y fotografías, describir, incluir, eliminar y ordenar evidencias, revisar el historial y generar Word/PDF. La aprobación interna requiere rol `admin` o `sup_admin` y asigna la referencia `XXX-AA-MARCA` dentro de una transacción.

Las selecciones de fotografías y documentos son acumulativas: el usuario puede elegir varios archivos juntos, volver a abrir el selector o arrastrar nuevas tandas sin reemplazar las anteriores. Cada fotografía admite descripción, marca/cliente y establecimiento. El informe puede generarse como borrador, pero no avanzar a revisión sin acta, fotografías, objetivo y cantidades; tampoco puede aprobarse internamente mientras existan cantidades pendientes de distribución o fotografías sin clasificar en expedientes con varios clientes.

## Decisiones documentadas

- No existe un catálogo de clientes en el proyecto; el cliente se registra como texto y las marcas reutilizan `brands`.
- El correlativo es global y no se reinicia automáticamente. El material suministrado no confirma reinicio anual ni por marca.
- `python-docx` genera el Word editable. ReportLab genera el PDF para evitar depender de conversiones variables de LibreOffice. Los PDF seleccionados se ensamblan al PDF final con `pypdf`; en Word se incorpora su texto extraíble.
- Los textos legales se conservan en inglés y no se traducen automáticamente.

## Despliegue

1. Respaldar PostgreSQL y `backend/assets`.
2. Incorporar el commit y reconstruir backend y frontend.
3. Iniciar el backend. El mecanismo existente `Base.metadata.create_all()` crea las tablas de forma idempotente. En entornos con migraciones controladas, aplicar el SQL provisto antes del arranque.
4. Confirmar que `./backend/assets:/app/assets` permanezca montado en producción.
5. Entrar con un usuario autenticado y crear un borrador de prueba.

No se requieren variables de entorno nuevas. La dependencia agregada es `pypdf==6.1.1`.

## Respaldo y rollback

Respaldar antes del despliegue:

```bash
pg_dump -Fc operativa_db > operativa_db_pre_seizure.dump
tar -czf seizure_assets_backup.tgz backend/assets
```

Para rollback de aplicación, volver al commit anterior y reconstruir los servicios. Conservar las tablas `seizure_*` y la carpeta de archivos para evitar pérdida de información. La migración no altera tablas existentes y no contiene `DROP` ni `TRUNCATE`.

## Verificación realizada

- Compilación de las imágenes Docker de backend y frontend.
- Importación completa de FastAPI y registro de rutas.
- CRUD aislado, cálculo de cantidades, historial, transiciones y referencia interna en SQLite.
- Apertura de Word y PDF generados.
- Maquetación PDF con 0, 1, 5, 20 y 50 fotografías horizontales y verticales.
- Lectura del PDF corporativo suministrado. Al tratarse de un informe final y no de un acta policial etiquetada, no produjo campos automáticos y se conserva como adjunto.

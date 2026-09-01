"""
Script para reiniciar y vaciar la base de datos de reportes, escaneos e investigaciones
dejando intactas las Marcas, Usuarios y Configuraciones.
Compatible con PostgreSQL y SQLite.
"""
import os
import shutil
from pathlib import Path
from sqlalchemy import text
from database import engine

def clean_investigations():
    tables_to_clean = [
        "messages",
        "conversations",
        "audit_logs",
        "correlation_links",
        "correlation_clusters",
        "rag_memory",
        "perfil_investigacion",
        "reporte_facebook_data",
        "reporte_instagram_data",
        "reporte_mercadolibre_data",
        "reporte_tiktok_data",
        "reportes_brand_defense"
    ]
    
    print("🧹 Iniciando limpieza de reportes, escaneos e investigaciones...")
    
    with engine.connect() as conn:
        for table in tables_to_clean:
            try:
                # Intento con TRUNCATE CASCADE (PostgreSQL) o DELETE (SQLite)
                conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
                conn.commit()
                print(f"  ✓ Tabla '{table}' vaciada con éxito.")
            except Exception:
                conn.rollback()
                try:
                    conn.execute(text(f"DELETE FROM {table};"))
                    conn.commit()
                    print(f"  ✓ Tabla '{table}' vaciada (DELETE).")
                except Exception as e:
                    conn.rollback()
                    print(f"  ⚠️ Error en tabla '{table}': {e}")
                    
    # Limpiar archivos de imágenes temporales / evidencias descargadas
    base_dir = Path(__file__).resolve().parent
    static_dirs = [base_dir / "static" / "evidencias", base_dir / "static" / "screenshots"]
    for s_dir in static_dirs:
        if s_dir.exists():
            for f in s_dir.glob("*.*"):
                try:
                    f.unlink()
                except Exception:
                    pass
            print(f"  ✓ Archivos estáticos en '{s_dir.name}' eliminados.")

    print("\n✨ ¡Limpieza completada! El sistema está en 0 escaneos listo para el nuevo scraping.")

if __name__ == "__main__":
    clean_investigations()

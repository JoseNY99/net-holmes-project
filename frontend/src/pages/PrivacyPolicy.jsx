import React from 'react';

export default function PrivacyPolicy() {
  return (
    <div style={{
      maxWidth: '850px',
      margin: '40px auto',
      padding: '30px 24px',
      backgroundColor: 'var(--card-bg, #161b22)',
      borderRadius: '12px',
      border: '1px solid var(--border-color, #30363d)',
      color: 'var(--text-primary, #e6edf3)',
      lineHeight: '1.7',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    }}>
      <h1 style={{ color: 'var(--accent-primary, #10c5c9)', fontSize: '2rem', marginBottom: '10px' }}>
        Política de Privacidad de Net Holmes
      </h1>
      <p style={{ color: 'var(--text-secondary, #8b949e)', fontSize: '0.9rem', marginBottom: '24px' }}>
        <strong>Última actualización:</strong> Septiembre 2026
      </p>

      <section style={{ marginBottom: '24px' }}>
        <h2 style={{ color: '#58a6ff', fontSize: '1.3rem', marginBottom: '8px' }}>1. Información General</h2>
        <p>
          Net Holmes es una plataforma integral de inteligencia OSINT, defensa de propiedad intelectual y análisis de 
          infracciones comerciales en línea. Esta política describe cómo se recopila, utiliza y protege la información en 
          nuestros servicios y canales de comunicación oficiales, incluyendo la plataforma WhatsApp Business Cloud API.
        </p>
      </section>

      <section style={{ marginBottom: '24px' }}>
        <h2 style={{ color: '#58a6ff', fontSize: '1.3rem', marginBottom: '8px' }}>2. Tratamiento y Uso de la Información</h2>
        <p>
          Las interacciones y datos recopilados a través de canales automatizados se utilizan exclusivamente para:
        </p>
        <ul style={{ paddingLeft: '20px', marginTop: '8px' }}>
          <li>Verificación y análisis pericial de autenticidad de productos y transacciones comerciales.</li>
          <li>Generación de reportes de auditoría y evidencia técnica de infracciones de marca.</li>
          <li>Comunicación y coordinación en el marco de investigaciones legítimas de propiedad industrial.</li>
        </ul>
        <p style={{ marginTop: '10px' }}>
          <strong>No comercialización:</strong> Net Holmes no vende, arrienda ni comparte datos personales con terceros para 
          fines publicitarios o comerciales externos.
        </p>
      </section>

      <section style={{ marginBottom: '24px' }}>
        <h2 style={{ color: '#58a6ff', fontSize: '1.3rem', marginBottom: '8px' }}>3. Seguridad y Confidencialidad</h2>
        <p>
          Toda la información procesada se resguarda bajo estrictas medidas de cifrado en tránsito (TLS/HTTPS) y en reposo, 
          conforme a los estándares de la industria y las normativas aplicables de protección de datos personales.
        </p>
      </section>

      <section style={{ marginBottom: '24px' }}>
        <h2 style={{ color: '#58a6ff', fontSize: '1.3rem', marginBottom: '8px' }}>4. Contacto y Derechos de los Titulares</h2>
        <p>
          Para ejercer derechos de acceso, rectificación, actualización o supresión de datos, o para cualquier consulta relativa a 
          esta política, comuníquese con nuestro equipo de cumplimiento:
        </p>
        <div style={{ marginTop: '10px', padding: '12px 16px', background: 'rgba(16, 197, 201, 0.08)', borderRadius: '8px', border: '1px solid rgba(16, 197, 201, 0.3)' }}>
          <strong>Correo de Cumplimiento:</strong> compliance@netholmes.tech<br />
          <strong>Sitio Oficial:</strong> https://netholmes.tech
        </div>
      </section>
    </div>
  );
}

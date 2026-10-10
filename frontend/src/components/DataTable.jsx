// Tabla de Datos Reutilizable — con efectos premium
import { FaInbox } from 'react-icons/fa';
import './DataTable.css';

export default function DataTable({ columns, data, emptyMessage = 'No hay datos disponibles', onRowClick }) {
  return (
    <div className="glass-card data-table-container">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>
                <div className="data-table__empty">
                  <div className="data-table__empty-icon">
                    <FaInbox />
                  </div>
                  <p className="data-table__empty-text">{emptyMessage}</p>
                </div>
              </td>
            </tr>
          ) : (
            data.map((row, index) => (
              <tr 
                key={row.id || index} 
                onClick={() => onRowClick && onRowClick(row)}
                style={onRowClick ? { cursor: 'pointer' } : {}}
              >
                {columns.map((col) => (
                  <td key={col.key}>
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

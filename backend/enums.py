from enum import Enum


class EstadoReporte(str, Enum):
    PENDIENTE = "Pendiente"
    SOSPECHOSO = "Sospechoso"
    INVESTIGANDO = "Investigando"
    CONFIRMADO = "Confirmado"
    DESCARTADO = "Descartado"
    SIMULACION = "Simulación"
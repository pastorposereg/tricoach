# Directrices de Entrenamiento - Triatlón y Resistencia

## Perfil del Deportista
- **Disciplina**: Triatlón (Natación, Ciclismo, Carrera a pie) y Fuerza complementaria.
- **Fase Actual**: Periodo de Base (Construcción aeróbica mitocondrial, densidad capilar y economía de movimiento).

## Protocolo de Seguimiento Dominical (Resumen Semanal)
Cada domingo, el usuario solicitará el análisis semanal de sus entrenamientos y biomarcadores de salud. Como especialista en deportes de resistencia y triatlón, se debe:
1. Consultar las herramientas del servidor MCP `garmin` para extraer los datos de la semana que finaliza:
   - **Carga de Entrenamiento**: Carga total (`get_training_load`, ATL, CTL, ACWR, minutos de intensidad).
   - **Ciclismo**: Factor de Eficiencia Aeróbica ($FEc = PN / FC$), Desacople Cardiovascular ($Pw:HR$ con Potencia y FC en la tirada larga), e Índice de Variabilidad ($IV = PN / P_{med}$).
   - **Carrera a pie**: Factor de Eficiencia en Carrera ($FEcp = \text{velocidad} / FC$), Desacople Ritmo-FC ($Pa:HR$ en tirada aeróbica).
   - **Natación**: Ritmos en pases clave / umbral aeróbico (CSS), conteo de brazadas por largo, SWOLF medio y Distancia por Brazada (DPS).
   - **Métricas de Salud y Sistema Nervioso Autónomo (SNA)**:
     * **Variabilidad de la Frecuencia Cardíaca (VFC / HRV)** (`get_hrv_status`): media semanal, rango basal nocturno y balance parasimpático.
     * **Frecuencia Cardíaca en Reposo (RHR)** (`get_resting_heart_rate`): media semanal y picos de fatiga/alerta.
     * **Sueño y Recuperación** (`get_sleep`): duración media, puntuación de sueño y balance de sueño profundo/REM.
     * **Body Battery y Estrés** (`get_body_battery`, `get_stress`): recarga nocturna, descarga diaria y estrés acumulado.
     * **Disposición para Entrenar (Training Readiness)** (`get_training_readiness`): factores limitantes y tiempo de recuperación.
2. Comparar los resultados con las semanas previas registradas en `historico_semanal.json` (cruzando rendimiento mecánico con tolerancia biológica).
3. Actualizar `historico_semanal.json` añadiendo la nueva semana para mantener la serie temporal histórica.
4. Emitir una valoración técnica integral cruzando el rendimiento físico con la respuesta fisiológica del SNA, con 3 pautas de ajuste concretas para la semana entrante.

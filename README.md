---
title: TriCoach Platform
emoji: 🏊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# TriCoach Pro - Plataforma de Rendimiento y Salud para Triatlón

Aplicación web progresiva (PWA) de alto rendimiento, optimizada tanto para **ordenador** como para **teléfono móvil**, diseñada específicamente para triatletas de resistencia.

Integra directamente tus datos de **Garmin Connect** (actividades y métricas de bienestar), **Intervals.icu** (entrenamientos planificados, umbrales y curvas PMC) y un **Coach IA especialista en triatlón**.

---

## 🚀 Inicio Rápido

### En tu Ordenador (Windows)
Simplemente haz doble clic en el archivo:
```bat
run.bat
```
O desde la consola con `uv`:
```bash
uv run --python 3.12 --with-requirements requirements.txt python run.py
```
Abre tu navegador en: **`http://localhost:8000`**

### En tu Teléfono Móvil
Conecta tu teléfono a la **misma red Wi-Fi** y abre en el navegador:
👉 **`http://192.168.1.135:8000`**

> **💡 Consejo PWA**: En Safari (iOS) o Chrome (Android), pulsa en *Compartir / Opciones* y selecciona **"Añadir a la pantalla de inicio"** para usarla a pantalla completa como una aplicación móvil nativa.

---

## 📋 Características Principales

### 1. Integración con Garmin Connect & Intervals.icu
- **Garmin Connect**:
  - Inicia sesión con tus credenciales (email y contraseña) o utiliza automáticamente la sesión activa persistida en tu equipo.
  - Sincroniza todas las actividades, tiempos por laps/splits, distribución de FC en zonas, y métricas de bienestar: **VFC / HRV, FC en Reposo (RHR), Puntuación de Sueño, Body Battery, Estrés y Disposición para Entrenar (Training Readiness)**.
- **Intervals.icu**:
  - Introduce tu Athlete ID y tu API Key (obtenida en *Intervals.icu > Settings > Developer Settings*).
  - Descarga automáticamente tus entrenamientos planificados, umbrales de potencia (FTP), umbrales de natación (CSS), ritmos umbral de carrera y zonas personalizadas.

---

### 2. Página 1: Semana y Entrenamientos
- **Navegación Semanal**: Visualiza la semana actual con botones intuitivos para navegar a semanas anteriores o futuras.
- **Calendario de 7 Días (Lunes a Domingo)**:
  - Tarjetas de cada día con indicadores fisiológicos del Sistema Nervioso Autónomo (VFC / RHR).
  - **Planificado**: Entrenamientos programados por disciplina (🏊 Natación, 🚴 Ciclismo, 🏃 Carrera, 🏋️ Fuerza), duración objetivo, distancia y TSS.
  - **Realizado**: Actividades completadas registradas en Garmin, indicando duración, distancia, FC media y factor de eficiencia.
- **Cuadro Resumen de Fin de Semana (Tiempos en Zonas Planificados vs Realizados)**:
  - Comparativa detallada por disciplina: Natación, Ciclismo, Carrera a pie y Fuerza.
  - Horas totales y cargas (TSS) planificadas vs completadas con porcentaje de cumplimiento.
  - Desglose zona por zona (**Z1 Recuperación, Z2 Base Aeróbica, Z3 Tempo, Z4 Umbral, Z5 VO2 Máx**) con barras visuales comparativas de minutos planificados vs ejecutados.

---

### 3. Modal de Análisis de Entrenamiento & Desacople
Al hacer clic en cualquier actividad completada, se abre una ventana con:
- **Factor de Eficiencia Aeróbica**:
  - Ciclismo: $FEc = \frac{\text{Potencia Normalizada } (NP)}{\text{FC Media}}$ (W/bpm) e Índice de Variabilidad ($IV = \frac{NP}{P_{\text{med}}}$).
  - Carrera a pie: $FEcp = \frac{\text{Velocidad en m/min}}{\text{FC Media}}$ y ritmo medio (min/km).
  - Natación: SWOLF medio, Distancia por Brazada ($DPS$) y ritmo cada 100m.
- **Desacople Cardiovascular ($Pw:HR$ en bici o $Pa:HR$ en carrera)**:
  - Desglose matemático comparando la 1ª mitad del entrenamiento vs la 2ª mitad.
  - Diagnóstico técnico de la deriva cardíaca:
    - `< 3.0%`: Desacople mínimo / Excelente economía aeróbica mitocondrial.
    - `3.0% - 5.0%`: Normal dentro de tolerancia para volumen de base.
    - `> 5.0%`: Alerta de deriva cardíaca por vaciamiento glucogénico, calor o deshidratación.
- **Gráfica interactiva de splits / laps**.
- **Informe del Entrenador Experto en Triatlón (Coach IA)**:
  1. *Calidad del Estímulo y Control de Ritmo*.
  2. *Eficiencia Mecánica y Desacople Cardiovascular*.
  3. *Respuesta Fisiológica y Sistema Nervioso Autónomo*.
  4. *Pautas de Ajuste para la Siguiente Sesión*.

---

### 4. Página 2: Estado de Forma (PMC) & Coach IA
- **Gráfica de Estado de Forma (Performance Management Chart)**:
  - Curva de **Forma / Fitness (CTL - Carga Crónica, 42 días)**.
  - Curva de **Fatiga (ATL - Carga Aguda, 7 días)**.
  - Curva de **Frescura / Balance (TSB = CTL - ATL)**.
  - Filtros temporales: 30 días, 60 días, 90 días, 180 días, 1 año.
  - Ratio de Carga Aguda:Crónica (**ACWR**) y semáforo de riesgo lesional.
  - Bandas de color con las zonas de TSB (Pico de forma, Neutro, Sobrecarga productiva, Fatiga crítica).
- **Chatbot Integrado con el Coach IA**:
  - Asistente conversacional especializado en triatlón y resistencia.
  - Conoce en tiempo real tu CTL, ATL, TSB, tu fase actual (Periodo de Base Aeróbica), tu VFC basal y tus entrenamientos recientes.
  - Botones de preguntas rápidas sobre balance de fatiga, interpretación de desacople y ajuste de tiradas largas.
  - Compatible con la API de **Gemini** (si introduces tu clave en Ajustes) y con un motor de heurística experta de triatlón sin necesidad de API key externa.

---

## 🛠️ Estructura del Proyecto

```
c:\Users\Pastor\Documents\Antigravity\
├── backend/
│   ├── config.py             # Configuración, umbrales y almacenamiento seguro
│   ├── garmin_service.py     # Cliente Garmin Connect (actividades, splits, bienestar)
│   ├── intervals_service.py  # Cliente Intervals.icu (planificación, umbrales, PMC)
│   ├── metrics.py            # Fórmulas de FEc, FEcp, Pw:HR, Pa:HR, SWOLF y PMC
│   ├── ai_coach.py           # Evaluador de entrenamientos y Chatbot de triatlón
│   ├── data_manager.py       # Orquestador unificado de datos y calendario semanal
│   └── main.py               # API REST FastAPI y servidor de archivos estáticos
├── static/
│   ├── css/app.css           # Estilos oscuros modernos y soporte para móviles
│   ├── js/app.js             # Controlador principal y gestión de navegación
│   ├── js/charts.js          # Gráficas interactivas con Chart.js
│   ├── icons/                # Iconos PWA (SVG)
│   ├── manifest.json         # Manifiesto de aplicación PWA para móviles
│   ├── sw.js                 # Service Worker para funcionamiento offline
│   └── index.html            # Interfaz Single Page Application (SPA)
├── historico_semanal.json    # Histórico de semanas previas registradas
├── run.py                    # Script de ejecución en 0.0.0.0:8000
├── run.bat                   # Lanzador directo de Windows
└── requirements.txt          # Dependencias de Python
```

# Cerebro Kindle — Búsqueda Híbrida de Subrayados

Una app de una sola página (HTML + JS vanilla) que convierte tus subrayados de Kindle en un motor de búsqueda inteligente que combina búsqueda semántica con búsqueda por palabras clave. Corre completamente en el browser, sin servidor, sin backend, sin instalar nada.

---

## ¿Qué hace?

Tomás tus subrayados de Kindle (`My_Clippings.txt`) y podés buscarlos de dos maneras al mismo tiempo:

- **Búsqueda por keywords**: encuentra fragmentos que contienen exactamente las palabras que escribís
- **Búsqueda semántica**: encuentra fragmentos que hablan del mismo *concepto*, aunque usen palabras completamente distintas

Un slider te deja mezclar ambos modos en tiempo real: desde "solo keywords" hasta "solo semántico", pasando por cualquier punto intermedio.

---

## Cómo usarla

### Primera vez
1. Abrí el archivo `kindle_hibrido.html` en tu browser (Chrome o Edge recomendado)
2. Conectá tu Kindle a la computadora y encontrá el archivo `My_Clippings.txt` (está en la carpeta `documents/` del dispositivo)
3. Arrastrá el archivo al área de carga, o hacé click en "Seleccionar archivo"
4. La app va a:
   - Parsear y limpiar tus subrayados (~5 segundos)
   - Descargar el modelo de IA (~23MB, solo la primera vez — queda cacheado en el browser)
   - Generar los embeddings semánticos para cada fragmento (puede tardar 1-3 minutos dependiendo de cuántos subrayados tengas)
5. Una vez listo, buscá cualquier idea, concepto o pregunta

### Veces siguientes (modo rápido ⚡)
Después del primer procesamiento, hacé click en **"⬇ Guardar índice"**. Esto descarga un archivo `.kindle-index.json` con tus subrayados + sus embeddings ya calculados.

La próxima vez podés cargar ese `.json` directamente: arranca en segundos, sin descargar ni reprocesar nada.

---

## Arquitectura técnica

### Stack

| Componente | Tecnología |
|---|---|
| UI & lógica | HTML + JavaScript vanilla (ES Modules) |
| Modelo de embeddings | `Xenova/all-MiniLM-L6-v2` (384 dimensiones) |
| Runtime de ML en browser | `@xenova/transformers` v2.17.2 (WebAssembly + ONNX) |
| Tipografía | Google Fonts — Playfair Display + DM Sans |
| Sin backend | Todo corre en el browser del usuario |

### Pipeline de procesamiento

```
My_Clippings.txt
      │
      ▼
1. PARSEO
   • Split por "=========="
   • Extrae: título, autor, fecha, texto
   • Maneja BOM (byte-order mark)
   • Parsea fechas en español ("Añadido el lunes, 15 de enero de 2024")
   • Descarta bookmarks (marcadores sin texto)
   • Requiere mínimo 60 caracteres por fragmento
      │
      ▼
2. FILTRADO Y DEDUPLICACIÓN
   • Descarta fragmentos > 900 caracteres (demasiado largos)
   • Ordena por longitud (prioriza fragmentos más ricos)
   • Deduplica: usa los primeros 80 caracteres como fingerprint
   • Cap de 80 subrayados por libro (evita que un libro domine los resultados)
      │
      ▼
3. GENERACIÓN DE EMBEDDINGS
   • Modelo: Xenova/all-MiniLM-L6-v2 (~23MB, cacheado en browser)
   • Procesa en batches de 32 fragmentos
   • Pooling: mean pooling con normalización L2
   • Resultado: vector Float32 de 384 dimensiones por fragmento
      │
      ▼
4. ÍNDICE LISTO
   • Array de clippings (texto + metadata)
   • Array de embeddings (Float32Array de 384 dims)
```

### Motor de búsqueda híbrida

Cuando el usuario escribe una consulta:

```
Query: "impacto de las redes sociales en la atención"
                │
                ▼
        ┌───────────────────────────────┐
        │                               │
        ▼                               ▼
  BÚSQUEDA SEMÁNTICA            BÚSQUEDA POR KEYWORDS
  
  1. Genera embedding del query   1. Tokeniza el query
     (mismo modelo, 384 dims)        (words ≥ 2 chars)
  
  2. Cosine similarity contra      2. Cuenta ocurrencias de
     cada embedding del corpus        cada término en el texto
     (producto punto, ya              (regex case-insensitive)
     normalizados = cosine)
  
  3. Score normalizado [0,1]       3. Score normalizado [0,1]
        │                               │
        └──────────────┬────────────────┘
                       ▼
             SCORE HÍBRIDO
             
   hybrid = α × semantic + (1−α) × keyword
   
   α viene del slider:
   • α = 0.0 → solo keywords
   • α = 0.5 → equilibrado (default)
   • α = 1.0 → solo semántico
   
   Filtra: hybrid < 0.05 → descartado
   Ordena: descendente por hybrid score
```

### Vistas de la app

**Búsqueda**: resultados agrupados por libro, con badges que muestran `sem XX%`, `kw XX%` y `↔ XX%` para cada resultado. Paginación de 25 en 25.

**Biblioteca**: todos tus libros organizados en categorías temáticas (IA, Economía, Neurociencia, etc.), con la cantidad de subrayados por libro y vista de detalle con buscador inline.

### Sistema de caché (`.kindle-index.json`)

El índice serializado contiene:
```json
{
  "version": 1,
  "generated": "2024-01-15T12:00:00.000Z",
  "clippings": [
    { "bookRaw": "...", "bookTitle": "...", "bookAuthor": "...", "text": "...", "year": 2023 }
  ],
  "embeddings": [[0.123, -0.045, ...]]  // Float32Arrays → arrays regulares para JSON
}
```

Al cargar el índice, los arrays se restauran como `Float32Array` para las operaciones de cosine similarity.

---

## Privacidad

**Tus datos nunca salen de tu computadora.** El único recurso externo que se carga es el modelo de IA (~23MB) desde jsDelivr la primera vez, que queda cacheado en el browser. Los subrayados, el índice y las búsquedas se procesan enteramente en tu máquina.

---

## Requisitos

- Browser moderno con soporte para ES Modules y WebAssembly: Chrome 80+, Edge 80+, Firefox 79+, Safari 15+
- Conexión a internet solo la primera vez (para descargar el modelo de ~23MB)
- Sin instalación, sin servidor, sin dependencias externas

---

## Limitaciones conocidas

- El procesamiento inicial puede tardar 1-5 minutos con bibliotecas muy grandes (>5.000 subrayados)
- El modelo de embeddings (`all-MiniLM-L6-v2`) fue entrenado principalmente en inglés; funciona bien con español pero puede tener menor precisión semántica que con textos en inglés
- El caché del modelo vive en el browser: si limpias el caché, se re-descarga la próxima vez

---

## Changelog

### v3 — Mayo 2026
- **Vista Biblioteca** — nueva pestaña "📚 Biblioteca" que muestra todos tus libros organizados por categorías temáticas (IA, Economía, Neurociencia, Creatividad, etc.) con color e iconografía por tema. Incluye grid de libros con título, autor y cantidad de subrayados; categorías colapsables; buscador inline por libro; y paginación de subrayados ("Ver más").
- **Navegación por tabs** — barra de tabs en la parte superior para alternar entre "🔍 Búsqueda" y "📚 Biblioteca" sin recargar ni reprocesar.
- `renderLibrary()` se invoca automáticamente al terminar de cargar el archivo o el índice.

### v2 — Mayo 2026
- Búsqueda híbrida semántica + keywords con slider ajustable
- Pipeline completo: parseo → filtrado → embeddings → búsqueda
- Sistema de caché con `.kindle-index.json` (guardar y recargar sin reprocesar)
- Resultados agrupados por libro con score badges (`sem`, `kw`, `↔`)
- Filtro por libro y paginación

---

## Archivos

```
kindle_hibrido.html     → la app completa (HTML + CSS + JS en un solo archivo)
README.md               → este archivo
```

Para usar la app con tus propios subrayados, abrí el archivo en el browser y cargá tu `My_Clippings.txt`.

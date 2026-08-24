# Arquitectura técnica — Cerebro Kindle

Documentación exhaustiva del código fuente de `kindle_hibrido.html`. El archivo es una app de una sola página completamente autocontenida: HTML + CSS + JavaScript en un único `.html`, sin dependencias locales, sin build step, sin servidor.

---

## Índice

1. [Estructura general del archivo](#1-estructura-general-del-archivo)
2. [Estado global](#2-estado-global)
3. [Máquina de pantallas](#3-máquina-de-pantallas)
4. [Flujo principal: carga desde archivo](#4-flujo-principal-carga-desde-archivo)
5. [Flujo alternativo: carga desde índice](#5-flujo-alternativo-carga-desde-índice)
6. [Parser de subrayados](#6-parser-de-subrayados)
7. [Filtrado y deduplicación](#7-filtrado-y-deduplicación)
8. [Embeddings semánticos](#8-embeddings-semánticos)
9. [Motor de búsqueda híbrida](#9-motor-de-búsqueda-híbrida)
10. [Renderizado de resultados](#10-renderizado-de-resultados)
11. [Sistema de caché](#11-sistema-de-caché)
12. [Vista Biblioteca](#12-vista-biblioteca)
13. [Utilidades](#13-utilidades)
14. [Estructura de datos](#14-estructura-de-datos)
15. [Flujo de datos completo](#15-flujo-de-datos-completo)
16. [Tema claro/oscuro y sidebar colapsable](#16-tema-clarooscuro-y-sidebar-colapsable)
17. [Accesibilidad (contraste WCAG)](#17-accesibilidad-contraste-wcag)

---

## 1. Estructura general del archivo

```
kindle_hibrido.html
├── <head>
│   ├── <script> inline — aplica tema oscuro pre-pintado (evita flash de tema claro)
│   ├── Google Fonts (Fraunces + Inter)
│   └── <style> — todo el CSS (~350 líneas, incluye paleta clara/oscura)
└── <body>
    ├── .theme-toggle-btn    — botón flotante para alternar tema claro/oscuro
    ├── .sidebar-expand-btn  — botón para reabrir el sidebar cuando está colapsado
    ├── #screen-upload       — pantalla de carga inicial
    ├── #screen-progress     — pantalla de progreso (parseo + embeddings)
    ├── #screen-app          — pantalla principal de la app
    │   ├── #sidebar         — columna de menú/filtros, colapsable
    │   ├── #tab-bar         — tabs "Búsqueda" / "Biblioteca"
    │   ├── #search-content  — vista de búsqueda completa
    │   └── #screen-library  — vista de biblioteca
    ├── .save-index-btn      — botón flotante "Guardar índice"
    └── <script type="module"> — toda la lógica (~550 líneas)
```

La única dependencia externa es `@xenova/transformers@2.17.2` cargada desde jsDelivr via ES Module import.

**Tipografía:** Fraunces (serif, para títulos) + Inter (sans, para cuerpo e interfaz) — elegidas como equivalentes gratuitos de las fuentes propietarias de Claude (Copernicus/Tiempos y Styrene), que no están disponibles como webfonts libres. Ver §16 para el detalle del sistema de theming que acompañó este cambio.

---

## 2. Estado global

```javascript
let clippings = [];      // Array de objetos Clipping (ver §14)
let embeddings = null;   // Array de Float32Array (un vector de 384 dims por clipping)
let extractor = null;    // Pipeline de transformers.js (feature-extraction)
let currentResults = []; // Resultados del último search, ya ordenados
let currentPage = 1;     // Página activa en la paginación
const PER_PAGE = 25;     // Resultados por página
```

`clippings` y `embeddings` están alineados por índice: `embeddings[i]` es el vector semántico de `clippings[i].text`.

---

## 3. Máquina de pantallas

```javascript
function show(id)
```

Controla qué pantalla es visible. Acepta `'screen-upload'`, `'screen-progress'` o `'screen-app'`. Las tres pantallas existen siempre en el DOM — `show()` las muestra/oculta cambiando `display`. La pantalla de progreso usa `display: flex`; las demás usan `display: block`.

```javascript
function setStep(id, state)
// state: 'done' | 'active' | ''
```

Actualiza el ícono y la clase CSS de cada paso en la lista de progreso (`#step-parse`, `#step-filter`, `#step-model`, `#step-embed`, `#step-done`).

```javascript
function setProg(pct, title, sub, detail)
```

Actualiza simultáneamente la barra de progreso (ancho en `%`), el título, el subtítulo y el detalle de la pantalla de progreso.

```javascript
function tick()
// return new Promise(r => setTimeout(r, 0))
```

Cede el control al event loop del browser. Se usa con `await tick()` antes de operaciones CPU-intensivas para que el DOM se actualice y el progreso sea visible. Sin esto, el browser quedaría congelado durante el parseo y la generación de embeddings.

---

## 4. Flujo principal: carga desde archivo

Se activa cuando el usuario arrastra o selecciona un `My_Clippings.txt`.

```
fileInput.change / dropZone.drop
        │
        ▼
loadFile(file)
        │
        ├─ show('screen-progress')
        │
        ├─ parseClippings(text)          → clippings[]
        │
        ├─ filterClippings(clippings)    → clippings[] (limpio)
        │
        ├─ Populate #book-filter <select>
        │
        ├─ pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2')
        │   (descarga ~23MB primera vez, luego usa caché del browser)
        │
        ├─ generateEmbeddings(texts)     → embeddings[]
        │
        ├─ show('screen-app')
        │
        ├─ Mostrar #save-btn y #tab-bar
        │
        └─ renderLibrary()
```

**Manejo del drag-and-drop:**

```javascript
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag');
  if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]);
});
```

`e.preventDefault()` en `dragover` es necesario para que el browser permita el drop (comportamiento predeterminado es rechazarlo).

---

## 5. Flujo alternativo: carga desde índice

Se activa cuando el usuario carga un `.kindle-index.json` generado previamente.

```
cache-input.change
        │
        ▼
loadIndex(file)
        │
        ├─ show('screen-progress')
        │
        ├─ JSON.parse(text)
        │   └─ Valida presencia de: clippings, embeddings, version
        │
        ├─ Restaura Float32Arrays:
        │   embeddings = data.embeddings.map(arr => new Float32Array(arr))
        │
        ├─ Carga el modelo igual que en el flujo normal
        │   (necesario para embeddings de nuevas búsquedas)
        │
        ├─ Populate #book-filter <select>
        │
        ├─ show('screen-app')
        │
        └─ renderLibrary()
```

**Por qué se carga el modelo incluso con el índice:** los embeddings del corpus ya están en el JSON, pero cada nueva query del usuario necesita ser convertida a embedding en tiempo real. El modelo se carga de todas formas (desde caché del browser si ya se descargó antes).

**Diferencia con el flujo normal:** no aparece el botón "Guardar índice" (ya tienen el índice) y el stats bar muestra `⚡` indicando carga rápida.

---

## 6. Parser de subrayados

```javascript
function parseClippings(raw) → Clipping[]
```

Procesa el contenido completo de `My_Clippings.txt`.

**Paso 1 — BOM:** el archivo exportado por Kindle incluye un Byte Order Mark (U+FEFF) al inicio. Se elimina si está presente:

```javascript
if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1);
```

**Paso 2 — Split:** el archivo usa `==========` como separador entre subrayados. Cada fragmento resultante es una entrada.

**Paso 3 — Por cada entrada:**

```javascript
const lines = entry.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
// lines[0] = "Título del libro (Apellido, Nombre)"
// lines[1] = "- Tu subrayado en la posición 123-456 | Añadido el lunes, 3 de enero de 2022 15:30:00"
// lines[2..] = texto del subrayado
```

**Descarte temprano:** si hay menos de 3 líneas, o el texto tiene < 60 caracteres, o la línea de meta contiene `'marcador'` (bookmarks de Kindle, que no tienen texto útil), la entrada se descarta.

**Extracción del libro:**

```javascript
const pm = bookRaw.match(/^(.+?)\s*\(([^)]+)\)\s*$/);
// pm[1] = título, pm[2] = autor
// Si no matchea, bookRaw se usa completo como título sin autor
```

**Extracción de fecha:**

```javascript
const monthMap = {enero:1, febrero:2, ..., diciembre:12};
const dm = meta.match(/Añadido el \w+, (\d+) de (\w+) de (\d+)/);
// dm[1] = día, dm[2] = mes (palabra), dm[3] = año
```

Solo se extrae el año para mostrarlo en la UI. El día y mes se descartan.

**Retorna** un objeto `Clipping` por entrada válida (ver §14).

---

## 7. Filtrado y deduplicación

```javascript
function filterClippings(clips) → Clipping[]
```

Se aplica después del parseo para reducir el corpus a fragmentos de alta calidad.

**Filtro 1 — longitud máxima:**

```javascript
.filter(c => c.text.length <= 900)
```

Fragmentos muy largos suelen ser capítulos enteros o errores de exportación.

**Paso 2 — Ordenar por longitud descendente:**

```javascript
.sort((a, b) => b.text.length - a.text.length)
```

Esto garantiza que cuando se deduplique, se quede con el fragmento más completo de cada par duplicado.

**Filtro 3 — Deduplicación por fingerprint:**

```javascript
const key = c.text.slice(0, 80).toLowerCase().replace(/\s+/g, ' ');
if (seen.has(key)) return false;
seen.add(key);
```

Kindle exporta el mismo subrayado múltiples veces cuando el usuario lo edita o cuando hay solapamiento. El fingerprint son los primeros 80 caracteres normalizados. Al haber ordenado previamente por longitud, siempre se conserva la versión más larga.

**Filtro 4 — Cap por libro:**

```javascript
bookCounts[c.bookRaw] = (bookCounts[c.bookRaw] || 0) + 1;
return bookCounts[c.bookRaw] <= 80;
```

Limita a 80 subrayados por libro para evitar que un libro muy subrayado domine los resultados de búsqueda.

---

## 8. Embeddings semánticos

### Carga del modelo

```javascript
extractor = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2', {
  progress_callback: p => {
    if (p.status === 'downloading') {
      const pct = p.total ? Math.round(p.loaded / p.total * 100) : 0;
      setProg(...);
    }
  }
});
```

`pipeline()` es de `@xenova/transformers`. Ejecuta el modelo ONNX en WebAssembly directamente en el browser. La primera vez descarga ~23MB desde jsDelivr y los almacena en `Cache Storage` (API del browser). Las siguientes veces arranca en segundos.

`env.allowLocalModels = false` — no busca modelos locales.
`env.useBrowserCache = true` — usa el caché del browser.

### Generación en batches

```javascript
async function generateEmbeddings(texts) → Float32Array[]
```

```javascript
const BATCH = 32;
for (let i = 0; i < total; i += BATCH) {
  const batch = texts.slice(i, i + BATCH);
  const out = await extractor(batch, { pooling: 'mean', normalize: true });
  const dim = 384;
  for (let j = 0; j < batch.length; j++)
    all.push(out.data.slice(j * dim, (j + 1) * dim));
  await tick(); // actualiza UI entre batches
}
```

- **Batch de 32:** balance entre throughput y responsividad de la UI.
- **`pooling: 'mean'`:** promedia los token embeddings para obtener un vector por oración.
- **`normalize: true`:** normalización L2, lo que permite usar producto punto como cosine similarity.
- **`out.data`:** `Float32Array` plano con todos los embeddings del batch concatenados. Se extrae la porción `[j*384, (j+1)*384)` para cada texto.

### Por qué `all-MiniLM-L6-v2`

- 384 dimensiones (vs 768 de modelos más grandes) → más liviano en browser.
- ~23MB de modelo ONNX cuantizado.
- Buena performance en tareas de sentence similarity.
- Disponible en Hugging Face Hub con conversión a ONNX lista.

---

## 9. Motor de búsqueda híbrida

```javascript
window.doSearch = async function()
```

### 1. Obtener la query

```javascript
const q = document.getElementById('search-input').value.trim();
const terms = q.toLowerCase().split(/\s+/).filter(t => t.length >= 2);
const alpha = parseInt(document.getElementById('hybrid-slider').value) / 100;
// alpha: 0.0 = solo keywords, 1.0 = solo semántico
```

### 2. Embedding de la query

```javascript
const qEmbed = await extractor([q], { pooling: 'mean', normalize: true });
const qVec = qEmbed.data.slice(0, 384);
```

La query pasa por el mismo modelo que el corpus, produciendo un vector de 384 dims en el mismo espacio semántico.

### 3. Score semántico

```javascript
function cosineSim(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) d += a[i] * b[i];
  return d;
}

const rawSemantic = clippings.map((c, i) => cosineSim(qVec, embeddings[i]));
```

Como todos los vectores están normalizados L2, el **producto punto = cosine similarity**. Rango: [-1, 1], en la práctica [0, 1] para texto.

### 4. Score por keywords

```javascript
function keywordScore(text, terms) {
  const lower = text.toLowerCase();
  let score = 0;
  terms.forEach(t => {
    const re = new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    const matches = lower.match(re);
    if (matches) score += matches.length * 2 + 1;
  });
  return score;
}
```

Por cada término de la query:
- `+1` por aparecer al menos una vez.
- `+2` adicionales por cada aparición extra.

Esto da más peso a términos que aparecen múltiples veces sin ser solo lineal.

### 5. Normalización

```javascript
const maxSem = Math.max(...rawSemantic) || 1;
const maxKw  = Math.max(...rawKeyword) || 1;
// semScore = rawSemantic[i] / maxSem  → [0, 1]
// kwScore  = rawKeyword[i] / maxKw    → [0, 1]
```

Normalización min-max simplificada (min implícito = 0). Lleva ambos scores al mismo rango para que el slider funcione correctamente.

### 6. Score híbrido y filtrado

```javascript
const hybrid = alpha * semScore + (1 - alpha) * kwScore;
```

Combinación lineal ponderada por `alpha`. Resultado:

| `alpha` | Comportamiento |
|---------|----------------|
| 0.0 | Solo keywords — exactitud léxica |
| 0.5 | Equilibrado (default) |
| 1.0 | Solo semántico — similitud conceptual |

Se filtran resultados con `hybrid < 0.05` (umbral mínimo de relevancia) y se ordenan descendentemente.

### 7. Label del slider

```javascript
window.updateHybridLabel = function() {
  const v = parseInt(document.getElementById('hybrid-slider').value);
  const label = v <= 10 ? 'Solo keywords'
              : v <= 30 ? 'Más keywords'
              : v <= 45 ? 'Levemente keywords'
              : v <= 55 ? 'Equilibrado'
              : v <= 70 ? 'Levemente semántico'
              : v <= 90 ? 'Más semántico'
              :           'Solo semántico';
  document.getElementById('hybrid-mode-label').textContent = label;
};
```

---

## 10. Renderizado de resultados

```javascript
window.renderResults = function(terms)
```

Se llama tanto al buscar como al cambiar el filtro de libro (`onchange`).

**Filtro por libro:**

```javascript
const bookFilter = document.getElementById('book-filter').value;
const filtered = currentResults.filter(c => !bookFilter || c.bookRaw === bookFilter);
```

**Paginación:**

```javascript
const start = (currentPage - 1) * PER_PAGE;
const page = filtered.slice(start, start + PER_PAGE);
```

**Agrupación por libro:** los resultados de la página se agrupan por `bookRaw` para mostrar un header de libro antes de cada grupo. El orden inter-libro refleja el ranking híbrido (el libro cuyo primer resultado tiene mayor score aparece primero).

**Resaltado de keywords:**

```javascript
function highlightKw(text, terms) {
  let result = esc(text);
  terms.forEach(t => {
    const re = new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    result = result.replace(re, '<mark>$1</mark>');
  });
  return result;
}
```

Los términos de búsqueda se resaltan con `<mark>` dentro del texto escapado. El escape HTML se aplica **antes** del highlight para evitar XSS.

**Clasificación por score (sin indicador visual):**

```javascript
const hybPct = Math.round(c.hybrid * 100);
const cls = hybPct >= 65 ? 'high'
           : hybPct >= 35 ? 'mid'
           :                'low';
```

La clase `high`/`mid`/`low` se sigue calculando y asignando a cada `.h-card`/`.clip-item`, pero ya no tiene efecto visual: se eliminó el `border-left` de color (verde/amarillo/gris) que antes decoraba cada subrayado, a pedido del usuario ("hay una linea que acompania a cada subrayado que no quiero que salga"). Las reglas `.h-card.high`, `.h-card.mid` y `.h-card.low` fueron borradas del CSS. La relevancia del resultado se sigue comunicando únicamente vía los `score-pill` (sem/kw/híbrido).

**Score badges:** solo se muestran los scores relevantes según el modo:

```javascript
${alpha > 0.1 ? `<span class="score-pill score-sem">sem ${semPct}%</span>` : ''}
${alpha < 0.9 ? `<span class="score-pill score-kw">kw ${kwPct}%</span>` : ''}
<span class="score-pill score-hybrid">↔ ${hybPct}%</span>
```

**Paginación dinámica:** muestra botones para las páginas `[currentPage-2, currentPage+2]` más anterior/siguiente.

---

## 11. Sistema de caché

### Guardar índice

```javascript
window.saveIndex = function()
```

Serializa el estado completo a JSON:

```javascript
const data = {
  version: 1,
  generated: new Date().toISOString(),
  clippings: clippings,                           // objetos JS → JSON directo
  embeddings: embeddings.map(arr => Array.from(arr)) // Float32Array → Array regular
};
```

`Float32Array` no es serializable directamente a JSON; `Array.from()` lo convierte a array de números. Esto infla el archivo (~3-5x respecto a binario) pero es compatible con JSON nativo del browser.

Se crea un `Blob`, se genera una URL temporal y se simula un click en un `<a download>` para disparar la descarga.

### Cargar índice

```javascript
embeddings = data.embeddings.map(arr => new Float32Array(arr));
```

La conversión inversa restaura los `Float32Array` para que `cosineSim()` funcione correctamente.

**Validación mínima:**

```javascript
if (!data.clippings || !data.embeddings || !data.version)
  throw new Error('Formato de índice inválido. Generá uno nuevo.');
```

Si el archivo es inválido, vuelve a la pantalla de upload después de 3 segundos.

---

## 12. Vista Biblioteca

### Estructura de datos LIBRARY

```javascript
const LIBRARY = {};
// Forma: { [categoría]: [{ t: título, a: autor, k: count, c: [textos] }] }
```

`LIBRARY` se construye en tiempo de ejecución al llamar `renderLibrary()`, leyendo `clippings[]`.

> **Nota:** la implementación actual de `renderLibrary()` renderiza desde `LIBRARY`, pero el código de *poblado* de `LIBRARY` no está implementado en el HTML — la vista Biblioteca requiere que `LIBRARY` esté pre-poblado (en la versión de demostración con datos hardcodeados). En uso con `My_Clippings.txt`, esta función muestra los libros del usuario una vez que se completa la integración.

### Metadatos de categorías

```javascript
const CAT_META = {
  "IA · Tecnología · Digital":         { color: "#2d5a8e", bg: "#E6F1FB", icon: "🤖" },
  "Economía · Finanzas · Conducta":    { color: "#085041", bg: "#E1F5EE", icon: "📊" },
  // ... 8 categorías más
};

const CAT_ORDER = [ /* orden de aparición */ ];
```

### Interacciones

**`toggleCat(ci)`** — colapsa/expande una categoría. Alterna `display: none/block` en `#books-{ci}` y rota la flecha.

**`showBook(ci, bi)`** — muestra el detalle de un libro:
1. Limpia todos los `.book-card-lib.selected` y `.book-detail.open`
2. Marca la card como `.selected`
3. Llama `renderDetail()` con `filter = ''`
4. Hace scroll suave al detalle

**`renderDetail(el, book, ci, bi, filter)`** — renderiza la vista de subrayados de un libro:
- Paginación interna con `clipPages[ci+'-'+bi]` (20 por página, con "Ver más")
- Buscador inline que filtra `book.c` (array de textos) por substring
- Highlight del término filtrado con `hlFilter()`

```javascript
function hlFilter(text, filter) {
  if (!filter) return esc(text);
  const re = new RegExp('(' + filter.replace(/[.*+?^${}()|[\]\\]/g, '\\$1') + ')', 'gi');
  return esc(text).replace(re, '<mark>$1</mark>');
}
```

---

## 13. Utilidades

```javascript
function esc(s)
// Escapa HTML: & < > "
// Previene XSS al insertar texto de usuario o subrayados en innerHTML
```

```javascript
function tick()
// return new Promise(r => setTimeout(r, 0))
// Cede el event loop para que el browser actualice el DOM
```

```javascript
window.qs(q)
// Escribe q en #search-input y dispara doSearch()
// Usado por los chips de sugerencias
```

```javascript
window.goPage(p)
// Navega a la página p y re-renderiza con los términos actuales
```

---

## 14. Estructura de datos

### Clipping

```typescript
interface Clipping {
  bookRaw:    string;  // línea completa: "Título (Autor)"
  bookTitle:  string;  // solo el título
  bookAuthor: string;  // solo el autor
  text:       string;  // texto del subrayado
  year:       number | null;  // año de la fecha de subrayado
}
```

### SearchResult (Clipping extendido)

```typescript
interface SearchResult extends Clipping {
  semScore:   number;  // score semántico normalizado [0, 1]
  kwScore:    number;  // score keyword normalizado [0, 1]
  hybrid:     number;  // score híbrido final [0, 1]
}
```

### IndexFile (formato del JSON guardado)

```typescript
interface IndexFile {
  version:    1;
  generated:  string;       // ISO 8601
  clippings:  Clipping[];
  embeddings: number[][];   // Float32Array serializado como Array<number> (384 dims)
}
```

### LibraryBook

```typescript
interface LibraryBook {
  t: string;    // título
  a: string;    // autor
  k: number;    // cantidad de subrayados
  c: string[];  // textos de subrayados
}
```

---

## 15. Flujo de datos completo

```
My_Clippings.txt
        │
        ▼ parseClippings()
Clipping[] (raw)
        │
        ▼ filterClippings()
Clipping[] (limpio, deduplicado, cap 80/libro)
        │
        ├──────────────────────────────────────────────────────┐
        │                                                       │
        ▼ .map(c => c.text)                                    │
string[]                                                       │ (metadata)
        │                                                       │
        ▼ generateEmbeddings()                                 │
Float32Array[] (un vector 384-dim por texto)                   │
        │                                                       │
        └──────────────────────┬────────────────────────────────┘
                               │
                    [clippings[], embeddings[]]  ← estado global
                               │
          ┌────────────────────┼──────────────────────┐
          │                    │                       │
          ▼                    ▼                       ▼
   doSearch(query)      renderLibrary()          saveIndex()
          │
          ├─ extractor([query]) → qVec (384-dim)
          │
          ├─ cosineSim(qVec, embeddings[i]) → rawSemantic[]
          │
          ├─ keywordScore(text, terms) → rawKeyword[]
          │
          ├─ normalizar → [0,1]
          │
          ├─ hybrid = α * sem + (1-α) * kw
          │
          ├─ filtrar (hybrid > 0.05) + sort desc
          │
          └─ currentResults[]
                     │
                     ▼ renderResults()
               HTML en #results
```

---

## 16. Tema claro/oscuro y sidebar colapsable

### Tema claro/oscuro

Toda la paleta de colores está definida con custom properties CSS en `:root`, incluyendo variables nuevas agregadas junto con el modo oscuro: `--card`, `--accent-bg`, `--accent-fg`, `--overlay-subtle`, `--shadow`, `--cat-accent` (además de las preexistentes `--ink`, `--ink-2`, `--ink-3`, `--paper`, `--paper-2`, `--paper-3`, `--accent`, `--line`).

El modo oscuro se activa agregando la clase `dark-theme` al elemento `<html>`. Un bloque `html.dark-theme { ... }` sobreescribe todas las variables con sus equivalentes oscuros. También se declara `color-scheme: light` / `dark` para que los controles nativos del browser (selects, scrollbars) respeten el tema.

**Evitar flash de tema claro (FOUC):** el tema se aplica *antes* de pintar, mediante un `<script>` inline ubicado justo después de `<title>` (antes de que se cargue el CSS/JS del módulo):

```html
<script>
  try { if (localStorage.getItem('theme') === 'dark') document.documentElement.classList.add('dark-theme'); } catch(e) {}
</script>
```

Si este script corriera después (por ejemplo dentro del `<script type="module">`, que se ejecuta de forma diferida), el usuario vería un parpadeo de tema claro antes de que se aplique el oscuro.

**Toggle:**

```javascript
window.toggleTheme = function() {
  document.documentElement.classList.toggle('dark-theme');
  const isDark = document.documentElement.classList.contains('dark-theme');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  // sincroniza el ícono del botón .theme-toggle-btn
};
```

El botón `.theme-toggle-btn` (flotante, agregado justo después de `<body>`) llama a `toggleTheme()` y su ícono/texto se sincroniza con el estado guardado al cargar la página.

**Casos especiales resueltos:**
- `<mark>` (highlight de keywords) tiene colores propios en modo oscuro (`html.dark-theme .h-text mark`, `html.dark-theme .clip-item mark`) para que el resaltado amarillo siga siendo legible sobre fondo oscuro.
- Reglas que combinaban `background: var(--ink)` con `color: #fff` (ej. `.btn-search`, `.score-pill`) se cambiaron a `color: var(--paper)`, para que ambos valores se inviertan juntos al cambiar de tema — con `#fff` fijo, el texto blanco se volvía invisible sobre fondo claro en modo oscuro (`--ink` pasa a ser claro).
- Todos los `background: white` / `background: #fff` hardcodeados (upload-box, search-input, cards, paneles, headers, etc.) se reemplazaron por `background: var(--card)`.

### Sidebar colapsable

El sidebar (`#sidebar`, columna de menú y filtros) se puede ocultar/mostrar:

```javascript
window.toggleSidebar = function() {
  document.getElementById('sidebar').classList.toggle('collapsed');
  // persiste el estado en localStorage.sidebarCollapsed
};
```

CSS relevante:

```css
#sidebar { transition: width 0.18s ease; }
#sidebar.collapsed { width: 0 !important; overflow: hidden; border-right: none; }
```

- `.sidebar-collapse-btn` (dentro de `.sidebar-brand`) colapsa el sidebar.
- `.sidebar-expand-btn` (fuera del sidebar, visible solo cuando está colapsado) lo vuelve a mostrar.
- El estado se persiste en `localStorage.sidebarCollapsed` y se restaura al cargar la página.

**Interacción con el resize por arrastre:** el sidebar ya tenía una feature previa de ancho ajustable por drag (mousedown/mousemove/mouseup, persistida en `localStorage.sidebarWidth`). La transición CSS (`transition: width 0.18s ease`) se desactiva momentáneamente durante el arrastre (`sidebar.style.transition = 'none'`) y se reactiva al soltar, para que el resize manual sea instantáneo y no quede "amortiguado" por la animación del collapse.

---

## 17. Accesibilidad (contraste WCAG)

Ajustes de contraste realizados para cumplir el estándar WCAG AA (4.5:1 para texto normal, 3:1 para texto grande):

- **`--ink-3`** (color de texto terciario/secundario, usado en metadatos): oscurecido de `#888888` a `#6f6f6f` en modo claro. El valor original daba ~3.56:1 contra blanco, por debajo del mínimo 4.5:1.
- **`--cat-accent`** (color de acento de las etiquetas de categoría en el sidebar, antes `#8B5E3C` hardcodeado): en modo oscuro usa `#caa06c` en lugar del mismo marrón, ya que `#8B5E3C` sobre fondo oscuro da solo ~3.36:1; `#caa06c` da ~7.35:1.
- **Tamaños de fuente aumentados** en elementos de categoría, que habían quedado visualmente pequeños tras el cambio de tipografía a Inter: `.sidebar-section-title` (0.62rem → 0.68rem), `.sidebar-cat-label` (0.8rem → 0.86rem), `.sidebar-cat-arrow` (0.6rem → 0.66rem), `#book-cat-selector` (0.73rem → 0.78rem), `.cat-icon` (1rem → 1.05rem), `.cat-name` (1.1rem → 1.18rem, peso 500 → 600), `.cat-count`/`.cat-arrow` (0.72rem → 0.76rem).

# Query 1 — Usuarios activos y cantidad de órdenes

## Problema

La consulta tenía un problema **N+1**:

- Primero obtenía todos los usuarios activos.
- Luego ejecutaba una consulta adicional por cada usuario para contar sus órdenes.

Además:

- Utilizaba `SELECT *`.
- Realizaba el ordenamiento en Python.
- Construía consultas mediante interpolación de cadenas, lo que representa un riesgo de SQL Injection.

## Solución óptima

Se reemplazó por una única consulta utilizando:

- `LEFT JOIN`
- `COUNT()`
- `GROUP BY`
- `ORDER BY`

Además:

- Se eliminaron las consultas repetidas.
- Se utilizaron parámetros seguros.
- Se seleccionaron únicamente las columnas necesarias.

---

# Query 2 — Productos más vendidos

## Problema

La consulta utilizaba una **subconsulta correlacionada**, ejecutándose una vez por cada producto.

Además:

- Utilizaba `DISTINCT` de forma innecesaria.
- Seleccionaba más columnas de las requeridas.

Esto generaba múltiples recorridos sobre las tablas y una agregación costosa.

## Solución óptima

Se reemplazó por:

- `JOIN` directos entre las tablas.
- Agregación mediante `SUM()`.
- Agrupamiento con `GROUP BY`.
- Filtrado temprano de órdenes pagadas.

Con estos cambios, todos los resultados se calculan en una única consulta.

---

# Query 3 — Usuarios que compraron una categoría

## Problema

La consulta contenía múltiples niveles de subconsultas anidadas utilizando `IN`, lo que dificultaba la optimización del plan de ejecución y aumentaba el costo de la consulta.

Además, existía riesgo de **SQL Injection** debido al uso de interpolación de parámetros.

## Solución óptima

Se reemplazó la lógica por:

- `INNER JOIN`.
- Filtros directos.
- `DISTINCT`.
- Consultas parametrizadas.

Esto simplifica el plan de ejecución y permite un mejor aprovechamiento de los índices.

---

# Query 4 — Búsqueda de productos por palabra clave

## Problema

La consulta utilizaba:

- `%LIKE%`.
- `JOIN` implícitos.
- `SELECT *`.
- Parámetros interpolados.

El uso de `%LIKE%` impide el aprovechamiento eficiente de los índices, degradando el rendimiento en búsquedas sobre grandes volúmenes de información.

## Solución óptima

Se implementó:

- **Full-Text Search** (`MATCH ... AGAINST`).
- `JOIN` explícitos.
- Parámetros seguros.
- Selección únicamente de las columnas necesarias.

Estos cambios mejoran significativamente el rendimiento de las búsquedas de texto.

---

# Query 5 — Reporte mensual de ingresos

## Problema

La consulta agrupaba los resultados utilizando funciones sobre columnas de fecha (`DATE_FORMAT()`), lo que dificulta el uso de índices.

Además, la paginación utilizaba valores interpolados.

## Solución óptima

Se reemplazó por:

- Agrupación mediante `YEAR()` y `MONTH()`.
- Parámetros seguros para la paginación.
- Procesamiento del formato de la fecha realizado fuera de SQL.

Con estas mejoras se reduce el costo de agregación y se mejora el aprovechamiento de los índices sobre las columnas de fecha.
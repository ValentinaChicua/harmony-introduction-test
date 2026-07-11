# Revisión Técnica - Integración con WhatsApp Business API


# 1. Búsqueda ineficiente de mensajes en memoria

## Problema

Los mensajes se almacenan en una lista.

```python
self._messages: List[Message] = []
```

Cuando se desea obtener todos los mensajes de un contacto, el método recorre uno por uno todos los mensajes almacenados.

```python
for message in self._messages:
    if message.to == phone_number:
        result.append(message)
```

Esta operación tiene una complejidad temporal **O(n)**.

Esto significa que si existen diez mensajes se recorrerán diez elementos, pero si existen un millón de mensajes se recorrerá el millón completo, incluso cuando únicamente se necesiten los mensajes de un solo contacto.

A medida que el sistema crece, este método se vuelve cada vez más lento.

## Impacto

- Baja escalabilidad.
- Mayor consumo de CPU.
- Tiempo de respuesta creciente conforme aumenta la cantidad de mensajes.

## Solución

Mantener una estructura indexada por número telefónico.

Por ejemplo:

```python
messages_by_contact = {
    "+573001112233": [...],
    "+573101112233": [...]
}
```

De esta forma, la búsqueda deja de recorrer toda la colección y pasa a obtener directamente los mensajes asociados al contacto.

## Beneficios

- Búsquedas prácticamente instantáneas.
- Mejor rendimiento.
- Mejor escalabilidad.

---

# 2. Actualización de estados poco eficiente


## Problema

El método `update_message_status()` también recorre completamente la lista de mensajes.

```python
for message in self._messages:
```

Cada vez que llega una confirmación de lectura o entrega desde WhatsApp, el sistema debe revisar todos los mensajes almacenados hasta encontrar el correcto.

Con miles de mensajes este proceso se vuelve costoso.

## Solución

Guardar los mensajes utilizando su identificador como clave.

Ejemplo:

```python
messages = {
    message_id: Message
}
```

Entonces la actualización sería simplemente:

```python
messages[message_id].status = nuevo_estado
```

## Beneficios

- Complejidad O(1).
- Actualizaciones mucho más rápidas.
- Menor consumo de recursos.

---

# 3. La gestión de conversaciones está incompleta


## Problema

Existe un diccionario para almacenar conversaciones.

```python
self._conversations = {}
```

Sin embargo, nunca se agrega ninguna conversación ni se actualiza cuando se envía o recibe un mensaje.

Como consecuencia, el método:

```python
get_conversation()
```

siempre devolverá `None`.

Esto significa que la funcionalidad existe parcialmente, pero nunca llega a utilizarse.

## Solución

Cada vez que se envíe o reciba un mensaje, verificar si ya existe una conversación para ese contacto.

Si no existe, crearla.

Si existe, agregar el nuevo mensaje y actualizar la fecha de última actividad.

## Beneficios

- La funcionalidad queda completa.
- Se facilita el historial de conversaciones.
- Mejor organización del almacenamiento.

---

# 4. Se crea una nueva sesión HTTP para cada petición


## Problema

Cada envío de mensaje crea una nueva instancia de `requests.Session`.

```python
session = requests.Session()
```

y posteriormente la destruye.

```python
session.close()
```

Una sesión HTTP permite reutilizar conexiones TCP abiertas.

Al crear una nueva para cada petición se pierde completamente esta ventaja.

Cada solicitud debe volver a negociar la conexión con el servidor, aumentando la latencia y el consumo de recursos.

## Solución

Crear la sesión una sola vez en el constructor.

```python
self._session = requests.Session()
```

y reutilizarla para todas las solicitudes.

## Beneficios

- Menor tiempo de respuesta.
- Reutilización de conexiones.
- Menor carga de red.
- Mejor rendimiento.

---

# 5. Configuración fija dentro del código


## Problema

La URL de la API está escrita directamente en el código.

```python
BASE_URL = "https://..."
```

Esto obliga a modificar el código fuente cuando cambia el entorno.

Por ejemplo:

- desarrollo
- pruebas
- producción

Cada uno puede utilizar una URL diferente.

## Solución

Leer esta configuración desde variables de entorno o archivos de configuración.

## Beneficios

- Mayor flexibilidad.
- No es necesario modificar el código para cambiar de ambiente.
- Mejor seguridad.

---

# 6. Manejo incompleto de errores de red


## Problema

El cliente HTTP únicamente valida códigos HTTP como:

- 401
- 404
- 429

Sin embargo, existen muchos errores que pueden ocurrir antes de recibir una respuesta.

Por ejemplo:

- pérdida de conexión
- timeout
- errores DNS
- errores SSL

Actualmente estas excepciones no son capturadas.

Si ocurren, la aplicación podría terminar con un error inesperado.

## Solución

Capturar las excepciones lanzadas por la librería `requests` y transformarlas en excepciones propias del dominio.

## Beneficios

- Mayor robustez.
- Mejor experiencia para el usuario.
- Errores controlados.

---

# 7. No existe ningún sistema de logging

## Problema

Cuando ocurre un error no queda ningún registro.

No es posible saber:

- qué mensaje falló
- cuándo ocurrió
- cuánto tardó
- cuál fue la respuesta de la API

En producción esto dificulta enormemente la investigación de incidentes.

## Solución

Incorporar logging estructurado.

Registrar eventos importantes como:

- envío exitoso
- errores
- reintentos
- tiempos de respuesta

## Beneficios

- Facilita el soporte.
- Mejora la observabilidad.
- Reduce tiempos de diagnóstico.

---

# 8. Fuerte acoplamiento entre clases


## Problema

`WhatsAppService` crea directamente sus dependencias.

```python
self._client = WhatsAppHttpClient(...)
self._storage = InMemoryMessageStorage()
```

Esto significa que el servicio está obligado a trabajar únicamente con esas implementaciones.

Si en el futuro se quisiera almacenar los mensajes en una base de datos o utilizar otro cliente HTTP, sería necesario modificar la propia clase.

Además, esta decisión dificulta enormemente la creación de pruebas unitarias.

## Solución

Aplicar Inyección de Dependencias.

Recibir las implementaciones desde el constructor.

```python
def __init__(self, client, storage):
```

De esta manera el servicio dependerá de abstracciones y no de implementaciones concretas.

## Beneficios

- Código desacoplado.
- Fácil de probar.
- Mayor reutilización.
- Mayor flexibilidad.

---

# 9. Violación del Principio de Responsabilidad Única (SRP)

## Problema

La clase `WhatsAppService` realiza demasiadas tareas diferentes:

- construye el payload
- realiza llamadas HTTP
- controla los reintentos
- almacena mensajes
- procesa webhooks
- consulta historial

Esto hace que la clase tenga múltiples razones para cambiar.

Cada nueva funcionalidad incrementará aún más su complejidad.

## Solución

Dividir las responsabilidades en clases especializadas.

Por ejemplo:

- Cliente HTTP
- Constructor de Payload
- Gestor de Reintentos
- Procesador de Webhooks
- Repositorio de Mensajes

## Beneficios

- Código más limpio.
- Mayor mantenibilidad.
- Mejor reutilización.
- Fácil extensión.

---

# 10. Uso de `time.sleep()` para los reintentos


## Problema

Cuando ocurre un error por límite de peticiones (`429`), el sistema ejecuta:

```python
time.sleep(60)
```

Durante ese tiempo el hilo queda completamente bloqueado.

En aplicaciones con múltiples usuarios esto reduce considerablemente la capacidad de procesamiento.

## Solución

Implementar una estrategia de reintentos con **Exponential Backoff** (retroceso exponencial), aumentando gradualmente el tiempo de espera entre intentos (por ejemplo: 1 s, 2 s, 4 s, 8 s) y, si es posible, añadiendo *jitter* (una pequeña variación aleatoria) para evitar que muchos clientes reintenten al mismo tiempo.

En aplicaciones con alta concurrencia también es recomendable utilizar mecanismos asíncronos o colas de procesamiento para no bloquear hilos mientras se espera el siguiente intento.

## Beneficios

- Mejor aprovechamiento de los recursos.
- Mayor capacidad de respuesta bajo carga.
- Menor riesgo de saturar nuevamente la API.
- Estrategia de reintentos más robusta y utilizada en sistemas distribuidos.

---

# 11. La respuesta de la API no se utiliza

## Problema

En el método `send_message()` se almacena la respuesta de la API en una variable:

```python
response = self._client.post_message(payload)
```

Sin embargo, esta variable nunca vuelve a utilizarse.

La API de WhatsApp normalmente devuelve información importante como:

- Identificador único del mensaje enviado.
- Información sobre la entrega.
- Datos adicionales para realizar trazabilidad.

Actualmente toda esa información se descarta.

## Impacto

Al no almacenar la respuesta:

- No es posible relacionar el mensaje interno con el mensaje registrado por WhatsApp.
- Se dificulta el seguimiento del estado del mensaje.
- Se pierde información útil para auditorías y soporte.

## Solución

Procesar la respuesta recibida y guardar la información relevante dentro del objeto `Message` o en el sistema de almacenamiento.

Por ejemplo:

- Identificador del mensaje remoto.
- Hora de procesamiento.
- Información adicional devuelta por la API.

## Beneficios

- Mejor trazabilidad.
- Mejor capacidad de auditoría.
- Facilita el seguimiento de errores.

---

# 12. Procesamiento secuencial del envío masivo

## Problema

El método `send_bulk()` envía cada mensaje de manera secuencial.

```python
for message in messages:
    self.send_message(message)
```

Cada mensaje debe esperar a que termine el anterior antes de comenzar.

Si cada petición tarda 500 ms y se deben enviar 2.000 mensajes, el proceso completo tardará aproximadamente 1.000 segundos.

## Impacto

- Muy bajo rendimiento.
- Baja capacidad de procesamiento.
- Mala experiencia para campañas masivas.

## Solución

Realizar el procesamiento concurrentemente utilizando mecanismos como:

- ThreadPoolExecutor.
- asyncio.
- Workers.
- Colas de procesamiento.

La solución dependerá de los requisitos del sistema y de las restricciones de la API.

## Beneficios

- Mayor velocidad.
- Mejor aprovechamiento de recursos.
- Mayor capacidad para procesar grandes volúmenes.

---

# 13. Construcción innecesaria de listas en memoria


## Problema

El método `send_notification_to_all_contacts()` primero crea una lista con todos los mensajes y únicamente después comienza el envío.

```python
messages = []

for contact in contacts:
    ...
    messages.append(message)

return self.send_bulk(messages)
```

Si la cantidad de contactos es muy grande, la memoria utilizada también crecerá.

## Impacto

- Mayor consumo de memoria.
- Se retrasa el inicio del envío hasta construir toda la colección.

## Solución

Construir y enviar cada mensaje inmediatamente o utilizar un generador (`generator`) para producir los mensajes bajo demanda.

## Beneficios

- Menor consumo de memoria.
- Inicio del procesamiento más rápido.

---

# 14. El procesamiento del webhook asume que el payload siempre es válido


## Problema

El método `receive_message()` accede directamente a múltiples niveles del diccionario.

```python
raw_payload["entry"][0]
```

Si alguno de estos elementos no existe, Python lanzará excepciones como:

- KeyError
- IndexError

La aplicación terminaría con un error inesperado.

## Impacto

- Baja robustez.
- Posibles fallos por cambios en la API.
- Mala experiencia para el usuario.

## Solución

Validar la estructura del payload antes de acceder a sus propiedades.

Si el contenido no es válido, lanzar una excepción controlada indicando claramente el problema.

## Beneficios

- Mayor estabilidad.
- Errores más claros.
- Mejor mantenimiento.

---

# 15. Duplicación de lógica al procesar webhooks

## Problema

Los métodos:

- receive_message()
- handle_status_update()

repiten exactamente la misma navegación por el payload.

```python
entry

↓

changes

↓

value
```

Esta lógica se encuentra duplicada.

## Impacto

Si la estructura del webhook cambia será necesario modificar varios métodos.

Esto incrementa el riesgo de inconsistencias.

## Solución

Crear un método privado encargado de extraer la información común del payload.

Por ejemplo:

```python
_extract_webhook_data()
```

Los demás métodos reutilizarían este resultado.

## Beneficios

- Menor duplicación.
- Código más limpio.
- Más fácil de mantener.

---

# 16. El método _build_payload() no es extensible


## Problema

El método construye únicamente mensajes de texto.

```python
"text": {
    "body": message.body
}
```

Sin embargo, el modelo `MessageType` ya contempla otros tipos:

- IMAGE
- DOCUMENT
- AUDIO

Cada nuevo tipo obligaría a modificar este método.

Esto viola el principio Abierto/Cerrado (Open/Closed Principle).

## Solución

Crear un constructor de payload independiente para cada tipo de mensaje.

Por ejemplo:

- TextPayloadBuilder
- ImagePayloadBuilder
- AudioPayloadBuilder

El servicio únicamente delegaría la construcción al componente correspondiente.

## Beneficios

- Mayor extensibilidad.
- Menor riesgo al agregar nuevas funcionalidades.
- Mejor organización del código.

---

# 17. No existe separación entre lógica de negocio e infraestructura


## Problema

La clase `WhatsAppService` mezcla reglas de negocio con detalles técnicos.

Dentro de la misma clase se encuentran:

- llamadas HTTP;
- almacenamiento;
- construcción de payloads;
- control de reintentos;
- procesamiento de webhooks.

Esto genera un fuerte acoplamiento entre el dominio y la infraestructura.

## Impacto

Cambios en la API de WhatsApp podrían obligar a modificar reglas de negocio.

## Solución

Separar claramente las capas del sistema.

Por ejemplo:

- Dominio.
- Aplicación.
- Infraestructura.

La lógica de negocio no debería conocer detalles de la comunicación HTTP.

## Beneficios

- Mejor arquitectura.
- Menor acoplamiento.
- Mayor facilidad para evolucionar el sistema.

---

# 18. El almacenamiento en memoria no es seguro para múltiples hilos


## Problema

Las colecciones internas pueden modificarse simultáneamente desde diferentes hilos.

```python
self._messages.append(...)
```

No existe ningún mecanismo de sincronización.

## Impacto

En aplicaciones concurrentes podrían aparecer:

- condiciones de carrera;
- pérdida de información;
- estados inconsistentes.

## Solución

Si el almacenamiento continúa siendo en memoria, utilizar mecanismos de sincronización como `threading.Lock`.

En un entorno de producción, reemplazar esta implementación por una base de datos o un sistema de persistencia adecuado.

## Beneficios

- Mayor seguridad en entornos concurrentes.
- Datos consistentes.

---

# 19. No existe trazabilidad de operaciones


## Problema

El sistema no genera ningún identificador de seguimiento para las operaciones realizadas.

Cuando un cliente reporta un problema, resulta muy difícil reconstruir qué ocurrió durante el envío del mensaje.

## Solución

Generar un identificador único para cada operación y registrarlo en los logs.

Este identificador puede acompañar todas las llamadas relacionadas con el mismo proceso.

## Beneficios

- Facilita el soporte técnico.
- Mejora la observabilidad.
- Permite rastrear errores de extremo a extremo.

---

# 20. La implementación actual dificulta las pruebas unitarias


## Problema

El servicio crea directamente sus dependencias y realiza llamadas HTTP reales.

Esto obliga a que las pruebas interactúen con servicios externos o requieran modificaciones adicionales para simular el comportamiento esperado.

Las pruebas unitarias deberían poder ejecutarse de manera aislada, rápida y determinista.

## Solución

Aplicar Inyección de Dependencias para que el cliente HTTP y el almacenamiento sean proporcionados desde el exterior.

Durante las pruebas, estas dependencias pueden reemplazarse por objetos simulados (*mocks* o *stubs*), evitando llamadas reales a la API.

## Beneficios

- Pruebas más rápidas y confiables.
- Aislamiento del código bajo prueba.
- Mayor facilidad para cubrir escenarios de error y casos límite.
- Mejor mantenibilidad del proyecto.
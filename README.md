# Acortador de URLs — Sistemas Distribuidos

Proyecto por fases. Esta es la **Fase 1**: una sola instancia de la API
(Python + FastAPI) que guarda los enlaces en Redis, todo levantado con
Docker Compose.

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (incluye Docker Compose)
- Opcional, para correr sin Docker o ejecutar pruebas: Python 3.11+

## Cómo correrlo

```bash
docker compose up --build
```

Luego abran **http://localhost:8000/docs**: es una página generada por
FastAPI donde pueden probar todos los endpoints con botones.

Para detenerlo: `Ctrl + C` y luego `docker compose down`.
(`docker compose down -v` además borra los datos guardados en Redis.)

## Endpoints

| Método | Ruta              | Qué hace                                  | Respuesta          |
|--------|-------------------|-------------------------------------------|--------------------|
| POST   | `/shorten`        | Crea un enlace corto                      | `201` + JSON       |
| GET    | `/{codigo}`       | Redirige a la URL original y cuenta clic  | `302` o `404`      |
| GET    | `/stats/{codigo}` | Clics y fecha de creación                 | `200` o `404`      |
| GET    | `/health`         | Estado del servicio y de Redis            | `200` o `503`      |

### Ejemplos con curl

```bash
# Acortar
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://es.wikipedia.org/wiki/Sistema_distribuido"}'
# -> {"codigo":"q0V","short_url":"http://localhost:8000/q0V", ...}

# Redirigir (o simplemente abrir la short_url en el navegador)
curl -i http://localhost:8000/q0V

# Estadísticas
curl http://localhost:8000/stats/q0V
```

> En Windows PowerShell es más fácil usar la página `/docs` que curl.

## Estructura

```
acortador/
├── app/
│   ├── main.py      # Endpoints de la API
│   ├── storage.py   # Todo el acceso a Redis
│   ├── base62.py    # Convierte números en códigos cortos
│   └── config.py    # Configuración por variables de entorno
├── tests/
│   └── test_api.py  # Pruebas automáticas
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Cómo funciona

1. Llega `POST /shorten` con una URL. Pydantic valida que sea una URL real.
2. Redis incrementa un contador (`INCR contador:urls`). `INCR` es
   **atómico**: aunque lleguen dos peticiones al mismo tiempo, cada una
   obtiene un número diferente.
3. El número se convierte a **Base62** (`100001` → `q0V`). Con 7
   caracteres caben ~3.5 billones de enlaces.
4. Se guarda un hash en Redis: `url:q0V → {url, creado, clics}`.
5. En `GET /q0V` se busca el hash, se suma un clic y se responde `302`
   con la cabecera `Location`; el navegador salta solo a la URL original.

### Decisiones de diseño (para el informe)

- **302 y no 301:** con 301 el navegador guarda la redirección y no
  vuelve a consultarnos, así que no podríamos contar clics.
- **Redis con `appendonly yes`:** Redis vive en memoria (muy rápido),
  pero con AOF escribe cada operación a disco y los datos sobreviven
  reinicios.
- **Almacenamiento separado de la API (`storage.py`):** en las siguientes
  fases cambiaremos cómo se guarda sin tocar los endpoints.
- **Contador inicial en 100000:** evita códigos de 1–2 caracteres.

### Limitaciones conocidas (lo que resolveremos en las siguientes fases)

- Un solo proceso de API: si se cae, el servicio se cae.
- Un solo Redis: es a la vez base de datos y generador de IDs, un
  **punto único de falla**.
- Los códigos son secuenciales, así que se puede adivinar el siguiente.

## Pruebas

```bash
python -m venv venv
# Linux/Mac: source venv/bin/activate   |   Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -v
```

Las pruebas usan `fakeredis` (un Redis simulado), así que no necesitan Docker.

## Correr sin Docker (opcional)

Con un Redis local en el puerto 6379:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

---

# Fase 3 — Réplicas + balanceador de carga

```
Cliente → Nginx (:8001) → api ×3 (round-robin) → Redis
```

## Cómo correrlo

```bash
docker compose up --build
```

Ahora el único punto de entrada es **http://localhost:8001** (Nginx). Las 3
réplicas de la API no exponen puertos hacia afuera. Para cambiar el número
de réplicas, editen `replicas:` en `docker-compose.yml`.

## Demostraciones (para el informe)

**1. Reparto de carga y unicidad de IDs**
```bash
python scripts/probar_fase3.py
```
Hace 30 peticiones a `/health` (cada respuesta trae el `instancia` que la
atendió) y luego 200 acortados en paralelo. Debe mostrar un reparto parejo
(~10/10/10) y 200 códigos únicos.

**2. Tolerancia a fallos de una réplica**
```bash
docker compose ps                      # ver los nombres de las réplicas
docker stop acortador-api-1            # tumbar una (ajusten el nombre)
python scripts/probar_fase3.py         # sigue funcionando, reparto 15/15
docker start acortador-api-1           # vuelve a entrar sola
```

**3. Ver qué réplica atendió una petición**
```bash
curl -i http://localhost:8001/health   # cabecera X-Upstream + campo "instancia"
```

## Qué aprendimos / decisiones

- **El generador de IDs sigue siendo correcto con varias réplicas** porque el
  contador vive en Redis (`INCR` es atómico) y no en la memoria de cada API.
  Si el contador estuviera en cada réplica, habría códigos repetidos.
- **Las réplicas no guardan estado** (*stateless*): todo está en Redis. Por
  eso se pueden crear, matar o reemplazar sin perder datos.
- **Nginx re-consulta el DNS de Docker cada 5 s** (`resolver` + variable en
  `proxy_pass`), así detecta réplicas nuevas o reiniciadas.
- **`proxy_next_upstream`**: si una réplica falla a media petición, Nginx
  reintenta con otra.

## Limitaciones (siguiente fase)

- **Redis es ahora el punto único de falla**: si cae, las 3 réplicas quedan
  inservibles. Se corrige con replicación (Redis réplica + Sentinel).
- Nginx también es un punto único de falla (en producción habría varios).

---

# Fase 4 — Alta disponibilidad de Redis (réplica + Sentinel)

```
Cliente → Nginx → api ×3 ──pregunta──▶ Sentinel ×3 (vigilan)
                     │                      │
                     └──────── escribe ──▶ Redis MAESTRO ──replica──▶ Redis RÉPLICA
```

## Cómo correrlo

```bash
docker compose down -v --remove-orphans   # IMPORTANTE: limpia contenedores y volúmenes de fases anteriores
docker compose up --build
```

Ahora hay 8 contenedores de infraestructura: Nginx, 3 APIs, Redis maestro,
Redis réplica y 3 Sentinels.

## Demostración del failover (para el informe)

**Terminal 1** — inicia la prueba (acorta una URL cada 0.2 s durante 90 s):
```bash
python scripts/probar_fase4.py
```

**Terminal 2** — a los ~10 s, tumben el maestro:
```bash
docker stop acortador-redis-master-1
```

La Terminal 1 mostrará algo como:
```
[  8.2s] FALLO (HTTP 503): el servicio no puede escribir
[ 12.5s] Servicio RECUPERADO tras 4.3 s de caída
Perdidos (confirmados pero ya no existen): 0
```

**Ver quién es el maestro ahora:**
```bash
docker compose exec sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name mymaster
```

**Revivir el maestro viejo** (vuelve como *réplica* del nuevo, tarda hasta ~10 s):
```bash
docker start acortador-redis-master-1
docker compose exec redis-master redis-cli info replication   # role:slave
```

## Cómo funciona

1. El **maestro** recibe todas las escrituras y las copia a la **réplica**.
2. Los 3 **Sentinels** hacen ping al maestro. Si uno deja de responder 3 s
   (`down-after-milliseconds`), cada Sentinel lo marca como "caído".
3. Con **quórum 2 de 3** (la mayoría) se declara el maestro caído y los
   Sentinels eligen un líder que **promueve a la réplica** a maestro.
4. Las APIs no tienen la dirección de Redis fija: en cada (re)conexión le
   preguntan a Sentinel quién es el maestro (`REDIS_SENTINELS`), así encuentran
   al nuevo solas. Mientras dura el failover responden `503` con
   `Retry-After` en vez de un `500` confuso.

## Problema real que encontramos: Sentinel en modo TILT

En la primera versión Redis y los Sentinels se encontraban por **nombre**
(`redis-master`). Al tumbar el maestro, **el failover nunca ocurría**. Los
logs de Sentinel mostraban, cada ~7 s:

```
# Failed to resolve hostname 'redis-master'
# +tilt #tilt mode entered
```

Qué pasaba:
1. Al detenerse un contenedor, Docker borra su nombre del DNS interno.
2. Cada vez que Sentinel intenta resolver el nombre perdido, la consulta
   **bloquea su único hilo** varios segundos.
3. Sentinel detecta que su reloj "se atrasó" y entra en **modo TILT**: por
   seguridad deja de tomar decisiones (**no hace failover**) durante 30 s.
4. Pero cada nuevo intento de resolución lo vuelve a meter en TILT: nunca sale.

Solución: **IPs fijas** (`172.28.0.10` maestro, `.11` réplica, `.21-.23`
Sentinels) en una red con subred propia. Sin DNS no hay bloqueo, y el failover
se completa en pocos segundos.

Lección: en sistemas distribuidos, **resolver nombres puede ser parte de la ruta
crítica de recuperación**, y una dependencia lenta (DNS) puede convertir un
fallo breve en una caída larga. Detectarlo requirió leer los logs, no solo
ver que "no se recuperaba".

## Decisiones y teoría (CAP)

- **¿Por qué 3 Sentinels y quórum 2?** Con uno solo, si el propio Sentinel cae
  no hay quién vigile; con 2 no hay mayoría posible si uno cae. Con 3 se
  tolera la caída de 1. El quórum evita que un Sentinel aislado por un fallo
  de red declare caído a un maestro sano (**split brain**: dos maestros a la vez).
- **Elegimos disponibilidad sobre consistencia fuerte.** La replicación de
  Redis es **asíncrona**: el maestro responde "OK" antes de que la réplica
  confirme. Si el maestro muere justo después de aceptar una escritura que aún
  no copió, esa escritura se pierde. En nuestras pruebas con tráfico continuo
  no se perdió ninguna (la réplica copia en milisegundos), pero la garantía
  teórica es de **consistencia eventual**, no absoluta.
- **Si se pierde el contador de IDs** (peor caso, mismo escenario), el nuevo
  maestro podría reutilizar un código cuyo enlace también se perdió. Mitigación
  posible (no implementada): comando `WAIT 1 100` tras cada escritura para
  esperar la confirmación de la réplica, pagando latencia.
- La réplica **solo** sirve para failover, no para repartir lecturas: todas las
  operaciones (incluso las redirecciones) van al maestro porque cada una suma
  un clic.

## Limitaciones

- Nginx sigue siendo un punto único de falla.
- Durante el failover (~4-10 s) no se puede escribir; se pierde disponibilidad
  de forma breve pero real.
- Los datos de cada Redis siguen en un solo disco/volumen: no hay *sharding*
  (posible Fase 5: partir los datos entre varios maestros con *consistent hashing*).

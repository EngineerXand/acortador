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

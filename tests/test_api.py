"""Pruebas automáticas. Usan fakeredis (un Redis simulado en memoria),
así se pueden correr sin Docker:  pytest -v
"""

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app import base62
from app.main import app, obtener_almacen
from app.storage import Almacen


@pytest.fixture
def cliente():
    almacen = Almacen(fakeredis.FakeRedis(decode_responses=True))
    app.dependency_overrides[obtener_almacen] = lambda: almacen
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- Base62 ----------

def test_base62_ida_y_vuelta():
    for n in [0, 1, 61, 62, 125, 100000, 10**12]:
        assert base62.decodificar(base62.codificar(n)) == n


def test_base62_valores_conocidos():
    assert base62.codificar(0) == "0"
    assert base62.codificar(61) == "Z"
    assert base62.codificar(62) == "10"


# ---------- API ----------

def test_acortar_y_redirigir(cliente):
    r = cliente.post("/shorten", json={"url": "https://www.ejemplo.com/pagina/larga"})
    assert r.status_code == 201
    codigo = r.json()["codigo"]
    assert r.json()["short_url"].endswith("/" + codigo)

    r = cliente.get(f"/{codigo}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://www.ejemplo.com/pagina/larga"


def test_codigos_unicos(cliente):
    codigos = {
        cliente.post("/shorten", json={"url": "https://ejemplo.com"}).json()["codigo"]
        for _ in range(50)
    }
    assert len(codigos) == 50


def test_url_invalida(cliente):
    r = cliente.post("/shorten", json={"url": "esto no es una url"})
    assert r.status_code == 422


def test_codigo_inexistente(cliente):
    assert cliente.get("/noexiste", follow_redirects=False).status_code == 404
    assert cliente.get("/stats/noexiste").status_code == 404


def test_estadisticas_cuentan_clics(cliente):
    codigo = cliente.post("/shorten", json={"url": "https://ejemplo.com"}).json()["codigo"]
    for _ in range(3):
        cliente.get(f"/{codigo}", follow_redirects=False)
    r = cliente.get(f"/stats/{codigo}")
    assert r.status_code == 200
    assert r.json()["clics"] == 3


def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["redis"] == "ok"

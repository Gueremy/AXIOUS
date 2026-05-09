"""
tests/test_picking.py  — Sprint 2
Verifica el algoritmo de optimizacion de ruta (Nearest Neighbor + Manhattan).
Son tests unitarios puros — no necesitan BD.
"""
import pytest
from app.services.picking import distancia_manhattan, optimizar_ruta


class TestDistanciaManhattan:
    def test_misma_posicion(self):
        assert distancia_manhattan((0, 0), (0, 0)) == 0

    def test_horizontal(self):
        assert distancia_manhattan((0, 0), (0, 5)) == 5

    def test_vertical(self):
        assert distancia_manhattan((0, 0), (3, 0)) == 3

    def test_diagonal(self):
        assert distancia_manhattan((1, 1), (4, 5)) == 7

    def test_simetria(self):
        a, b = (2, 3), (5, 1)
        assert distancia_manhattan(a, b) == distancia_manhattan(b, a)


class TestOptimizarRuta:
    def test_lista_vacia(self):
        resultado = optimizar_ruta([])
        assert resultado["distancia_total"] == 0
        assert resultado["ruta_optimizada"] == []

    def test_un_container(self):
        containers = [{"id": "a", "fila": 2, "col": 3}]
        resultado = optimizar_ruta(containers)
        assert len(resultado["ruta_optimizada"]) == 1
        assert resultado["distancia_total"] == distancia_manhattan((0, 0), (2, 3))

    def test_todos_los_containers_en_ruta(self):
        containers = [
            {"id": "a", "fila": 1, "col": 1},
            {"id": "b", "fila": 3, "col": 4},
            {"id": "c", "fila": 2, "col": 2},
        ]
        resultado = optimizar_ruta(containers)
        assert len(resultado["ruta_optimizada"]) == 3

    def test_ruta_mas_corta_que_orden_aleatorio(self):
        """Nearest Neighbor debe producir distancia <= orden original en este caso."""
        containers = [
            {"id": "lejos",  "fila": 5, "col": 5},
            {"id": "cerca",  "fila": 1, "col": 1},
            {"id": "medio",  "fila": 3, "col": 3},
        ]
        # Distancia orden original: (0,0)->(5,5) + (5,5)->(1,1) + (1,1)->(3,3) = 10+8+4 = 22
        # Nearest Neighbor: (0,0)->(1,1) + (1,1)->(3,3) + (3,3)->(5,5) = 2+4+4 = 10
        resultado = optimizar_ruta(containers)
        assert resultado["distancia_total"] <= 22

    def test_distancia_cada_paso_sumada_correctamente(self):
        containers = [
            {"id": "a", "fila": 0, "col": 3},
            {"id": "b", "fila": 0, "col": 6},
        ]
        resultado = optimizar_ruta(containers, inicio=(0, 0))
        total = sum(c["distancia_desde_anterior"] for c in resultado["ruta_optimizada"])
        assert total == resultado["distancia_total"]

    def test_inicio_personalizado(self):
        containers = [{"id": "x", "fila": 4, "col": 4}]
        desde_origen = optimizar_ruta(containers, inicio=(0, 0))
        desde_cerca  = optimizar_ruta(containers, inicio=(4, 3))
        assert desde_cerca["distancia_total"] < desde_origen["distancia_total"]

    def test_campo_distancia_desde_anterior_presente(self):
        containers = [
            {"id": "a", "fila": 1, "col": 1},
            {"id": "b", "fila": 2, "col": 2},
        ]
        resultado = optimizar_ruta(containers)
        for c in resultado["ruta_optimizada"]:
            assert "distancia_desde_anterior" in c

    def test_no_modifica_lista_original(self):
        """optimizar_ruta no debe mutar la lista de entrada."""
        containers = [{"id": "a", "fila": 1, "col": 1}]
        original = [{"id": "a", "fila": 1, "col": 1}]
        optimizar_ruta(containers)
        assert containers == original

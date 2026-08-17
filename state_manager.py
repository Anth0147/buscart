"""
Módulo de Gestión de Estado y Checkpoints (state_manager.py)
============================================================
Guarda y recupera el estado de ejecución cuando ocurre una pausa,
interrupción del usuario o error crítico (2 WAFs, 2 pantallas en blanco,
2 demoras excesivas).
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
CHECKPOINT_FILE = DATA_DIR / "estado_ejecucion.json"

logger = logging.getLogger("StateManager")


def guardar_checkpoint(
    portal: str,
    script: str,
    task_idx: int,
    all_tasks: List[Dict],
    stats: Dict[str, int],
    config: Dict[str, Any],
    motivo: str = "Pausa / Error crítico",
    ultimo_error: str = ""
) -> bool:
    """
    Guarda el progreso actual de la ejecución en data/estado_ejecucion.json.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tareas_restantes = max(0, len(all_tasks) - task_idx)

    estado = {
        "activo": True,
        "portal": portal,
        "script": script,
        "timestamp": datetime.now().isoformat(),
        "task_idx": task_idx,
        "total_tasks": len(all_tasks),
        "tareas_restantes": tareas_restantes,
        "stats": stats,
        "config": config,
        "motivo": motivo,
        "ultimo_error": ultimo_error,
        "all_tasks": all_tasks
    }

    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Checkpoint guardado en {CHECKPOINT_FILE} (Progreso: {task_idx}/{len(all_tasks)})")
        return True
    except Exception as e:
        logger.error(f"Error guardando checkpoint: {e}")
        return False


def cargar_checkpoint() -> Optional[Dict]:
    """
    Carga el estado guardado si existe y está activo.
    """
    if not CHECKPOINT_FILE.exists():
        return None

    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            estado = json.load(f)
            if estado.get("activo"):
                return estado
    except Exception as e:
        logger.warning(f"Error leyendo checkpoint: {e}")
    return None


def limpiar_checkpoint():
    """
    Elimina o desactiva el checkpoint tras completar la ejecución.
    """
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                estado = json.load(f)
            estado["activo"] = False
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(estado, f, ensure_ascii=False, indent=2)
        except Exception:
            try:
                CHECKPOINT_FILE.unlink(missing_ok=True)
            except:
                pass
        logger.info("Checkpoint limpiado.")

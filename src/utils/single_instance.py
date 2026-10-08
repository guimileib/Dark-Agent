"""Garante uma única instância do DarkAgent por usuário.

Windows: mutex nomeado no namespace ``Local\\`` (por sessão de usuário). O
kernel libera o mutex quando o processo morre — inclusive em crash — então não
há lock "preso".

Outras plataformas (dev): ``QLockFile`` no tempdir, que detecta locks órfãos.

Idempotente: ``launcher.main()`` e ``main.main()`` rodam no mesmo processo e
ambos chamam ``acquire()``; a segunda chamada reaproveita o lock já obtido.
"""

import sys
import tempfile
from pathlib import Path

_MUTEX_NAME = "Local\\DarkAgentPro_SingleInstance"
_ERROR_ALREADY_EXISTS = 183

# Mantém o handle/lock vivo enquanto o processo existir.
_lock = None


def acquire() -> bool:
    """Retorna True se este processo é a única instância (ou já detém o lock)."""
    global _lock
    if _lock is not None:
        return True

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        if not handle:
            # Falha inesperada da API — não impedir o usuário de abrir o app.
            return True
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _lock = handle
        return True

    from PyQt6.QtCore import QLockFile

    lock = QLockFile(str(Path(tempfile.gettempdir()) / "darkagent_pro.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        return False
    _lock = lock
    return True


def notify_already_running() -> None:
    """Mostra o aviso de que o app já está aberto. Requer QApplication criada."""
    from PyQt6.QtWidgets import QMessageBox

    QMessageBox.information(
        None,
        "DarkAgent Pro",
        "O DarkAgent Pro já está aberto.\n\n"
        "Verifique a barra de tarefas — só é possível ter uma janela aberta por vez.",
    )

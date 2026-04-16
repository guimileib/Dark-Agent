"""
PyTorch DLL Loading Fix for Windows
Solves the DLL loading issue on Windows by preloading DLLs and adding to PATH.
Works both in development and PyInstaller frozen environments.
"""

import os
import sys
from pathlib import Path


def fix_torch_dll():
    """Add torch library directory to PATH and preload DLLs before importing torch"""
    try:
        search_dirs = []

        # In frozen (PyInstaller) mode, torch libs are bundled inside _MEIPASS
        if getattr(sys, "frozen", False):
            meipass = Path(sys._MEIPASS)
            # PyInstaller collects torch libs into these possible locations
            candidates = [
                meipass / "torch" / "lib",
                meipass / "torch" / "bin",
                meipass,
            ]
            search_dirs.extend(p for p in candidates if p.exists())
        else:
            # Dev mode: find torch via site-packages
            try:
                import site
                for sp in site.getsitepackages():
                    torch_lib = Path(sp) / "torch" / "lib"
                    if torch_lib.exists():
                        search_dirs.append(torch_lib)
                    torch_bin = Path(sp) / "torch" / "bin"
                    if torch_bin.exists():
                        search_dirs.append(torch_bin)
            except Exception:
                pass

            # Also check sys.path entries
            for p in sys.path:
                torch_lib = Path(p) / "torch" / "lib"
                if torch_lib.exists() and torch_lib not in search_dirs:
                    search_dirs.append(torch_lib)

        if not search_dirs:
            print("[torch_fix] Warning: torch/lib directory not found")
            return False

        for torch_dir in search_dirs:
            torch_dir_str = str(torch_dir)

            # Add to PATH at the beginning
            os.environ["PATH"] = torch_dir_str + os.pathsep + os.environ.get("PATH", "")

            # Try to add DLL directory (Python 3.8+)
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(torch_dir_str)
                except Exception:
                    pass

        # Preload critical DLLs from the first found directory
        try:
            import ctypes
            critical_dlls = [
                "fbgemm.dll",
                "asmjit.dll",
                "cpuinfo.dll",
                "c10.dll",
                "torch_cpu.dll"
            ]

            for dll in critical_dlls:
                for torch_dir in search_dirs:
                    dll_path = torch_dir / dll
                    if dll_path.exists():
                        try:
                            ctypes.CDLL(str(dll_path))
                        except Exception:
                            pass
                        break

        except Exception:
            pass

        print(f"[torch_fix] PyTorch library paths configured: {[str(d) for d in search_dirs]}")
        return True

    except Exception as e:
        print(f"[torch_fix] Error fixing torch DLL: {e}")
        return False


# Apply fix on module import
fix_torch_dll()

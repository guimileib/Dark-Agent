"""
PyTorch DLL Loading Fix for Windows
Solves the DLL loading issue on Windows by preloading DLLs and adding to PATH
"""

import os
import sys
from pathlib import Path


def fix_torch_dll():
    """Add torch library directory to PATH and preload DLLs before importing torch"""
    try:
        # Try to find torch installation
        import site
        
        # Get site-packages directories
        site_packages = site.getsitepackages()
        
        for sp in site_packages:
            torch_lib = Path(sp) / "torch" / "lib"
            if torch_lib.exists():
                # Add to PATH at the beginning
                torch_lib_str = str(torch_lib)
                os.environ["PATH"] = torch_lib_str + os.pathsep + os.environ.get("PATH", "")
                
                # Also add torch/bin if it exists
                torch_bin = Path(sp) / "torch" / "bin"
                if torch_bin.exists():
                    os.environ["PATH"] = str(torch_bin) + os.pathsep + os.environ.get("PATH", "")
                
                # Try to add DLL directory (Python 3.8+)
                if hasattr(os, 'add_dll_directory'):
                    try:
                        os.add_dll_directory(str(torch_lib))
                        print(f"[torch_fix] Added DLL directory: {torch_lib_str}")
                    except Exception as e:
                        print(f"[torch_fix] Could not add DLL directory: {e}")
                
                # Preload critical DLLs
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
                        dll_path = torch_lib / dll
                        if dll_path.exists():
                            try:
                                ctypes.CDLL(str(dll_path))
                                print(f"[torch_fix] Preloaded: {dll}")
                            except Exception as e:
                                print(f"[torch_fix] Could not preload {dll}: {e}")
                
                except Exception as e:
                    print(f"[torch_fix] Error preloading DLLs: {e}")
                
                print(f"[torch_fix] PyTorch library path configured: {torch_lib_str}")
                return True
        
        print("[torch_fix] Warning: torch/lib directory not found")
        return False
        
    except Exception as e:
        print(f"[torch_fix] Error fixing torch DLL: {e}")
        return False


# Apply fix on module import
fix_torch_dll()

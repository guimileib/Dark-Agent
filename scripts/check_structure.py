"""Checagem estrutural do DarkAgent — roda no CI (push/PR para main) e no build_exe.bat.

Pega, sem precisar buildar o .exe, as classes de erro que já quebraram releases:
  - pacote de src/ fora do git (ex.: src/models/ ignorado por `models/` no .gitignore)
  - subpacote novo fora do collect_submodules do .spec
  - .spec sem pathex/datas/hiddenimports obrigatórios (ver CLAUDE.md)
  - __version__ inválido (quebra a comparação do auto-update)
  - Path(__file__) fora dos bootstraps, Gemini key em query param, cookies commitados

Uso:
    python scripts/check_structure.py             # checagens estáticas (rápido)
    python scripts/check_structure.py --imports   # + importa todos os módulos de src/
                                                  #   (precisa das deps instaladas)
"""

import argparse
import ast
import importlib
import os
import pkgutil
import re
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SPEC = ROOT / "DarkAgentLauncher.spec"

# Únicos arquivos autorizados a usar Path(__file__): rodam antes de config.paths existir.
PATH_FILE_ALLOWED = {"src/config/paths.py", "src/launcher.py", "src/main.py"}

SPEC_REQUIRED = {
    "pathex=['src']": "sem isso o PyInstaller não resolve `config.*`, `models.*`, ...",
    "('src/__init__.py', 'src')": "main.py faz `from src import __version__`",
    "'main'": "hiddenimport late-bound do launcher",
    "'torch_fix'": "hiddenimport late-bound do main",
    "'yt_dlp'": "downloader roda `exe -m yt_dlp`; sem collect_all o download quebra",
    "console=False": "exe windowed",
}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"  ✗ {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def py_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def git(*args: str) -> list[str] | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [line for line in out.splitlines() if line]


def check_syntax() -> None:
    print("[syntax]")
    bad = 0
    for p in py_files() + list((ROOT / "tests").glob("*.py")) + [ROOT / "scripts" / "check_structure.py"]:
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as e:
            bad += 1
            fail(f"{rel(p)}:{e.lineno}: {e.msg}")
    if not bad:
        ok("todos os .py compilam")


def subpackages() -> list[str]:
    return sorted(
        d.name for d in SRC.iterdir()
        if d.is_dir() and (d / "__init__.py").exists() and d.name != "__pycache__"
    )


def check_spec() -> None:
    print("[spec]")
    if not SPEC.exists():
        fail("DarkAgentLauncher.spec não existe (build_exe.bat antigo apagava o arquivo)")
        return
    text = SPEC.read_text(encoding="utf-8")

    for token, why in SPEC_REQUIRED.items():
        if token in text:
            ok(f"{token}")
        else:
            fail(f".spec sem {token} — {why}")

    m = re.search(r"for _pkg in \(([^)]*)\):\s*\n\s*hiddenimports \+= collect_submodules", text)
    if not m:
        fail(".spec sem o loop `collect_submodules` dos subpacotes de src/")
        return
    listed = set(re.findall(r"'(\w+)'", m.group(1)))
    missing = [p for p in subpackages() if p not in listed]
    if missing:
        fail(f"subpacotes fora do collect_submodules do .spec: {', '.join(missing)}")
    else:
        ok(f"collect_submodules cobre {', '.join(subpackages())}")


def check_git_tracking() -> None:
    print("[git]")
    ignored = git("ls-files", "--others", "--ignored", "--exclude-standard", "--", "src")
    if ignored is None:
        print("  - git indisponível, pulando")
        return
    ignored_py = [f for f in ignored if f.endswith(".py") and "__pycache__" not in f]
    if ignored_py:
        fail(
            "código-fonte ignorado pelo .gitignore (não chega ao CI/build): "
            + ", ".join(ignored_py)
        )
    else:
        ok("nenhum .py de src/ ignorado")

    tracked = git("ls-files") or []
    secrets = [
        f for f in tracked
        if re.search(r"(^|/)cookies[^/]*\.txt$|(^|/)\.env$|(^|/)config/config\.json$", f)
    ]
    if secrets:
        fail(f"arquivos sensíveis versionados: {', '.join(secrets)}")
    else:
        ok("nenhum cookies/.env/config.json versionado")


def check_version() -> None:
    print("[version]")
    tree = ast.parse((SRC / "__init__.py").read_text(encoding="utf-8"))
    version = next(
        (
            n.value.value for n in tree.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)
            and isinstance(n.value, ast.Constant)
        ),
        None,
    )
    if version and re.fullmatch(r"\d+\.\d+\.\d+", version):
        ok(f"__version__ = {version}")
    else:
        fail(f"__version__ ausente ou fora do formato X.Y.Z: {version!r}")


def check_code_rules() -> None:
    print("[regras do CLAUDE.md]")
    n = len(errors)
    for p in py_files():
        r = rel(p)
        text = p.read_text(encoding="utf-8")
        if "Path(__file__)" in text and r not in PATH_FILE_ALLOWED:
            fail(f"{r}: usa Path(__file__) — importar de config.paths (quebra no .exe)")
        if re.search(r"generativelanguage[^\n]*[?&]key=", text):
            fail(f"{r}: Gemini key na URL — usar header x-goog-api-key")
    if len(errors) == n:
        ok("Path(__file__) e Gemini key OK")


def check_imports() -> None:
    print("[imports]")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    for p in (str(SRC), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)

    modules = ["torch_fix", "main", "launcher", "yt_dlp", "Cryptodome.Cipher.AES"]
    for pkg in subpackages():
        modules.append(pkg)
        mod = importlib.import_module(pkg)
        modules += [
            m.name for m in pkgutil.walk_packages(mod.__path__, prefix=f"{pkg}.")
        ]

    bad = 0
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001
            bad += 1
            fail(f"import {name}: {type(e).__name__}: {e}")
            traceback.print_exc(limit=3)
    if not bad:
        ok(f"{len(modules)} módulos importados")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--imports", action="store_true", help="também importa todos os módulos")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ✓/✗ em console cp1252

    check_syntax()
    check_spec()
    check_git_tracking()
    check_version()
    check_code_rules()
    if args.imports:
        check_imports()

    print()
    if errors:
        print(f"FALHOU: {len(errors)} problema(s)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

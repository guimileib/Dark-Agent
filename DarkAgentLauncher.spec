# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ('src/assets', 'src/assets'),
    ('src/config/estilos_padrao.json', 'src/config'),
    ('src/config/config.json', 'src/config'),
    ('src/__init__.py', 'src'),
]
binaries = []
hiddenimports = [
    'PIL',
    'PyQt6',
    'PyQt6.QtSvg',
    'PyQt6.QtSvgWidgets',
    'main',
    'torch_fix',
]

# Garantir que todos os subpacotes de src/ entrem no bundle, mesmo que sejam
# carregados via import dinâmico/deferido.
for _pkg in ('config', 'models', 'ui', 'utils', 'core'):
    hiddenimports += collect_submodules(_pkg)

tmp_ret = collect_all('whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('torch')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['src\\launcher.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DarkAgentLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src\\assets\\icon.png'],
)

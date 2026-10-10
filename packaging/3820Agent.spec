# -*- mode: python ; coding: utf-8 -*-
"""Build with: python -m PyInstaller --noconfirm packaging/3820Agent.spec"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


root = Path(SPECPATH).parent
datas = [
    (str(root / 'web'), 'web'),
    (str(root / 'docs' / '基于3820战略工程内容的多智能体系统搭建指南.md'), 'docs'),
    *[(str(path), 'knowledge') for path in (root / 'knowledge').glob('*.json')],
    *collect_data_files('webview'),
]
hiddenimports = collect_submodules('uvicorn') + collect_submodules('webview')

analysis = Analysis(
    [str(root / 'desktop.py')],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'IPython', 'jupyter', 'matplotlib'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True,
    name='3820Agent',
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, analysis.binaries, analysis.datas,
               strip=False, upx=False, name='3820Agent')

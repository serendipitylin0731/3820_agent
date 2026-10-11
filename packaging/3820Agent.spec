# -*- mode: python ; coding: utf-8 -*-
"""Build with: python -m PyInstaller --noconfirm packaging/3820Agent.spec"""

from pathlib import Path


root = Path(SPECPATH).parent
datas = [
    (str(root / 'packaging' / 'logo.png'), 'packaging'),
    (str(root / 'packaging' / '3820Agent.ico'), 'packaging'),
    (str(root / 'docs' / '3820背景.md'), 'docs'),
    (str(root / 'docs' / '基于3820战略工程内容的多智能体系统搭建指南.md'), 'docs'),
    *[(str(path), 'knowledge') for path in (root / 'knowledge').glob('*.json')],
]
hiddenimports = []

analysis = Analysis(
    [str(root / 'desktop.py')],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'IPython', 'jupyter', 'matplotlib', 'webview', 'uvicorn'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True,
    name='3820Agent',
    console=False,
    manifest=str(root / 'packaging' / '3820Agent.manifest'),
    icon=str(root / 'packaging' / '3820Agent.ico'),
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, analysis.binaries, analysis.datas,
               strip=False, upx=False, name='3820Agent')

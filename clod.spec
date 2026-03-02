# -*- mode: python ; coding: utf-8 -*-
import os
import rich as _rich

# Path to the installed rich package
RICH_DIR = os.path.dirname(_rich.__file__)

# Collect all _unicode_data .py files as DATA (not as frozen modules).
# PyInstaller can't freeze modules whose names contain dashes, so we ship
# them as plain files and load them at runtime via the pyi_rth_rich_unicode hook.
unicode_data_src = os.path.join(RICH_DIR, "_unicode_data")
unicode_data_files = [
    (os.path.join(unicode_data_src, f), os.path.join("rich", "_unicode_data"))
    for f in os.listdir(unicode_data_src)
    if f.endswith(".py")
]

# Config files that docker-compose services need as bind-mounts.
# Bundled so the exe can restore them offline on first run.
config_datas = [
    ('docker-compose.yml',              '.'),
    ('litellm/config.yaml',             'litellm'),
    ('searxng/settings.yml',            'searxng'),
    ('nginx/nginx.conf',                'nginx'),
    ('pipelines/code_review_pipe.py',   'pipelines'),
    ('pipelines/reason_review_pipe.py', 'pipelines'),
    ('pipelines/chat_assist_pipe.py',   'pipelines'),
    ('pipelines/claude_review_pipe.py', 'pipelines'),
    ('.env.example',                    '.'),
]

a = Analysis(
    ['clod.py'],
    pathex=[],
    binaries=[],
    datas=unicode_data_files + config_datas,
    hiddenimports=[
        "mcp_server",
        "rich",
        "rich._unicode_data",
        "rich._unicode_data._versions",
        "rich.cells",
        "rich.console",
        "rich.panel",
        "rich.text",
        "rich.padding",
        "rich.measure",
        "rich.markup",
        "rich.style",
        "rich.theme",
        "rich.color",
        "rich.highlighter",
        "rich.syntax",
        "rich.progress",
        "rich.prompt",
        "rich.table",
        "rich.live",
        "rich.spinner",
        "rich.columns",
        "rich.segment",
        "rich.region",
        "rich.control",
        "rich.ansi",
        "rich.emoji",
        "rich.filesize",
        "rich.logging",
        "rich.pretty",
        "rich.traceback",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthooks/pyi_rth_rich_unicode.py'],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    a.zipfiles,
    [],
    name='clod',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

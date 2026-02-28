"""
Runtime hook: pre-register rich._unicode_data submodules in sys.modules.

PyInstaller cannot store or import Python modules whose names contain dashes
(e.g. rich._unicode_data.unicode17-0-0). This hook loads those files directly
from sys._MEIPASS using importlib.util and registers them before rich's
_unicode_data.load() is ever called.
"""
import importlib.util
import os
import sys

_meipass = getattr(sys, "_MEIPASS", None)
if _meipass:
    _data_dir = os.path.join(_meipass, "rich", "_unicode_data")
    if os.path.isdir(_data_dir):
        for _fname in os.listdir(_data_dir):
            if not _fname.endswith(".py"):
                continue
            _mod_stem = _fname[:-3]  # strip .py
            if _mod_stem.startswith("__"):
                continue
            _full_name = f"rich._unicode_data.{_mod_stem}"
            if _full_name in sys.modules:
                continue
            _fpath = os.path.join(_data_dir, _fname)
            try:
                _spec = importlib.util.spec_from_file_location(_full_name, _fpath)
                _mod = importlib.util.module_from_spec(_spec)
                _mod.__package__ = "rich._unicode_data"
                sys.modules[_full_name] = _mod
                _spec.loader.exec_module(_mod)
            except Exception:
                pass

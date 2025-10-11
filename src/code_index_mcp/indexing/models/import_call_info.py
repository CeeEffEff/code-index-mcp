"""
SymbolInfo model for representing called, imported code symbols.
"""


import logging
from dataclasses import dataclass
from importlib.machinery import PathFinder, ModuleSpec as _ModuleSpec
from importlib.util import find_spec, module_from_spec
from typing import Optional
import os
import sys
import inspect

from .symbol_info import SymbolInfo 

logger = logging.getLogger(__name__)


class ModuleSpec:

    def __init__(self, spec: _ModuleSpec, venv_pkgs: str = None, project_root: str = None, try_inspect = False):
        self.spec = spec
        self.initialised = False
        self._classes = {}
        self._functions = {}
        self._methods = {}
        self.venv_pkgs = venv_pkgs
        self.python_path_before = os.environ.get('PYTHONPATH', '')
        self.python_path = self.python_path_before
        self.project_root = project_root
        self.try_inspect = try_inspect

    def _getmembers(self):
        if self.try_inspect:
            try:
                # sys.path.insert(-1, self.venv_pkgs or self.spec.origin)
                sys.path.insert(-1, self.venv_pkgs or self.spec.origin or self.project_root)
                # sys.path.insert(-1, self.venv_pkgs or self.spec.origin or (self.spec.submodule_search_locations[0] if self.spec.submodule_search_locations else None)
                os.environ['PYTHONPATH'] = self.python_path
                self._module = module_from_spec(self.spec)
                self.spec.loader.exec_module(self._module)  # Errors because module has dependencies different to this repo (of course). This repo inspects other repos, but has its own dependencies.
                self._classes = {k: v for k, v in inspect.getmembers(self._module, inspect.isclass)}
                self._functions = {k: v for k, v in inspect.getmembers(self._module, inspect.isfunction)}
                self._methods = {f"{type(v.__self__).__name__}.{k}": v for k, v in inspect.getmembers(self._module, inspect.ismethod)}
                self.initialised = True
                return
            except Exception as e:
                logger.warning(f"Exception [{e}] when getting members for {self.spec.name} ({self.spec.origin}) :\n{list(self.classes.keys())[0:10]=}...\n{list(self.functions.keys())[0:10]=}...\n{list(self.methods.keys())[0:10]=}...\n")
            finally:
                sys.path.pop(-1)
                os.environ['PYTHONPATH'] = self.python_path_before
        if not self.spec.origin:
            return
        if "built-in" in self.spec.origin or "frozen" in self.spec.origin:
            return
        try:
            from ..strategies import python_strategy
            file_content = None
            with open(self.spec.origin) as mod_file:
                file_content = mod_file.read()
            module_symbols, module_file_info = python_strategy.PythonParsingStrategy().parse_file(self.spec.origin, file_content, self.spec.origin, self.venv_pkgs, explore_imports=False)
            logger.debug(f"{module_symbols=}")
            logger.debug(f"{module_file_info.symbols=}")
            self._classes = {name: info for name, info in module_symbols.items() if info.type == "class"}
            self._functions = {name: info for name, info in module_symbols.items() if info.type == "function"}
            self._methods = {name: info for name, info in module_symbols.items() if info.type == "method"}
            self.initialised = True
        except Exception as e:
            if self.spec.origin and "built-in" not in self.spec.origin:
                logger.warning(f"Exception [{e}] when getting members for {self.spec.name} ({self.spec.origin}) :\n{list(self.classes.keys())[0:10]=}...\n{list(self.functions.keys())[0:10]=}...\n{list(self.methods.keys())[0:10]=}...\n", exc_info=True)
            self.initialised = False


    @property
    def classes(self):
        return self._classes

    @property
    def functions(self):
        return self._functions

    @property
    def methods(self):
        return self._methods

    def try_get_symbol_type(self, symbol_id: str) -> Optional[str]:
        """
        Determine if the given symbol string is a class, function, or method.
        The string format is like (<relative-path>::)<imported-symbol>
        Parentheses indicate optional parts of the string.

        Args:
            symbol_str (str): The symbol string to check.

        Returns:
            Optional[str]: 'class', 'function', or 'method', or None if not found.
        """
        try:
            # Split the string into path and symbol parts
            if "::" in symbol_id:
                symbol_path, symbol_part = symbol_id.split("::", 1)
                # abs_id = os.path.abspath(symbol_path) + "::" + symbol_part
                # abs_id = os.path.abspath(symbol_path).removeprefix(self.project_root) + "::" + symbol_part
                # abs_id = os.path.abspath(symbol_path) + "/" + symbol_id
                # symbol_path is relative to project root
                abs_id = os.path.abspath(os.path.join(self.project_root, symbol_path)) + "::" + symbol_part  # TODO still not sure on this
                
            else:
                symbol_part = symbol_id
                abs_id = None
            if not self.initialised:
                self._getmembers()
            if not self.initialised:
                raise ValueError("Not initialised.")

            # Now check if the symbol is a class, function, or method
            if symbol_part in self.classes or symbol_id in self.classes or abs_id in self.classes:
                return "class"
            if symbol_part in self.functions or symbol_id in self.functions or abs_id in self.functions:
                return "function"
            if symbol_part in self.methods or symbol_id in self.methods or abs_id in self.methods:
                return "method"
        except ValueError:
            logger.debug("Not initialised?", exc_info=True)
            return
        except Exception as e:
            logger.exception(f"Exception when determining type of {symbol_id=} ({symbol_part=}): {e}", exc_info=True)
        logger.debug(f"Couldn't determine type of {symbol_id} ({symbol_part=}, {abs_id=}) from loaded symbols:\n{list(self.classes.keys())[0:10]=}...\n{list(self.functions.keys())[0:10]=}...\n{list(self.methods.keys())[0:10]=}...\n")
        return None


@dataclass
class ImportCallInfo:
    """Information about a called code symbol (function, class, method, etc.)."""
    import_spec: ModuleSpec
    import_relative_path: str
    called_symbol_id: str
    called_symbol_info: SymbolInfo

    @staticmethod
    def get_import_spec(import_fullname, path: str = None, project_root: str = None, import_module: str = None, venv_root: str = None) -> Optional[ModuleSpec]:
        def _get_import_spec():
            spec = ImportCallInfo._get_spec(
                project_root=project_root,
                find_spec_function=PathFinder.find_spec,
                import_fullname=import_fullname,
                path=None,
                venv_root=venv_root,
            )
            if spec:
                return spec

            spec = ImportCallInfo._get_spec(
                project_root=project_root,
                find_spec_function=PathFinder.find_spec,  # Using find instead of find_spec
                import_fullname=import_fullname,
                path=path,
                venv_root=venv_root,
            )
            if spec:
                return spec

            spec = ImportCallInfo._get_spec(
                project_root=project_root,
                find_spec_function=find_spec,
                import_fullname=import_fullname,
                venv_root=venv_root,
            )
            if spec:
                return spec

            if (not spec) and import_module:
                spec = ImportCallInfo.get_import_spec(import_module, path, project_root, import_module=None, venv_root=venv_root)
            return spec
        spec = _get_import_spec()
        return spec

    @staticmethod
    def _get_spec(project_root: str, find_spec_function, import_fullname: str, venv_root: str = None, *fn_args, **fn_kwargs) -> Optional[ModuleSpec]:
        """
        Abstracted method to get the import spec using the provided function.
        """
        venv_pkgs = ImportCallInfo._setup_paths(project_root, venv_root)
        try:
            _spec = find_spec_function(import_fullname, *fn_args, *fn_kwargs)
        except Exception as e:
            logger.debug(e, exc_info=True)
            ImportCallInfo._cleanup_paths(project_root, venv_pkgs)
            return None
        if not _spec:
            return None
        spec = None
        try:
            spec = ModuleSpec(spec=_spec, venv_pkgs=venv_pkgs, project_root=project_root)
        except Exception as e:
            logger.debug(e, exc_info=True)
        finally:
            ImportCallInfo._cleanup_paths(project_root, venv_pkgs)
        return spec

    @staticmethod
    def _setup_paths(project_root: str, venv_root: str = None) -> Optional[str]:
        """Sets up the paths for import operations."""
        sys.path.append(project_root)
        venv_pkgs = ImportCallInfo.get_venv_site_packages(project_root, venv_root)
        sys.path.append(venv_pkgs)
        # Optionally, set the path for the import operation
        # if path:
        #     os.environ['PYTHONPATH'] = path
        return venv_pkgs

    @staticmethod
    def _cleanup_paths(*args):
        """Cleans up the paths after import operations."""
        for arg in args:
            if arg in sys.path:
                sys.path.remove(arg)

    @staticmethod
    def get_venv_site_packages(project_root: Optional[str] = None, venv_root: Optional[str] = None):
        # Determine the project root (assuming script is run from project root)
        project_root = project_root or os.getcwd()
        venv_dir = venv_root or os.path.join(project_root, ".venv")

        # Read Python version from .python-version
        python_version = ""
        python_version_file = os.path.join(project_root, ".python-version")
        if os.path.exists(python_version_file):
            with open(python_version_file, "r") as f:
                python_version = f.read().strip()
        
        # Fallback: use Python version from sys if .python-version is missing
        if not python_version:
            python_version = sys.version.split()[0]
        
        # Construct the site-packages path
        if os.name == "posix":  # Unix-like systems
            site_packages = os.path.join(
                venv_dir, "lib", f"python{python_version}", "site-packages"
            )
        else:  # Windows
            site_packages = os.path.join(
                venv_dir, "Scripts", "site-packages"
            )
        logger.debug(
            f"{project_root=}\n"
            f"{venv_dir=}\n"
            f"{python_version_file=}\n"
            f"{python_version=}\n"
            f"{site_packages=}\n"
        )
        return site_packages

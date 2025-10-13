"""
Index Management Service - Business logic for index lifecycle management.

This service handles the business logic for index rebuilding, status monitoring,
and index-related operations using the new JSON-based indexing system.
"""
import time
import logging

from typing import Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from .base_service import BaseService
from ..indexing import get_index_manager


@dataclass
class IndexRebuildResult:
    """Business result for index rebuild operations."""
    file_count: int
    rebuild_time: float
    status: str
    message: str


class IndexManagementService(BaseService):
    """
    Business service for index lifecycle management.

    This service orchestrates index management workflows using the new
    JSON-based indexing system for optimal LLM performance.
    """

    def __init__(self, ctx):
        super().__init__(ctx)
        self._index_manager = get_index_manager()

    def rebuild_index(self) -> str:
        """
        Rebuild the project index using the new JSON indexing system.

        Returns:
            Success message with rebuild information

        Raises:
            ValueError: If project not set up or rebuild fails
        """
        # Business validation
        self._validate_rebuild_request()

        # Business workflow: Execute rebuild
        result = self._execute_rebuild_workflow()

        # Business result formatting
        return self._format_rebuild_result(result)

    def get_rebuild_status(self) -> Dict[str, Any]:
        """
        Get current index rebuild status information.

        Returns:
            Dictionary with rebuild status and metadata
        """
        # Check if project is set up
        if not self.base_path:
            return {
                'status': 'not_initialized',
                'message': 'Project not initialized',
                'is_rebuilding': False
            }

        # Get index stats from the new JSON system
        stats = self._index_manager.get_index_stats()
        
        return {
            'status': 'ready' if stats.get('status') == 'loaded' else 'needs_rebuild',
            'index_available': stats.get('status') == 'loaded',
            'is_rebuilding': False,
            'project_path': self.base_path,
            'file_count': stats.get('indexed_files', 0),
            'total_symbols': stats.get('total_symbols', 0),
            'symbol_types': stats.get('symbol_types', {}),
            'languages': stats.get('languages', [])
        }

    def _validate_rebuild_request(self) -> None:
        """
        Validate the index rebuild request according to business rules.

        Raises:
            ValueError: If validation fails
        """
        # Business rule: Project must be set up
        self._require_project_setup()

    def _execute_rebuild_workflow(self) -> IndexRebuildResult:
        """
        Execute the core index rebuild business workflow.

        Returns:
            IndexRebuildResult with rebuild data
        """
        start_time = time.time()

        # Set project path in index manager
        if self.settings.base_venv:
            self._index_manager.set_venv_path(self.settings.base_venv, init=False)
        if not self._index_manager.set_project_path(self.base_path):
            raise RuntimeError("Failed to set project path in index manager")

        # Rebuild the index
        if not self._index_manager.refresh_index():
            raise RuntimeError("Failed to rebuild index")

        # Get stats for result
        stats = self._index_manager.get_index_stats()
        file_count = stats.get('indexed_files', 0)

        rebuild_time = time.time() - start_time

        return IndexRebuildResult(
            file_count=file_count,
            rebuild_time=rebuild_time,
            status='success',
            message=f"Index rebuilt successfully with {file_count} files"
        )


    def _format_rebuild_result(self, result: IndexRebuildResult) -> str:
        """
        Format the rebuild result according to business requirements.

        Args:
            result: Rebuild result data

        Returns:
            Formatted result string for MCP response
        """
        return f"Project re-indexed. Found {result.file_count} files."

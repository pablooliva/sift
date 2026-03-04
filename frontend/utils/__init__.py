"""Utility modules for txtai frontend"""

from .api_client import TxtAIClient, APIHealthStatus, escape_for_markdown, generate_knowledge_summary, should_enable_entity_view, generate_entity_groups
from .config_validator import ConfigValidator, ValidationResult
from .document_processor import (
    DocumentProcessor,
    create_category_selector,
    validate_categories,
    get_manual_categories,
    get_category_colors,
    get_category_display_name
)
from .graph_builder import (
    build_graph_data,
    create_graph_config,
    filter_documents_by_category,
    compute_node_degrees,
    CATEGORY_COLORS,
    DEFAULT_COLOR
)

__all__ = [
    'TxtAIClient', 'APIHealthStatus', 'escape_for_markdown', 'generate_knowledge_summary',
    'should_enable_entity_view', 'generate_entity_groups',
    'ConfigValidator', 'ValidationResult',
    'DocumentProcessor', 'create_category_selector', 'validate_categories',
    'get_manual_categories', 'get_category_colors', 'get_category_display_name',
    'build_graph_data', 'create_graph_config', 'filter_documents_by_category',
    'compute_node_degrees', 'CATEGORY_COLORS', 'DEFAULT_COLOR'
]

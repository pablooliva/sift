"""
Configuration Validation Utility

Validates txtai configuration for critical settings.
Implements REQ-018: Verify graph.approximate: false in config.yml.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ValidationResult:
    """Configuration validation result"""

    def __init__(self, is_valid: bool, errors: List[str], warnings: List[str]):
        self.is_valid = is_valid
        self.errors = errors
        self.warnings = warnings

    def __bool__(self):
        return self.is_valid

    def get_message(self) -> str:
        """Get formatted validation message"""
        if self.is_valid:
            msg = "✅ Configuration is valid"
            if self.warnings:
                msg += f"\n\nWarnings:\n" + "\n".join(f"⚠️ {w}" for w in self.warnings)
            return msg
        else:
            msg = "❌ Configuration validation failed\n\nErrors:\n"
            msg += "\n".join(f"❌ {e}" for e in self.errors)
            if self.warnings:
                msg += f"\n\nWarnings:\n" + "\n".join(f"⚠️ {w}" for w in self.warnings)
            return msg


class ConfigValidator:
    """Validates txtai configuration file"""

    REQUIRED_GRAPH_SETTINGS = {
        "approximate": False  # CRITICAL: Must be False for relationship discovery
    }

    def __init__(self, config_path: str = "../config.yml"):
        """
        Initialize config validator.

        Args:
            config_path: Path to config.yml file (relative to frontend/)
        """
        self.config_path = Path(config_path)
        self.config = None

    def load_config(self) -> bool:
        """
        Load configuration file.

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not self.config_path.exists():
                logger.error(f"Config file not found: {self.config_path}")
                return False

            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)

            return True

        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in config file: {e}")
            return False

        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return False

    def validate(self) -> ValidationResult:
        """
        Validate configuration against requirements.
        CRITICAL: Implements REQ-018 - graph.approximate check.

        Returns:
            ValidationResult object
        """
        errors = []
        warnings = []

        # Load config if not already loaded
        if self.config is None:
            if not self.load_config():
                return ValidationResult(
                    is_valid=False,
                    errors=["Failed to load configuration file"],
                    warnings=[]
                )

        # Check for writable mode (required for document ingestion)
        if not self.config.get('writable', False):
            errors.append(
                "Configuration must have 'writable: true' for document ingestion"
            )

        # Check embeddings configuration
        if 'embeddings' not in self.config:
            errors.append("Missing 'embeddings' configuration")
        else:
            embeddings = self.config['embeddings']
            if 'path' not in embeddings:
                errors.append("Missing 'embeddings.path' (model specification)")
            if 'content' not in embeddings:
                warnings.append(
                    "'embeddings.content' not set - may affect document storage"
                )

        # CRITICAL: Check graph configuration
        # Reference: SPEC-001 A4, progress.md:126-134
        if 'graph' not in self.config:
            errors.append(
                "CRITICAL: Missing 'graph' configuration. "
                "This is required for relationship discovery. "
                "Add to config.yml:\n"
                "graph:\n"
                "  approximate: false  # REQUIRED for proper relationship discovery\n"
                "  limit: 15\n"
                "  minscore: 0.1"
            )
        else:
            graph_config = self.config['graph']

            # Check approximate setting (CRITICAL)
            if 'approximate' not in graph_config:
                errors.append(
                    "CRITICAL: Missing 'graph.approximate' setting. "
                    "Must be set to 'false' for new documents to discover relationships to existing content. "
                    "Add: graph.approximate: false"
                )
            elif graph_config['approximate'] is not False:
                errors.append(
                    f"CRITICAL: graph.approximate is set to '{graph_config['approximate']}' but MUST be 'false'. "
                    "Without this, new documents won't connect to existing knowledge base. "
                    "Change to: graph.approximate: false"
                )

            # Check optional graph settings
            if 'limit' not in graph_config:
                warnings.append(
                    "graph.limit not set - using txtai default. "
                    "Consider setting to 15 for balanced connection density."
                )

            if 'minscore' not in graph_config:
                warnings.append(
                    "graph.minscore not set - using txtai default. "
                    "Consider setting to 0.1 for reasonable similarity threshold."
                )

        # Check path configuration
        if 'path' not in self.config:
            warnings.append(
                "No 'path' specified - txtai will use default location for SQLite database"
            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def get_graph_status(self) -> Dict[str, Any]:
        """
        Get detailed graph configuration status.

        Returns:
            Dict with graph config details and validation status
        """
        if self.config is None:
            self.load_config()

        if 'graph' not in self.config:
            return {
                "configured": False,
                "approximate": None,
                "status": "missing",
                "message": "Graph configuration not found in config.yml"
            }

        graph_config = self.config['graph']
        approximate = graph_config.get('approximate', None)

        if approximate is False:
            status = "correct"
            message = "✅ Graph configuration is correct (approximate: false)"
        elif approximate is True:
            status = "incorrect"
            message = "❌ Graph configuration is INCORRECT (approximate: true). Change to false!"
        else:
            status = "missing"
            message = "⚠️ graph.approximate setting is missing. Add 'approximate: false'"

        return {
            "configured": True,
            "approximate": approximate,
            "limit": graph_config.get('limit'),
            "minscore": graph_config.get('minscore'),
            "status": status,
            "message": message
        }

    def suggest_graph_config(self) -> str:
        """
        Generate suggested graph configuration.

        Returns:
            YAML snippet for graph configuration
        """
        return """# Knowledge Graph Configuration
# CRITICAL: approximate must be false for relationship discovery
graph:
  approximate: false  # REQUIRED - ensures new documents connect to existing knowledge
  limit: 15          # Maximum connections per node
  minscore: 0.1      # Minimum similarity threshold (0.0-1.0)
"""

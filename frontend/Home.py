"""
txtai Personal Knowledge Management Interface

Main application entry point with health checks and navigation.
Implements REQ-020: API connectivity validation on startup.
"""

import streamlit as st
import os
import shutil
from glob import glob
from pathlib import Path
from dotenv import load_dotenv
import sys

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.api_client import TxtAIClient, APIHealthStatus
from utils.config_validator import ConfigValidator
import logging_config

# Load environment variables
load_dotenv()

# Initialize logging (must be done early, before any logging calls)
import logging
try:
    logging_config.setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("txtai Frontend application starting")
except Exception as e:
    # Fallback to basic console logging if file logging fails
    logging.basicConfig(level=logging.INFO)
    logging.error(f"Failed to initialize file logging: {e}")

# Page configuration
st.set_page_config(
    page_title="txtai Knowledge Manager",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .status-healthy {
        color: #00cc00;
        font-weight: bold;
    }
    .status-unhealthy {
        color: #ff0000;
        font-weight: bold;
    }
    .status-unknown {
        color: #ff9900;
        font-weight: bold;
    }
    .error-banner {
        background-color: #ffe6e6;
        border-left: 5px solid #ff0000;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
    .warning-banner {
        background-color: #fff3cd;
        border-left: 5px solid #ff9900;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
    .success-banner {
        background-color: #d4edda;
        border-left: 5px solid #00cc00;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)


def initialize_session_state():
    """Initialize Streamlit session state variables"""
    if 'api_client' not in st.session_state:
        api_url = os.getenv('TXTAI_API_URL', 'http://localhost:8300')
        st.session_state.api_client = TxtAIClient(base_url=api_url)

    if 'config_validator' not in st.session_state:
        config_path = Path(__file__).parent.parent / 'config.yml'
        st.session_state.config_validator = ConfigValidator(str(config_path))

    if 'health_checked' not in st.session_state:
        st.session_state.health_checked = False

    if 'config_validated' not in st.session_state:
        st.session_state.config_validated = False

    if 'archive_checked' not in st.session_state:
        st.session_state.archive_checked = False


def check_system_health():
    """
    Check system health status.
    Implements REQ-020 and FAIL-001.
    """
    api_client: TxtAIClient = st.session_state.api_client

    # Check API health
    health = api_client.check_health()

    return health


def validate_configuration():
    """
    Validate txtai configuration.
    Implements REQ-018: CRITICAL graph.approximate check.
    """
    validator: ConfigValidator = st.session_state.config_validator
    result = validator.validate()

    return result


def check_archive_health():
    """
    Check document archive health status.
    Implements SPEC-036 MONITOR-001: Archive functionality verification.

    Returns:
        dict: Archive health status with keys:
            - status: 'active', 'warning', or 'not_available'
            - message: Human-readable status message
            - size_mb: Archive size in megabytes (or None)
            - file_count: Number of archive files (or None)
            - disk_usage_percent: Disk usage percentage (or None)
            - warnings: List of warning messages
    """
    archive_dir = Path("/archive")
    result = {
        'status': 'not_available',
        'message': 'Archive not available',
        'size_mb': None,
        'file_count': None,
        'disk_usage_percent': None,
        'warnings': []
    }

    try:
        # Check if archive directory exists and is writable
        if not archive_dir.exists():
            result['warnings'].append("Archive directory not mounted")
            result['message'] = "Archive directory not found (volume not mounted)"
            return result

        if not os.access(archive_dir, os.W_OK):
            result['warnings'].append("Archive directory not writable")
            result['message'] = "Archive directory exists but is not writable"
            result['status'] = 'warning'
            return result

        # Calculate archive size and count files
        archive_files = list(archive_dir.glob('*.json'))
        file_count = len(archive_files)

        if file_count == 0:
            total_size = 0
        else:
            total_size = sum(f.stat().st_size for f in archive_files)

        size_mb = total_size / (1024 * 1024)  # Convert to MB

        # Check disk usage
        disk_usage = shutil.disk_usage(archive_dir)
        disk_usage_percent = (disk_usage.used / disk_usage.total) * 100

        # Determine status
        result['status'] = 'active'
        result['size_mb'] = size_mb
        result['file_count'] = file_count
        result['disk_usage_percent'] = disk_usage_percent

        # Generate warnings based on percentage thresholds
        # Calculate archive as percentage of total disk
        archive_percent = (total_size / disk_usage.total) * 100

        # Primary warning: archive consuming >10% of disk space
        if archive_percent > 10:
            result['warnings'].append(f"Archive consuming {archive_percent:.1f}% of disk space")
            result['status'] = 'warning'

        # Secondary warning: overall disk usage >80%
        if disk_usage_percent > 80:
            result['warnings'].append(f"Disk usage is high ({disk_usage_percent:.1f}%)")
            result['status'] = 'warning'

        # Generate status message
        if result['status'] == 'active':
            result['message'] = f"Active: {size_mb:.1f} MB ({file_count} files)"
        else:
            result['message'] = f"Warning: {size_mb:.1f} MB ({file_count} files) - {', '.join(result['warnings'])}"

    except Exception as e:
        result['warnings'].append(f"Error checking archive: {str(e)}")
        result['message'] = f"Error checking archive status: {str(e)}"
        result['status'] = 'warning'

    return result


def display_health_status(health: dict):
    """Display API health status with visual indicators"""
    col1, col2 = st.columns([1, 3])

    with col1:
        if health['status'] == APIHealthStatus.HEALTHY:
            st.markdown('<p class="status-healthy">● HEALTHY</p>', unsafe_allow_html=True)
        elif health['status'] == APIHealthStatus.UNHEALTHY:
            st.markdown('<p class="status-unhealthy">● UNHEALTHY</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="status-unknown">● UNKNOWN</p>', unsafe_allow_html=True)

    with col2:
        st.write(health['message'])

    # Show error banner if unhealthy (FAIL-001 implementation)
    if health['status'] == APIHealthStatus.UNHEALTHY:
        st.markdown(f"""
        <div class="error-banner">
            <strong>⚠️ Connection Error</strong><br>
            {health['message']}<br>
            <br>
            <strong>Troubleshooting:</strong><br>
            1. Check if Docker containers are running: <code>docker ps</code><br>
            2. Verify txtai is accessible: <code>curl http://localhost:8300/index</code><br>
            3. Check docker-compose.yml configuration
        </div>
        """, unsafe_allow_html=True)

        if st.button("🔄 Retry Connection", key="retry_connection"):
            st.session_state.health_checked = False
            st.rerun()


def display_config_status(validation_result):
    """Display configuration validation status"""
    if validation_result.is_valid:
        st.markdown(f"""
        <div class="success-banner">
            {validation_result.get_message()}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="error-banner">
            <strong>⚠️ Configuration Error</strong><br>
            {validation_result.get_message()}
        </div>
        """, unsafe_allow_html=True)

    # Show graph configuration details
    validator: ConfigValidator = st.session_state.config_validator
    graph_status = validator.get_graph_status()

    with st.expander("📊 Graph Configuration Details", expanded=not validation_result.is_valid):
        st.write(graph_status['message'])

        if graph_status['status'] != 'correct':
            st.code(validator.suggest_graph_config(), language='yaml')
            st.info(
                "**Action Required:** Add this configuration to your config.yml file "
                "and restart the txtai API container."
            )


def display_archive_status(archive_health):
    """
    Display archive health status with visual indicators.
    Implements SPEC-036 MONITOR-001.
    """
    if archive_health['status'] == 'active':
        st.markdown(f"""
        <div class="success-banner">
            <strong>✅ Document Archive Active</strong><br>
            {archive_health['message']}<br>
            Disk Usage: {archive_health['disk_usage_percent']:.1f}%
        </div>
        """, unsafe_allow_html=True)
    elif archive_health['status'] == 'warning':
        st.markdown(f"""
        <div class="warning-banner">
            <strong>⚠️ Document Archive Warning</strong><br>
            {archive_health['message']}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="error-banner">
            <strong>❌ Document Archive Not Available</strong><br>
            {archive_health['message']}<br>
            <br>
            <strong>Troubleshooting:</strong><br>
            1. Check docker-compose.yml has volume mount: <code>./document_archive:/archive</code><br>
            2. Restart containers: <code>docker compose restart frontend</code>
        </div>
        """, unsafe_allow_html=True)

    # Show detailed archive info
    if archive_health['status'] in ['active', 'warning']:
        with st.expander("📦 Archive Details", expanded=(archive_health['status'] == 'warning')):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Archive Size", f"{archive_health['size_mb']:.1f} MB")

            with col2:
                st.metric("Document Count", archive_health['file_count'])

            with col3:
                disk_delta = "normal" if archive_health['disk_usage_percent'] < 80 else "high"
                st.metric("Disk Usage", f"{archive_health['disk_usage_percent']:.1f}%", delta=disk_delta)

            if archive_health['warnings']:
                st.warning("**Warnings:**\n" + "\n".join(f"- {w}" for w in archive_health['warnings']))

            st.info(
                "**Archive Purpose:** The document archive provides content recovery "
                "if the database is corrupted or reset. Each uploaded document is archived "
                "as a JSON file with full content and metadata."
            )


def main():
    """Main application"""
    initialize_session_state()

    # Header
    st.markdown('<p class="main-header">🧠 txtai Knowledge Manager</p>', unsafe_allow_html=True)
    st.markdown("Personal knowledge management with semantic search and relationship discovery")

    st.divider()

    # Sidebar - System Status
    with st.sidebar:
        st.header("System Status")

        # Perform health checks
        if not st.session_state.health_checked:
            with st.spinner("Checking system health..."):
                health = check_system_health()
                st.session_state.last_health_check = health
                st.session_state.health_checked = True
        else:
            health = st.session_state.last_health_check

        st.subheader("API Connection")
        if health['status'] == APIHealthStatus.HEALTHY:
            st.success("✅ Connected")
        else:
            st.error("❌ Disconnected")

        # Configuration validation
        if not st.session_state.config_validated:
            with st.spinner("Validating configuration..."):
                config_result = validate_configuration()
                st.session_state.config_result = config_result
                st.session_state.config_validated = True
        else:
            config_result = st.session_state.config_result

        st.subheader("Configuration")
        if config_result.is_valid:
            st.success("✅ Valid")
        else:
            st.error("❌ Invalid")

        # Archive health check (SPEC-036 MONITOR-001)
        if not st.session_state.archive_checked:
            archive_health = check_archive_health()
            st.session_state.archive_health = archive_health
            st.session_state.archive_checked = True
        else:
            archive_health = st.session_state.archive_health

        st.subheader("Document Archive")
        if archive_health['status'] == 'active':
            st.success(f"✅ Active ({archive_health['file_count']} files)")
        elif archive_health['status'] == 'warning':
            st.warning(f"⚠️ Warning ({archive_health['file_count']} files)")
        else:
            st.error("❌ Not Available")

        st.divider()

        # Manual refresh
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.session_state.health_checked = False
            st.session_state.config_validated = False
            st.session_state.archive_checked = False
            st.rerun()

        st.divider()

        # Navigation info
        st.subheader("Navigation")
        st.info(
            "Use the sidebar to navigate between pages:\n\n"
            "📤 **Upload** - Add documents and URLs\n\n"
            "🔍 **Search** - Find documents semantically\n\n"
            "🕸️ **Visualize** - Explore knowledge graph\n\n"
            "📚 **Browse** - View all documents"
        )

    # Main content area
    st.subheader("📊 System Health")
    display_health_status(health)

    st.subheader("⚙️ Configuration Status")
    display_config_status(config_result)

    st.subheader("📦 Document Archive Status")
    display_archive_status(st.session_state.archive_health)

    # Show welcome message if system is healthy
    if health['status'] == APIHealthStatus.HEALTHY and config_result.is_valid:
        st.divider()
        if st.session_state.archive_health['status'] == 'active':
            st.success("✅ System is ready! Use the sidebar to navigate to different features.")
        else:
            st.success("✅ System is ready! (Archive warning - see above)")
            st.info("💡 Document archive is not critical for system operation, but provides content recovery capability.")

        # Quick start guide
        st.subheader("🚀 Quick Start Guide")

        tab1, tab2, tab3 = st.tabs(["📤 Upload Documents", "🔍 Search", "🕸️ Visualize"])

        with tab1:
            st.markdown("""
            **Add documents to your knowledge base:**

            1. Navigate to **Upload** in the sidebar
            2. Choose between:
               - **File Upload**: PDF, TXT, DOCX, MD files
               - **URL Ingestion**: Scrape web pages with FireCrawl
            3. Select categories (configurable via `MANUAL_CATEGORIES` env var)
            4. Preview and edit content
            5. Save to index

            *Note: All uploads require category selection and support preview/edit.*
            """)

        with tab2:
            st.markdown("""
            **Search your knowledge base:**

            1. Navigate to **Search** in the sidebar
            2. Enter your search query (semantic search, not just keywords)
            3. Filter by category if desired
            4. View results with relevance scores
            5. Click through to see full documents

            *Tip: Semantic search finds conceptually related content, not just exact matches.*
            """)

        with tab3:
            st.markdown("""
            **Explore relationships:**

            1. Navigate to **Visualize** in the sidebar
            2. View your knowledge graph
            3. See connections between documents
            4. Color-coded by category
            5. Click nodes to see details

            *Note: Requires graph.approximate: false in config for proper relationship discovery.*
            """)

    # Footer
    st.divider()
    st.caption("txtai Personal Knowledge Management Interface | Built with Streamlit")


if __name__ == "__main__":
    main()

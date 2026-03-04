"""
Settings Page - Auto-Classification Configuration

Implements REQ-009, REQ-011, REQ-012 from SPEC-012:
- Label management for zero-shot classification
- Enable/disable auto-classification toggle
- Confidence threshold configuration
"""

import streamlit as st
from pathlib import Path
import sys
import os
import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import TxtAIClient

st.set_page_config(
    page_title="Settings - txtai Knowledge Manager",
    page_icon="⚙️",
    layout="wide"
)

# Initialize API client
@st.cache_resource
def get_api_client():
    """Get cached API client instance."""
    api_url = os.getenv("TXTAI_API_URL", "http://localhost:8300")
    return TxtAIClient(api_url)

# Load default labels from config.yml
def load_default_labels():
    """Load default labels from config.yml"""
    config_path = Path(__file__).parent.parent.parent / "config.yml"
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            if 'labels' in config and 'default_labels' in config['labels']:
                return config['labels']['default_labels']
    except Exception as e:
        st.error(f"Error loading config.yml: {e}")

    # Fallback to hardcoded defaults
    return [
        "professional",
        "personal",
        "financial",
        "legal",
        "reference",
        "project",
        "work (Memodo)",
        "activism"
    ]

# Initialize session state for settings
if 'classification_enabled' not in st.session_state:
    st.session_state.classification_enabled = True

if 'classification_labels' not in st.session_state:
    st.session_state.classification_labels = load_default_labels()

if 'auto_apply_threshold' not in st.session_state:
    st.session_state.auto_apply_threshold = 85

if 'suggestion_threshold' not in st.session_state:
    st.session_state.suggestion_threshold = 60

if 'new_label' not in st.session_state:
    st.session_state.new_label = ""

# Page header
st.title("⚙️ Settings")
st.markdown("Configure auto-classification behavior for uploaded documents.")

st.divider()

# Section 1: Enable/Disable Auto-Classification (REQ-011)
st.header("🔧 Auto-Classification")

col1, col2 = st.columns([1, 3])
with col1:
    classification_enabled = st.toggle(
        "Enable auto-classification",
        value=st.session_state.classification_enabled,
        help="When enabled, documents will be automatically classified with AI-generated labels during upload."
    )
    if classification_enabled != st.session_state.classification_enabled:
        st.session_state.classification_enabled = classification_enabled
        st.success("✓ Auto-classification " + ("enabled" if classification_enabled else "disabled"))

with col2:
    if st.session_state.classification_enabled:
        st.info("✨ Documents will be automatically classified with AI-generated labels during upload.")
    else:
        st.warning("⚠️ Auto-classification is disabled. No AI labels will be generated for new uploads.")

st.divider()

# Section 2: Confidence Thresholds (REQ-012)
st.header("🎯 Confidence Thresholds")

st.markdown("""
Configure how confident the AI must be before applying or suggesting labels:
- **Auto-apply threshold**: Labels with confidence ≥ this value will be automatically applied
- **Suggestion threshold**: Labels with confidence ≥ this value will be shown as suggestions (you decide)
- Labels below the suggestion threshold are hidden
""")

col1, col2 = st.columns(2)

with col1:
    auto_apply_threshold = st.slider(
        "Auto-apply threshold (%)",
        min_value=50,
        max_value=100,
        value=st.session_state.auto_apply_threshold,
        step=5,
        help="Labels with confidence at or above this value will be automatically applied. Default: 85%",
        disabled=not st.session_state.classification_enabled
    )
    if auto_apply_threshold != st.session_state.auto_apply_threshold:
        st.session_state.auto_apply_threshold = auto_apply_threshold
        st.success(f"✓ Auto-apply threshold set to {auto_apply_threshold}%")

with col2:
    suggestion_threshold = st.slider(
        "Suggestion threshold (%)",
        min_value=40,
        max_value=st.session_state.auto_apply_threshold,
        value=min(st.session_state.suggestion_threshold, st.session_state.auto_apply_threshold),
        step=5,
        help="Labels with confidence between this value and auto-apply threshold will be shown as suggestions. Default: 60%",
        disabled=not st.session_state.classification_enabled
    )
    if suggestion_threshold != st.session_state.suggestion_threshold:
        st.session_state.suggestion_threshold = suggestion_threshold
        st.success(f"✓ Suggestion threshold set to {suggestion_threshold}%")

# Visual preview of thresholds
st.markdown("**Threshold Preview:**")
threshold_col1, threshold_col2, threshold_col3 = st.columns(3)
with threshold_col1:
    st.metric("Auto-applied (✓)", f"≥ {st.session_state.auto_apply_threshold}%", delta="High confidence", delta_color="normal")
with threshold_col2:
    st.metric("Suggested (?)", f"{st.session_state.suggestion_threshold}%-{st.session_state.auto_apply_threshold-1}%", delta="Medium confidence", delta_color="off")
with threshold_col3:
    st.metric("Hidden", f"< {st.session_state.suggestion_threshold}%", delta="Low confidence", delta_color="inverse")

st.divider()

# Section 3: Label Management (REQ-009)
st.header("🏷️ Classification Labels")

st.markdown("""
Manage the list of labels used for zero-shot classification. These labels are used by the AI model
to categorize your documents. Choose labels that represent the types of documents you typically work with.
""")

# Display current labels
st.subheader("Current Labels")
st.markdown(f"**{len(st.session_state.classification_labels)}** labels configured")

# Labels display in a grid
num_cols = 4
rows = [st.session_state.classification_labels[i:i+num_cols]
        for i in range(0, len(st.session_state.classification_labels), num_cols)]

for row in rows:
    cols = st.columns(num_cols)
    for idx, label in enumerate(row):
        with cols[idx]:
            col_inner1, col_inner2 = st.columns([3, 1])
            with col_inner1:
                st.markdown(f"🏷️ **{label}**")
            with col_inner2:
                if st.button("🗑️", key=f"delete_{label}", help=f"Delete '{label}'", disabled=not st.session_state.classification_enabled):
                    st.session_state.classification_labels.remove(label)
                    st.success(f"✓ Removed label: {label}")
                    st.rerun()

st.divider()

# Add new label
st.subheader("Add New Label")

col1, col2 = st.columns([3, 1])
with col1:
    new_label = st.text_input(
        "Label name",
        value=st.session_state.new_label,
        placeholder="e.g., urgent, archive, confidential",
        help="Enter a descriptive label name (2-30 characters)",
        disabled=not st.session_state.classification_enabled
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)  # Align button with input
    if st.button("➕ Add Label", disabled=not st.session_state.classification_enabled or not new_label or len(new_label) < 2):
        # Validate label
        if len(new_label) < 2:
            st.error("❌ Label must be at least 2 characters long")
        elif len(new_label) > 30:
            st.error("❌ Label must be at most 30 characters long")
        elif new_label in st.session_state.classification_labels:
            st.warning(f"⚠️ Label '{new_label}' already exists")
        else:
            st.session_state.classification_labels.append(new_label)
            st.session_state.new_label = ""
            st.success(f"✓ Added label: {new_label}")
            st.rerun()

st.divider()

# Reset to defaults
st.subheader("Reset Configuration")
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    if st.button("🔄 Reset Labels to Default", type="secondary"):
        st.session_state.classification_labels = load_default_labels()
        st.success("✓ Labels reset to default configuration")
        st.rerun()

with col2:
    if st.button("🔄 Reset Thresholds", type="secondary"):
        st.session_state.auto_apply_threshold = 85
        st.session_state.suggestion_threshold = 60
        st.success("✓ Thresholds reset to defaults (85% / 60%)")
        st.rerun()

st.divider()

# Section 4: Information and Help
with st.expander("ℹ️ About Auto-Classification"):
    st.markdown("""
    **How it works:**

    Auto-classification uses zero-shot text classification powered by the
    **facebook/bart-large-mnli** model. This means the AI can classify documents
    into any category you define, without requiring training data.

    **During upload:**
    1. Document text is extracted
    2. AI analyzes content against your configured labels
    3. Confidence scores are calculated for each label
    4. Labels meeting your thresholds are applied or suggested

    **Visual indicators:**
    - ✨ Sparkle icon indicates AI-generated labels
    - 🟢 Green (≥85%) = High confidence, auto-applied
    - 🟡 Yellow (≥70%) = Medium-high confidence
    - 🟠 Orange (≥60%) = Medium confidence, suggested
    - ✓ Auto-applied labels
    - ? Suggested labels (your decision)

    **Best practices:**
    - Use 5-15 labels for optimal results
    - Choose specific, descriptive label names
    - Labels should represent distinct document types
    - Avoid overly broad labels (e.g., "document", "file")
    - Test with sample documents to tune thresholds
    """)

with st.expander("🔍 Technical Details"):
    st.markdown(f"""
    **Model Configuration:**
    - Model: facebook/bart-large-mnli (405M parameters)
    - Processing: Local (all data stays on your machine)
    - Current labels: {len(st.session_state.classification_labels)}
    - Auto-apply threshold: {st.session_state.auto_apply_threshold}%
    - Suggestion threshold: {st.session_state.suggestion_threshold}%
    - Status: {'Enabled ✓' if st.session_state.classification_enabled else 'Disabled ✗'}

    **API Endpoint:**
    - Workflow: `/workflow` with `name: "labels"`
    - Timeout: 30 seconds
    - Retry: Once on failure (5s delay)
    - Error handling: Graceful fallback (upload succeeds even if classification fails)
    """)

# Footer
st.markdown("---")
st.caption("💡 Changes take effect immediately for new uploads. Existing documents are not affected.")

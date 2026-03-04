"""
Ask Page - RAG Query Interface

Get AI-generated answers from your documents using RAG (Retrieval-Augmented Generation).
Implements SPEC-014: RAG UI Page for Streamlit Frontend.
"""

import streamlit as st
from utils import TxtAIClient, APIHealthStatus

# Page config
st.set_page_config(
    page_title="Ask - txtai Knowledge Manager",
    page_icon="💬",
    layout="wide"
)

# Cache API client
@st.cache_resource
def get_api_client():
    """Initialize cached API client"""
    return TxtAIClient()

# Initialize session state for RAG (SPEC-014 REQ-004)
if 'rag_state' not in st.session_state:
    st.session_state.rag_state = 'idle'  # State machine: idle | generating | complete | error
if 'rag_answer' not in st.session_state:
    st.session_state.rag_answer = None
if 'rag_sources' not in st.session_state:
    st.session_state.rag_sources = []
if 'rag_response_time' not in st.session_state:
    st.session_state.rag_response_time = 0
if 'rag_num_documents' not in st.session_state:
    st.session_state.rag_num_documents = 0
if 'rag_error' not in st.session_state:
    st.session_state.rag_error = None
if 'last_question' not in st.session_state:
    st.session_state.last_question = ""

# Header
st.title("💬 Ask Questions")
st.markdown("Get AI-generated answers from your document collection using natural language questions")
st.divider()

# API Health Check (SPEC-014 REQ-006, implements barrier pattern from Search page)
api_client = get_api_client()
health = api_client.check_health()

if health['status'] != APIHealthStatus.HEALTHY:
    st.error(f"""
    ⚠️ **txtai API Unavailable**

    {health['message']}

    **Actions:**
    - Ensure Docker containers are running: `docker-compose up -d`
    - Check API health at: http://localhost:8300
    """)
    st.stop()

# API is healthy - show ready status
st.success("✅ RAG service is ready")

st.markdown("""
### How it Works

This page uses **RAG (Retrieval-Augmented Generation)** to answer your questions:
1. 🔍 Searches your indexed documents for relevant context
2. 🤖 Uses AI to generate an answer based on the retrieved documents
3. 📚 Shows source documents for verification

**Note:** Generating answers takes 5-10 seconds. Loading feedback will be shown during processing.
""")

st.divider()

# Question Input Section (SPEC-014 Phase 2: REQ-001)
st.subheader("Ask a Question")

# Text area for question input with 1000 char limit (SPEC-014 REQ-001, SEC-002)
question = st.text_area(
    "Enter your question",
    placeholder="e.g., 'What is txtai?' or 'How do I use semantic search?'",
    help="Ask natural language questions about your indexed documents. Max 1000 characters.",
    max_chars=1000,
    height=120,
    key="rag_question_input"
)

# Character counter with color coding (SPEC-014 REQ-001, EDGE-002)
char_count = len(question)
if char_count >= 1000:
    # Red warning at limit
    st.caption(":red[⚠️ Character limit reached: 1000/1000]")
elif char_count >= 900:
    # Yellow warning approaching limit
    st.caption(f":orange[Character count: {char_count}/1000 - Approaching limit]")
elif char_count > 0:
    # Normal gray counter
    st.caption(f"Character count: {char_count}/1000")

# Generate Answer button with disabled state (SPEC-014 REQ-001, REQ-004, EDGE-008)
# Button disabled when: empty question OR currently generating
button_disabled = (st.session_state.rag_state == 'generating') or (not question.strip())

# Button callback to set state to generating (SPEC-014 REQ-004 state machine)
def on_generate_click():
    """Button click handler to initiate RAG query"""
    st.session_state.rag_state = 'generating'
    st.session_state.last_question = question
    st.rerun()

col1, col2 = st.columns([1, 4])
with col1:
    if st.button(
        "🤖 Generate Answer" if st.session_state.rag_state != 'generating' else "⏳ Generating...",
        disabled=button_disabled,
        on_click=on_generate_click,
        type="primary",
        key="generate_button"
    ):
        pass  # Click handled by callback

with col2:
    if st.session_state.rag_state == 'generating':
        st.info("⏳ Generating answer... This may take 5-10 seconds")
    elif not question.strip():
        st.caption("💡 Enter a question to generate an answer")

st.divider()

# RAG Query Execution (SPEC-014 Phase 3: REQ-002, REQ-004)
# State machine: idle → generating → complete/error → idle
if st.session_state.rag_state == 'generating':
    # Show loading spinner with contextual message (SPEC-014 UX-001)
    with st.spinner("🔍 Searching documents and generating AI answer..."):
        # Call RAG API (SPEC-014 REQ-002)
        result = api_client.rag_query(
            question=st.session_state.last_question,
            context_limit=5,  # Use default 5 documents (SPEC-014 decision)
            timeout=30
        )

        # Update session state based on result
        if result.get('success'):
            # Transition to 'complete' state
            st.session_state.rag_state = 'complete'
            st.session_state.rag_answer = result.get('answer', '')
            st.session_state.rag_sources = result.get('sources', [])
            st.session_state.rag_response_time = result.get('response_time', 0)
            st.session_state.rag_num_documents = result.get('num_documents', 0)
            st.session_state.rag_error = None
        else:
            # Transition to 'error' state
            st.session_state.rag_state = 'error'
            st.session_state.rag_error = result.get('error', 'unknown_error')
            st.session_state.rag_answer = None
            st.session_state.rag_sources = []

        # Rerun to display results
        st.rerun()

# Error Handling (SPEC-014 Phase 5: REQ-005, All EDGE and FAIL scenarios)
if st.session_state.rag_state == 'error' and st.session_state.rag_error:
    error_code = st.session_state.rag_error

    # Error message mapping with user-friendly messages and recovery actions
    # (SPEC-014 EDGE-001, EDGE-003, EDGE-004, EDGE-005, EDGE-006, FAIL-001, FAIL-002, FAIL-004)

    if error_code == 'empty_question':
        # EDGE: Empty question (shouldn't happen due to button disable, but handle gracefully)
        st.warning("⚠️ Please enter a question before generating an answer.")

    elif error_code == 'missing_api_key':
        # EDGE-004: API Key Missing - Configuration instructions
        st.error("""
        🔑 **RAG Feature Requires API Key**

        The RAG feature requires a Together AI API key to function.

        **Setup Instructions:**
        1. Get a free API key from [Together AI](https://api.together.xyz/)
        2. Set the `TOGETHERAI_API_KEY` environment variable:
           ```
           export TOGETHERAI_API_KEY="your-api-key-here"
           ```
        3. Or add it to your `.env` file
        4. Restart the application

        **Alternative:** Use the Search page to find relevant documents without AI generation.
        """)

    elif error_code == 'timeout':
        # EDGE-005, FAIL-001: Network Timeout - Retry suggestion
        st.error("""
        ⏱️ **Request Timed Out**

        The AI service took too long to respond (>30 seconds).

        **Possible causes:**
        - High load on Together AI service
        - Network connectivity issues
        - Complex question requiring long processing

        **What to try:**
        - Wait a moment and try again
        - Try a simpler or more specific question
        - Check your internet connection
        """)

        # Retry button (FAIL-001: Preserve state, allow retry)
        if st.button("🔄 Retry Question", key="retry_timeout"):
            st.session_state.rag_state = 'generating'
            st.rerun()

    elif error_code == 'low_quality_response':
        # EDGE-006, FAIL-002: Low Quality Response - Rephrase suggestion
        st.warning("""
        ⚠️ **Unable to Generate Quality Answer**

        The AI couldn't produce a satisfactory answer for your question.

        **Suggestions:**
        - Rephrase your question to be more specific
        - Try asking about a different aspect of the topic
        - Use the Search page to find relevant documents first
        - Ensure documents related to your question are indexed

        **Example better questions:**
        - Instead of "What is this?" → "What is txtai and how does it work?"
        - Instead of "Tell me more" → "What are the main features of semantic search?"
        """)

        # Link to Search page (EDGE-003 pattern)
        st.info("💡 Try using the [Search page](/Search) to explore available topics")

    elif 'api_error' in error_code:
        # FAIL-001, FAIL-004: API errors including rate limiting
        if '429' in error_code or 'rate' in error_code.lower():
            # FAIL-004: Rate Limiting
            st.error("""
            🚦 **Service Rate Limit Reached**

            The Together AI service has temporarily rate-limited requests.

            **What to do:**
            - Wait 1-2 minutes before trying again
            - Reduce query frequency
            - Contact administrator if this persists

            **Note:** No automatic retries are performed to avoid amplifying rate limits.
            """)
        else:
            # General API error
            st.error(f"""
            ❌ **AI Service Error**

            The AI service encountered an error: `{error_code}`

            **Actions:**
            - Try again in a moment
            - Check if the Together AI service is available
            - Use the Search page as an alternative
            """)

        # Retry button for general API errors
        if '429' not in error_code:  # Don't show retry for rate limits
            if st.button("🔄 Try Again", key="retry_api_error"):
                st.session_state.rag_state = 'generating'
                st.rerun()

    else:
        # Unknown error - generic handling
        st.error(f"""
        ❌ **Unexpected Error**

        An unexpected error occurred: `{error_code}`

        **Actions:**
        - Try asking a different question
        - Check the application logs for details
        - Use the Search page as an alternative
        """)

    # Always show "Ask Another Question" button for errors
    st.divider()
    if st.button("🔄 Ask Another Question", key="ask_another_after_error"):
        st.session_state.rag_state = 'idle'
        st.session_state.rag_error = None
        st.session_state.rag_answer = None
        st.session_state.rag_sources = []
        st.rerun()

# Results Display (SPEC-014 Phase 4: REQ-002, REQ-003)
if st.session_state.rag_state == 'complete' and st.session_state.rag_answer:
    # Check for special case: No information available (EDGE-001, EDGE-003)
    if "don't have enough information" in st.session_state.rag_answer.lower():
        # EDGE-001: Empty Document Index OR EDGE-003: No Matching Documents
        st.warning("""
        ℹ️ **No Relevant Information Found**

        The system couldn't find documents related to your question.

        **Possible reasons:**
        - No documents have been indexed yet
        - Your question topic isn't covered in indexed documents
        - Try rephrasing your question

        **Next steps:**
        """)

        col1, col2 = st.columns(2)
        with col1:
            st.info("""
            📤 **Upload Documents**

            Go to the Upload page to index documents
            """)
        with col2:
            st.info("""
            🔍 **Try Search**

            Use Search to explore what topics are available
            """)

        # Reset button
        if st.button("🔄 Try Different Question", key="try_different"):
            st.session_state.rag_state = 'idle'
            st.session_state.rag_answer = None
            st.session_state.rag_sources = []
            st.rerun()

    else:
        # Normal answer display
        st.subheader("Answer")

        # Quality indicator based on source count (SPEC-014 REQ-003, FAIL-003)
        num_sources = len(st.session_state.rag_sources)
        if num_sources >= 3:
            quality_emoji = "🟢"
            quality_text = "High confidence"
            quality_type = "success"
        elif num_sources >= 1:
            quality_emoji = "🟡"
            quality_text = "Medium confidence"
            quality_type = "warning"
        else:
            quality_emoji = "🔴"
            quality_text = "Low confidence"
            quality_type = "error"

        # Display answer card with quality indicator
        with st.container():
            # Header with quality indicator and response time (SPEC-014 REQ-002, REQ-003)
            col_quality, col_time = st.columns([3, 1])

            with col_quality:
                if quality_type == "success":
                    st.success(f"{quality_emoji} **{quality_text}** - Based on {num_sources} source document(s)")
                elif quality_type == "warning":
                    st.warning(f"{quality_emoji} **{quality_text}** - Based on {num_sources} source document(s)")
                else:
                    st.error(f"{quality_emoji} **{quality_text}** - Limited sources ({num_sources})")

            with col_time:
                # Response time display (SPEC-014 REQ-002)
                st.metric("Response Time", f"{st.session_state.rag_response_time:.2f}s")
                # Debug: Show number of documents retrieved
                st.caption(f"🔍 Documents retrieved: {st.session_state.rag_num_documents}")

            # Answer text (SPEC-014 REQ-002)
            st.markdown("### Answer")
            st.markdown(st.session_state.rag_answer)

            # Source attribution (SPEC-014 REQ-003)
            if st.session_state.rag_sources:
                st.markdown("---")
                st.markdown("### 📚 Sources")
                st.caption(f"Answer generated from {len(st.session_state.rag_sources)} document(s):")

                # Display sources with titles and links
                for idx, source in enumerate(st.session_state.rag_sources, 1):
                    # Handle both old format (string IDs) and new format (objects with id and title)
                    if isinstance(source, dict):
                        doc_id = source.get('id', 'unknown')
                        title = source.get('title', f'Document {doc_id}')
                    else:
                        # Fallback for old format (just ID strings)
                        doc_id = source
                        title = f'Document {doc_id}'

                    # Create a clickable link to View Source page with document ID
                    # Users can click to view the full source document
                    source_url = f"/View_Source?id={doc_id}"
                    st.markdown(f"{idx}. **{title}** ([View Source]({source_url})) - `{doc_id}`")

                st.caption("💡 Verify the answer by clicking the links to view source documents")
            else:
                st.info("ℹ️ No specific sources used - answer may be less reliable")

            # Ask another question button (resets state to idle)
            if st.button("🔄 Ask Another Question", key="ask_another"):
                st.session_state.rag_state = 'idle'
                st.session_state.rag_answer = None
                st.session_state.rag_sources = []
                st.session_state.rag_error = None
                st.rerun()

# Sidebar Content (SPEC-014 Phase 6: REQ-007, REQ-008)
with st.sidebar:
    st.header("💡 Help & Examples")

    # RAG vs Search explanation (SPEC-014 REQ-008)
    with st.expander("🤔 RAG vs Search - When to Use Each", expanded=False):
        st.markdown("""
        **💬 Ask (RAG)** - Use when you want:
        - Direct AI-generated answers
        - Concise responses to specific questions
        - Information synthesized from multiple documents
        - Quick answers without reading full documents

        **🔍 Search** - Use when you want:
        - Find specific documents by topic
        - Browse available documents
        - Review full document contents
        - Filter by categories or metadata

        **Tip:** If RAG can't answer your question, use Search to explore what documents are available!
        """)

    st.divider()

    # Example Questions (SPEC-014 REQ-007)
    st.subheader("📝 Example Questions")
    st.caption("Click to try these questions:")

    example_questions = [
        "What is txtai?",
        "How does semantic search work?",
        "What are the main features of txtai?",
        "How do I index documents?",
        "What file formats are supported?",
        "How can I improve search accuracy?",
        "What is the difference between RAG and semantic search?"
    ]

    for i, example in enumerate(example_questions):
        if st.button(f"💬 {example}", key=f"example_{i}", use_container_width=True):
            # Fill the question input with the example
            st.session_state.rag_question_input = example
            st.session_state.rag_state = 'idle'  # Reset state
            st.rerun()

    st.divider()

    # Tips for better answers (SPEC-014 REQ-008)
    with st.expander("✨ Tips for Better Answers", expanded=False):
        st.markdown("""
        **Good Questions:**
        - Be specific: "How do I configure embeddings?" ✅
        - Ask one thing: "What is semantic search?" ✅
        - Use clear language: "What formats can I upload?" ✅

        **Avoid:**
        - Too vague: "Tell me about everything" ❌
        - Multiple questions: "How do I upload and search and delete?" ❌
        - Questions outside your documents' scope ❌

        **Response Time:**
        - Generating answers takes 5-10 seconds
        - This is normal for AI processing
        - Loading feedback will be shown

        **Answer Quality:**
        - 🟢 High confidence: 3+ source documents
        - 🟡 Medium confidence: 1-2 source documents
        - 🔴 Low confidence: 0 source documents
        """)

    st.divider()

    # Link to other pages
    st.subheader("🔗 Quick Links")
    st.markdown("""
    - 📤 [Upload Documents](/Upload)
    - 🔍 [Search Documents](/Search)
    - 📊 [Browse Collection](/Browse)
    """)

    st.divider()

    # Technical info
    with st.expander("🔧 Technical Details", expanded=False):
        st.markdown("""
        **How RAG Works:**
        1. Your question is used to search indexed documents
        2. Top 5 most relevant documents are retrieved
        3. AI generates an answer using only those documents
        4. Sources are shown for verification

        **AI Model:** Qwen/Qwen2.5-72B-Instruct-Turbo (via Together AI)

        **Privacy:** Your questions and documents are processed through Together AI's API. Ensure you're comfortable with this before asking sensitive questions.
        """)


"""
Test suite for scripts/graphiti-cleanup.py
Tests REQ-015 cleanup script functionality
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Import graphiti-cleanup.py using importlib (can't use regular import due to hyphen)
spec = importlib.util.spec_from_file_location(
    "graphiti_cleanup",
    SCRIPTS_DIR / "graphiti-cleanup.py"
)
graphiti_cleanup = importlib.util.module_from_spec(spec)
sys.modules['graphiti_cleanup'] = graphiti_cleanup
spec.loader.exec_module(graphiti_cleanup)


class TestEnvironmentChecks:
    """Test Docker environment and environment variable validation"""

    def test_check_docker_environment_inside_docker(self):
        """Test that check passes when /.dockerenv exists"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            # Should not raise
            try:
                graphiti_cleanup.check_docker_environment()
            except SystemExit:
                pytest.fail("Should not exit when /.dockerenv exists")

    def test_check_docker_environment_outside_docker(self):
        """Test that check fails when /.dockerenv doesn't exist"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False

            # Should exit with code 1
            with pytest.raises(SystemExit) as exc_info:
                graphiti_cleanup.check_docker_environment()
            assert exc_info.value.code == 1

    def test_validate_environment_with_password(self):
        """Test validation succeeds with NEO4J_PASSWORD"""
        with patch.dict(os.environ, {
            'NEO4J_URI': 'bolt://neo4j:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'test-password',
        }):
            uri, user, password = graphiti_cleanup.validate_environment()
            assert uri == 'bolt://neo4j:7687'
            assert user == 'neo4j'
            assert password == 'test-password'

    def test_validate_environment_missing_password(self):
        """Test validation fails when NEO4J_PASSWORD is missing"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                graphiti_cleanup.validate_environment()
            assert exc_info.value.code == 1

    def test_validate_environment_uses_defaults(self):
        """Test that default values are used for URI and USER"""
        with patch.dict(os.environ, {
            'NEO4J_PASSWORD': 'test-password',
        }, clear=True):
            uri, user, password = graphiti_cleanup.validate_environment()
            assert uri == 'bolt://neo4j:7687'  # Default
            assert user == 'neo4j'  # Default
            assert password == 'test-password'


class TestEntityCounting:
    """Test entity counting functions"""

    def test_count_entities_for_document_with_entities(self):
        """Test counting entities for a specific document"""
        # Mock Neo4j driver and session
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {'cnt': 42}

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result
        mock_result.single.return_value = mock_record
        mock_driver.session.return_value = mock_session

        count = graphiti_cleanup.count_entities_for_document(mock_driver, 'test-doc-id')

        assert count == 42
        # Verify correct query was executed
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        assert 'group_id' in call_args[0][0]  # Query contains group_id
        assert call_args[1]['doc_id'] == 'test-doc-id'  # Parameter is correct

    def test_count_entities_for_document_no_entities(self):
        """Test counting when document has no entities"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {'cnt': 0}

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result
        mock_result.single.return_value = mock_record
        mock_driver.session.return_value = mock_session

        count = graphiti_cleanup.count_entities_for_document(mock_driver, 'nonexistent-doc')

        assert count == 0

    def test_count_all_entities_with_entities(self):
        """Test counting all entities in the graph"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {'cnt': 1000}

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result
        mock_result.single.return_value = mock_record
        mock_driver.session.return_value = mock_session

        count = graphiti_cleanup.count_all_entities(mock_driver)

        assert count == 1000

    def test_count_all_entities_empty_graph(self):
        """Test counting when graph is empty"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {'cnt': 0}

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result
        mock_result.single.return_value = mock_record
        mock_driver.session.return_value = mock_session

        count = graphiti_cleanup.count_all_entities(mock_driver)

        assert count == 0


class TestEntityDeletion:
    """Test entity deletion functions"""

    def test_delete_entities_for_document_success(self):
        """Test successful deletion of document entities"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_record = {'cnt': 10}

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result
        mock_result.single.return_value = mock_record
        mock_driver.session.return_value = mock_session

        # Mock count_entities_for_document to return 10
        with patch('graphiti_cleanup.count_entities_for_document', return_value=10):
            deleted = graphiti_cleanup.delete_entities_for_document(mock_driver, 'test-doc-id')

        assert deleted == 10
        # Verify DETACH DELETE was called
        assert mock_session.run.call_count >= 1
        # Check that a DELETE query was executed
        delete_call = None
        for call_item in mock_session.run.call_args_list:
            if 'DELETE' in call_item[0][0]:
                delete_call = call_item
                break
        assert delete_call is not None, "DELETE query should have been executed"

    def test_delete_entities_for_document_no_entities(self):
        """Test deletion when document has no entities"""
        mock_driver = MagicMock()

        # Mock count_entities_for_document to return 0
        with patch('graphiti_cleanup.count_entities_for_document', return_value=0):
            deleted = graphiti_cleanup.delete_entities_for_document(mock_driver, 'nonexistent-doc')

        assert deleted == 0

    def test_delete_all_entities_success(self):
        """Test successful deletion of all entities"""
        mock_driver = MagicMock()
        mock_session = MagicMock()

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_driver.session.return_value = mock_session

        # Mock count_all_entities to return 500
        with patch('graphiti_cleanup.count_all_entities', return_value=500):
            deleted = graphiti_cleanup.delete_all_entities(mock_driver)

        assert deleted == 500
        # Verify DELETE was called
        assert mock_session.run.called

    def test_delete_all_entities_empty_graph(self):
        """Test deletion when graph is already empty"""
        mock_driver = MagicMock()

        # Mock count_all_entities to return 0
        with patch('graphiti_cleanup.count_all_entities', return_value=0):
            deleted = graphiti_cleanup.delete_all_entities(mock_driver)

        assert deleted == 0


class TestListDocuments:
    """Test document listing functionality"""

    def test_list_documents_with_entities(self):
        """Test listing documents with entities"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = [
            {'doc_id': 'doc-1', 'cnt': 100},
            {'doc_id': 'doc-2', 'cnt': 50},
            {'doc_id': 'doc-3', 'cnt': 25},
        ]

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value = mock_session

        documents = graphiti_cleanup.list_documents_with_entities(mock_driver)

        assert len(documents) == 3
        assert documents[0] == ('doc-1', 100)
        assert documents[1] == ('doc-2', 50)
        assert documents[2] == ('doc-3', 25)

    def test_list_documents_empty_graph(self):
        """Test listing when no documents have entities"""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = []

        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value = mock_session

        documents = graphiti_cleanup.list_documents_with_entities(mock_driver)

        assert len(documents) == 0


class TestMainFunctionFlow:
    """Test main function argument handling and flow"""

    @patch('graphiti_cleanup.GraphDatabase')
    @patch('graphiti_cleanup.check_docker_environment')
    @patch('graphiti_cleanup.validate_environment')
    @patch('graphiti_cleanup.list_documents_with_entities')
    def test_list_mode_with_documents(self, mock_list, mock_validate, mock_check, mock_db):
        """Test --list mode with documents"""
        # Setup mocks
        mock_validate.return_value = ('bolt://neo4j:7687', 'neo4j', 'password')
        mock_driver = MagicMock()
        mock_db.driver.return_value = mock_driver
        mock_driver.verify_connectivity.return_value = None
        mock_list.return_value = [('doc-1', 100), ('doc-2', 50)]

        # Mock sys.argv
        with patch('sys.argv', ['graphiti-cleanup.py', '--list']):
            result = graphiti_cleanup.main()

        assert result == 0
        mock_list.assert_called_once_with(mock_driver)

    @patch('graphiti_cleanup.GraphDatabase')
    @patch('graphiti_cleanup.check_docker_environment')
    @patch('graphiti_cleanup.validate_environment')
    @patch('graphiti_cleanup.count_entities_for_document')
    def test_document_id_mode_dry_run(self, mock_count, mock_validate, mock_check, mock_db):
        """Test --document-id mode without --confirm (dry-run)"""
        # Setup mocks
        mock_validate.return_value = ('bolt://neo4j:7687', 'neo4j', 'password')
        mock_driver = MagicMock()
        mock_db.driver.return_value = mock_driver
        mock_driver.verify_connectivity.return_value = None
        mock_count.return_value = 42

        # Mock sys.argv for --document-id without --confirm
        with patch('sys.argv', ['graphiti-cleanup.py', '--document-id', 'test-uuid']):
            result = graphiti_cleanup.main()

        assert result == 0
        mock_count.assert_called_once_with(mock_driver, 'test-uuid')

    @patch('graphiti_cleanup.GraphDatabase')
    @patch('graphiti_cleanup.check_docker_environment')
    @patch('graphiti_cleanup.validate_environment')
    @patch('graphiti_cleanup.count_entities_for_document')
    @patch('graphiti_cleanup.delete_entities_for_document')
    def test_document_id_mode_with_confirm(self, mock_delete, mock_count, mock_validate, mock_check, mock_db):
        """Test --document-id mode with --confirm (actual deletion)"""
        # Setup mocks
        mock_validate.return_value = ('bolt://neo4j:7687', 'neo4j', 'password')
        mock_driver = MagicMock()
        mock_db.driver.return_value = mock_driver
        mock_driver.verify_connectivity.return_value = None
        mock_count.return_value = 42
        mock_delete.return_value = 42

        # Mock sys.argv for --document-id with --confirm
        with patch('sys.argv', ['graphiti-cleanup.py', '--document-id', 'test-uuid', '--confirm']):
            result = graphiti_cleanup.main()

        assert result == 0
        mock_delete.assert_called_once_with(mock_driver, 'test-uuid')

    @patch('graphiti_cleanup.GraphDatabase')
    @patch('graphiti_cleanup.check_docker_environment')
    @patch('graphiti_cleanup.validate_environment')
    @patch('graphiti_cleanup.count_entities_for_document')
    def test_document_id_mode_no_entities(self, mock_count, mock_validate, mock_check, mock_db):
        """Test --document-id mode when document has no entities"""
        # Setup mocks
        mock_validate.return_value = ('bolt://neo4j:7687', 'neo4j', 'password')
        mock_driver = MagicMock()
        mock_db.driver.return_value = mock_driver
        mock_driver.verify_connectivity.return_value = None
        mock_count.return_value = 0

        # Mock sys.argv
        with patch('sys.argv', ['graphiti-cleanup.py', '--document-id', 'test-uuid']):
            result = graphiti_cleanup.main()

        assert result == 0

    @patch('graphiti_cleanup.GraphDatabase')
    @patch('graphiti_cleanup.check_docker_environment')
    @patch('graphiti_cleanup.validate_environment')
    @patch('graphiti_cleanup.count_all_entities')
    def test_all_mode_dry_run(self, mock_count, mock_validate, mock_check, mock_db):
        """Test --all mode without --confirm (dry-run)"""
        # Setup mocks
        mock_validate.return_value = ('bolt://neo4j:7687', 'neo4j', 'password')
        mock_driver = MagicMock()
        mock_db.driver.return_value = mock_driver
        mock_driver.verify_connectivity.return_value = None
        mock_count.return_value = 1000

        # Mock sys.argv for --all without --confirm
        with patch('sys.argv', ['graphiti-cleanup.py', '--all']):
            result = graphiti_cleanup.main()

        assert result == 0
        mock_count.assert_called_once_with(mock_driver)

    @patch('graphiti_cleanup.GraphDatabase')
    @patch('graphiti_cleanup.check_docker_environment')
    @patch('graphiti_cleanup.validate_environment')
    @patch('graphiti_cleanup.count_all_entities')
    @patch('graphiti_cleanup.delete_all_entities')
    def test_all_mode_with_confirm(self, mock_delete, mock_count, mock_validate, mock_check, mock_db):
        """Test --all mode with --confirm (actual deletion)"""
        # Setup mocks
        mock_validate.return_value = ('bolt://neo4j:7687', 'neo4j', 'password')
        mock_driver = MagicMock()
        mock_db.driver.return_value = mock_driver
        mock_driver.verify_connectivity.return_value = None
        mock_count.return_value = 1000
        mock_delete.return_value = 1000

        # Mock sys.argv for --all with --confirm
        with patch('sys.argv', ['graphiti-cleanup.py', '--all', '--confirm']):
            result = graphiti_cleanup.main()

        assert result == 0
        mock_delete.assert_called_once_with(mock_driver)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

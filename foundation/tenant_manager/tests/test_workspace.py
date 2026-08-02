"""
Tests for WorkspaceManager - workspace lifecycle, templates, file storage.
"""

import os
import shutil
import tempfile
import unittest

from ..workspace import (
    WorkspaceManager,
    Workspace,
    WorkspaceTemplate,
    WorkspaceStatus,
    WorkspaceFile,
)


class TestWorkspaceManager(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = WorkspaceManager(base_storage_path=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- Lifecycle ---

    def test_create_workspace(self):
        ws = self.manager.create_workspace("tenant1", "My Workspace")
        self.assertTrue(ws.workspace_id.startswith("ws_"))
        self.assertEqual(ws.tenant_id, "tenant1")
        self.assertEqual(ws.name, "My Workspace")
        self.assertEqual(ws.status, WorkspaceStatus.ACTIVE)

    def test_create_workspace_empty_name(self):
        with self.assertRaises(ValueError):
            self.manager.create_workspace("t1", "")

    def test_create_workspace_with_config(self):
        ws = self.manager.create_workspace("t1", "ConfigWS", config={"theme": "dark"})
        self.assertEqual(ws.config["theme"], "dark")

    def test_get_workspace(self):
        created = self.manager.create_workspace("t1", "GetMe")
        retrieved = self.manager.get_workspace(created.workspace_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.workspace_id, created.workspace_id)

    def test_get_workspace_not_found(self):
        self.assertIsNone(self.manager.get_workspace("bad_id"))

    def test_archive_workspace(self):
        ws = self.manager.create_workspace("t1", "ArchiveMe")
        archived = self.manager.archive_workspace(ws.workspace_id)
        self.assertEqual(archived.status, WorkspaceStatus.ARCHIVED)
        self.assertIsNotNone(archived.archived_at)

    def test_archive_non_active_raises(self):
        ws = self.manager.create_workspace("t1", "BadArchive")
        self.manager.archive_workspace(ws.workspace_id)
        with self.assertRaises(ValueError):
            self.manager.archive_workspace(ws.workspace_id)

    def test_restore_workspace(self):
        ws = self.manager.create_workspace("t1", "RestoreMe")
        self.manager.archive_workspace(ws.workspace_id)
        restored = self.manager.restore_workspace(ws.workspace_id)
        self.assertEqual(restored.status, WorkspaceStatus.ACTIVE)
        self.assertIsNone(restored.archived_at)

    def test_restore_non_archived_raises(self):
        ws = self.manager.create_workspace("t1", "BadRestore")
        with self.assertRaises(ValueError):
            self.manager.restore_workspace(ws.workspace_id)

    def test_delete_workspace_soft(self):
        ws = self.manager.create_workspace("t1", "SoftDelete")
        self.assertTrue(self.manager.delete_workspace(ws.workspace_id, hard=False))
        retrieved = self.manager.get_workspace(ws.workspace_id)
        self.assertEqual(retrieved.status, WorkspaceStatus.DELETED)

    def test_delete_workspace_hard(self):
        ws = self.manager.create_workspace("t1", "HardDelete")
        self.assertTrue(self.manager.delete_workspace(ws.workspace_id, hard=True))
        self.assertIsNone(self.manager.get_workspace(ws.workspace_id))

    def test_delete_not_found(self):
        self.assertFalse(self.manager.delete_workspace("bad_id"))

    def test_purge_deleted(self):
        ws = self.manager.create_workspace("t1", "PurgeMe")
        self.manager.delete_workspace(ws.workspace_id, hard=False)
        purged = self.manager.purge_deleted(older_than_days=0)
        self.assertEqual(purged, 1)
        self.assertIsNone(self.manager.get_workspace(ws.workspace_id))

    # --- Templates ---

    def test_create_template(self):
        tmpl = self.manager.create_template(
            name="Data Science",
            description="For ML projects",
            base_config={"runtime": "python3.10"},
        )
        self.assertTrue(tmpl.template_id.startswith("tmpl_"))
        self.assertEqual(tmpl.name, "Data Science")
        self.assertEqual(tmpl.base_config["runtime"], "python3.10")

    def test_create_workspace_from_template(self):
        tmpl = self.manager.create_template(
            name="Python",
            base_config={"runtime": "python3.10", "memory": "2GB"},
            features={"jupyter", "git"},
        )
        ws = self.manager.create_workspace("t1", "FromTemplate", template_id=tmpl.template_id)
        self.assertEqual(ws.config["runtime"], "python3.10")
        self.assertEqual(ws.config["memory"], "2GB")
        self.assertIsNotNone(ws.template)

    def test_create_workspace_invalid_template(self):
        with self.assertRaises(ValueError):
            self.manager.create_workspace("t1", "BadTmpl", template_id="nonexistent")

    def test_get_template(self):
        tmpl = self.manager.create_template(name="TestTmpl")
        self.assertEqual(self.manager.get_template(tmpl.template_id), tmpl)

    def test_list_templates(self):
        self.manager.create_template(name="A")
        self.manager.create_template(name="B")
        self.assertEqual(len(self.manager.list_templates()), 2)

    def test_delete_template(self):
        tmpl = self.manager.create_template(name="DelMe")
        self.assertTrue(self.manager.delete_template(tmpl.template_id))
        self.assertIsNone(self.manager.get_template(tmpl.template_id))

    def test_delete_template_not_found(self):
        self.assertFalse(self.manager.delete_template("bad_id"))

    # --- File Storage ---

    def test_store_file(self):
        ws = self.manager.create_workspace("t1", "FileWS")
        wf = self.manager.store_file(
            ws.workspace_id, "hello.txt", b"Hello World", path="/docs",
            mime_type="text/plain", metadata={"author": "test"},
        )
        self.assertIsNotNone(wf)
        self.assertEqual(wf.filename, "hello.txt")
        self.assertEqual(wf.path, "/docs/hello.txt")
        self.assertEqual(wf.size_bytes, 11)
        self.assertEqual(wf.mime_type, "text/plain")
        self.assertEqual(wf.metadata["author"], "test")

    def test_store_file_non_active_raises(self):
        ws = self.manager.create_workspace("t1", "InactiveWS")
        self.manager.archive_workspace(ws.workspace_id)
        with self.assertRaises(ValueError):
            self.manager.store_file(ws.workspace_id, "test.txt", b"data")

    def test_store_file_workspace_not_found(self):
        self.assertIsNone(self.manager.store_file("bad_ws", "test.txt", b"data"))

    def test_get_file(self):
        ws = self.manager.create_workspace("t1", "GetFileWS")
        wf = self.manager.store_file(ws.workspace_id, "data.bin", b"\x00\x01\x02")
        content, meta = self.manager.get_file(ws.workspace_id, wf.file_id)
        self.assertEqual(content, b"\x00\x01\x02")
        self.assertEqual(meta.filename, "data.bin")

    def test_get_file_not_found(self):
        ws = self.manager.create_workspace("t1", "NoFileWS")
        content, meta = self.manager.get_file(ws.workspace_id, "bad_file")
        self.assertIsNone(content)
        self.assertIsNone(meta)

    def test_delete_file(self):
        ws = self.manager.create_workspace("t1", "DelFileWS")
        wf = self.manager.store_file(ws.workspace_id, "temp.txt", b"temp")
        self.assertTrue(self.manager.delete_file(ws.workspace_id, wf.file_id))
        self.assertFalse(self.manager.delete_file(ws.workspace_id, wf.file_id))

    def test_list_files(self):
        ws = self.manager.create_workspace("t1", "ListWS")
        self.manager.store_file(ws.workspace_id, "a.txt", b"a", path="/")
        self.manager.store_file(ws.workspace_id, "b.txt", b"b", path="/sub")
        self.manager.store_file(ws.workspace_id, "c.txt", b"c", path="/sub/deep")
        self.assertEqual(len(self.manager.list_files(ws.workspace_id)), 3)
        self.assertEqual(len(self.manager.list_files(ws.workspace_id, path_prefix="/sub")), 2)

    def test_get_storage_usage(self):
        ws = self.manager.create_workspace("t1", "StorageWS")
        self.manager.store_file(ws.workspace_id, "f1.txt", b"12345")  # 5 bytes
        self.manager.store_file(ws.workspace_id, "f2.txt", b"1234567890")  # 10 bytes
        self.assertEqual(self.manager.get_storage_usage(ws.workspace_id), 15)

    def test_get_tenant_storage_usage(self):
        ws1 = self.manager.create_workspace("t1", "WS1")
        ws2 = self.manager.create_workspace("t1", "WS2")
        self.manager.store_file(ws1.workspace_id, "f1.txt", b"12345")
        self.manager.store_file(ws2.workspace_id, "f2.txt", b"12345")
        self.assertEqual(self.manager.get_tenant_storage_usage("t1"), 10)

    # --- Workspace listing ---

    def test_list_workspaces_by_tenant(self):
        self.manager.create_workspace("t1", "A")
        self.manager.create_workspace("t2", "B")
        self.manager.create_workspace("t1", "C")
        t1_ws = self.manager.list_workspaces(tenant_id="t1")
        self.assertEqual(len(t1_ws), 2)
        t2_ws = self.manager.list_workspaces(tenant_id="t2")
        self.assertEqual(len(t2_ws), 1)

    def test_list_workspaces_by_status(self):
        ws = self.manager.create_workspace("t1", "ArchWS")
        self.manager.archive_workspace(ws.workspace_id)
        active = self.manager.list_workspaces(status_filter=WorkspaceStatus.ACTIVE)
        archived = self.manager.list_workspaces(status_filter=WorkspaceStatus.ARCHIVED)
        self.assertEqual(len(archived), 1)

    def test_get_tenant_workspace_count(self):
        self.manager.create_workspace("t1", "A")
        self.manager.create_workspace("t1", "B")
        ws = self.manager.create_workspace("t1", "C")
        self.manager.delete_workspace(ws.workspace_id, hard=False)
        # Deleted should not count
        self.assertEqual(self.manager.get_tenant_workspace_count("t1"), 2)

    # --- Config ---

    def test_update_workspace_config(self):
        ws = self.manager.create_workspace("t1", "ConfigWS", config={"a": 1})
        updated = self.manager.update_workspace_config(ws.workspace_id, {"b": 2, "a": 99})
        self.assertEqual(updated.config["a"], 99)
        self.assertEqual(updated.config["b"], 2)

    def test_get_workspace_config(self):
        ws = self.manager.create_workspace("t1", "GetConfWS", config={"x": "y"})
        cfg = self.manager.get_workspace_config(ws.workspace_id)
        self.assertEqual(cfg, {"x": "y"})


if __name__ == "__main__":
    unittest.main()
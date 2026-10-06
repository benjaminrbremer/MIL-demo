import hashlib
import logging
import os
import time
import uuid
from pathlib import Path

import pytest

from app import db
from app import registry as registry_module
from app.db import DB_FILENAME, SlideStatus, init_db
from app.registry import UNREADABLE_MESSAGE, Registry
from tests.fakes import PHI_NAME, FakeSlide, FakeSlideBadMpp, FakeSlideNoMpp, phi_opener

APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def acq(tmp_path) -> Path:
    """An empty acquisition folder."""
    path = tmp_path / "acquisition"
    path.mkdir()
    return path


@pytest.fixture
def db_path(tmp_path) -> Path:
    """An initialized, empty database."""
    path = tmp_path / "data" / DB_FILENAME
    init_db(path)
    return path


@pytest.fixture
def registry(acq, db_path) -> Registry:
    """A registry that opens slides with FakeSlide."""
    return Registry(acq, db_path, opener=FakeSlide)


def only_slide(db_path):
    """Return the single slide row, failing if there isn't exactly one."""
    rows = db.list_slides(db_path)
    assert len(rows) == 1
    return rows[0]


def test_req_001_new_file_is_registered_without_user_action(acq, db_path, registry):
    """REQ-001: a slide file dropped in the folder becomes ready on its own."""
    (acq / "slide.tif").write_bytes(b"pixels")

    registry.scan_once(now=0)
    assert only_slide(db_path)["status"] == SlideStatus.ARRIVING

    registry.scan_once(now=5)
    row = only_slide(db_path)
    assert row["status"] == SlideStatus.READY
    assert (row["width"], row["height"], row["level_count"]) == (2000, 1000, 3)
    assert (row["mpp_x"], row["mpp_y"]) == (0.243, 0.244)
    assert row["registered_at"].endswith("Z")
    assert row["detected_at"].endswith("Z")


def test_req_002_file_not_registered_until_size_stable_5s(acq, db_path, registry):
    """REQ-002: registration waits for 5 s of unchanged size."""
    (acq / "slide.tif").write_bytes(b"pixels")

    registry.scan_once(now=0)
    registry.scan_once(now=4.9)
    assert only_slide(db_path)["status"] == SlideStatus.ARRIVING

    registry.scan_once(now=5.0)
    assert only_slide(db_path)["status"] == SlideStatus.READY


def test_req_002_growing_file_restarts_the_wait(acq, db_path, registry):
    """REQ-002: a size change restarts the 5 s stability window."""
    slide = acq / "slide.tif"
    slide.write_bytes(b"part one")
    registry.scan_once(now=0)

    with slide.open("ab") as f:
        f.write(b" part two")
    registry.scan_once(now=3)  # change seen here
    registry.scan_once(now=7.9)
    assert only_slide(db_path)["status"] == SlideStatus.ARRIVING

    registry.scan_once(now=8)
    assert only_slide(db_path)["status"] == SlideStatus.READY


def test_req_002_file_that_changes_during_hashing_returns_to_arriving(
    acq, db_path, registry, monkeypatch
):
    """REQ-002: a file that grows while being hashed waits again before registering."""
    slide = acq / "slide.tif"
    slide.write_bytes(b"part one")
    real_sha256 = registry_module.sha256_file
    calls = []

    def sha256_then_grow(path):
        """Hash the file, then (first call only) append to it like a resumed copy."""
        digest = real_sha256(path)
        if not calls:
            with path.open("ab") as f:
                f.write(b" more")
        calls.append(path)
        return digest

    monkeypatch.setattr(registry_module, "sha256_file", sha256_then_grow)

    registry.scan_once(now=0)
    registry.scan_once(now=5)
    assert only_slide(db_path)["status"] == SlideStatus.ARRIVING

    registry.scan_once(now=10)
    row = only_slide(db_path)
    assert row["status"] == SlideStatus.READY
    assert row["sha256"] == hashlib.sha256(slide.read_bytes()).hexdigest()


def test_req_003_slide_gets_uuid_and_sha256(acq, db_path, registry):
    """REQ-003: the slide ID is a random UUID and the SHA-256 matches the bytes."""
    content = os.urandom(3 * 1024 * 1024 + 7)  # spans several hash chunks
    (acq / "slide.tif").write_bytes(content)

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    row = only_slide(db_path)
    assert uuid.UUID(row["id"]).version == 4
    assert row["sha256"] == hashlib.sha256(content).hexdigest()


def test_req_003_identical_files_get_distinct_ids_same_hash(acq, db_path, registry):
    """REQ-003: IDs never derive from content; equal files share only the hash."""
    (acq / "a.tif").write_bytes(b"same")
    (acq / "b.tif").write_bytes(b"same")

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    rows = db.list_slides(db_path)
    assert len({row["id"] for row in rows}) == 2
    assert len({row["sha256"] for row in rows}) == 1


def test_req_004_associated_images_never_accessed(acq, db_path, registry):
    """REQ-004: registering a slide never touches its associated images."""
    FakeSlide.associated_images_read = False
    (acq / "slide.tif").write_bytes(b"pixels")

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    assert only_slide(db_path)["status"] == SlideStatus.READY
    assert FakeSlide.associated_images_read is False


def test_req_004_service_code_never_references_associated_images():
    """REQ-004: no module in app/ mentions OpenSlide's associated_images API."""
    for source in APP_DIR.rglob("*.py"):
        assert "associated_images" not in source.read_text(), source.name


def test_req_005_only_allowlisted_metadata_is_stored(acq, db_path, registry):
    """REQ-005: other slide properties (e.g. barcode) are not stored."""
    (acq / "slide.tif").write_bytes(b"pixels")

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    row = only_slide(db_path)
    assert "PATIENT-BARCODE" not in [str(value) for value in tuple(row)]


@pytest.mark.parametrize("opener", [FakeSlideNoMpp, FakeSlideBadMpp])
def test_missing_or_invalid_mpp_is_stored_as_null(acq, db_path, opener):
    """Absent or non-numeric microns per pixel become null, not an error."""
    registry = Registry(acq, db_path, opener=opener)
    (acq / "slide.tif").write_bytes(b"pixels")

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    row = only_slide(db_path)
    assert row["status"] == SlideStatus.READY
    assert (row["mpp_x"], row["mpp_y"]) == (None, None)


def test_unopenable_file_is_marked_unreadable_by_real_openslide(acq, db_path):
    """A text file renamed to .tif ends up unreadable with SLIDE_UNREADABLE."""
    registry = Registry(acq, db_path)  # real OpenSlide
    (acq / "fake.tif").write_text("not a slide")

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    row = only_slide(db_path)
    assert row["status"] == SlideStatus.UNREADABLE
    assert row["error_code"] == "SLIDE_UNREADABLE"
    assert row["error_message"] == UNREADABLE_MESSAGE
    assert row["sha256"] == hashlib.sha256(b"not a slide").hexdigest()
    assert row["registered_at"] is None


def test_req_006_no_filename_or_path_in_logs(acq, db_path, caplog):
    """REQ-006: neither the filename nor the folder path is logged, ready or not."""
    caplog.set_level(logging.DEBUG)
    (acq / PHI_NAME).write_bytes(b"pixels")
    (acq / f"unreadable-{PHI_NAME}").write_text("not a slide")

    registry = Registry(acq, db_path, opener=phi_opener)
    registry.scan_once(now=0)
    registry.scan_once(now=5)

    statuses = {row["status"] for row in db.list_slides(db_path)}
    assert statuses == {SlideStatus.READY, SlideStatus.UNREADABLE}
    assert caplog.records  # something was logged
    assert "DOE-JOHN" not in caplog.text
    assert str(acq) not in caplog.text


@pytest.mark.parametrize(
    "name", [".hidden.tif", "notes.txt", "slide.tif.part", "index.mrxs"]
)
def test_non_slide_and_hidden_files_are_ignored(acq, db_path, registry, name):
    """Hidden files and unknown extensions are never registered."""
    (acq / name).write_bytes(b"data")

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    assert db.list_slides(db_path) == []


def test_subdirectories_are_ignored(acq, db_path, registry):
    """Only the top level of the folder is scanned."""
    (acq / "nested.tif").mkdir()
    (acq / "nested.tif" / "slide.tif").write_bytes(b"pixels")

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    assert db.list_slides(db_path) == []


def test_extension_match_is_case_insensitive(acq, db_path, registry):
    """Uppercase extensions such as .SVS are recognised."""
    (acq / "SLIDE.SVS").write_bytes(b"pixels")

    registry.scan_once(now=0)

    assert only_slide(db_path)["status"] == SlideStatus.ARRIVING


def test_restart_resumes_unfinished_slide_with_same_id(acq, db_path):
    """A slide left arriving or registering at shutdown keeps its ID and restarts."""
    (acq / "slide.tif").write_bytes(b"pixels")
    Registry(acq, db_path, opener=FakeSlide).scan_once(now=0)
    slide_id = only_slide(db_path)["id"]
    db.set_status(db_path, slide_id, SlideStatus.REGISTERING)  # crashed mid-hash

    restarted = Registry(acq, db_path, opener=FakeSlide)
    restarted.scan_once(now=100)
    assert only_slide(db_path)["status"] == SlideStatus.ARRIVING

    restarted.scan_once(now=105)
    row = only_slide(db_path)
    assert row["id"] == slide_id
    assert row["status"] == SlideStatus.READY


def test_registered_slide_is_not_processed_again(acq, db_path, registry):
    """Ready slides are skipped on later scans, even across restarts."""
    (acq / "slide.tif").write_bytes(b"pixels")
    registry.scan_once(now=0)
    registry.scan_once(now=5)
    before = tuple(only_slide(db_path))

    restarted = Registry(acq, db_path, opener=FakeSlideNoMpp)
    restarted.scan_once(now=100)
    restarted.scan_once(now=200)

    assert tuple(only_slide(db_path)) == before


def test_file_removed_while_arriving_is_forgotten(acq, db_path, registry):
    """A file deleted before registration stops being tracked; its row stays."""
    slide = acq / "slide.tif"
    slide.write_bytes(b"pixels")
    registry.scan_once(now=0)

    slide.unlink()
    registry.scan_once(now=1)
    registry.scan_once(now=10)

    assert only_slide(db_path)["status"] == SlideStatus.ARRIVING


def test_polling_thread_registers_and_stops(acq, db_path):
    """start() polls in the background; stop() ends the thread promptly."""
    registry = Registry(
        acq, db_path, opener=FakeSlide, stable_seconds=0, poll_interval=0.01
    )
    (acq / "slide.tif").write_bytes(b"pixels")

    registry.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            rows = db.list_slides(db_path)
            if rows and rows[0]["status"] == SlideStatus.READY:
                break
            time.sleep(0.01)
    finally:
        registry.stop()

    assert only_slide(db_path)["status"] == SlideStatus.READY
    assert not registry._thread.is_alive()


@pytest.mark.skipif(
    not os.environ.get("TEST_SLIDE_PATH"), reason="set TEST_SLIDE_PATH to a real WSI"
)
def test_real_slide_registers(acq, db_path):
    """A real whole-slide image registers as ready with plausible metadata."""
    source = Path(os.environ["TEST_SLIDE_PATH"]).expanduser()
    (acq / f"real{source.suffix}").symlink_to(source)
    registry = Registry(acq, db_path)  # real OpenSlide

    registry.scan_once(now=0)
    registry.scan_once(now=5)

    row = only_slide(db_path)
    assert row["status"] == SlideStatus.READY
    assert row["width"] > 0 and row["height"] > 0 and row["level_count"] >= 1

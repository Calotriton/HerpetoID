"""GUI tests (headless via the offscreen Qt platform + pytest-qt)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from herpetoid.application.project_service import ProjectService
from herpetoid.application.registry import PluginRegistry
from herpetoid.application.settings import SettingsService
from herpetoid.gui.main_window import MainWindow
from herpetoid.gui.screens.plugins import PluginManagerScreen
from herpetoid.gui.screens.projects import ProjectManagerScreen
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer, ndarray_to_qimage
from herpetoid.infrastructure.plugin_discovery import discover_entry_points
from herpetoid.infrastructure.settings_store import JsonSettingsStore

pytestmark = pytest.mark.gui


@pytest.fixture
def app_state(tmp_path: Path, qtbot) -> AppState:
    registry = PluginRegistry()
    discover_entry_points(registry)
    settings = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    return AppState(
        registry=registry,
        project_service=ProjectService(app_version="test"),
        settings=settings,
    )


def test_ndarray_to_qimage(qtbot) -> None:
    gray = ndarray_to_qimage(np.zeros((10, 12), np.uint8))
    assert (gray.width(), gray.height()) == (12, 10)
    rgb = ndarray_to_qimage(np.zeros((10, 12, 3), np.uint8))
    assert (rgb.width(), rgb.height()) == (12, 10)


def test_image_viewer_set_and_zoom(qtbot) -> None:
    viewer = ImageViewer()
    qtbot.addWidget(viewer)
    assert not viewer.has_image()
    viewer.set_image(np.random.default_rng(0).integers(0, 256, (64, 80), dtype=np.uint8))
    assert viewer.has_image()
    before = viewer.current_scale()
    viewer.zoom(2.0)
    assert viewer.current_scale() > before


def test_main_window_navigation(app_state: AppState, qtbot) -> None:
    window = MainWindow(app_state)
    qtbot.addWidget(window)
    names = window.screen_names()
    assert "Home" in names
    assert "Projects" in names
    assert len(names) == 11
    assert window.current_screen_name() == "Home"
    window.navigate_to("Plugins")
    assert window.current_screen_name() == "Plugins"


def test_plugin_manager_shows_registered_plugins(app_state: AppState, qtbot) -> None:
    screen = PluginManagerScreen(app_state.registry)
    qtbot.addWidget(screen)
    assert screen.modules_table.rowCount() >= 1
    assert screen.algorithms_table.rowCount() >= 1


def test_create_project_updates_state(app_state: AppState, tmp_path: Path, qtbot) -> None:
    bundle = tmp_path / "study"
    app_state.create_project(bundle, "P1")
    assert app_state.project is not None
    assert app_state.project.project.name == "P1"
    assert (bundle / "project.db").exists()
    assert app_state.settings.settings.recent_projects == [str(bundle)]


def test_project_manager_screen_reflects_open_project(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    screen = ProjectManagerScreen(app_state)
    qtbot.addWidget(screen)
    assert "No project open" in screen.current_label.text()
    app_state.create_project(tmp_path / "p2", "P2")  # emits project_changed -> screen refreshes
    assert "P2" in screen.current_label.text()
    assert screen.recent_list.count() == 1


def test_main_window_title_tracks_project(app_state: AppState, tmp_path: Path, qtbot) -> None:
    window = MainWindow(app_state)
    qtbot.addWidget(window)
    assert window.windowTitle() == "HerpetoID"
    app_state.create_project(tmp_path / "p3", "Pyrenees")
    assert "Pyrenees" in window.windowTitle()


def test_image_import_creates_observation(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.species_combo.count() >= 1  # Calotriton asper from the registry

    source = tmp_path / "newt.png"
    PilImage.fromarray(np.zeros((32, 32, 3), np.uint8)).save(source)
    assert screen.import_files([source]) == 1

    catalog = app_state.catalog
    assert catalog is not None
    assert catalog.observation_count() == 1
    assert list((tmp_path / "proj" / "images").glob("*"))
    assert screen.gallery.count() == 1  # imported image appears as a thumbnail


def test_dynamic_form_roundtrip_and_validation(qtbot) -> None:
    from herpetoid.gui.widgets.dynamic_form import DynamicForm
    from herpetoid.plugins.species.calotriton_asper import CalotritonAsperModule

    fields = CalotritonAsperModule().define_observation_fields()
    form = DynamicForm(fields)
    qtbot.addWidget(form)

    form.set_values({"svl": 52.3, "sex": "female"})
    values = form.values()
    assert values["svl"] == 52.3
    assert values["sex"] == "female"
    assert form.validate().ok

    form.set_values({"svl": -5.0})  # below the field's min_value
    assert not form.validate().ok


def test_statistics_screen(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.statistics import StatisticsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(image)
    catalog.import_observation(species.id, [image], measurements={"svl": 40.0, "sex": "female"})
    catalog.import_observation(species.id, [image], measurements={"svl": 50.0, "sex": "male"})

    screen = StatisticsScreen(app_state)
    qtbot.addWidget(screen)
    assert "Observations: 2" in screen.summary_label.text()
    names = [screen.table.item(r, 0).text() for r in range(screen.table.rowCount())]
    assert "mean_svl" in names
    assert "sex_ratio" in names


def test_settings_screen_changes_theme(app_state: AppState, qtbot) -> None:
    from herpetoid.gui.screens.settings import SettingsScreen

    screen = SettingsScreen(app_state)
    qtbot.addWidget(screen)
    screen.theme_combo.setCurrentText("dark")
    assert app_state.settings.settings.theme == "dark"
    screen.top_k_spin.setValue(7)
    assert app_state.settings.settings.default_top_k == 7


def test_observations_screen_lists_and_shows_image(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((16, 16, 3), 120, np.uint8)).save(image)
    catalog.import_observation(species.id, [image], observer="AL", measurements={"svl": 40.0})

    screen = ObservationsScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.table.rowCount() == 1
    assert screen.table.item(0, 2).text() == "AL"  # observer column
    assert screen.viewer.has_image()  # first row auto-selected, image shown without a click
    screen.table.selectRow(0)
    assert screen.viewer.has_image()


def test_candidate_ranking_identify_and_confirm(app_state: AppState, tmp_path: Path, qtbot) -> None:
    import cv2
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.candidate_ranking import CandidateRankingScreen

    def spots(seed: int, size: int = 256, count: int = 45) -> np.ndarray:
        rng = np.random.default_rng(seed)
        img = np.full((size, size), 255, np.uint8)
        for _ in range(count):
            cx, cy = rng.integers(20, size - 20, size=2)
            ax, ay = rng.integers(5, 15, size=2)
            cv2.ellipse(
                img,
                (int(cx), int(cy)),
                (int(ax), int(ay)),
                int(rng.integers(0, 180)),
                0,
                360,
                0,
                -1,
            )
        return img

    def rotate(img: np.ndarray, deg: float) -> np.ndarray:
        h, w = img.shape[:2]
        return cv2.warpAffine(
            img, cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0), (w, h), borderValue=255
        )

    def save(path: Path, gray: np.ndarray) -> None:
        PilImage.fromarray(np.stack([gray, gray, gray], axis=-1)).save(path)

    cv2.setRNGSeed(7)
    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    base = spots(1)
    pa, pb, pc = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    save(pa, base)
    save(pb, rotate(base, 10))
    save(pc, spots(999))
    obs_a = catalog.import_observation(species.id, [pa])
    obs_b = catalog.import_observation(species.id, [pb])
    catalog.import_observation(species.id, [pc])

    screen = CandidateRankingScreen(app_state)
    qtbot.addWidget(screen)
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(obs_a.id))
    screen.algorithm_combo.setCurrentIndex(screen.algorithm_combo.findData("orb"))
    screen.identify()

    assert screen._candidates
    assert screen._candidates[0].observation.id == obs_b.id  # same individual (rotated) first
    assert screen.query_viewer.has_image()
    screen.table.selectRow(0)
    assert screen.candidate_viewer.has_image()

    screen.confirm_same()  # links query + candidate to one (new) individual
    assert catalog.individual_count() == 1


def test_individual_browser(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.individuals import IndividualBrowserScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((16, 16, 3), 100, np.uint8)).save(image)
    observation = catalog.import_observation(species.id, [image])
    individual = catalog.create_individual(species.id, code="CA-001")
    assert observation.id is not None
    catalog.link_observation(observation.id, individual.id)

    screen = IndividualBrowserScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.table.rowCount() == 1
    assert screen.table.item(0, 0).text() == "CA-001"
    assert screen.table.item(0, 3).text() == "1"  # one linked observation
    assert screen.viewer.has_image()

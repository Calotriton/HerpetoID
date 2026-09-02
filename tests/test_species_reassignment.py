"""Moving observations to another species — the fix for a batch imported under the wrong one."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.api import ROI
from herpetoid.application.catalog_service import PENDING_CODE_KEY, CatalogService, pending_code
from herpetoid.application.project_service import ProjectContext, ProjectService
from herpetoid.domain import PluginRef

pytestmark = pytest.mark.integration

NEWT = PluginRef("calotriton_asper", "1.0")
SALAMANDER = PluginRef("salamandra_salamandra", "1.0")


def _catalog(tmp_path: Path) -> tuple[ProjectContext, CatalogService]:
    context = ProjectService().create(tmp_path / "bundle", "B")
    return context, CatalogService(context)


def _capture(catalog: CatalogService, species_id: int, path: Path, **kwargs: object) -> int:
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)
    observation = catalog.import_observation(species_id, [path], **kwargs)  # type: ignore[arg-type]
    assert observation.id is not None
    return observation.id


def test_moving_observations_keeps_their_data_and_empties_the_old_species(tmp_path: Path) -> None:
    context, catalog = _catalog(tmp_path)
    wrong = catalog.ensure_species("Calotriton asper", module=NEWT)
    assert wrong.id is not None
    ids = [
        _capture(
            catalog, wrong.id, tmp_path / f"{index}.png",
            observer="AL", measurements={"svl": 90.0 + index},
        )
        for index in range(3)
    ]
    image = catalog.images_for(ids[0])[0]
    assert image.id is not None
    catalog.set_image_roi(image.id, ROI.rectangle(2, 2, 10, 10))

    right = catalog.ensure_species("Salamandra salamandra", module=SALAMANDER)
    assert right.id is not None
    report = catalog.reassign_species(ids, right.id)

    assert report.observations == 3
    assert [o.species_id for o in catalog.list_observations()] == [right.id] * 3
    # Everything recorded survives the move: measurements, observer, and the marked region.
    moved = {o.id: o for o in catalog.list_observations()}
    assert moved[ids[0]].measurements["svl"] == 90.0
    assert moved[ids[0]].observer == "AL"
    assert catalog.get_image_roi(image.id) is not None
    # The project no longer claims a species it does not hold — this is what the status bar reads.
    assert [s.scientific_name for s in catalog.list_species()] == ["Salamandra salamandra"]
    assert report.species_removed == ("Calotriton asper",)
    context.close()


def test_an_individual_whose_captures_all_move_comes_across_intact(tmp_path: Path) -> None:
    context, catalog = _catalog(tmp_path)
    wrong = catalog.ensure_species("Calotriton asper", module=NEWT)
    assert wrong.id is not None
    first = _capture(catalog, wrong.id, tmp_path / "a.png")
    second = _capture(catalog, wrong.id, tmp_path / "b.png")
    individual = catalog.create_individual(wrong.id, code="X-001")
    assert individual.id is not None
    for observation_id in (first, second):
        catalog.link_observation(observation_id, individual.id)

    right = catalog.ensure_species("Salamandra salamandra", module=SALAMANDER)
    assert right.id is not None
    report = catalog.reassign_species([first, second], right.id)

    assert report.individuals_moved == ("X-001",)
    assert report.observations_unlinked == ()
    moved = catalog.list_individuals()
    assert [(i.code, i.species_id) for i in moved] == [("X-001", right.id)]
    # The identity is intact: both captures still point at it.
    assert {o.individual_id for o in catalog.list_observations()} == {individual.id}
    context.close()


def test_a_capture_leaving_its_individual_behind_is_unlinked_and_keeps_its_code_pending(
    tmp_path: Path,
) -> None:
    """The individual keeps the captures that stay; the one that moves keeps its code to re-confirm."""
    context, catalog = _catalog(tmp_path)
    wrong = catalog.ensure_species("Calotriton asper", module=NEWT)
    assert wrong.id is not None
    staying = _capture(catalog, wrong.id, tmp_path / "a.png")
    moving = _capture(catalog, wrong.id, tmp_path / "b.png")
    individual = catalog.create_individual(wrong.id, code="X-001")
    assert individual.id is not None
    for observation_id in (staying, moving):
        catalog.link_observation(observation_id, individual.id)

    right = catalog.ensure_species("Salamandra salamandra", module=SALAMANDER)
    assert right.id is not None
    report = catalog.reassign_species([moving], right.id)

    assert report.individuals_moved == ()
    assert report.observations_unlinked == (moving,)
    assert report.species_removed == ()  # the old species still holds the capture that stayed
    by_id = {o.id: o for o in catalog.list_observations()}
    assert by_id[staying].individual_id == individual.id  # untouched
    assert by_id[moving].individual_id is None
    assert pending_code(by_id[moving]) == "X-001"  # nothing is silently lost
    assert by_id[moving].measurements[PENDING_CODE_KEY] == "X-001"
    context.close()


def test_a_code_already_taken_in_the_target_species_unlinks_rather_than_collides(
    tmp_path: Path,
) -> None:
    """The (species, code) pair is unique — moving onto an existing code must not corrupt either."""
    context, catalog = _catalog(tmp_path)
    wrong = catalog.ensure_species("Calotriton asper", module=NEWT)
    right = catalog.ensure_species("Salamandra salamandra", module=SALAMANDER)
    assert wrong.id is not None and right.id is not None
    moving = _capture(catalog, wrong.id, tmp_path / "a.png")
    mine = catalog.create_individual(wrong.id, code="SHARED")
    assert mine.id is not None
    catalog.link_observation(moving, mine.id)
    catalog.create_individual(right.id, code="SHARED")  # the target already uses that code

    report = catalog.reassign_species([moving], right.id)

    assert report.individuals_moved == ()
    assert report.observations_unlinked == (moving,)
    codes = sorted((i.code, i.species_id) for i in catalog.list_individuals())
    assert codes == [("SHARED", wrong.id), ("SHARED", right.id)]  # both survive, unmerged
    context.close()


def test_moving_nothing_or_moving_to_the_same_species_does_nothing(tmp_path: Path) -> None:
    context, catalog = _catalog(tmp_path)
    species = catalog.ensure_species("Calotriton asper", module=NEWT)
    assert species.id is not None
    observation = _capture(catalog, species.id, tmp_path / "a.png")

    assert catalog.reassign_species([], species.id).observations == 0
    assert catalog.reassign_species([observation], species.id).observations == 0
    assert catalog.reassign_species([9999], species.id).observations == 0
    assert [s.scientific_name for s in catalog.list_species()] == ["Calotriton asper"]
    with pytest.raises(KeyError):
        catalog.reassign_species([observation], 4242)
    context.close()

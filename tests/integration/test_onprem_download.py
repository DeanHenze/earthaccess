import logging
import random
import shutil

import earthaccess
import pytest
from earthaccess import Auth, DataCollections, DataGranules, Store

logger = logging.getLogger(__name__)


daacs_list = [
    {
        "short_name": "NSIDC",
        "collections_count": 50,
        "collections_sample_size": 3,
        "granules_count": 100,
        "granules_sample_size": 2,
        "granules_max_size_mb": 100,
    },
    {
        "short_name": "GES_DISC",
        "collections_count": 100,
        "collections_sample_size": 2,
        "granules_count": 100,
        "granules_sample_size": 2,
        "granules_max_size_mb": 130,
    },
    {
        "short_name": "LPDAAC",
        "collections_count": 100,
        "collections_sample_size": 2,
        "granules_count": 100,
        "granules_sample_size": 2,
        "granules_max_size_mb": 100,
    },
    #
    # ORNLDAAC no longer has any on-prem collections.  This returns 0 collections:
    # https://cmr.earthdata.nasa.gov/search/collections?data_center=ORNL_DAAC&cloud_hosted=false
    # The following is commented out because the test in this file will now always fail
    # because there are no longer any on-prem collections.
    #
    # {
    #     "short_name": "ORNLDAAC",
    #     "collections_count": 100,
    #     "collections_sample_size": 3,
    #     "granules_count": 100,
    #     "granules_sample_size": 2,
    #     "granules_max_size_mb": 50,
    # },
]


def get_sample_granules(granules, sample_size, max_granule_size):
    """Returns a list with sample granules and their size in MB if
    the total size is less than the max_granule_size.
    """
    files_to_download = []
    total_size = 0
    max_tries = sample_size * 2
    tries = 0

    while tries <= max_tries:
        g = random.sample(granules, 1)[0]
        if g.size() > max_granule_size:
            tries += 1
            continue
        else:
            files_to_download.append(g)
            total_size += g.size()
            if len(files_to_download) >= sample_size:
                break
    return files_to_download, round(total_size, 2)


def supported_collection(data_links):
    return all("podaac-tools.jpl.nasa.gov/drive" not in url for url in data_links)


@pytest.mark.parametrize("daac", daacs_list)
def test_earthaccess_can_download_onprem_collection_granules(tmp_path, daac):
    """Tests that we can download cloud collections using HTTPS links."""
    daac_shortname = daac["short_name"]
    collections_count = daac["collections_count"]
    collections_sample_size = daac["collections_sample_size"]
    granules_count = daac["granules_count"]
    granules_sample_size = daac["granules_sample_size"]
    granules_max_size = daac["granules_max_size_mb"]

    collection_query = DataCollections().data_center(daac_shortname).cloud_hosted(False)
    hits = collection_query.hits()
    logger.info(f"Cloud hosted collections for {daac_shortname}: {hits}")
    collections = collection_query.get(collections_count)
    assert len(collections) > collections_sample_size
    # We sample n cloud hosted collections from the results
    random_collections = random.sample(collections, collections_sample_size)
    logger.info(f"Sampled {len(random_collections)} collections")

    for collection in random_collections:
        concept_id = collection.concept_id()
        granule_query = DataGranules().concept_id(concept_id)
        total_granules = granule_query.hits()
        granules = granule_query.get(granules_count)
        assert len(granules) > 0, "Could not fetch granules"
        assert isinstance(granules[0], earthaccess.DataGranule)
        data_links = granules[0].data_links()
        if not supported_collection(data_links):
            logger.warning(f"PODAAC DRIVE is not supported at the moment: {data_links}")
            continue
        granules_to_download, total_size_cmr = get_sample_granules(
            granules, granules_sample_size, granules_max_size
        )
        if len(granules_to_download) == 0:
            logger.debug(
                f"Skipping {concept_id}, granule size exceeds configured max size"
            )
            continue
        logger.info(
            f"Testing {concept_id}, granules in collection: {total_granules}, "
            f"download size(MB): {total_size_cmr}"
        )
        path = tmp_path / "tests" / "integration" / "data" / concept_id
        path.mkdir(parents=True)
        store = Store(Auth().login(strategy="environment"))
        # We are testing this method
        downloaded_results = store.get(granules_to_download, local_path=path)

        assert isinstance(downloaded_results, list)
        assert len(downloaded_results) >= granules_sample_size

        # test that we downloaded the mb reported by CMR
        total_mb_downloaded = round(
            (sum(file.stat().st_size for file in path.rglob("*")) / 1024**2), 2
        )
        # clean the directory
        shutil.rmtree(path)

        # test that we could download the data
        if total_mb_downloaded <= 0:
            logger.warning(f"earthaccess could not download {concept_id}")
        if total_mb_downloaded != total_size_cmr:
            logger.warning(
                f"Warning: {concept_id} downloaded size {total_mb_downloaded}MB is "
                f"different from the size reported by CMR: {total_size_cmr}MB"
            )

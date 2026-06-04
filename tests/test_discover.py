from outlier_scout.discover import discover_channels
from tests.fakes import FakeYouTubeClient


def test_discovery_merges_seeds_and_search_deduped_and_capped():
    client = FakeYouTubeClient(
        channels={}, videos={},
        search_results={"kw1": ["@A", "@B"], "kw2": ["@B", "@C", "@D"]},
    )
    result = discover_channels(
        client, keywords=["kw1", "kw2"], seed_channels=["@A", "@SEED"],
        max_channels=4,
    )
    # seeds first (order preserved), then new discovered, deduped, capped at 4
    assert result == ["@A", "@SEED", "@B", "@C"]


def test_discovery_respects_cap_with_only_seeds():
    client = FakeYouTubeClient(channels={}, videos={}, search_results={})
    result = discover_channels(
        client, keywords=[], seed_channels=["@A", "@B", "@C"], max_channels=2,
    )
    assert result == ["@A", "@B"]


import httplib2
from googleapiclient.errors import HttpError


class _SearchFailsClient:
    def __init__(self):
        self._results = {"kw1": ["@A"]}

    def search_channels(self, query, max_results):
        if query == "kw2":
            raise HttpError(httplib2.Response({"status": 403}), b"quota exceeded")
        return self._results.get(query, [])


def test_discovery_stops_gracefully_on_quota_error():
    client = _SearchFailsClient()
    result = discover_channels(
        client, keywords=["kw1", "kw2"], seed_channels=["@S"], max_channels=10,
    )
    # seed + kw1 result kept; the kw2 quota error halts further discovery
    assert result == ["@S", "@A"]

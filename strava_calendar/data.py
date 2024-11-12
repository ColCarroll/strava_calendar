import datetime
import gzip
import json
import pathlib
import zipfile
from collections.abc import Callable, Generator, Iterable
from typing import Any

import gpxpy
import tqdm
from fitparse import FitFile


class StravaGPXFile:
    def __init__(self, data):
        self.data = gpxpy.parse(data)
        self.session_data = self._get_session_data()

    def _get_session_data(self):
        if len(self.data.tracks) != 1 or len(self.data.tracks[0].segments) != 1:
            print(
                f"expected only 1 session record per file, not {len(self.data.tracks)} "
                f"tracks and {len(self.data.tracks[0].segments)} segments"
            )
        segment = self.data.tracks[0].segments[0]
        return {
            "distance": self._get_total_distance(segment),
            "elapsed_time": self._get_duration(segment),
            "start_time": self._get_start_time(segment),
            "sport": None,
            "sub_sport": None,
            "location": self._get_location(segment),
            "route": self._get_route(segment),
        }

    def _get_total_distance(self, segment):
        return segment.get_moving_data().moving_distance

    def _get_duration(self, segment):
        return segment.get_moving_data().moving_time

    def _get_start_time(self, segment):
        return segment.points[0].time.replace(tzinfo=None)

    def _get_location(self, segment):
        point = segment.points[0]
        return {"lat": point.latitude, "long": point.longitude}

    def _get_route(self, segment):
        lat, long = zip(
            *[
                (
                    int(pt.latitude * 2**31 / 180.0),
                    int(pt.longitude * 2**31 / 180.0),
                )
                for pt in segment.points
            ]
        )
        return {"lat": lat, "long": long}

    def to_json(self):
        data = self.session_data.copy()
        data["start_time"] = data["start_time"].isoformat()
        return data


class StravaFile(FitFile):
    def __init__(self, file):
        # The check_crc being false should make things somewhat faster, at
        # the expense of error messages, I think...
        super().__init__(file, check_crc=False)
        self.session_data = self._get_session_data()

    def _get_session_data(self):
        session_data = list(self.get_messages("session"))[:1]
        if len(session_data) != 1:
            print(
                f"expected only 1 session record per file, not {len(self.data.tracks)} "
                f"tracks and {len(self.data.tracks[0].segments)} segments"
            )
        return {j["name"]: j["value"] for j in session_data[0].as_dict()["fields"]}

    def location(self) -> dict[str, float]:
        lat, long = (
            self.session_data["start_position_lat"],
            self.session_data["start_position_long"],
        )
        if (lat is not None) and (long is not None):
            lat *= 180.0 / 2**31
            long *= 180.0 / 2**31
        return {"lat": lat, "long": long}

    def route(self) -> dict[str, list[float]]:
        coords = [
            [record.get_value("position_long"), record.get_value("position_lat")]
            for record in self.get_messages("record")
        ]
        coords = [row for row in coords if not any(j is None for j in row)]
        if len(coords) > 0:
            long, lat = zip(*coords)
        else:
            long, lat = [], []
        return {"lat": lat, "long": long}

    def to_json(self) -> dict[str, Any]:
        return {
            "distance": self.session_data["total_distance"],
            "elapsed_time": self.session_data["total_timer_time"],
            "start_time": self.session_data["start_time"].isoformat(),
            "sport": self.session_data["sport"],
            "sub_sport": self.session_data["sub_sport"],
            "location": self.location(),
            "route": self.route(),
        }


DataFile = StravaFile | StravaGPXFile
FilterFunc = Callable[[DataFile], bool]


def is_sport(sport: str = "running") -> FilterFunc:
    # hardcode more paces if you are using GPX files...
    if sport == "running":
        # if not labelled, use 5min/mile -> 10min/mile
        # as a guess for what is a run.
        lo, hi = 0.1875, 0.375
    else:
        lo, hi = 0, 0

    def filter_func(strava_file: DataFile) -> bool:
        if strava_file.session_data["sport"] is None:
            # if distance is 0 or False-y, just skip it.
            if strava_file.session_data["distance"]:
                pace = (
                    strava_file.session_data["elapsed_time"]
                    / strava_file.session_data["distance"]
                )
                return lo < pace < hi
            else:
                return False
        return strava_file.session_data["sport"] == sport

    return filter_func


def is_after(start_date: datetime.datetime) -> FilterFunc:
    def filter_func(strava_file: DataFile) -> bool:
        return strava_file.session_data["start_time"] >= start_date

    return filter_func


def is_before(end_date: datetime.datetime) -> FilterFunc:
    def filter_func(strava_file: DataFile) -> bool:
        return strava_file.session_data["start_time"] < end_date

    return filter_func


def get_files(zip_path: pathlib.Path) -> Generator[tuple[bytes, str]]:
    suffixes = (".fit.gz", ".gpx", ".gpx.gz")
    with zipfile.ZipFile(zip_path) as run_zip:
        good_files = []
        for f in run_zip.namelist():
            if f.startswith("activities/") and any(
                f.endswith(suffix) for suffix in suffixes
            ):
                good_files.append(f)
        for filename in tqdm.tqdm(good_files):
            with run_zip.open(filename) as buff:
                if filename.endswith("gz"):
                    yield gzip.decompress(buff.read()), filename
                else:
                    yield buff.read(), filename


def filter_files(
    zip_path: pathlib.Path, filters: Iterable[FilterFunc]
) -> Generator[DataFile]:
    for data, fname in get_files(zip_path):
        if fname.endswith(".fit.gz"):
            strava_file = StravaFile(data)
        elif fname.endswith(".gpx") or fname.endswith(".gpx.gz"):
            strava_file = StravaGPXFile(data)
        if all(f(strava_file) for f in filters):
            yield strava_file


def get_data(
    zip_path: str | pathlib.Path,
    sport: str,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    cache_dir: pathlib.Path | None = None,
):
    if cache_dir is None:
        cache_dir = pathlib.Path(__file__).parent.resolve() / ".cache"
        if not cache_dir.is_dir():
            cache_dir.mkdir()

    zip_path: pathlib.Path = pathlib.Path(zip_path)
    date_fmt = "%Y-%m-%d"
    cache_dir = cache_dir / zip_path.name
    if not cache_dir.is_dir():
        cache_dir.mkdir()
    filename = (
        cache_dir
        / f"{sport}_{start_date.strftime(date_fmt)}_{end_date.strftime(date_fmt)}.json"
    )
    if not filename.exists():
        filters = [is_sport(sport), is_after(start_date), is_before(end_date)]
        data = {"activities": []}
        for strava_file in filter_files(zip_path, filters):
            try:
                data["activities"].append(strava_file.to_json())
            except KeyError as e:
                print(e)
        with filename.open("w") as buff:
            json.dump(data, buff)
    with filename.open() as buff:
        return json.load(buff)

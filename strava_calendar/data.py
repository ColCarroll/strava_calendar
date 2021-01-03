import gzip
import json
import os
import re
import zipfile

from fitparse import FitFile
import gpxpy
import gzip
import tqdm

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
if not os.path.isdir(CACHE):
    os.mkdir(CACHE)


class StravaGPXFile:
    def __init__(self, data):
        self.data = gpxpy.parse(data)
        self.session_data = self._get_session_data()

    def _get_session_data(self):
        if len(self.data.tracks) != 1 or len(self.data.tracks[0].segments) != 1:
            raise AssertionError("expected only 1 session record per file!")
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
                    int(pt.latitude * 2 ** 31 / 180.0),
                    int(pt.longitude * 2 ** 31 / 180.0),
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
        super().__init__(file)
        self.session_data = self._get_session_data()

    def _get_session_data(self):
        session_data = list(self.get_messages("session"))
        if len(session_data) != 1:
            raise AssertionError("Expected only 1 session record per file!")
        return {j["name"]: j["value"] for j in session_data[0].as_dict()["fields"]}

    def location(self):
        lat, long = (
            self.session_data["start_position_lat"],
            self.session_data["start_position_long"],
        )
        if (lat is not None) and (long is not None):
            lat *= 180.0 / 2 ** 31
            long *= 180.0 / 2 ** 31
        return {"lat": lat, "long": long}

    def route(self):
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

    def to_json(self):
        return {
            "distance": self.session_data["total_distance"],
            "elapsed_time": self.session_data["total_timer_time"],
            "start_time": self.session_data["start_time"].isoformat(),
            "sport": self.session_data["sport"],
            "sub_sport": self.session_data["sub_sport"],
            "location": self.location(),
            "route": self.route(),
        }


def is_sport(sport="running"):
    # hardcode more paces if you are using GPX files...
    if sport == "running":
        # if not labelled, use 5min/mile -> 10min/mile
        # as a guess for what is a run.
        lo, hi = 0.1875, 0.375
    else:
        lo, hi = 0, 0

    def filter_func(strava_file):
        if strava_file.session_data["sport"] is None:
            pace = (
                strava_file.session_data["elapsed_time"]
                / strava_file.session_data["distance"]
            )
            return lo < pace < hi
        return strava_file.session_data["sport"] == sport

    return filter_func


def is_after(start_date):
    def filter_func(strava_file):
        return strava_file.session_data["start_time"] >= start_date

    return filter_func


def is_before(end_date):
    def filter_func(strava_file):
        return strava_file.session_data["start_time"] < end_date

    return filter_func


def get_files(zip_path):
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


def filter_files(zip_path, filters):
    for data, fname in get_files(zip_path):
        if fname.endswith(".fit.gz"):
            strava_file = StravaFile(data)
        elif fname.endswith(".gpx") or fname.endswith(".gpx.gz"):
            strava_file = StravaGPXFile(data)
        if all(f(strava_file) for f in filters):
            yield strava_file


def get_data(zip_path, sport, start_date, end_date):
    date_fmt = "%Y-%m-%d"
    zip_fname = os.path.basename(zip_path)
    filter_dir = os.path.join(CACHE, zip_fname)
    if not os.path.isdir(filter_dir):
        os.mkdir(filter_dir)
    filename = os.path.join(
        filter_dir,
        f"{sport}_{start_date.strftime(date_fmt)}_{end_date.strftime(date_fmt)}.json",
    )
    if not os.path.exists(filename):
        filters = [is_sport(sport), is_after(start_date), is_before(end_date)]
        data = {"activities": []}
        for strava_file in filter_files(zip_path, filters):
            try:
                data["activities"].append(strava_file.to_json())
            except KeyError as e:
                print(e)
        with open(filename, "w") as buff:
            json.dump(data, buff)
    with open(filename, "r") as buff:
        return json.load(buff)


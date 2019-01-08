import copy
import datetime

import matplotlib.pyplot as plt
import numpy as np


def _datetime_to_week_day(my_datetime):
    """Returns day of week in (0, 7) and week of year in (-1, -52).

    This function is bad and should be fixed.
    """
    if my_datetime.day == 1 and my_datetime.month == 1:
        return (1, -1)
    if not isinstance(my_datetime, datetime.datetime) and isinstance(
        my_datetime, datetime.date
    ):
        my_datetime = datetime.datetime(
            my_datetime.year, my_datetime.month, my_datetime.day
        )
    year, week, day = my_datetime.date().isocalendar()
    week += 52 * (year % my_datetime.year)
    week_del, day = divmod(day, 7)
    week += week_del
    return day, -week


class Run:
    def __init__(self, data, origin=np.array([0, 0])):
        self.data = copy.copy(data)
        self.data["route"] = np.array(
            [self.data["route"]["lat"], self.data["route"]["long"]]
        ).T
        self.data["start_time"] = datetime.datetime.strptime(
            self.data["start_time"], "%Y-%m-%dT%H:%M:%S"
        )
        self.origin = origin

    def get_scale(self, xlims=(0.1, 0.9), ylims=(0.1, 0.9)):
        coords = self.data["route"]
        if coords.shape[0] == 0:
            return 1.0

        scales = coords.max(axis=0) - coords.min(axis=0)

        scales[0] /= xlims[1] - xlims[0]
        scales[1] /= ylims[1] - ylims[0]
        return max(scales)

    def get_offsets(self, scale, xlims=(0.1, 0.9), ylims=(0.1, 0.9)):
        coords = self.data["route"]

        if coords.shape[0] == 0:
            return np.array([0, 0])
        offset = coords.min(axis=0)

        offset[0] -= scale * xlims[0]
        offset[1] -= scale * ylims[0]

        padding = ((coords - offset) / scale).max(axis=0)

        offset[0] -= 0.5 * scale * (xlims[1] - padding[0])
        offset[1] -= 0.5 * scale * (ylims[1] - padding[1])

        return offset

    def get_scale_and_offsets(self, xlims=(0.1, 0.9), ylims=(0.1, 0.9)):
        scale = self.get_scale(xlims=xlims, ylims=ylims)
        offsets = self.get_offsets(scale, xlims=xlims, ylims=ylims)
        return scale, offsets

    def route(self, origin=None, scale_and_offset=None):
        if origin is None:
            origin = self.origin + self.get_week_day()
        if scale_and_offset is None:
            scale_and_offset = self.get_scale_and_offsets()
        scale, offset = scale_and_offset
        return (((self.data["route"] - offset) / scale) + origin).T

    def get_week_day(self):
        return np.array(_datetime_to_week_day(self.data["start_time"]))

    def date(self):
        return self.data["start_time"].date()


class Day:
    def __init__(self, *runs):
        self.runs = list(runs)

    def add_run(self, run):
        self.runs.append(run)

    def default_offset(self):
        return self.runs[0].get_week_day()

    def bottom_left(self):
        return np.min([j.min(axis=1) for j in self.routes()], axis=0)

    def date(self):
        return self.runs[0].date()

    def routes(self, extra_offset=np.array([0, 0])):
        scale = max(run.get_scale() for run in self.runs)
        for run in self.runs:
            offset = run.get_offsets(scale)
            offset = offset + scale * extra_offset
            yield run.route(scale_and_offset=(scale, offset))


class Plotter:
    def __init__(self, data):
        self.years = {}
        self.months = {}
        self.days = {}
        for activity in data["activities"]:
            self.add_activity(activity)

    def add_activity(self, activity):
        run = Run(activity)
        run_date = run.date()
        key = (run_date.year, run_date.month, run_date.day)
        if key not in self.days:
            self.days[key] = Day()
            if key[:2] not in self.months:
                self.months[key[:2]] = []
                if key[0] not in self.years:
                    self.years[key[0]] = []

        self.days[key].add_run(run)
        self.months[key[:2]].append(self.days[key])
        self.years[key[0]].append(self.months[key[:2]])

    def plot_day(self, *, year, month, day, fig, ax):
        if (year, month, day) not in self.days:
            raise TypeError(f"No data from {year}-{month}-{day}!")
        day = self.days[(year, month, day)]
        for route in day.routes():
            ax.plot(*route, "k", linewidth=1, antialiased=True)
        label = f'{day.date().strftime("%b")} {day.date().day}'

        ax.text(
            *day.bottom_left(),
            label,
            fontdict={"fontsize": fig.get_figheight() * fig.get_dpi() / 10},
            alpha=0.5,
        )
        ax.axis("off")

    def plot_month(self, *, year, month, fig, ax, extra_offset=np.array([0, 0])):
        month_data = {day.date(): day for day in self.months.get((year, month), [])}

        date = datetime.date(year, month, 1)
        cur_week = 1
        week_days = []
        while date.year == year and date.month == month:
            if date in month_data:
                for route in month_data[date].routes(extra_offset=extra_offset):
                    ax.plot(*route, "k", linewidth=1, antialiased=True)

            day, week = _datetime_to_week_day(date)
            if week != cur_week:
                if week_days:
                    hline_x = (
                        np.array([min(week_days), max(week_days) + 0.95])
                        - extra_offset[0]
                    )
                    hline_y = np.array([cur_week, cur_week]) - extra_offset[1]
                    ax.plot(hline_x, hline_y, "k-", alpha=0.5, linewidth=0.5)
                cur_week = week
                week_days = []

            if date.day == 1:
                label = f'{date.strftime("%b")} {date.day}'
            else:
                label = str(date.day)
            ax.text(
                day - extra_offset[0], week + 0.05 - extra_offset[1], label, alpha=0.5
            )
            week_days.append(day)
            date += datetime.timedelta(days=1)

        if week_days:
            hline_x = (
                np.array([min(week_days), max(week_days) + 0.95]) - extra_offset[0]
            )
            hline_y = np.array([cur_week, cur_week]) - extra_offset[1]
            ax.plot(hline_x, hline_y, "k-", alpha=0.5, linewidth=0.5)
            cur_week = week

        ax.axis("off")
        plt.tight_layout()
        return fig, ax, cur_week

    def plot_year(self, *, year, fig, ax, n_cols=4, month_gap=0, col_gap=0.5):
        n_rows = 12 // n_cols
        y_offset = 0
        new_y_offset = 0

        for idx in range(n_cols):
            y_offset = new_y_offset + 1
            new_y_offset = 0
            for month in range(n_rows * idx + 1, n_rows * idx + n_rows + 1):
                row = month - n_rows * idx - 1
                fig, ax, new_y_offset = self.plot_month(
                    year=year,
                    month=month,
                    fig=fig,
                    ax=ax,
                    extra_offset=np.array(
                        [-(7 + col_gap) * idx, y_offset + month_gap * row]
                    ),
                )
        return fig, ax


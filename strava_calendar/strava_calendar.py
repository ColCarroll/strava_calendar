import datetime

import matplotlib.pyplot as plt

from .data import get_data
from .plot import Plotter


def plot_calendar(
    *,
    zip_path,
    year,
    plot_size=1,
    n_cols=4,
    month_gap=0,
    col_gap=0.5,
    sport="running",
    label=None,
):
    data = get_data(
        zip_path,
        sport,
        datetime.datetime(year, 1, 1),
        datetime.datetime(year + 1, 1, 1),
    )

    plotter = Plotter(data)

    fig, ax = plt.subplots(figsize=(plot_size * 5 * n_cols, plot_size * 40 / n_cols))
    fig, ax = plotter.plot_year(
        year=year, fig=fig, ax=ax, n_cols=n_cols, month_gap=month_gap, col_gap=col_gap
    )
    if label is None:
        label = str(year)
    ax.text(0, -1, label, fontdict={"fontsize": 32, "fontweight": "heavy"}, alpha=0.5)
    return fig, ax

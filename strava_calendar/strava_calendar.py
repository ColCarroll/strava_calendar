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
    """Plot a year of Strava data in a calendar layout.

    Parameters
    ----------
    zip_path : str
        Path to .zip archive from Strava
    year : int
        Year of data to use. We have to unzip and read each file in the archive
        to figure out what year it is from, and this takes around 5 minutes for
        a new year of data.
    plot_size : float (default=1)
        The size of the plot is dynamically chosen for the layout, but you can make
        it bigger or smaller by making this number bigger or smaller.
    n_cols : int (default=4)
        Number of columns to divide the days into. Splits evenly on months, so
        this number should evenly divide 12.
    month_gap : float (default=0)
        Vertical space between two months. Each calendar square is 1 x 1, so
        a value of 1.5 here would move the months 1.5 calendar squares apart.
    col_gap : float (default=0.5)
        Horizontal space between columns. A calendar square is 1 x 1, so a
        value of 0.5 here puts columns half a square apart.
    sport : str (default="running")
        Sport to plot routes for. I have not tested this with anything except
        running, but maybe you get lucky!
    label : str or None
        Label in the top left corner of the plots. Defaults to the year. Use ""
        to not have any label.

    Returns
    -------
    figure, axis
        The matplotlib figure and axis with the plot. These can be used
        for further customization.
    """
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

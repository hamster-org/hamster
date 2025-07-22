import heapq
import itertools
import math
import string
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Tuple
import seaborn as sns
from matplotlib.cm import Pastel1
import numpy as np
from matplotlib import pyplot as plt
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from upsetplot import from_memberships, UpSet

from hamster.code_analysis.utils import constants
from hamster.utils.pretty import RichLog


class ExtractStatisticsUtils:

    def __init__(self, filepath: Path):
        self.filepath = filepath

    @staticmethod
    def compare_ordered(a, b):
        min_len = min(len(a), len(b))
        match_count = sum(1 for i in range(min_len) if a[i] == b[i])
        avg_len = (len(a) + len(b)) / 2
        return (match_count / avg_len) * 100 if avg_len else 0

    def match_percentage(self, data: list) -> Tuple[dict, dict]:
        """
        Given a list of data, provide the match percentage
        Returns:

        """
        # Counters for match categories
        order_inde_matches = {
            '100% match': 0,
            '>=70% match': 0,
            '>=50% match': 0,
            '>=30% match': 0,
            '<30% match': 0
        }
        order_de_matches = {
            '100% match': 0,
            '>=70% match': 0,
            '>=50% match': 0,
            '>=30% match': 0,
            '<30% match': 0
        }

        # Track best match for each list
        best_matches = [0] * len(data)
        order_de_best_matches = [0] * len(data)
        # Compare all unique pairs
        for i, j in itertools.combinations(range(len(data)), 2):
            set_i, set_j = set(data[i]), set(data[j])
            common = set_i.intersection(set_j)
            avg_len = (len(set_i) + len(set_j)) / 2
            percent_match = len(common) / avg_len * 100 if avg_len else 0

            # Keep the best (highest) match seen for each list
            best_matches[i] = max(best_matches[i], percent_match)
            best_matches[j] = max(best_matches[j], percent_match)

            a, b = data[i], data[j]
            percent_match = self.compare_ordered(a, b)
            order_de_best_matches[i] = max(order_de_best_matches[i], percent_match)
            order_de_best_matches[j] = max(order_de_best_matches[j], percent_match)
        for score in best_matches:
            category = self.categorize(score)
            order_inde_matches[category] += 1

        for score in order_de_best_matches:
            category = self.categorize(score)
            order_de_matches[category] += 1
        return order_inde_matches, order_de_matches

    @staticmethod
    def categorize(score):
        if score == 100:
            return '100% match'
        elif score >= 70:
            return '>=70% match'
        elif score >= 50:
            return '>=50% match'
        elif score >= 30:
            return '>=30% match'
        else:
            return '<30% match'

    def get_percentiles_per_type(self, data: dict) -> dict:
        """
        Get percentiles from the given data
        Args:
            data:

        Returns:
            P25, P50, P75, and P90 percentiles
        """
        percentiles = {}
        for type in data:
            if len(data[type]) > 0:
                percentiles[type] = self.get_percentiles(data[type])
        return percentiles

    @staticmethod
    def get_percentiles(data: List[float]) -> dict:
        """
        Get percentiles from the given data
        Args:
            data:

        Returns:
            P25, P50, P75, and P90 percentiles
        """
        if len(data) == 0:
            return {}
        percentiles = np.percentile(data, [25, 50, 75, 90])
        return {"P25": percentiles[0],
                "P50": percentiles[1],
                "P75": percentiles[2],
                "P90": percentiles[3]}

    @staticmethod
    def get_summary_stats(data: List[float]) -> dict:
        if not data:
            return {'mean': 0.0, 'min': 0.0, 'max': 0.0, 'p25': 0.0, 'p50': 0.0, 'p75': 0.0, 'p90': 0.0}

        percentiles = np.percentile(data, [25, 50, 75, 90])
        return {
            'mean': float(np.mean(data)),
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'p25': float(percentiles[0]),
            'p50': float(percentiles[1]),
            'p75': float(percentiles[2]),
            'p90': float(percentiles[3]),
        }

    @staticmethod
    def get_percentage_dict(count_dict: dict[str, int]) -> dict[str, float]:
        total = sum(count_dict.values())
        if total == 0:
            return {key : 0.0 for key in count_dict}
        return {key: (value / total) for key, value in count_dict.items()}

    @staticmethod
    def get_distribution_percentage(elements: list) -> dict:
        counts = Counter(elements)
        total_elements = len(elements)
        percentages = {element: (count / total_elements) * 100 for element, count in counts.items()}
        return percentages

    def multiple_thin_box_plot(self, list_of_dicts: list, filename: str, figure_names:List[str]=[],
                               box_plot_types=constants.BOX_PLOT_TYPES,
                               is_scale=True) -> None:
        # Step 1: Collect all cleaned values to determine global y-limit
        all_cleaned_values = []
        for d in list_of_dicts:
            for key in box_plot_types:
                if key in d:
                    if is_scale:
                        cleaned = self.remove_outliers_iqr(np.asarray(d[key]))
                    else:
                        cleaned = d[key]
                    all_cleaned_values.extend(cleaned)

        # Use percentile range to cap (exclude extremes)
        if is_scale:
            y_min, y_max = np.percentile(all_cleaned_values, [5, 95])  #
        else:
            y_min = min(all_cleaned_values)
            y_max = max(all_cleaned_values)
        y_min = 0
        # Setup subplots side by side
        n_plots = len(list_of_dicts)
        ncols = math.ceil(n_plots)
        fig, axes = plt.subplots(1, ncols, figsize=(ncols*1.5, 4), sharey=True)

        # Flatten axes for easy looping
        axes = axes.flatten()

        # Define pastel colors
        pastel_colors = list(mcolors.TABLEAU_COLORS.values())
        # Subplot labels like (a), (b), ...
        if len(figure_names) == len(list_of_dicts):
            subplot_labels = [fig.replace(' ', '\n').replace('_', ' ') for fig in figure_names]
        else:
            subplot_labels = ['('+a+')' for a in list(string.ascii_lowercase)]
        # Loop through each dictionary and subplot
        for i, (data_dict, ax) in enumerate(zip(list_of_dicts, axes)):
            # Clean and filter data
            filtered_dict = {k: data_dict[k] for k in box_plot_types if k in data_dict}
            cleaned_data_dict = {k: self.remove_outliers_iqr(np.asarray(v)) for k, v in filtered_dict.items()}
            data = list(cleaned_data_dict.values())
            positions = np.arange(1, len(data) + 1) * 0.5

            # Create boxplot on this axis
            box = ax.boxplot(data, widths=0.2, patch_artist=True, showmeans=False, positions=positions)

            # Apply color and red median
            for patch, color in zip(box['boxes'], pastel_colors):
                patch.set_facecolor(color)
            for median in box['medians']:
                median.set(color='black', linewidth=4)

            # Set labels and title
            ax.set_xticks(positions)
            ax.set_xticklabels([str(j + 1) for j in range(len(data))])
            # Label each subplot BELOW with (a), (b), ...
            ax.set_xlabel(f"{subplot_labels[i]}", fontsize=10)
            ax.set_ylim(y_min, y_max)  # Cap y-axis
            ax.grid(True, axis='y')
        # plt.yticks(fontsize=6)
        plt.tight_layout()
        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')
        plt.close()


    def upset_diagram(self, dictionary: dict, filename: str) -> None:
        if '' in dictionary:
            del dictionary['']
        set_names = list(dictionary.keys())

        # Build a mapping from item to which sets it appears in
        item_to_sets = {}
        for set_index, items in enumerate(list(dictionary.values())):
            for item in items:
                item_to_sets.setdefault(item, set()).add(set_names[set_index])

        # Create membership data
        memberships = list(item_to_sets.values())
        data = from_memberships(memberships)

        # 4. Plot using only relevant sets
        plt.figure(figsize=(10, 6))
        plt.rcParams["font.size"] = 12
        upset = UpSet(
            data,
            subset_size='count',
            show_counts=True,
            sort_by='cardinality',
            # orientation='horizontal',
            intersection_plot_elements=10
        )
        # upset = UpSet(data, subset_size='count', show_counts=True)
        upset.plot()

        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')
        plt.close()

    def thin_box_plot(self, input_data: dict, filename: str):
        filtered_dict = {k: input_data[k] for k in constants.BOX_PLOT_TYPES if k in input_data}
        cleaned_data_dict = {k: self.remove_outliers_iqr(np.asarray(v)) for k, v in filtered_dict.items()}
        data = list(cleaned_data_dict.values())

        # Define pastel colors (using Tableau palette)
        pastel_colors = list(mcolors.TABLEAU_COLORS.values())

        # Create the figure
        # Use closely spaced custom positions
        positions = np.arange(1, len(data) + 1) * 0.1  # e.g., [0.5, 1.0]

        # Create the plot
        plt.figure(figsize=(2, 2))
        box = plt.boxplot(data, widths=0.05, patch_artist=True, showmeans=False, positions=positions)

        # Color the boxes
        for patch, color in zip(box['boxes'], pastel_colors):
            patch.set_facecolor(color)

        # Highlight medians in red
        for median in box['medians']:
            median.set(color='red', linewidth=2)

        # Correctly aligned x-axis labels
        plt.xticks(ticks=positions, labels=[str(i + 1) for i in range(len(data))], fontsize=8)
        plt.yticks(fontsize=6)
        # Add grid and title
        # Save as PDF
        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')
        plt.close()

    def get_distribution_figures(self, elements: list, xlabel: str, ylabel: str, title: str, filename: str) -> None:
        # Plotting the bar chart
        plt.figure(figsize=(8, 6))
        distribution = self.get_distribution_percentage(elements)
        percentages = list(distribution.values())
        bars = plt.bar(list(distribution.keys()), percentages, color='#4589ff')
        if len(list(distribution.keys())) > 5 or any(len(label) > 10 for label in list(distribution.keys())):
            fontsize = 3.5  # Smaller font
        else:
            fontsize = 12  # Default
        # Adding percentage labels on each bar
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2, yval + 1, f'{yval:.2f}%', ha='center', va='bottom')

        # Axis labels and title
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.xticks(fontsize=fontsize)
        # Grid and limits to mimic MATLAB style
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.ylim(0, max(percentages) + 10)

        # Save as PDF
        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')

        plt.close()

    @staticmethod
    def __inlier_mask(arr):
        """
        Outliers are removed per pair of variables with the IQR rule
        (value < Q1 – 1.5·IQR or value > Q3 + 1.5·IQR).
        Args:
            arr:

        Returns:

        """
        q1, q3 = np.percentile(arr, [20, 75])
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        return (arr >= low) & (arr <= high)

    def hex_bin(self, x, y, xlab, ylab, filename):
        plt.figure(figsize=(14, 8))

        # Hex-bin density
        hb = plt.hexbin(
            x, y,
            gridsize=30,  # bigger → coarser; smaller → finer
            cmap="Reds",
            mincnt=1  # only colour hexes that have ≥1 point
        )

        # Optional colour bar to show counts
        cb = plt.colorbar(hb)
        # cb.set_label("Count per hex")

        # (Optional) overlay the raw points for context
        plt.scatter(x, y, color="black", alpha=0.4, s=12)

        # plt.xlim(1, 2)
        plt.xlabel(xlab)
        plt.ylabel(ylab)
        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')
        plt.close()

    def heat_map(self, x, y, xlab, ylab, filename):
        plt.figure(figsize=(14, 8))
        sns.kdeplot(
            x=x,
            y=y,
            fill=True,
            cmap="Reds",
            thresh=1,
            levels=100
        )
        plt.scatter(x, y, color="black", alpha=0.4)
        plt.xlim(1, 2)
        plt.xlabel(xlab)
        plt.ylabel(ylab)
        plt.grid(True)
        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')
        plt.close()

    def scatter_plot(self, x, y, xlab, ylab, filename):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        mask = self.__inlier_mask(x) & self.__inlier_mask(y)
        x, y = x[mask], y[mask]

        plt.figure(figsize=(6, 5))
        plt.scatter(x, y, s=60, alpha=1, color="#0043ce", edgecolor="black")
        if len(x) >= 2 and np.std(x) > 0 and np.std(y) > 0:
            slope, intercept = np.polyfit(x, y, deg=1)
            x_line = np.linspace(x.min(), x.max(), 100)
            y_line = slope * x_line + intercept
            plt.plot(x_line, y_line, color="#da1e28", linewidth=2, label="Trend")

            # Pearson correlation
            r = np.corrcoef(x, y)[0, 1]

        # plt.hist2d(x, y)
        plt.xlabel(xlab)
        plt.ylabel(ylab)
        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')
        plt.close()

    @staticmethod
    def __normalize(arr):
        return (arr - arr.min()) / (arr.max() - arr.min())

    @staticmethod
    def remove_outliers_iqr(arr, k=1.5):
        """
        Return `arr` with outliers (beyond k×IQR from Q1/Q3) removed.
        """
        if len(arr) < 2:
            return arr

        q1, q3 = np.percentile(arr, [0, 75])
        iqr = q3 - q1
        lo, hi = q1 - k * iqr, q3 + k * iqr
        return arr[(arr >= lo) & (arr <= hi)]

    def get_box_plot(self, elements: list, labels: List[str], title: str, filename: str) -> None:
        if not elements:
            RichLog.error(f'No elements found to crea {title}')
            return None

        fig, ax = plt.subplots(figsize=(3, 6))
        cleaned = self.remove_outliers_iqr(np.asarray(elements))
        if len(cleaned) == 0:
            plt.close()
            return

        # Turn on patch_artist=True so the boxes are real Patch objects
        box = ax.boxplot(
            cleaned,
            labels=[""],
            patch_artist=True,  # <-- lets us fill with colour
            medianprops=dict(color="red", linewidth=1.5)
        )

        # Use either a Matplotlib colormap or your own hex colours
        pastel_cycle = itertools.cycle(Pastel1.colors)  # or your own list

        for patch in box["boxes"]:
            patch.set_facecolor(next(pastel_cycle))
            patch.set_alpha(0.9)  # a touch of transparency is optional
            patch.set_linewidth(1)

        # Optional: soften the whisker & cap colours too
        for whisker in box["whiskers"]:
            whisker.set_color("grey")
        for cap in box["caps"]:
            cap.set_color("grey")

        # ------------------------------------------------------------
        # Title, grid, save
        # ------------------------------------------------------------
        # ax.set_title(title)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        plt.savefig(self.filepath.joinpath(filename + '.pdf'), format='pdf', bbox_inches='tight')
        plt.close()


@dataclass(order=True)  # Comparable by fields in order of placement
class AnalysisMetric:
    sort_index: int | float
    value: float | int = field(compare=False)
    metric: str = field(compare=False)
    method_signature: str | None = field(compare=False)
    qualified_class_name: str | None = field(compare=False)
    project_name: str | None = field(compare=False)


class TopK:
    def __init__(self, k: int, metric: str, keep_largest: bool = True):
        """
        A custom heap that can be used to store outliers in a linear scan.
        Args:
            k: The k number of outliers to keep.
            keep_largest: A boolean describing whether we want to store the large outliers or the small outliers.
        """
        self.k = k
        self.metric = metric
        self.keep_largest = keep_largest
        self._heap: List[AnalysisMetric] = []  # Using a min-heap to store top k

    def add(self, value: float | int, method_signature: str | None = None, qualified_class_name: str | None = None,
            project_name: str | None = None) -> None:
        sort_index = value if self.keep_largest else -value
        # If keep_largest, then min_heap[0] is smallest value in heap
        # If not keep_largest, then min_heap[0] is largest value (stored as large neg) in heap

        analysis_metric = AnalysisMetric(sort_index, value, self.metric, method_signature, qualified_class_name,
                                         project_name)
        if len(self._heap) < self.k:
            heapq.heappush(self._heap, analysis_metric)
        else:
            # Compare against the "worst" value in heap
            if analysis_metric.sort_index > self._heap[0].sort_index:
                heapq.heapreplace(self._heap, analysis_metric)

    def top_k(self) -> List[AnalysisMetric]:
        """Returns top_k in sorted order.  Descending if largest, ascending if smallest."""
        return sorted(
            self._heap,
            key=lambda analysis_metric: analysis_metric.value,
            reverse=self.keep_largest
        )

    def top_k_serialized(self) -> List[Dict[str, Any]]:
        """Returns top_k in sorted order.  Descending if largest, ascending if smallest."""
        sorted_analysis_metrics: List[AnalysisMetric] = self.top_k()
        serialized_analysis_metrics: List[Dict[str, Any]] = [asdict(analysis_metric) for
                                                             analysis_metric in sorted_analysis_metrics]
        return serialized_analysis_metrics
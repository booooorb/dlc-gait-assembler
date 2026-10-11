"""Render cohort figures from calculated PCA and grouped-classification results."""


def render_run_pca(context, output_folder):
    import matplotlib
    import numpy as np

    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt

    data = context["data"]
    score_frame = context["score_frame"]
    component_count = context["component_count"]
    (figure, axis) = plt.subplots(figsize=(7.5, 5.5))
    if component_count >= 2:
        for group, group_frame in score_frame.groupby("group"):
            axis.scatter(group_frame["PC1"], group_frame["PC2"], label=str(group), alpha=0.82)
        axis.set_ylabel(f"PC2 ({context['variance_ratio'][1] * 100:.1f}%)")
    else:
        axis.scatter(score_frame["PC1"], np.zeros(len(score_frame)), alpha=0.82)
        axis.set_ylabel("")
    axis.set_xlabel(f"PC1 ({context['variance_ratio'][0] * 100:.1f}%)")
    axis.set_title("Animal-session PCA")
    if data["group"].nunique() > 1:
        axis.legend(frameon=False)
    figure.tight_layout()
    cluster_path = output_folder / "PCA_clusters.svg"
    figure.savefig(cluster_path, format="svg")
    plt.close(figure)
    (figure, axis) = plt.subplots(figsize=(7.5, 4.5))
    axis.plot(range(1, component_count + 1), np.cumsum(context["variance_ratio"]), marker="o")
    axis.set_ylim(0, 1.05)
    axis.set_xlabel("Number of components")
    axis.set_ylabel("Cumulative explained variance")
    axis.set_title("PCA scree summary")
    figure.tight_layout()
    scree_path = output_folder / "PCA_scree_plot.svg"
    figure.savefig(scree_path, format="svg")
    plt.close(figure)
    return (cluster_path, scree_path)


def render_run_grouped_random_forest(context, output_folder):
    import matplotlib

    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay

    y = context["y"]
    predictions = context["predictions"]
    accuracy = context["accuracy"]
    (figure, axis) = plt.subplots(figsize=(6.5, 5.5))
    ConfusionMatrixDisplay.from_predictions(y, predictions, ax=axis, cmap="Blues")
    axis.set_title(f"Animal-grouped Random Forest (accuracy {accuracy:.3f})")
    figure.tight_layout()
    confusion_path = output_folder / f"random_forest_confusion_acc_{accuracy:.3f}.svg"
    figure.savefig(confusion_path, format="svg")
    plt.close(figure)
    return (confusion_path,)

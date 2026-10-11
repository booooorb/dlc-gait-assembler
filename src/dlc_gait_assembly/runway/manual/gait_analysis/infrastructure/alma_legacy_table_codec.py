"""Preserve ALMA's established table headers, column order, and output serialization."""

from __future__ import annotations

import os

import pandas as pd


def read_file(file):
    pd_dataframe = pd.read_csv(file, header=[1, 2])
    filename = file.split("/")[-1]
    return (pd_dataframe, filename)


def make_parameters_output(pathname, parameters):
    parameters.to_csv(pathname)


def make_averaged_output(pathname, truncated=False):
    files = []
    for file in os.listdir(pathname):
        if truncated:
            if file.endswith(".csv") and file.startswith("continuous_strides_parameters_"):
                files.append(file)
        elif file.endswith(".csv") and file.startswith("parameters_"):
            files.append(file)
    dfs = []
    for file in files:
        if truncated:
            input_name = file.split("continuous_strides_parameters_")[1].split(".")[0]
        else:
            input_name = file.split("parameters_")[1].split(".")[0]
        path = os.path.join(pathname, file)
        df = pd.read_csv(path)
        df["id"] = input_name
        dfs.append(df)
    res = pd.concat(dfs).groupby("id").agg(["mean", "std"])
    res = res.drop(["Unnamed: 0", "stride_start (frame)", "stride_end (frame)"], axis=1, errors="ignore")
    if truncated:
        res.to_csv(os.path.join(pathname, "averaged_truncated_results.csv"))
    else:
        res.to_csv(os.path.join(pathname, "averaged_results.csv"))

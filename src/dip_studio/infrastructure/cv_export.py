"""Versioned trajectory export."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable

from dip_studio.domain.cv_model import Trajectory


def trajectories_to_json(trajectories: Iterable[Trajectory], *, version: int) -> str:
    if version <= 0:
        raise ValueError("Export version must be positive")
    return json.dumps(
        {
            "format": "dip-studio-trajectories",
            "version": version,
            "trajectories": [trajectory.to_json_dict() for trajectory in trajectories],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def trajectories_to_csv(trajectories: Iterable[Trajectory], *, version: int) -> str:
    if version <= 0:
        raise ValueError("Export version must be positive")
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["format", "dip-studio-trajectories", "version", version])
    for trajectory in trajectories:
        for row in trajectory.to_csv_rows()[1:]:
            writer.writerow(row)
    return output.getvalue()

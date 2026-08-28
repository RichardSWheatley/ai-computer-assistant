"""Projects: hand a task to RITA — an AI may plan it, only RITA executes.

The plan is data: items phrased in RITA's own command grammar, validated
deterministically by routing each one, persisted in ~/.rita, executed by
the orchestrator through the full gate pipeline.
"""

from .model import Project, ProjectItem, ProjectStore
from .planner import PlanError, plan_project, quick_plan
from .runner import ProjectResult, run_project

__all__ = ["Project", "ProjectItem", "ProjectStore", "PlanError",
           "plan_project", "quick_plan", "ProjectResult", "run_project"]

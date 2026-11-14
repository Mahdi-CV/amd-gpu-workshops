"""Deployment compatibility module for the Rules to Reasoning workshop.

The participant notebook intentionally defines its three small HTTP helpers
directly:

    preview_route(prompt)
    send_prompt(prompt)
    apply_recipe(recipe)

This file keeps the established workshop deployment contract intact without
reintroducing the old participant-facing ``WorkshopLab`` abstraction.
"""

from pathlib import Path


WORKSHOP_NAME = "From Rules to Reasoning"
NOTEBOOK_NAME = "route-one-agent-across-two-models-v3.ipynb"
NOTEBOOK_PATH = Path(__file__).resolve().with_name(NOTEBOOK_NAME)


def workshop_info() -> dict[str, str]:
    """Return the deployment-visible workshop identity."""
    return {
        "name": WORKSHOP_NAME,
        "notebook": str(NOTEBOOK_PATH),
        "participant_api": (
            "preview_route(prompt), send_prompt(prompt), apply_recipe(recipe)"
        ),
    }

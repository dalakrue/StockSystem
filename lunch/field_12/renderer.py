from __future__ import annotations


def render(view_model) -> None:
    context = view_model["context"]
    from ui.lunch_field12_higher_regime_rank import render_field12
    render_field12(context.history_repository.state)

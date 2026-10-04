"""Dispatch explicit implementations; never substitute an unknown experiment family."""

from . import astrosat_experiments, percolation_experiments
from .astrosat_experiments import ASTROSAT_RECIPES as ASTROSAT_RECIPES
from .astrosat_experiments import astrosat_baseline as astrosat_baseline
from .astrosat_experiments import transit_batch as transit_batch
from .astrosat_experiments import transit_geometry as transit_geometry
from .scientific_statistics import seed_for as seed_for

IMPLEMENTATIONS = {
    "astrosat": astrosat_experiments,
    "percolation": percolation_experiments,
}
MEASUREMENT_CONTRACTS = {
    name: module.MEASUREMENT_CONTRACT for name, module in IMPLEMENTATIONS.items()
}


def implementation(domain):
    if domain not in IMPLEMENTATIONS:
        raise ValueError("No implementation for this paper's scientific context")
    return IMPLEMENTATIONS[domain]


def batch_cost(domain, trials, sizes):
    return implementation(domain).batch_cost(trials, sizes)


def execute_batch(domain, recipe, sizes, trials, seed, budget, on_row=None):
    return implementation(domain).execute_batch(recipe, sizes, trials, seed, budget, on_row)


def summarize_branch(domain, rows, config, batches):
    return implementation(domain).summarize_branch(rows, config, batches)


def audit_statistics(domain, rows, config):
    return implementation(domain).audit_statistics(rows, config)

"""Repository provenance, generated-code handoffs, and real sandbox probes."""

import hashlib
import io
import os
import stat
import sys
import threading
import zipfile

import pytest

from hacknation_databricks.research.artifacts import RunStore, verify_artifacts
from hacknation_databricks.research.code_sandbox import execute_code, run_bounded
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.repository_models import RepositoryImplementation
from hacknation_databricks.research.repository_source import (
    github_repository,
    repository_links,
    unpack_snapshot,
)
from hacknation_databricks.research.repository_workflow import run_repository
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import load_journal

KERNEL = "def advance(value, rate):\n    return value * rate\n"
DRIVER = """from kernel import advance
def simulate(parameters, seed, library):
    value = 1.0
    values = [value]
    for _ in range(3):
        value = advance(value, parameters['rate'])
        values.append(value)
    return {'metric': value, 'times': [0., 1., 2., 3.], 'values': values}
"""


def fixture_repository(source, url, ref, store):
    path = store.write_text("repository/source/kernel.py", KERNEL)
    manifest = {
        "url": url,
        "commit": "a" * 40,
        "source_sha256": source.sha256,
        "origin": "user_supplied",
        "files": [
            {
                "path": "kernel.py",
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ],
    }
    store.write("repository/manifest.json", manifest)
    return manifest


def evidence():
    return {
        "source_id": "seed",
        "page": 1,
        "quote": "Compare decay rates with a reproducible numerical model.",
    }


class RepositoryRoles:
    def __init__(self, sources, store, config):
        self.calls = 0
        self.store = store

    def close(self):
        pass

    def ask(self, role, payload, contract):
        self.calls += 1
        direction = {
            "id": "decay",
            "title": "Compare decay rates",
            "hypothesis": "Faster decay reduces the final state.",
            "origin": "agent_hypothesis",
            "evidence": [evidence()],
        }
        if role == "repository_reader":
            raw = {
                "research_question": "How does decay affect the final state?",
                "directions": [direction],
                "repository_fit": "A small numerical decay kernel is supplied.",
                "version_limitations": ["Test fixture"],
                "repository_files": ["kernel.py"],
            }
        elif role == "repository_literature":
            raw = {
                "literature_assessment": "Only the supplied source was reviewed.",
                "search_scope": "Supplied source only; no external search.",
                "evidence": [evidence()],
                "missing_evidence": ["Independent comparison"],
            }
        elif role == "repository_critic":
            raw = {
                "critiques": [
                    {
                        "proposal_id": "decay",
                        "decision": "accept",
                        "rationale": "The kernel supports a falsifiable paired test.",
                        "risks": ["Simplified model"],
                    }
                ],
                "selected_proposal_id": "decay",
                "literature_assessment": "Only the supplied source was reviewed.",
                "search_scope": "Supplied source only; no external search.",
                "evidence": [evidence()],
                "missing_evidence": ["Independent comparison"],
            }
        elif role == "repository_planner":
            raw = {
                "proposal_id": "decay",
                "hypothesis": direction["hypothesis"],
                "tests": [
                    {
                        "id": name,
                        "replicates": n,
                        "expected_learning": "Estimate the change in the final state.",
                        "feasibility": "Small deterministic numerical model.",
                    }
                    for name, n in [("screen", 4), ("precision", 8)]
                ],
                "selected_test_id": "screen",
                "rationale": "Screening is sufficient for a deterministic test.",
                "primary_module": "kernel",
                "dependencies": ["kernel"],
                "metric": "Final state",
                "units": "units",
                "metric_lower": 0.0,
                "metric_upper": 2.0,
                "baseline": {"rate": 1.0},
                "treatment": {"rate": 0.9},
                "sanity": {"rate": 1.0},
                "sanity_expected": 1.0,
                "sanity_tolerance": 0.0,
                "baseline_scope": "Analytical no-decay consistency check.",
                "controls": "Same seed and initial state for both arms.",
                "meaningful_difference": 0.1,
                "limitations": ["Test fixture only"],
            }
        elif role == "repository_experimenter":
            raw = {
                "python_code": DRIVER,
                "c_code": "",
                "c_repository_files": [],
                "explanation": "Call the supplied repository kernel at each time step.",
                "repository_files": ["kernel.py"],
            }
        else:
            first = len(payload["prior_results"]) == 1
            raw = {
                "action": "followup" if first else "stop",
                "result_interpretation": "The measured rate change reduced the final state.",
                "rationale": "Measure a stronger decay to check the parameter response."
                if first
                else "The second test confirms the expected response.",
                "next_experiment": "Test a stronger decay rate using the same baseline.",
                "next_treatment": {"rate": 0.8} if first else None,
                "limitations": ["Synthetic fixture"],
            }
        return contract.model_validate(raw)


def fixture_execute(store, implementation, manifest, jobs, *, stage, timeout):
    # Trusted fixture only: no generated code is executed in this path.
    trials = [
        {
            **j,
            "output": {
                "metric": j["parameters"]["rate"] ** 3,
                "times": [0.0, 1.0, 2.0, 3.0],
                "values": [j["parameters"]["rate"] ** i for i in range(4)],
            },
        }
        for j in jobs
    ]
    result = {"trials": trials, "repository_calls": ["kernel.py"], "compiled_library_loaded": False}
    store.write(stage + "/trials.json", result)
    store.write(
        stage + "/execution.json",
        {
            "returncode": 0,
            "failure": None,
            "backend": "fixture",
            "repository_commit": manifest["commit"],
            "source_sha256": manifest["source_sha256"],
            "jobs": jobs,
        },
    )
    return result


def make_repository_run(tmp_path, **kwargs):
    paper = tmp_path / "paper.md"
    paper.write_text("Compare decay rates with a reproducible numerical model.")
    source = read_source(paper)
    config = RunConfig(
        workflow="repository", repository_url="https://github.com/example/science", max_rounds=2
    )
    output = tmp_path / "run"
    report = run_repository(
        source,
        output,
        config,
        backend="fixture",
        roles_factory=kwargs.get("roles_factory", RepositoryRoles),
        repository_fetcher=fixture_repository,
        code_executor=kwargs.get("code_executor", fixture_execute),
    )
    return output, report


def test_repository_loop_changes_executed_parameters_and_seals_provenance(tmp_path):
    output, report = make_repository_run(tmp_path)
    assert report["status"] == "research_stopped"
    assert report["rounds"][0]["treatment"] == {"rate": 0.9}
    assert report["rounds"][1]["treatment"] == {"rate": 0.8}
    assert report["computed_simulations"] == 20
    assert not report["acceptance"]["live_agents_executed"]
    assert not verify_artifacts(output)
    journal = load_journal(output)
    assert journal.verified, journal.issues
    from hacknation_databricks.research.activity import load_activity

    assert len(load_activity(journal)) == 10


def test_independent_workers_overlap_and_critic_waits_for_both(tmp_path):
    import json

    barrier = threading.Barrier(2, timeout=5)

    class ConcurrentRoles(RepositoryRoles):
        def ask(self, role, payload, contract):
            if role in {"repository_reader", "repository_literature"}:
                barrier.wait()
            elif role == "repository_critic":
                assert payload["brief"]["directions"]
                assert payload["independent_literature_review"]["evidence"]
            return super().ask(role, payload, contract)

    output, report = make_repository_run(tmp_path, roles_factory=ConcurrentRoles)
    assert report["status"] == "research_stopped", report
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    stages = [(e["event"], e["data"]) for e in events if e["event"].startswith("stage_")]
    starts = {d["stage"]: i for i, (kind, d) in enumerate(stages) if kind == "stage_started"}
    ends = {d["stage"]: i for i, (kind, d) in enumerate(stages) if kind == "stage_completed"}
    assert max(starts["reader"], starts["literature"]) < min(ends["reader"], ends["literature"])
    assert starts["critic"] > max(ends["reader"], ends["literature"])
    assert set(stages[starts["critic"]][1]["parents"]) == {"reader", "literature"}
    assert load_journal(output).verified


def test_failed_reader_joins_literature_before_sealing(tmp_path):
    class FailedReader(RepositoryRoles):
        def ask(self, role, payload, contract):
            if role == "repository_reader":
                raise RuntimeError("Rejected reader fixture")
            return super().ask(role, payload, contract)

    output, report = make_repository_run(tmp_path, roles_factory=FailedReader)
    assert report["status"] == "failed"
    assert (output / "approved_literature.json").is_file()
    assert not (output / "critic.json").exists()
    assert load_journal(output).verified


def test_process_provenance_ignores_parameter_dictionary_order(tmp_path):
    class UnsortedPlan(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_planner":
                for field in ["baseline", "treatment", "sanity"]:
                    setattr(value, field, {"z_offset": 0, **getattr(value, field)})
            if role == "repository_evaluator" and value.next_treatment:
                value.next_treatment = {"z_offset": 0, **value.next_treatment}
            return value

    output, report = make_repository_run(tmp_path, roles_factory=UnsortedPlan)
    assert report["status"] == "research_stopped"
    assert not verify_artifacts(output)


def test_repository_failure_retains_partial_output(tmp_path):
    def failing(*args, **kwargs):
        raise RuntimeError("Fixture execution failure")

    output, report = make_repository_run(tmp_path, code_executor=failing)
    assert report["status"] == "failed"
    assert not report["rounds"]
    assert (output / "implementation.json").exists()
    assert not verify_artifacts(output)


def test_sanity_parameters_must_be_executable_not_inheritance_prose(tmp_path):
    import json

    from hacknation_databricks.research.repository_models import RepositoryPlan

    output, _ = make_repository_run(tmp_path)
    plan = json.loads((output / "planner.json").read_text())
    plan["sanity"] = {"configuration": "Use baseline, replacing rate with 1.0"}
    with pytest.raises(ValueError, match="complete parameter keys"):
        RepositoryPlan.model_validate(plan)


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_inexact_evidence_gets_one_recorded_repair(tmp_path, repair_succeeds):
    class InexactReader(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_reader" and ("repair" not in payload or not repair_succeeds):
                value.directions[0].evidence[0].quote = "A paraphrase absent from the paper."
            return value

    output, report = make_repository_run(tmp_path, roles_factory=InexactReader)
    assert (output / "reader_evidence_failure.json").is_file()
    assert (output / "reader_repair.json").is_file()
    assert not verify_artifacts(output)
    if repair_succeeds:
        assert report["status"] == "research_stopped"
        assert load_journal(output).verified
    else:
        assert report["status"] == "failed"
        assert report["role_calls"] == 3
        assert not report["rounds"]


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_structured_contract_gets_only_one_correction(tmp_path, repair_succeeds):
    class InvalidPlanner(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_planner" and (
                "contract_repair" not in payload or not repair_succeeds
            ):
                raw = value.model_dump()
                raw["dependencies"] = ["a source path is not a package name"]
                return contract.model_validate(raw)
            return value

    output, report = make_repository_run(tmp_path, roles_factory=InvalidPlanner)
    assert (output / "planner_contract_failure.json").is_file()
    assert not verify_artifacts(output)
    if repair_succeeds:
        assert report["status"] == "research_stopped"
        assert load_journal(output).verified
    else:
        assert report["status"] == "failed"
        assert report["role_calls"] == 5
        assert not report["rounds"]


@pytest.mark.parametrize("target", ["seed", "trajectory"])
def test_resealed_measurement_tampering_is_rejected(tmp_path, target):
    import json

    output, report = make_repository_run(tmp_path)
    name = "rounds/01/trials.json" if target == "seed" else "rounds/01/process.json"
    path = output / name
    data = json.loads(path.read_text())
    if target == "seed":
        data["trials"][0]["seed"] += 1
    else:
        data["process"]["original"]["geometry"][0]["y"] += 0.1
    path.write_text(json.dumps(data))
    # Simulate a re-sealed archive: hash validation alone must not accept it.
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"][name] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest))
    assert verify_artifacts(output)


def test_replay_uses_archived_program_and_no_models(tmp_path, monkeypatch):
    from hacknation_databricks.research import repository_replay

    output, report = make_repository_run(tmp_path)
    monkeypatch.setattr(repository_replay, "execute_code", fixture_execute)
    replay = repository_replay.replay_repository(output, tmp_path / "replay")
    assert replay["status"] == "matched"
    assert replay["new_model_calls"] == 0


def test_missing_repository_does_not_fall_back_to_preset(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("A scientific question with no repository link.")
    result = run_repository(
        read_source(path),
        tmp_path / "run",
        RunConfig(workflow="repository"),
        backend="fixture",
        roles_factory=RepositoryRoles,
    )
    assert result["status"] == "repository_required"
    assert result["computed_simulations"] == result["role_calls"] == 0


@pytest.mark.parametrize("name", ["root/../../outside", "/absolute/path", "root/symlink"])
def test_repository_archive_rejects_escapes(tmp_path, name):
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        info = zipfile.ZipInfo(name)
        if name.endswith("symlink"):
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "outside")
    with pytest.raises(ValueError):
        unpack_snapshot(body.getvalue(), tmp_path / "snapshot")


def test_repository_urls_are_public_github_and_paper_local(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("Code: https://github.com/example/science.")
    assert repository_links(read_source(path)) == {"https://github.com/example/science": 1}
    assert github_repository("https://github.com/example/science.git") == ("example", "science")
    for url in [
        "http://127.0.0.1/a/b",
        "https://github.com@evil.com/a/b",
        "https://github.com/a/../b",
    ]:
        with pytest.raises(ValueError):
            github_repository(url)


def test_timeout_and_output_limit_kill_child(tmp_path):
    result = run_bounded(
        [sys.executable, "-c", "while True: pass"], cwd=tmp_path, env={}, timeout=0.15
    )
    assert result["failure"] == "timeout"
    result = run_bounded(
        [sys.executable, "-c", "print('x'*100000)"],
        cwd=tmp_path,
        env={},
        timeout=2,
        output_limit=1000,
    )
    assert result["failure"] == "output_limit"


@pytest.mark.skipif(
    os.environ.get("RUN_SANDBOX_TESTS") != "1",
    reason="Real OS sandbox needs a host that permits sandbox activation",
)
@pytest.mark.parametrize("language", ["python", "c", "denials", "paper"])
def test_real_omnigent_sandbox(tmp_path, language, monkeypatch):
    monkeypatch.setenv("SANDBOX_TEST_SECRET", "harmless-env-canary")
    store = RunStore(tmp_path / "archive")
    paper = tmp_path / "paper.md"
    paper.write_text("A sandbox capability probe, not scientific evidence.")
    manifest = fixture_repository(
        read_source(paper), "https://github.com/example/science", "HEAD", store
    )
    implementation = RepositoryImplementation(
        python_code=DRIVER,
        explanation="Use the repository's numerical kernel.",
        repository_files=["kernel.py"],
    )
    if language == "paper":
        manifest = {
            "url": "",
            "commit": "",
            "files": [],
            "origin": "paper_implementation",
            "source_sha256": read_source(paper).sha256,
        }
        implementation = implementation.model_copy(
            update={
                "repository_files": [],
                "python_code": DRIVER.replace("from kernel import advance", KERNEL),
            }
        )
    if language == "c":
        c_source = "double advance(double value, double rate) { return value*rate; }\n"
        store.write_text("repository/source/kernel.c", c_source)
        manifest["files"].append(
            {
                "path": "kernel.c",
                "bytes": len(c_source),
                "sha256": hashlib.sha256(c_source.encode()).hexdigest(),
            }
        )
        implementation = implementation.model_copy(
            update={
                "python_code": """import ctypes
def simulate(parameters, seed, library):
    kernel = ctypes.CDLL(library)
    kernel.advance.argtypes = [ctypes.c_double, ctypes.c_double]
    kernel.advance.restype = ctypes.c_double
    return {'metric': kernel.advance(1.,parameters['rate']),
            'times': [0.,1.], 'values': [1.,parameters['rate']]}
""",
                "repository_files": ["kernel.c"],
                "c_repository_files": ["kernel.c"],
            }
        )
    if language == "denials":
        outside = tmp_path / "private-canary.txt"
        outside.write_text("harmless sandbox test marker")
        code = DRIVER.replace(
            "    value = 1.0",
            f"""    import os, socket
    assert 'SANDBOX_TEST_SECRET' not in os.environ
    try:
        open({str(outside)!r}).read()
    except PermissionError:
        pass
    else:
        raise AssertionError('outside read allowed')
    try:
        open({str(outside)!r}, 'w').write('changed')
    except PermissionError:
        pass
    else:
        raise AssertionError('outside write allowed')
    try:
        socket.socket().connect(('127.0.0.1', 6767))
    except PermissionError:
        pass
    else:
        raise AssertionError('network allowed')
    value = 1.0""",
        )
        implementation = implementation.model_copy(update={"python_code": code})
    result = execute_code(
        store,
        implementation,
        manifest,
        [{"arm": "control", "parameters": {"rate": 0.9}, "seed": 123}],
        stage="probe",
        timeout=20,
    )
    assert result["trials"][0]["output"]["metric"] == pytest.approx(
        0.9 if language == "c" else 0.9**3
    )


def test_repository_result_page_displays_recorded_simulation(tmp_path):
    from hacknation_databricks.repository_ui import render_repository_result
    from hacknation_databricks.web.components import Session, render

    output, _ = make_repository_run(tmp_path)
    view = render(Session(), lambda: render_repository_result(load_journal(output)))
    main = view["main"]
    assert main[0]["type"] == "iframe"
    assert sum(item["type"] == "iframe" for item in main) == 1
    assert any("Final state:" in item.get("value", "") for item in main)
    assert not any(item.get("label") == "Experiment" for item in main)
    assert any("Earlier experiments" in item.get("label", "") for item in main)


def test_constant_trajectories_remain_diagnostics_without_final_highlight(tmp_path):
    def flat_execute(store, *args, **kwargs):
        result = fixture_execute(store, *args, **kwargs)
        for trial in result["trials"]:
            trial["output"]["values"] = [trial["output"]["metric"]] * 4
        store.write(kwargs["stage"] + "/trials.json", result)
        return result

    output, report = make_repository_run(tmp_path, code_executor=flat_execute)
    assert report["status"] == "failed"
    assert "constant" in report["reason"]
    assert report["final_experiment"] is None
    assert not report["rounds"]
    assert (output / "rounds/01/trials.json").is_file()
    assert not (output / "comparison/process.json").exists()
    assert not load_journal(output).issues


def test_only_terminal_evaluated_result_is_featured(tmp_path):
    from hacknation_databricks.repository_ui import final_experiment

    _, report = make_repository_run(tmp_path)
    assert report["final_experiment"] == 2
    assert final_experiment(report)["round"] == 2
    for status in ("running", "failed", "interrupted", "blocked_live_backend"):
        assert final_experiment({**report, "status": status}) is None
    assert final_experiment({**report, "final_experiment": 1}) is None
    assert final_experiment({**report, "final_experiment": None}) is None


def test_latest_paper_attempt_wins_even_if_failed(tmp_path):
    import json

    from hacknation_databricks.tracking_ui import latest_runs_by_paper

    runs = []
    for name, paper, status in [
        ("fresh-failed", "paper-a", "failed"),
        ("other-paper", "paper-b", "research_stopped"),
        ("old-success", "paper-a", "research_stopped"),
    ]:
        path = tmp_path / name
        path.mkdir()
        (path / "sources.json").write_text(json.dumps([{"source_id": "seed", "sha256": paper}]))
        (path / "report.json").write_text(json.dumps({"status": status}))
        runs.append(path)
    assert latest_runs_by_paper(runs) == runs[:2]


def test_fixed_width_scientific_inputs_reach_agents_unchanged(tmp_path):
    from hacknation_databricks.research.models import Evidence

    path = tmp_path / "reference.md"
    tle = "1 25469U 98051C   09119.61415140 -.00000218  00000-0 -84793-4 0  4781"
    path.write_text("Reference orbital input:\n" + tle + "\n")
    source = read_source(path)
    assert tle in source.payload()["pages"][0]
    assert source.supports(Evidence(page=1, quote="Reference orbital input: " + tle))


def test_reader_repair_explicitly_identifies_allowed_evidence_sources(tmp_path):
    captured = []

    class SupportingCitation(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_reader":
                if "repair" not in payload:
                    value.directions[0].evidence[0].source_id = "literature_1"
                else:
                    captured.append(payload["allowed_evidence_source_ids"])
            return value

    _, report = make_repository_run(tmp_path, roles_factory=SupportingCitation)
    assert report["status"] == "research_stopped"
    assert captured == [["seed"]]


def test_trajectory_units_can_differ_from_summary_metric(tmp_path):
    import json

    class SeparateUnits(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_planner":
                value.trajectory_label = "Recorded state"
                value.trajectory_units = "state units"
            return value

    output, report = make_repository_run(tmp_path, roles_factory=SeparateUnits)
    assert report["status"] == "research_stopped"
    process = json.loads((output / "comparison/process.json").read_text())["process"]
    assert process["y_label"] == "state units"
    assert process["title"] == "Recorded state"
    assert not load_journal(output).issues


class PaperRoles(RepositoryRoles):
    def ask(self, role, payload, contract):
        value = super().ask(role, payload, contract)
        if role in {"repository_reader", "repository_experimenter"}:
            value.repository_files = []
        if role == "repository_experimenter":
            value.python_code = DRIVER.replace("from kernel import advance", KERNEL)
        return value


@pytest.mark.parametrize("paper_link", ["", "\nCode: https://github.com/example/science"])
def test_paper_only_loop_executes_all_roles_and_adapts_without_repository(tmp_path, paper_link):
    paper = tmp_path / "paper.md"
    paper.write_text(evidence()["quote"] + paper_link)
    output = tmp_path / "run"
    roles_seen = []

    class RecordingPaperRoles(PaperRoles):
        def ask(self, role, payload, contract):
            roles_seen.append(role)
            return super().ask(role, payload, contract)

    def no_repository(*args):
        pytest.fail("Paper-only experiment must not invent a repository")

    report = run_repository(
        read_source(paper),
        output,
        RunConfig(workflow="repository", allow_paper_implementation=True, max_rounds=2),
        backend="fixture",
        roles_factory=RecordingPaperRoles,
        repository_fetcher=no_repository,
        code_executor=fixture_execute,
    )
    assert report["status"] == "research_stopped", report
    assert report["code_origin"] == "paper_implementation"
    assert "repository" not in report
    assert set(roles_seen[:2]) == {"repository_reader", "repository_literature"}
    assert roles_seen[2:] == [
        "repository_critic",
        "repository_planner",
        "repository_experimenter",
        "repository_evaluator",
        "repository_evaluator",
    ]
    assert report["rounds"][1]["treatment"] == {"rate": 0.8}
    assert not verify_artifacts(output)
    assert load_journal(output).verified


def test_supplied_repository_failure_never_switches_to_paper_implementation(tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text(evidence()["quote"])

    def unavailable(*args):
        raise ValueError("Repository unavailable")

    report = run_repository(
        read_source(paper),
        tmp_path / "run",
        RunConfig(
            workflow="repository",
            allow_paper_implementation=True,
            repository_url="https://github.com/example/science",
        ),
        backend="fixture",
        roles_factory=PaperRoles,
        repository_fetcher=unavailable,
    )
    assert report["status"] == "failed"
    assert not report["rounds"]
    assert report["role_calls"] == 0

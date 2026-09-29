"""CLI 测试：四子命令分发 + run 的 retrieval_fallback 映射（monkeypatch build_components）。"""

from types import SimpleNamespace

from evoagent import cli
from evoagent.models import Skill
from evoagent.skills.registry import SkillRegistry
from evoagent.storage import Storage


def _make_skill(skill_id="code-review", version="1.0.0", status="active"):
    return Skill(
        skill_id=skill_id, name="Code Review", description="d", version=version,
        tags=[], prompt_template="处理 {task}", few_shots=[], tools=[], status=status,
        parent_version="", change_log="", metrics={}, created_at="", updated_at="",
    )


def test_main_list_end_to_end(tmp_path, capsys, monkeypatch):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    registry = SkillRegistry(storage, skills_dir=tmp_path / "skills")
    registry.register(_make_skill(skill_id="code-review", status="active"))

    monkeypatch.setattr(cli, "build_components", lambda db_path=None: SimpleNamespace(registry=registry))

    rc = cli.main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "code-review" in out


def test_main_run_maps_retrieval_fallback(monkeypatch, capsys):
    calls = {}

    def fake_retrieve_top1(task):
        return SimpleNamespace(skill=_make_skill(), score=0.5, fallback=True)

    def fake_executor_run(task, skill, *, retrieval_fallback=False):
        calls["retrieval_fallback"] = retrieval_fallback
        return SimpleNamespace(final_output="ok", status="success")

    components = SimpleNamespace(
        retriever=SimpleNamespace(retrieve_top1=fake_retrieve_top1),
        executor=SimpleNamespace(run=fake_executor_run),
    )
    monkeypatch.setattr(cli, "build_components", lambda db_path=None: components)

    rc = cli.main(["run", "some task"])
    assert rc == 0
    assert calls["retrieval_fallback"] is True  # fallback 正确映射


def test_main_evolve_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_tasks_by_name", lambda name: [object()])

    def fake_loop_run(tasks):
        assert len(tasks) == 1
        return [SimpleNamespace(reason="promoted", win_rate=0.6, sample_size=20)]

    components = SimpleNamespace(loop=SimpleNamespace(run=fake_loop_run))
    monkeypatch.setattr(cli, "build_components", lambda db_path=None: components)

    rc = cli.main(["evolve"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "promoted" in out


def test_main_bench_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_tasks_by_name", lambda name: [object()])
    calls = {}

    def fake_get_active(skill_id):
        calls["skill_id"] = skill_id
        return _make_skill()

    def fake_benchmark_run(tasks, skill):
        calls["tasks"] = tasks
        return SimpleNamespace(to_dict=lambda: {"ok": True})

    components = SimpleNamespace(
        registry=SimpleNamespace(get_active=fake_get_active),
        benchmark=SimpleNamespace(run=fake_benchmark_run),
    )
    monkeypatch.setattr(cli, "build_components", lambda db_path=None: components)

    rc = cli.main(["bench", "code-review"])
    out = capsys.readouterr().out
    assert rc == 0
    assert calls["skill_id"] == "code-review"
    assert "ok" in out


def test_main_bench_skill_not_found(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_tasks_by_name", lambda name: [object()])
    components = SimpleNamespace(
        registry=SimpleNamespace(get_active=lambda skill_id: None),
        benchmark=SimpleNamespace(),
    )
    monkeypatch.setattr(cli, "build_components", lambda db_path=None: components)

    rc = cli.main(["bench", "nope"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "skill not found" in out

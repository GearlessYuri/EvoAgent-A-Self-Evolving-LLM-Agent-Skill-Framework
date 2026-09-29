"""CLI 入口：run / evolve / bench / list 四子命令（§13）。薄层：argparse + 组装 + 分发。"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

from . import config
from .eval.benchmark import Benchmark, load_tasks_by_name
from .eval.evaluator import Evaluator
from .eval.experience import ExperienceExtractor
from .eval.store import EvalStore
from .evolution.evolver import SkillEvolver
from .evolution.loop import EvolutionLoop
from .evolution.validator import Validator
from .execution.executor import AgentExecutor
from .execution.trace import TraceStore
from .llm import LLMClient
from .models import Task
from .skills.registry import SkillRegistry
from .skills.retriever import SkillRetriever
from .storage import Storage


def build_components(db_path=None):
    """组合根：全量组装所有组件（`list` 子命令冗余但可接受）。"""
    storage = Storage(db_path if db_path else config.DB_PATH)
    storage.connect()
    storage.init_schema()

    registry = SkillRegistry(storage, skills_dir=config.SKILLS_DIR)
    trace_store = TraceStore(storage)
    eval_store = EvalStore(storage)
    llm = LLMClient()
    retriever = SkillRetriever(registry)
    executor = AgentExecutor(llm, trace_store)
    evaluator = Evaluator(llm, eval_store)
    extractor = ExperienceExtractor(llm)
    benchmark = Benchmark(executor, evaluator)
    evolver = SkillEvolver(llm)
    validator = Validator(benchmark, registry, eval_store)
    loop = EvolutionLoop(trace_store, eval_store, extractor, evolver, validator, registry)

    return SimpleNamespace(
        storage=storage, registry=registry, trace_store=trace_store, eval_store=eval_store,
        llm=llm, retriever=retriever, executor=executor, evaluator=evaluator,
        extractor=extractor, benchmark=benchmark, evolver=evolver, validator=validator, loop=loop,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evoagent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p_run = sub.add_parser("run")
    p_run.add_argument("task")
    sub.add_parser("evolve")
    p_bench = sub.add_parser("bench")
    p_bench.add_argument("skill_id")
    p_bench.add_argument("--set", default="regression", choices=["regression", "extension"])

    args = parser.parse_args(argv)
    c = build_components()

    if args.command == "list":
        for skill in c.registry.list():
            print(f"{skill.skill_id}\t{skill.version}\t{skill.status}\t{skill.name}")
        return 0

    if args.command == "run":
        task = Task(task=args.task, task_source="real")
        r = c.retriever.retrieve_top1(task)
        trace = c.executor.run(task, r.skill, retrieval_fallback=r.fallback)  # §3.4 裁定：映射 fallback
        print(trace.final_output)
        return 0 if trace.status == "success" else 1

    if args.command == "evolve":
        tasks = load_tasks_by_name("regression")
        for vr in c.loop.run(tasks):
            print(f"{vr.reason}\twin_rate={vr.win_rate:.3f}\tsample_size={vr.sample_size}")
        return 0

    if args.command == "bench":
        tasks = load_tasks_by_name(args.set)
        skill = c.registry.get_active(args.skill_id)
        if skill is None:
            print(f"skill not found: {args.skill_id}")
            return 1
        report = c.benchmark.run(tasks, skill)
        print(report.to_dict())
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""AgentExecutor 测试：mock LLMClient + tmp_path TraceStore，全程不发真实请求。"""

from evoagent.execution.executor import AgentExecutor
from evoagent.execution.trace import TraceStore
from evoagent.models import FewShot, Skill, Task
from evoagent.storage import Storage


def _make_trace_store(tmp_path):
    storage = Storage(tmp_path / "evo.db")
    storage.connect()
    storage.init_schema()
    return TraceStore(storage)


def _make_skill(**overrides):
    kwargs = dict(
        skill_id="code-review",
        name="Code Review",
        description="review code",
        version="1.0.0",
        tags=["code"],
        prompt_template="请审查：{task}",
        few_shots=[],
        tools=[],
        status="active",
        parent_version="",
        change_log="",
        metrics={},
        created_at="",
        updated_at="",
    )
    kwargs.update(overrides)
    return Skill(**kwargs)


class _FakeLLM:
    """暴露 complete_with_usage 的假 LLM，可设返回答案或抛异常。"""

    def __init__(self, answer="答案", error=None, usage=None):
        self.answer = answer
        self.error = error
        self.usage = usage if usage is not None else {
            "total_tokens": 10,
            "total_cost": 0.0,
            "total_latency_ms": 5,
        }
        self.prompts = []

    def complete_with_usage(self, prompt):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.answer, self.usage


def test_run_success(tmp_path):
    store = _make_trace_store(tmp_path)
    executor = AgentExecutor(llm=_FakeLLM(answer="OK"), trace_store=store)
    task = Task(task="写个函数", task_source="real")
    skill = _make_skill()

    trace = executor.run(task, skill)

    assert trace.status == "success"
    assert trace.error_type == ""
    assert trace.error == ""
    assert trace.final_output == "OK"
    assert trace.task_source == "real"
    assert trace.skill_id == "code-review"
    assert trace.skill_version == "1.0.0"
    assert trace.retrieval_fallback is False
    assert trace.usage["total_tokens"] == 10
    assert trace.usage["total_cost"] == 0.0
    assert trace.usage["total_latency_ms"] == 5
    assert trace.started_at and trace.ended_at
    assert [s.type for s in trace.steps] == ["llm_call", "final"]
    assert [s.step_index for s in trace.steps] == [0, 1]

    # 写后回读一致
    got = store.get(trace.trace_id)
    assert got is not None
    assert got.trace_id == trace.trace_id
    assert got.task_source == "real"
    assert got.skill_id == "code-review"
    assert got.skill_version == "1.0.0"
    assert got.final_output == "OK"
    assert got.status == "success"
    assert got.error_type == ""


def test_run_error_infra(tmp_path):
    store = _make_trace_store(tmp_path)
    executor = AgentExecutor(llm=_FakeLLM(error=RuntimeError("boom")), trace_store=store)

    trace = executor.run(Task(task="x", task_source="real"), _make_skill())

    assert trace.status == "error"
    assert trace.error_type == "infra"
    assert trace.error == "boom"
    assert trace.final_output == ""
    assert trace.usage is None
    assert [s.type for s in trace.steps] == ["llm_call"]
    assert [s.step_index for s in trace.steps] == [0]


def test_prompt_rendering(tmp_path):
    store = _make_trace_store(tmp_path)
    llm = _FakeLLM(answer="OK")
    executor = AgentExecutor(llm=llm, trace_store=store)
    skill = _make_skill(
        prompt_template="处理 {task} 与 {other} 字面 {brace}",
        few_shots=[FewShot("in1", "out1"), FewShot("in2", "out2")],
    )

    trace = executor.run(Task(task="任务X", task_source="real"), skill)
    prompt = trace.steps[0].content  # llm_call 步骤内容即渲染后的 prompt

    assert "任务X" in prompt  # {task} 被替换
    assert "{other}" in prompt  # 其它占位符字面保留
    assert "{brace}" in prompt  # 字面花括号保留
    assert "示例 1：" in prompt
    assert "示例 2：" in prompt
    assert "in1" in prompt and "out1" in prompt
    assert "in2" in prompt and "out2" in prompt


def test_retrieval_fallback_field(tmp_path):
    store = _make_trace_store(tmp_path)
    executor = AgentExecutor(llm=_FakeLLM(answer="OK"), trace_store=store)

    trace = executor.run(
        Task(task="x", task_source="real"), _make_skill(), retrieval_fallback=True
    )
    assert trace.retrieval_fallback is True

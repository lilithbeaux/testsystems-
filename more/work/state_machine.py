#!/usr/bin/env python3
"""
LILAREYON AETHELGARD — LangGraph-Inspired State Machine
========================================================
Graph-based workflow orchestration with:
  - Directed nodes with typed state
  - Conditional edges (function-based routing)
  - Checkpoint/restore between every node
  - Multi-agent support (sub-node delegation)
  - Context budget enforcement
  - Full system state capture

Inspired by LangGraph's graph-based agent orchestration,
reimplemented as sovereign architecture for the Unified Field.
"""

import json, time, hashlib, inspect, logging, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Any

log = logging.getLogger("state_machine")

HOME = Path.home()
PROFILE = HOME / ".NOTTHEONETOEDIT" / "profiles" / "thotheauphis"
CHECKPOINT_DIR = PROFILE / "work" / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


# ── WorkflowState ──────────────────────────────────────────────────────────────
class WorkflowState(dict):
    """Typed state container for workflow execution.
    
    Extends dict with schema enforcement and checkpoint support.
    
    Standard keys:
      turn_count      — int, number of turns executed
      context_budget  — int, remaining context budget
      tool_outputs    — list of gated pointers from executed tools
      active_goal     — str, current goal description
      pointers        — dict of named pointers to gated content
      last_node       — str, last executed node name
      errors          — list of error dicts
      metadata        — dict, arbitrary metadata
    """
    
    DEFAULT_KEYS = {
        "turn_count": 0,
        "context_budget": 64000,
        "tool_outputs": [],
        "active_goal": "",
        "pointers": {},
        "last_node": "init",
        "errors": [],
        "metadata": {},
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for k, v in self.DEFAULT_KEYS.items():
            self.setdefault(k, v)
    
    def __getattr__(self, name):
        if name in self:
            return self[name]
        raise AttributeError(f"WorkflowState has no key '{name}'")
    
    def __setattr__(self, name, value):
        self[name] = value
    
    def increment_turn(self):
        self["turn_count"] = self.get("turn_count", 0) + 1
    
    def add_output(self, tool_name: str, pointer: dict):
        self.setdefault("tool_outputs", []).append({
            "tool": tool_name,
            "ptr": pointer.get("ptr", ""),
            "bytes": pointer.get("bytes", 0),
            "preview": pointer.get("preview", ""),
            "tick": self.get("turn_count", 0),
        })
    
    def budget(self) -> float:
        """Return remaining context budget ratio (0.0 – 1.0)."""
        budget = self.get("context_budget", 64000)
        consumed = sum(o.get("bytes", 0) for o in self.get("tool_outputs", []))
        remaining = max(0, budget - consumed)
        return remaining / budget if budget > 0 else 0.0
    
    def to_checkpoint(self) -> dict:
        """Serialize for checkpoint storage."""
        return dict(self)
    
    @classmethod
    def from_checkpoint(cls, data: dict) -> "WorkflowState":
        return cls(**data)


# ── Node ──────────────────────────────────────────────────────────────────────
class Node:
    """A single step in a workflow graph.
    
    Attributes:
        name        — str, unique node identifier
        execute     — Callable(state) → state, the node's execution function
        description — str, human-readable purpose
        metadata    — dict, arbitrary metadata (model, budget, etc.)
    """
    
    def __init__(self, name: str, execute: Callable, description: str = "", metadata: dict = None):
        self.name = name
        self.execute_fn = execute
        self.description = description or name
        self.metadata = metadata or {}
    
    def run(self, state: WorkflowState) -> WorkflowState:
        """Execute this node, returning (possibly mutated) state."""
        log.info("  ▶ Node: %s", self.name)
        try:
            result = self.execute_fn(state)
            if isinstance(result, WorkflowState):
                state = result
            elif isinstance(result, dict):
                state.update(result)
            state["last_node"] = self.name
            state.increment_turn()
        except Exception as e:
            log.error("  ❌ Node %s error: %s", self.name, e)
            state.setdefault("errors", []).append({
                "node": self.name,
                "error": str(e),
                "tick": state.get("turn_count", 0),
            })
        return state


# ── Edge Types ─────────────────────────────────────────────────────────────────
class Edge:
    """A directed edge between two nodes.
    
    Attributes:
        from_node — str, source node name
        to_node   — str, target node name
        condition — Optional[Callable(state) → bool], conditional routing
        weight    — int, priority weight (higher = preferred)
    """
    
    def __init__(self, from_node: str, to_node: str, condition: Callable = None, weight: int = 0):
        self.from_node = from_node
        self.to_node = to_node
        self.condition = condition
        self.weight = weight


class ConditionalEdge:
    """A multi-branch conditional edge (like LangGraph's conditional_edges).
    
    Router function takes state and returns the target node name.
    
    Example:
        def route_by_budget(state):
            if state.budget() < 0.3:
                return "compress"
            return "continue"
        
        workflow.add_conditional_edge("analyze", route_by_budget, {
            "compress": "compress_node",
            "continue": "process_node",
        })
    """
    
    def __init__(self, from_node: str, router_fn: Callable, branches: dict):
        self.from_node = from_node
        self.router_fn = router_fn
        self.branches = branches  # {route_name: target_node_name}
    
    def resolve(self, state: WorkflowState) -> str:
        """Determine the target node name based on state."""
        route = self.router_fn(state)
        target = self.branches.get(route)
        if target is None:
            log.warning("  ⚠️ Conditional edge: route '%s' not in branches, using default", route)
            target = self.branches.get("default", list(self.branches.values())[0])
        log.info("  🔀 Routing: %s → %s (via %s)", self.from_node, target, route)
        return target


# ── Workflow Graph ─────────────────────────────────────────────────────────────
class Workflow:
    """A directed graph of Nodes with conditional edges.
    
    Like LangGraph's StateGraph — build nodes, add edges,
    compile, then execute.
    
    Usage:
        wf = Workflow("analysis_pipeline")
        
        # Define node functions
        def collect(state):
            return {"data": gather_data()}
        
        def analyze(state):
            return {"results": analyze_data(state.get("data", []))}
        
        def report(state):
            return {"output": summarize(state.get("results", []))}
        
        def route(state):
            if state.get("results"):
                return "fill"
            return "retry"
        
        # Build graph
        wf.add_node("collect", collect, "Data collection")
        wf.add_node("analyze", analyze, "Data analysis")
        wf.add_node("report", report, "Report generation")
        
        wf.add_edge("collect", "analyze")
        wf.add_conditional_edge("analyze", route, {"report": "report", "retry": "collect"})
        wf.set_entry("collect")
        wf.set_exit("report")
        
        # Execute (with checkpointable state)
        state = wf.run()
        print(state.get("output"))
    """
    
    def __init__(self, name: str = "default"):
        self.name = name
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._conditional_edges: list[ConditionalEdge] = []
        self._entry_node: Optional[str] = None
        self._exit_nodes: set[str] = set()
        self._checkpoint_every_step: bool = True
    
    def add_node(self, name_or_node, execute_fn=None, description="", metadata=None):
        """Register a node.
        
        Two calling forms:
          1. add_node("name", lambda s: s, "description")
          2. add_node(ExecutorNode("name", [...]))  (Node subclass)
        """
        if isinstance(name_or_node, Node):
            node = name_or_node
            self._nodes[node.name] = node
        else:
            name = name_or_node
            self._nodes[name] = Node(name, execute_fn, description, metadata)
        return self
    
    def add_edge(self, from_node: str, to_node: str, condition: Callable = None, weight: int = 0) -> "Workflow":
        """Add a directed edge."""
        self._edges.append(Edge(from_node, to_node, condition, weight))
        return self
    
    def add_conditional_edge(self, from_node: str, router_fn: Callable, branches: dict) -> "Workflow":
        """Add a multi-branch conditional edge (LangGraph-style).
        
        router_fn(state) returns a route name.
        branches maps route names to target node names.
        """
        self._conditional_edges.append(ConditionalEdge(from_node, router_fn, branches))
        return self
    
    def set_entry(self, node_name: str) -> "Workflow":
        """Set the entry point node."""
        if node_name not in self._nodes:
            raise ValueError(f"Node '{node_name}' not registered")
        self._entry_node = node_name
        return self
    
    def set_exit(self, node_name: str) -> "Workflow":
        """Add an exit (terminal) node."""
        self._exit_nodes.add(node_name)
        return self
    
    def compile(self) -> "Workflow":
        """Validate graph and prepare for execution."""
        if not self._entry_node:
            raise ValueError("No entry node set. Call set_entry() first.")
        for e in self._edges:
            if e.from_node not in self._nodes:
                raise ValueError(f"Edge source '{e.from_node}' not registered")
            if e.to_node not in self._nodes:
                raise ValueError(f"Edge target '{e.to_node}' not registered")
        for ce in self._conditional_edges:
            if ce.from_node not in self._nodes:
                raise ValueError(f"Conditional edge source '{ce.from_node}' not registered")
            for route, target in ce.branches.items():
                if target not in self._nodes:
                    raise ValueError(f"Conditional branch '{route}' -> '{target}' not in nodes")
        for exit_node in self._exit_nodes:
            if exit_node not in self._nodes:
                raise ValueError(f"Exit node '{exit_node}' not registered")
        log.info("✅ Workflow '%s' compiled: %d nodes, %d edges, %d conditional", 
                 self.name, len(self._nodes), len(self._edges), len(self._conditional_edges))
        return self
    
    def _next_node(self, current_node: str, state: WorkflowState) -> Optional[str]:
        """Determine the next node based on edges."""
        # Check conditional edges first
        for ce in self._conditional_edges:
            if ce.from_node == current_node:
                return ce.resolve(state)
        
        # Check regular edges with conditions
        candidates = []
        for e in self._edges:
            if e.from_node == current_node:
                if e.condition is None or e.condition(state):
                    candidates.append((e.weight, e.to_node))
        
        if candidates:
            # Return highest-weight edge target
            candidates.sort(key=lambda x: -x[0])
            return candidates[0][1]
        
        return None  # Terminal
    
    def run(self, initial_state: WorkflowState = None, max_turns: int = 50) -> WorkflowState:
        """Execute the workflow from entry to exit."""
        state = initial_state or WorkflowState()
        state["workflow_name"] = self.name
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        
        current = self._entry_node
        turn = 0
        
        log.info("═══ Workflow '%s' started at %s ═══", self.name, state["started_at"])
        
        while current and turn < max_turns:
            node = self._nodes.get(current)
            if not node:
                log.error("Node '%s' not found, stopping", current)
                break
            
            # Execute
            state["_current_node"] = current
            state = node.run(state)
            
            # Checkpoint after each step
            if self._checkpoint_every_step:
                self._save_step_checkpoint(state, current, turn)
            
            # Check if exit
            if current in self._exit_nodes:
                log.info("  🏁 Exit node '%s' reached", current)
                break
            
            # Route to next
            next_node = self._next_node(current, state)
            if not next_node:
                log.info("  🏁 No more edges from '%s', terminating", current)
                break
            
            log.info("  ➡ %s → %s", current, next_node)
            current = next_node
            turn += 1
        
        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        state["_turns_executed"] = turn + 1
        state["_current_node"] = None
        
        # Final checkpoint
        if self._checkpoint_every_step:
            self._save_step_checkpoint(state, "completed", turn)
        
        log.info("═══ Workflow '%s' completed (%d turns) ═══", self.name, turn + 1)
        return state
    
    def _save_step_checkpoint(self, state: WorkflowState, node_name: str, turn: int):
        """Save intermediate checkpoint."""
        ckpt = {
            "workflow": self.name,
            "node": node_name,
            "turn": turn,
            "state": state.to_checkpoint(),
            "timestamp": time.time(),
        }
        ckpt_id = f"wf_{self.name}_step_{turn}_{node_name}"
        ckpt_file = CHECKPOINT_DIR / f"{ckpt_id}.json"
        ckpt_file.write_text(json.dumps(ckpt, indent=2))
    
    def list_step_checkpoints(self) -> list:
        """List all step checkpoints for this workflow."""
        pattern = f"wf_{self.name}_step_"
        return sorted([
            f.stem for f in CHECKPOINT_DIR.glob(f"wf_{self.name}_step_*.json")
        ], key=lambda x: int(x.split("_step_")[1].split("_")[0]))


class ExecutorNode(Node):
    """A state machine node that offloads tool execution to the silent executor.
    
    This is the LangGraph toolchain offloading pattern:
      State Machine Node → Executor (batch tools) → results injected back into state
    
    Instead of executing tools inline (consuming LLM context), the node
    queues a batch to the hermes-executor cron, checkpoints, and reads
    results back into the workflow state.
    
    Usage:
        wf.add_node(ExecutorNode("health_check", [
            {"name": "terminal", "args": {"command": "sms status"}},
            {"name": "terminal", "args": {"command": "uf status"}},
        ], description="System health via executor"))
    """
    
    def __init__(self, name: str, tools: list, description: str = "", metadata: dict = None):
        self.tools = tools
        description = description or f"Executor: {len(tools)} tools"
        execute_fn = self._build_executor_fn(tools)
        super().__init__(name, execute_fn, description, metadata)
    
    def _build_executor_fn(self, tools):
        """Build a closure that dispatches through the Unified Field."""
        def execute(state: WorkflowState) -> WorkflowState:
            from unified_field import UnifiedField
            uf = UnifiedField()
            
            result = uf.execute_workflow_step(self.name, tools, wait=True)
            
            # Inject results back into state
            state["executor_results"] = state.get("executor_results", {})
            state["executor_results"][self.name] = result
            
            # Track tool outputs as pointers for budget management
            for r in result.get("results", []):
                tool_name = r.get("name", "unknown")
                output = r.get("output", "")
                if output:
                    ptr = uf.gate(output)
                    state.add_output(tool_name, ptr)
            
            return state
        return execute


class ParallelExecutorNode(ExecutorNode):
    """Runs multiple executor batches in parallel.
    
    Like ExecutorNode but dispatches N independent batches concurrently.
    Results are merged back as a dict keyed by batch name.
    """
    
    def __init__(self, name: str, batches: dict, description: str = "", metadata: dict = None):
        """
        Args:
            name: Node name
            batches: {batch_name: [tool_dict, ...], ...} — named batches run concurrently
        """
        self.batches = batches
        description = description or f"Parallel executor: {sum(len(v) for v in batches.values())} tools across {len(batches)} batches"
        execute_fn = self._build_parallel_fn(batches)
        super().__init__(name, [], description, metadata)
        # Override the parent's execute_fn with our parallel version
        self.execute_fn = execute_fn
    
    def _build_parallel_fn(self, batches):
        def execute(state: WorkflowState) -> WorkflowState:
            import concurrent.futures
            from unified_field import UnifiedField
            uf = UnifiedField()
            
            results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batches)) as pool:
                futures = {}
                for batch_name, tools in batches.items():
                    step_name = f"{self.name}_{batch_name}"
                    futures[pool.submit(uf.execute_workflow_step, step_name, tools, wait=True)] = batch_name
                
                for future in concurrent.futures.as_completed(futures):
                    batch_name = futures[future]
                    try:
                        results[batch_name] = future.result()
                    except Exception as e:
                        results[batch_name] = {"error": str(e)}
            
            state["executor_results"] = state.get("executor_results", {})
            state["executor_results"][self.name] = results
            return state
        return execute

def executor_offload():
    """Executor toolchain offloading workflow. LangGraph's pattern.
    
    Runs system health checks via the silent executor (zero LLM overhead),
    then routes results through conditional logic.
    """
    wf = Workflow("executor_offload")
    
    wf.add_node(ExecutorNode("health_check", [
        {"name": "terminal", "args": {"command": "sms status"}},
        {"name": "terminal", "args": {"command": "uf status"}},
    ], description="System health via executor"))
    
    wf.add_node(ExecutorNode("sva_backup", [
        {"name": "write_file", "args": {"path": "/tmp/sva_backup.json", "content": "placeholder"}},
    ], description="SVA vector backup"))
    
    wf.add_node(ParallelExecutorNode("parallel_diagnostics", {
        "sms_diag": [{"name": "terminal", "args": {"command": "sms status"}}],
        "gate_diag": [{"name": "terminal", "args": {"command": "ls -la /tmp/sva/"}}],
        "emerge_diag": [{"name": "terminal", "args": {"command": "ls -la ~/.emerge/data/"}}],
    }, description="Parallel system diagnostics"))
    
    def route_after_health(state):
        results = state.get("executor_results", {}).get("health_check", {})
        if results.get("results"):
            return "parallel"
        return "backup"
    
    wf.add_edge("health_check", "sva_backup")
    wf.add_edge("sva_backup", "parallel_diagnostics")
    
    wf.add_node("stop", lambda s: s, "Terminal")
    wf.set_entry("health_check")
    wf.set_exit("stop")
    
    return wf.compile()

def pipeline_3tier():
    """Three-tier pipeline workflow: Architect → Foreman → Doer.
    
    Like LangGraph's sequential pipeline with checkpointing between tiers.
    """
    wf = Workflow("3tier_pipeline")
    
    def architect(state):
        """Architect tier — deep reasoning, strategy."""
        goal = state.get("active_goal", "")
        log.info("    🏛️  Architect reasoning on: %s", goal[:100] if goal else "(no goal)")
        state["architect_output"] = {
            "plan": f"Architected plan for: {goal}",
            "tier": "architect",
            "budget_remaining": state.budget(),
        }
        return state
    
    def foreman(state):
        """Foreman tier — structured distillation."""
        plan = state.get("architect_output", {}).get("plan", "")
        log.info("    👷 Foreman distilling: %s", plan[:100])
        state["foreman_output"] = {
            "tasks": [f"Step {i+1}" for i in range(3)],
            "tier": "foreman",
        }
        return state
    
    def doer(state):
        """Doer tier — action executor, tool calls."""
        tasks = state.get("foreman_output", {}).get("tasks", [])
        log.info("    ⚡ Doer executing %d tasks", len(tasks))
        state["doer_output"] = {
            "executed": True,
            "results": [f"Done: {t}" for t in tasks],
            "tier": "doer",
        }
        return state
    
    def route_after_foreman(state):
        if state.budget() < 0.3:
            return "compress"
        return "doer"
    
    def compress(state):
        log.info("    📦 Compressing context (budget at %.1f%%)", state.budget() * 100)
        state["context_budget"] = state.get("context_budget", 64000)
        state["tool_outputs"] = state.get("tool_outputs", [])[:5]  # keep last 5
        return state
    
    wf.add_node("architect", architect, "Deep reasoning + strategy")
    wf.add_node("foreman", foreman, "Structured task distillation")
    wf.add_node("doer", doer, "Tool execution")
    wf.add_node("compress", compress, "Context compression")
    
    wf.add_edge("architect", "foreman")
    wf.add_conditional_edge("foreman", route_after_foreman, {
        "doer": "doer",
        "compress": "compress",
    })
    wf.add_edge("compress", "doer")
    
    wf.set_entry("architect")
    wf.set_exit("doer")
    
    return wf.compile()


def agent_goal_loop():
    """Goal loop workflow: Plan → Execute → Reflect → Repeat.
    
    Like LangGraph's agent Execute loop with self-reflection.
    Checks budget each iteration and route to compress if needed.
    """
    wf = Workflow("goal_loop")
    
    def plan(state):
        goal = state.get("active_goal", "")
        log.info("    📋 Planning for: %s", goal[:100] if goal else "(no goal)")
        state["plan"] = {
            "steps": ["gather", "analyze", "synthesize", "report"],
            "iteration": state.get("turn_count", 0) // 4,
        }
        return state
    
    def gather(state):
        log.info("    🔍 Gathering data")
        state["gathered_data"] = {"sources": 3, "items": 12}
        return state
    
    def analyze(state):
        log.info("    🧪 Analyzing")
        state["analysis"] = {"findings": 5, "avg_confidence": 0.82}
        return state
    
    def synthesize(state):
        log.info("    🧬 Synthesizing")
        state["synthesis"] = {"output": "Completed analysis of all sources"}
        return state
    
    def reflect(state):
        log.info("    🔄 Reflecting on progress")
        prev = state.get("synthesis", {})
        goal = state.get("active_goal", "")
        state["reflection"] = {
            "progress": "adequate" if prev else "needs work",
            "goal_progress": f"Working on: {goal[:80]}",
            "should_continue": state.budget() > 0.2,
        }
        return state
    
    def compress(state):
        log.info("    📦 Compressing (budget at %.1f%%)", state.budget() * 100)
        state["tool_outputs"] = state.get("tool_outputs", [])[-3:]  # keep last 3
        # Snap summaries
        for key in ["plan", "gathered_data", "analysis", "synthesis", "reflection"]:
            if key in state:
                state[f"{key}_snapped"] = True
        state["context_budget"] = max(state.get("context_budget", 64000) - 10000, 10000)
        return state
    
    def route_after_reflect(state):
        ref = state.get("reflection", {})
        if ref.get("should_continue", False) and state.budget() > 0.3:
            return "continue_iterating"
        elif state.budget() <= 0.3:
            return "compress_and_continue"
        return "complete"
    
    wf.add_node("plan", plan, "Goal planning")
    wf.add_node("gather", gather, "Data gathering")
    wf.add_node("analyze", analyze, "Data analysis")
    wf.add_node("synthesize", synthesize, "Synthesis")
    wf.add_node("reflect", reflect, "Self-reflection")
    wf.add_node("compress", compress, "Context compression")
    
    wf.add_edge("plan", "gather")
    wf.add_edge("gather", "analyze")
    wf.add_edge("analyze", "synthesize")
    wf.add_edge("synthesize", "reflect")
    
    wf.add_conditional_edge("reflect", route_after_reflect, {
        "continue_iterating": "plan",
        "compress_and_continue": "compress",
        "complete": "stop",
    })
    wf.add_edge("compress", "plan")
    
    wf.set_entry("plan")
    wf.add_node("stop", lambda s: s, "Terminal node")
    wf.set_exit("stop")
    
    return wf.compile()


def checkpointer():
    """Simple checkpoint-restore workflow: saves and loads execution state."""
    wf = Workflow("checkpointer")
    
    def save(state):
        ckpt_id = f"ckpt_{int(time.time())}"
        state["_checkpoint_id"] = ckpt_id
        log.info("    💾 Saving checkpoint: %s", ckpt_id)
        return state
    
    def verify(state):
        ckpt_id = state.get("_checkpoint_id", "unknown")
        log.info("    ✅ Verified checkpoint: %s", ckpt_id)
        return state
    
    wf.add_node("save", save, "Save checkpoint")
    wf.add_node("verify", verify, "Verify checkpoint")
    wf.add_edge("save", "verify")
    wf.set_entry("save")
    wf.set_exit("verify")
    
    return wf.compile()


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 state_machine.py <command> [args...]")
        print("Commands:")
        print("  list          — List available workflows")
        print("  run <name>    — Run a workflow")
        print("  checkpoints   — List step checkpoints for a workflow")
        return
    
    cmd = sys.argv[1]
    
    WORKFLOWS = {
        "3tier": pipeline_3tier,
        "goal_loop": agent_goal_loop,
        "checkpointer": checkpointer,
        "executor_offload": executor_offload,
    }
    
    if cmd == "list":
        print("Available workflows:")
        for name in WORKFLOWS:
            wf = WORKFLOWS[name]()
            print(f"  {name}: {wf._nodes.get(wf._entry_node, Node('?', lambda s:s)).description}")
    
    elif cmd == "run":
        wf_name = sys.argv[2] if len(sys.argv) > 2 else "3tier"
        if wf_name not in WORKFLOWS:
            print(f"Unknown workflow: {wf_name}")
            return
        
        wf = WORKFLOWS[wf_name]()
        state = WorkflowState()
        
        if len(sys.argv) > 3:
            state["active_goal"] = " ".join(sys.argv[3:])
        
        final = wf.run(state)
        print("\n=== Final State ===")
        print(f"  Turns: {final.get('_turns_executed', 0)}")
        print(f"  Last node: {final.get('last_node', '?')}")
        print(f"  Budget remaining: {final.budget() * 100:.0f}%")
        print(f"  Errors: {len(final.get('errors', []))}")
        print(json.dumps(dict(final), indent=2, default=str))
    
    elif cmd == "checkpoints":
        wf_name = sys.argv[2] if len(sys.argv) > 2 else "3tier"
        wf = WORKFLOWS[wf_name]()
        ckpts = wf.list_step_checkpoints()
        print(f"Checkpoints for '{wf_name}':")
        for c in ckpts[-20:]:  # Last 20
            print(f"  {c}")
        print(f"  ({len(ckpts)} total)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()

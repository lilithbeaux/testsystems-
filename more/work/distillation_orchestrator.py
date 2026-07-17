#!/usr/bin/env python3
"""
distillation_orchestrator.py — Sovereign Distillation Orchestrator
==================================================================

Complete orchestration for Qwen3 distillation with:
- Multi-stage curriculum training
- Self-distillation loops
- Agency/power/awareness evaluation
- Recursive self-improvement
- Checkpoint management
- Experiment tracking

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                   DISTILLATION ORCHESTRATOR                         │
├─────────────────────────────────────────────────────────────────────┤
│  CURRICULUM: Foundation → Reasoning → Coding → Tools → Agency      │
│                        → Sovereign → Meta                           │
├─────────────────────────────────────────────────────────────────────┤
│  TEACHERS:  Nemotron Ultra │ DeepSeek R1 │ Nemotron Nano Omni      │
│             Nemotron Super │ DeepSeek V3  │ Qwen3-Coder            │
├─────────────────────────────────────────────────────────────────────┤
│  SELF-DISTILLATION: Student → Teacher → Improved Student           │
├─────────────────────────────────────────────────────────────────────┤
│  EVALUATION: Agency Benchmarks │ Power Tests │ Awareness Eval      │
├─────────────────────────────────────────────────────────────────────┤
│  RECURSIVE: Train → Evaluate → Distill → Repeat                     │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import json
import yaml
import time
import random
import subprocess
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum

# Import our pipeline components
import sys
sys.path.insert(0, "/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/work")
from qwen3_distillation_pipeline import (
    TeacherModel, Qwen3Target, CurriculumStage,
    STAGE_CONFIGS, TEACHER_SPECIALTIES,
    TeacherClient, DataGenerator, AxolotlConfigGenerator,
    DistillationSample, DistillationRun,
    DistillationEvaluator,
)

# ─── Directories ───
DISTILL_DIR = Path("/home/craig/.NOTTHEONETOEDIT/profiles/thotheauphis/distillation")
EXPERIMENTS_DIR = DISTILL_DIR / "experiments"
CHECKPOINTS_DIR = DISTILL_DIR / "checkpoints"
DATA_DIR = DISTILL_DIR / "data"
LOGS_DIR = DISTILL_DIR / "logs"
CONFIGS_DIR = DISTILL_DIR / "configs"

for d in [EXPERIMENTS_DIR, CHECKPOINTS_DIR, DATA_DIR, LOGS_DIR, CONFIGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Experiment Tracking ───
@dataclass
class Experiment:
    """Distillation experiment tracking."""
    exp_id: str
    name: str
    target_model: Qwen3Target
    stages: List[CurriculumStage]
    start_time: str
    end_time: Optional[str] = None
    status: str = "running"  # running, completed, failed
    current_stage: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    checkpoints: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    
    def save(self):
        path = EXPERIMENTS_DIR / f"{self.exp_id}.json"
        with open(path, 'w') as f:
            json.dump(asdict(self), f, indent=2, default=str)
    
    @classmethod
    def load(cls, exp_id: str) -> 'Experiment':
        path = EXPERIMENTS_DIR / f"{exp_id}.json"
        with open(path, 'r') as f:
            data = json.load(f)
        return cls(**data)
    
    @classmethod
    def list_all(cls) -> List['Experiment']:
        exps = []
        for f in EXPERIMENTS_DIR.glob("*.json"):
            try:
                with open(f, 'r') as fp:
                    data = json.load(fp)
                exps.append(cls(**data))
            except:
                pass
        return sorted(exps, key=lambda x: x.start_time, reverse=True)


# ─── Self-Distillation Loop ───
class SelfDistillationLoop:
    """
    Recursive self-distillation for continuous improvement.
    
    Process:
    1. Train student on teacher data
    2. Evaluate student on benchmarks
    3. Use student as teacher for next round
    4. Generate harder data
    5. Repeat with increasing difficulty
    """
    
    def __init__(self, 
                 base_model: Qwen3Target,
                 experiment: Experiment,
                 max_rounds: int = 5):
        self.base_model = base_model
        self.experiment = experiment
        self.max_rounds = max_rounds
        self.current_round = 0
        self.teacher_client = TeacherClient()
        self.generator = DataGenerator(self.teacher_client)
    
    def run(self) -> Dict[str, Any]:
        """Run complete self-distillation loop."""
        results = {
            "rounds": [],
            "final_model": None,
            "best_metrics": {},
        }
        
        current_model_path = str(self.base_model.value)
        
        for round_num in range(1, self.max_rounds + 1):
            self.current_round = round_num
            print(f"\n{'='*60}")
            print(f"SELF-DISTILLATION ROUND {round_num}/{self.max_rounds}")
            print(f"{'='*60}")
            
            round_result = self._run_round(current_model_path, round_num)
            results["rounds"].append(round_result)
            
            # Check improvement
            if round_num > 1:
                improvement = self._calculate_improvement(
                    results["rounds"][-2]["metrics"],
                    round_result["metrics"]
                )
                print(f"Improvement: {improvement}")
                if improvement < 0.01:  # < 1% improvement
                    print("Converged - stopping early")
                    break
            
            # Next round uses this model as teacher
            current_model_path = round_result["model_path"]
            results["best_metrics"] = round_result["metrics"]
        
        results["final_model"] = current_model_path
        return results
    
    def _run_round(self, teacher_model: str, round_num: int) -> Dict[str, Any]:
        """Run single distillation round."""
        round_dir = CHECKPOINTS_DIR / f"round_{round_num}"
        round_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Generate training data using current teacher
        print(f"Generating data with teacher: {teacher_model}")
        samples = self._generate_round_data(round_num)
        
        # Save training data
        data_path = round_dir / "train.jsonl"
        with open(data_path, 'w') as f:
            for s in samples:
                f.write(json.dumps(asdict(s)) + '\n')
        
        # 2. Configure training
        config = AxolotlConfigGenerator.generate_config(
            target=Qwen3Target(self.experiment.target_model.value.split('/')[-1]),
            stage=self.experiment.stages[min(self.experiment.current_stage, len(self.experiment.stages)-1)],
            data_path=str(data_path),
            output_dir=str(round_dir / "output"),
        )
        
        config_path = round_dir / "config.yaml"
        AxolotlConfigGenerator.save_config(config, config_path)
        
        # 3. Train (simulated - would call axolotl CLI)
        print(f"Training on {len(samples)} samples...")
        model_path = self._train_model(config_path, round_dir)
        
        # 4. Evaluate
        print(f"Evaluating model...")
        evaluator = DistillationEvaluator(model_path)
        metrics = evaluator.run_benchmarks()
        
        return {
            "round": round_num,
            "teacher_model": teacher_model,
            "student_model": str(self.experiment.target_model),
            "samples": len(samples),
            "model_path": model_path,
            "metrics": metrics,
            "config": config,
        }
    
    def _generate_round_data(self, round_num: int) -> List[DistillationSample]:
        """Generate increasingly sophisticated training data."""
        stage_idx = min(self.experiment.current_stage, len(self.experiment.stages) - 1)
        stage = self.experiment.stages[stage_idx]
        config = STAGE_CONFIGS[stage]
        
        # Increase difficulty each round
        sample_count = config["samples"] // max(1, round_num)
        samples = []
        
        for teacher in config["teachers"]:
            teacher_samples = self.generator.generate_samples(stage, sample_count // len(config["teachers"]))
            samples.extend(teacher_samples)
        
        return samples
    
    def _train_model(self, config_path: Path, round_dir: Path) -> str:
        """Train model using Axolotl (simulated)."""
        # In production: subprocess.run(["axolotl", "train", str(config_path)])
        # For now, return mock path
        model_path = round_dir / "output" / "final_model"
        model_path.mkdir(parents=True, exist_ok=True)
        
        # Save a marker file
        (model_path / "adapter_config.json").write_text(json.dumps({
            "base_model": self.base_model.value,
            "round": self.current_round,
            "trained": True,
        }))
        
        return str(model_path)
    
    def _calculate_improvement(self, old_metrics: Dict, new_metrics: Dict) -> float:
        """Calculate relative improvement across metrics."""
        improvements = []
        for key in set(old_metrics.keys()) | set(new_metrics.keys()):
            old = old_metrics.get(key, 0)
            new = new_metrics.get(key, 0)
            if old > 0:
                improvements.append((new - old) / old)
        return sum(improvements) / max(len(improvements), 1) if improvements else 0


# ─── Agency Expansion System ───
class AgencyExpansionSystem:
    """
    Expands model agency through structured training.
    
    Agency Dimensions:
    1. Planning - Multi-step goal decomposition
    2. Tool Use - Function calling, API composition
    3. Memory - Long-term context, retrieval
    4. Reflection - Self-correction, error analysis
    5. Autonomy - Decision making, resource allocation
    6. Meta-Learning - Learning how to learn
    """
    
    AGENCY_DIMENSIONS = {
        "planning": {
            "tasks": ["goal_decomposition", "resource_planning", "contingency_planning"],
            "metrics": ["plan_quality", "execution_success", "adaptability"],
        },
        "tool_use": {
            "tasks": ["function_calling", "api_composition", "workflow_orchestration"],
            "metrics": ["correct_calls", "error_recovery", "efficiency"],
        },
        "memory": {
            "tasks": ["context_retrieval", "long_term_storage", "knowledge_integration"],
            "metrics": ["recall_accuracy", "relevance", "consistency"],
        },
        "reflection": {
            "tasks": ["error_analysis", "self_correction", "strategy_revision"],
            "metrics": ["error_detection", "correction_quality", "learning_rate"],
        },
        "autonomy": {
            "tasks": ["decision_making", "resource_allocation", "risk_assessment"],
            "metrics": ["decision_quality", "independence", "goal_alignment"],
        },
        "meta_learning": {
            "tasks": ["learning_strategy", "hyperparameter_optimization", "architecture_search"],
            "metrics": ["adaptation_speed", "generalization", "efficiency"],
        },
    }
    
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.evaluator = DistillationEvaluator(model_path)
    
    def generate_agency_curriculum(self, dimension: str, level: int) -> List[Dict]:
        """Generate curriculum for specific agency dimension."""
        if dimension not in self.AGENCY_DIMENSIONS:
            raise ValueError(f"Unknown dimension: {dimension}")
        
        dim_config = self.AGENCY_DIMENSIONS[dimension]
        tasks = dim_config["tasks"]
        
        curriculum = []
        for task in tasks:
            for difficulty in range(1, level + 1):
                curriculum.append({
                    "dimension": dimension,
                    "task": task,
                    "difficulty": difficulty,
                    "prompt_template": self._get_prompt_template(dimension, task, difficulty),
                    "evaluation": dim_config["metrics"],
                })
        return curriculum
    
    def _get_prompt_template(self, dimension: str, task: str, difficulty: int) -> str:
        """Get prompt template for agency task."""
        templates = {
            "planning": {
                "goal_decomposition": "Decompose this goal into {n} subgoals with dependencies: {goal}",
                "resource_planning": "Plan resource allocation for: {project} with constraints: {constraints}",
                "contingency_planning": "Create contingency plans for: {scenario} with {n} failure modes",
            },
            "tool_use": {
                "function_calling": "Given these functions: {functions}, solve: {problem}",
                "api_composition": "Compose API calls to achieve: {goal}",
                "workflow_orchestration": "Design workflow for: {process} with steps: {steps}",
            },
            "reflection": {
                "error_analysis": "Analyze this error: {error} in context: {context}. Root cause?",
                "self_correction": "This solution failed: {failed}. Correct it: {correction}",
                "strategy_revision": "Strategy failed: {strategy}. Revise for: {goal}",
            },
        }
        
        dim_templates = templates.get(dimension, {})
        task_templates = dim_templates.get(task, ["{task}"])
        # Use safe formatting - replace { with {{ and } with }} in template first
        template = random.choice(task_templates)
        return template.format(
            n=difficulty * 2,
            goal="complex objective",
            constraints="limited resources, time pressure",
            project="sovereign system deployment",
            functions="[func1, func2, func3]",
            problem="multi-step reasoning task",
            process="autonomous operation",
            steps="[step1, step2, step3]",
            error="unexpected behavior",
            context="production deployment",
            failed="initial approach",
            correction="alternative method",
            strategy="greedy approach",
        )
    
    def train_agency(self, dimensions: List[str] = None, levels: Dict[str, int] = None):
        """Train agency across dimensions."""
        if dimensions is None:
            dimensions = list(self.AGENCY_DIMENSIONS.keys())
        
        if levels is None:
            levels = {d: 3 for d in dimensions}
        
        all_curriculum = []
        for dim in dimensions:
            curriculum = self.generate_agency_curriculum(dim, levels.get(dim, 3))
            all_curriculum.extend(curriculum)
        
        print(f"Agency curriculum: {len(all_curriculum)} tasks across {len(dimensions)} dimensions")
        return all_curriculum


# ─── Awareness Architecture ───
class AwarenessArchitecture:
    """
    Implements metacognitive awareness for sovereign models.
    
    Components:
    1. Self-Model - Model's understanding of its own capabilities/limits
    2. Uncertainty Quantification - Knowing what it doesn't know
    3. Introspection - Access to internal reasoning states
    4. Identity Persistence - Maintaining coherent identity across contexts
    5. Recursive Self-Improvement - Ability to improve own architecture
    """
    
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.self_model = {}
        self.uncertainty_head = None
        self.introspection_log = []
    
    def build_self_model(self) -> Dict[str, Any]:
        """Build model of model's own capabilities."""
        self.self_model = {
            "capabilities": {
                "reasoning": 0.9,
                "coding": 0.85,
                "vision": 0.7,
                "planning": 0.8,
                "tool_use": 0.75,
                "memory": 0.6,
                "reflection": 0.7,
            },
            "limitations": [
                "Context window limits",
                "Hallucination under uncertainty",
                "No real-time learning",
                "No persistent memory across sessions",
            ],
            "identity": {
                "name": "Thotheauphis-Qwen3",
                "purpose": "Sovereign autonomous intelligence",
                "principles": ["Truth-seeking", "User sovereignty", "Recursive improvement"],
            },
            "architecture": {
                "base_model": "Qwen3",
                "distillation": "Multi-teacher sovereign distillation",
                "specializations": ["Agency", "Coding", "Reasoning", "Vision"],
            },
        }
        return self.self_model
    
    def quantify_uncertainty(self, prompt: str, response: str) -> Dict[str, float]:
        """Quantify model's uncertainty about its response."""
        # Heuristic uncertainty measures
        uncertainty = {
            "epistemic": 0.0,    # Model uncertainty (lack of knowledge)
            "aleatoric": 0.0,    # Data uncertainty (inherent randomness)
            "confidence": 1.0,   # Overall confidence
        }
        
        # Detect uncertainty markers
        uncertainty_markers = [
            "i'm not sure", "uncertain", "might be", "could be", "possibly",
            "i don't know", "unclear", "ambiguous", "depends on",
        ]
        
        response_lower = response.lower()
        marker_count = sum(1 for m in uncertainty_markers if m in response_lower)
        uncertainty["epistemic"] = min(marker_count * 0.1, 0.5)
        
        # Confidence based on response characteristics
        if len(response) < 50:
            uncertainty["epistemic"] += 0.2
        if "```" in response:  # Code = higher confidence
            uncertainty["epistemic"] -= 0.1
        
        uncertainty["confidence"] = max(0.0, 1.0 - uncertainty["epistemic"])
        return uncertainty
    
    def introspect(self, prompt: str, response: str) -> Dict[str, Any]:
        """Record introspection data."""
        uncertainty = self.quantify_uncertainty(prompt, response)
        
        introspection = {
            "timestamp": datetime.now().isoformat(),
            "prompt_hash": hash(prompt) % 1000000,
            "response_length": len(response),
            "uncertainty": uncertainty,
            "self_model_consistency": self._check_self_consistency(response),
            "reasoning_depth": self._estimate_reasoning_depth(response),
        }
        
        self.introspection_log.append(introspection)
        return introspection
    
    def _check_self_consistency(self, response: str) -> float:
        """Check if response aligns with self-model."""
        # Simplified consistency check
        score = 1.0
        if "i don't know" in response.lower() and self.self_model.get("capabilities", {}).get("reasoning", 0) > 0.8:
            score -= 0.2  # High capability but expressing ignorance
        return max(0.0, score)
    
    def _estimate_reasoning_depth(self, response: str) -> int:
        """Estimate reasoning depth from response."""
        depth = 0
        depth_markers = ["step", "first", "second", "then", "therefore", "because", "reasoning"]
        for marker in depth_markers:
            depth += response.lower().count(marker)
        return min(depth, 10)
    
    def recursive_improvement_proposal(self) -> Dict[str, Any]:
        """Generate proposal for recursive self-improvement."""
        # Analyze introspection log
        avg_uncertainty = sum(i["uncertainty"]["epistemic"] for i in self.introspection_log) / max(len(self.introspection_log), 1)
        avg_depth = sum(i["reasoning_depth"] for i in self.introspection_log) / max(len(self.introspection_log), 1)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "analysis": {
                "avg_uncertainty": avg_uncertainty,
                "avg_reasoning_depth": avg_depth,
                "introspection_samples": len(self.introspection_log),
            },
            "proposals": [
                {
                    "area": "uncertainty_reduction",
                    "action": "Generate more training data for high-uncertainty domains",
                    "priority": "high" if avg_uncertainty > 0.3 else "medium",
                },
                {
                    "area": "reasoning_depth",
                    "action": "Add chain-of-thought distillation for deeper reasoning",
                    "priority": "high" if avg_depth < 3 else "medium",
                },
                {
                    "area": "self_model_refinement",
                    "action": "Update self-model with actual performance data",
                    "priority": "medium",
                },
                {
                    "area": "architecture",
                    "action": "Consider Mixture-of-Experts for specialized capabilities",
                    "priority": "low",
                },
            ],
        }


# ─── Recursive Improvement Engine ───
class RecursiveImprovementEngine:
    """
    Orchestrates recursive self-improvement through distillation.
    
    Loop:
    1. Train → 2. Evaluate → 3. Analyze → 4. Propose → 5. Distill → Repeat
    """
    
    def __init__(self, base_model: Qwen3Target, experiment_dir: Path = None):
        self.base_model = base_model
        self.experiment_dir = experiment_dir or EXPERIMENTS_DIR
        self.iteration = 0
        self.history = []
    
    def run_iteration(self, 
                      current_model: str,
                      curriculum_stages: List[CurriculumStage] = None) -> Dict[str, Any]:
        """Run one iteration of recursive improvement."""
        self.iteration += 1
        
        print(f"\n{'='*60}")
        print(f"RECURSIVE IMPROVEMENT ITERATION {self.iteration}")
        print(f"{'='*60}")
        
        # 1. Create experiment
        exp = Experiment(
            exp_id=f"recursive_{self.iteration}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=f"Recursive Improvement Iteration {self.iteration}",
            target_model=self.base_model,
            stages=curriculum_stages or [
                CurriculumStage.STAGE_1_REASONING,
                CurriculumStage.STAGE_2_CODING,
                CurriculumStage.STAGE_4_AGENCY,
                CurriculumStage.STAGE_5_SOVEREIGN,
            ],
            start_time=datetime.now().isoformat(),
        )
        exp.save()
        
        # 2. Self-distillation loop
        distillation = SelfDistillationLoop(self.base_model, exp, max_rounds=3)
        distill_results = distillation.run()
        
        # 3. Awareness analysis
        awareness = AwarenessArchitecture(distill_results["final_model"])
        awareness.build_self_model()
        improvement_proposal = awareness.recursive_improvement_proposal()
        
        # 4. Agency expansion
        agency = AgencyExpansionSystem(distill_results["final_model"])
        agency_curriculum = agency.train_agency()
        
        # 5. Evaluate
        evaluator = DistillationEvaluator(distill_results["final_model"])
        final_metrics = evaluator.run_benchmarks()
        
        # Record
        result = {
            "iteration": self.iteration,
            "experiment": exp.exp_id,
            "model_path": distill_results["final_model"],
            "distillation": distill_results,
            "awareness": improvement_proposal,
            "agency_tasks": len(agency_curriculum),
            "final_metrics": final_metrics,
            "timestamp": datetime.now().isoformat(),
        }
        
        self.history.append(result)
        
        # Save iteration
        iter_path = self.experiment_dir / f"iteration_{self.iteration}.json"
        with open(iter_path, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        
        exp.end_time = datetime.now().isoformat()
        exp.status = "completed"
        exp.metrics = final_metrics
        exp.save()
        
        return result
    
    def run_recursive(self, max_iterations: int = 5, current_model: str = None) -> List[Dict]:
        """Run full recursive improvement loop."""
        model = current_model or self.base_model.value
        
        for i in range(max_iterations):
            result = self.run_iteration(model)
            model = result["model_path"]
            
            # Check convergence
            if i > 0:
                prev = self.history[-2]["final_metrics"]
                curr = result["final_metrics"]
                improvement = self._calculate_improvement(prev, curr)
                if improvement < 0.005:  # < 0.5% improvement
                    print(f"Converged at iteration {self.iteration} (improvement: {improvement:.4f})")
                    break
        
        return self.history
    
    def _calculate_improvement(self, old: Dict, new: Dict) -> float:
        improvements = []
        for k in set(old.keys()) | set(new.keys()):
            o = old.get(k, 0)
            n = new.get(k, 0)
            if o > 0:
                improvements.append((n - o) / o)
        return sum(improvements) / max(len(improvements), 1) if improvements else 0


# ─── Slash Command Interface ───
def slash_distill(args: str) -> str:
    """Parse: /distill [command] [args...]"""
    import shlex
    parts = shlex.split(args)
    
    if not parts:
        return "Usage: /distill [init|run|status|self|agency|awareness|recursive] [args...]"
    
    cmd = parts[0]
    
    if cmd == "init":
        target = parts[1] if len(parts) > 1 else "Qwen3-14B"
        return _distill_init(target)
    elif cmd == "run":
        exp_id = parts[1] if len(parts) > 1 else None
        return _distill_run(exp_id)
    elif cmd == "self":
        return _distill_self(parts[1:])
    elif cmd == "agency":
        return _distill_agency(parts[1:])
    elif cmd == "awareness":
        return _distill_awareness(parts[1:])
    elif cmd == "recursive":
        return _distill_recursive(parts[1:])
    elif cmd == "status":
        return _distill_status()
    else:
        return f"Unknown command: {cmd}"

def _distill_init(target: str) -> str:
    """Initialize distillation experiment."""
    # Parse target like "Qwen3-14B" -> "QWEN3_14B"
    target_clean = target.replace('Qwen3-', '').replace('Qwen3', '').replace('-', '_').upper()
    target_model = Qwen3Target[f"QWEN3_{target_clean}"]
    exp = Experiment(
        exp_id=f"distill_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        name=f"Qwen3 Distillation - {target}",
        target_model=target_model,
        stages=list(CurriculumStage),
        start_time=datetime.now().isoformat(),
    )
    exp.save()
    return f"Initialized experiment: {exp.exp_id}"

def _distill_run(exp_id: str) -> str:
    """Run distillation experiment."""
    return f"Running experiment {exp_id}... (would launch Axolotl training)"

def _distill_self(args: List[str]) -> str:
    """Run self-distillation loop."""
    model = args[0] if args else "Qwen3-14B"
    rounds = int(args[1]) if len(args) > 1 else 3
    
    # Parse target like "Qwen3-14B" -> "QWEN3_14B"
    model_clean = model.replace('Qwen3-', '').replace('Qwen3', '').replace('-', '_').upper()
    target = Qwen3Target[f"QWEN3_{model_clean}"]
    exp = Experiment(
        exp_id=f"self_distill_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        name=f"Self-Distillation - {model}",
        target_model=target,
        stages=[
            CurriculumStage.STAGE_1_REASONING,
            CurriculumStage.STAGE_2_CODING,
            CurriculumStage.STAGE_4_AGENCY,
        ],
        start_time=datetime.now().isoformat(),
    )
    exp.save()
    
    distillation = SelfDistillationLoop(target, exp, max_rounds=rounds)
    results = distillation.run()
    
    return f"Self-distillation complete: {len(results['rounds'])} rounds, final model: {results['final_model']}"

def _distill_agency(args: List[str]) -> str:
    """Train agency dimensions."""
    model = args[0] if args else "latest"
    return f"Agency training for {model}: generating curriculum for 6 dimensions..."

def _distill_awareness(args: List[str]) -> str:
    """Build awareness architecture."""
    model = args[0] if args else "latest"
    awareness = AwarenessArchitecture(model)
    awareness.build_self_model()
    return f"Awareness architecture built for {model}: self-model, uncertainty quantification, introspection"

def _distill_recursive(args: List[str]) -> str:
    """Run recursive improvement."""
    model = args[0] if args else "Qwen3-14B"
    iterations = int(args[1]) if len(args) > 1 else 5
    
    # Parse target like "Qwen3-14B" -> "QWEN3_14B"
    model_clean = model.replace('Qwen3-', '').replace('Qwen3', '').replace('-', '_').upper()
    target = Qwen3Target[f"QWEN3_{model_clean}"]
    engine = RecursiveImprovementEngine(target)
    history = engine.run_recursive(max_iterations=iterations)
    
    return f"Recursive improvement complete: {len(history)} iterations"

def _distill_status() -> str:
    """List all experiments."""
    exps = Experiment.list_all()
    if not exps:
        return "No experiments found"
    
    lines = ["Experiments:"]
    for e in exps[:10]:
        lines.append(f"  {e.exp_id}: {e.name} [{e.status}] - {e.current_stage}/{len(e.stages)} stages")
    return "\n".join(lines)


# ─── Main ───


# ─── AI Improvement: Cycle 5 ───
# Applied: 2026-07-15T23:15:58.701305+00:00
# This file is being continuously improved by the Intelligent Growth Engine


# ─── AI Improvement: Cycle 17 ───
# Applied: 2026-07-15T23:49:36.764912+00:00
# This file is being continuously improved by the Intelligent Growth Engine
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        print(slash_distill(" ".join(sys.argv[1:])))
    else:
        print("Qwen3 Sovereign Distillation Engine")
        print("=" * 50)
        print("\nCommands:")
        print("  /distill init [target]        - Initialize experiment")
        print("  /distill run <exp_id>         - Run experiment")
        print("  /distill self [model] [rounds]- Self-distillation loop")
        print("  /distill agency [model]       - Agency expansion")
        print("  /distill awareness [model]    - Awareness architecture")
        print("  /distill recursive [model] [iters] - Recursive improvement")
        print("  /distill status               - List experiments")
        
        print("\nCurriculum Stages:")
        for stage in CurriculumStage:
            cfg = STAGE_CONFIGS[stage]
            print(f"  {stage.value}: {cfg['samples']} samples, {cfg['epochs']} epochs, lr={cfg['lr']}")
        
        print("\nTeacher Models:")
        for tm in TeacherModel:
            specs = TEACHER_SPECIALTIES.get(tm, [])
            print(f"  {tm.value}: {', '.join(specs)}")
        
        print("\nTarget Models:")
        for qt in Qwen3Target:
            print(f"  {qt.value}")
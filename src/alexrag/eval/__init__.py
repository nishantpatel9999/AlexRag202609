from alexrag.eval.cutoff import aware, enter_evidence_illegal, sealed_ok
from alexrag.eval.gates import evaluate_promotion_readiness
from alexrag.eval.golden_cases import stub_golden_cases
from alexrag.eval.harness import Prediction, load_golden_pack, score_case, score_pack
from alexrag.eval.metrics import PaperMetrics, paper_run_diagnostics, paper_window_met

__all__ = [
    "PaperMetrics",
    "paper_window_met",
    "paper_run_diagnostics",
    "evaluate_promotion_readiness",
    "stub_golden_cases",
    "load_golden_pack",
    "score_case",
    "score_pack",
    "Prediction",
    "sealed_ok",
    "enter_evidence_illegal",
    "aware",
]

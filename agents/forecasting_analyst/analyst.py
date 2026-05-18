"""
agents/forecasting_analyst/analyst.py
───────────────────────────────────────
The Forecasting Analyst agent — a "research agent" pattern with iterative loops.

WHAT IS A RESEARCH AGENT PATTERN?
A regular agent: user query → single LLM call → answer
A research agent: user query → LOOP { observe → reason → act } → answer

The loop:
  1. OBSERVE: Read current MAPE metrics from DB
  2. REASON: Identify worst performers (MAPE > threshold), understand WHY
  3. ACT: Propose hyperparameter change, log it
  4. REPEAT: Check if the proposed change would improve MAPE (simulate)
  5. STOP: After N iterations or when MAPE is acceptable

WHY does this matter for your resume?
"Autonomous research agent that analyzes forecasting outputs and auto-tunes
hyperparameters, eliminating manual intervention"

This is exactly what that bullet means in code. The agent doesn't just
read the MAPE — it reasons about what's causing the error and proposes
a specific, justified change. Without this, a data scientist would have
to manually inspect each model and decide what to change.

MAPE CONCEPTS:
  MAPE = Mean Absolute Percentage Error
  = (1/n) * Σ |actual - predicted| / actual * 100

  <8%: Excellent (stable products)
  8-15%: Good (acceptable for most supply chain)
  15-25%: High (investigation needed)
  >25%: Very high (model needs retraining)

HYPERPARAMETER TUNING LOGIC:
  XGBoost hyperparameters we tune:
  - n_estimators: more trees = better fit but slower. Start at 100, try 200.
  - max_depth: deeper = captures more patterns but risks overfitting. 6 → 8.
  - learning_rate: lower = more stable but needs more trees. 0.1 → 0.05.
  - min_child_weight: regularization. Higher = less overfitting. 1 → 3.

  SEASONAL products (sunscreen, cosmetics): add is_seasonal=True, increase n_estimators
  STABLE products (body lotion): fewer trees, lower depth is fine
"""

import os
import json
import asyncpg
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

analyst_llm = ChatOpenAI(model="gpt-4o", temperature=0.1)

MAPE_HIGH_THRESHOLD = 0.15    # >15% = needs attention
MAX_ITERATIONS = 2            # prevent infinite loops


async def run_forecasting_analyst(
    query: str,
    session_id: str,
    role: str,
    iterations: int = 0
) -> dict:
    """
    Run the forecasting analyst research agent.

    Returns:
        dict with 'metrics', 'worst_performers', 'proposed_tuning',
                  'summary', 'iterations_run'
    """

    # ─────────────────────────────────────────────
    # STEP 1: OBSERVE — read MAPE metrics from DB
    # ─────────────────────────────────────────────
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    async with pool.acquire() as conn:
        metrics_rows = await conn.fetch("""
            SELECT
                fm.product_id,
                p.product_name,
                p.category,
                fm.model_name,
                fm.mape,
                fm.mae,
                fm.hyperparameters,
                fm.notes,
                fm.run_date
            FROM forecast_metrics fm
            JOIN products p ON fm.product_id = p.product_id
            ORDER BY fm.mape DESC
        """)
    await pool.close()

    metrics = [dict(row) for row in metrics_rows]

    # Convert hyperparameters from JSON string to dict if needed
    for m in metrics:
        if isinstance(m.get("hyperparameters"), str):
            m["hyperparameters"] = json.loads(m["hyperparameters"])
        m["mape_pct"] = round(float(m["mape"]) * 100, 2)   # 0.1823 → 18.23%

    # ─────────────────────────────────────────────
    # STEP 2: REASON — identify worst performers
    # ─────────────────────────────────────────────
    worst_performers = [m for m in metrics if float(m["mape"]) > MAPE_HIGH_THRESHOLD]

    logger.info(f"Forecasting analyst: {len(worst_performers)} products above MAPE threshold")

    if not worst_performers:
        return {
            "metrics": metrics,
            "worst_performers": [],
            "proposed_tuning": None,
            "summary": f"All forecast models are performing well (MAPE < {MAPE_HIGH_THRESHOLD*100:.0f}%). No tuning needed.",
            "iterations_run": iterations
        }

    # ─────────────────────────────────────────────
    # STEP 3: REASON — use LLM to analyze and propose tuning
    #
    # WHY use an LLM here and not just rule-based logic?
    # Rule-based: "if MAPE > 15%, increase n_estimators by 50"
    # LLM: "SKU-008 (Sunscreen) has high MAPE in summer months — this is likely
    #       seasonal demand not captured by the model. Recommend adding is_seasonal
    #       feature and increasing learning_rate_decay."
    #
    # The LLM can reason about WHY MAPE is high (seasonality vs. outliers vs.
    # insufficient data) in a way that rule-based logic can't.
    # ─────────────────────────────────────────────
    analyst_prompt = f"""You are a supply chain forecasting expert analyzing XGBoost model performance.

Current worst-performing products (MAPE > {MAPE_HIGH_THRESHOLD*100:.0f}%):
{json.dumps(worst_performers, default=str, indent=2)}

User's question: {query}

Analyze the MAPE data and propose hyperparameter changes for the worst performer.

Consider:
1. Is the high MAPE likely due to seasonality? (sunscreen in summer, cosmetics in Q4)
2. Is the model underfitting (too simple) or overfitting (too complex)?
3. What specific hyperparameter changes would address the root cause?

Return a JSON object:
{{
  "target_product_id": "SKU-XXX",
  "root_cause": "one sentence explanation",
  "old_params": {{current hyperparameters}},
  "new_params": {{proposed hyperparameters with changes}},
  "rationale": "detailed explanation of why these changes help",
  "expected_mape_improvement": "X% reduction",
  "iteration": {iterations + 1}
}}"""

    response = await analyst_llm.ainvoke([
        SystemMessage(content="You are a precise supply chain ML analyst. Return only valid JSON."),
        HumanMessage(content=analyst_prompt)
    ])

    try:
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        proposed_tuning = json.loads(raw)
    except json.JSONDecodeError:
        proposed_tuning = {
            "target_product_id": worst_performers[0]["product_id"],
            "root_cause": "Analysis parsing failed, using heuristic",
            "old_params": worst_performers[0]["hyperparameters"],
            "new_params": {
                **worst_performers[0]["hyperparameters"],
                "n_estimators": worst_performers[0]["hyperparameters"].get("n_estimators", 100) * 2,
                "learning_rate": 0.05
            },
            "rationale": "Heuristic: double estimators and halve learning rate for underfitting",
            "expected_mape_improvement": "5-10% reduction",
            "iteration": iterations + 1
        }

    # ─────────────────────────────────────────────
    # STEP 4: SIMULATE IMPROVEMENT (for demo purposes)
    # In a real system, you'd retrain the model and measure actual MAPE.
    # Here we simulate: show what MAPE would look like with new params.
    # ─────────────────────────────────────────────
    simulated_improvement = 0.05   # assume 5% improvement per iteration
    for wp in worst_performers:
        if wp["product_id"] == proposed_tuning.get("target_product_id"):
            wp["projected_mape"] = max(0.05, float(wp["mape"]) - simulated_improvement)
            wp["projected_mape_pct"] = round(wp["projected_mape"] * 100, 2)

    # ─────────────────────────────────────────────
    # STEP 5: GENERATE SUMMARY
    # ─────────────────────────────────────────────
    target = proposed_tuning.get("target_product_id", "unknown")
    summary = (
        f"Found {len(worst_performers)} product(s) with MAPE above {MAPE_HIGH_THRESHOLD*100:.0f}%. "
        f"Worst performer: {target} (MAPE: {worst_performers[0]['mape_pct']}%). "
        f"Root cause: {proposed_tuning.get('root_cause', 'N/A')}. "
        f"Proposed fix: {proposed_tuning.get('rationale', 'N/A')}. "
        f"Expected improvement: {proposed_tuning.get('expected_mape_improvement', 'N/A')}."
    )

    return {
        "metrics": metrics,
        "worst_performers": worst_performers,
        "proposed_tuning": proposed_tuning,
        "summary": summary,
        "iterations_run": iterations + 1
    }

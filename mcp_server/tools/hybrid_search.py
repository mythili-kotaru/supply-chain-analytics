"""
mcp_server/tools/hybrid_search.py
───────────────────────────────────
Implementation of the hybrid_search tool.

This is the most technically interesting part of the MCP server.
Read this carefully — it's what you'd walk through in a system design interview.

HYBRID SEARCH = VECTOR SEARCH + FULL-TEXT SEARCH, merged with RRF

Why not just vector search?
  Vector search is great for semantic similarity but bad at exact matches.
  "SKU-008" won't match "sunscreen" semantically, and vice versa.

Why not just full-text (BM25)?
  BM25 only matches exact words (after stemming). "SPF cream" won't match
  "Sunscreen SPF50" because "cream" isn't in the text.

Hybrid (RRF) gives you both: semantic understanding AND keyword precision.
"""

import asyncpg
import openai
from typing import Any


EMBEDDING_MODEL = "text-embedding-3-small"
RRF_K = 60  # Standard RRF constant. Higher = smoother rank blending.
             # 60 is the value used in the original RRF paper (Cormack 2009).


async def hybrid_search_impl(
    db_pool: asyncpg.Pool,
    openai_client: openai.AsyncOpenAI,
    query: str,
    region: str | None,
    category: str | None,
    limit: int
) -> list[dict]:
    """
    Execute hybrid search:
      1. Embed the query
      2. Run vector search (ANN via HNSW index)
      3. Run full-text search (GIN index on tsvector)
      4. Merge results with RRF
      5. Apply optional SQL filters (region, category)
      6. Return top-N results
    """

    # ─────────────────────────────────────────────
    # STEP 1: Embed the query
    #
    # We use the same model that embedded the records (text-embedding-3-small).
    # CRITICAL: query embedding and record embedding MUST use the same model.
    # If you embed records with model A and queries with model B, the vector
    # spaces don't align — similarity scores are meaningless.
    # ─────────────────────────────────────────────
    embedding_response = await openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query
    )
    query_embedding = embedding_response.data[0].embedding
    # query_embedding is a list of 1536 floats

    # pgvector expects the vector as a string: "[0.1, 0.2, ...]"
    query_embedding_str = str(query_embedding)

    async with db_pool.acquire() as conn:

        # ─────────────────────────────────────────────
        # STEP 2: VECTOR SEARCH
        #
        # <=> = cosine distance operator (pgvector)
        # 1 - (embedding <=> query_embedding) = cosine similarity (0 to 1)
        #
        # SET hnsw.ef_search = 100: tells the HNSW index how many candidate
        # nodes to explore. Higher = better recall, slower query.
        # 100 is a good default for our dataset size.
        #
        # WHY LIMIT 20 (not limit directly)?
        # We fetch more candidates than needed because RRF reranks them.
        # After merging, the top-10 by RRF might not be the top-10 by vector alone.
        # ─────────────────────────────────────────────
        await conn.execute("SET hnsw.ef_search = 100")

        vector_sql = """
            SELECT
                scr.record_id,
                p.product_id,
                p.product_name,
                p.category,
                scr.region,
                scr.customer_segment,
                scr.revenue,
                scr.order_quantity,
                scr.order_date,
                ROW_NUMBER() OVER (ORDER BY scr.embedding <=> $1::vector) AS vector_rank
            FROM supply_chain_records scr
            JOIN products p ON scr.product_id = p.product_id
            WHERE scr.embedding IS NOT NULL
            {region_filter}
            {category_filter}
            ORDER BY scr.embedding <=> $1::vector
            LIMIT 20
        """.format(
            region_filter="AND scr.region = $2" if region else "",
            category_filter=(
                f"AND p.category = ${'3' if region else '2'}" if category else ""
            )
        )

        # Build params list dynamically based on which filters are active
        params = [query_embedding_str]
        if region:
            params.append(region)
        if category:
            params.append(category)

        vector_results = await conn.fetch(vector_sql, *params)

        # ─────────────────────────────────────────────
        # STEP 3: FULL-TEXT SEARCH
        #
        # to_tsquery converts the query string to a tsquery:
        #   "sunscreen stockout" → 'sunscreen' & 'stockout'
        #   (both words must appear, after stemming)
        #
        # plainto_tsquery is more forgiving — doesn't require all words.
        # We use plainto_tsquery for better recall on natural language queries.
        #
        # ts_rank_cd: cover density ranking — gives higher scores when
        # query terms appear close together in the text.
        # ─────────────────────────────────────────────
        fts_sql = """
            SELECT
                scr.record_id,
                p.product_id,
                p.product_name,
                p.category,
                scr.region,
                scr.customer_segment,
                scr.revenue,
                scr.order_quantity,
                scr.order_date,
                ROW_NUMBER() OVER (ORDER BY ts_rank_cd(scr.search_vector, query) DESC) AS fts_rank
            FROM supply_chain_records scr
            JOIN products p ON scr.product_id = p.product_id,
            plainto_tsquery('english', $1) query
            WHERE scr.search_vector @@ query
            {region_filter}
            {category_filter}
            ORDER BY ts_rank_cd(scr.search_vector, query) DESC
            LIMIT 20
        """.format(
            region_filter="AND scr.region = $2" if region else "",
            category_filter=(
                f"AND p.category = ${'3' if region else '2'}" if category else ""
            )
        )

        fts_params = [query]
        if region:
            fts_params.append(region)
        if category:
            fts_params.append(category)

        fts_results = await conn.fetch(fts_sql, *fts_params)

    # ─────────────────────────────────────────────
    # STEP 4: RECIPROCAL RANK FUSION (RRF)
    #
    # RRF formula: score(d) = sum over each ranklist: 1 / (rank + K)
    #
    # Example:
    #   Record 42 is rank 3 in vector search and rank 7 in FTS:
    #   RRF score = 1/(3+60) + 1/(7+60) = 0.01587 + 0.01493 = 0.03080
    #
    #   Record 17 is rank 1 in vector, not in FTS:
    #   RRF score = 1/(1+60) = 0.01639
    #
    #   Record 42 wins despite not being #1 in either list!
    #   This is the power of RRF — it rewards consistently good ranking.
    # ─────────────────────────────────────────────
    rrf_scores: dict[int, float] = {}
    record_data: dict[int, dict] = {}

    # Process vector results
    for row in vector_results:
        rid = row["record_id"]
        rrf_scores[rid] = rrf_scores.get(rid, 0) + (1.0 / (row["vector_rank"] + RRF_K))
        record_data[rid] = dict(row)
        record_data[rid]["match_type"] = "vector"

    # Process FTS results (add to existing scores)
    for row in fts_results:
        rid = row["record_id"]
        rrf_scores[rid] = rrf_scores.get(rid, 0) + (1.0 / (row["fts_rank"] + RRF_K))
        if rid not in record_data:
            record_data[rid] = dict(row)
            record_data[rid]["match_type"] = "fulltext"
        else:
            record_data[rid]["match_type"] = "hybrid"   # appeared in both lists

    # ─────────────────────────────────────────────
    # STEP 5: Sort by RRF score and return top-N
    # ─────────────────────────────────────────────
    sorted_ids = sorted(rrf_scores.keys(), key=lambda rid: rrf_scores[rid], reverse=True)
    top_ids = sorted_ids[:limit]

    results = []
    for rid in top_ids:
        data = record_data[rid]
        results.append({
            "record_id": rid,
            "product_id": data["product_id"],
            "product_name": data["product_name"],
            "category": data["category"],
            "region": data["region"],
            "customer_segment": data["customer_segment"],
            "revenue": float(data["revenue"]) if data["revenue"] else None,
            "order_quantity": data["order_quantity"],
            "order_date": str(data["order_date"]) if data["order_date"] else None,
            "rrf_score": round(rrf_scores[rid], 5),
            "match_type": data["match_type"]   # 'vector', 'fulltext', or 'hybrid'
        })

    return results

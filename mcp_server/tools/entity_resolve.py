"""
mcp_server/tools/entity_resolve.py
─────────────────────────────────────
Entity resolution via embedding similarity.

THE PROBLEM:
  Users say "face cream", agents hallucinate "SKU-999".
  We need to map fuzzy names → canonical IDs with confidence scores.

THE APPROACH:
  1. Embed the fuzzy name
  2. Compute cosine similarity vs. all product name embeddings in the DB
  3. Return top-3 candidates with scores

WHY store product embeddings separately?
  We could re-embed all product names on every entity_resolve call.
  Instead, we pre-compute and store them in a products_embeddings table.
  This is a performance trade-off: slightly more storage, much faster queries.

NOTE: In this implementation, product embeddings are generated from product names.
The entity_resolve tool stores them in a separate column on the products table
(added by 03_product_embeddings.sql migration).
"""

import asyncpg
import openai


EMBEDDING_MODEL = "text-embedding-3-small"


async def entity_resolve_impl(
    db_pool: asyncpg.Pool,
    openai_client: openai.AsyncOpenAI,
    entity_name: str,
    entity_type: str
) -> dict:

    # Embed the fuzzy name
    resp = await openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=entity_name
    )
    query_vec = str(resp.data[0].embedding)

    async with db_pool.acquire() as conn:

        if entity_type == "product":
            # Cosine similarity between query vector and product name embeddings
            # 1 - (embedding <=> query) = cosine similarity (0 to 1, higher = more similar)
            sql = """
                SELECT
                    product_id,
                    product_name,
                    category,
                    1 - (name_embedding <=> $1::vector) AS similarity
                FROM products
                WHERE name_embedding IS NOT NULL
                ORDER BY name_embedding <=> $1::vector
                LIMIT 3
            """
            rows = await conn.fetch(sql, query_vec)
            candidates = [
                {
                    "id": row["product_id"],
                    "name": row["product_name"],
                    "category": row["category"],
                    "confidence": round(float(row["similarity"]), 4)
                }
                for row in rows
            ]

        elif entity_type == "supplier":
            sql = """
                SELECT
                    supplier_id,
                    supplier_name,
                    location,
                    1 - (name_embedding <=> $1::vector) AS similarity
                FROM suppliers
                WHERE name_embedding IS NOT NULL
                ORDER BY name_embedding <=> $1::vector
                LIMIT 3
            """
            rows = await conn.fetch(sql, query_vec)
            candidates = [
                {
                    "id": row["supplier_id"],
                    "name": row["supplier_name"],
                    "location": row["location"],
                    "confidence": round(float(row["similarity"]), 4)
                }
                for row in rows
            ]

        else:
            return {"error": f"Unknown entity_type: {entity_type}. Use 'product' or 'supplier'."}

    if not candidates:
        return {
            "query": entity_name,
            "entity_type": entity_type,
            "best_match": None,
            "candidates": [],
            "message": "No matches found. Run generate_product_embeddings.py to populate embeddings."
        }

    best = candidates[0]
    return {
        "query": entity_name,
        "entity_type": entity_type,
        "best_match": best,
        "candidates": candidates,
        "confident": best["confidence"] > 0.85   # threshold for auto-resolution
    }

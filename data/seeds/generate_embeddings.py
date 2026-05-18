"""
generate_embeddings.py
──────────────────────
Run this ONCE after docker-compose up to populate the embedding column.

WHY a separate script and not part of the SQL seed?
SQL can't call OpenAI. We need Python to:
  1. Fetch rows without embeddings
  2. Build a text description per row
  3. Call OpenAI text-embedding-3-small
  4. Write the vector back to Postgres

WHY text-embedding-3-small and not text-embedding-3-large?
  - small: 1536 dimensions, ~$0.02 per 1M tokens, ~50ms latency
  - large: 3072 dimensions, ~$0.13 per 1M tokens, ~80ms latency
  For supply chain entity resolution, small is sufficient.
  If you switch to large, change vector(1536) → vector(3072) in the schema.

Usage:
  pip install openai psycopg2-binary python-dotenv
  python data/seeds/generate_embeddings.py
"""

import os
import psycopg2
import openai
import time
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"   # 1536 dims
BATCH_SIZE = 20                               # OpenAI allows up to 2048 inputs per request
                                              # but smaller batches = easier to debug

client = openai.OpenAI(api_key=OPENAI_API_KEY)


def build_embedding_text(row: dict) -> str:
    """
    Convert a supply chain record into a text description for embedding.

    WHY this specific format?
    The embedding model learns from language. The more meaningful context
    you give it, the better the semantic similarity will be.

    "Product: Moisturizing Face Cream | Category: skincare | Region: Southeast
     | Segment: retail | Revenue: $7500.00"

    This means: searching "budget skincare in the south" will find this record
    because 'skincare', 'Southeast', and 'retail' are semantically close to
    'budget skincare in the south' in the embedding space.

    What NOT to embed: raw IDs (SKU-001), dates — they add noise.
    """
    return (
        f"Product: {row['product_name']} | "
        f"Category: {row['category']} | "
        f"Region: {row['region']} | "
        f"Customer Segment: {row['customer_segment']} | "
        f"Revenue: ${row['revenue']:.2f} | "
        f"Order Quantity: {row['order_quantity']}"
    )


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Call OpenAI to get embeddings for a batch of texts.

    WHY batch and not one-by-one?
    Reduces API round trips. 20 texts = 1 HTTP call instead of 20.
    OpenAI bills per token regardless, but batching reduces latency overhead.
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts
    )
    # response.data is a list of Embedding objects, ordered same as input
    return [item.embedding for item in response.data]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Fetch rows that don't have embeddings yet
    # WHY 'embedding IS NULL'? Idempotent — safe to re-run if script fails halfway.
    cur.execute("""
        SELECT scr.record_id, p.product_name, p.category,
               scr.region, scr.customer_segment, scr.revenue, scr.order_quantity
        FROM supply_chain_records scr
        JOIN products p ON scr.product_id = p.product_id
        WHERE scr.embedding IS NULL
        ORDER BY scr.record_id
    """)
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    rows_as_dicts = [dict(zip(columns, row)) for row in rows]

    if not rows_as_dicts:
        print("All embeddings already populated. Nothing to do.")
        return

    print(f"Generating embeddings for {len(rows_as_dicts)} records...")

    # Process in batches
    for i in range(0, len(rows_as_dicts), BATCH_SIZE):
        batch = rows_as_dicts[i:i + BATCH_SIZE]
        texts = [build_embedding_text(row) for row in batch]
        record_ids = [row["record_id"] for row in batch]

        print(f"  Batch {i//BATCH_SIZE + 1}: records {record_ids[0]}–{record_ids[-1]}")

        embeddings = get_embeddings(texts)

        # Write embeddings back to Postgres
        # pgvector accepts Python lists directly when using psycopg2 + pgvector adapter
        # OR you can cast to string: str(embedding) → "[0.1, 0.2, ...]"
        for record_id, embedding in zip(record_ids, embeddings):
            cur.execute(
                "UPDATE supply_chain_records SET embedding = %s WHERE record_id = %s",
                (str(embedding), record_id)   # pgvector accepts "[f1, f2, ...]" string
            )

        conn.commit()

        # Rate limit: OpenAI allows 3000 RPM on tier 1
        # At BATCH_SIZE=20, we're nowhere near that, but be polite
        time.sleep(0.1)

    print("Done! All embeddings populated.")

    # Verify
    cur.execute("SELECT COUNT(*) FROM supply_chain_records WHERE embedding IS NOT NULL")
    count = cur.fetchone()[0]
    print(f"Records with embeddings: {count}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

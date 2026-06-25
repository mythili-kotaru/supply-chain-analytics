import asyncio
import json
import urllib.request
import urllib.error
import asyncpg
import sys

BASE_URL = "http://localhost:8003"
DATABASE_URL = "postgresql://scai:scai_password@localhost:5439/supply_chain"

def make_request(path, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    url = f"{BASE_URL}{path}"
    
    req_data = None
    if data is not None:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status = response.status
            body = response.read().decode("utf-8")
            return status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err_data = json.loads(body)
        except Exception:
            err_data = body
        return e.code, err_data
    except Exception as e:
        print(f"Request error: {e}")
        return 0, str(e)

async def run_integration_test():
    print("[1] Logging in as Admin...")
    login_data = {"username": "admin", "password": "admin123"}
    status, body = make_request("/api/dashboard/auth/login", method="POST", data=login_data)
    if status != 200:
        print(f"❌ Login failed: {status} - {body}")
        sys.exit(1)
    
    token = body.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("✓ Logged in. Token retrieved.")

    print("\n[2] Running sandbox simulation to generate deficits and mitigations...")
    sim_data = {"demand_multiplier": 3.0, "lead_time_multiplier": 1.0, "disrupted_supplier_id": None}
    status, sim_body = make_request("/api/dashboard/simulation/run", method="POST", headers=headers, data=sim_data)
    if status != 200:
        print(f"❌ Simulation run failed: {status} - {sim_body}")
        sys.exit(1)
    
    mitigations = sim_body.get("mitigations", [])
    print(f"✓ Simulation returned {len(mitigations)} mitigations.")
    
    mitigation_to_apply = None
    if mitigations:
        mitigation_to_apply = mitigations[0]
        print(f"Using simulation mitigation: {mitigation_to_apply}")
    else:
        # Fallback mitigation if no stockouts generated
        mitigation_to_apply = {
            "product_id": "SKU-001",
            "product_name": "Premium Multivitamin",
            "location": "Northeast",
            "action_type": "purchase_order",
            "quantity": 100,
            "supplier_name": "Global Wellness Distributors"
        }
        print(f"Using fallback mitigation: {mitigation_to_apply}")

    print("\n[3] POSTing apply-mitigation request...")
    status, apply_body = make_request("/api/dashboard/simulation/apply-mitigation", method="POST", headers=headers, data=mitigation_to_apply)
    if status != 200:
        print(f"❌ Apply mitigation failed: {status} - {apply_body}")
        sys.exit(1)
        
    proposal_id = apply_body.get("proposal_id")
    print(f"✓ Apply mitigation success. Created proposal ID: {proposal_id}")
    
    print("\n[4] Querying PostgreSQL database to verify proposal insertion and payloads...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT * FROM proposals WHERE id = $1", proposal_id)
        if not row:
            print("❌ Proposal row not found in database!")
            sys.exit(1)
        
        print("✓ Database record verified:")
        print(f"  - Status: {row['status']} (expected: pending)")
        print(f"  - Type: {row['type']}")
        print(f"  - Trigger Product: {row['trigger_product_id']} ({row['trigger_product_name']})")
        print(f"  - Reasoning: {row['agent_reasoning']}")
        
        # Verify replenishment_payload or allocation_payload
        repl_payload = row['replenishment_payload']
        alloc_payload = row['allocation_payload']
        if row['type'] == 'replenishment':
            if not repl_payload:
                print("❌ Replenishment payload is missing in proposals table!")
                sys.exit(1)
            repl_dict = json.loads(repl_payload)
            print("  - Replenishment PO quantity:", repl_dict['purchase_orders'][0]['order_quantity'])
        else:
            if not alloc_payload:
                print("❌ Allocation payload is missing in proposals table!")
                sys.exit(1)
            alloc_dict = json.loads(alloc_payload)
            print("  - Allocation Transfer quantity:", alloc_dict['transfers'][0]['transfer_quantity'])
            
    finally:
        await conn.close()

    print("\n[5] Approving proposal through the REST API...")
    status, approve_body = make_request(f"/api/dashboard/proposals/{proposal_id}/approve", method="POST", headers=headers)
    if status != 200:
        print(f"❌ Approve proposal failed: {status} - {approve_body}")
        sys.exit(1)
    print("✓ Approve endpoint returned 200:", approve_body)

    print("\n[6] Verifying updated proposal status in database...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT * FROM proposals WHERE id = $1", proposal_id)
        print(f"  - Status: {row['status']} (expected: approved)")
        if row['status'] != 'approved':
            print("❌ Proposal status was not set to approved!")
            sys.exit(1)
        print("✓ Proposal status successfully set to approved.")
    finally:
        await conn.close()
        
    print("\n🎉 Sandbox Mitigation Integration Test Passed Successfully!")

if __name__ == "__main__":
    asyncio.run(run_integration_test())

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

    print("\n[2] Running sandbox simulation to generate stockouts and purchase order mitigations...")
    sim_data = {"demand_multiplier": 3.0, "lead_time_multiplier": 1.0, "disrupted_supplier_id": None}
    status, sim_body = make_request("/api/dashboard/simulation/run", method="POST", headers=headers, data=sim_data)
    if status != 200:
        print(f"❌ Simulation run failed: {status} - {sim_body}")
        sys.exit(1)
    
    mitigations = sim_body.get("mitigations", [])
    print(f"✓ Simulation returned {len(mitigations)} mitigations.")
    
    po_mitigations = [m for m in mitigations if m.get("action_type") == "purchase_order"]
    if not po_mitigations:
        print("❌ No purchase order mitigations returned by simulation! Please ensure seed data has stockout-prone products.")
        sys.exit(1)
    
    # Verify Alternative Suppliers list presence and sorting
    po_action = po_mitigations[0]
    print(f"✓ Found PO mitigation for {po_action['product_name']} ({po_action['product_id']}) at {po_action['location']}")
    
    alt_suppliers = po_action.get("alternative_suppliers")
    if not alt_suppliers:
        print("❌ 'alternative_suppliers' list is empty or missing in PO mitigation response!")
        sys.exit(1)
        
    print(f"✓ Found {len(alt_suppliers)} alternative suppliers:")
    for idx, s in enumerate(alt_suppliers):
        print(f"  [{idx}] {s['supplier_name']} ({s['supplier_id']}) - Lead: {s['lead_time_days']}d, Price: ${s['price']}, Risk Score: {s['risk_score']}")
        # Assert keys exist
        for key in ["supplier_id", "supplier_name", "lead_time_days", "price", "defect_rate", "risk_score"]:
            assert key in s, f"Missing key '{key}' in alternative supplier data: {s}"
            
    # Assert they are sorted by risk_score ascending
    risk_scores = [s["risk_score"] for s in alt_suppliers]
    assert risk_scores == sorted(risk_scores), f"Alternative suppliers risk scores not sorted ascending: {risk_scores}"
    print("✓ Verified alternative suppliers are sorted ascending by risk score.")
    
    # Assert recommended supplier is the default selection
    assert po_action["supplier_id"] == alt_suppliers[0]["supplier_id"], "Default selection supplier_id does not match lowest risk alternative supplier!"
    assert po_action["supplier_name"] == alt_suppliers[0]["supplier_name"], "Default selection supplier_name does not match lowest risk alternative supplier!"
    assert po_action["risk_score"] == alt_suppliers[0]["risk_score"], "Default selection risk_score does not match lowest risk alternative supplier!"
    assert po_action["lead_time_days"] == alt_suppliers[0]["lead_time_days"], "Default selection lead_time_days does not match lowest risk alternative supplier!"
    print("✓ Verified default recommended supplier is the lowest risk option.")

    # Select an override supplier (backup supplier if available, else primary)
    override_supplier = alt_suppliers[1] if len(alt_suppliers) > 1 else alt_suppliers[0]
    print(f"\n[3] Applying mitigation override to select supplier: {override_supplier['supplier_name']} ({override_supplier['supplier_id']})")
    
    override_action = {
        "product_id": po_action["product_id"],
        "product_name": po_action["product_name"],
        "location": po_action["location"],
        "action_type": "purchase_order",
        "quantity": po_action["quantity"],
        "supplier_id": override_supplier["supplier_id"],
        "supplier_name": override_supplier["supplier_name"]
    }
    
    status, apply_body = make_request("/api/dashboard/simulation/apply-mitigation", method="POST", headers=headers, data=override_action)
    if status != 200:
        print(f"❌ Apply mitigation override failed: {status} - {apply_body}")
        sys.exit(1)
        
    proposal_id = apply_body.get("proposal_id")
    print(f"✓ Apply mitigation override success. Created proposal ID: {proposal_id}")
    
    print("\n[4] Querying PostgreSQL database to verify proposal record details and pricing payload...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT * FROM proposals WHERE id = $1", proposal_id)
        if not row:
            print("❌ Proposal record not found in PostgreSQL!")
            sys.exit(1)
            
        print("✓ Database record verified:")
        print(f"  - Status: {row['status']} (expected: pending)")
        print(f"  - Type: {row['type']} (expected: replenishment)")
        
        repl_payload = row['replenishment_payload']
        if not repl_payload:
            print("❌ replenishment_payload is NULL!")
            sys.exit(1)
            
        repl_dict = json.loads(repl_payload)
        po_details = repl_dict['purchase_orders'][0]
        
        print("✓ Replenishment PO details inside payload:")
        print(f"  - PO Number: {po_details['po_number']}")
        print(f"  - Supplier ID: {po_details['supplier_id']} (expected: {override_supplier['supplier_id']})")
        print(f"  - Supplier Name: {po_details['supplier_name']} (expected: {override_supplier['supplier_name']})")
        print(f"  - Lead Time Days: {po_details['lead_time_days']} (expected: {override_supplier['lead_time_days']})")
        print(f"  - Order Quantity: {po_details['order_quantity']} (expected: {po_action['quantity']})")
        print(f"  - Order Value: ${po_details['order_value']} (expected: ${override_supplier['price'] * po_action['quantity']:.2f})")
        
        assert po_details['supplier_id'] == override_supplier['supplier_id']
        assert po_details['supplier_name'] == override_supplier['supplier_name']
        assert po_details['lead_time_days'] == override_supplier['lead_time_days']
        assert abs(float(po_details['order_value']) - (override_supplier['price'] * po_action['quantity'])) < 0.01
        
        print("\n✓ All assertions passed. Sourcing Optimizer & Risk Scorecard Integration is working perfectly!")
        
    finally:
        await conn.close()

    print("\n🎉 Sandbox Sourcing Optimizer Integration Test Passed Successfully!")

if __name__ == "__main__":
    asyncio.run(run_integration_test())

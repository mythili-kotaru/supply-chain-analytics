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

    print("\n[2] Running sandbox simulation to get metrics for saving...")
    sim_data = {"demand_multiplier": 2.5, "lead_time_multiplier": 1.2, "disrupted_supplier_id": None}
    status, sim_body = make_request("/api/dashboard/simulation/run", method="POST", headers=headers, data=sim_data)
    if status != 200:
        print(f"❌ Simulation run failed: {status} - {sim_body}")
        sys.exit(1)
    
    print("✓ Simulation ran successfully.")
    
    # Extract some charts data and metrics
    charts_data = sim_body.get("charts_data", [])
    mitigations = sim_body.get("mitigations", [])
    
    scenario_payload = {
        "name": "Holiday Season Surge Test",
        "demand_multiplier": 2.5,
        "lead_time_multiplier": 1.2,
        "disrupted_supplier_id": None,
        "disrupted_supplier_name": None,
        "critical_stockouts": len(sim_body.get("stockout_details", [])),
        "total_mitigation_cost": sum(float(m.get("cost") or 0) for m in mitigations),
        "avg_mitigation_risk": sum(float(m.get("risk_score") or 0) for m in mitigations) / len(mitigations) if mitigations else 0.0,
        "total_mitigations_count": len(mitigations),
        "charts_data": charts_data
    }

    print("\n[3] POSTing save-scenario request...")
    status, save_body = make_request("/api/dashboard/simulation/scenarios", method="POST", headers=headers, data=scenario_payload)
    if status != 200:
        print(f"❌ Save scenario failed: {status} - {save_body}")
        sys.exit(1)
        
    scenario_id = save_body.get("id")
    print(f"✓ Scenario saved successfully. Scenario ID: {scenario_id}")
    
    print("\n[4] Querying PostgreSQL database to verify saved scenario...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT * FROM sandbox_scenarios WHERE id = $1", scenario_id)
        if not row:
            print("❌ Scenario not found in database!")
            sys.exit(1)
        
        print("✓ Database record verified:")
        print(f"  - Name: {row['name']} (expected: Holiday Season Surge Test)")
        print(f"  - Demand Multiplier: {row['demand_multiplier']} (expected: 2.50)")
        print(f"  - Lead Time Multiplier: {row['lead_time_multiplier']} (expected: 1.20)")
        print(f"  - Critical Stockouts: {row['critical_stockouts']}")
        print(f"  - Total Mitigation Cost: {row['total_mitigation_cost']}")
        
        assert row['name'] == "Holiday Season Surge Test"
        assert abs(float(row['demand_multiplier']) - 2.5) < 0.01
        assert abs(float(row['lead_time_multiplier']) - 1.2) < 0.01
        
    finally:
        await conn.close()

    print("\n[5] Fetching all scenarios via list endpoint...")
    status, list_body = make_request("/api/dashboard/simulation/scenarios", method="GET", headers=headers)
    if status != 200:
        print(f"❌ List scenarios failed: {status} - {list_body}")
        sys.exit(1)
        
    assert isinstance(list_body, list), "List scenarios response is not a list!"
    scenario_names = [s.get("name") for s in list_body]
    print(f"✓ Retrieved {len(list_body)} saved scenarios. Saved names: {scenario_names}")
    assert "Holiday Season Surge Test" in scenario_names, "Saved scenario name not found in list response!"

    print("\n[6] Deleting scenario via delete endpoint...")
    status, delete_body = make_request(f"/api/dashboard/simulation/scenarios/{scenario_id}", method="DELETE", headers=headers)
    if status != 200:
        print(f"❌ Delete scenario failed: {status} - {delete_body}")
        sys.exit(1)
    print("✓ Delete endpoint returned success.")

    print("\n[7] Verifying scenario removal in database...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT * FROM sandbox_scenarios WHERE id = $1", scenario_id)
        if row:
            print("❌ Scenario record still exists in database after deletion!")
            sys.exit(1)
        print("✓ Scenario successfully removed from database.")
    finally:
        await conn.close()
        
    print("\n🎉 Sandbox Scenario Versioning Integration Test Passed Successfully!")

if __name__ == "__main__":
    asyncio.run(run_integration_test())

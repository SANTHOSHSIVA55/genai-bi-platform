import requests
import json
import os

BASE_URL = "http://localhost:8000/api"

print("--- Testing API with fixes ---")

# 1. Register a new user
print("\n1. Registering user...")
reg_data = {
    "email": "test@example.com",
    "username": "testuser",
    "password": "password123"
}
r1 = requests.post(f"{BASE_URL}/auth/register", json=reg_data)
print(f"Status: {r1.status_code}")
if r1.status_code not in (200, 400):  # 400 might be "Email already registered"
    print(r1.text)

# 2. Login
print("\n2. Logging in...")
login_data = {
    "username": "test@example.com",  # FastAPI OAuth2 uses 'username' field, which we map to email
    "password": "password123"
}
r2 = requests.post(f"{BASE_URL}/auth/login", data=login_data)
print(f"Status: {r2.status_code}")
if r2.status_code == 200:
    token = r2.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Get profile
    print("\n3. Fetching profile...")
    r3 = requests.get(f"{BASE_URL}/auth/profile", headers=headers)
    print(f"Status: {r3.status_code}")
    print(json.dumps(r3.json(), indent=2))
    
    # 4. Get datasets
    print("\n4. Fetching datasets...")
    r4 = requests.get(f"{BASE_URL}/data/datasets", headers=headers)
    print(f"Status: {r4.status_code}")
    if r4.status_code == 200:
        datasets = r4.json()
        print(f"Found {len(datasets)} datasets")
    else:
        print(r4.text)
else:
    print(r2.text)

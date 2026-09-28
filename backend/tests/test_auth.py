def test_register_login_and_me(client):
    register = client.post(
        "/api/auth/register",
        json={"name": "Ada", "email": "ada@example.com", "password": "lovelace123"},
    )
    assert register.status_code == 201
    token = register.json()["access_token"]
    assert register.json()["user"]["email"] == "ada@example.com"

    duplicate = client.post(
        "/api/auth/register",
        json={"name": "Ada", "email": "ada@example.com", "password": "lovelace123"},
    )
    assert duplicate.status_code == 409

    login = client.post(
        "/api/auth/login", json={"email": "ada@example.com", "password": "lovelace123"}
    )
    assert login.status_code == 200

    bad_login = client.post(
        "/api/auth/login", json={"email": "ada@example.com", "password": "wrong-password"}
    )
    assert bad_login.status_code == 401

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Ada"


def test_password_is_hashed_not_stored_plaintext(client, db_session):
    from app.models import User

    client.post(
        "/api/auth/register",
        json={"name": "Grace", "email": "grace@example.com", "password": "hopper12345"},
    )
    user = db_session.query(User).filter_by(email="grace@example.com").one()
    assert user.password_hash != "hopper12345"
    assert user.password_hash.startswith("$2")


def test_protected_routes_require_a_token(client):
    assert client.get("/api/migrations").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/migrations", headers={"Authorization": "Bearer nope"}).status_code == 401

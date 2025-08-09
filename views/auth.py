import os
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

import pkce
import requests
from flask import (
    Blueprint,
    abort,
    redirect,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

# Avoid circular import by importing the database instance
# from models instead of app.
from models import TeslaToken, db

auth_bp = Blueprint("auth", __name__)


def get_user_token():
    token = TeslaToken.query.filter_by(user_id=current_user.id).first()
    if token and token.expires_at <= datetime.utcnow():
        data = {
            "grant_type": "refresh_token",
            "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
            "refresh_token": token.refresh_token,
        }
        headers = {"User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0")}
        resp = requests.post(
            "https://auth.tesla.com/oauth2/v3/token",
            json=data,
            headers=headers,
        )
        if resp.ok:
            info = resp.json()
            token.access_token = info["access_token"]
            token.refresh_token = info["refresh_token"]
            token.expires_at = datetime.utcnow() + timedelta(
                seconds=info["expires_in"]
            )
            db.session.commit()
        else:
            db.session.delete(token)
            db.session.commit()
            return None
    return token


def tesla_token_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_user_token():
            return redirect(url_for("auth.oauth_start"))
        return func(*args, **kwargs)

    return wrapper


@auth_bp.route("/oauth/start")
@login_required
def oauth_start():
    code_verifier = pkce.generate_code_verifier()
    code_challenge = pkce.generate_code_challenge(code_verifier)
    session["code_verifier"] = code_verifier
    params = {
        "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "redirect_uri": os.getenv("TESLA_REDIRECT_URI"),
        "response_type": "code",
        "scope": "openid email offline_access",
    }
    url = "https://auth.tesla.com/oauth2/v3/authorize?" + urlencode(params)
    return redirect(url)


@auth_bp.route("/oauth/callback")
@login_required
def oauth_callback():
    code = request.args.get("code")
    code_verifier = session.pop("code_verifier", None)
    if not code or not code_verifier:
        abort(400)
    data = {
        "grant_type": "authorization_code",
        "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": os.getenv("TESLA_REDIRECT_URI"),
    }
    headers = {"User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0")}
    resp = requests.post(
        "https://auth.tesla.com/oauth2/v3/token",
        json=data,
        headers=headers,
    )
    resp.raise_for_status()
    token_data = resp.json()
    expires_at = datetime.utcnow() + timedelta(token_data.get("expires_in", 0))
    token = TeslaToken(
        user_id=current_user.id,
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
    )
    db.session.add(token)
    db.session.commit()
    try:
        headers_api = {
            "Authorization": f"Bearer {token.access_token}",
            "User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0"),
        }
        veh_resp = requests.get(
            "https://owner-api.teslamotors.com/api/1/vehicles",
            headers=headers_api,
        )
        veh_resp.raise_for_status()
        vehicles = veh_resp.json().get("response", [])
        if vehicles:
            token.vehicle_id = vehicles[0].get("id_s")
            db.session.commit()
    except Exception:
        pass
    return redirect(url_for("index", username_slug=current_user.username_slug))


@auth_bp.route("/oauth/revoke", methods=["POST"])
@login_required
def oauth_revoke():
    token = TeslaToken.query.filter_by(user_id=current_user.id).first()
    if token:
        db.session.delete(token)
        db.session.commit()
    return redirect(url_for("index", username_slug=current_user.username_slug))

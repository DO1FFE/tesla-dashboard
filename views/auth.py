import os
from datetime import datetime, timedelta
from functools import wraps

import requests
from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
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
    data = {
        "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
        "scope": "openid email offline_access",
    }
    headers = {"User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0")}
    resp = requests.post(
        "https://auth.tesla.com/oauth2/v3/device/code",
        json=data,
        headers=headers,
    )
    resp.raise_for_status()
    info = resp.json()
    session["device_code"] = info["device_code"]
    return render_template(
        "oauth_device.html", verify_url=info["verification_uri_complete"]
    )


@auth_bp.route("/oauth/callback")
@login_required
def oauth_callback():
    device_code = session.get("device_code")
    if not device_code:
        abort(400)
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": os.getenv("TESLA_CLIENT_ID", "ownerapi"),
        "device_code": device_code,
    }
    headers = {"User-Agent": os.getenv("TESLA_USER_AGENT", "Mozilla/5.0")}
    resp = requests.post(
        "https://auth.tesla.com/oauth2/v3/token",
        json=data,
        headers=headers,
    )
    if resp.status_code == 400:
        error = resp.json().get("error")
        if error in ("authorization_pending", "slow_down"):
            return render_template("oauth_pending.html")
        resp.raise_for_status()
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
    session.pop("device_code", None)
    return redirect(url_for("index", username_slug=current_user.username_slug))


@auth_bp.route("/oauth/revoke", methods=["POST"])
@login_required
def oauth_revoke():
    token = TeslaToken.query.filter_by(user_id=current_user.id).first()
    if token:
        db.session.delete(token)
        db.session.commit()
    return redirect(url_for("index", username_slug=current_user.username_slug))

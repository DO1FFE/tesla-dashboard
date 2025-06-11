import os
import teslapy


def get_vehicle_data():
    email = os.getenv("TESLA_EMAIL")
    password = os.getenv("TESLA_PASSWORD")
    access_token = os.getenv("TESLA_ACCESS_TOKEN")
    refresh_token = os.getenv("TESLA_REFRESH_TOKEN")

    tesla = teslapy.Tesla(email)
    if access_token and refresh_token:
        tesla.sso_token = {"access_token": access_token, "refresh_token": refresh_token}
        tesla.refresh_token()
    else:
        tesla.password = password

    with tesla:
        vehicles = tesla.vehicle_list()
        return [v['display_name'] for v in vehicles]

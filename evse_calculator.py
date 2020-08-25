# -*- coding: utf-8 -*-
import json
import requests
from requests.auth import HTTPBasicAuth


class CalculatorOfEVSE:
    def __init__(self, url, username, password, **kwargs):
        """Constructor to load args"""
        self.url = url
        self.username = username
        self.password = password
        self.context = kwargs

    @staticmethod
    def import_data(url, username, password):
        """Auth and Get the data in json format"""
        response = requests.get(url, auth=HTTPBasicAuth(username, password))
        return json.loads(response.content)

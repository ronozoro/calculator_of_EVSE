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

    def parse_supplier_data_types(self, key, value):
        """Utility : Parsing float and list attributes in the json object for each supplier dict"""
        if key in ('kwh_price',
                   'max_session_fee',
                   'min_billing_amount',
                   'min_cosumed_energy',
                   'session_fee',
                   'min_consumption',
                   'max_session_fee') and isinstance(value, str):
            return float(
                value.replace(',', '.'))  # Todo Maybe need to be changed to be based on currency obj [currency,symbol]
        elif isinstance(value,
                        list) and key == 'time_price':  # Check the time price obj to avoid manipulating other list obj
            cleaned_value = []
            for item in value:
                time_dict = dict()
                for key, value in item.items():
                    new_key = key.lower().replace(' ', '_')
                    new_value = self.parse_supplier_data_types(new_key, value if value not in ('false', 'False') else 0)
                    time_dict.update({
                        new_key: new_value
                    })
                cleaned_value.append(time_dict)
            return cleaned_value
        return value

    @staticmethod
    def parse_transaction_data_types(key, value):
        """Utility : Parsing float  attributes in the json object for each transaction dict"""
        if key in ('meter_value_end', 'meter_value_start'):
            return float(
                value.replace(',', '.'))  # Todo Maybe need to be changed to be based on currency obj [currency,symbol]
        return value

    def parse_supplier_data(self, supplier_data):
        """Clean up supplier data and make dict keys meaningful"""
        supplier_list = []  # Cleaned Supplier List
        for supplier in supplier_data:
            supplier_item = dict()
            for key, value in supplier.items():
                new_key = key.lower().replace(' ', '_')  # rename the dict keys to make it meaningful
                new_value = self.parse_supplier_data_types(new_key, value if value not in ('false', 'False') else 0)
                supplier_item.update({new_key: new_value})
            supplier_list.append(supplier_item)
        return supplier_list

    def clean_transaction_data(self, transaction_data):
        """Clean up transaction data and make dict keys meaningful"""
        transaction_list = []  # Cleaned Transactions
        for transaction in transaction_data:
            transaction_item = dict()
            for key, value in transaction.items():
                new_key = key.lower().replace(' ', '_')
                new_value = self.parse_transaction_data_types(key.lower().replace(' ', '_'),
                                                              value)  # rename the dict keys to make it meaningful
                transaction_item.update({new_key: new_value})
            transaction_list.append(transaction_item)
        return transaction_list

    def cleaned_data(self):
        """Start to connect to the server and pass data to required function to start parsing and cleaning the data"""
        json_response = self.import_data(self.url, self.username, self.password)
        cleaned_supplier_data = self.parse_supplier_data(
            json_response.get('supplier_prices', []))  # Clean the supplier json obj
        cleaned_transaction_data = self.clean_transaction_data(
            json_response.get('transactions', []))  # Clean the transaction json obj
        return {'cleaned_supplier_data': cleaned_supplier_data,
                'cleaned_transaction_data': cleaned_transaction_data}  # cleaned data after simple manipulation

    @staticmethod
    def merge_supplier_transaction(cleaned_supplier_data, cleaned_transaction_data):
        """Match suppliers with transaction and merge them to construct final data"""
        merged_data = [{'supplier_detail': x, 'supplier_transaction': y}
                       for x in cleaned_supplier_data for y in cleaned_transaction_data
                       if (x['product_id'] == y['partner_product_id'] and x['evse_id'] == False) or x['evse_id'] == y[
                           'evseid']]  # Todo maybe remove duplicates to only loop throw transactions?
        return merged_data
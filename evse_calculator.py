# -*- coding: utf-8 -*-
from __future__ import division

import json
import requests
from datetime import datetime
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

    @staticmethod
    def compute_fee_price(supplier_with_transaction):
        """Start calculate the fee price for each transaction"""
        supplier_item = supplier_with_transaction.get('supplier_detail')
        result = 0
        # Check if the session has min threshold and max threshold to get the right value for result
        if supplier_item.get('has_session_fee') and supplier_item.get(
                'has_minimum_billing_threshold') and supplier_item.get('has_max_session_fee'):
            if supplier_item.get('min_billing_amount', 0) > supplier_item.get('session_fee', 0):
                result = supplier_item.get('min_billing_amount', 0)
            elif supplier_item.get('max_session_fee') > supplier_item['session_fee'] > supplier_item[
                'min_billing_amount']:
                result = supplier_item.get('session_fee', 0)
            elif supplier_item.get('session_fee', 0) > supplier_item.get('max_session_fee'):
                result = supplier_item.get('max_session_fee')
        # Check for min threshold only to get the min bill
        elif supplier_item.get('has_session_fee') and supplier_item.get('has_minimum_billing_threshold'):
            if supplier_item.get('min_billing_amount') > supplier_item.get('session_fee'):
                result = supplier_item.get('min_billing_amount')
            elif supplier_item.get('session_fee') > supplier_item.get('min_billing_amount'):
                result = supplier_item.get('session_fee')
        return result

    @staticmethod
    def compute_time_price(supplier_with_transaction):
        """Start to calculate time prices with both versions simple&complex"""
        supplier_item = supplier_with_transaction.get('supplier_detail')
        transaction_item = supplier_with_transaction.get('supplier_transaction')
        # Check if there is time prices or not
        if supplier_with_transaction.get('time_price'):
            # Check if we will compute in complex or simple
            if not supplier_item.get('has_complex_minute_price'):
                # start to calculate the simple version for time price
                charging_start = transaction_item.get('charging_start')
                charging_end = transaction_item.get('charging_end')
                if charging_start and charging_end:
                    charging_start_obj = datetime.strptime(charging_start, '%Y-%m-%dT%H:%M:%S')
                    charging_end_obj = datetime.strptime(charging_end, '%Y-%m-%dT%H:%M:%S')
                    duration_in_minutes = (charging_end_obj - charging_start_obj).total_seconds() / 60
                    # Check for min duration
                    if supplier_item.get('min_duration') and duration_in_minutes < supplier_item.get('min_duration'):
                        duration_in_minutes = supplier_item.get('min_duration')
                    price = supplier_item.get('simple_minute_price')
                    total_price = price * duration_in_minutes
                    return total_price
            else:
                # start calculate the complex version for time price
                total_price = 0
                if supplier_item.get('interval') == 'start':
                    for start_rec in supplier_item.get('time_price'):
                        timeframe = start_rec.get('billing_each_timeframe') * 60
                        if start_rec.get('hour_from', 0) > start_rec.get('hour_to', 0):
                            duration = (start_rec.get('hour_to') - start_rec.get('hour_from')) * 60
                        else:
                            duration = (start_rec.get('hour_to') - (24 - start_rec.get('hour_from'))) * 60
                        duration_after_timeframe = duration % timeframe
                        total_duration = duration + duration_after_timeframe
                        total_price += total_duration * start_rec.get('minute_price')
                else:
                    for end_rec in supplier_item.get('time_price'):
                        timeframe = end_rec.get('billing_each_timeframe') * 60
                        if end_rec.get('hour_from', 0) > end_rec.get('hour_to', 0):
                            duration = (end_rec.get('hour_to') - end_rec.get('hour_from')) * 60
                        else:
                            duration = (end_rec.get('hour_to') - (24 - end_rec.get('hour_from'))) * 60
                        duration_after_timeframe = duration % timeframe
                        total_duration = duration - (timeframe - duration_after_timeframe)
                        total_price += total_duration * end_rec.get('minute_price')

                return total_price
        else:
            total_price = 0
            return total_price

    def compute_kwh_price(self, supplier_with_transaction):
        return 0

    def calculate_prices(self, merged_data):
        """Prepare data to be exported or printed for final stage"""
        calculated_prices = []
        for record in merged_data:
            prices_dict = dict()
            supplier_price_id = record.get('supplier_detail').get('identifier')  # get the supplier price id
            session_id = record.get('supplier_transaction').get('session_id')  # get the transaction session
            supplier_trans_fee_price = self.compute_fee_price(
                record)  # Get the fee price for each transaction if needed
            supplier_trans_time_price = self.compute_time_price(
                record)  # Get the time price for each transaction if needed
            supplier_trans_kwh_price = self.compute_kwh_price(record)
            total_price = supplier_trans_fee_price + supplier_trans_time_price + supplier_trans_kwh_price
            prices_dict.update({'fee_price': supplier_trans_fee_price,
                                'time_price': supplier_trans_time_price,
                                'kwh_price': supplier_trans_kwh_price,
                                'total_price': total_price,
                                'session_id': session_id,
                                'supplier_price_id': supplier_price_id})
            calculated_prices.append(prices_dict)

        return calculated_prices

    def get_transaction_prices(self):
        """Get the final transaction details to be exported"""
        cleaned_data = self.cleaned_data()
        supplier_cleaned_data = cleaned_data.get('cleaned_supplier_data')
        transaction_cleaned_data = cleaned_data.get('cleaned_transaction_data')
        merged_data = self.merge_supplier_transaction(supplier_cleaned_data, transaction_cleaned_data)
        return self.calculate_prices(merged_data)


sub_calc = CalculatorOfEVSE('https://hgy780tcj2.execute-api.eu-central-1.amazonaws.com/dev/data', 'interviewee',
                            'muchpassword', dt_view='preview')
from pprint import pprint

pprint(sub_calc.get_transaction_prices())

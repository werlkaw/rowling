import enum

from collections import OrderedDict

def format_currency(value):
    return "${:,.2f}".format(value)


class BillingTier:
    def set_asset_range(self, asset_range):
        self.asset_range = asset_range
        self.amount = 0
        self.fee_amount = 0
        return self

    def set_amount(self, amount):
        self.amount = amount
        return self
    
    def set_rate(self, rate):
        self.rate = rate
        return self

    def set_fee_amount(self):
        self.fee_amount = self.rate * self.amount
        return self


class Account:
    def __init__(self, name):
        self.name = name
        self.mgmt_fees = 0
        self.account_type = ''

    def set_account_type(self, account_type):
        self.account_type = account_type
        return self

    def set_account_number(self, account_number):
        self.account_number = account_number
        return self

    def set_billing_account(self, billing_account):
        self.billing_account = billing_account
        return self

    def set_value(self, value):
        self.value = float(value)
        return self

    def get_value(self):
        return self.value

    def set_parent_portfolio(self, parent_portfolio):
        self.parent_portfolio = parent_portfolio
        return self

    def add_mgmt_fee(self, fee):
        self.mgmt_fees += float(fee)

    def value_as_currency(self):
        return format_currency(self.value)

    def amount_to_bill(self):
        if self.parent_portfolio.value == 0:
            print(self.name  + " account " + self.account_type + " has a portfolio value of 0. Check netflows file")
            return format_currency(0)
        return format_currency(self.parent_portfolio.amount_to_bill() * self.value / self.parent_portfolio.value)


class Portfolio:
    def __init__(self, name):
        self.accounts = []
        self.five_mil_alert = False
        self.netflow = 0
        self.value = 0
        self.curr_fee = 0
        self.name = name
        self.disabled = False
        self.alerted_mgmt_fee_zero = False
        self.alerted_curr_fee_zero = False

    def set_address(self, address):
        self.address = address
        return self

    def set_dec_fee(self, dec_fee):
        self.dec_fee = float(dec_fee)
        return self

    def set_jxr_code(self, jxr_code):
        self.jxr_code = jxr_code
        return self

    def set_billing_spec(self, billing_spec):
        self.billing_spec = billing_spec
        return self

    def set_value(self, value):
        try:
            self.value = float(value)
        except:
            print("tried to set this value: " + value)
        return self

    def set_previous_value(self, value):
        try:
            self.prev_value = float(value)
        except:
            print("tried to set this prev value: " + value)
        return self

    def set_legacy_id(self, legacy_id):
        self.legacy_id = legacy_id
        return self

    def set_netflow(self, netflow):
        self.netflow = float(netflow)
        return self

    def value_as_currency(self):
        return format_currency(self.value)

    def amount_to_bill(self):
        if self.min_fee_applies():
            if self.disabled:
                return 0
            else:
                return self.min_fee()
        else:
            return self.curr_fee

    def _calculate_tiered_fees(self, asset_ranges, rates, sub_amounts):
        for i in range(len(rates)):
            self.billing_tiers.append(
                BillingTier()
                .set_asset_range(asset_ranges[i])
                .set_rate(rates[i])
            )

        curr_value = self.value
        current_tier_index = 0
        while curr_value > 0:
            current_tier = self.billing_tiers[current_tier_index]
            (current_tier
            .set_amount(min(curr_value, (current_tier.asset_range[1] - current_tier.asset_range[0])))
            .set_fee_amount())

            curr_value -= (current_tier.asset_range[1] - current_tier.asset_range[0])
            # Update the top range of tier if the value is less than it.
            current_tier.asset_range[1] = min(current_tier.asset_range[1], self.value)
            current_tier_index += 1

        self.curr_fee = 0
        for tier in self.billing_tiers:
            self.curr_fee += tier.fee_amount

    def _calculate_standard_fee(self):
        asset_ranges = (
            [[0, 500000],
            [500000.01, 1000000],
            [1000000.01, 2000000],
            [2000000.01, 3000000],
            [3000000.01, 4000000],
            [4000000.01, 5000000]])
        rates = [0.003125, 0.0025, 0.00225, 0.002, 0.00175, 0.0015]
        sub_amounts = [0, 500000, 1000000, 1000000, 1000000, 1000000]
        self._calculate_tiered_fees(asset_ranges, rates, sub_amounts)

    def _calculate_step_down_fee(self):
        asset_ranges = (
            [[0, 500000],
            [500000.01, 1000000],
            [1000000.01, 2000000],
            [2000000.01, 3000000],
            [3000000.01, 4000000]])
        rates = [0.0025, 0.00225, 0.002, 0.00175, 0.0015]
        sub_amounts = [0, 500000, 1000000, 1000000, 1000000]
        self._calculate_tiered_fees(asset_ranges, rates, sub_amounts)

    def _calculate_flat_fee(self):
        self.curr_fee = 0.0015 * self.value 

    def calculate_current_fee(self):
        self.billing_tiers = []
        if self.billing_spec == 'ADVANCED STANDARD FEES':
            self._calculate_standard_fee()
        elif self.billing_spec == 'Advance - Over 5 Mil - Flat .60':
            self._calculate_flat_fee()
        elif self.billing_spec == 'Advance - One Step Down':
            self._calculate_step_down_fee()

    def min_fee(self):
        if self.value == 0 or self.prev_value == 0:
            return 0
        total_mgmt_fees = 0
        for account in self.accounts:
            total_mgmt_fees += account.mgmt_fees
        if total_mgmt_fees == 0 and not self.alerted_mgmt_fee_zero:
            self.alerted_mgmt_fee_zero = True
            print("0 management fees for: " + self.name)
        # The total management fees are a negative value, so we add that to netflows.
        portfolio_value_ratio = min(1, (self.prev_value + self.netflow + total_mgmt_fees) / self.prev_value)
        return 0.95 * self.dec_fee * portfolio_value_ratio

    def min_fee_applies(self):
        if (self.min_fee == 0 or self.curr_fee == 0) and not self.alerted_curr_fee_zero:
            self.alerted_curr_fee_zero = True
            print('client: ' + self.name + '. Min fee = ' + str(self.min_fee()) + '. Curr Fee = ' + str(self.curr_fee))
            self.disable()
        return self.min_fee() > self.curr_fee

    def disable(self):
        self.disabled = True